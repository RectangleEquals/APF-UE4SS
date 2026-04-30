"""
PackageHeaderWidget — collapsible registry-scoped package group header.

Extends BaseContentRow with:
  - has_hover=True: HoverRow — entire header click toggles collapse
  - any_checked semantics: checkbox activates when ANY child is checked
  - No expand chevron (header click IS the toggle)
"""
from __future__ import annotations

from typing import Optional, Callable

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from .base_content_row import BaseContentRow


class PackageHeaderWidget(BaseContentRow):
    """
    Collapsible group header for registry-scoped mod packages.

    Parameters
    ----------
    pkg_id      : str — unique package identifier (e.g. "owner/repo")
    pkg_label   : str — display name shown on the header
    mod_count   : int — number of child mods in this package
    any_checked : bool — True when ANY child mod is currently checked
    on_toggle   : Callable[[], None] — called to toggle collapsed state
    on_check    : Callable[[bool], None] — called when group checkbox changes
    collapsed   : bool — current collapsed state
    """

    def __init__(
        self,
        pkg_id: str,
        pkg_label: str,
        mod_count: int,
        any_checked: bool,
        on_toggle: Optional[Callable] = None,
        on_check: Optional[Callable[[bool], None]] = None,
        collapsed: bool = False,
        **kwargs,
    ):
        self._pkg_id = pkg_id
        self._pkg_label = pkg_label
        self._mod_count = mod_count
        self._collapsed = collapsed

        super().__init__(
            row_index=0,
            checked=any_checked,
            expanded=False,
            on_check=on_check,
            on_expand=on_toggle,
            has_hover=True,
            header_height=40,
            show_chevron=False,
            expand_on_header=True,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # BaseContentRow interface
    # ------------------------------------------------------------------

    def _build_header_content(self, header, info_col) -> None:
        # Collapse/expand chevron icon (visual indicator only — header click triggers toggle)
        chevron = "chevron-right" if self._collapsed else "chevron-down"
        header.add_widget(MDIcon(
            icon=chevron,
            size_hint=(None, 1), width=dp(18),
            theme_icon_color="Custom", icon_color=(0.6, 0.6, 0.6, 1),
        ))

        # Package label
        info_col.add_widget(MDLabel(
            text=self._pkg_label,
            font_style="Label", role="medium",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        if self._mod_count:
            info_col.add_widget(MDLabel(
                text=f"{self._mod_count} mod{'s' if self._mod_count != 1 else ''}",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.5, 0.5, 1),
            ))

    def _build_right_side(self, header) -> None:
        # No right-side chevron — the whole header is the toggle target
        header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

    def _build_detail_content(self):
        return None
