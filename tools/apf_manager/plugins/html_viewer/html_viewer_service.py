"""
HTMLViewerService — displays HTML in a frameless pywebview window.

Features:
- Frameless window (no OS title bar) with an injected sticky title bar
- Injected close button calls Python via js_api
- Kivy ModalView overlay dims the app while the window is open
- on_top=True keeps the viewer above the Kivy app

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
import tempfile
import threading
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

def _webview_process_main(html_path: str, title: str, width: int, height: int) -> None:
    """
    Runs in a separate process. Opens a frameless pywebview window and blocks
    until the window is closed.

    Must be module-level (not a nested function or lambda) to be picklable
    for multiprocessing's 'spawn' start method used by cx_Freeze.
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
        width/height   — Initial window size in pixels
        extra_api      — Reserved; currently a no-op (process boundary)
        inject_titlebar — If True (default), prepend a draggable title bar with
                          close button. Set False when the HTML already has its own.
        on_closed      — Callback fired (on Kivy main thread) when window closes
        """
        from kivy.clock import Clock
        from kivy.uix.modalview import ModalView

        overlay = ModalView(overlay_color=(0, 0, 0, 0.55), auto_dismiss=False)
        overlay.open()

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

        def _monitor():
            try:
                proc = multiprocessing.Process(
                    target=_webview_process_main,
                    args=(tmp_path, title, width, height),
                    daemon=True,
                )
                proc.start()
                proc.join()
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: print(f"[html_viewer] webview error: {err}")
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                Clock.schedule_once(lambda dt: overlay.dismiss())
                if on_closed:
                    Clock.schedule_once(lambda dt: on_closed())

        threading.Thread(target=_monitor, daemon=True).start()
