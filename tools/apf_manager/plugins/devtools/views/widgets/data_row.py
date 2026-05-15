"""DevDataRow — base row widget and DevHeaderRow for DevTools tabs."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.animation import Animation
from kivy.metrics import dp
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel


class DevDataRow(HoverBehavior, MDBoxLayout):
    """
    Horizontal data row base class for DevTools tabs.

    Provides consistent spacing/padding, animated hover highlight (via HoverBehavior),
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
    # HoverBehavior callbacks
    # -----------------------------------------------------------------------

    def on_enter(self):
        if not self._hover_enabled:
            return
        Animation(md_bg_color=(1, 1, 1, 0.06), duration=0.10).start(self)

    def on_leave(self):
        if not self._hover_enabled:
            return
        Animation(md_bg_color=(0, 0, 0, 0), duration=0.10).start(self)

    def on_parent(self, widget, parent):
        if parent is None:
            Animation.cancel_all(self, "md_bg_color")
            self.md_bg_color = (0, 0, 0, 0)

    # -----------------------------------------------------------------------
    # Press
    # -----------------------------------------------------------------------

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self._on_press_cb:
            self._on_press_cb()
        return super().on_touch_down(touch)


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
    def from_columns(
        cls,
        columns: list[tuple[str, Optional[float]]],
        fixed_widths: Optional[dict[int, float]] = None,
    ) -> "DevHeaderRow":
        """
        Build a header row from [(label_text, size_hint_x), ...].

        Pass size_hint_x=None for fixed-width columns.  When size_hint_x is None
        and the column index appears in fixed_widths, that pixel value is used;
        otherwise falls back to dp(36).
        """
        row = cls()
        fw = fixed_widths or {}
        for i, (text, shx) in enumerate(columns):
            lbl = MDLabel(
                text=text,
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            )
            if shx is None:
                lbl.size_hint_x = None
                lbl.width = fw.get(i, dp(36))
            else:
                lbl.size_hint_x = shx
            row.add_widget(lbl)
        return row
