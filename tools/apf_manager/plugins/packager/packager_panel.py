"""
PackagerPanel — dev-only hub_panel for building release ZIPs and .apworld files.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from ...gui.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.config import GameProfile


class PackagerPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._build_ui()

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile

    def on_deactivate(self) -> None:
        pass

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56),
                              md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0))
        toolbar.add_widget(MDLabel(text="Package", font_style="Title", role="large",
                                   size_hint_x=1, halign="left"))
        self._toolbar = toolbar
        self.add_widget(toolbar)

        form = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            adaptive_height=True,
            padding=[dp(24), dp(16)],
            spacing=dp(12),
        )

        form.add_widget(MDLabel(
            text="Build release artifacts from source_project + build_dir.",
            size_hint=(1, None),
            height=dp(36),
        ))

        version_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(56),
            spacing=dp(8),
        )
        version_row.add_widget(MDLabel(
            text="Version:",
            size_hint=(0.3, 1),
            halign="right",
            valign="middle",
        ))
        self._version_field = MDTextField(
            hint_text="e.g. 1.2.0",
            mode="outlined",
            size_hint=(0.7, 1),
        )
        version_row.add_widget(self._version_field)
        form.add_widget(version_row)

        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(56),
            spacing=dp(12),
        )
        btn_row.add_widget(MDButton(
            MDButtonText(text="Build Release ZIP"),
            style="filled",
            on_release=lambda *_: threading.Thread(
                target=self._build_release, daemon=True
            ).start(),
        ))
        btn_row.add_widget(MDButton(
            MDButtonText(text="Build .apworld"),
            style="filled",
            on_release=lambda *_: threading.Thread(
                target=self._build_apworld, daemon=True
            ).start(),
        ))
        form.add_widget(btn_row)
        self.add_widget(form)

    def _build_release(self) -> None:
        if not self._profile:
            Clock.schedule_once(lambda dt: self._host.log("No game profile."), 0)
            return

        version = self._version_field.text.strip() or "0.0.0"
        detection = self._host.get_detection()
        if not detection:
            Clock.schedule_once(lambda dt: self._host.log("No UE4SS detection."), 0)
            return

        from .package_builder import PackageBuilder
        output_dir = Path.home() / "Desktop"
        if not output_dir.is_dir():
            output_dir = Path.home()

        builder = PackageBuilder(
            self._profile, detection, version,
            log_fn=lambda m: Clock.schedule_once(
                lambda dt, msg=m: self._host.log(msg), 0
            ),
        )
        builder.build(output_dir)

    def _build_apworld(self) -> None:
        if not self._profile or not self._profile.source_project:
            Clock.schedule_once(lambda dt: self._host.log("source_project not configured."), 0)
            return

        from .package_builder import ApworldPackager
        source = Path(self._profile.source_project)
        worlds_apf = source / "worlds" / "apf"
        output = source / "apf.apworld"

        ok = ApworldPackager.build(
            worlds_apf, output,
            log_fn=lambda m: Clock.schedule_once(
                lambda dt, msg=m: self._host.log(msg), 0
            ),
        )
        if not ok:
            Clock.schedule_once(lambda dt: self._host.log("apworld build failed."), 0)
