"""
ManifestoPanel — stub placeholder for the future visual manifest editor.
"""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

from ...core.views.widgets.plugin_panel import PluginPanel


class ManifestoPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self.orientation = "vertical"

        _bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56),
                           md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0))
        _bar.add_widget(MDLabel(text="Manifesto Editor", font_style="Title", role="large",
                                size_hint_x=1, halign="left"))
        self.add_widget(_bar)
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
