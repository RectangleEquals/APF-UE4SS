"""
CacheGraphWidget — compact, clickable cache usage graph for the Downloads tab header.

Replaces the plain MDLabel title with a rich visual element showing:
  - "Downloads" heading + total cache size
  - A proportional stacked horizontal bar, color-coded by category
  - Up to 4 legend rows (largest segments)

Clicking the widget opens CacheDetailDialog for a full interactive breakdown.
"""
from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

from .....core.controllers.logging.manager import APFLogManager

if TYPE_CHECKING:
    from ....models.state.cache_stats import CacheStats, CacheSegment

_log = APFLogManager.get_logger(__name__)

# Category color palette — kept in sync with DownloadsTab._CAT_ACCENT
_CAT_COLOR = {
    "mod":      (0.3,  0.5,  0.9,  1),
    "template": (0.2,  0.7,  0.6,  1),
    "other":    (0.8,  0.55, 0.1,  1),
}
_COL_EMPTY  = (0.25, 0.25, 0.28, 1)
_COL_TITLE  = (0.9,  0.9,  0.95, 1)
_COL_DIM    = (0.55, 0.55, 0.58, 1)
_COL_HOVER  = (1,    1,    1,    0.06)


class _StackedBar(BoxLayout):
    """
    A horizontal proportional stacked bar rendered via KV canvas instructions.

    Each segment is a child BoxLayout with md_bg_color; segments are sized
    proportionally to their share of total_bytes.
    """

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(8), **kwargs)

    def update(self, segments: list, total_bytes: int) -> None:
        self.clear_widgets()
        if total_bytes <= 0 or not segments:
            empty = MDBoxLayout(
                md_bg_color=_COL_EMPTY,
                size_hint=(1, 1),
                radius=[dp(3)],
            )
            self.add_widget(empty)
            return

        sorted_segs = sorted(segments, key=lambda s: s.size_bytes, reverse=True)
        for i, seg in enumerate(sorted_segs):
            if seg.size_bytes <= 0:
                continue
            frac = seg.size_bytes / total_bytes
            color = _CAT_COLOR.get(seg.category, (0.5, 0.5, 0.5, 1))
            # Round outer corners on first and last visible segment
            radius = []
            is_first = (i == 0)
            is_last  = (i == len(sorted_segs) - 1)
            if is_first and is_last:
                radius = [dp(3)]
            elif is_first:
                radius = [dp(3), 0, 0, dp(3)]
            elif is_last:
                radius = [0, dp(3), dp(3), 0]
            seg_widget = MDBoxLayout(
                md_bg_color=color,
                size_hint=(frac, 1),
                radius=radius or [0],
            )
            self.add_widget(seg_widget)


class _LegendRow(MDBoxLayout):
    """Single legend entry: colored dot + label text + size string."""

    def __init__(self, segment: "CacheSegment", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=dp(16),
            spacing=dp(6),
            **kwargs,
        )
        color = _CAT_COLOR.get(segment.category, (0.5, 0.5, 0.5, 1))
        dot = MDBoxLayout(
            md_bg_color=color,
            size_hint=(None, None), width=dp(8), height=dp(8),
            pos_hint={"center_y": 0.5},
            radius=[dp(4)],
        )
        self.add_widget(dot)
        self.add_widget(MDLabel(
            text=segment.label,
            font_style="Label", role="small",
            size_hint=(1, 1),
            theme_text_color="Custom", text_color=_COL_DIM,
            shorten=True, shorten_from="right",
            halign="left", valign="middle",
        ))
        self.add_widget(MDLabel(
            text=segment.size_fmt,
            font_style="Label", role="small",
            size_hint=(None, 1), width=dp(58),
            theme_text_color="Custom", text_color=_COL_TITLE,
            halign="right", valign="middle",
        ))


class CacheGraphWidget(HoverBehavior, MDBoxLayout):
    """
    Compact, clickable cache graph widget for the Downloads tab toolbar.

    Parameters
    ----------
    on_click   : callable(stats) — called on tap; receives the current CacheStats
    on_refresh : callable() — called when the inline refresh button is pressed
    """

    def __init__(
        self,
        on_click: Optional[Callable] = None,
        on_refresh: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            size_hint_y=None, adaptive_height=True,
            padding=[dp(8), dp(4), dp(4), dp(4)],
            spacing=dp(2),
            **kwargs,
        )
        self._on_click = on_click
        self._on_refresh = on_refresh
        self._stats: Optional["CacheStats"] = None
        self._hovering = False

        self._header_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(4),
        )
        self._title_lbl = MDLabel(
            text="Downloads",
            font_style="Title", role="medium",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom", text_color=_COL_TITLE,
        )
        self._size_lbl = MDLabel(
            text="",
            font_style="Label", role="small",
            size_hint=(None, 1), width=dp(80),
            halign="right", valign="middle",
            theme_text_color="Custom", text_color=_COL_DIM,
        )
        from .....core.views.widgets.tip_icon_button import TipIconButton
        self._refresh_btn = TipIconButton(
            icon="refresh",
            tooltip_text="Rescan cache",
            on_release=lambda *_: self._on_refresh() if self._on_refresh else None,
        )
        self._header_row.add_widget(self._title_lbl)
        self._header_row.add_widget(self._size_lbl)
        self._header_row.add_widget(self._refresh_btn)
        self.add_widget(self._header_row)

        self._bar = _StackedBar()
        self.add_widget(self._bar)

        self._legend_box = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            spacing=dp(1), padding=[dp(2), dp(2), 0, 0],
        )
        self.add_widget(self._legend_box)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, stats: "CacheStats") -> None:
        """Rebuild the visual with fresh CacheStats. Must be called on the Kivy main thread."""
        self._stats = stats
        if stats.is_empty:
            self._size_lbl.text = ""
            self._bar.update([], 0)
            self._legend_box.clear_widgets()
            return

        self._size_lbl.text = stats.total_fmt
        self._bar.update(stats.segments, stats.total_bytes)

        self._legend_box.clear_widgets()
        for seg in stats.top_segments:
            self._legend_box.add_widget(_LegendRow(segment=seg))

    # ------------------------------------------------------------------
    # Hover feedback (HoverBehavior overrides)
    # ------------------------------------------------------------------

    def on_enter(self):
        if self._hovering:
            return
        self._hovering = True
        from kivy.core.window import Window
        Window.set_system_cursor("hand")

    def on_leave(self):
        if not self._hovering:
            return
        self._hovering = False
        from kivy.core.window import Window
        Window.set_system_cursor("arrow")

    def on_parent(self, widget, parent):
        if parent is None:
            self._hovering = False
            from kivy.core.window import Window
            Window.set_system_cursor("arrow")

    # ------------------------------------------------------------------
    # Touch / click
    # ------------------------------------------------------------------

    def on_touch_up(self, touch):
        # Refresh button owns its own touch — do not intercept it as a graph click.
        if self._refresh_btn and self._refresh_btn.collide_point(*touch.pos):
            return super().on_touch_up(touch)
        if self.collide_point(*touch.pos) and self._on_click and self._stats:
            if not self._stats.is_empty:
                self._on_click(self._stats)
                return True
        return super().on_touch_up(touch)
