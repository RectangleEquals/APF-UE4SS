"""templates_section.py — TemplatesSectionMixin: template rows + framework banners."""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from .....shared.ui.constants import COL_DIM, COL_WARN


_BG_ROW_EVEN = (0.13, 0.13, 0.13, 1)
_BG_ROW_ODD  = (0.11, 0.11, 0.11, 1)
_BG_BANNER   = (0.20, 0.14, 0.06, 1)


class TemplatesSectionMixin:
    """Template row builders and framework state banners for ContentTab."""

    def _conflict_banner(self, conflict_paths: list) -> MDBoxLayout:
        names = ", ".join(p.name if hasattr(p, "name") else str(p) for p in conflict_paths)
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            md_bg_color=(0.22, 0.06, 0.06, 1), padding=[dp(12), 0], spacing=dp(8),
        )
        row.add_widget(MDIcon(
            icon="alert-octagon", size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=(1.0, 0.3, 0.3, 1),
        ))
        row.add_widget(MDLabel(
            text=f"Multiple framework mods detected — resolve conflict before managing mods.\nConflicting: {names}",
            theme_text_color="Custom", text_color=(1.0, 0.5, 0.5, 1),
            font_style="Body", role="small",
        ))
        return row

    def _no_framework_notice(self) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            md_bg_color=(0.20, 0.14, 0.06, 1), padding=[dp(12), 0], spacing=dp(8),
        )
        row.add_widget(MDIcon(
            icon="alert", size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=COL_WARN,
        ))
        row.add_widget(MDLabel(
            text=(
                "Framework mod not installed — Templates and Mods cannot be deployed. "
                "Install it via the Other section or Registries tab."
            ),
            theme_text_color="Custom", text_color=COL_WARN,
            font_style="Body", role="small",
        ))
        return row

    def _framework_banner(self) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36),
            md_bg_color=_BG_BANNER, padding=[dp(12), 0], spacing=dp(8),
        )
        row.add_widget(MDIcon(
            icon="alert", size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=COL_WARN,
        ))
        row.add_widget(MDLabel(
            text="No AP Framework mod found in this registry",
            theme_text_color="Custom", text_color=COL_WARN,
        ))
        return row

    def _template_row(self, tmpl, index: int) -> MDBoxLayout:
        tpath = getattr(tmpl, "template_path", getattr(tmpl, "path", str(index)))
        key = f"tmpl:{tpath}"
        bg = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )

        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            padding=[dp(8), dp(4)], spacing=dp(8),
        )
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = key in self._checked
        cb.bind(active=lambda inst, val, k=key: self._on_check(k, val))
        header.add_widget(cb)

        _tags = getattr(tmpl, "tags", None)
        has_conflict = (_tags.has_conflict if _tags is not None else getattr(tmpl, "has_conflict", False))
        if has_conflict:
            header.add_widget(MDIcon(
                icon="alert-circle", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=COL_WARN,
            ))

        label = tpath.rsplit("/", 1)[-1] if tpath else "Template"
        _src = getattr(tmpl, "source", None)
        if _src is not None:
            registry_lbl = _src.repo.full_name if _src.repo else ""
        else:
            registry_lbl = f"{tmpl.owner}/{tmpl.repo}" if hasattr(tmpl, "owner") else ""

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info.add_widget(MDLabel(
            text=label, font_style="Body", size_hint_y=None, height=dp(22),
        ))
        if registry_lbl:
            info.add_widget(MDLabel(
                text=registry_lbl, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        info.bind(on_touch_down=lambda w, t: self._toggle_expand(key)
                  if w.collide_point(*t.pos) else None)
        header.add_widget(info)

        chevron_icon = "chevron-up" if expanded else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=key: self._toggle_expand(k),
        ))
        container.add_widget(header)

        if expanded:
            container.add_widget(self._template_detail(tmpl))
        return container

    def _template_detail(self, tmpl) -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(6)], spacing=dp(4),
        )
        owner = getattr(tmpl, "owner", "")
        repo  = getattr(tmpl, "repo", "")
        path  = getattr(tmpl, "path", "")

        if owner and repo:
            panel.add_widget(MDLabel(
                text=f"Source: {owner}/{repo}",
                font_style="Label", role="small", size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        file_paths = getattr(tmpl, "file_paths", []) or []
        deploy_svc = self._host.get_service("deploy") if self._host.has_service("deploy") else None
        game_name  = getattr(tmpl, "game_name", getattr(tmpl, "game_id", ""))
        templates_dir = None
        if deploy_svc and hasattr(deploy_svc, "get_templates_dir") and game_name:
            templates_dir = deploy_svc.get_templates_dir(game_name)
        for fp in file_paths[:8]:
            present = bool(templates_dir and (templates_dir / fp).exists())
            dot_color = (0.3, 0.8, 0.4, 1) if present else (0.5, 0.5, 0.5, 1)
            row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(16), spacing=dp(6),
            )
            row.add_widget(MDIcon(
                icon="circle-small", size_hint=(None, 1), width=dp(16),
                theme_icon_color="Custom", icon_color=dot_color,
            ))
            row.add_widget(MDLabel(
                text=fp, font_style="Label", role="small",
                size_hint=(1, 1), halign="left",
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            panel.add_widget(row)
        if len(file_paths) > 8:
            panel.add_widget(MDLabel(
                text=f"… and {len(file_paths) - 8} more files",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        if templates_dir:
            panel.add_widget(MDLabel(
                text=f"Target: {templates_dir}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        elif game_name:
            panel.add_widget(MDLabel(
                text="Target: Framework mod not installed",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_WARN,
            ))

        deps = [
            m for m in self._all_mods
            if path and path in getattr(m, "capabilities_includes", [])
        ]
        if deps:
            panel.add_widget(MDLabel(
                text="Used by: " + ", ".join(getattr(m, "name", m.mod_id) for m in deps[:4]),
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        return panel
