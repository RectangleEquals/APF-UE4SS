"""BusyOverlay — full-screen semi-translucent overlay with animated throbber.

Shown/hidden by BusyService; never dismissed by the user (auto_dismiss=False).
All public methods must be called on the main Kivy thread (BusyService handles
the Clock.schedule_once routing).
"""
from __future__ import annotations


class BusyOverlay:
    """
    Semi-translucent full-screen overlay with animated throbber and status text.

    Lazily constructs its widgets on first show so it's safe to instantiate
    before the Kivy window is fully initialised.
    """

    def __init__(self) -> None:
        self._modal = None
        self._label = None
        self._built = False

    # -----------------------------------------------------------------------
    # Public API (main thread only)
    # -----------------------------------------------------------------------

    def show(self, message: str = "Working...") -> None:
        self._ensure_built()
        if self._label:
            self._label.text = message
        if self._modal and not self._modal.parent:
            self._modal.open()

    def hide(self) -> None:
        if self._modal and self._modal.parent:
            self._modal.dismiss()

    def set_message(self, message: str) -> None:
        if self._label:
            self._label.text = message

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _ensure_built(self) -> None:
        if self._built:
            return
        self._built = True

        from kivy.metrics import dp
        from kivy.uix.modalview import ModalView
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.label import MDLabel
        from kivymd.uix.progressindicator import MDCircularProgressIndicator

        self._modal = ModalView(
            size_hint=(1, 1),
            background="",
            background_color=(0, 0, 0, 0.65),
            overlay_color=(0, 0, 0, 0),
            auto_dismiss=False,
        )

        container = MDBoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            width=dp(240),
            adaptive_height=True,
            spacing=dp(16),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            padding=(dp(24), dp(24)),
        )

        spinner_wrap = MDBoxLayout(
            orientation="vertical",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(56),
        )
        spinner = MDCircularProgressIndicator(
            size_hint=(None, None),
            size=(dp(48), dp(48)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        spinner_wrap.add_widget(spinner)
        container.add_widget(spinner_wrap)

        self._label = MDLabel(
            text="Working...",
            halign="center",
            adaptive_height=True,
            theme_text_color="Custom",
            text_color=(0.85, 0.85, 0.85, 1),
        )
        container.add_widget(self._label)

        self._modal.add_widget(container)
