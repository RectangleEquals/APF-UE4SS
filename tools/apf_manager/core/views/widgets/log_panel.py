"""
LogPanel — scrollable, timestamped log widget shared across all hub panels.

Keeps the last MAX_LINES lines. Has a collapse/expand toggle.
"""

from __future__ import annotations

from datetime import datetime

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

MAX_LINES = 500


class LogPanel(MDBoxLayout):
    collapsed = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, **kwargs)
        self._lines: list[str] = []
        self._build()

    def _build(self):
        # Header bar
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

        # Scroll area
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

    def append(self, message: str) -> None:
        """Add a log line (or multiple lines for multiline messages). Thread-safe."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        lines = message.split("\n")
        Clock.schedule_once(lambda dt: self._add_line(f"[{ts}] {lines[0]}"))
        for cont in lines[1:]:
            stripped = cont.strip()
            if stripped:
                Clock.schedule_once(lambda dt, l=stripped: self._add_line(f"  {l}"))

    def _add_line(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > MAX_LINES:
            self._lines.pop(0)
            if self._content.children:
                self._content.remove_widget(self._content.children[-1])

        lbl = MDLabel(
            text=line,
            font_style="Label", role="small",
            size_hint_y=None,
            height="16dp",
            halign="left",
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
