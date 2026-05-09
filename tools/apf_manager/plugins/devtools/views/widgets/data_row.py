"""DevDataRow — base row widget and DevHeaderRow for DevTools tabs."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.animation import Animation
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel


class DevDataRow(MDBoxLayout):
    """
    Horizontal data row base class for DevTools tabs.

    Provides consistent spacing/padding, optional hover highlight,
    and optional on_press callback. Subclasses add typed cells via add_cell().
    """

    def __init__(
        self,
        hover: bool = True,
        on_press: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            orientation="horizontal",
            adaptive_height=True,
            spacing=dp(8),
            padding=(0, dp(4), 0, dp(4)),
            **kwargs,
        )
        self._hover_enabled = hover
        self._on_press_cb = on_press
        self._hover_alpha = 0.0
        self._rect: Optional[Rectangle] = None
        self._color_instr: Optional[Color] = None
        if hover:
            self._setup_hover_canvas()

    # -----------------------------------------------------------------------
    # Public helpers
    # -----------------------------------------------------------------------

    def add_cell(
        self,
        widget,
        size_hint_x: Optional[float] = None,
        fixed_width: Optional[float] = None,
    ) -> None:
        if fixed_width is not None:
            widget.size_hint_x = None
            widget.width = dp(fixed_width)
        elif size_hint_x is not None:
            widget.size_hint_x = size_hint_x
        self.add_widget(widget)

    # -----------------------------------------------------------------------
    # Hover
    # -----------------------------------------------------------------------

    def _setup_hover_canvas(self) -> None:
        with self.canvas.before:
            self._color_instr = Color(1, 1, 1, 0)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_) -> None:
        if self._rect:
            self._rect.pos = self.pos
            self._rect.size = self.size

    def on_touch_move(self, touch):
        if self._hover_enabled and self.collide_point(*touch.pos):
            self._set_hover(True)
        else:
            self._set_hover(False)
        return super().on_touch_move(touch)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self._on_press_cb:
                self._set_hover(False)
                self._on_press_cb()
        return super().on_touch_down(touch)

    def _set_hover(self, active: bool) -> None:
        if not self._hover_enabled or not self._color_instr:
            return
        target = 0.06 if active else 0.0
        if abs(self._hover_alpha - target) < 0.01:
            return
        self._hover_alpha = target
        Animation(a=target, duration=0.12).start(self._color_instr)


class DevHeaderRow(MDBoxLayout):
    """
    Header row matching DevDataRow column layout, no hover, Secondary text color.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            orientation="horizontal",
            adaptive_height=True,
            spacing=dp(8),
            padding=(0, dp(2), 0, dp(2)),
            **kwargs,
        )

    @classmethod
    def from_columns(cls, columns: list[tuple[str, Optional[float]]]) -> "DevHeaderRow":
        """
        Build a header row from [(label_text, size_hint_x), ...].
        Pass size_hint_x=None for fixed-width spacer columns (uses dp(36)).
        """
        row = cls()
        for text, shx in columns:
            lbl = MDLabel(
                text=text,
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            )
            if shx is None:
                lbl.size_hint_x = None
                lbl.width = dp(36)
            else:
                lbl.size_hint_x = shx
            row.add_widget(lbl)
        return row
