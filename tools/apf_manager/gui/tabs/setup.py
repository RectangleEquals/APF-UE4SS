"""
APF Manager — Setup tab.

First-run wizard / always-accessible settings:
  - Player vs Developer mode toggle
  - Game root field with live UE4SS validation
  - Repo URL (player mode)
  - Source project + build dir (dev mode only)
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.textfield import MDTextField


class SetupTab(MDFloatLayout, MDTabsBase):
    title = "Setup"

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        layout = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="16dp",
        )

        # Mode toggle
        mode_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="12dp",
        )
        mode_label = MDLabel(
            text="Mode:",
            size_hint_x=None,
            width="80dp",
        )
        self._player_btn = MDRaisedButton(
            text="Player",
            size_hint=(None, None),
            size=("120dp", "40dp"),
        )
        self._dev_btn = MDFlatButton(
            text="Developer",
            size_hint=(None, None),
            size=("120dp", "40dp"),
        )
        self._player_btn.bind(on_release=lambda _: self._set_mode("player"))
        self._dev_btn.bind(on_release=lambda _: self._set_mode("dev"))
        mode_row.add_widget(mode_label)
        mode_row.add_widget(self._player_btn)
        mode_row.add_widget(self._dev_btn)
        layout.add_widget(mode_row)

        # Game root field
        self._game_root_field = MDTextField(
            hint_text="Game root folder (e.g. E:/SteamLibrary/steamapps/common/Palworld)",
            text=self.app.config_data.game_root,
            mode="rectangle",
        )
        self._game_root_field.bind(text=self._on_game_root_changed)
        layout.add_widget(self._game_root_field)

        # UE4SS detection status
        self._ue4ss_status = MDLabel(
            text="",
            size_hint_y=None,
            height="32dp",
            theme_text_color="Secondary",
        )
        layout.add_widget(self._ue4ss_status)

        # Browse button
        browse_btn = MDFlatButton(
            text="Browse...",
            size_hint=(None, None),
            size=("100dp", "36dp"),
        )
        browse_btn.bind(on_release=self._browse_game_root)
        layout.add_widget(browse_btn)

        # Repo URL (player mode)
        self._repo_url_field = MDTextField(
            hint_text="GitHub repo URL (e.g. https://github.com/owner/repo)",
            text=self.app.config_data.repo_api_url,
            mode="rectangle",
        )
        self._repo_url_field.bind(text=self._on_repo_url_changed)
        self._repo_url_row = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="72dp",
        )
        self._repo_url_row.add_widget(MDLabel(
            text="Repository URL (for checking updates)",
            font_style="Caption",
            size_hint_y=None,
            height="24dp",
        ))
        self._repo_url_row.add_widget(self._repo_url_field)
        layout.add_widget(self._repo_url_row)

        # Source project (dev mode only)
        self._src_field = MDTextField(
            hint_text="Source project root (defaults to project root relative to this tool)",
            text=self.app.config_data.source_project,
            mode="rectangle",
        )
        self._src_field.bind(text=self._on_src_changed)
        self._build_field = MDTextField(
            hint_text="Build output directory (e.g. build/Release/bin)",
            text=self.app.config_data.build_dir,
            mode="rectangle",
        )
        self._build_field.bind(text=self._on_build_changed)
        self._dev_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="180dp",
            spacing="8dp",
        )
        self._dev_box.add_widget(MDLabel(
            text="Developer settings",
            font_style="Subtitle2",
            size_hint_y=None,
            height="32dp",
        ))
        self._dev_box.add_widget(self._src_field)
        self._dev_box.add_widget(self._build_field)
        layout.add_widget(self._dev_box)

        # Save button
        save_btn = MDRaisedButton(
            text="Save Settings",
            size_hint=(None, None),
            size=("160dp", "40dp"),
        )
        save_btn.bind(on_release=self._save)
        layout.add_widget(save_btn)

        self.add_widget(layout)
        self._apply_mode_ui()

    def on_tab_activated(self):
        self._apply_mode_ui()

    def _set_mode(self, mode: str):
        self.app.config_data.mode = mode
        self._apply_mode_ui()

    def _apply_mode_ui(self):
        mode = self.app.config_data.mode
        is_dev = (mode == "dev")
        self._dev_box.opacity = 1 if is_dev else 0.3
        self._dev_box.disabled = not is_dev
        # Style active button
        if is_dev:
            self._dev_btn.__class__ = MDRaisedButton
            self._player_btn.__class__ = MDFlatButton
        else:
            self._player_btn.__class__ = MDRaisedButton
            self._dev_btn.__class__ = MDFlatButton

    def _on_game_root_changed(self, instance, value):
        self.app.config_data.game_root = value
        # Debounce detection by 0.5s
        Clock.unschedule(self._run_detection)
        Clock.schedule_once(self._run_detection, 0.5)

    def _run_detection(self, *_):
        result = self.app.refresh_detection()
        if result.valid:
            self._ue4ss_status.text = (
                f"✓ UE4SS found — Mods: {result.mods_dir}"
            )
            self._ue4ss_status.theme_text_color = "Custom"
            self._ue4ss_status.text_color = (0.1, 0.6, 0.1, 1)
        else:
            missing_str = "; ".join(result.missing[:2])
            self._ue4ss_status.text = f"✗ {missing_str}"
            self._ue4ss_status.theme_text_color = "Custom"
            self._ue4ss_status.text_color = (0.8, 0.1, 0.1, 1)

    def _on_repo_url_changed(self, instance, value):
        self.app.config_data.repo_api_url = value

    def _on_src_changed(self, instance, value):
        self.app.config_data.source_project = value

    def _on_build_changed(self, instance, value):
        self.app.config_data.build_dir = value

    def _browse_game_root(self, *_):
        from kivymd.uix.filemanager import MDFileManager
        self._file_manager = MDFileManager(
            exit_manager=self._close_file_manager,
            select_path=self._select_game_root,
            selector="folder",
        )
        self._file_manager.show("/")

    def _close_file_manager(self, *_):
        if hasattr(self, "_file_manager"):
            self._file_manager.close()

    def _select_game_root(self, path: str):
        self._game_root_field.text = path
        self._close_file_manager()

    def _save(self, *_):
        self.app.save_config()
        # Reflect any URL normalization back into the field
        self._repo_url_field.text = self.app.config_data.repo_api_url
        self._ue4ss_status.text = "Settings saved."
