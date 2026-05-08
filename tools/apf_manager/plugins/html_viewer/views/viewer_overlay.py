"""
ViewerOverlay — Kivy ModalView scrim for the HTML viewer.

Manages:
  - Full-screen translucent ModalView while the webview window is open
  - Clock polling to write Window position/size to the SharedMemory buffer
  - Window on_minimize / on_restore binding for minimize-sync
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple


class ViewerOverlay:
    """
    Manages the Kivy-side overlay for the HTML viewer subprocess.

    Registered with HTMLViewerService at setup time. The service calls
    open()/dismiss() without importing any Kivy symbols itself.
    """

    def __init__(self) -> None:
        self._modal = None
        self._clock_ev = None
        self._write_shm: Optional[Callable] = None

    def open(
        self,
        width: int,
        height: int,
        write_shm: Callable[[int, int, int, int, bool], None],
    ) -> Tuple[int, int]:
        """
        Open the ModalView scrim and start SHM polling.

        write_shm(x, y, w, h, minimized) — service-provided callback that
        packs Window position data into the SharedMemory buffer.

        Returns (final_w, final_h) clamped to 90%/92% of the main window.
        """
        from kivy.clock import Clock
        from kivy.core.window import Window as _KW
        from kivy.uix.modalview import ModalView

        self._write_shm = write_shm

        final_w = max(900, min(width,  int(_KW.width  * 0.90)))
        final_h = max(620, min(height, int(_KW.height * 0.92)))

        self._modal = ModalView(
            size_hint=(1, 1),
            background="",
            background_color=(0, 0, 0, 0.7),
            overlay_color=(0, 0, 0, 0),
            auto_dismiss=False,
        )
        self._modal.open()

        def _poll(dt: float) -> None:
            write_shm(int(_KW.left), int(_KW.top), int(_KW.width), int(_KW.height), False)

        self._clock_ev = Clock.schedule_interval(_poll, 0.15)
        _poll(0)

        def _on_min(*_) -> None:
            write_shm(int(_KW.left), int(_KW.top), int(_KW.width), int(_KW.height), True)

        def _on_res(*_) -> None:
            write_shm(int(_KW.left), int(_KW.top), int(_KW.width), int(_KW.height), False)

        self._on_min = _on_min
        self._on_res = _on_res
        _KW.bind(on_minimize=_on_min, on_restore=_on_res)

        return final_w, final_h

    def dismiss(self) -> None:
        """Dismiss the ModalView and cancel the Clock interval."""
        from kivy.clock import Clock
        from kivy.core.window import Window as _KW

        if self._clock_ev:
            self._clock_ev.cancel()
            self._clock_ev = None

        _on_min = getattr(self, "_on_min", None)
        _on_res = getattr(self, "_on_res", None)
        if _on_min:
            _KW.unbind(on_minimize=_on_min)
        if _on_res:
            _KW.unbind(on_restore=_on_res)

        modal = self._modal
        if modal:
            self._modal = None
            Clock.schedule_once(lambda dt: modal.dismiss())
