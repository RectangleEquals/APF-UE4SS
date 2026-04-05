"""
Tab 3 — Mods

Shows:
  - Framework mod status banner (green/amber/red)
  - Mod groups per registry/repo (collapsible header)
  - Mod rows: name, mod_id, description, Docs button, Stage button
  - Preview pane on the right (manifest details + inline docs + Stage/Unstage)

Disabled until at least 1 registry is added.
"""

from __future__ import annotations

import webbrowser
from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel

if TYPE_CHECKING:
    from ...registry_service import RegistryService, RegistryModEntry


class ModsTab(MDBoxLayout):
    """Tab 3 — Mods (browse and stage from registry)."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._content: Optional[MDBoxLayout] = None
        self._banner: Optional[MDLabel] = None
        self._game_id: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        # Framework mod status banner
        self._banner = MDLabel(
            text="",
            size_hint_y=None,
            height=dp(36),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
            md_bg_color=(0.12, 0.14, 0.16, 1),
        )
        self.add_widget(self._banner)

        scroll = ScrollView(size_hint=(1, 1))
        self._content = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(12), dp(8)],
            spacing=dp(8),
        )
        scroll.add_widget(self._content)
        self.add_widget(scroll)

    def refresh(self, game_id: str) -> None:
        self._game_id = game_id
        self._content.clear_widgets()
        svc = self._registry_svc()

        if not svc or not svc.get_user_registries():
            self._banner.text = "Add registries to browse mods."
            self._content.add_widget(MDLabel(
                text="Add at least one registry in the Registries tab.",
                halign="center",
                size_hint_y=None,
                height=dp(60),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        # Update framework mod banner
        candidates = svc.get_framework_candidates(game_id)
        if not candidates:
            self._banner.text = "✗ No framework mod found — install blocked"
            self._banner.text_color = (0.9, 0.3, 0.3, 1)
        elif len(candidates) > 1:
            self._banner.text = "⚠ Multiple framework mod candidates — confirm selection"
            self._banner.text_color = (0.9, 0.6, 0.1, 1)
        else:
            name = candidates[0].entry.name or candidates[0].entry.mod_id
            self._banner.text = f"✓ Framework mod: {name}"
            self._banner.text_color = (0.3, 0.8, 0.4, 1)

        # Render mods grouped by repo
        mods = svc.get_mods(game_id)
        if not mods:
            self._content.add_widget(MDLabel(
                text="No mods found in registered repositories.",
                halign="center",
                size_hint_y=None,
                height=dp(60),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        # Group by owner/repo
        by_repo: dict[str, list[RegistryModEntry]] = {}
        for mod in mods:
            key = f"{mod.owner}/{mod.repo}"
            by_repo.setdefault(key, []).append(mod)

        staged_ids = {m.mod_id for m in svc.get_staged()}

        for repo_key, repo_mods in by_repo.items():
            group = MDBoxLayout(
                orientation="vertical",
                adaptive_height=True,
                spacing=dp(2),
            )
            group.add_widget(MDLabel(
                text=repo_key,
                font_style="Label",
                role="medium",
                size_hint_y=None,
                height=dp(28),
                padding=[dp(8), 0],
                theme_text_color="Custom",
                text_color=(0.6, 0.75, 0.9, 1),
                md_bg_color=(0.08, 0.1, 0.12, 1),
            ))
            for mod in repo_mods:
                group.add_widget(self._build_mod_row(mod, mod.mod_id in staged_ids, svc))
            self._content.add_widget(group)

    def _build_mod_row(
        self, mod: "RegistryModEntry", is_staged: bool, svc: "RegistryService"
    ) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(16), dp(4)],
            spacing=dp(8),
        )

        # Name + description
        info_col = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info_col.add_widget(MDLabel(
            text=mod.name or mod.mod_id,
            font_style="Body",
            size_hint_y=None,
            height=dp(22),
        ))
        if mod.description:
            info_col.add_widget(MDLabel(
                text=mod.description[:80],
                font_style="Label",
                role="small",
                size_hint_y=None,
                height=dp(18),
                theme_text_color="Custom",
                text_color=(0.6, 0.6, 0.6, 1),
            ))
        row.add_widget(info_col)

        # Docs button (if readme available)
        if mod.readme_url:
            row.add_widget(MDIconButton(
                icon="file-document-outline",
                on_release=lambda *_, m=mod: self._on_view_docs(m),
            ))

        # Stage/Unstage button
        if is_staged:
            row.add_widget(MDButton(
                MDButtonText(text="Staged"),
                style="tonal",
                size_hint=(None, None),
                size=(dp(80), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, mid=mod.mod_id: svc.unstage_mod(mid) or self.refresh(self._game_id),
            ))
        else:
            row.add_widget(MDButton(
                MDButtonText(text="+ Stage"),
                style="filled",
                size_hint=(None, None),
                size=(dp(80), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, mid=mod.mod_id: svc.stage_mod(mid) or self.refresh(self._game_id),
            ))

        return row

    def _on_view_docs(self, mod: "RegistryModEntry") -> None:
        svc = self._registry_svc()
        if not svc:
            return
        docs = svc.get_mod_docs(mod)
        if docs and self._host.has_service("html_viewer"):
            viewer = self._host.get_service("html_viewer")
            # Fetch and render the README
            api = svc._make_api(mod.owner, mod.repo)
            md_text = api.fetch_text(docs[0].raw_url)
            if md_text:
                try:
                    from ....plugins.docs_viewer.md_to_html import convert
                    html = convert(md_text, title=mod.name or mod.mod_id)
                    viewer.show(mod.name or mod.mod_id, html)
                    return
                except Exception:
                    pass
        # Fallback: open in browser
        if docs:
            webbrowser.open(docs[0].raw_url)

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
