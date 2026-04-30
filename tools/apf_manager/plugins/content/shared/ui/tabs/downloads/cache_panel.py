"""cache_panel.py — CachePanelMixin: cached items list + install/remove logic."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel

from .....shared.ui.constants import COL_DIM

if TYPE_CHECKING:
    from .downloads_tab import _CacheItem


_BG_ITEM = (0.13, 0.13, 0.13, 1)


class CachePanelMixin:
    """Cached item row builder and install/remove logic for DownloadsTab."""

    def _cache_row(self, ci: "_CacheItem") -> MDBoxLayout:
        from .....shared.ui.content_row import ContentRowWidget
        from .....shared.ui.content_detail import ContentDetailPanel
        cache_key = str(ci.cache_path)
        expanded  = cache_key in self._expanded_cache

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
        ))
        if expanded:
            container.add_widget(self._cache_detail(ci))
        return container

    def _cache_detail(self, ci: "_CacheItem") -> MDBoxLayout:
        from .....shared.ui.content_detail import ContentDetailPanel
        from .....shared.data.content_types import GithubReleaseBinary as _GRB

        outer = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
        )
        outer.add_widget(ContentDetailPanel(content=ci.content))

        # Size label
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

        # Changelog button for GRB
        if isinstance(ci.content, _GRB) and ci.content.source and ci.content.source.changelog:
            changelog = ci.content.source.changelog

            def _show_changelog(*_, _cl=changelog, _nm=ci.display_name):
                from .....shared.ui.dialogs.changelog_dialog import ChangelogDialog
                ChangelogDialog(title=f"{_nm} — Release Notes", changelog=_cl).open()

            outer.add_widget(MDButton(
                MDButtonText(text="Release Notes"),
                style="text", size_hint_y=None, height=dp(36),
                on_release=_show_changelog,
            ))

        return outer

    def _toggle_cache_expand(self, key: str) -> None:
        if key in self._expanded_cache:
            self._expanded_cache.discard(key)
        else:
            self._expanded_cache.clear()
            self._expanded_cache.add(key)
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    # -----------------------------------------------------------------------
    # Cache actions
    # -----------------------------------------------------------------------

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

    def _remove_cached(self, ci: "_CacheItem") -> None:
        import shutil
        try:
            shutil.rmtree(ci.cache_path, ignore_errors=True)
        except Exception as exc:
            self._host.log(f"[cache] WARN: failed to remove cached item {ci.cache_path}: {exc}")
        self._selected_cache.discard(str(ci.cache_path))
        self._scan_cache_and_rebuild()

    def _on_install_selected(self) -> None:
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        if not selected:
            return
        self._validate_and_install(selected)

    def _on_remove_selected(self) -> None:
        import shutil
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        for ci in selected:
            try:
                shutil.rmtree(ci.cache_path, ignore_errors=True)
            except Exception as exc:
                self._host.log(f"[cache] WARN: failed to remove {ci.cache_path}: {exc}")
            self._selected_cache.discard(str(ci.cache_path))
        self._scan_cache_and_rebuild()

    def _validate_and_install(self, items: list) -> None:
        other_items = [ci for ci in items if getattr(ci, "category", "mod") == "other"]
        mod_items   = [ci for ci in items if getattr(ci, "category", "mod") != "other"]

        validation_svc = self._host.get_service("validation")
        if validation_svc and self._detection and mod_items:
            results = validation_svc.validate_cached(mod_items, self._detection)
            errors   = [r for r in results if r.status == "error"]
            warnings = [r for r in results if r.status == "warn"]
            if errors:
                self._show_install_warn(errors, warnings, allow_proceed=False)
                return
            if warnings:
                self._show_install_warn(errors, warnings, allow_proceed=True, items=items)
                return
        self._do_install(self._sort_for_install(items))

    def _sort_for_install(self, items: list) -> list:
        """Sort cache items in dependency-correct install order via resolve_install_order."""
        try:
            from .....utils.dependency_resolver import resolve_install_order
            from .....shared.data.pipeline_state import InstallRecord

            staged = [ci.content for ci in items]
            available: dict = {}
            installed: dict = {}
            registry_svc = self._host.get_service("registry")
            if registry_svc and self._game_id:
                for m in registry_svc.get_mods(self._game_id):
                    mid = getattr(m, "mod_id", "")
                    if mid:
                        available[mid] = m
            if self._game_id:
                from .....shared.data.install_state import InstallStateManager
                installed = {
                    d.get("mod_id", ""): InstallRecord.from_dict(d)
                    for d in InstallStateManager(self._game_id).get_all()
                    if d.get("mod_id")
                }
            ordered_content, _, _ = resolve_install_order(staged, available, installed)
            # Re-map ordered content back to _CacheItem objects
            content_to_ci = {id(ci.content): ci for ci in items}
            result = [content_to_ci[id(c)] for c in ordered_content if id(c) in content_to_ci]
            # Append any items whose content wasn't in ordered_content (shouldn't happen)
            seen = {id(ci) for ci in result}
            result += [ci for ci in items if id(ci) not in seen]
            return result
        except Exception as exc:
            self._host.log(f"[cache] WARN: dependency sort failed, using original order: {exc}")
            return items

    def _on_install_all(self) -> None:
        self._validate_and_install(self._cached)

    def _show_install_warn(self, errors, warnings, allow_proceed: bool,
                           items: Optional[list] = None) -> None:
        from .....shared.ui.dialogs.validation_warning_dialog import ValidationWarningDialog
        install_items = items or self._cached
        lines  = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title  = "Cannot Install" if not allow_proceed else "Install with Warnings?"
        ValidationWarningDialog.for_install(
            title=title,
            lines=lines,
            allow_proceed=allow_proceed,
            on_confirm=lambda: self._do_install(install_items),
        ).open()

    def _do_install(self, items: list) -> None:
        deploy_svc = self._host.get_service("deploy")
        if not deploy_svc or not self._detection:
            return

        game_id = self._game_id
        for ci in list(items):
            try:
                if ci.category == "template":
                    if not (self._ue4ss_detected and self._framework_detected):
                        self._host.log(
                            f"[downloads] Skipped template '{ci.display_name}': "
                            "framework mod required"
                        )
                        continue
                elif ci.category == "mod":
                    if not self._ue4ss_detected:
                        self._host.log(
                            f"[downloads] Skipped mod '{ci.display_name}': UE4SS required"
                        )
                        continue
                deploy_svc.deploy_content(ci.cache_path, ci.content, self._detection, game_id)
                self._host.log(f"[downloads] Installed {ci.display_name}")
            except Exception as exc:
                self._host.log(f"[downloads] Install failed for {ci.display_name}: {exc}")

        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()

        from .....shared.data.content_types import BinaryDescriptor
        ue4ss_installed = any(
            isinstance(ci.content, BinaryDescriptor) and ci.install_type == "ue4ss"
            for ci in items
        )
        if ue4ss_installed:
            profile = self._host.get_game_context()
            if profile:
                from .......core.ue4ss import UE4SSDetector
                new_detection = UE4SSDetector.detect(profile.game_root)
                self._detection = new_detection
                self._host.set_game_context(profile, new_detection)

        if self._on_switch_to_installed:
            self._on_switch_to_installed()
