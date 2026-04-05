"""
Tab 2 — Templates

Shows per-registry template contributions for the current game:
  - Items/Locations/Regions vocabulary counts
  - Logic fragment file list
  - Conflict indicator when two repos provide the same template with different content
  - Merged preview (expandable)

Disabled until at least 1 registry is added.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel

if TYPE_CHECKING:
    from ...registry_service import RegistryService, TemplateEntry


class TemplatesTab(MDBoxLayout):
    """Tab 2 — Templates."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._content: Optional[MDBoxLayout] = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Tab subtitle — always visible, not cleared on refresh
        self.add_widget(MDLabel(
            text=(
                "Templates are shared region definitions, item/location vocabulary, "
                "and logic fragments provided by your registries. "
                "They are fetched automatically — no manual setup required."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        scroll = ScrollView(size_hint=(1, 1))
        self._content = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(12), dp(8)],
            spacing=dp(12),
        )
        scroll.add_widget(self._content)
        self.add_widget(scroll)

    def refresh(self, game_id: str) -> None:
        self._content.clear_widgets()
        svc = self._registry_svc()
        if not svc:
            return

        if not svc.get_user_registries(game_id):
            self._content.add_widget(MDLabel(
                text="Add a registry in the Registries tab to see templates for this game.",
                halign="center",
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        templates = svc.get_templates(game_id)
        if not templates:
            self._content.add_widget(MDLabel(
                text="No templates found for this game in your registries.",
                halign="center",
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        # Group by repo
        by_repo: dict[str, list[TemplateEntry]] = {}
        for t in templates:
            key = f"{t.owner}/{t.repo}"
            by_repo.setdefault(key, []).append(t)

        for repo_key, entries in by_repo.items():
            section = MDBoxLayout(
                orientation="vertical",
                adaptive_height=True,
                spacing=dp(4),
                padding=[dp(8), dp(4)],
                md_bg_color=(0.1, 0.12, 0.14, 1),
            )
            header_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(32),
                spacing=dp(8),
            )
            header_row.add_widget(MDLabel(
                text=repo_key,
                font_style="Label",
                role="medium",
                size_hint=(1, 1),
                theme_text_color="Custom",
                text_color=(0.7, 0.85, 1.0, 1),
            ))
            section.add_widget(header_row)

            for t in entries:
                row = MDBoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(28),
                    spacing=dp(8),
                    padding=[dp(8), 0],
                )
                path_lbl = MDLabel(
                    text=t.path,
                    size_hint=(1, 1),
                    theme_text_color="Custom",
                    text_color=(0.75, 0.75, 0.75, 1),
                )
                row.add_widget(path_lbl)
                if t.has_conflict:
                    row.add_widget(MDLabel(
                        text="⚠ Conflict",
                        size_hint=(None, 1),
                        width=dp(80),
                        theme_text_color="Custom",
                        text_color=(0.9, 0.55, 0.1, 1),
                    ))
                section.add_widget(row)

            self._content.add_widget(section)

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
