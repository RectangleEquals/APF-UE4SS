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
from kivymd.uix.button import MDButton, MDButtonText
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
        self._build_ui()

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

        if not (self._detection and getattr(self._detection, "valid", False)):
            self._list.add_widget(self._empty_label(
                "UE4SS is required to manage installed mods.\n"
                "Install UE4SS in the Registries tab first."
            ))
            return

        mods_svc   = self._host.get_service("mods")
        deploy_svc = self._host.get_service("deploy")

        all_mods: list["ModInfo"] = mods_svc.scan() if mods_svc else []
        mods_txt   = deploy_svc.mods_txt if deploy_svc else None

        # Sort by mods.txt order for Lua/C++ mods, alphabetical for BP-only
        if mods_txt:
            order = mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
        else:
            order_idx = {}

        # Separate: AP mods, non-AP mods
        ap_mods    = [m for m in all_mods if m.is_ap_mod]
        non_ap_mods = [m for m in all_mods if not m.is_ap_mod
                       and m.folder_name.lower() not in ("keybinds",)]

        ap_mods.sort(key=lambda m: order_idx.get(m.folder_name, 9999))

        # AP mods
        for mod in ap_mods:
            self._list.add_widget(self._ap_mod_row(mod, deploy_svc))

        # Non-AP mods
        for mod in non_ap_mods:
            self._list.add_widget(self._non_ap_row(mod, deploy_svc))

        # Orphaned BP pak files
        self._add_orphaned_bp_rows()

        if not ap_mods and not non_ap_mods:
            self._list.add_widget(self._empty_label(
                "No mods installed yet.\n"
                "Download mods from the Content tab."
            ))

    # -----------------------------------------------------------------------
    # AP mod row
    # -----------------------------------------------------------------------

    def _ap_mod_row(self, mod, deploy_svc) -> MDBoxLayout:
        is_orphaned = getattr(mod, "is_orphaned", False)
        components  = getattr(mod, "components", ["lua"])
        bg = _BG_ROW_ORPHAN if is_orphaned else _BG_ROW_AP

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg, padding=[dp(8), dp(6)], spacing=dp(4),
        )

        # Top row: badge + name + mod_id + badges + version + uninstall
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

        return container

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
