from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.uix.scrollview import ScrollView
from kivymd.uix.divider import MDDivider
from kivymd.uix.tab import MDTabsPrimary, MDTabsItem, MDTabsItemIcon, MDTabsItemText, MDTabsCarousel

from ....core.views.widgets.plugin_panel import PluginPanel
from ..controllers import GitHubAuth, CIManager
from ..controllers.tabs import (
    AccountController, DevSetupController,
    SourceControlController, VersionsController, CITabController,
)
from .tabs import AccountTab, DevSetupTab, SourceControlTab, VersionsTab, CITab

if TYPE_CHECKING:
    from ....core.models.config import GameProfile

_PLUGIN_JSON = Path(__file__).parent.parent / "plugin.json"


def _load_meta() -> dict:
    try:
        return json.loads(_PLUGIN_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[devtools] Failed to load plugin.json: %s", exc)
        return {}


class DevToolsPanel(PluginPanel):

    def __init__(self, host, **kwargs):
        super().__init__(host=host, **kwargs)
        meta = _load_meta()
        self._repo_owner: str = meta.get("repo_owner", "")
        self._repo_name:  str = meta.get("repo_name", "")

        # Shared service objects — controllers share these instances
        _auth = GitHubAuth()
        _ci   = CIManager(self._repo_owner, self._repo_name)

        # Tab controllers
        self._account_ctrl  = AccountController(_auth, host, self._repo_owner, self._repo_name)
        self._ds_ctrl       = DevSetupController(host, self._repo_owner, self._repo_name)
        self._sc_ctrl       = SourceControlController(
            _ci, _auth, host, self._repo_owner, self._repo_name)
        self._versions_ctrl = VersionsController(_ci, _auth, host)
        self._ci_ctrl       = CITabController(_ci, _auth, host)

        # Load persisted repo root before building UI
        self._ds_ctrl.load_saved_repo_root()

        # Tab views
        self._account_tab  = AccountTab(
            self._account_ctrl, on_auth_changed=self._on_auth_changed)
        self._ds_tab       = DevSetupTab(
            self._ds_ctrl, on_setup_changed=self._on_setup_changed)
        self._sc_tab       = SourceControlTab(self._sc_ctrl)
        self._versions_tab = VersionsTab(self._versions_ctrl)
        self._ci_tab       = CITab(self._ci_ctrl)

        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._refresh()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        tabs = MDTabsPrimary()
        for label, icon in [
            ("Account",        "account"),
            ("Dev Setup",      "book-open-variant"),
            ("Source Control", "source-branch"),
            ("Versions",       "tag-multiple"),
            ("CI",             "cog-play"),
        ]:
            tabs.add_widget(MDTabsItem(
                MDTabsItemIcon(icon=icon),
                MDTabsItemText(text=label),
            ))

        carousel = MDTabsCarousel(size_hint=(1, 1))
        tabs._tabs_carousel = carousel
        carousel._tabs = tabs
        carousel.bind(
            _offset=tabs.android_animation,
            index=tabs.on_carousel_index,
        )

        for tab_widget in [
            self._account_tab, self._ds_tab, self._sc_tab,
            self._versions_tab, self._ci_tab,
        ]:
            sv = ScrollView(size_hint=(1, 1))
            sv.add_widget(tab_widget)
            carousel.add_widget(sv)

        self.add_widget(tabs)
        self.add_widget(MDDivider())
        self.add_widget(carousel)

        self._rebuild_all_tabs()

    # -----------------------------------------------------------------------
    # Refresh flow
    # -----------------------------------------------------------------------

    def _refresh(self) -> None:
        if self._account_ctrl.is_logged_in:
            self._account_ctrl.refresh_async(
                on_complete=lambda ok: Clock.schedule_once(
                    lambda dt: self._on_auth_refresh(ok)
                ),
            )
        else:
            self._rebuild_all_tabs()

    def _on_auth_refresh(self, ok: bool) -> None:
        self._rebuild_all_tabs()
        if ok and self._account_ctrl.is_logged_in:
            self._sc_tab.refresh_pr_branch()
        if ok and self._account_ctrl.is_write_tier:
            self._versions_tab.refresh()
            self._ci_tab.refresh_workflows()
            self._ci_tab.refresh_releases()
            self._sc_tab.refresh_branches()

    def _rebuild_all_tabs(self) -> None:
        logged_in  = self._account_ctrl.is_logged_in
        write_tier = self._account_ctrl.is_write_tier
        self._account_tab.rebuild()
        self._sc_tab.rebuild(logged_in=logged_in, write_tier=write_tier)
        self._versions_tab.rebuild(write_tier=write_tier)
        self._ci_tab.rebuild(write_tier=write_tier)
        # DevSetupTab is static — no rebuild needed; just refresh display
        self._ds_tab.update_repo_root_display()

    # -----------------------------------------------------------------------
    # Callbacks from tab views
    # -----------------------------------------------------------------------

    def _on_auth_changed(self) -> None:
        """Called by AccountTab after login or logout."""
        self._rebuild_all_tabs()
        if self._account_ctrl.is_write_tier:
            self._versions_tab.refresh()
            self._ci_tab.refresh_workflows()
            self._ci_tab.refresh_releases()
            self._sc_tab.refresh_branches()

    def _on_setup_changed(self) -> None:
        """Called by DevSetupTab after repo root is set or changed."""
        if self._account_ctrl.is_write_tier:
            self._versions_tab.rebuild(write_tier=True)
            self._versions_tab.refresh()
