"""
APF Manager — KivyMD application root.
"""

from __future__ import annotations

from kivymd.app import MDApp
from kivymd.uix.tab import MDTabsBase
from kivymd.uix.floatlayout import MDFloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder

from ..config import APFConfig, APFState
from ..discovery import ModDiscovery
from ..ue4ss import UE4SSDetector, UE4SSDetectionResult

KV = """
<APFTab>:
    MDLabel:
        text: root.title

MDBoxLayout:
    orientation: 'vertical'

    MDTopAppBar:
        title: "APF Manager"
        elevation: 4

    MDTabs:
        id: tabs
        on_tab_switch: app.on_tab_switch(*args)
"""


class APFTab(MDFloatLayout, MDTabsBase):
    pass


class APFManagerApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = APFConfig.load().resolve()
        self.state = APFState.load()
        self.discovery = ModDiscovery(self.config_data)
        self.detector = UE4SSDetector()
        self.detection: UE4SSDetectionResult | None = None
        self.title = "APF Manager"
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Blue"

    def build(self):
        from .tabs.setup import SetupTab
        from .tabs.deploy import DeployTab
        from .tabs.config_tab import ConfigTab
        from .tabs.diagnostics import DiagnosticsTab
        from .tabs.package import PackageTab

        root = BoxLayout(orientation="vertical")

        from kivymd.uix.toolbar import MDTopAppBar
        toolbar = MDTopAppBar(title="APF Manager", elevation=4)
        root.add_widget(toolbar)

        from kivymd.uix.tab import MDTabs
        self.tabs = MDTabs()
        self.tabs.bind(on_tab_switch=self.on_tab_switch)

        self.setup_tab = SetupTab(app=self)
        self.deploy_tab = DeployTab(app=self)
        self.config_tab = ConfigTab(app=self)
        self.diag_tab = DiagnosticsTab(app=self)
        self.package_tab = PackageTab(app=self)

        self.tabs.add_widget(self.setup_tab)
        self.tabs.add_widget(self.deploy_tab)
        self.tabs.add_widget(self.config_tab)
        self.tabs.add_widget(self.diag_tab)
        self.tabs.add_widget(self.package_tab)

        root.add_widget(self.tabs)
        return root

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if hasattr(instance_tab, "on_tab_activated"):
            instance_tab.on_tab_activated()

    def refresh_detection(self) -> UE4SSDetectionResult:
        self.detection = self.detector.detect(self.config_data.game_root)
        return self.detection

    def save_config(self) -> None:
        self.config_data.save()
        self.discovery.invalidate()

    def log(self, msg: str) -> None:
        """Append a message to the deploy tab log panel."""
        if hasattr(self, "deploy_tab"):
            self.deploy_tab.log(msg)

    def on_stop(self):
        self.state.save()
        self.config_data.save()
