"""
Tab 2 — Templates (facelift)

Shows per-registry template contributions for the current game:
  - Standard template file tree per registry (Regions/Items/Locations/options/logic)
  - Conflict badge when two repos provide the same template directory
  - Merge preview: which registries contribute which content type
  - "Resolve" button opens Repo Viewer for conflict resolution

Disabled until at least 1 registry is added.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel

if TYPE_CHECKING:
    from ...registry_service import RegistryService, TemplateEntry

# Standard template files expected in every Templates/<game>/ directory.
_STANDARD_FILES = [
    ("file-code-outline",       "Regions.json",    "region vocabulary"),
    ("package-variant-outline", "Items.json",      "item vocabulary"),
    ("map-marker-outline",      "Locations.json",  "location vocabulary"),
    ("cog-outline",             "{game}_options.json", "game options"),
    ("folder-outline",          "logic/",          "logic fragments"),
]


def _file_rows(game_id: str) -> list[tuple[str, str, str]]:
    """Expand _STANDARD_FILES, substituting {game} with game_id."""
    return [
        (icon, name.replace("{game}", game_id), desc)
        for icon, name, desc in _STANDARD_FILES
    ]


class TemplatesTab(MDBoxLayout):
    """Tab 2 — Templates."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._game_id: str = ""
        self._content: Optional[MDBoxLayout] = None
        self._build_ui()

    def _build_ui(self) -> None:
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
            spacing=dp(16),
        )
        scroll.add_widget(self._content)
        self.add_widget(scroll)

    def refresh(self, game_id: str) -> None:
        self._game_id = game_id
        self._content.clear_widgets()
        svc = self._registry_svc()
        if not svc:
            return

        if not svc.get_user_registries(game_id):
            self._content.add_widget(_empty_label(
                "Add a registry in the Registries tab to see templates for this game."
            ))
            return

        templates = svc.get_templates(game_id)
        if not templates:
            self._content.add_widget(_empty_label(
                "No templates found for this game in your registries.\n"
                "Add a registry that includes Templates/"
                + (game_id.title() or "<Game>") + "/ content."
            ))
            return

        # Group by repo for per-registry sections
        by_repo: dict[str, list["TemplateEntry"]] = {}
        for t in templates:
            key = f"{t.owner}/{t.repo}"
            by_repo.setdefault(key, []).append(t)

        # Per-registry sections
        for repo_key, entries in by_repo.items():
            self._content.add_widget(
                self._build_repo_section(repo_key, entries, game_id)
            )

        # Merge preview
        conflict_entries = [t for t in templates if t.has_conflict]
        self._content.add_widget(
            self._build_merge_preview(templates, conflict_entries, game_id)
        )

    # -----------------------------------------------------------------------
    # Section builders
    # -----------------------------------------------------------------------

    def _build_repo_section(
        self,
        repo_key: str,
        entries: list["TemplateEntry"],
        game_id: str,
    ) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(10), dp(8)],
            radius=[dp(6)],
            md_bg_color=(0.08, 0.10, 0.13, 1),
        )

        # Header row: repo icon + name + "View Docs" button
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            spacing=dp(6),
        )
        header.add_widget(MDIcon(
            icon="source-repository",
            size_hint=(None, None),
            size=(dp(20), dp(20)),
            theme_text_color="Custom",
            text_color=(0.45, 0.65, 0.9, 1),
        ))
        header.add_widget(MDLabel(
            text=repo_key,
            font_style="Label",
            role="large",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.85, 1.0, 1),
        ))
        section.add_widget(header)

        # Template path rows
        for t in entries:
            section.add_widget(self._build_template_row(t, game_id))

        return section

    def _build_template_row(
        self,
        t: "TemplateEntry",
        game_id: str,
    ) -> MDBoxLayout:
        outer = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(8), dp(4)],
        )

        # Template path + conflict badge row
        path_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(28),
            spacing=dp(6),
        )
        path_row.add_widget(MDIcon(
            icon="folder-table-outline",
            size_hint=(None, None),
            size=(dp(18), dp(18)),
            theme_text_color="Custom",
            text_color=(0.55, 0.75, 0.45, 1),
        ))
        path_row.add_widget(MDLabel(
            text=t.path,
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.8, 0.8, 0.8, 1),
            font_style="Body",
            role="medium",
        ))

        if t.has_conflict:
            conflict_repos = ", ".join(t.conflict_repos)
            resolve_btn = MDButton(
                MDButtonText(text="⚠  Conflict — Resolve"),
                style="text",
                size_hint=(None, None),
                height=dp(28),
            )
            resolve_btn.bind(
                on_release=lambda *_, te=t: self._on_resolve_conflict(te)
            )
            path_row.add_widget(resolve_btn)

        outer.add_widget(path_row)

        if t.has_conflict:
            conflict_repos = " vs ".join(t.conflict_repos)
            outer.add_widget(MDLabel(
                text=f"      Provided by: {conflict_repos}",
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.9, 0.55, 0.1, 1),
                font_style="Body",
                role="small",
            ))

        # Standard file tree (informational)
        file_tree = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(28), 0, 0, 0],
            spacing=dp(1),
        )
        for icon, name, desc in _file_rows(game_id):
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(22),
                spacing=dp(4),
            )
            row.add_widget(MDIcon(
                icon=icon,
                size_hint=(None, None),
                size=(dp(16), dp(16)),
                theme_text_color="Custom",
                text_color=(0.5, 0.5, 0.5, 1),
            ))
            row.add_widget(MDLabel(
                text=f"{name}  —  {desc}",
                size_hint=(1, 1),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
                font_style="Body",
                role="small",
            ))
            file_tree.add_widget(row)
        outer.add_widget(file_tree)

        return outer

    def _build_merge_preview(
        self,
        templates: list["TemplateEntry"],
        conflicts: list["TemplateEntry"],
        game_id: str,
    ) -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(4),
            padding=[dp(10), dp(8)],
            radius=[dp(6)],
            md_bg_color=(0.06, 0.09, 0.11, 1),
        )

        # Header
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(32),
            spacing=dp(6),
        )
        header.add_widget(MDIcon(
            icon="merge",
            size_hint=(None, None),
            size=(dp(20), dp(20)),
            theme_text_color="Custom",
            text_color=(0.55, 0.75, 0.45, 1),
        ))
        header.add_widget(MDLabel(
            text="Merge Preview",
            font_style="Label",
            role="large",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.85, 1.0, 1),
        ))
        panel.add_widget(header)

        # Source list
        by_repo: dict[str, int] = {}
        for t in templates:
            key = f"{t.owner}/{t.repo}"
            by_repo[key] = by_repo.get(key, 0) + 1

        for repo_key, path_count in by_repo.items():
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(22),
                spacing=dp(6),
                padding=[dp(8), 0],
            )
            row.add_widget(MDIcon(
                icon="source-repository",
                size_hint=(None, None),
                size=(dp(16), dp(16)),
                theme_text_color="Custom",
                text_color=(0.45, 0.65, 0.9, 1),
            ))
            row.add_widget(MDLabel(
                text=f"{repo_key}  —  {path_count} template path(s)",
                size_hint=(1, 1),
                theme_text_color="Custom",
                text_color=(0.7, 0.7, 0.7, 1),
                font_style="Body",
                role="small",
            ))
            panel.add_widget(row)

        # Amalgamation note
        amalgamation_text = (
            "Logic expressions across registries are OR-merged at install time. "
            "Item/location vocabularies are combined with deduplication."
        )
        if conflicts:
            amalgamation_text += (
                f"\n⚠  {len(conflicts)} conflict(s) detected — resolve before installing."
            )
            text_color = (0.9, 0.7, 0.2, 1)
        else:
            text_color = (0.45, 0.45, 0.45, 1)

        panel.add_widget(MDLabel(
            text=amalgamation_text,
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Custom",
            text_color=text_color,
            font_style="Body",
            role="small",
            padding=[dp(8), dp(4)],
        ))

        return panel

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_resolve_conflict(self, t: "TemplateEntry") -> None:
        """Open Repo Viewer for the first conflicting repo to resolve the conflict."""
        if not self._host.has_service("repo_viewer"):
            return
        svc = self._registry_svc()
        if not svc:
            return

        # Use first conflicting repo for traversal
        if not t.conflict_repos:
            return
        repo_key = t.conflict_repos[0]
        url = f"https://github.com/{repo_key}"

        def _on_traversal_done(mods):
            if not mods:
                return
            self._host.show_dialog(
                "repo_viewer",
                repo_url=url,
                game_id=self._game_id,
                traversal_result=mods,
                on_confirm=lambda _selected: self.refresh(self._game_id),
                on_cancel=None,
            )

        def _bg():
            from kivy.clock import Clock
            from ..registry_resolver import RegistryResolver
            resolver = svc._get_resolver()
            cache = svc._get_cache()
            try:
                mods = resolver.traverse(url, cache)
            except Exception:
                mods = []
            Clock.schedule_once(lambda dt: _on_traversal_done(mods))

        import threading
        threading.Thread(target=_bg, daemon=True).start()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None


def _empty_label(text: str) -> MDLabel:
    return MDLabel(
        text=text,
        halign="center",
        size_hint_y=None,
        adaptive_height=True,
        theme_text_color="Custom",
        text_color=(0.45, 0.45, 0.45, 1),
        padding=[dp(16), dp(8)],
    )
