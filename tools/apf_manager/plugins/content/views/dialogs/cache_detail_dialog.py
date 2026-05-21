"""
CacheDetailDialog — full interactive cache breakdown modal for the Downloads tab.

Shows a detailed proportional stacked bar, per-category/per-game segment rows
with individual "Free" buttons, and bulk actions to free game-scoped or all
cached data.  Opened by clicking the CacheGraphWidget in the Downloads toolbar.
"""
from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.divider import MDDivider

from .....core.controllers.logging.manager import APFLogManager
from ..chrome.constants import COL_DIM, COL_WARN

if TYPE_CHECKING:
    from ....models.state.cache_stats import CacheStats, CacheSegment
    from ....controllers.tabs.downloads.cache import CacheController

_log = APFLogManager.get_logger(__name__)

_CAT_COLOR = {
    "mod":      (0.3,  0.5,  0.9,  1),
    "template": (0.2,  0.7,  0.6,  1),
    "other":    (0.8,  0.55, 0.1,  1),
}
_CAT_HEADING = {
    "mod":      "Mods",
    "template": "Templates",
    "other":    "Binaries / Other",
}
_COL_TITLE   = (0.9,  0.9,  0.95, 1)
_COL_DIM_LBL = (0.55, 0.55, 0.58, 1)
_COL_DANGER  = (0.85, 0.3,  0.3,  1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _DetailStackedBar(MDBoxLayout):
    """Larger proportional stacked bar for the detail dialog header."""

    def __init__(self, stats: "CacheStats", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=dp(14),
            **kwargs,
        )
        if stats.is_empty or not stats.segments:
            self.add_widget(MDBoxLayout(
                md_bg_color=(0.25, 0.25, 0.28, 1),
                size_hint=(1, 1),
                radius=[dp(4)],
            ))
            return

        sorted_segs = sorted(stats.segments, key=lambda s: s.size_bytes, reverse=True)
        for i, seg in enumerate(sorted_segs):
            if seg.size_bytes <= 0:
                continue
            frac = seg.size_bytes / stats.total_bytes
            color = _CAT_COLOR.get(seg.category, (0.5, 0.5, 0.5, 1))
            is_first = (i == 0)
            is_last  = (i == len(sorted_segs) - 1)
            if is_first and is_last:
                radius = [dp(4)]
            elif is_first:
                radius = [dp(4), 0, 0, dp(4)]
            elif is_last:
                radius = [0, dp(4), dp(4), 0]
            else:
                radius = [0]
            self.add_widget(MDBoxLayout(
                md_bg_color=color,
                size_hint=(frac, 1),
                radius=radius,
            ))


class _SegmentRow(MDBoxLayout):
    """One row in the breakdown list: colored dot + label + size + Free button."""

    def __init__(
        self,
        segment: "CacheSegment",
        on_free: Callable,
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=dp(36),
            spacing=dp(8),
            padding=[dp(4), 0],
            **kwargs,
        )
        color = _CAT_COLOR.get(segment.category, (0.5, 0.5, 0.5, 1))
        dot = MDBoxLayout(
            md_bg_color=color,
            size_hint=(None, None), width=dp(10), height=dp(10),
            pos_hint={"center_y": 0.5},
            radius=[dp(5)],
        )
        self.add_widget(dot)
        self.add_widget(MDLabel(
            text=segment.label,
            font_style="Label", role="medium",
            size_hint=(1, 1),
            theme_text_color="Custom", text_color=_COL_TITLE,
            shorten=True, shorten_from="right",
            halign="left", valign="middle",
        ))
        count_txt = f"{segment.item_count} item{'s' if segment.item_count != 1 else ''}"
        self.add_widget(MDLabel(
            text=count_txt,
            font_style="Label", role="small",
            size_hint=(None, 1), width=dp(70),
            theme_text_color="Custom", text_color=_COL_DIM_LBL,
            halign="right", valign="middle",
        ))
        self.add_widget(MDLabel(
            text=segment.size_fmt,
            font_style="Label", role="medium",
            size_hint=(None, 1), width=dp(70),
            theme_text_color="Custom", text_color=_COL_TITLE,
            halign="right", valign="middle",
        ))
        free_btn = MDButton(
            MDButtonText(text="Free"),
            style="text",
            size_hint=(None, None), size=(dp(56), dp(30)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: on_free(segment),
        )
        self.add_widget(free_btn)


class _CategorySection(MDBoxLayout):
    """Collapsible category group: heading + per-segment rows."""

    def __init__(
        self,
        category: str,
        segments: list,
        on_free_segment: Callable,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            size_hint_y=None, adaptive_height=True,
            spacing=dp(2),
            **kwargs,
        )
        color = _CAT_COLOR.get(category, (0.5, 0.5, 0.5, 1))
        heading_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=dp(28),
            spacing=dp(6),
            padding=[0, dp(4), 0, 0],
        )
        heading_row.add_widget(MDBoxLayout(
            md_bg_color=color,
            size_hint=(None, None), width=dp(3), height=dp(16),
            pos_hint={"center_y": 0.5},
            radius=[dp(1)],
        ))
        heading_row.add_widget(MDLabel(
            text=_CAT_HEADING.get(category, category.capitalize()),
            font_style="Label", role="large",
            size_hint=(1, 1),
            theme_text_color="Custom", text_color=_COL_TITLE,
            halign="left", valign="middle",
        ))
        self.add_widget(heading_row)

        for seg in sorted(segments, key=lambda s: s.size_bytes, reverse=True):
            self.add_widget(_SegmentRow(segment=seg, on_free=on_free_segment))


# ---------------------------------------------------------------------------
# Public dialog class
# ---------------------------------------------------------------------------

class CacheDetailDialog:
    """
    Full cache breakdown dialog, opened by CacheGraphWidget.

    Parameters
    ----------
    stats      : CacheStats — snapshot at the time of opening; refreshed after free ops
    ctrl       : CacheController — handles all I/O (free operations)
    on_refresh : Callable — triggers _scan_cache_and_rebuild() on the downloads tab
    """

    def __init__(
        self,
        stats: "CacheStats",
        ctrl: "CacheController",
        on_refresh: Callable,
    ):
        self._stats = stats
        self._ctrl = ctrl
        self._on_refresh = on_refresh
        self._dialog: Optional[MDDialog] = None
        self._content_area: Optional[MDBoxLayout] = None

    def open(self) -> None:
        if self._dialog:
            self._dialog.dismiss()
        self._dialog = self._build()
        self._dialog.open()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> MDDialog:
        self._content_area = self._build_content(self._stats)
        game_id = self._stats.game_id
        game_name = (game_id.replace("_", " ").title() if game_id else "")

        btn_close = MDButton(
            MDButtonText(text="Close"),
            style="text",
            on_release=lambda *_: self._dialog.dismiss() if self._dialog else None,
        )
        btn_free_game = MDButton(
            MDButtonText(
                text=f"Free {game_name} data" if game_name else "Free game data",
                theme_text_color="Custom",
                text_color=_COL_DANGER,
            ),
            style="text",
            on_release=lambda *_: self._free_game(),
        )
        btn_free_all = MDButton(
            MDButtonText(
                text="Free all cached data",
                theme_text_color="Custom",
                text_color=_COL_DANGER,
            ),
            style="text",
            on_release=lambda *_: self._free_all(),
        )

        has_game_data = game_id and any(
            s.game_id == game_id and s.category in ("mod", "template")
            for s in self._stats.segments
        )

        button_container = MDDialogButtonContainer(spacing=dp(4))
        if has_game_data:
            button_container.add_widget(btn_free_game)
        button_container.add_widget(Widget(size_hint_x=1))
        button_container.add_widget(btn_free_all)
        button_container.add_widget(btn_close)

        return MDDialog(
            MDDialogHeadlineText(text="Cache Details"),
            MDDialogSupportingText(
                text=f"Total cached: {self._stats.total_fmt}",
            ),
            MDDialogContentContainer(self._content_area),
            button_container,
            size_hint=(0.85, None),
        )

    def _build_content(self, stats: "CacheStats") -> MDBoxLayout:
        wrapper = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None, adaptive_height=True,
            spacing=dp(6),
            padding=[0, dp(4)],
        )

        # Large stacked bar
        wrapper.add_widget(_DetailStackedBar(stats=stats))

        if stats.is_empty:
            wrapper.add_widget(MDLabel(
                text="No cached data found.",
                font_style="Body", role="small",
                size_hint_y=None, height=dp(32),
                theme_text_color="Custom", text_color=_COL_DIM_LBL,
                halign="center", valign="middle",
            ))
            return wrapper

        # Group segments by category
        by_cat: dict = {"mod": [], "template": [], "other": []}
        for seg in stats.segments:
            by_cat.setdefault(seg.category, []).append(seg)

        scroll = MDScrollView(size_hint=(1, None), height=dp(320))
        list_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None, adaptive_height=True,
            spacing=dp(8),
        )

        for cat in ("mod", "template", "other"):
            segs = by_cat.get(cat, [])
            if not segs:
                continue
            list_box.add_widget(_CategorySection(
                category=cat,
                segments=segs,
                on_free_segment=self._free_segment,
            ))
            list_box.add_widget(MDDivider())

        scroll.add_widget(list_box)
        wrapper.add_widget(scroll)
        return wrapper

    # ------------------------------------------------------------------
    # Free operations
    # ------------------------------------------------------------------

    def _free_segment(self, segment: "CacheSegment") -> None:
        self._ctrl.free_segments([segment], on_done=self._on_free_done)

    def _free_game(self) -> None:
        if not self._stats.game_id:
            return
        game_segs = [
            s for s in self._stats.segments
            if s.game_id == self._stats.game_id and s.category in ("mod", "template")
        ]
        if game_segs:
            self._ctrl.free_segments(game_segs, on_done=self._on_free_done)

    def _free_all(self) -> None:
        self._ctrl.free_segments(list(self._stats.segments), on_done=self._on_free_done)

    def _on_free_done(self) -> None:
        """Called on the main Kivy thread after a free operation completes."""
        self._on_refresh()
        # Dismiss and let the user re-open for an updated view
        if self._dialog:
            self._dialog.dismiss()
