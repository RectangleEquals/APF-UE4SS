"""
APF Manager — Config tab.

Reads/writes the deployed framework_config.json (not the source copy).
"""

from __future__ import annotations

import json
from pathlib import Path

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.textfield import MDTextField


class ConfigTab(MDFloatLayout, MDTabsBase):
    title = "Config"

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
            text="Framework Config (framework_config.json)",
            font_style="H6",
            size_hint_y=None,
            height="40dp",
        ))
        layout.add_widget(MDLabel(
            text="Editing the deployed config (in your game's Mods folder). Changes persist across redeploys.",
            font_style="Caption",
            theme_text_color="Secondary",
            size_hint_y=None,
            height="24dp",
        ))

        self._host_field = MDTextField(
            hint_text="Server host (e.g. archipelago.gg or localhost)",
            mode="rectangle",
        )
        self._port_field = MDTextField(
            hint_text="Server port (default: 38281)",
            mode="rectangle",
            input_filter="int",
        )
        self._slot_field = MDTextField(
            hint_text="Slot name (your player name)",
            mode="rectangle",
        )
        self._password_field = MDTextField(
            hint_text="Password (leave blank if none)",
            mode="rectangle",
            password=True,
        )

        for field in (self._host_field, self._port_field, self._slot_field, self._password_field):
            layout.add_widget(field)

        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="8dp",
        )
        save_btn = MDRaisedButton(
            text="Save Config",
            size_hint=(None, None),
            size=("140dp", "40dp"),
        )
        save_btn.bind(on_release=self._save)
        reload_btn = MDFlatButton(
            text="Reload",
            size_hint=(None, None),
            size=("100dp", "40dp"),
        )
        reload_btn.bind(on_release=lambda _: self._load())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(reload_btn)
        layout.add_widget(btn_row)

        self._status = MDLabel(
            text="",
            size_hint_y=None,
            height="32dp",
            theme_text_color="Secondary",
        )
        layout.add_widget(self._status)

        self.add_widget(layout)

    def on_tab_activated(self):
        self._load()

    def _config_path(self) -> Path | None:
        detection = self.app.detection or self.app.refresh_detection()
        if not detection.valid:
            return None
        return detection.mods_dir / "APFrameworkMod" / "framework_config.json"

    def _load(self):
        path = self._config_path()
        if path is None or not path.exists():
            self._status.text = "Config not found — deploy APFrameworkMod first."
            return
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            ap = cfg.get("ap_server", {})
            self._host_field.text = str(ap.get("host", ""))
            self._port_field.text = str(ap.get("port", "38281"))
            self._slot_field.text = str(ap.get("slot_name", ""))
            self._password_field.text = str(ap.get("password", ""))
            self._status.text = f"Loaded from {path}"
        except Exception as exc:
            self._status.text = f"Error reading config: {exc}"

    def _save(self, *_):
        path = self._config_path()
        if path is None:
            self._status.text = "UE4SS not detected — configure game root in Setup tab."
            return
        try:
            # Read existing to preserve unknown fields
            existing: dict = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            ap = existing.setdefault("ap_server", {})
            ap["host"] = self._host_field.text
            try:
                ap["port"] = int(self._port_field.text)
            except ValueError:
                ap["port"] = 38281
            ap["slot_name"] = self._slot_field.text
            ap["password"] = self._password_field.text

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(existing, indent=4), encoding="utf-8")
            self._status.text = "Config saved."
        except Exception as exc:
            self._status.text = f"Error saving config: {exc}"
