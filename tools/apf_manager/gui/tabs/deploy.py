"""
APF Manager — Deploy tab.

Shows the full mods.txt load order (AP mods draggable, non-AP mods dimmed).
Provides Deploy Selected, Clean, Validate, and (player mode) Check for Updates buttons.
Log panel at the bottom with inline fullscreen toggle.
"""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.tab import MDTabsBase

from ..widgets.mod_list import ModList
from ..widgets.log_panel import LogPanel


class DeployTab(MDFloatLayout, MDTabsBase):
    title = "Deploy"

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        root = MDBoxLayout(orientation="vertical", padding="8dp", spacing="8dp")

        # Toolbar buttons
        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="8dp",
        )
        self._deploy_btn = MDRaisedButton(
            text="Deploy Selected",
            size_hint=(None, None),
            size=("160dp", "40dp"),
        )
        self._deploy_btn.bind(on_release=self._on_deploy)
        self._clean_btn = MDFlatButton(
            text="Clean",
            size_hint=(None, None),
            size=("80dp", "40dp"),
        )
        self._clean_btn.bind(on_release=self._on_clean)
        self._validate_btn = MDFlatButton(
            text="Validate",
            size_hint=(None, None),
            size=("80dp", "40dp"),
        )
        self._validate_btn.bind(on_release=self._on_validate)
        self._update_btn = MDFlatButton(
            text="Check for Updates",
            size_hint=(None, None),
            size=("160dp", "40dp"),
        )
        self._update_btn.bind(on_release=self._on_check_updates)
        btn_row.add_widget(self._deploy_btn)
        btn_row.add_widget(self._clean_btn)
        btn_row.add_widget(self._validate_btn)
        btn_row.add_widget(self._update_btn)
        root.add_widget(btn_row)

        # Mod list (fills available space)
        list_scroll = ScrollView(size_hint=(1, 1))
        self._mod_list = ModList(app=self.app)
        list_scroll.add_widget(self._mod_list)
        root.add_widget(list_scroll)

        # Log panel (fixed height, with toggle)
        self._log_panel = LogPanel(size_hint_y=None, height="200dp")
        root.add_widget(self._log_panel)

        self.add_widget(root)

    def on_tab_activated(self):
        self._refresh_mod_list()
        self._apply_mode_ui()

    def _apply_mode_ui(self):
        is_player = (self.app.config_data.mode == "player")
        self._update_btn.opacity = 1 if is_player else 0
        self._update_btn.disabled = not is_player

    def _refresh_mod_list(self):
        detection = self.app.refresh_detection()
        if not detection.valid:
            self.log(f"[WARN] UE4SS not detected: {'; '.join(detection.missing)}")
            return

        from ...load_order import ModsTextManager
        known = self.app.discovery.known_ap_mod_names()
        mgr = ModsTextManager()
        entries = mgr.get_entries(detection.mods_txt, known)

        # Fill in folder_exists flags
        for e in entries:
            e.folder_exists = (detection.mods_dir / e.name).is_dir()

        mod_infos = {m.folder_name: m for m in self.app.discovery.discover()}
        installed = set(self.app.state.installed_mods.keys())
        self._mod_list.populate(entries, mod_infos, installed)

    def log(self, msg: str):
        self._log_panel.append(msg)

    def _on_deploy(self, *_):
        detection = self.app.refresh_detection()
        if not detection.valid:
            self.log(f"[ERROR] UE4SS not detected. Configure game root in Setup tab first.")
            return
        # Ensure logicmods_dir exists (may need to be created)
        if detection.logicmods_dir and not detection.logicmods_dir.exists():
            detection.logicmods_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Created LogicMods folder: {detection.logicmods_dir}")

        from ...engine import InstallEngine
        engine = InstallEngine(self.app.config_data, log=self.log)

        # Deploy all selected (enabled) AP mods
        mods = [m for m in self.app.discovery.discover() if not m.is_stub]

        def manual_step_cb(steps):
            for s in steps:
                from ..dialogs import show_step_dialog
                show_step_dialog(s, self.app.config_data.source_project)

        ok = True
        for mod in mods:
            if not engine.deploy(mod, self.app.state, detection,
                                 manual_step_cb=manual_step_cb):
                ok = False

        self.app.state.save()
        self.log("Deploy complete." if ok else "Deploy finished with errors.")
        self._refresh_mod_list()

    def _on_clean(self, *_):
        detection = self.app.refresh_detection()
        if not detection.valid:
            self.log("[ERROR] UE4SS not detected.")
            return
        from ...engine import InstallEngine
        engine = InstallEngine(self.app.config_data, log=self.log)
        known = list(self.app.discovery.known_ap_mod_names())
        engine.clean(known, self.app.state, detection)
        self.app.state.save()
        self._refresh_mod_list()

    def _on_validate(self, *_):
        detection = self.app.refresh_detection()
        if not detection.valid:
            self.log("[ERROR] UE4SS not detected.")
            return
        from ...validator import Validator
        v = Validator(self.app.config_data, self.app.discovery,
                      self.app.state, detection, log=self.log)
        results = v.validate_all()
        for status, label, detail in results:
            self.log(f"  [{status}] {label}: {detail}")

    def _on_check_updates(self, *_):
        from ...remote import GitHubReleaseManager
        mgr = GitHubReleaseManager(self.app.config_data.repo_api_url)
        self.log("Checking for updates...")
        info = mgr.check_latest()
        if info is None:
            self.log("[WARN] Could not check for updates. Check repo URL in Setup tab.")
            return
        version = mgr.get_release_version(info)
        self.log(f"Latest release: {version}")
