"""cache_panel.py — CachePanelMixin: cached items list + install/remove logic."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from .....shared.ui.constants import COL_CPP, COL_BP, COL_DIM

if TYPE_CHECKING:
    from .downloads_tab import _CacheItem


_BG_ITEM = (0.13, 0.13, 0.13, 1)


class CachePanelMixin:
    """Cached item row builder and install/remove logic for DownloadsTab."""

    def _cache_row(self, ci: "_CacheItem") -> MDBoxLayout:
        cache_key = str(ci.cache_path)
        is_checked = cache_key in self._selected_cache
        expanded   = cache_key in self._expanded_cache

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM,
        )

        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            padding=[dp(4), dp(4)], spacing=dp(4),
        )

        chk = MDCheckbox(
            size_hint=(None, None), size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
            active=is_checked,
        )
        chk.bind(active=lambda inst, val, k=cache_key: self._on_cache_check(k, val))
        header.add_widget(chk)

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        name_row.add_widget(MDLabel(
            text=ci.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        if "cpp" in ci.components:
            name_row.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=COL_CPP,
            ))
        if "blueprint" in ci.components:
            name_row.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=COL_BP,
            ))
        info.add_widget(name_row)

        sub_parts = []
        if ci.version:
            sub_parts.append(f"v{ci.version}")
        size = ci.size_mb
        if size > 0:
            sub_parts.append(f"{size:.1f} MB")
        if ci.owner or ci.repo:
            sub_parts.append(f"{ci.owner}/{ci.repo}")
        info.add_widget(MDLabel(
            text="  ·  ".join(sub_parts),
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=COL_DIM,
        ))
        header.add_widget(info)

        chevron_icon = "chevron-up" if expanded else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=cache_key: self._toggle_cache_expand(k),
        ))
        def _on_header_touch(w, touch, k=cache_key):
            if w.collide_point(*touch.pos) and touch.button == "left":
                self._toggle_cache_expand(k)
                return True
        info.bind(on_touch_down=_on_header_touch)
        container.add_widget(header)

        if expanded:
            container.add_widget(self._cache_detail(ci))
        return container

    def _cache_detail(self, ci: "_CacheItem") -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.08, 0.09, 0.11, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )
        if ci.owner or ci.repo:
            panel.add_widget(MDLabel(
                text=f"Source: {ci.owner}/{ci.repo}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        if ci.version:
            panel.add_widget(MDLabel(
                text=f"Version: v{ci.version}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        comp_labels = {"lua": "Lua", "cpp": "C++", "blueprint": "Blueprint"}
        comp_texts = [comp_labels.get(c, c) for c in ci.components]
        if comp_texts:
            comp_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(18), spacing=dp(8),
            )
            comp_row.add_widget(MDLabel(
                text="Components:",
                font_style="Label", role="small", size_hint=(None, 1), width=dp(80),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            for ct in comp_texts:
                comp_row.add_widget(MDLabel(
                    text=ct, font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(64),
                    theme_text_color="Custom", text_color=(0.6, 0.8, 1.0, 1),
                ))
            panel.add_widget(comp_row)
        size = ci.size_mb
        if size > 0:
            panel.add_widget(MDLabel(
                text=f"Cache size: {size:.1f} MB",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        cat_display = {"template": "Template", "mod": "Mod", "other": "Other"}.get(
            ci.category, ci.category.capitalize() if ci.category else "Mod"
        )
        panel.add_widget(MDLabel(
            text=f"Category: {cat_display}",
            font_style="Label", role="small", size_hint_y=None, height=dp(16),
            theme_text_color="Custom", text_color=COL_DIM,
        ))
        from .....shared.data.content_types import GithubReleaseBinary
        _other_ref = ci.mod_ref
        if ci.category == "other" and isinstance(ci.content, GithubReleaseBinary) and ci.content.source:
            _other_ref = ci.content
        if ci.category == "other" and _other_ref is None:
            registry_svc = self._host.get_service("registry") if self._host.has_service("registry") else None
            updates_svc = self._host.get_service("updates") if self._host.has_service("updates") else None
            all_other: list = []
            if registry_svc and hasattr(registry_svc, "get_other_content"):
                all_other += registry_svc.get_other_content(self._game_id) or []
            if updates_svc and hasattr(updates_svc, "get_ue4ss_releases_for_content"):
                all_other += updates_svc.get_ue4ss_releases_for_content() or []
            if updates_svc and hasattr(updates_svc, "get_framework_releases_for_content"):
                all_other += updates_svc.get_framework_releases_for_content() or []
            for entry in all_other:
                if (getattr(entry, "owner", "") == ci.owner and
                        getattr(entry, "repo", "") == ci.repo):
                    _other_ref = entry
                    break
        if ci.category == "other" and _other_ref is not None:
            if isinstance(_other_ref, GithubReleaseBinary) and _other_ref.source:
                changelog = _other_ref.source.changelog
            else:
                changelog = getattr(_other_ref, "changelog", "")
            if changelog:
                def _show_changelog(*_, _cl=changelog):
                    from kivymd.uix.dialog import (
                        MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
                        MDDialogButtonContainer,
                    )
                    from kivymd.uix.button import MDButton, MDButtonText
                    dlg_ref = [None]
                    def _close(*_):
                        if dlg_ref[0]:
                            dlg_ref[0].dismiss()
                    dlg = MDDialog(
                        MDDialogHeadlineText(text="Release Notes"),
                        MDDialogSupportingText(text=_cl),
                        MDDialogButtonContainer(
                            MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
                        ),
                    )
                    dlg_ref[0] = dlg
                    dlg.open()
                from kivymd.uix.button import MDButton, MDButtonText
                panel.add_widget(MDButton(
                    MDButtonText(text="Release Notes"),
                    style="text",
                    size_hint_y=None, height=dp(36),
                    on_release=_show_changelog,
                ))
        return panel

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
                    game_name = ci.game_name or game_id
                    deploy_svc.deploy_template(ci.cache_path, game_name)
                    self._host.log(f"[downloads] Installed template {ci.display_name}")

                elif ci.category == "other":
                    deploy_svc.deploy_other(ci.cache_path, ci.install_type, self._detection)
                    self._host.log(f"[downloads] Installed other '{ci.display_name}'")

                else:
                    if not self._ue4ss_detected:
                        self._host.log(
                            f"[downloads] Skipped mod '{ci.display_name}': UE4SS required"
                        )
                        continue
                    components   = ci.components
                    bp_pak_files = ci.bp_pak_files
                    from .....shared.data.content_types import APModDescriptor
                    metadata     = {
                        "content_type":  ci.content.content_type if ci.content else "ap_mod",
                        "name":          ci.display_name,
                        "mod_id":        ci.content.mod_id if isinstance(ci.content, APModDescriptor) else (getattr(ci.mod_ref, "mod_id", "") if ci.mod_ref else ""),
                        "folder_name":   ci.folder_name,
                        "source_repo":   f"{ci.owner}/{ci.repo}",
                        "source_folder": ci.folder_name,
                        "version":       ci.version,
                        "description":   ci.content.description if hasattr(ci.content, "description") else "",
                        "author":        ci.content.author if hasattr(ci.content, "author") else "",
                    }
                    deploy_svc.deploy_mod(
                        ci.cache_path, ci.folder_name,
                        components, bp_pak_files,
                        self._detection, game_id, metadata,
                    )
                    self._host.log(f"[downloads] Installed mod {ci.display_name}")

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
