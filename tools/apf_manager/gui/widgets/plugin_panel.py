"""
PluginPanel — base class for all hub_panel plugin contributions.

Plugins subclass this and override on_activate / on_deactivate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivymd.uix.boxlayout import MDBoxLayout

if TYPE_CHECKING:
    from ...core.config import GameProfile


class PluginPanel(MDBoxLayout):
    """
    Base widget for all hub_panel contributions.

    Lifecycle:
      on_activate(game_profile)  — called when this panel becomes visible
      on_deactivate()            — called when another panel is selected
    """

    def __init__(self, host=None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.host = host

    def on_activate(self, game_profile: "GameProfile") -> None:
        """Override to refresh content when this panel is shown."""

    def on_deactivate(self) -> None:
        """Override to clean up when this panel is hidden."""

    def can_deactivate(self) -> bool:
        """Override to block panel switching (e.g. unsaved changes). Return False to stay."""
        return True
