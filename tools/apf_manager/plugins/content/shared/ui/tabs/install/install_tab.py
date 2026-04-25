"""
Tab 4 — Installed

Shows ALL content deployed to the game directory:
  - Managed AP mods (installed via APF Manager) — registry source badge
  - Manually installed AP mods (not tracked by InstallStateManager) — folder-account badge
  - Non-AP mods (no mod_id) — Non-AP badge
  - Manually installed BP pak files (in Content/Paks/LogicMods/, not tracked)

NO enable/disable toggle — that lives in Load Order.
Uninstall calls deploy_svc.undeploy_content() (Phase F) for full component cleanup.
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

from .......gui.widgets.tip_icon_button import TipIconButton
from .....services.mod_service import _FRAMEWORK_MOD_RE
from .....shared.ui.constants import COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS
from .install_row import InstallRowMixin, _BG_ROW_AP

if TYPE_CHECKING:
    from .......core.config import GameProfile
    from .......core.ue4ss import UE4SSResult
    from .....services.mod_service import ModInfo


class InstalledTab(InstallRowMixin, MDBoxLayout):
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

        # Load install_map once for this refresh cycle
        game_id = self._get_game_id()
        install_map: dict = {}
        if game_id:
            from .....shared.data.install_state import InstallStateManager
            from .....shared.data.pipeline_state import InstallRecord
            install_map = {
                d.get("folder_name", ""): InstallRecord.from_dict(d)
                for d in InstallStateManager(game_id).get_all()
                if d.get("folder_name")
            }

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
                ir = install_map.get(mod.folder_name)
                self._list.add_widget(self._ap_mod_row(mod, deploy_svc, ir))
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
            self._list.add_widget(self._templates_section(install_map))

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
            icon_color=COL_STATUS_OK if ue4ss_ok else COL_STATUS_MISS,
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
            icon_color=COL_STATUS_OK if fw_bins_ok else COL_STATUS_MISS,
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
            theme_text_color="Custom", text_color=COL_DIM,
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

    def _templates_section(self, install_map: dict) -> MDBoxLayout:
        """Installed templates sub-section — scans framework mod's Templates/ directory."""
        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
        )
        templates: list[str] = []
        if self._fw_mod_dir:
            templates_root = self._fw_mod_dir / "Templates"
            if templates_root.is_dir():
                templates = sorted(d.name for d in templates_root.iterdir() if d.is_dir())

        # Also include template InstallRecords not yet on disk (or supplement with record data)
        tmpl_records = {
            r.game_id or r.name: r
            for r in install_map.values()
            if r.content_type == "template"
        }

        section.add_widget(self._section_header("Templates", len(templates)))
        if not templates:
            section.add_widget(self._empty_label(
                "No templates installed yet.\n"
                "Download templates from the Content tab."
            ))
        else:
            for game_name in templates:
                record = tmpl_records.get(game_name)
                section.add_widget(self._template_row(game_name, record))
        return section

    def _template_row(self, game_name: str, install_record=None) -> MDBoxLayout:
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
        if install_record:
            detail_parts = []
            if install_record.source_repo:
                detail_parts.append(install_record.source_repo)
            if install_record.deployed_at:
                detail_parts.append(install_record.deployed_at[:10])
            if detail_parts:
                row.add_widget(MDLabel(
                    text="  ·  ".join(detail_parts),
                    font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(200),
                    halign="right", valign="middle",
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
        return row

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

    def _on_uninstall(self, mod, is_orphaned: bool, install_record=None) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        is_framework = bool(mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id))

        if is_framework:
            self._on_uninstall_framework(mod, install_record)
            return

        components = list(install_record.components if install_record and install_record.components
                          else getattr(mod, "components", ["lua"]))
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
            self._do_uninstall(mod, install_record)

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

    def _on_uninstall_framework(self, mod, install_record=None) -> None:
        """Cascade analysis + confirmation dialog for framework mod uninstall."""
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        deploy_svc = self._host.get_service("deploy")
        impact = {}
        if deploy_svc and install_record and hasattr(deploy_svc, "get_uninstall_impact"):
            impact = deploy_svc.get_uninstall_impact(install_record)
        elif deploy_svc and hasattr(deploy_svc, "get_framework_uninstall_impact"):
            impact = deploy_svc.get_framework_uninstall_impact()

        affected_mods = impact.get("affected_mods", [])
        template_dirs = impact.get("template_dirs_removed", [])

        if affected_mods or template_dirs:
            affected_lines = "\n".join(
                f"  • {getattr(m, 'name', getattr(m, 'display_name', str(m)))} "
                f"({', '.join(getattr(m, 'capabilities_includes', []))})"
                for m in affected_mods
            )
            template_lines = "\n".join(f"  • {p}" for p in template_dirs)
            body = "Uninstalling the framework mod will also remove its entire Templates/ folder."
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
            self._do_uninstall(mod, install_record)

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

    def _do_uninstall(self, mod, install_record=None) -> None:
        from kivy.clock import Clock

        is_framework = bool(mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id))
        deploy_svc = self._host.get_service("deploy")
        mods_svc   = self._host.get_service("mods")

        try:
            if deploy_svc and install_record and hasattr(deploy_svc, "undeploy_content"):
                deploy_svc.undeploy_content(install_record, self._detection)
            elif deploy_svc and hasattr(deploy_svc, "undeploy_mod"):
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
