"""
Tab 4 — Installed

Shows ALL content deployed to the game directory:
  - Managed AP mods (installed via APF Manager) — registry source badge
  - Manually installed AP mods (not tracked by InstallStateManager) — folder-account badge
  - Non-AP mods (no mod_id) — Non-AP badge
  - Manually installed BP pak files (in Content/Paks/LogicMods/, not tracked)

NO enable/disable toggle — that lives in Load Order.
Uninstall calls deploy_svc.undeploy_mod() for full component cleanup.
Uninstalling the framework mod triggers a cascade impact analysis and confirmation dialog.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel

from ....gui.widgets.tip_icon_button import TipIconButton
from ..mod_service import _FRAMEWORK_MOD_RE

if TYPE_CHECKING:
    from ....core.config import GameProfile
    from ....core.ue4ss import UE4SSResult
    from ..mod_service import ModInfo


_BG_ROW_AP        = (0.13, 0.14, 0.15, 1)
_BG_ROW_ORPHAN    = (0.18, 0.13, 0.08, 1)
_BG_ROW_NONAP     = (0.11, 0.11, 0.11, 1)
_BG_ROW_BP_ORPHAN = (0.16, 0.12, 0.07, 1)
_COL_WARN         = (0.9, 0.6, 0.1, 1)
_COL_CPP          = (0.4, 0.7, 1.0, 1)
_COL_BP           = (1.0, 0.6, 0.2, 1)
_COL_DIM          = (0.5, 0.5, 0.5, 1)
_COL_REGISTRY     = (0.3, 0.8, 0.6, 1)
_COL_NONAP        = (0.6, 0.6, 0.6, 1)
_COL_STATUS_OK    = (0.3, 0.8, 0.4, 1)
_COL_STATUS_MISS  = (0.8, 0.3, 0.3, 1)


class InstalledTab(MDBoxLayout):
    """Tab 4 — Installed (all deployed content, full component status)."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        # Framework state — updated by mods_panel via set_framework_state()
        self._fw_mod_dir = None   # Path or None — framework lua mod directory
        self._fw_conflict: list = []  # non-empty if multiple framework mods detected
        # Expanded row detail panels
        self._expanded: set[str] = set()
        self._build_ui()

    def set_framework_state(self, ue4ss_ok: bool, fw_dir, fw_conflict) -> None:
        """Called by mods_panel._refresh_all() when detection/validation changes."""
        self._fw_mod_dir = fw_dir
        self._fw_conflict = list(fw_conflict) if fw_conflict else []

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1), padding=(dp(8), 0), spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Installed", font_style="Title", role="medium",
            size_hint_x=1, halign="left",
        ))
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan installed mods",
            on_release=lambda *_: self._do_refresh(),
        ))
        self.add_widget(toolbar)

        self.add_widget(MDLabel(
            text="All content deployed to your game directory. Use Load Order to enable/disable.",
            size_hint_y=None, adaptive_height=True,
            theme_text_color="Secondary", font_style="Body", role="small",
            padding=[dp(12), dp(4)],
        ))

        self._scroll = ScrollView(size_hint=(1, 1))
        self._list = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            spacing=dp(2), padding=[dp(8), dp(4)],
        )
        self._scroll.add_widget(self._list)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, profile: Optional["GameProfile"], detection) -> None:
        self._profile = profile
        self._detection = detection
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._list.clear_widgets()

        ue4ss_ok = bool(self._detection and getattr(self._detection, "valid", False))
        fw_mod_ok = bool(self._fw_mod_dir)

        # --- Framework conflict banner (shown at top if multiple framework mods) ---
        if self._fw_conflict:
            self._list.add_widget(self._conflict_banner(self._fw_conflict))

        # --- Other section (always shown regardless of UE4SS state) ---
        self._list.add_widget(self._other_status_section())

        mods_svc   = self._host.get_service("mods")
        deploy_svc = self._host.get_service("deploy")

        # --- Mods section ---
        if not ue4ss_ok:
            self._list.add_widget(self._locked_section(
                "Mods",
                "UE4SS required — browse the Other section above to install it.",
                color=(0.8, 0.2, 0.2, 1),
            ))
        else:
            all_mods: list["ModInfo"] = mods_svc.scan() if mods_svc else []
            mods_txt = deploy_svc.mods_txt if deploy_svc else None

            if mods_txt:
                order = mods_txt.get_order()
                order_idx = {name: i for i, name in enumerate(order)}
            else:
                order_idx = {}

            ap_mods    = [m for m in all_mods if m.is_ap_mod]
            non_ap_mods = [m for m in all_mods if not m.is_ap_mod
                           and m.folder_name.lower() not in ("keybinds",)]
            ap_mods.sort(key=lambda m: order_idx.get(m.folder_name, 9999))

            self._list.add_widget(self._section_header("Mods", len(ap_mods + non_ap_mods)))

            for mod in ap_mods:
                self._list.add_widget(self._ap_mod_row(mod, deploy_svc))
            for mod in non_ap_mods:
                self._list.add_widget(self._non_ap_row(mod, deploy_svc))

            self._add_orphaned_bp_rows()

            if not ap_mods and not non_ap_mods:
                self._list.add_widget(self._empty_label(
                    "No mods installed yet.\n"
                    "Download mods from the Content tab."
                ))

        # --- Templates section ---
        if not ue4ss_ok:
            self._list.add_widget(self._locked_section(
                "Templates",
                "UE4SS required before templates can be deployed.",
                color=(0.8, 0.2, 0.2, 1),
            ))
        elif not fw_mod_ok:
            self._list.add_widget(self._locked_section(
                "Templates",
                "Framework mod required — install it from the Mods section above.",
                color=(0.8, 0.55, 0.1, 1),
            ))
        else:
            self._list.add_widget(self._templates_section())

    # -----------------------------------------------------------------------
    # Section builders
    # -----------------------------------------------------------------------

    def _other_status_section(self) -> MDBoxLayout:
        """Bootstrap status section — always rendered regardless of UE4SS state."""
        ue4ss_ok = bool(self._detection and getattr(self._detection, "valid", False))
        platform_dir = getattr(self._detection, "platform_dir", None) if self._detection else None

        updates_svc = (
            self._host.get_service("updates")
            if self._host.has_service("updates") else None
        )
        ue4ss_update_info = updates_svc.get_update_info("ue4ss") if updates_svc else None
        fw_update_info    = updates_svc.get_update_info("framework") if updates_svc else None

        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.10, 0.13, 0.17, 1),
            padding=[dp(8), dp(6)], spacing=dp(4),
        )
        section.add_widget(MDLabel(
            text="OTHER — Bootstrap Components",
            font_style="Label", role="medium",
            size_hint_y=None, height=dp(22),
            theme_text_color="Custom", text_color=(0.55, 0.75, 0.95, 1),
        ))

        # UE4SS row
        ue4ss_version = ""
        if ue4ss_ok and self._detection:
            ue4ss_version = getattr(self._detection, "ue4ss_version", "") or ""
        if not ue4ss_version and ue4ss_update_info:
            ue4ss_version = ue4ss_update_info.current if ue4ss_update_info.current != "unknown" else ""
        ue4ss_detail = (
            f"v{ue4ss_version} installed" if (ue4ss_ok and ue4ss_version) else
            ("Detected (version unknown — manually installed)" if ue4ss_ok else
             "Not installed — get it from the Content tab")
        )
        section.add_widget(self._status_row(
            icon="check-circle-outline" if ue4ss_ok else "close-circle-outline",
            icon_color=_COL_STATUS_OK if ue4ss_ok else _COL_STATUS_MISS,
            label="UE4SS",
            detail=ue4ss_detail,
            update_tag=(ue4ss_update_info.latest_stable.tag_name
                        if (ue4ss_update_info and ue4ss_update_info.is_update_available
                            and ue4ss_update_info.latest_stable) else ""),
        ))

        # Framework binaries row
        fw_dll = None
        if platform_dir:
            from pathlib import Path
            fw_dll = Path(platform_dir) / "APFrameworkCore.dll"
        fw_bins_ok = bool(fw_dll and fw_dll.exists())
        section.add_widget(self._status_row(
            icon="check-circle-outline" if fw_bins_ok else "close-circle-outline",
            icon_color=_COL_STATUS_OK if fw_bins_ok else _COL_STATUS_MISS,
            label="Framework",
            detail="Installed" if fw_bins_ok else "Not installed — get it from the Content tab",
            update_tag=(fw_update_info.latest_stable.tag_name
                        if (fw_update_info and fw_update_info.is_update_available
                            and fw_update_info.latest_stable) else ""),
        ))

        return section

    def _status_row(self, icon: str, icon_color, label: str, detail: str,
                    update_tag: str = "") -> MDBoxLayout:
        outer = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
        )
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )
        row.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(20),
            theme_icon_color="Custom", icon_color=icon_color,
        ))
        row.add_widget(MDLabel(
            text=label, font_style="Body",
            size_hint=(None, 1), width=dp(180),
            halign="left", valign="middle",
        ))
        row.add_widget(MDLabel(
            text=detail, font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom", text_color=_COL_DIM,
        ))
        outer.add_widget(row)
        if update_tag:
            update_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(20),
                spacing=dp(4), padding=[dp(28), 0, 0, 0],
            )
            update_row.add_widget(MDIcon(
                icon="arrow-up-circle", size_hint=(None, 1), width=dp(16),
                theme_icon_color="Custom", icon_color=(0.25, 0.55, 1.0, 1),
            ))
            update_row.add_widget(MDLabel(
                text=f"Update available: {update_tag}",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=(0.25, 0.55, 1.0, 1),
            ))
            outer.add_widget(update_row)
        return outer

    def _section_header(self, title: str, count: int = 0) -> MDBoxLayout:
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(32),
            md_bg_color=(0.12, 0.16, 0.20, 1), padding=[dp(8), 0], spacing=dp(8),
        )
        label = title if not count else f"{title}  ({count})"
        header.add_widget(MDLabel(
            text=label, font_style="Title", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        return header

    def _locked_section(self, title: str, notice: str, color) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.11, 0.11, 0.11, 1),
        )
        section.add_widget(self._section_header(title))
        notice_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36),
            padding=[dp(12), dp(4)], spacing=dp(8),
        )
        notice_row.add_widget(MDIcon(
            icon="lock-outline", size_hint=(None, 1), width=dp(18),
            theme_icon_color="Custom", icon_color=color,
        ))
        notice_row.add_widget(MDLabel(
            text=notice, font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom", text_color=color,
        ))
        section.add_widget(notice_row)
        return section

    def _templates_section(self) -> MDBoxLayout:
        """Installed templates sub-section — scans framework mod's Templates/ directory."""
        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
        )
        # List subdirectories of <fw_dir>/Templates/ as installed game template packs
        templates: list[str] = []
        if self._fw_mod_dir:
            templates_root = self._fw_mod_dir / "Templates"
            if templates_root.is_dir():
                templates = sorted(d.name for d in templates_root.iterdir() if d.is_dir())

        section.add_widget(self._section_header("Templates", len(templates)))
        if not templates:
            section.add_widget(self._empty_label(
                "No templates installed yet.\n"
                "Download templates from the Content tab."
            ))
        else:
            for game_name in templates:
                section.add_widget(self._template_row(game_name))
        return section

    def _template_row(self, game_name: str) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(40),
            md_bg_color=_BG_ROW_AP, padding=[dp(8), dp(4)], spacing=dp(8),
        )
        row.add_widget(MDIcon(
            icon="file-tree", size_hint=(None, 1), width=dp(20),
            theme_icon_color="Custom", icon_color=(0.6, 0.85, 0.6, 1),
        ))
        row.add_widget(MDLabel(
            text=game_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        return row

    # -----------------------------------------------------------------------
    # AP mod row
    # -----------------------------------------------------------------------

    def _ap_mod_row(self, mod, deploy_svc) -> MDBoxLayout:
        is_orphaned = getattr(mod, "is_orphaned", False)
        components  = getattr(mod, "components", ["lua"])
        bg = _BG_ROW_ORPHAN if is_orphaned else _BG_ROW_AP
        key = f"mod:{mod.folder_name}"
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg, padding=[dp(8), dp(6)], spacing=dp(4),
        )

        # Top row: badge + name + component badges + version + chevron + uninstall
        top = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )

        # Source badge
        if is_orphaned:
            top.add_widget(self._badge_icon("folder-account", _COL_WARN, "Manually installed"))
        else:
            registry_name = self._get_registry_name(mod)
            top.add_widget(self._badge_text(registry_name or "Managed", _COL_REGISTRY))

        # Name
        top.add_widget(MDLabel(
            text=mod.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))

        # Component badges
        if "cpp" in components:
            top.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_CPP,
            ))
        if "blueprint" in components:
            top.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_BP,
            ))

        # Version
        if mod.version:
            top.add_widget(MDLabel(
                text=f"v{mod.version}", font_style="Label", role="small",
                size_hint=(None, 1), width=dp(60),
                halign="right", valign="middle",
                theme_text_color="Custom", text_color=_COL_DIM,
            ))

        # Expand chevron
        top.add_widget(MDIconButton(
            icon="chevron-up" if expanded else "chevron-down",
            size_hint=(None, None), size=(dp(28), dp(28)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=key: self._toggle_expand(k),
        ))
        top.add_widget(MDButton(
            MDButtonText(text="Uninstall"),
            style="text", size_hint=(None, None), size=(dp(88), dp(28)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, m=mod: self._on_uninstall(m, is_orphaned),
        ))
        container.add_widget(top)

        # mod_id sub-label
        if mod.mod_id:
            container.add_widget(MDLabel(
                text=mod.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
                padding=[dp(0), 0],
            ))
        if is_orphaned:
            container.add_widget(MDLabel(
                text="Not tracked by APF Manager",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom", text_color=(_COL_WARN[0], _COL_WARN[1], _COL_WARN[2], 0.75),
                padding=[dp(0), 0],
            ))

        # Component status sub-row (always shown for multi-component mods)
        status = self._get_component_status(mod, deploy_svc)
        if len(components) > 1 or is_orphaned:
            status_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(20),
                spacing=dp(12), padding=[dp(4), 0],
            )
            for comp in components:
                ok = status.get(comp, False)
                status_row.add_widget(self._component_status_chip(comp, ok))
            container.add_widget(status_row)

        # Expanded detail panel
        if expanded:
            container.add_widget(self._ap_mod_detail(mod, deploy_svc, status))

        return container

    def _ap_mod_detail(self, mod, deploy_svc, status: dict) -> MDBoxLayout:
        """Expanded detail panel for an installed AP mod."""
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.13, 1),
            padding=[dp(8), dp(4), dp(8), dp(6)], spacing=dp(4),
        )
        # mod_id
        if mod.mod_id:
            panel.add_widget(MDLabel(
                text=mod.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))

        # Version + source from InstallStateManager
        game_id = self._get_game_id()
        record = None
        if game_id:
            from ..install_state import InstallStateManager
            record = InstallStateManager(game_id).find(mod.folder_name)
        if record:
            ver = record.get("version", "")
            src = record.get("source_repo", "")
            parts = []
            if ver:
                parts.append(f"v{ver}")
            if src:
                parts.append(src)
            if parts:
                panel.add_widget(MDLabel(
                    text="  ·  ".join(parts),
                    font_style="Label", role="small", size_hint_y=None, height=dp(16),
                    theme_text_color="Custom", text_color=_COL_DIM,
                ))

        # Component status (full row for each component)
        components = getattr(mod, "components", ["lua"])
        if components:
            comp_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(20),
                spacing=dp(12),
            )
            for comp in components:
                ok = status.get(comp, False)
                comp_row.add_widget(self._component_status_chip(comp, ok))
            panel.add_widget(comp_row)

        # Install path
        folder_path = getattr(mod, "folder_path", None)
        if folder_path:
            path_str = str(folder_path)
            # Truncate long paths
            if len(path_str) > 60:
                path_str = "…" + path_str[-58:]
            panel.add_widget(MDLabel(
                text=path_str, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        return panel

    def _toggle_expand(self, key: str) -> None:
        if key in self._expanded:
            self._expanded.discard(key)
        else:
            self._expanded.add(key)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    # -----------------------------------------------------------------------
    # Non-AP row
    # -----------------------------------------------------------------------

    def _non_ap_row(self, mod, deploy_svc) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            md_bg_color=_BG_ROW_NONAP, padding=[dp(8), dp(4)], spacing=dp(8),
        )
        row.add_widget(self._badge_text("Non-AP", _COL_NONAP))
        row.add_widget(MDLabel(
            text=mod.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom", text_color=(0.6, 0.6, 0.6, 1),
        ))
        row.add_widget(MDButton(
            MDButtonText(text="Remove"),
            style="text", size_hint=(None, None), size=(dp(80), dp(28)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, m=mod: self._on_remove_nonap(m),
        ))
        return row

    # -----------------------------------------------------------------------
    # Orphaned BP pak rows
    # -----------------------------------------------------------------------

    def _add_orphaned_bp_rows(self) -> None:
        logicmods_dir = getattr(self._detection, "logicmods_dir", None)
        if not logicmods_dir or not logicmods_dir.is_dir():
            return

        from ..install_state import InstallStateManager
        game_id = self._get_game_id()
        state = InstallStateManager(game_id) if game_id else None

        for f in sorted(logicmods_dir.iterdir()):
            if f.suffix.lower() not in (".pak", ".ucas", ".utoc"):
                continue
            if state and state.is_pak_managed(f.name):
                continue
            row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(40),
                md_bg_color=_BG_ROW_BP_ORPHAN, padding=[dp(8), dp(4)], spacing=dp(8),
            )
            row.add_widget(MDIcon(
                icon="folder-account", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=_COL_WARN,
            ))
            row.add_widget(MDLabel(
                text=f"Manually installed BP file: {f.name}",
                font_style="Body", size_hint=(1, 1),
                halign="left", valign="middle",
            ))
            row.add_widget(MDButton(
                MDButtonText(text="Remove"),
                style="text", size_hint=(None, None), size=(dp(80), dp(28)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, fp=f: self._remove_pak(fp),
            ))
            self._list.add_widget(row)

    # -----------------------------------------------------------------------
    # Component status
    # -----------------------------------------------------------------------

    def _get_component_status(self, mod, deploy_svc) -> dict:
        if deploy_svc and hasattr(deploy_svc, "get_component_status"):
            return deploy_svc.get_component_status(mod, self._detection)
        # Fallback: manual check
        components = getattr(mod, "components", ["lua"])
        result: dict = {}
        mods_dir = getattr(self._detection, "mods_dir", None)
        logicmods_dir = getattr(self._detection, "logicmods_dir", None)
        fn = mod.folder_name
        if "lua" in components:
            result["lua"] = bool(
                mods_dir and (mods_dir / fn / "scripts" / "main.lua").exists()
            )
        if "cpp" in components:
            result["cpp"] = bool(
                mods_dir and (mods_dir / fn / "dlls" / "main.dll").exists()
            )
        if "blueprint" in components:
            pak_files = getattr(mod, "bp_pak_files", [])
            result["blueprint"] = bool(pak_files) and all(
                logicmods_dir and (logicmods_dir / p).exists()
                for p in pak_files
            )
        return result

    def _component_status_chip(self, component: str, ok: bool) -> MDBoxLayout:
        chip = MDBoxLayout(
            orientation="horizontal", size_hint=(None, 1),
            width=dp(80), spacing=dp(4),
        )
        chip.add_widget(MDIcon(
            icon="check-circle-outline" if ok else "close-circle-outline",
            size_hint=(None, 1), width=dp(16),
            theme_icon_color="Custom",
            icon_color=_COL_STATUS_OK if ok else _COL_STATUS_MISS,
        ))
        labels = {"lua": "Lua", "cpp": "C++", "blueprint": "BP"}
        chip.add_widget(MDLabel(
            text=labels.get(component, component),
            font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom",
            text_color=_COL_STATUS_OK if ok else _COL_STATUS_MISS,
        ))
        return chip

    # -----------------------------------------------------------------------
    # Badges
    # -----------------------------------------------------------------------

    @staticmethod
    def _badge_icon(icon: str, color, tooltip: str = "") -> MDBoxLayout:
        box = MDBoxLayout(size_hint=(None, 1), width=dp(20))
        box.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(16),
            theme_icon_color="Custom", icon_color=color,
        ))
        return box

    @staticmethod
    def _badge_text(text: str, color) -> MDLabel:
        return MDLabel(
            text=f"[{text}]", font_style="Label", role="small",
            size_hint=(None, 1), width=dp(90),
            halign="left", valign="middle",
            theme_text_color="Custom", text_color=color,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_registry_name(self, mod) -> str:
        registry_svc = self._host.get_service("registry")
        if not registry_svc:
            return ""
        game_id = self._get_game_id()
        for entry in registry_svc.get_mods(game_id):
            if getattr(entry, "mod_id", "") == mod.mod_id:
                reg = getattr(entry, "registry", None)
                if reg:
                    return getattr(reg, "repo", "")
        return ""

    def _get_game_id(self) -> str:
        if self._profile:
            name = getattr(self._profile, "display_name", None) or getattr(self._profile, "name", "")
            return name.lower().replace(" ", "_") if name else ""
        return ""

    @staticmethod
    def _empty_label(text: str) -> MDLabel:
        return MDLabel(
            text=text, halign="center",
            size_hint=(1, None), height=dp(80),
            theme_text_color="Secondary",
        )

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_uninstall(self, mod, is_orphaned: bool) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        is_framework = bool(mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id))

        if is_framework:
            self._on_uninstall_framework(mod)
            return

        components = getattr(mod, "components", ["lua"])
        comp_names = {
            "lua": "Lua scripts (scripts/)",
            "cpp": "C++ module (dlls/main.dll)",
            "blueprint": f"Blueprint files ({', '.join(getattr(mod, 'bp_pak_files', []) or ['LogicMods/*.pak'])})",
        }
        comp_text = "\n".join(f"  • {comp_names[c]}" for c in components if c in comp_names)
        manual_note = (
            "\n\nThis mod was installed manually — APF Manager will remove it, "
            "but no backup was tracked."
            if is_orphaned else ""
        )

        def _confirm(*_):
            dlg.dismiss()
            self._do_uninstall(mod)

        dlg = MDDialog(
            MDDialogHeadlineText(text=f"Uninstall {mod.display_name}?"),
            MDDialogSupportingText(
                text=f"The following will be removed:\n{comp_text}{manual_note}"
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
                MDButton(MDButtonText(text="Uninstall"), style="filled",
                         on_release=_confirm),
            ),
        )
        dlg.open()

    def _on_uninstall_framework(self, mod) -> None:
        """Cascade analysis + confirmation dialog for framework mod uninstall."""
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        deploy_svc = self._host.get_service("deploy")
        impact = {}
        if deploy_svc and hasattr(deploy_svc, "get_framework_uninstall_impact"):
            impact = deploy_svc.get_framework_uninstall_impact()

        affected_mods = impact.get("affected_mods", [])
        template_dirs = impact.get("template_dirs_removed", [])

        if affected_mods or template_dirs:
            affected_lines = "\n".join(
                f"  • {m.display_name} ({', '.join(getattr(m, 'capabilities_includes', []))})"
                for m in affected_mods
            )
            template_lines = "\n".join(f"  • {p}" for p in template_dirs)
            body = (
                "Uninstalling the framework mod will also remove its entire Templates/ folder."
            )
            if template_dirs:
                body += f"\n\nTemplate directories that will be removed:\n{template_lines}"
            if affected_mods:
                body += (
                    f"\n\nThe following mods use capabilities.include and will "
                    f"not function correctly without the templates:\n{affected_lines}"
                    f"\n\nThese mods will need to be reinstalled after reinstalling the framework mod."
                )
        else:
            body = (
                "Uninstalling the framework mod will remove the AP runtime and all templates.\n"
                "No currently installed mods appear to depend on its templates."
            )

        def _confirm(*_):
            dlg.dismiss()
            self._do_uninstall(mod)

        dlg = MDDialog(
            MDDialogHeadlineText(text="Warning — Cascading Removal"),
            MDDialogSupportingText(text=body),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
                MDButton(MDButtonText(text="Uninstall Anyway"), style="filled",
                         on_release=_confirm),
            ),
        )
        dlg.open()

    def _do_uninstall(self, mod) -> None:
        from kivy.clock import Clock

        is_framework = bool(mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id))
        deploy_svc = self._host.get_service("deploy")
        mods_svc   = self._host.get_service("mods")

        try:
            if deploy_svc and hasattr(deploy_svc, "undeploy_mod"):
                deploy_svc.undeploy_mod(mod, self._detection)
            else:
                import shutil
                if mod.folder_path and mod.folder_path.exists():
                    shutil.rmtree(mod.folder_path, ignore_errors=True)
                if deploy_svc:
                    deploy_svc.remove_entry(mod.folder_name)

            if mods_svc:
                mods_svc.rescan()

            self._host.log(f"[installed] Uninstalled {mod.display_name} ({mod.folder_name})")
        except Exception as exc:
            self._host.log(f"[installed] Uninstall failed for {mod.folder_name}: {exc}")

        if is_framework:
            # Full panel refresh — framework mod removal affects all tabs
            Clock.schedule_once(lambda dt: self._trigger_full_refresh(), 0)
        else:
            Clock.schedule_once(lambda dt: self._do_refresh(), 0)

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

    def _trigger_full_refresh(self) -> None:
        """After framework mod removal, re-validate everything and refresh all tabs."""
        self._do_refresh()
        # Walk up to ModsPanel and call on_activate to cascade a full refresh
        parent = self.parent
        while parent is not None:
            if hasattr(parent, "on_activate") and hasattr(parent, "_profile"):
                try:
                    parent.on_activate(parent._profile)
                except Exception:
                    pass
                break
            parent = getattr(parent, "parent", None)

    def _on_remove_nonap(self, mod) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        def _confirm(*_):
            dlg.dismiss()
            self._do_remove_nonap(mod)

        dlg = MDDialog(
            MDDialogHeadlineText(text=f"Remove {mod.display_name}?"),
            MDDialogSupportingText(
                text=(
                    f"This will remove {mod.folder_name} from your Mods/ directory "
                    "and from mods.txt. This is not an AP mod."
                )
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
                MDButton(MDButtonText(text="Remove"), style="filled",
                         on_release=_confirm),
            ),
        )
        dlg.open()

    def _do_remove_nonap(self, mod) -> None:
        import shutil
        from kivy.clock import Clock

        deploy_svc = self._host.get_service("deploy")
        mods_svc   = self._host.get_service("mods")

        try:
            if mod.folder_path and mod.folder_path.exists():
                shutil.rmtree(mod.folder_path, ignore_errors=True)
            if deploy_svc:
                deploy_svc.remove_entry(mod.folder_name)
            if mods_svc:
                mods_svc.rescan()
        except Exception as exc:
            self._host.log(f"[installed] Remove failed for {mod.folder_name}: {exc}")

        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _remove_pak(self, pak_path) -> None:
        from kivy.clock import Clock
        try:
            pak_path.unlink(missing_ok=True)
        except Exception as exc:
            self._host.log(f"[installed] Failed to remove {pak_path.name}: {exc}")
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    # -----------------------------------------------------------------------
    # Badge count
    # -----------------------------------------------------------------------

    def get_installed_count(self) -> tuple[int, int]:
        """Returns (total, orphaned_count) for badge coloring."""
        mods_svc = self._host.get_service("mods")
        if not mods_svc or not (self._detection and getattr(self._detection, "valid", False)):
            return (0, 0)
        try:
            all_mods = mods_svc.scan()
            orphaned = sum(1 for m in all_mods if getattr(m, "is_orphaned", False))
            return (len(all_mods), orphaned)
        except Exception:
            return (0, 0)
