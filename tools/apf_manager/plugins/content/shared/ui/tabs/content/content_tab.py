"""
Tab 2 — Content

Merges Templates and Mods into a single browsable tab.
Browse registry content and stage items for download.

Sections (collapsible):
  - Templates: per-registry template entries with conflict badges
  - Mods: framework status banner + per-mod rows with component badges

Queue flow: check items → [Queue for Download →] → validate_staged → on_queue callback
"""

from __future__ import annotations

from typing import Optional, Callable

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from .......gui.widgets.tip_icon_button import TipIconButton
from .....services.mod_service import _FRAMEWORK_MOD_RE
from .....shared.ui.constants import COL_CPP, COL_BP, COL_DIM, COL_WARN
from .....shared.ui.hover_row import HoverRow
from .....shared.ui.section_header import make_section_header
from .templates_section import TemplatesSectionMixin
from .mods_section import ModsSectionMixin


class ContentTab(TemplatesSectionMixin, ModsSectionMixin, MDBoxLayout):
    """Tab 2 — Content (registry templates + mods with component badges)."""

    def __init__(self, host, on_queue: Optional[Callable] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._on_queue = on_queue       # called with list[(obj, category)]
        self._game_id: str = ""
        self._checked: set[str] = set()
        self._all_mods: list = []
        self._all_templates: list = []
        self._all_other: list = []
        self._cached_other_items: list = []   # loaded in background; avoids main-thread HTTP
        # Framework state (set by mods_panel via set_framework_state)
        self._ue4ss_ok: bool = False
        self._fw_dir = None
        self._fw_conflict: list = []
        # Collapsed sections (section title → True if collapsed)
        self._collapsed: set[str] = set()
        # Expanded row detail panels
        self._expanded: set[str] = set()
        self._build_ui()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1),
            padding=(dp(8), 0), spacing=dp(4),
        )
        from kivymd.uix.button import MDButtonIcon
        self._btn_check_all = MDButton(
            MDButtonIcon(icon="checkbox-multiple-marked"),
            MDButtonText(text="Select All"),
            style="outlined", size_hint=(None, None), size=(dp(128), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._check_all(True),
        )
        self._btn_uncheck_all = MDButton(
            MDButtonIcon(icon="checkbox-multiple-blank-outline"),
            MDButtonText(text="Select None"),
            style="outlined", size_hint=(None, None), size=(dp(128), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._check_all(False),
        )
        toolbar.add_widget(self._btn_check_all)
        toolbar.add_widget(self._btn_uncheck_all)
        toolbar.add_widget(Widget(size_hint_x=1))
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Refresh registry content",
            on_release=lambda *_: self._load_other_items_bg(),
        ))
        self._btn_queue = MDButton(
            MDButtonText(text="Queue for Download"),
            style="filled", size_hint=(None, None), size=(dp(200), dp(36)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_queue_pressed(),
        )
        self._btn_queue.disabled = True
        toolbar.add_widget(self._btn_queue)
        self.add_widget(toolbar)

        self.add_widget(MDLabel(
            text=(
                "Browse mods and templates from your registries. Select items to queue them "
                "for download. Templates provide reusable logic and vocabulary for mod "
                "capabilities — mods that depend on them require templates to be installed "
                "to the framework mod folder."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        self._scroll = ScrollView(size_hint=(1, 1))
        self._list = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None, adaptive_height=True,
            spacing=dp(2), padding=[dp(8), dp(4)],
        )
        self._scroll.add_widget(self._list)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, game_id: str) -> None:
        if self._game_id != game_id:
            self._cached_other_items = []   # invalidate cache on game change
        self._game_id = game_id
        self._load_other_items_bg()

    def set_framework_state(self, ue4ss_ok: bool, fw_dir, fw_conflict: list) -> None:
        """Called by mods_panel after detection — drives section notices."""
        self._ue4ss_ok = ue4ss_ok
        self._fw_dir = fw_dir
        self._fw_conflict = list(fw_conflict) if fw_conflict else []
        self._do_refresh()   # framework state doesn't require re-fetching Other items

    def _do_refresh(self) -> None:
        self._list.clear_widgets()
        self._all_mods = []
        self._all_templates = []
        self._all_other = []

        # --- Framework state notices ---
        if self._fw_conflict:
            self._list.add_widget(self._conflict_banner(self._fw_conflict))
        elif self._ue4ss_ok and self._fw_dir is None:
            self._list.add_widget(self._no_framework_notice())

        registry_svc = self._host.get_service("registry")
        if not registry_svc:
            self._list.add_widget(self._empty_label("No registry service available."))
            return

        # --- Templates section ---
        templates = registry_svc.get_templates(self._game_id) or []
        self._all_templates = templates
        if templates:
            collapsed = "Templates" in self._collapsed
            self._list.add_widget(self._section_header(
                "Templates", "file-tree", len(templates), collapsed=collapsed
            ))
            if not collapsed:
                for i, tmpl in enumerate(templates):
                    self._list.add_widget(self._template_row(tmpl, i))

        # --- Mods section ---
        mods = registry_svc.get_mods(self._game_id) or []
        self._all_mods = mods

        if mods:
            collapsed = "Mods" in self._collapsed
            self._list.add_widget(self._section_header(
                "Mods", "layers-search", len(mods), collapsed=collapsed
            ))
            if not collapsed:
                has_framework = any(
                    _FRAMEWORK_MOD_RE.match(getattr(m, "mod_id", "") or "") for m in mods
                )
                if not has_framework:
                    self._list.add_widget(self._framework_banner())

                # Group mods by source_package_id where multiple mods share the same package
                from collections import defaultdict as _dd
                pkg_groups: dict = _dd(list)
                for mod in mods:
                    pkg_id = getattr(mod, "source_package_id", "") or f"{mod.owner}/{mod.repo}"
                    pkg_groups[pkg_id].append(mod)

                row_idx = 0
                for pkg_id, pkg_mods in pkg_groups.items():
                    if len(pkg_mods) > 1:
                        pkg_collapsed = f"pkg:{pkg_id}" in self._collapsed
                        self._list.add_widget(self._package_header(pkg_id, pkg_mods, pkg_collapsed))
                        if not pkg_collapsed:
                            for mod in pkg_mods:
                                self._list.add_widget(self._mod_row(mod, row_idx, indent=True))
                                row_idx += 1
                    else:
                        self._list.add_widget(self._mod_row(pkg_mods[0], row_idx))
                        row_idx += 1
        elif not templates:
            self._list.add_widget(self._empty_label(
                "No content available.\nAdd a registry in the Registries tab."
            ))

        # --- Other section (UE4SS + framework binaries) ---
        other_items = self._cached_other_items
        self._all_other = other_items
        if other_items:
            collapsed = "Other" in self._collapsed
            self._list.add_widget(self._section_header(
                "Other", "package-variant", len(other_items), collapsed=collapsed
            ))
            if not collapsed:
                for i, item in enumerate(other_items):
                    self._list.add_widget(self._other_row(item, i))

        self._sync_queue_btn()

    def _load_other_items_bg(self) -> None:
        """Fetch UE4SS + framework Other items in a background thread, then refresh."""
        import threading

        game_id = self._game_id

        def _bg():
            try:
                from .....services.registry_service import _OtherEntry, _compute_other_entry_hash
                registry_svc = self._host.get_service("registry")
                updates_svc = (self._host.get_service("updates")
                               if self._host.has_service("updates") else None)

                registry_ue4ss = (
                    registry_svc.get_other_content(game_id)
                    if registry_svc and hasattr(registry_svc, "get_other_content")
                    else []
                ) or []

                sep = " \u2022 "
                enriched_custom = []
                for entry in registry_ue4ss:
                    if entry.type == "github_release" and entry.owner and entry.repo and entry.tag:
                        fork_releases = (
                            updates_svc.get_ue4ss_releases_for_content(entry.owner, entry.repo)
                            if updates_svc else []
                        ) or []
                        matched = next((r for r in fork_releases if r.tag == entry.tag), None)
                        if matched:
                            reg_pfx = (f"{entry.registry_owner}/{entry.registry_repo}"
                                       if entry.registry_owner else "")
                            fork_pfx = f"{entry.owner}/{entry.repo}"
                            subtitle = f"{reg_pfx}{sep}{fork_pfx}" if reg_pfx else fork_pfx
                            new_entry = _OtherEntry(
                                name           = f"{entry.repo}{sep}{entry.note}",
                                note           = subtitle,
                                type           = entry.type,
                                owner          = entry.owner,
                                repo           = entry.repo,
                                tag            = entry.tag,
                                url            = matched.url,
                                install_type   = entry.install_type,
                                published_at   = matched.published_at,
                                asset_name     = matched.asset_name,
                                changelog      = matched.changelog,
                                assets         = matched.assets,
                                docs           = entry.docs,
                                registry_owner = entry.registry_owner,
                                registry_repo  = entry.registry_repo,
                                prerelease     = matched.prerelease,
                            )
                            new_entry.content_hash = _compute_other_entry_hash(new_entry)
                            enriched_custom.append(new_entry)
                        else:
                            entry.content_hash = _compute_other_entry_hash(entry)
                            enriched_custom.append(entry)
                    elif entry.type == "manual":
                        reg_pfx = (f"{entry.registry_owner}/{entry.registry_repo}"
                                   if entry.registry_owner else "")
                        subtitle = f"{reg_pfx}{sep}MANUAL" if reg_pfx else "MANUAL"
                        new_entry = _OtherEntry(
                            name           = f"UE4SS{sep}{entry.note}",
                            note           = subtitle,
                            type           = entry.type,
                            owner          = entry.owner,
                            repo           = entry.repo,
                            tag            = entry.tag,
                            url            = entry.url,
                            install_type   = entry.install_type,
                            docs           = entry.docs,
                            registry_owner = entry.registry_owner,
                            registry_repo  = entry.registry_repo,
                        )
                        new_entry.content_hash = _compute_other_entry_hash(new_entry)
                        enriched_custom.append(new_entry)
                    else:
                        enriched_custom.append(entry)

                ue4ss_official = (
                    updates_svc.get_ue4ss_releases_for_content("UE4SS-RE", "RE-UE4SS")
                    if updates_svc and hasattr(updates_svc, "get_ue4ss_releases_for_content")
                    else []
                ) or []

                fw_items = (
                    updates_svc.get_framework_releases_for_content()
                    if updates_svc and hasattr(updates_svc, "get_framework_releases_for_content")
                    else []
                ) or []

                combined = enriched_custom + ue4ss_official + fw_items
                self._cached_other_items = _dedup_other_items(combined)
            except Exception:
                import traceback
                traceback.print_exc()
                self._cached_other_items = []

            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._do_refresh(), 0)

        threading.Thread(target=_bg, daemon=True).start()
        self._do_refresh()

    # -----------------------------------------------------------------------
    # Row builders (section headers + shared expand toggle)
    # -----------------------------------------------------------------------

    _ACCENT_COLORS = {
        "Templates": (0.2, 0.7, 0.6, 1),
        "Mods":      (0.3, 0.5, 0.9, 1),
        "Other":     (0.8, 0.55, 0.1, 1),
    }

    def _section_header(self, title: str, icon: str, count: int,
                        collapsed: bool = False) -> MDBoxLayout:
        accent = self._ACCENT_COLORS.get(title, (0.5, 0.5, 0.7, 1))
        return make_section_header(
            title=title, icon=icon, count=count,
            accent_color=accent, collapsed=collapsed,
            on_toggle=self._toggle_section,
        )

    def _toggle_section(self, title: str) -> None:
        if title in self._collapsed:
            self._collapsed.discard(title)
        else:
            self._collapsed.add(title)
        self._do_refresh()

    def _toggle_expand(self, key: str) -> None:
        if key in self._expanded:
            self._expanded.discard(key)
        else:
            self._expanded.clear()
            self._expanded.add(key)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    @staticmethod
    def _empty_label(text: str) -> MDLabel:
        return MDLabel(
            text=text, halign="center",
            size_hint=(1, None), height=dp(80),
            theme_text_color="Secondary",
        )

    # -----------------------------------------------------------------------
    # Check / queue logic
    # -----------------------------------------------------------------------

    def _on_check(self, key: str, checked: bool) -> None:
        if checked:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self._sync_queue_btn()

    def _on_mod_check(self, key: str, checked: bool, mod) -> None:
        self._on_check(key, checked)

    def _check_all(self, checked: bool) -> None:
        for mod in self._all_mods:
            folder = getattr(mod, "folder", getattr(mod, "mod_id", ""))
            key = f"mod:{folder}"
            self._checked.add(key) if checked else self._checked.discard(key)
        for i, tmpl in enumerate(self._all_templates):
            key = f"tmpl:{getattr(tmpl, 'path', str(i))}"
            self._checked.add(key) if checked else self._checked.discard(key)
        for i, item in enumerate(self._all_other):
            if getattr(item, "type", "manual") == "github_release":
                _hash = getattr(item, "content_hash", "")
                key = (f"other:{_hash}" if _hash else
                       f"other:{getattr(item,'owner','')}+{getattr(item,'repo','')}/{getattr(item,'tag','') or getattr(item,'name',str(i))}")
                self._checked.add(key) if checked else self._checked.discard(key)
        self._sync_queue_btn()
        self._do_refresh()

    def _sync_queue_btn(self) -> None:
        self._btn_queue.disabled = not bool(self._checked)

    def _on_queue_pressed(self) -> None:
        checked_mods = [
            m for m in self._all_mods
            if f"mod:{getattr(m, 'folder', getattr(m, 'mod_id', ''))}" in self._checked
        ]
        checked_templates = [
            t for i, t in enumerate(self._all_templates)
            if f"tmpl:{getattr(t, 'path', str(i))}" in self._checked
        ]
        checked_other = []
        for i, item in enumerate(self._all_other):
            if getattr(item, "type", "manual") != "github_release":
                continue
            _hash = getattr(item, "content_hash", "")
            _key = (f"other:{_hash}" if _hash else
                    f"other:{getattr(item,'owner','')}+{getattr(item,'repo','')}/{getattr(item,'tag','') or getattr(item,'name',str(i))}")
            if _key not in self._checked:
                continue
            if not any(getattr(a, "selected", False) for a in (getattr(item, "assets", []) or [{"selected": True}])):
                continue
            checked_other.append(item)

        if not checked_mods and not checked_templates and not checked_other:
            return

        validation_svc = self._host.get_service("validation")
        if validation_svc and checked_mods:
            mods_svc = self._host.get_service("mods")
            installed_ids: set = set()
            if mods_svc:
                installed_ids = {m.mod_id for m in mods_svc.scan() if m.mod_id}
            results = validation_svc.validate_staged(
                checked_mods, self._game_id, installed_ids
            )
            errors   = [r for r in results if r.status == "error"]
            warnings = [r for r in results if r.status == "warn"]
            if errors:
                self._show_validation_dlg(errors, warnings, checked_mods, checked_templates,
                                          checked_other, allow_proceed=False)
                return
            if warnings:
                self._show_validation_dlg(errors, warnings, checked_mods, checked_templates,
                                          checked_other, allow_proceed=True)
                return

        self._do_queue(checked_mods, checked_templates, checked_other)

    def _show_validation_dlg(self, errors, warnings, mods, templates,
                              other=None, allow_proceed: bool = False) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        lines = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title = "Cannot Queue" if not allow_proceed else "Queue with Warnings?"
        text  = "\n".join(lines) or "Validation issue."
        _other = other or []

        btns: list = [
            Widget(),
            MDButton(MDButtonText(text="Cancel"), style="text",
                     on_release=lambda *_: dlg.dismiss()),
        ]
        if allow_proceed:
            btns.append(MDButton(
                MDButtonText(text="Queue Anyway"), style="filled",
                on_release=lambda *_, m=mods, t=templates, o=_other: (
                    dlg.dismiss(), self._do_queue(m, t, o)
                ),
            ))

        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text=text),
            MDDialogButtonContainer(*btns),
        )
        dlg.open()

    def _do_queue(self, mods: list, templates: Optional[list] = None,
                  other: Optional[list] = None) -> None:
        if templates is None:
            templates = []
        if other is None:
            other = []
        items = (
            [(m, "mod") for m in mods]
            + [(t, "template") for t in templates]
            + [(o, "other") for o in other]
        )
        if self._on_queue:
            self._on_queue(items)
        for mod in mods:
            folder = getattr(mod, "folder", getattr(mod, "mod_id", ""))
            self._checked.discard(f"mod:{folder}")
        for i, tmpl in enumerate(templates):
            path = getattr(tmpl, "path", str(i))
            self._checked.discard(f"tmpl:{path}")
        for i, item in enumerate(other):
            _hash = getattr(item, "content_hash", "")
            key = (f"other:{_hash}" if _hash else
                   f"other:{getattr(item,'owner','')}+{getattr(item,'repo','')}/{getattr(item,'tag','') or getattr(item,'name',str(i))}")
            self._checked.discard(key)
        self._sync_queue_btn()
        self._do_refresh()

    # -----------------------------------------------------------------------
    # Badge count
    # -----------------------------------------------------------------------

    def get_available_count(self) -> int:
        return len(self._all_mods) + len(self._all_templates) + len(self._all_other)


def _dedup_other_items(items: list) -> list:
    """Deduplicate Other items by endpoint (owner:repo:tag:install_type). First occurrence wins."""
    seen_endpoints: dict = {}
    result = []
    for item in items:
        ep = "{}:{}:{}:{}".format(
            getattr(item, "owner", ""),
            getattr(item, "repo", ""),
            getattr(item, "tag", ""),
            getattr(item, "install_type", ""),
        )
        if ep in seen_endpoints:
            seen_endpoints[ep].has_duplicate_source = True
        else:
            seen_endpoints[ep] = item
            result.append(item)
    return result
