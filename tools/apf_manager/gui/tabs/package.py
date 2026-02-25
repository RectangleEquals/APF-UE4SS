"""
APF Manager — Package tab (dev mode only).

Builds a distributable release zip for end-users/testers.
"""

from __future__ import annotations

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.textfield import MDTextField


class PackageTab(MDFloatLayout, MDTabsBase):
    title = "Package"

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        layout = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
        )
        layout.add_widget(MDLabel(
            text="Build Release Package",
            font_style="H6",
            size_hint_y=None,
            height="40dp",
        ))
        layout.add_widget(MDLabel(
            text="Creates a distributable zip for players. Only available in Developer mode.",
            font_style="Caption",
            theme_text_color="Secondary",
            size_hint_y=None,
            height="24dp",
        ))

        self._version_field = MDTextField(
            hint_text="Version tag (e.g. v0.1.0-alpha)",
            mode="rectangle",
        )
        layout.add_widget(self._version_field)

        build_btn = MDRaisedButton(
            text="Build Package Zip",
            size_hint=(None, None),
            size=("180dp", "40dp"),
        )
        build_btn.bind(on_release=self._on_build)
        layout.add_widget(build_btn)

        self._status = MDLabel(
            text="",
            size_hint_y=None,
            height="48dp",
            theme_text_color="Secondary",
        )
        layout.add_widget(self._status)

        self.add_widget(layout)

    def on_tab_activated(self):
        is_dev = (self.app.config_data.mode == "dev")
        self.disabled = not is_dev
        self.opacity = 1.0 if is_dev else 0.4

    def _on_build(self, *_):
        if self.app.config_data.mode != "dev":
            self._status.text = "Package building is only available in Developer mode."
            return
        version = self._version_field.text.strip() or "dev"
        try:
            from ...packager import PackageBuilder
            builder = PackageBuilder(
                self.app.config_data,
                self.app.discovery,
                log=lambda msg: setattr(self._status, "text", msg),
            )
            out = builder.build(version)
            self._status.text = f"Package saved to:\n{out}"
        except Exception as exc:
            self._status.text = f"Error: {exc}"
