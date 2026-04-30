"""templates_section.py — TemplatesSectionMixin: template rows + framework banners."""

from __future__ import annotations

from kivymd.uix.boxlayout import MDBoxLayout

from .....shared.ui.banners.conflict_banner import ConflictBanner
from .....shared.ui.banners.framework_status_banner import FrameworkStatusBanner


class TemplatesSectionMixin:
    """Template row builders and framework state banners for ContentTab."""

    def _conflict_banner(self, conflict_paths: list) -> ConflictBanner:
        return ConflictBanner(conflict_paths=conflict_paths)

    def _no_framework_notice(self) -> FrameworkStatusBanner:
        return FrameworkStatusBanner(state="no_framework")

    def _framework_banner(self) -> FrameworkStatusBanner:
        return FrameworkStatusBanner(state="no_registry_framework")

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
