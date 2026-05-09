"""
LogPanel — scrollable log widget. Receives pre-formatted records from APFPanelHandler.

Level-based coloring: DEBUG=gray · INFO=white · WARNING=amber · ERROR=red
"""

from __future__ import annotations

import logging
from datetime import datetime

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.properties import BooleanProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

_LEVEL_COLORS: dict[int, tuple] = {
    logging.DEBUG:    (0.5,  0.5,  0.5,  1),
    logging.INFO:     (0.9,  0.9,  0.9,  1),
    logging.WARNING:  (1.0,  0.75, 0.0,  1),
    logging.ERROR:    (1.0,  0.35, 0.35, 1),
    logging.CRITICAL: (1.0,  0.2,  0.2,  1),
}


def _color_for_level(level: int) -> tuple:
    for threshold in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG):
        if level >= threshold:
            return _LEVEL_COLORS[threshold]
    return _LEVEL_COLORS[logging.DEBUG]


class LogPanel(MDBoxLayout):
    collapsed = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, **kwargs)
        self._lines: list[str] = []
        self._build()

    def _build(self):
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="36dp",
            md_bg_color=(0.12, 0.12, 0.12, 1),
            padding=("8dp", 0),
        )
        lbl = MDLabel(
            text="Log",
            font_style="Label", role="small",
            halign="left",
            size_hint_x=1,
        )
        copy_btn = MDIconButton(
            icon="content-copy",
            on_release=self._on_copy,
            size_hint_x=None,
            width=dp(36),
        )
        toggle_btn = MDIconButton(
            icon="chevron-down",
            on_release=self._toggle_collapse,
            size_hint_x=None,
            width=dp(36),
        )
        self._toggle_btn = toggle_btn
        header.add_widget(lbl)
        header.add_widget(copy_btn)
        header.add_widget(toggle_btn)
        self.add_widget(header)

        self._scroll = MDScrollView(size_hint_y=None, height="120dp")
        self._content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=("6dp", "4dp"),
            spacing="1dp",
        )
        self._content.bind(minimum_height=self._content.setter("height"))
        self._scroll.add_widget(self._content)
        self.add_widget(self._scroll)

        self._update_height()

    def _update_height(self):
        if self.collapsed:
            self._scroll.height = "0dp"
            self.height = "36dp"
            self._toggle_btn.icon = "chevron-up"
        else:
            self._scroll.height = "120dp"
            self.height = "156dp"
            self._toggle_btn.icon = "chevron-down"

    def _toggle_collapse(self, *_):
        self.collapsed = not self.collapsed
        self._update_height()

    def append(self, message: str, level: int = logging.INFO) -> None:
        """Add a pre-formatted log record. Thread-safe via Clock.schedule_once."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = _color_for_level(level)
        lines = message.split("\n")
        Clock.schedule_once(lambda dt: self._add_line(f"[{ts}] {lines[0]}", color))
        for cont in lines[1:]:
            stripped = cont.strip()
            if stripped:
                Clock.schedule_once(lambda dt, l=stripped, c=color: self._add_line(f"  {l}", c))

    def _add_line(self, line: str, color: tuple) -> None:
        self._lines.append(line)
        lbl = MDLabel(
            text=line,
            font_style="Label", role="small",
            size_hint_y=None,
            height="16dp",
            halign="left",
            theme_text_color="Custom",
            text_color=color,
        )
        self._content.add_widget(lbl)
        Clock.schedule_once(lambda dt: self._scroll_to_bottom())

    def _scroll_to_bottom(self):
        self._scroll.scroll_y = 0

    def _on_copy(self, *_) -> None:
        if self._lines:
            Clipboard.copy("\n".join(self._lines))
        MDSnackbar(
            MDSnackbarText(text="Log copied to clipboard."),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.6,
            duration=2,
        ).open()

    def clear(self) -> None:
        self._lines.clear()
        self._content.clear_widgets()
