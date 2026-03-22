"""
ManifestoPanel — stub placeholder for the future visual manifest editor.
"""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.label import MDLabel
from kivymd.uix.toolbar import MDTopAppBar

from ...gui.widgets.plugin_panel import PluginPanel


class ManifestoPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self.orientation = "vertical"

        self.add_widget(MDTopAppBar(title="Manifesto Editor", elevation=0))
        self.add_widget(MDLabel(
            text=(
                "Visual Manifest Editor\n\n"
                "Coming Soon\n\n"
                "A fully visual WYSIWYG editor for AP Framework mod manifests,\n"
                "including logic canvas, item/location/goal editors,\n"
                "schema validation, and logic probability simulation."
            ),
            halign="center",
            valign="middle",
        ))

    def on_activate(self, game_profile) -> None:
        pass

    def on_deactivate(self) -> None:
        pass
