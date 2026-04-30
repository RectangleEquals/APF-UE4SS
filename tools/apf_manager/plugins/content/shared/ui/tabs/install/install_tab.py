"""
Tab 4 — Installed

Shows ALL content deployed to the game directory:
  - Managed AP mods (installed via APF Manager) — registry source badge
  - Orphaned AP mods (not tracked by InstallStateManager) — folder-account badge
  - Non-AP mods (no mod_id) — Non-AP badge
  - Manually installed BP pak files (in Content/Paks/LogicMods/, not tracked)

NO enable/disable toggle — that lives in Load Order.
Uninstall calls deploy_svc.undeploy_content() for full component cleanup.
Uninstalling the framework mod triggers a cascade impact analysis and confirmation dialog.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel

from .......gui.widgets.tip_icon_button import TipIconButton
from .....services.mod_service import _FRAMEWORK_MOD_RE
from .....shared.ui.constants import COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS
from .....shared.ui.installed_row_widget import InstalledRowWidget
from .....shared.ui.badges import badge_text
from .....shared.ui.banners.conflict_banner import ConflictBanner
from .....shared.ui.banners.framework_status_banner import FrameworkStatusBanner
from .....shared.ui.dialogs.uninstall_dialog import UninstallDialog

if TYPE_CHECKING:
    from .......core.config import GameProfile
    from .......core.ue4ss import UE4SSResult
    from .....services.mod_service import ModInfo
    from .....shared.data.pipeline_state import InstallRecord


_BG_ROW_AP     = (0.13, 0.14, 0.15, 1)
_BG_ROW_NONAP  = (0.11, 0.11, 0.11, 1)
_COL_NONAP     = (0.6, 0.6, 0.6, 1)


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
        # Expanded row detail panels (keyed by "mod:{folder_name}")
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

        ue4ss_ok  = bool(self._detection and getattr(self._detection, "valid", False))
        fw_mod_ok = bool(self._fw_mod_dir)

        game_id = self._get_game_id()
        install_map: dict[str, "InstallRecord"] = {}
        if game_id:
            from .....shared.data.install_state import InstallStateManager
            from .....shared.data.pipeline_state import InstallRecord
            install_map = {
                d.get("folder_name", ""): InstallRecord.from_dict(d)
                for d in InstallStateManager(game_id).get_all()
                if d.get("folder_name")
            }

        # --- Framework conflict banner ---
        if self._fw_conflict:
            self._list.add_widget(self._conflict_banner(self._fw_conflict))

        # --- Bootstrap (Other) section — always shown ---
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

            ap_mods     = [m for m in all_mods if m.is_ap_mod]
            non_ap_mods = [m for m in all_mods if not m.is_ap_mod
                           and m.folder_name.lower() not in ("keybinds",)]
            ap_mods.sort(key=lambda m: order_idx.get(m.folder_name, 9999))

            self._list.add_widget(self._section_header("Mods", len(ap_mods + non_ap_mods)))

            row_idx = 0
            for mod in ap_mods:
                ir = install_map.get(mod.folder_name)
                is_orphaned = ir is None   # on disk but no tracked install record

                if ir:
                    record = ir
                else:
                    # Build a synthetic InstallRecord for orphaned AP mods so that
                    # InstalledRowWidget has typed data to render.
                    from .....shared.data.pipeline_state import InstallRecord
                    record = InstallRecord(
                        content_type="ap_mod",
                        name=getattr(mod, "display_name", mod.folder_name),
                        mod_id=getattr(mod, "mod_id", ""),
                        folder_name=mod.folder_name,
                        components=list(getattr(mod, "components", ["lua"])),
                        game_id=game_id,
                    )

                expanded = f"mod:{record.folder_name}" in self._expanded

                def _make_expand_cb(fn=record.folder_name):
                    return lambda *_: self._toggle_expand(f"mod:{fn}")

                def _make_uninstall_cb(m=mod, rec=ir, orphaned=is_orphaned):
                    return lambda: self._on_uninstall(rec or self._synthetic_record(m, game_id),
                                                      orphaned, m)

                widget = InstalledRowWidget(
                    install_record=record,
                    detection=self._detection,
                    deploy_svc=deploy_svc,
                    row_index=row_idx,
                    expanded=expanded,
                    on_expand=_make_expand_cb(),
                    on_uninstall=_make_uninstall_cb(),
                    is_orphaned=is_orphaned,
                )
                self._list.add_widget(widget)
                row_idx += 1

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
    # Row builders
    # -----------------------------------------------------------------------

    def _non_ap_row(self, mod, deploy_svc) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            md_bg_color=_BG_ROW_NONAP, padding=[dp(8), dp(4)], spacing=dp(8),
        )
        row.add_widget(badge_text("Non-AP", _COL_NONAP))
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

    def _add_orphaned_bp_rows(self) -> None:
        logicmods_dir = getattr(self._detection, "logicmods_dir", None)
        if not logicmods_dir or not logicmods_dir.is_dir():
            return
        from .....shared.data.install_state import InstallStateManager
        game_id = self._get_game_id()
        state = InstallStateManager(game_id) if game_id else None
        for f in sorted(logicmods_dir.iterdir()):
            if f.suffix.lower() not in (".pak", ".ucas", ".utoc"):
                continue
            if state and state.is_pak_managed(f.name):
                continue
            row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(40),
                md_bg_color=(0.16, 0.12, 0.07, 1), padding=[dp(8), dp(4)], spacing=dp(8),
            )
            row.add_widget(MDIcon(
                icon="folder-account", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=COL_WARN,
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

    def _toggle_expand(self, key: str) -> None:
        if key in self._expanded:
            self._expanded.discard(key)
        else:
            self._expanded.add(key)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    # -----------------------------------------------------------------------
    # Section builders
    # -----------------------------------------------------------------------

    def _other_status_section(self) -> MDBoxLayout:
        """Bootstrap status section — always rendered regardless of UE4SS state."""
        ue4ss_ok    = bool(self._detection and getattr(self._detection, "valid", False))
        platform_dir = getattr(self._detection, "platform_dir", None) if self._detection else None

        updates_svc = (
            self._host.get_service("updates")
            if self._host.has_service("updates") else None
        )
        ue4ss_update_info = updates_svc.get_update_info("ue4ss")      if updates_svc else None
        fw_update_info    = updates_svc.get_update_info("framework")  if updates_svc else None

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

        from pathlib import Path
        fw_dll = Path(platform_dir) / "APFrameworkCore.dll" if platform_dir else None
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
        outer = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)
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
        section.add_widget(FrameworkStatusBanner(state="locked", detail=notice, color=color))
        return section

    def _templates_section(self, install_map: dict) -> MDBoxLayout:
        section = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)
        templates: list[str] = []
        if self._fw_mod_dir:
            templates_root = self._fw_mod_dir / "Templates"
            if templates_root.is_dir():
                templates = sorted(d.name for d in templates_root.iterdir() if d.is_dir())

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
                    text="  \u00b7  ".join(detail_parts),
                    font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(200),
                    halign="right", valign="middle",
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
        return row

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_game_id(self) -> str:
        if self._profile:
            name = getattr(self._profile, "display_name", None) or getattr(self._profile, "name", "")
            return name.lower().replace(" ", "_") if name else ""
        return ""

    @staticmethod
    def _synthetic_record(mod, game_id: str) -> "InstallRecord":
        from .....shared.data.pipeline_state import InstallRecord
        return InstallRecord(
            content_type="ap_mod",
            name=getattr(mod, "display_name", mod.folder_name),
            mod_id=getattr(mod, "mod_id", ""),
            folder_name=mod.folder_name,
            components=list(getattr(mod, "components", ["lua"])),
            game_id=game_id,
        )

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

    def _on_uninstall(self, install_record: "InstallRecord", is_orphaned: bool,
                      mod_info=None) -> None:
        is_framework = bool(
            install_record.mod_id and _FRAMEWORK_MOD_RE.match(install_record.mod_id)
        )
        is_ap_mod = bool(install_record.mod_id)

        # Cascade detection for ALL AP mods (not just framework)
        if is_ap_mod:
            deploy_svc = self._host.get_service("deploy")
            impact: dict = {}
            if deploy_svc and hasattr(deploy_svc, "get_uninstall_impact"):
                impact = deploy_svc.get_uninstall_impact(install_record)
            elif is_framework and deploy_svc and hasattr(deploy_svc, "get_framework_uninstall_impact"):
                impact = deploy_svc.get_framework_uninstall_impact()
            affected_mods = impact.get("affected_mods", [])
            template_dirs = impact.get("template_dirs_removed", [])

            if is_framework or affected_mods or template_dirs:
                UninstallDialog.for_cascade(
                    install_record=install_record,
                    affected_mods=affected_mods,
                    template_dirs=template_dirs,
                    on_confirm=lambda: self._do_uninstall(install_record, mod_info),
                ).open()
                return

        UninstallDialog.for_mod(
            install_record=install_record,
            is_orphaned=is_orphaned,
            on_confirm=lambda: self._do_uninstall(install_record, mod_info),
        ).open()

    def _do_uninstall(self, install_record: "InstallRecord", mod_info=None) -> None:
        from kivy.clock import Clock

        is_framework = bool(
            install_record.mod_id and _FRAMEWORK_MOD_RE.match(install_record.mod_id)
        )
        deploy_svc = self._host.get_service("deploy")
        mods_svc   = self._host.get_service("mods")

        try:
            if deploy_svc and hasattr(deploy_svc, "undeploy_content"):
                deploy_svc.undeploy_content(install_record, self._detection)
            elif mod_info and deploy_svc and hasattr(deploy_svc, "undeploy_mod"):
                deploy_svc.undeploy_mod(mod_info, self._detection)
            else:
                import shutil
                if mod_info:
                    folder_path = getattr(mod_info, "folder_path", None)
                    if folder_path and folder_path.exists():
                        shutil.rmtree(str(folder_path), ignore_errors=True)
                if deploy_svc:
                    deploy_svc.remove_entry(install_record.folder_name)

            if mods_svc:
                mods_svc.rescan()

            self._host.log(
                f"[installed] Uninstalled {install_record.name} ({install_record.folder_name})"
            )
        except Exception as exc:
            self._host.log(
                f"[installed] Uninstall failed for {install_record.folder_name}: {exc}"
            )

        if hasattr(self._host, "notify_state_change"):
            Clock.schedule_once(lambda dt: self._host.notify_state_change("install"), 0)

        if is_framework:
            Clock.schedule_once(lambda dt: self._trigger_full_refresh(), 0)
        else:
            Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _conflict_banner(self, conflict_paths: list) -> ConflictBanner:
        return ConflictBanner(conflict_paths=conflict_paths)

    def _trigger_full_refresh(self) -> None:
        self._do_refresh()
        parent = self.parent
        while parent is not None:
            if hasattr(parent, "on_activate") and hasattr(parent, "_profile"):
                try:
                    parent.on_activate(parent._profile)
                except Exception as exc:
                    self._host.log(f"[installed] WARN: full refresh trigger failed: {exc}")
                break
            parent = getattr(parent, "parent", None)

    def _on_remove_nonap(self, mod) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        dlg_ref = [None]

        def _confirm(*_):
            dlg_ref[0].dismiss()
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
                         on_release=lambda *_: dlg_ref[0].dismiss()),
                MDButton(MDButtonText(text="Remove"), style="filled",
                         on_release=_confirm),
            ),
        )
        dlg_ref[0] = dlg
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
        mods_svc = self._host.get_service("mods")
        if not mods_svc or not (self._detection and getattr(self._detection, "valid", False)):
            return (0, 0)
        try:
            all_mods = mods_svc.scan()
            orphaned = sum(1 for m in all_mods if getattr(m, "is_orphaned", False))
            return (len(all_mods), orphaned)
        except Exception as exc:
            self._host.log(f"[installed] WARN: get_installed_count failed: {exc}")
            return (0, 0)
