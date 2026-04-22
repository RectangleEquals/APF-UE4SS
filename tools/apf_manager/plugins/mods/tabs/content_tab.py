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

from kivy.animation import Animation
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from ....gui.widgets.tip_icon_button import TipIconButton
from ..mod_service import _FRAMEWORK_MOD_RE


_BG_SECTION   = (0.07, 0.09, 0.12, 1)
_BG_ROW_EVEN  = (0.13, 0.13, 0.13, 1)
_BG_ROW_ODD   = (0.11, 0.11, 0.11, 1)
_BG_BANNER    = (0.20, 0.14, 0.06, 1)
_COL_WARN     = (0.9, 0.6, 0.1, 1)
_COL_CPP      = (0.4, 0.7, 1.0, 1)
_COL_BP       = (1.0, 0.6, 0.2, 1)
_COL_SECTION  = (0.85, 0.85, 0.95, 1)
_COL_DIM      = (0.5, 0.5, 0.5, 1)


_HOVER_DURATION_IN  = 0.08
_HOVER_DURATION_OUT = 0.30
_TARGET_ALPHA       = 0.07


class _HoverRow(HoverBehavior, MDBoxLayout):
    """MDBoxLayout with animated hover feedback — used for expandable github_release rows."""

    _hovering = False

    def on_enter(self):
        if self._hovering:
            return
        self._hovering = True
        from kivy.core.window import Window
        Window.set_system_cursor("hand")
        current_alpha = (self.md_bg_color or [0, 0, 0, 0])[3]
        remaining = _TARGET_ALPHA - current_alpha
        if remaining <= 0:
            return
        duration = max(_HOVER_DURATION_IN * (remaining / _TARGET_ALPHA), 0.01)
        Animation(md_bg_color=(1, 1, 1, _TARGET_ALPHA), duration=duration).start(self)

    def on_leave(self):
        if not self._hovering:
            return
        self._hovering = False
        from kivy.core.window import Window
        Window.set_system_cursor("arrow")
        current_alpha = (self.md_bg_color or [0, 0, 0, 0])[3]
        if current_alpha <= 0:
            return
        duration = max(_HOVER_DURATION_OUT * (current_alpha / _TARGET_ALPHA), 0.01)
        Animation(md_bg_color=(0, 0, 0, 0), duration=duration).start(self)

    def on_parent(self, widget, parent):
        if parent is None:
            self._hovering = False
            from kivy.core.window import Window
            Window.set_system_cursor("arrow")
            Animation.cancel_all(self, "md_bg_color")
            self.md_bg_color = (0, 0, 0, 0)


class ContentTab(MDBoxLayout):
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
                        # Multi-mod package — show collapsible group header
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
        # Populated by _load_other_items_bg(); read from cache here to avoid main-thread HTTP
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
                from ..registry_service import _OtherEntry, _compute_other_entry_hash
                registry_svc = self._host.get_service("registry")
                updates_svc = (self._host.get_service("updates")
                               if self._host.has_service("updates") else None)

                registry_ue4ss = (
                    registry_svc.get_other_content(game_id)
                    if registry_svc and hasattr(registry_svc, "get_other_content")
                    else []
                ) or []

                # Enrich custom entries with real GitHub release metadata
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

                # Always use official UE4SS-RE/RE-UE4SS for official releases (never overridden)
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

                # Custom entries appear above official; deduplicate by endpoint
                combined = enriched_custom + ue4ss_official + fw_items
                self._cached_other_items = _dedup_other_items(combined)
            except Exception:
                import traceback
                traceback.print_exc()
                self._cached_other_items = []

            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._do_refresh(), 0)

        threading.Thread(target=_bg, daemon=True).start()
        # Show current state immediately while waiting for background result
        self._do_refresh()

    # -----------------------------------------------------------------------
    # Row builders
    # -----------------------------------------------------------------------

    # Accent bar colors per content category
    _ACCENT_COLORS = {
        "Templates": (0.2, 0.7, 0.6, 1),   # teal
        "Mods":      (0.3, 0.5, 0.9, 1),   # blue
        "Other":     (0.8, 0.55, 0.1, 1),  # amber
    }

    def _section_header(self, title: str, icon: str, count: int,
                        collapsed: bool = False) -> MDBoxLayout:
        accent = self._ACCENT_COLORS.get(title, (0.5, 0.5, 0.7, 1))
        outer = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36),
            md_bg_color=_BG_SECTION,
        )
        outer.add_widget(MDBoxLayout(
            size_hint=(None, 1), width=dp(3),
            md_bg_color=accent,
        ))
        inner = MDBoxLayout(
            orientation="horizontal", size_hint=(1, 1),
            padding=[dp(8), 0], spacing=dp(8),
        )
        inner.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=_COL_SECTION,
        ))
        inner.add_widget(MDLabel(
            text=f"{title}  ({count})", font_style="Title", role="small",
            size_hint_x=1, halign="left",
            theme_text_color="Custom", text_color=_COL_SECTION,
        ))
        chevron = MDIcon(
            icon="chevron-right" if collapsed else "chevron-down",
            size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=_COL_DIM,
        )
        inner.add_widget(chevron)
        outer.add_widget(inner)
        # Make entire header row clickable to toggle collapse
        outer.bind(on_touch_down=lambda w, t: self._on_section_toggle(title, w, t))
        return outer

    def _on_section_toggle(self, title: str, widget, touch) -> bool:
        if not widget.collide_point(*touch.pos):
            return False
        if title in self._collapsed:
            self._collapsed.discard(title)
        else:
            self._collapsed.add(title)
        self._do_refresh()
        return True

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
            theme_icon_color="Custom", icon_color=_COL_WARN,
        ))
        row.add_widget(MDLabel(
            text=(
                "Framework mod not installed — Templates and Mods cannot be deployed. "
                "Install it via the Other section or Registries tab."
            ),
            theme_text_color="Custom", text_color=_COL_WARN,
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
            theme_icon_color="Custom", icon_color=_COL_WARN,
        ))
        row.add_widget(MDLabel(
            text="No AP Framework mod found in this registry",
            theme_text_color="Custom", text_color=_COL_WARN,
        ))
        return row

    def _template_row(self, tmpl, index: int) -> MDBoxLayout:
        key = f"tmpl:{getattr(tmpl, 'path', str(index))}"
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

        has_conflict = getattr(tmpl, "has_conflict", False)
        if has_conflict:
            header.add_widget(MDIcon(
                icon="alert-circle", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_WARN,
            ))

        path = getattr(tmpl, "path", "")
        label = path.rsplit("/", 1)[-1] if path else "Template"
        registry_lbl = f"{tmpl.owner}/{tmpl.repo}" if hasattr(tmpl, "owner") else ""

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info.add_widget(MDLabel(
            text=label, font_style="Body", size_hint_y=None, height=dp(22),
        ))
        if registry_lbl:
            info.add_widget(MDLabel(
                text=registry_lbl, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        # Clicking anywhere on the info area also toggles expand
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
        """Expanded detail panel for a template entry."""
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(6)], spacing=dp(4),
        )
        owner = getattr(tmpl, "owner", "")
        repo  = getattr(tmpl, "repo", "")
        path  = getattr(tmpl, "path", "")

        # Source
        if owner and repo:
            panel.add_widget(MDLabel(
                text=f"Source: {owner}/{repo}",
                font_style="Label", role="small", size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))

        # Files provided
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
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
            panel.add_widget(row)
        if len(file_paths) > 8:
            panel.add_widget(MDLabel(
                text=f"… and {len(file_paths) - 8} more files",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))

        # Install target
        if templates_dir:
            panel.add_widget(MDLabel(
                text=f"Target: {templates_dir}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        elif game_name:
            panel.add_widget(MDLabel(
                text="Target: Framework mod not installed",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_WARN,
            ))

        # Dependent mods (mods whose capabilities.include overlaps this template's path)
        deps = [
            m for m in self._all_mods
            if path and path in getattr(m, "capabilities_includes", [])
        ]
        if deps:
            panel.add_widget(MDLabel(
                text="Used by: " + ", ".join(getattr(m, "name", m.mod_id) for m in deps[:4]),
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        return panel

    def _package_header(self, pkg_id: str, pkg_mods: list, collapsed: bool) -> MDBoxLayout:
        """Collapsible header row for a multi-mod package group."""
        key = f"pkg:{pkg_id}"
        bg = (0.10, 0.13, 0.17, 1)
        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            padding=[dp(8), dp(4)], spacing=dp(8),
        )
        # Aggregate checkbox: check all/none in group
        all_checked = all(f"mod:{getattr(m,'folder',m.mod_id)}" in self._checked for m in pkg_mods)
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = all_checked
        def _on_pkg_check(inst, val, mods=pkg_mods):
            for m in mods:
                k = f"mod:{getattr(m,'folder',m.mod_id)}"
                if val:
                    self._checked.add(k)
                else:
                    self._checked.discard(k)
        cb.bind(active=_on_pkg_check)
        header.add_widget(cb)
        header.add_widget(MDIcon(
            icon="package-variant-closed", size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=(0.5, 0.6, 0.9, 1),
        ))
        pkg_label = pkg_id.split("/")[-1] if "/" in pkg_id else pkg_id
        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info.add_widget(MDLabel(
            text=pkg_label, font_style="Body",
            size_hint_y=None, height=dp(24),
        ))
        info.add_widget(MDLabel(
            text=f"{len(pkg_mods)} components  ·  {pkg_id}",
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=_COL_DIM,
        ))
        info.bind(on_touch_down=lambda w, t: self._toggle_pkg_collapse(key)
                  if w.collide_point(*t.pos) else None)
        header.add_widget(info)
        chevron_icon = "chevron-up" if not collapsed else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=key: self._toggle_pkg_collapse(k),
        ))
        container.add_widget(header)
        return container

    def _toggle_pkg_collapse(self, key: str) -> None:
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _mod_row(self, mod, index: int, indent: bool = False) -> MDBoxLayout:
        folder = getattr(mod, "folder", getattr(mod, "mod_id", str(index)))
        key = f"mod:{folder}"
        components = getattr(mod, "components", ["lua"])
        bg = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )

        left_pad = dp(24) if indent else dp(8)
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            padding=[left_pad, dp(4), dp(8), dp(4)], spacing=dp(8),
        )

        # Checkbox
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = key in self._checked
        cb.bind(active=lambda inst, val, k=key, m=mod: self._on_mod_check(k, val, m))
        header.add_widget(cb)

        # Info column
        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))

        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        display = getattr(mod, "name", folder)
        name_row.add_widget(MDLabel(
            text=display, font_style="Body", size_hint=(1, 1),
            halign="left", valign="middle",
        ))
        if "cpp" in components:
            name_row.add_widget(MDIcon(
                icon="code-braces",
                size_hint=(None, None), size=(dp(20), dp(20)),
                pos_hint={"center_y": 0.5},
                theme_icon_color="Custom", icon_color=_COL_CPP,
            ))
        if "blueprint" in components:
            name_row.add_widget(MDIcon(
                icon="blueprint",
                size_hint=(None, None), size=(dp(20), dp(20)),
                pos_hint={"center_y": 0.5},
                theme_icon_color="Custom", icon_color=_COL_BP,
            ))
        info.add_widget(name_row)

        mod_id = getattr(mod, "mod_id", "")
        desc   = getattr(mod, "description", "")
        if mod_id:
            sub = mod_id
        elif desc:
            sub = desc
        else:
            sub = "Non-AP Mod"
        if sub:
            info.add_widget(MDLabel(
                text=sub, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        # Clicking anywhere on the info area also toggles expand
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
            container.add_widget(self._mod_detail(mod))
        return container

    def _mod_detail(self, mod) -> MDBoxLayout:
        """Expanded detail panel for a registry mod entry."""
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )
        mod_id = getattr(mod, "mod_id", "")
        desc   = getattr(mod, "description", "")
        owner  = getattr(mod, "owner", "")
        repo   = getattr(mod, "repo", "")

        # Description
        if desc:
            panel.add_widget(MDLabel(
                text=desc, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Secondary",
            ))
        elif not mod_id:
            panel.add_widget(MDLabel(
                text="This is a regular UE4SS mod that does not directly contribute toward "
                     "Archipelago randomization on its own.",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(32),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        else:
            panel.add_widget(MDLabel(
                text="No description",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))

        # mod_id
        if mod_id:
            panel.add_widget(MDLabel(
                text=mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))

        # Dependencies
        known_ids = {getattr(m, "mod_id", "") for m in self._all_mods}
        depends = getattr(mod, "depends", []) or []
        if depends:
            dep_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(16),
                spacing=dp(4),
            )
            dep_row.add_widget(MDLabel(
                text="Deps:", font_style="Label", role="small",
                size_hint=(None, 1), width=dp(32),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
            for dep in depends[:5]:
                dep_id = dep.split(" ")[0] if isinstance(dep, str) else str(dep)
                missing = dep_id not in known_ids
                dep_row.add_widget(MDLabel(
                    text=dep_id, font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(max(80, len(dep_id) * 7)),
                    theme_text_color="Custom",
                    text_color=(0.9, 0.3, 0.3, 1) if missing else _COL_DIM,
                ))
            panel.add_widget(dep_row)

        # Incompatibilities
        incompatible = getattr(mod, "incompatible", []) or []
        if incompatible:
            panel.add_widget(MDLabel(
                text="Incompatible: " + ", ".join(str(i) for i in incompatible[:4]),
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.8, 0.5, 0.2, 1),
            ))

        # capabilities.include paths
        includes = getattr(mod, "capabilities_includes", []) or []
        if includes:
            deploy_svc = self._host.get_service("deploy") if self._host.has_service("deploy") else None
            fw_dir = self._fw_dir
            for inc in includes[:4]:
                present = False
                if fw_dir:
                    from pathlib import Path
                    present = (Path(fw_dir) / inc).exists()
                inc_row = MDBoxLayout(
                    orientation="horizontal", size_hint_y=None, height=dp(16), spacing=dp(4),
                )
                inc_row.add_widget(MDIcon(
                    icon="circle-small", size_hint=(None, 1), width=dp(14),
                    theme_icon_color="Custom",
                    icon_color=(0.3, 0.8, 0.4, 1) if present else _COL_WARN,
                ))
                inc_row.add_widget(MDLabel(
                    text=inc, font_style="Label", role="small",
                    size_hint=(1, 1), halign="left",
                    theme_text_color="Custom",
                    text_color=_COL_DIM if present else _COL_WARN,
                ))
                panel.add_widget(inc_row)

        # Submodule content tag
        if getattr(mod, "is_submodule_content", False):
            panel.add_widget(MDLabel(
                text=f"from submodule: {owner}/{repo}",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.6, 0.7, 0.9, 1),
            ))

        # Registry
        if owner and repo:
            reg_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8),
            )
            reg_row.add_widget(MDLabel(
                text=f"{owner}/{repo}", font_style="Label", role="small",
                size_hint=(1, 1), halign="left",
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
            panel.add_widget(reg_row)
        return panel

    def _toggle_expand(self, key: str) -> None:
        if key in self._expanded:
            self._expanded.discard(key)
        else:
            # Auto-collapse sibling rows — only one detail panel open at a time
            self._expanded.clear()
            self._expanded.add(key)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _open_other_docs(self, docs_path: str, owner: str, repo: str,
                          registry_owner: str = "", registry_repo: str = "") -> None:
        """Open documentation for a ue4ss_option entry via the docs_viewer service."""
        docs_svc = self._host.get_service("docs_viewer") if self._host.has_service("docs_viewer") else None
        if not docs_svc:
            return
        # docs_path is relative to the registry repo, not the UE4SS fork repo
        raw_owner = registry_owner or owner
        raw_repo  = registry_repo  or repo
        raw_url = f"https://raw.githubusercontent.com/{raw_owner}/{raw_repo}/HEAD/{docs_path}"
        title = docs_path.rsplit("/", 1)[-1].replace("_", " ").replace(".md", "").title()
        if hasattr(docs_svc, "open_url"):
            docs_svc.open_url(raw_url, title=title, show_sidebar=True, show_mode_toggle=False)

    def _other_row(self, item, index: int) -> MDBoxLayout:
        """Row for an Other-category item (UE4SS option or framework binary release)."""
        opt_type = getattr(item, "type", "manual")
        tag      = getattr(item, "tag", "")
        owner    = getattr(item, "owner", "")
        repo_    = getattr(item, "repo", "")
        _hash    = getattr(item, "content_hash", "")
        if _hash:
            key = f"other:{_hash}"
        else:
            key = f"other:{owner}+{repo_}/{tag or getattr(item, 'name', str(index))}"
        bg       = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )

        if opt_type == "github_release":
            header = _HoverRow(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )
        else:
            header = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )

        if opt_type == "github_release":
            cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                            pos_hint={"center_y": 0.5})
            cb.active = key in self._checked
            cb.bind(active=lambda inst, val, k=key: self._on_check(k, val))
            header.add_widget(cb)
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(24)))

        header.add_widget(MDIcon(
            icon="package-variant", size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=(0.8, 0.55, 0.1, 1),
        ))

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        name_lbl = getattr(item, "name", "Unknown")
        info.add_widget(MDLabel(
            text=name_lbl, font_style="Body",
            size_hint_y=None, height=dp(24),
        ))
        note = getattr(item, "note", "")
        # Show partial-selection hint when some (not all) assets are selected
        _assets = getattr(item, "assets", []) or []
        _n_sel = sum(1 for a in _assets if getattr(a, "selected", False))
        if _assets and 0 < _n_sel < len(_assets):
            note = f"{note}   ({_n_sel}/{len(_assets)} assets)" if note else f"({_n_sel}/{len(_assets)} assets selected)"
        if note:
            info.add_widget(MDLabel(
                text=note, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        if getattr(item, "has_duplicate_source", False):
            info.add_widget(MDLabel(
                text="duplicate source",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom", text_color=(1.0, 0.75, 0.0, 1),
            ))
        # Manual rows are informational-only — no expand toggle
        if opt_type != "manual":
            info.bind(on_touch_down=lambda w, t: self._toggle_expand(key)
                      if w.collide_point(*t.pos) else None)
        header.add_widget(info)

        # Docs slot — always dp(32) wide for column consistency across all row types
        _docs_path = getattr(item, "docs", "")
        if _docs_path:
            _docs_owner = getattr(item, "owner", "")
            _docs_repo  = getattr(item, "repo",  "")
            _reg_owner  = getattr(item, "registry_owner", "")
            _reg_repo   = getattr(item, "registry_repo",  "")
            header.add_widget(MDIconButton(
                icon="file-document-outline",
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, dpath=_docs_path, do=_docs_owner, dr=_docs_repo, ro=_reg_owner, rr=_reg_repo: (
                    self._open_other_docs(dpath, do, dr, ro, rr)
                ),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(32)))

        # Trailing action slot — always dp(32) wide
        if opt_type == "external_url":
            import webbrowser
            url = getattr(item, "url", "")
            header.add_widget(MDButton(
                MDButtonText(text="Open"),
                style="outlined", size_hint=(None, None), size=(dp(72), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, u=url: webbrowser.open(u) if u else None,
            ))
        elif opt_type == "github_release":
            chevron_icon = "chevron-up" if expanded else "chevron-down"
            header.add_widget(MDIconButton(
                icon=chevron_icon,
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, k=key: self._toggle_expand(k),
            ))
        else:  # manual — dp(32) spacer for column alignment (matches chevron width)
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

        container.add_widget(header)

        if expanded:
            container.add_widget(self._other_detail(item, outer_key=key))
        return container

    def _other_detail(self, item, outer_key: str = "") -> MDBoxLayout:
        """Expanded detail panel for an Other-category item."""
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )

        install_type = getattr(item, "install_type", "ue4ss")
        opt_type     = getattr(item, "type", "manual")
        owner        = getattr(item, "owner", "")
        repo_        = getattr(item, "repo", "")
        tag          = getattr(item, "tag", "")
        published_at = getattr(item, "published_at", "")
        asset_name   = getattr(item, "asset_name", "")
        changelog    = getattr(item, "changelog", "")
        assets       = getattr(item, "assets", []) or []

        if install_type == "framework_binary":
            type_label = "Framework Binaries"
        elif opt_type == "manual":
            type_label = "Manual Installation"
        else:
            type_label = "UE4SS experimental" if getattr(item, "prerelease", False) else "UE4SS stable"

        def _detail_row(key_text: str, val_text: str) -> MDBoxLayout:
            r = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8))
            r.add_widget(MDLabel(
                text=key_text, font_style="Label", role="small",
                size_hint=(None, 1), width=dp(96),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
            r.add_widget(MDLabel(
                text=val_text, font_style="Label", role="small",
                size_hint=(1, 1),
            ))
            return r

        panel.add_widget(_detail_row("Type", type_label))
        if owner and repo_:
            panel.add_widget(_detail_row("Source", f"{owner}/{repo_}"))
        if tag:
            panel.add_widget(_detail_row("Tag", tag))
        if published_at:
            panel.add_widget(_detail_row("Published", published_at[:10]))
        if asset_name and not assets:
            panel.add_widget(_detail_row("Asset", asset_name))

        if opt_type == "manual":
            panel.add_widget(MDLabel(
                text="This option requires manual installation. Refer to the UE4SS documentation for this game.",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(36),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))

        # --- Asset sub-rows ---
        if assets:
            sep = MDBoxLayout(size_hint_y=None, height=dp(1), md_bg_color=(0.2, 0.2, 0.25, 1))
            panel.add_widget(sep)
            assets_lbl = MDLabel(
                text="Assets", font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=_COL_DIM,
            )
            panel.add_widget(assets_lbl)

            def _on_asset_check(asset, val, ok=outer_key):
                asset.selected = val
                # Auto-sync outer checkbox: uncheck release if no assets remain selected
                any_selected = any(a.selected for a in assets)
                if not any_selected and ok in self._checked:
                    self._checked.discard(ok)
                    self._sync_queue_btn()
                elif any_selected and ok not in self._checked:
                    self._checked.add(ok)
                    self._sync_queue_btn()
                # Refresh to update partial-selection indicator in row header
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._do_refresh(), 0)

            for asset in assets:
                asset_row = MDBoxLayout(
                    orientation="horizontal", size_hint_y=None, height=dp(28),
                    padding=[dp(8), 0, 0, 0], spacing=dp(8),
                )
                chk = MDCheckbox(
                    size_hint=(None, None), size=(dp(20), dp(20)),
                    pos_hint={"center_y": 0.5},
                )
                chk.active = asset.selected
                chk.bind(active=lambda inst, val, a=asset: _on_asset_check(a, val))
                asset_row.add_widget(chk)
                asset_row.add_widget(MDLabel(
                    text=asset.name, font_style="Label", role="small",
                    size_hint=(1, 1),
                ))
                sz = getattr(asset, "size", 0) or 0
                if sz:
                    size_lbl = MDLabel(
                        text=_fmt_bytes(sz), font_style="Label", role="small",
                        size_hint=(None, 1), width=dp(72),
                        halign="right", theme_text_color="Custom", text_color=_COL_DIM,
                    )
                    asset_row.add_widget(size_lbl)
                panel.add_widget(asset_row)

        if changelog:
            _name = getattr(item, "name", "Release Notes")

            def _show_changelog(*_, _cl=changelog, _nm=_name):
                docs_svc = self._host.get_service("docs_viewer") if self._host.has_service("docs_viewer") else None
                if docs_svc and hasattr(docs_svc, "show_inline"):
                    docs_svc.show_inline(
                        content=_cl,
                        title=f"{_nm} — Release Notes",
                        sidebar_mode="verbose",
                        allow_mode_toggle=False,
                    )
                else:
                    # Fallback: plain MDDialog if docs_viewer unavailable
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

            panel.add_widget(MDButton(
                MDButtonText(text="Release Notes"),
                style="text",
                size_hint_y=None, height=dp(36),
                on_release=_show_changelog,
            ))

        return panel

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

        # Validate mods only (templates and other items skip dependency checks)
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
        """Pass (item, category) tuples to the on_queue callback."""
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


def _fmt_bytes(n: int) -> str:
    """Format byte count as human-readable string (e.g. '12.4 MB')."""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


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
