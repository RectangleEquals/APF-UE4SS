"""
SettingsScreen — global settings and plugin management.

Sections:
  - Mode toggle: Player / Dev
  - Plugin Manager: list all plugins, enable/disable, install .apfplugin
  - Steam library path override
  - Restart Required banner (shown after toggling plugins)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.selectioncontrol import MDSwitch

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost, PluginInfo
    from ...core.config import APFConfig
    from ...plugins.updates.updates_service import UpdatesService


class SettingsScreen(MDScreen):
    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(name="settings", **kwargs)
        self._host = host
        self._config = config
        self._restart_needed = False
        self._original_mode = config.mode
        self._original_disabled = set(config.disabled_plugins)
        self._updates_section = None   # built lazily in on_pre_enter
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        root = MDBoxLayout(orientation="vertical")

        # Top bar
        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=("8dp", 0),
        )
        back_btn = MDIconButton(icon="arrow-left", on_release=self._go_back)
        bar.add_widget(back_btn)
        bar.add_widget(MDLabel(text="Settings", font_style="Headline", role="small", halign="left"))
        root.add_widget(bar)

        # Restart required banner (hidden by default)
        self._restart_banner = self._build_restart_banner()
        root.add_widget(self._restart_banner)

        # Scrollable content
        scroll = ScrollView(
            bar_width=dp(6),
            bar_color=[0.5, 0.5, 0.5, 0.8],
            do_scroll_x=False,
            size_hint=(1, 1),
        )
        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            padding="16dp",
            spacing="12dp",
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(self._build_mode_section())
        content.add_widget(MDDivider())
        content.add_widget(self._build_plugin_section())
        content.add_widget(MDDivider())
        content.add_widget(self._build_steam_section())
        content.add_widget(MDDivider())
        content.add_widget(self._build_cache_section())

        self._scroll_content = content
        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)
        Clock.schedule_once(lambda dt: self._scroll_content.do_layout(), 0)

    def _build_restart_banner(self) -> MDBoxLayout:
        banner = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=0,
            opacity=0,
            md_bg_color=(0.7, 0.1, 0.1, 1),
            padding=("16dp", "4dp"),
            spacing="8dp",
        )
        lbl = MDLabel(
            text="Restart required to apply changes",
            font_style="Label",
            role="small",
            halign="left",
            size_hint_x=1,
        )
        restart_btn = MDButton(
            MDButtonText(text="Restart"),
            style="filled",
            size_hint_x=None,
            width=dp(96),
            on_release=self._restart_app,
        )
        banner.add_widget(lbl)
        banner.add_widget(restart_btn)
        self._restart_banner_widget = banner
        return banner

    def _build_mode_section(self) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="80dp",
            spacing="4dp",
        )
        section.add_widget(MDLabel(text="Mode", font_style="Title",
                                   role="large",
                                   size_hint_y=None, height="28dp"))
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="40dp", spacing="8dp")
        player_lbl = MDLabel(text="Player", size_hint_x=None, width="60dp")
        switch = MDSwitch()
        switch.active = (self._config.mode == "dev")
        switch.bind(active=self._on_mode_toggle)
        dev_lbl = MDLabel(text="Dev", size_hint_x=None, width="40dp")
        row.add_widget(player_lbl)
        row.add_widget(switch)
        row.add_widget(dev_lbl)
        section.add_widget(row)
        return section

    def _build_plugin_section(self) -> MDBoxLayout:
        section = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True, spacing="4dp")
        section.add_widget(MDLabel(
            text="Plugins",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))

        self._plugin_list_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing="2dp",
        )
        self._plugin_list_box.bind(minimum_height=self._plugin_list_box.setter("height"))
        self._refresh_plugin_list()
        section.add_widget(self._plugin_list_box)

        # Install plugin button
        install_btn = MDButton(
            MDButtonText(text="Install .apfplugin…"),
            style="text",
            size_hint_y=None,
            height="40dp",
            on_release=self._install_plugin,
        )
        section.add_widget(install_btn)
        return section

    def _build_steam_section(self) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="80dp",
            spacing="4dp",
        )
        section.add_widget(MDLabel(
            text="Steam Library",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))
        override = self._config.steam_library_override or ""
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="40dp", spacing="8dp")
        from kivymd.uix.textfield import MDTextField
        self._steam_path_field = MDTextField(
            text=override,
            hint_text="libraryfolders.vdf path (leave blank for auto-detect)",
            size_hint_x=1,
        )
        save_btn = MDButton(
            MDButtonText(text="Save"),
            style="text",
            size_hint_x=None,
            width=dp(60),
            on_release=self._save_steam_override,
        )
        row.add_widget(self._steam_path_field)
        row.add_widget(save_btn)
        section.add_widget(row)
        return section

    def _build_cache_section(self) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing="8dp",
            padding=("0dp", "4dp"),
        )
        section.add_widget(MDLabel(
            text="Cache",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))

        clear_btn = MDButton(
            MDButtonText(text="Clear Download Cache"),
            style="outlined",
            size_hint_y=None,
            height="40dp",
            on_release=self._confirm_clear_cache,
        )
        section.add_widget(clear_btn)

        reset_btn = MDButton(
            MDButtonText(text="Reset App Data"),
            style="outlined",
            size_hint_y=None,
            height="40dp",
            on_release=self._confirm_reset_app_data,
        )
        section.add_widget(reset_btn)
        return section

    # -----------------------------------------------------------------------
    # Plugin list
    # -----------------------------------------------------------------------

    def _refresh_plugin_list(self) -> None:
        self._plugin_list_box.clear_widgets()
        for info in self._host.get_all_plugins():
            self._plugin_list_box.add_widget(self._make_plugin_row(info))

    def _make_plugin_row(self, info: "PluginInfo") -> MDBoxLayout:
        is_user_disabled = info.plugin_id in self._config.disabled_plugins
        is_actual_failure = info.status == "failed" and not is_user_disabled

        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="44dp",
            padding=("8dp", 0),
            spacing="8dp",
            md_bg_color=(0.3, 0.05, 0.05, 1) if is_actual_failure else (0.12, 0.12, 0.12, 1),
        )

        # Status icon
        icon = "alert-circle" if is_actual_failure else ("toggle-switch-off" if is_user_disabled else "puzzle-check")
        icon_color = (1, 0.3, 0.3, 1) if is_actual_failure else (0.7, 0.7, 0.7, 1)
        row.add_widget(MDIconButton(
            icon=icon,
            theme_icon_color="Custom",
            icon_color=icon_color,
            size_hint=(None, None),
            width=dp(40),
            height=dp(40),
            pos_hint={"center_y": 0.5},
            disabled=True,
        ))

        # Name + version + error
        info_box = MDBoxLayout(orientation="vertical", size_hint_x=1)
        if is_actual_failure and info.error:
            info_box.add_widget(MDLabel(
                text=f"{info.name}  v{info.version}  [{info.mode}]",
                font_style="Body",
                size_hint_y=None,
                height=dp(22),
                valign="middle",
            ))
            info_box.add_widget(MDLabel(
                text=info.error,
                font_style="Label",
                role="small",
                theme_text_color="Custom",
                text_color=(1, 0.5, 0.5, 1),
                size_hint_y=None,
                height=dp(18),
            ))
        else:
            info_box.add_widget(MDLabel(
                text=f"{info.name}  v{info.version}  [{info.mode}]",
                font_style="Body",
                size_hint_y=1,
                valign="middle",
            ))
        row.add_widget(info_box)

        # Enable/disable toggle
        switch = MDSwitch()
        switch.active = not is_user_disabled
        switch.pos_hint = {"center_y": 0.5}
        switch.bind(active=lambda _, val, pid=info.plugin_id: self._on_plugin_toggle(pid, val))
        row.add_widget(switch)

        return row

    # -----------------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------------

    def _on_mode_toggle(self, widget, value: bool) -> None:
        self._config.mode = "dev" if value else "player"
        self._config.save()
        self._update_restart_banner()

    def _on_plugin_toggle(self, plugin_id: str, enabled: bool) -> None:
        if not enabled:
            # Block disabling the sole home_screen provider
            home_contribs = self._host.get_contributions("home_screen")
            if home_contribs and all(c.plugin_id == plugin_id for c in home_contribs):
                self._show_snackbar("Library plugin is required. Enable another library plugin first.")
                self._refresh_plugin_list()  # revert switch visually
                return
        self._config.set_plugin_disabled(plugin_id, not enabled)
        self._update_restart_banner()
        self._refresh_plugin_list()

    def _show_snackbar(self, text: str) -> None:
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()

    def _update_restart_banner(self) -> None:
        dirty = (
            self._config.mode != self._original_mode
            or set(self._config.disabled_plugins) != self._original_disabled
        )
        if dirty and not self._restart_needed:
            self._restart_needed = True
            self._restart_banner_widget.height = dp(44)
            self._restart_banner_widget.opacity = 1
        elif not dirty and self._restart_needed:
            self._restart_needed = False
            self._restart_banner_widget.height = 0
            self._restart_banner_widget.opacity = 0

    def _restart_app(self, *_) -> None:
        """Close and relaunch the application."""
        import subprocess
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable])
        else:
            tools_dir = Path(__file__).parent.parent.parent
            subprocess.Popen([sys.executable, "-m", "apf_manager"], cwd=str(tools_dir))
            from kivymd.app import MDApp
            MDApp.get_running_app().stop()

    def _save_steam_override(self, *_) -> None:
        val = self._steam_path_field.text.strip() or None
        self._config.steam_library_override = val
        self._config.save()

    def _install_plugin(self, *_) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        dlg_ref = [None]

        def _close(*_):
            if dlg_ref[0]:
                dlg_ref[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Not Yet Implemented"),
            MDDialogSupportingText(
                text=(
                    "Installing plugins from a file (.apfplugin) is planned for a future release.\n\n"
                    "For now, plugins can be installed manually by placing them in the "
                    "custom_plugins/ folder inside the APF Manager installation directory."
                ),
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        dlg_ref[0] = dlg
        dlg.open()

    def _confirm_clear_cache(self, *_) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        dlg_ref = [None]

        def _close(*_):
            if dlg_ref[0]:
                dlg_ref[0].dismiss()

        def _do_clear(*_):
            _close()
            self._run_clear_cache()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Clear Download Cache?"),
            MDDialogSupportingText(
                text=(
                    "This will delete all cached downloads (staged mods, UE4SS releases, "
                    "framework binaries). Items currently installed on disk are NOT affected. "
                    "You will need to re-download content before installing."
                ),
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_close),
                MDButton(MDButtonText(text="Clear Cache"), style="filled", on_release=_do_clear),
            ),
        )
        dlg_ref[0] = dlg
        dlg.open()

    def _run_clear_cache(self) -> None:
        import shutil
        cache_dir = Path.home() / ".apf_manager" / "cache"
        try:
            if cache_dir.is_dir():
                for child in cache_dir.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            self._show_snackbar("Download cache cleared.")
        except Exception as exc:
            self._show_snackbar(f"Error clearing cache: {exc}")

    def _confirm_reset_app_data(self, *_) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        dlg_ref = [None]

        def _close(*_):
            if dlg_ref[0]:
                dlg_ref[0].dismiss()

        def _show_second_confirm(*_):
            _close()
            self._confirm_reset_app_data_final()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Reset All App Data?"),
            MDDialogSupportingText(
                text=(
                    "WARNING: This will delete ALL app data including:\n"
                    "  • All download caches\n"
                    "  • All install state records (orphan detection will break)\n"
                    "  • All cached registry/API responses\n"
                    "  • App configuration and game paths\n\n"
                    "Installed mods on disk are NOT affected. This cannot be undone."
                ),
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_close),
                MDButton(MDButtonText(text="Continue…"), style="outlined", on_release=_show_second_confirm),
            ),
        )
        dlg_ref[0] = dlg
        dlg.open()

    def _confirm_reset_app_data_final(self) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        dlg_ref = [None]

        def _close(*_):
            if dlg_ref[0]:
                dlg_ref[0].dismiss()

        def _do_reset(*_):
            _close()
            self._run_reset_app_data()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Delete Everything?"),
            MDDialogSupportingText(
                text="This will permanently delete all APF Manager app data. This cannot be undone.",
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_close),
                MDButton(
                    MDButtonText(text="Delete Everything", theme_text_color="Custom",
                                 text_color=(1, 0.3, 0.3, 1)),
                    style="outlined",
                    on_release=_do_reset,
                ),
            ),
        )
        dlg_ref[0] = dlg
        dlg.open()

    def _run_reset_app_data(self) -> None:
        import shutil
        app_data_dir = Path.home() / ".apf_manager"
        try:
            if app_data_dir.is_dir():
                shutil.rmtree(app_data_dir, ignore_errors=True)
            app_data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._show_snackbar(f"Error resetting app data: {exc}")
            return
        # Restart the app so all services re-initialize cleanly
        self._restart_app()

    def _go_back(self, *_) -> None:
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        if app and hasattr(app, "navigate_back"):
            app.navigate_back()

    def on_pre_enter(self, *args) -> None:
        super().on_pre_enter(*args)
        self._refresh_updates_section()

    def refresh(self) -> None:
        """Called when screen is shown — refresh plugin list."""
        self._refresh_plugin_list()

    # -----------------------------------------------------------------------
    # Updates section
    # -----------------------------------------------------------------------

    def _refresh_updates_section(self) -> None:
        """Build/rebuild the Updates section at the top of the scroll content."""
        if self._updates_section is not None:
            self._scroll_content.remove_widget(self._updates_section)
            self._updates_section = None
        if not self._host.has_service("updates"):
            return
        updates_svc: "UpdatesService" = self._host.get_service("updates")
        section = self._build_updates_section(updates_svc)
        if section is not None:
            self._updates_section = section
            # index=len(children) inserts at the visual top of the BoxLayout
            self._scroll_content.add_widget(section, index=len(self._scroll_content.children))

    def _build_updates_section(self, updates_svc: "UpdatesService") -> Optional[MDBoxLayout]:
        """Return an Updates section widget if any updates are available, else None."""
        mgr = updates_svc.get_update_info("manager")
        apw = updates_svc.get_update_info("apworld")

        rows: list[tuple[str, str, str, str, str]] = []
        if mgr and mgr.is_update_available and mgr.latest_stable:
            rows.append(("APF Manager", mgr.current,
                         mgr.latest_stable.tag_name, "manager", mgr.asset_url))
        if apw and apw.is_update_available and apw.latest_stable:
            rows.append(("APWorld", apw.current,
                         apw.latest_stable.tag_name, "apworld", apw.asset_url))

        pre_rows: list[tuple[str, str, str, str, str]] = []
        if mgr and mgr.is_pre_available and mgr.latest_pre:
            if not (mgr.is_update_available and mgr.latest_stable
                    and mgr.latest_pre.tag_name == mgr.latest_stable.tag_name):
                pre_rows.append(("APF Manager (pre-release)", mgr.current,
                                 mgr.latest_pre.tag_name, "manager_pre", mgr.asset_url))
        if apw and apw.is_pre_available and apw.latest_pre:
            if not (apw.is_update_available and apw.latest_stable
                    and apw.latest_pre.tag_name == apw.latest_stable.tag_name):
                pre_rows.append(("APWorld (pre-release)", apw.current,
                                 apw.latest_pre.tag_name, "apworld_pre", apw.asset_url))

        if not rows and not pre_rows:
            return None

        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing="4dp",
            padding=("0dp", "4dp"),
        )
        section.add_widget(MDLabel(
            text="Updates",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))

        for name, current, latest_tag, component, asset_url in rows:
            section.add_widget(self._make_update_row(
                name, current, latest_tag, component, asset_url, prerelease=False
            ))

        if pre_rows:
            section.add_widget(MDDivider())
            for name, current, latest_tag, component, asset_url in pre_rows:
                section.add_widget(self._make_update_row(
                    name, current, latest_tag, component, asset_url, prerelease=True
                ))

        section.add_widget(MDDivider())
        return section

    def _make_update_row(
        self,
        name: str,
        current: str,
        latest_tag: str,
        component: str,
        asset_url: str,
        prerelease: bool,
    ) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="44dp",
            spacing="8dp",
        )

        ver_text = f"{name}   {current} → {latest_tag}"
        row.add_widget(MDLabel(
            text=ver_text,
            font_style="Body",
            size_hint_x=1,
            valign="middle",
        ))

        action_btn = MDButton(
            MDButtonText(text="Download"),
            style="filled",
            size_hint_x=None,
            width=dp(108),
        )
        action_btn.bind(on_release=lambda _, c=component, u=asset_url, b=action_btn:
                        self._on_download(c, u, b))
        row.add_widget(action_btn)
        return row

    def _on_download(self, component: str, asset_url: str, btn: MDButton) -> None:
        """Start downloading the update; swap button to Install/View on completion."""
        if not self._host.has_service("updates"):
            return
        updates_svc: "UpdatesService" = self._host.get_service("updates")

        # Find the MDButtonText child — first MDButtonText in children list
        from kivymd.uix.button import MDButtonText as _MBT
        btn_text = next((c for c in btn.children if isinstance(c, _MBT)), None)
        if btn_text:
            btn_text.text = "…"
        btn.disabled = True

        # Derive destination file path from the asset URL filename
        import tempfile
        url_filename = asset_url.split("/")[-1].split("?")[0] if asset_url else "update"
        if not url_filename:
            url_filename = f"{component}_update"
        dest_dir = Path(tempfile.mkdtemp(prefix="apf_update_"))
        dest_file = dest_dir / url_filename

        # State container shared between this closure and _done
        state: dict = {"dest": str(dest_file)}

        def _progress(downloaded: int, total: int) -> None:
            pass

        def _done(ok: bool, _msg: str) -> None:
            from kivy.clock import Clock as _Clock
            _Clock.schedule_once(lambda dt: self._after_download(
                component, state["dest"], btn, btn_text, ok
            ), 0)

        updates_svc.download_update(
            component.replace("_pre", ""),
            dest_file,
            progress_cb=_progress,
            on_done=_done,
        )

    def _after_download(
        self,
        component: str,
        dest_path: str,
        btn: MDButton,
        btn_text,
        ok: bool,
    ) -> None:
        """Swap the button to Install or View depending on component."""
        btn.disabled = False
        if not ok:
            if btn_text:
                btn_text.text = "Error"
            return

        base_component = component.replace("_pre", "")
        # Use a mutable state dict so the closure can be replaced safely
        action: dict = {}

        if base_component == "manager":
            if btn_text:
                btn_text.text = "Install"
            action["path"] = dest_path

            def _on_release_install(*_):
                import subprocess
                p = action.get("path", "")
                try:
                    subprocess.Popen([p], shell=False)
                except Exception:
                    subprocess.Popen(p, shell=True)
                sys.exit(0)

            btn.bind(on_release=_on_release_install)

        else:  # apworld
            if btn_text:
                btn_text.text = "View"
            action["folder"] = str(Path(dest_path).parent)

            def _on_release_view(*_):
                os.startfile(action.get("folder", "."))

            btn.bind(on_release=_on_release_view)
