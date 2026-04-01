"""
HTMLViewerService — displays HTML in a frameless pywebview window.

Features:
- Frameless window (no OS title bar) with an injected sticky title bar
- Injected close button calls Python via js_api
- Kivy ModalView overlay dims the app while the window is open
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
  window closes. A monitor daemon-thread waits for the process to exit, then dismisses
  the Kivy overlay and fires on_closed.

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
# Injected title bar snippet (prepended to <body> of every simple document)
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
    """Prepend a sticky draggable title bar with close button to the HTML body."""
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
) -> None:
    """
    Runs in a separate process. Opens a frameless pywebview window and blocks
    until the window is closed.

    Must be module-level (not a nested function or lambda) to be picklable
    for multiprocessing's 'spawn' start method used by cx_Freeze.

    shm_name — name of a SharedMemory segment written by the parent process
    every ~150ms with layout: struct.pack('iiiii', main_x, main_y, main_w, main_h, minimized)
    The tracking thread reads this and calls win.move()/hide()/show() accordingly.
    """
    import webview
    import webbrowser
    from pathlib import Path

    html = Path(html_path).read_text(encoding="utf-8")
    win_ref = [None]

    class _API:
        def close(self):
            if win_ref[0]:
                win_ref[0].destroy()

        def open_url(self, url):
            if url.startswith(("http://", "https://")):
                webbrowser.open(url)

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

    # ── Real-time tracking thread ──────────────────────────────────────────
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
    """

    def show(
        self,
        title: str,
        html: str,
        width: int = 1000,
        height: int = 750,
        extra_api=None,           # Reserved; not used (process boundary prevents this)
        inject_titlebar: bool = True,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Open a frameless pywebview window showing the given HTML.

        title          — Window title + title bar label
        html           — Full HTML document string
        width/height   — Requested window size; clamped to 90%/92% of main window
        extra_api      — Reserved; currently a no-op (process boundary)
        inject_titlebar — If True (default), prepend a draggable title bar with
                          close button. Set False when the HTML already has its own.
        on_closed      — Callback fired (on Kivy main thread) when window closes
        """
        from kivy.clock import Clock
        from kivy.core.window import Window as _KW
        from kivy.uix.modalview import ModalView

        # ── Fix 39-B: full-screen translucent scrim ────────────────────────
        # ModalView.overlay_color draws behind the panel, not as the panel.
        # Using background_color + size_hint=(1,1) + background='' gives a
        # reliable full-screen semi-transparent dim.
        overlay = ModalView(
            size_hint=(1, 1),
            background="",
            background_color=(0, 0, 0, 0.7),
            overlay_color=(0, 0, 0, 0),
            auto_dismiss=False,
        )
        overlay.open()

        # ── Fix 39-A: clamp window size to main window ────────────────────
        final_w = max(900, min(width,  int(_KW.width  * 0.90)))
        final_h = max(620, min(height, int(_KW.height * 0.92)))

        # ── Fix 39-A: shared memory for real-time position/minimize sync ──
        shm = SharedMemory(create=True, size=20)

        def _write_shm(minimized: bool = False) -> None:
            try:
                struct.pack_into(
                    "iiiii", shm.buf, 0,
                    int(_KW.left), int(_KW.top),
                    int(_KW.width), int(_KW.height),
                    1 if minimized else 0,
                )
            except Exception:
                pass

        _write_shm()

        clock_ev = Clock.schedule_interval(lambda dt: _write_shm(), 0.15)

        def _on_min(*_) -> None:
            _write_shm(True)

        def _on_res(*_) -> None:
            _write_shm(False)

        _KW.bind(on_minimize=_on_min, on_restore=_on_res)

        final_html = _inject_titlebar(title, html) if inject_titlebar else html

        # Write HTML to a temp file to avoid process arg-length limits
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
            try:
                proc = multiprocessing.Process(
                    target=_webview_process_main,
                    args=(tmp_path, title, final_w, final_h, shm.name),
                    daemon=True,
                )
                proc.start()
                proc.join()
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: print(f"[html_viewer] webview error: {err}")
                )
            finally:
                # Cancel clock + unbind on Kivy main thread
                def _cleanup(dt) -> None:
                    clock_ev.cancel()
                    _KW.unbind(on_minimize=_on_min, on_restore=_on_res)

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

                Clock.schedule_once(lambda dt: overlay.dismiss())
                if on_closed:
                    Clock.schedule_once(lambda dt: on_closed())

        threading.Thread(target=_monitor, daemon=True).start()
