"""
ContentDetailPanel — expandable detail panel for any ContentDescriptor.

Renders stage-appropriate detail sections based on isinstance checks.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from .constants import COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS
from .badges import component_status_chip

if TYPE_CHECKING:
    from ..data.pipeline_state import InstallRecord


_BG_DETAIL = (0.09, 0.10, 0.12, 1)


class ContentDetailPanel(MDBoxLayout):
    """
    Expandable detail panel for any ContentDescriptor.

    Sections rendered based on isinstance checks:
    - All:               version, game_id, content_type
    - ModDescriptor:     description, author, source repo, registry URL
    - APModDescriptor:   + mod_id, dependencies (coloured by status), capabilities_includes
    - TemplateDescriptor: template_path, conflict sources list
    - GithubReleaseBinary: source repo/tag, published_at, changelog excerpt, asset list
    - install_record present: deployed_at, per-component health chips
    """

    def __init__(self, content, install_record=None, known_mod_ids: Optional[set] = None, **kwargs):
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
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        from ..data.content_types import (
            GithubReleaseBinary as _GRB,
            TemplateDescriptor as _TPL,
            ModDescriptor as _MOD,
            APModDescriptor as _AP,
            FrameworkModDescriptor as _FW,
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
            self._row("Type", c.content_type or "unknown")
            if c.name:
                self._row("Name", c.name)

        if self._install_record:
            self._build_install_record(self._install_record)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_mod(self, c) -> None:
        desc = getattr(c, "description", "")
        if desc:
            self.add_widget(MDLabel(
                text=desc, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Secondary",
            ))
        _src = getattr(c, "source", None)
        if _src:
            self._row("Source", _src.repo.full_name)
            if _src.registry_url:
                self._row("Registry", _src.registry_url)

    def _build_ap_mod(self, c) -> None:
        self._build_mod(c)
        if c.mod_id:
            self.add_widget(MDLabel(
                text=c.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))
        deps = [d for d in (c.dependencies or []) if not d.is_incompatible]
        incompat = [d for d in (c.dependencies or []) if d.is_incompatible]
        if deps:
            dep_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(16), spacing=dp(4),
            )
            dep_row.add_widget(MDLabel(
                text="Deps:", font_style="Label", role="small",
                size_hint=(None, 1), width=dp(32),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            for dep in deps[:5]:
                missing = dep.mod_id not in self._known_mod_ids
                dep_row.add_widget(MDLabel(
                    text=dep.mod_id + (f" {dep.version_constraint}" if dep.version_constraint else ""),
                    font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(max(80, len(dep.mod_id) * 7)),
                    theme_text_color="Custom",
                    text_color=(0.9, 0.3, 0.3, 1) if missing else COL_DIM,
                ))
            self.add_widget(dep_row)
        if incompat:
            self.add_widget(MDLabel(
                text="Incompatible: " + ", ".join(d.mod_id for d in incompat[:4]),
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.8, 0.5, 0.2, 1),
            ))
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
            self._row("Source", _src.repo.full_name)

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
                asset_col.add_widget(MDLabel(
                    text=f"\u2022 {a.name}",
                    font_style="Label", role="small",
                    size_hint_y=None, height=dp(16),
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
            self.add_widget(asset_col)
        if _src and _src.changelog:
            self.add_widget(MDLabel(
                text=_src.changelog[:300],
                font_style="Label", role="small",
                size_hint_y=None, height=dp(48),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

    def _build_install_record(self, record) -> None:
        if getattr(record, "deployed_at", ""):
            self._row("Installed", record.deployed_at[:10])
        if getattr(record, "version", ""):
            self._row("Version", record.version)
        components = getattr(record, "components", []) or []
        if components:
            chip_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6),
            )
            for comp in components:
                chip_row.add_widget(component_status_chip(comp, ok=True))
            self.add_widget(chip_row)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _row(self, key_text: str, val_text: str) -> None:
        r = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8))
        r.add_widget(MDLabel(
            text=key_text, font_style="Label", role="small",
            size_hint=(None, 1), width=dp(96),
            theme_text_color="Custom", text_color=COL_DIM,
        ))
        r.add_widget(MDLabel(
            text=val_text, font_style="Label", role="small",
            size_hint=(1, 1),
        ))
        self.add_widget(r)
