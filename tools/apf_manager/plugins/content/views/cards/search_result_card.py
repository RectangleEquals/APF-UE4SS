"""SearchResultCard — card for a single GitHub registry search result."""
from __future__ import annotations

import math
from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel


class SearchResultCard(MDBoxLayout):
    """
    Card displaying a GitHub search result for a registry.

    Parameters
    ----------
    result          : dict — {"owner", "repo", "html_url", "stars", "last_push_days"}
    is_blacklisted  : bool — when True, shows block warning and disables View button
    is_already_added: bool — when True, shows "Already Added" indicator
    on_view         : Callable[[str], None] — called with html_url
    on_report       : Callable[[str], None] — called with html_url
    """

    def __init__(
        self,
        result: dict,
        is_blacklisted: bool = False,
        is_already_added: bool = False,
        on_view: Optional[Callable] = None,
        on_report: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            spacing=0,
            **kwargs,
        )
        owner = result["owner"]
        repo  = result["repo"]
        url   = result["html_url"]

        # Main row: name + freshness dot + stars + report + view
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8),
        )

        info_box = MDBoxLayout(
            orientation="horizontal",
            adaptive_height=True,
            spacing=dp(4),
            size_hint_x=1,
        )
        info_box.add_widget(MDLabel(
            text=f"{owner}/{repo}",
            size_hint_x=1,
            adaptive_height=True,
        ))

        days = result.get("last_push_days", 999)
        if days <= 30:
            dot_color = (0.3, 0.8, 0.4, 1)
        elif days <= 90:
            dot_color = (0.9, 0.7, 0.2, 1)
        else:
            dot_color = (0.5, 0.5, 0.5, 1)
        info_box.add_widget(MDIcon(
            icon="circle-small",
            size_hint=(None, None),
            size=(dp(20), dp(20)),
            theme_icon_color="Custom",
            icon_color=dot_color,
            pos_hint={"center_y": 0.5},
        ))

        stars = result.get("stars", 0)
        star_box = MDBoxLayout(
            orientation="horizontal",
            adaptive_height=True,
            size_hint_x=None,
            width=dp(60),
            spacing=dp(2),
        )
        star_box.add_widget(MDIcon(
            icon="star",
            size_hint=(None, None),
            size=(dp(16), dp(16)),
            theme_icon_color="Custom",
            icon_color=(1, 0.84, 0, 1),
            pos_hint={"center_y": 0.5},
        ))
        star_box.add_widget(MDLabel(
            text=str(stars),
            size_hint_x=None,
            width=dp(36),
            adaptive_height=True,
        ))
        info_box.add_widget(star_box)
        row.add_widget(info_box)

        row.add_widget(MDIconButton(
            icon="flag",
            theme_icon_color="Custom",
            icon_color=(0.9, 0.2, 0.2, 1),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: on_report(url) if on_report else None,
        ))
        row.add_widget(MDButton(
            MDButtonText(text="View"),
            style="filled",
            size_hint=(None, None),
            size=(dp(64), dp(32)),
            pos_hint={"center_y": 0.5},
            disabled=is_blacklisted,
            on_release=lambda *_: on_view(url) if on_view else None,
        ))
        self.add_widget(row)

        # Already-added indicator
        if is_already_added:
            added_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(22),
                spacing=dp(4),
                padding=[dp(4), 0],
            )
            added_row.add_widget(MDIcon(
                icon="check-circle",
                size_hint=(None, None),
                size=(dp(16), dp(16)),
                theme_icon_color="Custom",
                icon_color=(0.3, 0.8, 0.4, 1),
                pos_hint={"center_y": 0.5},
            ))
            added_row.add_widget(MDLabel(
                text="Already in your registry list.",
                size_hint_y=None,
                height=dp(22),
                theme_text_color="Custom",
                text_color=(0.3, 0.8, 0.4, 1),
                font_style="Body",
                role="small",
            ))
            self.add_widget(added_row)

        if is_blacklisted:
            warn_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(22),
                spacing=dp(4),
                padding=[dp(4), 0],
            )
            warn_row.add_widget(MDIcon(
                icon="block-helper",
                size_hint=(None, None),
                size=(dp(16), dp(16)),
                theme_icon_color="Custom",
                icon_color=(0.9, 0.3, 0.3, 1),
                pos_hint={"center_y": 0.5},
            ))
            warn_row.add_widget(MDLabel(
                text="On block list.",
                size_hint_y=None,
                height=dp(22),
                theme_text_color="Custom",
                text_color=(0.9, 0.3, 0.3, 1),
                font_style="Body",
                role="small",
            ))
            self.add_widget(warn_row)


def search_score(r: dict) -> int:
    """Freshness + star score for sorting search results descending."""
    days = r.get("last_push_days", 999)
    stars = r.get("stars", 0)
    freshness = 3 if days <= 30 else (2 if days <= 90 else 0)
    star_pts = min(5, int(math.log10(stars + 1) * 5)) if stars >= 0 else 0
    return freshness + star_pts
