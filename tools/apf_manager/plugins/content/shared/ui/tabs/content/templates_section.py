"""templates_section.py — TemplatesSectionMixin: template rows + framework banners."""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from .....shared.ui.constants import COL_WARN


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
            md_bg_color=(0.20, 0.14, 0.06, 1), padding=[dp(12), 0], spacing=dp(8),
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
        from .....shared.ui.content_row import ContentRowWidget
        from .....shared.ui.content_detail import ContentDetailPanel
        tpath = getattr(tmpl, "template_path", getattr(tmpl, "path", str(index)))
        key = f"tmpl:{tpath}"
        expanded = key in self._expanded

        outer = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)
        outer.add_widget(ContentRowWidget(
            content=tmpl, row_index=index,
            checked=key in self._checked, expanded=expanded,
            on_check=lambda val, k=key: self._on_check(k, val),
            on_expand=lambda *_: self._toggle_expand(key),
        ))
        if expanded:
            outer.add_widget(ContentDetailPanel(content=tmpl))
        return outer
