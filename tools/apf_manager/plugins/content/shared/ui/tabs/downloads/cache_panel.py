"""cache_panel.py — CachePanelMixin: cached items list + install/remove logic."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
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
            from kivymd.uix.boxlayout import MDBoxLayout as _BL
            from kivymd.uix.label import MDLabel as _ML
            size_row = _BL(orientation="horizontal", size_hint_y=None, height=dp(22),
                           padding=[dp(16), 0, dp(8), 0])
            size_row.add_widget(_ML(
                text=f"Cache size: {size:.1f} MB",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            outer.add_widget(size_row)

        # Changelog button for GRB
        if isinstance(ci.content, _GRB) and ci.content.source and ci.content.source.changelog:
            changelog = ci.content.source.changelog

            def _show_changelog(*_, _cl=changelog, _nm=ci.display_name):
                from kivymd.uix.dialog import (
                    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
                    MDDialogButtonContainer,
                )
                dlg_ref = [None]
                def _close(*_):
                    if dlg_ref[0]:
                        dlg_ref[0].dismiss()
                dlg = MDDialog(
                    MDDialogHeadlineText(text="Release Notes"),
                    MDDialogSupportingText(text=_cl[:500]),
                    MDDialogButtonContainer(
                        MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
                    ),
                )
                dlg_ref[0] = dlg
                dlg.open()

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
        except Exception:
            pass
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
            except Exception:
                pass
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
        self._do_install(items)

    def _on_install_all(self) -> None:
        self._validate_and_install(self._cached)

    def _show_install_warn(self, errors, warnings, allow_proceed: bool,
                           items: Optional[list] = None) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        lines  = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title  = "Cannot Install" if not allow_proceed else "Install with Warnings?"
        install_items = items or self._cached
        btns: list = [
            Widget(),
            MDButton(MDButtonText(text="Cancel"), style="text",
                     on_release=lambda *_: dlg.dismiss()),
        ]
        if allow_proceed:
            btns.append(MDButton(
                MDButtonText(text="Install Anyway"), style="filled",
                on_release=lambda *_: (dlg.dismiss(), self._do_install(install_items)),
            ))
        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text="\n".join(lines) or "Validation issue."),
            MDDialogButtonContainer(*btns),
        )
        dlg.open()

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
