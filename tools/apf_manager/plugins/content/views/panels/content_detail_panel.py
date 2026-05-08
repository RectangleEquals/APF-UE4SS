"""
ContentDetailPanel — expandable detail panel for any ContentDescriptor.

Renders stage-appropriate detail sections based on isinstance checks.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from ..chrome.constants import COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS
from ..chrome.badges import component_status_chip

if TYPE_CHECKING:
    from ...models.state.pipeline import InstallRecord


_BG_DETAIL = (0.09, 0.10, 0.12, 1)

_COL_MISSING  = (0.9, 0.3, 0.3, 1)
_COL_DEP_OK   = (0.4, 0.8, 0.4, 1)
_COL_INCOMPAT = (0.8, 0.5, 0.2, 1)
_COL_UPDATE   = (0.95, 0.75, 0.2, 1)

_TYPE_LABELS = {
    "ap_mod":              "AP Mod",
    "framework_mod":       "Framework Mod",
    "third_party_mod":     "Third-Party Mod",
    "template":            "Template",
    "github_release_binary": "GitHub Release",
    "external_url_binary": "External URL",
    "manual_binary":       "Manual",
}


class ContentDetailPanel(MDBoxLayout):
    """
    Expandable detail panel for any ContentDescriptor.

    Sections rendered based on isinstance checks:
    - All:               content_type
    - ModDescriptor:     author, components, path, registry, tags
    - APModDescriptor:   + mod_id (highlighted), dependencies (coloured), capabilities_includes
    - TemplateDescriptor: template_path, conflict sources list
    - GithubReleaseBinary: source repo/tag, published_at, asset list w/ sizes
    - install_record present: deployed_at, installed version, update-available cue
    """

    def __init__(
        self,
        content,
        install_record=None,
        known_mod_ids: Optional[set] = None,
        component_health: Optional[dict] = None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            md_bg_color=_BG_DETAIL,
            padding=[dp(16), dp(6), dp(8), dp(8)],
            spacing=dp(4),
            **kwargs,
        )
        self._content = content
        self._install_record = install_record
        self._known_mod_ids = known_mod_ids or set()
        self._component_health = component_health
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        from ...models.descriptors.types import (
            GithubReleaseBinary as _GRB,
            TemplateDescriptor as _TPL,
            ModDescriptor as _MOD,
            APModDescriptor as _AP,
        )
        c = self._content

        if isinstance(c, _GRB):
            self._build_grb(c)
        elif isinstance(c, _TPL):
            self._build_template(c)
        elif isinstance(c, _AP):
            self._build_ap_mod(c)
        elif isinstance(c, _MOD):
            self._build_mod(c)
        else:
            self._row("Type", _TYPE_LABELS.get(c.content_type, c.content_type or "unknown"))
            if c.name:
                self._row("Name", c.name)

        if self._install_record:
            self._build_install_record(self._install_record)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_mod(self, c) -> None:
        # Type
        type_label = _TYPE_LABELS.get(c.content_type, c.content_type or "")
        if type_label:
            self._row("Type", type_label)

        # Author
        author = getattr(c, "author", "")
        if author:
            self._row("Author", author)

        # Component chips
        comps = getattr(c, "components", None)
        if comps and comps.types:
            chip_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6),
                padding=[0, 0, 0, 0],
            )
            for ct in comps.types:
                chip_row.add_widget(component_status_chip(ct, ok=True))
            self.add_widget(chip_row)

        # Path within registry repo (deduplicates redundant Folder row — K-1)
        _src = getattr(c, "source", None)
        if _src and _src.folder:
            self._row("Path", _src.folder)
        else:
            fn = getattr(c, "folder_name", "")
            if fn:
                self._row("Folder", fn)

        # Registry (short name only — no URL row)
        if _src:
            self._row("Registry", _src.repo.full_name)

        # Tags
        _tags = getattr(c, "tags", None)
        if _tags:
            labels = []
            if _tags.is_framework:   labels.append("Framework")
            if _tags.is_submodule:   labels.append("Submodule")
            if _tags.is_cross_game:  labels.append("Cross-game")
            if _tags.has_conflict:   labels.append("Conflict")
            if labels:
                self._row("Tags", ", ".join(labels))

    def _build_ap_mod(self, c) -> None:
        self._build_mod(c)

        # Mod ID as a highlighted blue label (K-4)
        if c.mod_id:
            self.add_widget(MDLabel(
                text=c.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))

        deps    = [d for d in (c.dependencies or []) if not d.is_incompatible]
        incompat = [d for d in (c.dependencies or []) if d.is_incompatible]

        for dep in deps[:6]:
            missing = dep.mod_id not in self._known_mod_ids
            display = dep.mod_id + (f" {dep.version_constraint}" if dep.version_constraint else "")
            self._row_colored("Requires", display, _COL_MISSING if missing else _COL_DEP_OK)

        for dep in incompat[:4]:
            self._row_colored("Conflicts", dep.mod_id, _COL_INCOMPAT)

        includes = getattr(c, "capabilities_includes", []) or []
        if includes:
            for inc in includes[:4]:
                inc_row = MDBoxLayout(
                    orientation="horizontal", size_hint_y=None, height=dp(16), spacing=dp(4),
                )
                inc_row.add_widget(MDIcon(
                    icon="circle-small", size_hint=(None, 1), width=dp(14),
                    theme_icon_color="Custom", icon_color=COL_DIM,
                ))
                inc_row.add_widget(MDLabel(
                    text=inc, font_style="Label", role="small",
                    size_hint=(1, 1), halign="left",
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
                self.add_widget(inc_row)

    def _build_template(self, c) -> None:
        self._row("Path", c.template_path or "")
        _tags = getattr(c, "tags", None)
        if _tags and _tags.has_conflict:
            conflicts = getattr(c, "conflict_sources", []) or []
            self._row("Conflict", ", ".join(r.full_name for r in conflicts))
        _src = getattr(c, "source", None)
        if _src:
            self._row("Registry", _src.repo.full_name)

    def _build_grb(self, c) -> None:
        _src = c.source
        install_type = c.install_type
        if install_type == "framework_binary":
            self._row("Type", "Framework Binaries")
        elif _src and _src.is_prerelease:
            self._row("Type", "UE4SS experimental")
        else:
            self._row("Type", "UE4SS stable")
        if _src:
            self._row("Source", _src.repo.full_name)
            if _src.tag:
                self._row("Tag", _src.tag)
            if _src.published_at:
                self._row("Published", _src.published_at[:10])
        if c.assets:
            asset_col = MDBoxLayout(
                orientation="vertical", size_hint_y=None, adaptive_height=True, spacing=dp(2),
            )
            for a in c.assets[:6]:
                size_str = f" ({a.size_bytes / 1_000_000:.1f} MB)" if getattr(a, "size_bytes", 0) else ""
                asset_col.add_widget(MDLabel(
                    text=f"\u2022 {a.name}{size_str}",
                    font_style="Label", role="small",
                    size_hint_y=None, height=dp(16),
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
            self.add_widget(asset_col)
    def _build_install_record(self, record) -> None:
        if getattr(record, "deployed_at", ""):
            self._row("Installed", record.deployed_at[:10])

        rec_ver = getattr(record, "version", "")
        if rec_ver:
            self._row("Inst. Version", rec_ver)

        # Update-available cue: registry version newer than installed
        reg_ver = getattr(self._content, "version", "")
        if reg_ver and rec_ver and reg_ver != rec_ver:
            try:
                from .....core.models.semver import SemVer
                if SemVer.parse(reg_ver) > SemVer.parse(rec_ver):
                    self._row_colored("Registry Ver.", reg_ver, _COL_UPDATE)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("[content_detail] WARN: version compare failed: %s", exc)
                self._row_colored("Registry Ver.", reg_ver, _COL_UPDATE)

        components = getattr(record, "components", []) or []
        if components:
            health = self._component_health or {}
            chip_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6),
            )
            for comp in components:
                ok = health.get(comp, True) if health else True
                chip_row.add_widget(component_status_chip(comp, ok=ok))
            self.add_widget(chip_row)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _row_colored(self, key_text: str, val_text: str, val_color) -> None:
        r = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8))
        r.add_widget(MDLabel(
            text=key_text, font_style="Label", role="small",
            size_hint=(None, 1), width=dp(96),
            theme_text_color="Custom", text_color=COL_DIM,
        ))
        lbl = MDLabel(text=val_text, font_style="Label", role="small", size_hint=(1, 1))
        if val_color:
            lbl.theme_text_color = "Custom"
            lbl.text_color = val_color
        r.add_widget(lbl)
        self.add_widget(r)

    def _row(self, key_text: str, val_text: str) -> None:
        self._row_colored(key_text, val_text, None)
