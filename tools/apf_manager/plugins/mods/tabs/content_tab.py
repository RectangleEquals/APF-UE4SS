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
from kivymd.uix.button import MDButton, MDButtonText
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
        # Framework state (set by mods_panel via set_framework_state)
        self._ue4ss_ok: bool = False
        self._fw_dir = None
        self._fw_conflict: list = []
        # Collapsed sections (section title → True if collapsed)
        self._collapsed: set[str] = set()
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
            on_release=lambda *_: self._do_refresh(),
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
        self._game_id = game_id
        self._do_refresh()

    def set_framework_state(self, ue4ss_ok: bool, fw_dir, fw_conflict: list) -> None:
        """Called by mods_panel after detection — drives section notices."""
        self._ue4ss_ok = ue4ss_ok
        self._fw_dir = fw_dir
        self._fw_conflict = list(fw_conflict) if fw_conflict else []
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._list.clear_widgets()
        self._all_mods = []
        self._all_templates = []

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
                for i, mod in enumerate(mods):
                    self._list.add_widget(self._mod_row(mod, i))
        elif not templates:
            self._list.add_widget(self._empty_label(
                "No content available.\nAdd a registry in the Registries tab."
            ))

        self._sync_queue_btn()

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

        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            md_bg_color=bg, padding=[dp(8), dp(4)], spacing=dp(8),
        )
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = key in self._checked
        cb.bind(active=lambda inst, val, k=key: self._on_check(k, val))
        row.add_widget(cb)

        has_conflict = getattr(tmpl, "has_conflict", False)
        if has_conflict:
            row.add_widget(MDIcon(
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
        row.add_widget(info)
        return row

    def _mod_row(self, mod, index: int) -> MDBoxLayout:
        folder = getattr(mod, "folder", getattr(mod, "mod_id", str(index)))
        key = f"mod:{folder}"
        components = getattr(mod, "components", ["lua"])
        bg = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD

        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            md_bg_color=bg, padding=[dp(8), dp(4)], spacing=dp(8),
        )

        # Checkbox
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = key in self._checked
        cb.bind(active=lambda inst, val, k=key, m=mod: self._on_mod_check(k, val, m))
        row.add_widget(cb)

        # Info column
        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))

        # Name row + component badges
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
                icon="code-braces", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_CPP,
            ))
        if "blueprint" in components:
            name_row.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_BP,
            ))
        info.add_widget(name_row)

        # Sub-label: mod_id or description
        mod_id = getattr(mod, "mod_id", "")
        desc = getattr(mod, "description", "")
        sub = mod_id or desc
        if sub:
            info.add_widget(MDLabel(
                text=sub, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        row.add_widget(info)

        return row

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

        if not checked_mods and not checked_templates:
            return

        # Validate mods only (templates are just files — no dependency checks)
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
                                          allow_proceed=False)
                return
            if warnings:
                self._show_validation_dlg(errors, warnings, checked_mods, checked_templates,
                                          allow_proceed=True)
                return

        self._do_queue(checked_mods, checked_templates)

    def _show_validation_dlg(self, errors, warnings, mods, templates,
                              allow_proceed: bool) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        lines = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title = "Cannot Queue" if not allow_proceed else "Queue with Warnings?"
        text  = "\n".join(lines) or "Validation issue."

        btns: list = [
            Widget(),
            MDButton(MDButtonText(text="Cancel"), style="text",
                     on_release=lambda *_: dlg.dismiss()),
        ]
        if allow_proceed:
            btns.append(MDButton(
                MDButtonText(text="Queue Anyway"), style="filled",
                on_release=lambda *_, m=mods, t=templates: (
                    dlg.dismiss(), self._do_queue(m, t)
                ),
            ))

        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text=text),
            MDDialogButtonContainer(*btns),
        )
        dlg.open()

    def _do_queue(self, mods: list, templates: list = None) -> None:
        """Pass (item, category) tuples to the on_queue callback."""
        if templates is None:
            templates = []
        items = [(m, "mod") for m in mods] + [(t, "template") for t in templates]
        if self._on_queue:
            self._on_queue(items)
        for mod in mods:
            folder = getattr(mod, "folder", getattr(mod, "mod_id", ""))
            self._checked.discard(f"mod:{folder}")
        for i, tmpl in enumerate(templates):
            path = getattr(tmpl, "path", str(i))
            self._checked.discard(f"tmpl:{path}")
        self._sync_queue_btn()
        self._do_refresh()

    # -----------------------------------------------------------------------
    # Badge count
    # -----------------------------------------------------------------------

    def get_available_count(self) -> int:
        return len(self._all_mods) + len(self._all_templates)
