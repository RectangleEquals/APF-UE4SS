"""install_row.py — InstallRowMixin: AP/non-AP/orphaned BP row builders for InstalledTab."""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel

from .....shared.ui.constants import COL_CPP, COL_BP, COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS
from .....shared.ui.badges import badge_icon, badge_text, component_status_chip


_BG_ROW_AP        = (0.13, 0.14, 0.15, 1)
_BG_ROW_ORPHAN    = (0.18, 0.13, 0.08, 1)
_BG_ROW_NONAP     = (0.11, 0.11, 0.11, 1)
_BG_ROW_BP_ORPHAN = (0.16, 0.12, 0.07, 1)
_COL_REGISTRY     = (0.3, 0.8, 0.6, 1)
_COL_NONAP        = (0.6, 0.6, 0.6, 1)


class InstallRowMixin:
    """Row builder methods for InstalledTab. Accesses self.* via MRO."""

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

        top = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )

        if is_orphaned:
            top.add_widget(badge_icon("folder-account", COL_WARN, "Manually installed"))
        else:
            registry_name = self._get_registry_name(mod)
            top.add_widget(badge_text(registry_name or "Managed", _COL_REGISTRY))

        top.add_widget(MDLabel(
            text=mod.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))

        if "cpp" in components:
            top.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=COL_CPP,
            ))
        if "blueprint" in components:
            top.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=COL_BP,
            ))

        if mod.version:
            top.add_widget(MDLabel(
                text=f"v{mod.version}", font_style="Label", role="small",
                size_hint=(None, 1), width=dp(60),
                halign="right", valign="middle",
                theme_text_color="Custom", text_color=COL_DIM,
            ))

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

        if mod.mod_id:
            container.add_widget(MDLabel(
                text=mod.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
                padding=[dp(0), 0],
            ))
        if is_orphaned:
            container.add_widget(MDLabel(
                text="Not tracked by APF Manager",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom",
                text_color=(COL_WARN[0], COL_WARN[1], COL_WARN[2], 0.75),
                padding=[dp(0), 0],
            ))

        status = self._get_component_status(mod, deploy_svc)
        if len(components) > 1 or is_orphaned:
            status_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(20),
                spacing=dp(12), padding=[dp(4), 0],
            )
            for comp in components:
                ok = status.get(comp, False)
                status_row.add_widget(component_status_chip(comp, ok))
            container.add_widget(status_row)

        if expanded:
            container.add_widget(self._ap_mod_detail(mod, deploy_svc, status))

        return container

    def _ap_mod_detail(self, mod, deploy_svc, status: dict) -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.13, 1),
            padding=[dp(8), dp(4), dp(8), dp(6)], spacing=dp(4),
        )
        if mod.mod_id:
            panel.add_widget(MDLabel(
                text=mod.mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))

        game_id = self._get_game_id()
        record = None
        if game_id:
            from .....shared.data.install_state import InstallStateManager
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
                    theme_text_color="Custom", text_color=COL_DIM,
                ))

        components = getattr(mod, "components", ["lua"])
        if components:
            comp_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(20),
                spacing=dp(12),
            )
            for comp in components:
                ok = status.get(comp, False)
                comp_row.add_widget(component_status_chip(comp, ok))
            panel.add_widget(comp_row)

        folder_path = getattr(mod, "folder_path", None)
        if folder_path:
            path_str = str(folder_path)
            if len(path_str) > 60:
                path_str = "…" + path_str[-58:]
            panel.add_widget(MDLabel(
                text=path_str, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
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

    # -----------------------------------------------------------------------
    # Orphaned BP pak rows
    # -----------------------------------------------------------------------

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
                md_bg_color=_BG_ROW_BP_ORPHAN, padding=[dp(8), dp(4)], spacing=dp(8),
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

    # -----------------------------------------------------------------------
    # Component status
    # -----------------------------------------------------------------------

    def _get_component_status(self, mod, deploy_svc) -> dict:
        if deploy_svc and hasattr(deploy_svc, "get_component_status"):
            return deploy_svc.get_component_status(mod, self._detection)
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
