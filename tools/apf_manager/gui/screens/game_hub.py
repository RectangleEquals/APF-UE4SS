"""
GameHubScreen — the per-game screen.

Layout:
  ┌─ Top bar (game name, hub_action buttons, Settings) ──────────────────────┐
  │                                                                           │
  ├─ NavigationRail (left) ─┬─ PluginPanel host (center) ─────────────────── │
  │  icon per hub_panel     │  active plugin fills this area                 │
  │                         │                                                 │
  └─────────────────────────┴─────────────────────────────────────────────── │
  │  LogPanel (bottom, collapsible)                                           │
  └───────────────────────────────────────────────────────────────────────────┘

The NavigationRail is populated from all registered hub_panel contributions.
"""

from __future__ import annotations

import shutil
import threading
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from ..widgets.log_panel import LogPanel
from ..widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost, PluginContribution
    from ...core.config import APFConfig, GameProfile
    from ...core.ue4ss import UE4SSResult


class _NavRailButton(MDIconButton):
    """Icon button for the navigation rail with tooltip label."""

    def __init__(self, label: str, icon: str, on_select, **kwargs):
        super().__init__(icon=icon, **kwargs)
        self._nav_label = label
        self._on_select = on_select

    def on_release(self):
        self._on_select(self._nav_label)


class GameHubScreen(MDScreen):
    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(name="game_hub", **kwargs)
        self._host = host
        self._config = config
        self._active_panel: Optional[PluginPanel] = None
        self._panel_map: dict[str, PluginPanel] = {}  # label -> panel instance
        self._nav_buttons: dict[str, _NavRailButton] = {}
        self._log_panel = LogPanel()
        self._current_profile: Optional["GameProfile"] = None
        self._current_detection: Optional["UE4SSResult"] = None

        # Wire host log to our panel
        host.set_log_fn(self._log_panel.append)

        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        root = MDBoxLayout(orientation="vertical")

        # Top bar
        self._top_bar = self._build_top_bar()
        root.add_widget(self._top_bar)

        # Middle: nav rail + panel host
        middle = MDBoxLayout(orientation="horizontal", size_hint_y=1)
        self._nav_rail = self._build_nav_rail()
        middle.add_widget(self._nav_rail)

        self._panel_host = MDBoxLayout(orientation="vertical", size_hint_x=1)
        middle.add_widget(self._panel_host)
        root.add_widget(middle)

        # Log panel (bottom)
        root.add_widget(self._log_panel)

        self.add_widget(root)

    def _build_top_bar(self) -> MDBoxLayout:
        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=("8dp", 0),
            spacing="4dp",
        )
        # Back button
        back_btn = MDIconButton(
            icon="arrow-left",
            on_release=self._go_home,
        )
        bar.add_widget(back_btn)

        # Game name label
        self._game_name_lbl = MDLabel(
            text="",
            font_style="Headline",
            role="small",
            halign="left",
            size_hint_x=1,
        )
        bar.add_widget(self._game_name_lbl)

        # hub_action buttons placeholder (populated in populate_panels)
        self._action_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width="0dp",
            spacing="4dp",
        )
        bar.add_widget(self._action_bar)

        # Remove game button
        remove_btn = MDIconButton(
            icon="trash-can-outline",
            on_release=lambda *_: self._on_remove_game(),
        )
        bar.add_widget(remove_btn)

        # Settings button
        settings_btn = MDIconButton(
            icon="cog",
            on_release=self._go_settings,
        )
        bar.add_widget(settings_btn)
        return bar

    def _build_nav_rail(self) -> MDBoxLayout:
        rail = MDBoxLayout(
            orientation="vertical",
            size_hint_x=None,
            width="56dp",
            md_bg_color=(0.1, 0.1, 0.1, 1),
            padding=(0, "8dp"),
            spacing="4dp",
        )
        self._nav_rail_inner = rail
        return rail

    # -----------------------------------------------------------------------
    # Populate with plugin contributions
    # -----------------------------------------------------------------------

    def populate_panels(self) -> None:
        """Called after plugins are loaded to register all hub_panel contributions."""
        panels = self._host.get_contributions("hub_panel")
        actions = self._host.get_contributions("hub_action")

        # Build nav rail buttons
        for contrib in panels:
            btn = _NavRailButton(
                label=contrib.label,
                icon=contrib.icon or "puzzle",
                on_select=self._select_panel,
            )
            self._nav_buttons[contrib.label] = btn
            self._nav_rail_inner.add_widget(btn)

            # Instantiate the panel
            if contrib.panel_class:
                panel = contrib.panel_class(host=self._host)
                self._panel_map[contrib.label] = panel

        # Build action buttons
        action_width = 0
        for contrib in actions:
            btn = MDIconButton(
                icon=contrib.icon or "lightning-bolt",
                on_release=lambda _, c=contrib: c.handler() if c.handler else None,
            )
            self._action_bar.add_widget(btn)
            action_width += dp(48)
        self._action_bar.width = str(action_width) + "dp"

        # Select first panel
        if panels:
            self._select_panel(panels[0].label)

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _select_panel(self, label: str) -> None:
        if self._active_panel is not None:
            self._active_panel.on_deactivate()
            self._panel_host.remove_widget(self._active_panel)

        panel = self._panel_map.get(label)
        if panel is None:
            return

        self._active_panel = panel
        self._panel_host.add_widget(panel)

        profile = self._host.get_game_context()
        if profile:
            panel.on_activate(profile)

    def activate_for_game(self, profile: "GameProfile") -> None:
        """Called when the user navigates to this game."""
        self._current_profile = profile
        self._current_detection = self._host.get_detection()
        self._game_name_lbl.text = profile.display_name
        if self._active_panel and profile:
            self._active_panel.on_activate(profile)

    # -----------------------------------------------------------------------
    # Remove game
    # -----------------------------------------------------------------------

    def _on_remove_game(self) -> None:
        if not self._current_profile:
            return
        self._show_remove_checklist(self._current_profile, self._current_detection)

    def _show_remove_checklist(self, profile: "GameProfile", detection: Optional["UE4SSResult"]) -> None:
        from kivymd.uix.button import MDButton, MDButtonText
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText,
            MDDialogContentContainer, MDDialogButtonContainer,
        )
        from kivymd.uix.selectioncontrol import MDSwitch
        from kivy.uix.widget import Widget

        # Determine which options are available
        deploy_svc = self._host.get_service("deploy")
        has_framework = (
            deploy_svc is not None
            and bool(deploy_svc.get_framework_manifest_files(profile.game_id))
        )
        has_mods_svc = self._host.has_service("mods")
        has_sessions_svc = self._host.has_service("sessions")
        has_ue4ss = (
            detection is not None
            and detection.ue4ss_dir
            and Path(str(detection.ue4ss_dir)).is_dir()
        )

        switches: dict[str, MDSwitch] = {}
        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
            padding=(0, dp(8)),
        )
        content.bind(minimum_height=content.setter("height"))

        def _add_row(key: str, text: str, active: bool = False, locked: bool = False) -> None:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(44),
                spacing=dp(8),
            )
            sw = MDSwitch(active=active, disabled=locked, pos_hint={"center_y": 0.5})
            lbl = MDLabel(text=text, size_hint_x=1)
            row.add_widget(sw)
            row.add_widget(lbl)
            content.add_widget(row)
            switches[key] = sw

        _add_row("library", "Remove from library", active=True, locked=True)
        if has_mods_svc:
            _add_row("mods", "Remove deployed AP mods")
        if has_framework:
            _add_row("framework", "Remove AP Framework binaries")
        if has_sessions_svc:
            _add_row("sessions", "Remove session history")
        if has_ue4ss:
            _add_row("ue4ss", "Uninstall UE4SS")

        dialog = [None]

        def _dismiss(*_):
            if dialog[0]:
                dialog[0].dismiss()

        def _on_remove(*_):
            _dismiss()
            self._execute_remove(profile, detection, switches)

        dialog[0] = MDDialog(
            MDDialogHeadlineText(text=f'Remove "{profile.display_name}"?'),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Remove Selected"), style="filled",
                         on_release=_on_remove),
            ),
        )
        dialog[0].open()

    def _execute_remove(
        self,
        profile: "GameProfile",
        detection: Optional["UE4SSResult"],
        switches: dict,
    ) -> None:
        errors: list[str] = []

        def _run() -> None:
            # 1. Remove deployed AP mods
            if switches.get("mods") and switches["mods"].active:
                mods_svc = self._host.get_service("mods")
                deploy_svc = self._host.get_service("deploy")
                if mods_svc and deploy_svc:
                    try:
                        for mod in mods_svc.scan():
                            if mod.is_ap_mod:
                                deploy_svc.uninstall_mod(mod, profile.game_id)
                    except Exception as exc:
                        errors.append(str(exc))

            # 2. Remove AP Framework binaries
            if switches.get("framework") and switches["framework"].active:
                deploy_svc = self._host.get_service("deploy")
                if deploy_svc:
                    try:
                        for f in deploy_svc.get_framework_manifest_files(profile.game_id):
                            try:
                                Path(f).unlink(missing_ok=True)
                            except Exception as exc:
                                errors.append(f"Could not remove {Path(f).name}: {exc}")
                        manifest = (
                            Path.home() / ".apf_manager" / "deployments"
                            / f"{profile.game_id}_framework.json"
                        )
                        manifest.unlink(missing_ok=True)
                    except Exception as exc:
                        errors.append(str(exc))

            # 3. Remove session history
            if switches.get("sessions") and switches["sessions"].active:
                sessions_svc = self._host.get_service("sessions")
                if sessions_svc:
                    try:
                        sessions_svc.clear_sessions(profile.game_id)
                    except Exception as exc:
                        errors.append(str(exc))

            # 4. Uninstall UE4SS
            if switches.get("ue4ss") and switches["ue4ss"].active:
                if detection and detection.ue4ss_dir:
                    try:
                        shutil.rmtree(str(detection.ue4ss_dir))
                    except Exception as exc:
                        errors.append(f"Could not remove UE4SS: {exc}")

            # 5. Remove from library (always — this is the committed action)
            self._config.remove_game(profile.game_id)

            Clock.schedule_once(lambda dt: self._after_remove(errors), 0)

        threading.Thread(target=_run, daemon=True).start()

    def _after_remove(self, errors: list[str]) -> None:
        app = self._get_app()
        if app:
            app.navigate_to_library()
            # Refresh the home/library screen if it supports it
            if hasattr(app, "_home_screen") and app._home_screen:
                children = app._home_screen.children
                if children and hasattr(children[0], "refresh"):
                    children[0].refresh()
        if errors:
            self._show_snackbar(f"Removed ({len(errors)} error(s) — see console).")
        else:
            self._show_snackbar("Removed.")

    def _show_snackbar(self, text: str) -> None:
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _go_home(self, *_) -> None:
        app = self._get_app()
        if app:
            app.navigate_to_library()

    def _go_settings(self, *_) -> None:
        app = self._get_app()
        if app:
            app.root.current = "settings"

    def _get_app(self):
        from kivymd.app import MDApp
        return MDApp.get_running_app()

    # -----------------------------------------------------------------------
    # Log passthrough
    # -----------------------------------------------------------------------

    @property
    def log_panel(self) -> LogPanel:
        return self._log_panel
