"""cache_panel.py — CachePanelMixin: cached items list widget logic for DownloadsTab."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel

from ..chrome.constants import COL_DIM

if TYPE_CHECKING:
    from ..tabs.downloads import _CacheItem


_BG_ITEM = (0.13, 0.13, 0.13, 1)


class CachePanelMixin:
    """Cached item row builder and selection/action delegation for DownloadsTab.

    Requires host-owning class to expose:
      self._host, self._cached, self._selected_cache, self._expanded_cache,
      self._detection, self._game_id, self._ue4ss_detected, self._framework_detected,
      self._on_switch_to_installed, self._ctrl (CacheController), self._rebuild_ui()
    """

    # -----------------------------------------------------------------------
    # Row + detail builders
    # -----------------------------------------------------------------------

    def _cache_row(self, ci: "_CacheItem") -> MDBoxLayout:
        from ..rows.content_row import ContentRowWidget
        cache_key = str(ci.cache_path)
        expanded  = cache_key in self._expanded_cache
        cache_detail = self._cache_detail(ci) if expanded else None

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM,
        )
        container.add_widget(ContentRowWidget(
            content=ci.content,
            checked=cache_key in self._selected_cache,
            expanded=expanded,
            on_check=lambda val, k=cache_key: self._on_cache_check(k, val),
            on_expand=lambda *_: self._toggle_cache_expand(cache_key),
            detail_widget=cache_detail,
        ))
        return container

    def _cache_detail(self, ci: "_CacheItem") -> MDBoxLayout:
        from ...models.descriptors.types import GithubReleaseBinary as _GRB
        from ..panels.content_detail_panel import ContentDetailPanel

        outer = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
        )

        # X-1: Full descriptor info first, then supplemental cache metadata below
        outer.add_widget(ContentDetailPanel(content=ci.content))

        size = ci.size_mb
        if size > 0:
            size_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(22),
                padding=[dp(16), 0, dp(8), 0],
            )
            size_row.add_widget(MDLabel(
                text=f"Cache size: {size:.1f} MB",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            outer.add_widget(size_row)

        # X-2: Release Notes — opens docs viewer; omitted if service unavailable
        if isinstance(ci.content, _GRB) and ci.content.source and ci.content.source.changelog:
            changelog = ci.content.source.changelog
            docs_svc = (
                self._host.get_service("docs_viewer")
                if self._host.has_service("docs_viewer") else None
            )
            if docs_svc and hasattr(docs_svc, "show_inline"):
                def _show_release_notes(*_, _cl=changelog, _nm=ci.display_name, _svc=docs_svc):
                    _svc.show_inline(
                        content=_cl,
                        title=f"{_nm} — Release Notes",
                        sidebar_mode="verbose",
                        allow_mode_toggle=False,
                    )
                outer.add_widget(MDButton(
                    MDButtonText(text="Release Notes"),
                    style="text", size_hint_y=None, height=dp(36),
                    on_release=_show_release_notes,
                ))

        return outer

    # -----------------------------------------------------------------------
    # Expand / select state (pure view state)
    # -----------------------------------------------------------------------

    def _toggle_cache_expand(self, key: str) -> None:
        if key in self._expanded_cache:
            self._expanded_cache.discard(key)
        else:
            self._expanded_cache.clear()
            self._expanded_cache.add(key)
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _on_cache_check(self, cache_key: str, checked: bool) -> None:
        if checked:
            self._selected_cache.add(cache_key)
        else:
            self._selected_cache.discard(cache_key)

    def _select_all_cached(self, select: bool) -> None:
        if select:
            self._selected_cache = {str(ci.cache_path) for ci in self._cached}
        else:
            self._selected_cache.clear()
        self._rebuild_ui()

    # -----------------------------------------------------------------------
    # Actions — delegate to CacheController
    # -----------------------------------------------------------------------

    def _remove_cached(self, ci: "_CacheItem") -> None:
        """Delete a single item and refresh the panel."""
        self._selected_cache.discard(str(ci.cache_path))
        self._ctrl.delete(ci)

    def _on_install_selected(self) -> None:
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        if not selected:
            return
        self._trigger_validate_and_install(selected)

    def _on_remove_selected(self) -> None:
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        for ci in selected:
            self._selected_cache.discard(str(ci.cache_path))
        self._ctrl.delete_items(selected)

    def _on_install_all(self) -> None:
        self._trigger_validate_and_install(self._cached)

    # -----------------------------------------------------------------------
    # Validation flow — controller validates, view shows dialog if needed
    # -----------------------------------------------------------------------

    def _trigger_validate_and_install(self, items: list) -> None:
        self._ctrl.validate_and_install(
            items=items,
            detection=self._detection,
            game_id=self._game_id,
            ue4ss_detected=self._ue4ss_detected,
            framework_detected=self._framework_detected,
            on_errors_only=lambda errors, warnings: self._show_install_warn(
                errors, warnings, allow_proceed=False,
            ),
            on_warnings=lambda errors, warnings, proceed_fn: self._show_install_warn(
                errors, warnings, allow_proceed=True, on_confirmed=proceed_fn,
            ),
            on_proceed=self._do_install,
        )

    def _do_install(self, sorted_items: list) -> None:
        """Called by validation flow when it's safe to install."""
        self._ctrl.do_install(
            items=sorted_items,
            detection=self._detection,
            game_id=self._game_id,
            ue4ss_detected=self._ue4ss_detected,
            framework_detected=self._framework_detected,
            on_switch_to_installed=self._on_switch_to_installed,
        )

    def _show_install_warn(
        self,
        errors: list,
        warnings: list,
        allow_proceed: bool,
        on_confirmed=None,
    ) -> None:
        from ..dialogs.validation_warning_dialog import ValidationWarningDialog
        lines  = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title  = "Cannot Install" if not allow_proceed else "Install with Warnings?"
        dlg = ValidationWarningDialog.for_install(
            title=title,
            lines=lines,
            allow_proceed=allow_proceed,
            on_confirm=on_confirmed or (lambda: None),
        )
        dlg.open()
