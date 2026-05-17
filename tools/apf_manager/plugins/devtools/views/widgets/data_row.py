"""DevDataRow — base row widget and DevHeaderRow for DevTools tabs."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.animation import Animation
from kivy.metrics import dp
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

_BG_ROW_EVEN = (0.11, 0.12, 0.15, 1)
_BG_ROW_ODD  = (0.09, 0.10, 0.13, 1)
_BG_HEADER   = (0.07, 0.08, 0.10, 1)
_BG_HOVER    = (1, 1, 1, 0.06)

_ROW_H   = 40   # dp — data row height
_HDR_H   = 36   # dp — header row height


class DevDataRow(HoverBehavior, MDBoxLayout):
    """
    Horizontal data row base class for DevTools tabs.

    Fixed height (40 dp), alternating backgrounds, animated hover highlight,
    and optional on_press callback.  Primary/name columns use size_hint_x=1;
    action columns use explicit dp widths — both must match the header exactly.
    """

    def __init__(
        self,
        hover: bool = True,
        row_index: int = 0,
        on_press: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        base_bg = _BG_ROW_EVEN if row_index % 2 == 0 else _BG_ROW_ODD
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(_ROW_H),
            spacing=dp(8),
            padding=(dp(8), 0, dp(8), 0),
            md_bg_color=base_bg,
            **kwargs,
        )
        self._base_bg = base_bg
        self._hover_enabled = hover
        self._on_press_cb = on_press

    # -----------------------------------------------------------------------
    # HoverBehavior callbacks
    # -----------------------------------------------------------------------

    def on_enter(self):
        if not self._hover_enabled:
            return
        Animation.cancel_all(self, "md_bg_color")
        Animation(md_bg_color=_BG_HOVER, duration=0.08, t="out_quad").start(self)

    def on_leave(self):
        if not self._hover_enabled:
            return
        Animation.cancel_all(self, "md_bg_color")
        Animation(md_bg_color=self._base_bg, duration=0.12, t="out_quad").start(self)

    def on_parent(self, widget, parent):
        if parent is None:
            Animation.cancel_all(self, "md_bg_color")
            self.md_bg_color = self._base_bg

    # -----------------------------------------------------------------------
    # Press
    # -----------------------------------------------------------------------

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self._on_press_cb:
            self._on_press_cb()
        return super().on_touch_down(touch)


class DevHeaderRow(MDBoxLayout):
    """
    Header row matching DevDataRow column layout.
    Fixed height (36 dp), slightly darker background, Secondary text color.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(_HDR_H),
            spacing=dp(8),
            padding=(dp(8), 0, dp(8), 0),
            md_bg_color=_BG_HEADER,
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

        size_hint_x=1   → flexible column (fills remaining width)
        size_hint_x=None → fixed-width column; width taken from fixed_widths[i] or dp(36)
        """
        row = cls()
        fw = fixed_widths or {}
        for i, (text, shx) in enumerate(columns):
            lbl = MDLabel(
                text=text,
                size_hint_y=1,
                valign="middle",
                halign="left",
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