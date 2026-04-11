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
from typing import Optional, Callable, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel

if TYPE_CHECKING:
    from ...registry_service import RegistryService, RegistryModEntry




class ModsTab(MDBoxLayout):
    """Tab 3 — Mods (browse and stage from registry)."""

    def __init__(self, host, on_staged_changed: Optional[Callable] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._on_staged_changed = on_staged_changed
        self._content: Optional[MDBoxLayout] = None
        self._banner: Optional[MDBoxLayout] = None
        self._banner_icon: Optional[MDIcon] = None
        self._banner_lbl: Optional[MDLabel] = None
        self._game_id: str = ""
        self._framework_candidates: list = []
        self._build_ui()

    def _build_ui(self) -> None:
        # Tab subtitle — static, never cleared
        self.add_widget(MDLabel(
            text=(
                "Browse and stage mods from your registries. "
                "Click + on a mod to stage it, then review and install from the Queue tab."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        # Framework mod status banner (tappable for picker/detail)
        from kivymd.uix.behaviors import CommonElevationBehavior
        from kivy.uix.behaviors import ButtonBehavior

        class _TapBox(ButtonBehavior, MDBoxLayout):
            pass

        self._banner = _TapBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            padding=[dp(12), 0],
            spacing=dp(8),
            md_bg_color=(0.12, 0.14, 0.16, 1),
        )
        self._banner.bind(on_release=lambda *_: self._on_banner_tap())
        self._banner_icon = MDIcon(
            icon="help-circle-outline",
            size_hint=(None, 1),
            width=dp(24),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self._banner_lbl = MDLabel(
            text="",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self._banner.add_widget(self._banner_icon)
        self._banner.add_widget(self._banner_lbl)
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

        if not svc or not svc.get_user_registries(game_id):
            self._banner_icon.icon = "information-outline"
            self._banner_icon.text_color = (0.7, 0.7, 0.7, 1)
            self._banner_lbl.text = "Add a registry to browse mods."
            self._banner_lbl.text_color = (0.7, 0.7, 0.7, 1)
            self._content.add_widget(MDLabel(
                text=(
                    "No registries added for this game yet.\n"
                    "Go to the Registries tab and add a GitHub registry URL to get started."
                ),
                halign="center",
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        # Update framework mod banner
        candidates = svc.get_framework_candidates(game_id)
        self._framework_candidates = candidates
        if not candidates:
            self._banner_icon.icon = "close-circle"
            self._banner_icon.text_color = (0.9, 0.3, 0.3, 1)
            self._banner_lbl.text = "No framework mod found — install blocked"
            self._banner_lbl.text_color = (0.9, 0.3, 0.3, 1)
        elif len(candidates) > 1:
            self._banner_icon.icon = "alert"
            self._banner_icon.text_color = (0.9, 0.6, 0.1, 1)
            self._banner_lbl.text = "Multiple framework mod candidates — confirm selection"
            self._banner_lbl.text_color = (0.9, 0.6, 0.1, 1)
        else:
            name = candidates[0].entry.name or candidates[0].entry.mod_id
            self._banner_icon.icon = "check-circle"
            self._banner_icon.text_color = (0.3, 0.8, 0.4, 1)
            self._banner_lbl.text = f"Framework mod: {name}"
            self._banner_lbl.text_color = (0.3, 0.8, 0.4, 1)

        # Render mods grouped by repo
        mods = svc.get_mods(game_id)
        if not mods:
            self._content.add_widget(MDLabel(
                text=(
                    "No mods found for this game in your registries.\n"
                    "Try refreshing your registries or adding more registry URLs."
                ),
                halign="center",
                size_hint_y=None,
                adaptive_height=True,
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
                on_release=lambda *_, mid=mod.mod_id, s=svc: self._do_unstage(mid, s),
            ))
        else:
            row.add_widget(MDButton(
                MDButtonText(text="+ Stage"),
                style="filled",
                size_hint=(None, None),
                size=(dp(80), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, mid=mod.mod_id, s=svc: self._do_stage(mid, s),
            ))

        return row

    def _do_stage(self, mod_id: str, svc: "RegistryService") -> None:
        svc.stage_mod(mod_id)
        self.refresh(self._game_id)
        if self._on_staged_changed:
            self._on_staged_changed()

    def _do_unstage(self, mod_id: str, svc: "RegistryService") -> None:
        svc.unstage_mod(mod_id)
        self.refresh(self._game_id)
        if self._on_staged_changed:
            self._on_staged_changed()

    def _on_banner_tap(self) -> None:
        if not self._framework_candidates:
            return
        if len(self._framework_candidates) == 1:
            self._show_framework_detail(self._framework_candidates[0])
        else:
            self._show_framework_picker(self._framework_candidates)

    def _show_framework_detail(self, candidate) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        from kivymd.uix.button import MDButton, MDButtonText
        name = candidate.entry.name or candidate.entry.mod_id
        breakdown_text = "  ".join(
            f"[{k} {'+' if v >= 0 else ''}{v}]"
            for k, v in candidate.score_breakdown.items()
        )
        dlg = MDDialog(
            MDDialogHeadlineText(text=f"Framework Mod: {name}"),
            MDDialogSupportingText(
                text=(
                    f"Repo: {candidate.entry.owner}/{candidate.entry.repo}\n"
                    f"Score: {candidate.score}\n"
                    f"Breakdown: {breakdown_text or 'n/a'}"
                )
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
            ),
        )
        dlg.open()

    def _show_framework_picker(self, candidates: list) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        from kivymd.uix.button import MDButton, MDButtonText

        lines = []
        for i, c in enumerate(candidates, 1):
            name = c.entry.name or c.entry.mod_id
            breakdown_text = "  ".join(
                f"[{k} {'+' if v >= 0 else ''}{v}]"
                for k, v in c.score_breakdown.items()
            )
            lines.append(
                f"{i}. {name}  ({c.entry.owner}/{c.entry.repo})\n"
                f"   Score: {c.score}  {breakdown_text}"
            )

        dlg = MDDialog(
            MDDialogHeadlineText(text="Multiple Framework Candidates"),
            MDDialogSupportingText(
                text=(
                    "More than one framework mod was found. "
                    "The highest-scoring candidate will be used. "
                    "Remove conflicting registries if needed.\n\n"
                    + "\n\n".join(lines)
                )
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
            ),
        )
        dlg.open()

    def _on_view_docs(self, mod: "RegistryModEntry") -> None:
        svc = self._registry_svc()
        if not svc:
            return
        docs = svc.get_mod_docs(mod)
        if not docs:
            return
        if self._host.has_service("docs_viewer"):
            viewer = self._host.get_service("docs_viewer")
            viewer.open_url(docs[0].raw_url, title=f"{mod.owner}/{mod.repo} — {mod.name or mod.mod_id}")
            return
        # Fallback: open in system browser
        webbrowser.open(docs[0].raw_url)

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
