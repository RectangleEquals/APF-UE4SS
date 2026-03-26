"""
HTMLViewerService — displays HTML in a frameless pywebview window.

Features:
- Frameless window (no OS title bar) with an injected sticky title bar
- Injected close button calls Python via js_api
- Kivy ModalView overlay dims the app while the window is open
- on_top=True keeps the viewer above the Kivy app
- Optional extra_api: caller-supplied object whose public methods are also
  exposed to JavaScript alongside the built-in close() method

Usage (simple doc):
    svc = host.get_service("html_viewer")
    svc.show("My Doc", html_string)

Usage (with extra JS API, e.g. for the docs browser SPA):
    class MyAPI:
        def get_data(self, key): ...
    svc.show("Browser", spa_html, extra_api=MyAPI(), inject_titlebar=False)
"""

from __future__ import annotations

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
        # Insert after the opening <body> tag
        idx = html.index("<body")
        end = html.index(">", idx) + 1
        return html[:end] + bar + html[end:]
    return bar + html


# ---------------------------------------------------------------------------
# Combined API builder
# ---------------------------------------------------------------------------

def _build_api(win_ref: list, extra=None):
    """
    Build a combined js_api object:
      - Built-in close() method that destroys the webview window
      - All public callable methods from extra (if provided)
    """
    class _API:
        def close(self):
            if win_ref[0] is not None:
                win_ref[0].destroy()

    if extra is not None:
        for name in dir(extra):
            if name.startswith("_") or name == "close":
                continue
            try:
                method = getattr(extra, name)
                if callable(method):
                    # Capture `method` value at loop time to avoid closure issue
                    setattr(
                        _API, name,
                        lambda self, *args, _m=method, **kwargs: _m(*args, **kwargs),
                    )
            except AttributeError:
                pass

    return _API()


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
        extra_api=None,
        inject_titlebar: bool = True,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Open a frameless pywebview window showing the given HTML.

        title          — Window title + title bar label
        html           — Full HTML document string
        width/height   — Initial window size in pixels
        extra_api      — Optional object; its public methods are exposed to JS
                         alongside the built-in close() method
        inject_titlebar — If True (default), prepend a draggable title bar with
                          close button. Set False when the HTML already has its own.
        on_closed      — Callback fired (on Kivy main thread) when window closes
        """
        from kivy.clock import Clock
        from kivy.uix.modalview import ModalView

        overlay = ModalView(overlay_color=(0, 0, 0, 0.55), auto_dismiss=False)
        overlay.open()

        final_html = _inject_titlebar(title, html) if inject_titlebar else html

        def _run():
            try:
                import webview

                win_ref: list = [None]
                api = _build_api(win_ref, extra_api)

                win = webview.create_window(
                    title,
                    html=final_html,
                    frameless=True,
                    on_top=True,
                    easy_drag=False,
                    js_api=api,
                    width=width,
                    height=height,
                )
                win_ref[0] = win

                def _on_closed():
                    Clock.schedule_once(lambda dt: overlay.dismiss())
                    if on_closed:
                        Clock.schedule_once(lambda dt: on_closed())

                win.events.closed += _on_closed
                webview.start(gui="edgechromium")

            except Exception as exc:
                # If webview fails to start, dismiss overlay immediately
                Clock.schedule_once(lambda dt: overlay.dismiss())
                Clock.schedule_once(
                    lambda dt, e=exc: print(f"[html_viewer] webview error: {e}")
                )

        threading.Thread(target=_run, daemon=True).start()
