"""
APF Manager — Log panel widget with inline fullscreen toggle.
"""

from __future__ import annotations

import datetime

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.properties import BooleanProperty
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout


class LogPanel(MDBoxLayout):
    """
    A scrollable log area with a fullscreen toggle button.
    Height expands to fill available space; toggle button is inline in the header.
    """

    fullscreen = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._lines: list[str] = []
        self._build_ui()

    def _build_ui(self):
        # Header bar with "Log" label and expand toggle
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="36dp",
            md_bg_color=self.theme_cls.primary_color if hasattr(self, "theme_cls") else (0.2, 0.4, 0.8, 1),
            padding=("8dp", "4dp"),
        )
        self._header_label = MDLabel(
            text="Log",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True,
        )
        self._toggle_btn = MDIconButton(
            icon="arrow-expand",
            theme_icon_color="Custom",
            icon_color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=("36dp", "36dp"),
        )
        self._toggle_btn.bind(on_release=self._toggle_fullscreen)
        header.add_widget(self._header_label)
        header.add_widget(self._toggle_btn)
        self.add_widget(header)

        # Scrollable text area
        scroll = ScrollView()
        self._text_label = MDLabel(
            text="",
            font_style="Body2",
            size_hint_y=None,
            markup=True,
        )
        self._text_label.bind(texture_size=self._text_label.setter("size"))
        scroll.add_widget(self._text_label)
        self._scroll = scroll
        self.add_widget(scroll)

    def append(self, msg: str) -> None:
        """Add a timestamped line to the log."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self._lines.append(line)
        # Keep last 500 lines to avoid unbounded growth
        if len(self._lines) > 500:
            self._lines = self._lines[-500:]
        self._text_label.text = "\n".join(self._lines)
        # Scroll to bottom
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(self._scroll, "scroll_y", 0))

    def clear(self) -> None:
        self._lines.clear()
        self._text_label.text = ""

    def _toggle_fullscreen(self, *_):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self._toggle_btn.icon = "arrow-collapse"
            # Request parent to give us all available space
            self.size_hint_y = 1
        else:
            self._toggle_btn.icon = "arrow-expand"
            self.size_hint_y = None
            self.height = "200dp"
