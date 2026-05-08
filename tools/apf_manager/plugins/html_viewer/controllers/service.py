"""
HTMLViewerService — displays HTML in a frameless pywebview window.

Features:
- Frameless window (no OS title bar) with an injected sticky title bar
- Injected close button calls Python via js_api
- on_top=True keeps the viewer above the Kivy app
- Real-time window centering + minimize/restore sync via SharedMemory

Why multiprocessing (not threading or subprocess -c):
  pywebview.start() checks threading.current_thread().name != 'MainThread' and raises
  "pywebview must be run on a main thread." Kivy already owns the OS main thread, so
  daemon threads (named 'Thread-N') always fail.

  subprocess.Popen([sys.executable, "-c", code]) works in dev but fails in frozen builds
  because sys.executable becomes APFManager.exe (not a Python interpreter).

  Fix: multiprocessing.Process with a module-level target function. This works in both
  dev and frozen cx_Freeze builds — freeze_support() in __main__.py intercepts the
  multiprocessing respawn before the Kivy app loop starts.

  HTML is written to a temp file before spawning (avoids arg-length limits for large
  SPA content). The subprocess reads the file, opens the window, and exits when the
  window closes. A monitor daemon-thread waits for the process to exit, then calls
  the registered overlay dismiss callback and fires on_closed.

Usage:
    svc = host.get_service("html_viewer")
    svc.show("My Doc", html_string)
"""

from __future__ import annotations

import multiprocessing
import os
import struct
import tempfile
import threading
import time
from multiprocessing.shared_memory import SharedMemory
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Title bar styles
# ---------------------------------------------------------------------------

_TITLEBAR_STYLE = """
<style>
.apf-titlebar {
  position: sticky; top: 0; height: 40px; z-index: 9999;
  background: #161b22; border-bottom: 1px solid #30363d;
  display: flex; align-items: center; padding: 0 12px; gap: 8px;
  -webkit-app-region: drag;
}
.apf-titlebar .apf-title {
  flex: 1; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 13px; color: #8b949e; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.apf-titlebar .apf-close {
  -webkit-app-region: no-drag;
  background: #c0392b; color: white; border: none; border-radius: 4px;
  padding: 3px 10px; cursor: pointer; font-size: 13px; flex-shrink: 0;
}
.apf-titlebar .apf-close:hover { background: #e74c3c; }
</style>
"""


def _inject_titlebar(title: str, html: str) -> str:
    """Prepend a sticky draggable title bar with a close button."""
    bar = (
        f'{_TITLEBAR_STYLE}'
        f'<div class="apf-titlebar" pywebview-drag-region>'
        f'  <span class="apf-title">{title}</span>'
        f'  <button class="apf-close" onclick="pywebview.api.close()">&#x2715;</button>'
        f'</div>'
    )
    if "<body" in html:
        idx = html.index("<body")
        end = html.index(">", idx) + 1
        return html[:end] + bar + html[end:]
    return bar + html


# ---------------------------------------------------------------------------
# Multiprocessing worker — module-level so it's picklable for spawn
# ---------------------------------------------------------------------------

def _webview_process_main(
    html_path: str,
    title: str,
    width: int,
    height: int,
    shm_name: str,
    output_file: str = "",
) -> None:
    """
    Runs in a separate process. Opens a frameless pywebview window and blocks
    until the window is closed.

    Must be module-level (not a nested function or lambda) to be picklable
    for multiprocessing's 'spawn' start method used by cx_Freeze.

    shm_name — name of a SharedMemory segment written by the parent process
    every ~150ms with layout: struct.pack('iiiii', main_x, main_y, main_w, main_h, minimized)
    The tracking thread reads this and calls win.move()/hide()/show() accordingly.

    output_file — optional path to a file where confirm(data) will write the
    result string before closing. Used by SPA dialogs (e.g. Repo Viewer) to
    pass structured data back to the parent process across the process boundary.
    """
    import webview
    import webbrowser
    from pathlib import Path

    html = Path(html_path).read_text(encoding="utf-8")
    win_ref = [None]
    _out = output_file

    class _API:
        def close(self):
            if win_ref[0]:
                win_ref[0].destroy()

        def open_url(self, url):
            if url.startswith(("http://", "https://")):
                webbrowser.open(url)

        def confirm(self, data: str) -> None:
            """Write result data to output_file then close the window."""
            if _out:
                try:
                    Path(_out).write_text(data, encoding="utf-8")
                except Exception:
                    pass
            self.close()

    api = _API()

    win = webview.create_window(
        title,
        html=html,
        frameless=True,
        on_top=True,
        easy_drag=False,
        js_api=api,
        width=width,
        height=height,
    )
    win_ref[0] = win

    shm = SharedMemory(name=shm_name, create=False)
    _last_xy: list = [-9999, -9999]
    _prev_min: list = [False]

    def _track() -> None:
        try:
            while True:
                time.sleep(0.15)
                w = win_ref[0]
                if w is None:
                    break
                try:
                    mx, my, mw, mh, minimized = struct.unpack_from("iiiii", shm.buf)
                except Exception:
                    break
                is_min = bool(minimized)
                if is_min != _prev_min[0]:
                    w.hide() if is_min else w.show()
                    _prev_min[0] = is_min
                if not is_min:
                    nx = mx + (mw - width) // 2
                    ny = my + (mh - height) // 2
                    if abs(nx - _last_xy[0]) > 3 or abs(ny - _last_xy[1]) > 3:
                        w.move(nx, ny)
                        _last_xy[0] = nx
                        _last_xy[1] = ny
        except Exception:
            pass
        finally:
            try:
                shm.close()
            except Exception:
                pass

    threading.Thread(target=_track, daemon=True).start()
    webview.start(gui="edgechromium")


# ---------------------------------------------------------------------------
# HTMLViewerService
# ---------------------------------------------------------------------------

class HTMLViewerService:
    """
    Generic service for displaying HTML in a frameless native window.
    Registered as service "html_viewer" by the plugin setup().

    An overlay (ViewerOverlay) is registered at setup time via register_overlay().
    The overlay handles all Kivy concerns (ModalView, Clock, Window binding).
    The service handles subprocess spawning and SharedMemory coordination.
    """

    def __init__(self) -> None:
        self._overlay = None

    def register_overlay(self, overlay) -> None:
        """Register the ViewerOverlay that manages the Kivy ModalView scrim."""
        self._overlay = overlay

    def show(
        self,
        title: str,
        html: str,
        width: int = 1000,
        height: int = 750,
        extra_api=None,
        inject_titlebar: bool = True,
        on_closed: Optional[Callable[[], None]] = None,
        output_file: str = "",
    ) -> None:
        """
        Open a frameless pywebview window showing the given HTML.

        title          — Window title + title bar label
        html           — Full HTML document string
        width/height   — Requested window size; the overlay clamps to 90%/92% of main window
        extra_api      — Reserved; currently a no-op (process boundary)
        inject_titlebar — If True (default), prepend a draggable title bar with a close button.
                          Set False when the HTML already has its own chrome (e.g. SPA).
        on_closed      — Callback fired (on Kivy main thread) when window closes
        output_file    — Optional path where JS can write result data via
                          pywebview.api.confirm(data). Read by parent after on_closed.
        """
        shm = SharedMemory(create=True, size=20)

        def _write_shm(x: int, y: int, w: int, h: int, minimized: bool = False) -> None:
            try:
                struct.pack_into("iiiii", shm.buf, 0, x, y, w, h, 1 if minimized else 0)
            except Exception:
                pass

        # Overlay handles ModalView, Clock polling, Window binding.
        # It returns the clamped (final_w, final_h) for the subprocess.
        if self._overlay:
            final_w, final_h = self._overlay.open(width, height, _write_shm)
        else:
            final_w, final_h = width, height

        final_html = _inject_titlebar(title, html) if inject_titlebar else html

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(final_html)
        except Exception:
            try:
                os.close(tmp_fd)
            except OSError:
                pass

        def _monitor() -> None:
            from kivy.clock import Clock
            try:
                proc = multiprocessing.Process(
                    target=_webview_process_main,
                    args=(tmp_path, title, final_w, final_h, shm.name, output_file),
                    daemon=True,
                )
                proc.start()
                proc.join()
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: print(f"[html_viewer] webview error: {err}")
                )
            finally:
                def _cleanup(dt) -> None:
                    if self._overlay:
                        self._overlay.dismiss()

                Clock.schedule_once(_cleanup)

                try:
                    shm.close()
                    shm.unlink()
                except Exception:
                    pass

                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

                if on_closed:
                    from kivy.clock import Clock as _C
                    _C.schedule_once(lambda dt: on_closed())

        threading.Thread(target=_monitor, daemon=True).start()
