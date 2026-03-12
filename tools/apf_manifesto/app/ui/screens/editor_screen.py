"""
ui/screens/editor_screen.py
"""
from __future__ import annotations
import traceback
from kivy.app import App
from kivy.properties import StringProperty
from kivy.uix.screenmanager import Screen
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.tab import MDTabsBase, MDTabs

from ...core.manifest_model import ManifestModel
from ...core.mod_registry import ModRegistry

_KV_LOADED = False
KV = """
<EditorTab>:
    MDLabel:
        text: root.title
        halign: "center"

<EditorScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        md_bg_color: app.theme_cls.bg_darkest

        MDTopAppBar:
            id: toolbar
            title: root.editor_title
            elevation: 2
            left_action_items: [["arrow-left", lambda x: app.go_home(), "Back"]]
            right_action_items: [["content-save", lambda x: root.save(), "Save"], ["check-circle-outline", lambda x: root.validate(), "Validate"]]

        MDTabs:
            id: tabs
            on_tab_switch: root.on_tab_switch(*args)
"""


def _ensure_kv():
    global _KV_LOADED
    if not _KV_LOADED:
        from kivy.lang import Builder
        Builder.load_string(KV)
        _KV_LOADED = True


class EditorTab(MDFloatLayout, MDTabsBase):
    pass


class EditorScreen(Screen):
    # Must be a Kivy Property so KV bindings work
    editor_title = StringProperty("")

    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        _ensure_kv()
        super().__init__(**kwargs)
        self.model    = model
        self.registry = registry
        self.editor_title = (model.name or model.mod_id) + \
                            ("  [read-only]" if model._read_only else "")
        self._panels = {}
        self._built  = False

    def on_enter(self, *_):
        if not self._built:
            try:
                self._build_tabs()
                self._built = True
            except Exception:
                App.get_running_app()._show_error(
                    f"Failed to build editor tabs:\n{traceback.format_exc()}"
                )

    def _build_tabs(self):
        from ..panels.mod_info_panel     import ModInfoPanel
        from ..panels.options_panel      import OptionsPanel
        from ..panels.goals_panel        import GoalsPanel
        from ..panels.capabilities_panel import CapabilitiesPanel

        tabs = self.ids.tabs
        for title, PanelCls in [
            ("Mod Info",     ModInfoPanel),
            ("Options",      OptionsPanel),
            ("Goals",        GoalsPanel),
            ("Capabilities", CapabilitiesPanel),
        ]:
            tab = EditorTab(title=title)
            panel = PanelCls(model=self.model, registry=self.registry,
                             size_hint=(1, 1))
            tab.add_widget(panel)
            tabs.add_widget(tab)
            self._panels[title] = panel

    def on_tab_switch(self, instance_tabs, instance_tab,
                      instance_tab_label, tab_text):
        panel = self._panels.get(tab_text)
        if panel and hasattr(panel, "on_show"):
            panel.on_show()

    def save(self):
        from ...core.manifest_io import save_manifest
        from kivymd.uix.snackbar import MDSnackbar
        from kivymd.uix.label import MDLabel as _Lbl
        for panel in self._panels.values():
            if hasattr(panel, "flush"):
                panel.flush()
        try:
            save_manifest(self.model)
            sb = MDSnackbar(pos_hint={"center_x": 0.5}, size_hint_x=0.4,
                            y="12dp")
            sb.add_widget(_Lbl(text="Manifest saved \u2713"))
            sb.open()
        except Exception:
            App.get_running_app()._show_error(
                f"Save failed:\n{traceback.format_exc()}"
            )

    def validate(self):
        from ...core.validator import ManifestValidator
        from kivymd.uix.dialog import MDDialog
        from kivymd.uix.button import MDFlatButton
        from kivymd.uix.list import MDList, TwoLineListItem

        for panel in self._panels.values():
            if hasattr(panel, "flush"):
                panel.flush()

        try:
            errors = ManifestValidator(self.registry).validate(self.model)
        except Exception:
            App.get_running_app()._show_error(
                f"Validation failed:\n{traceback.format_exc()}"
            )
            return

        if not errors:
            text, content = "\u2713  No issues found.", None
        else:
            text = f"{len(errors)} issue(s):"
            lst = MDList()
            for e in errors:
                icon = "\u26a0" if e.severity == "warning" else "\u2716"
                lst.add_widget(TwoLineListItem(
                    text=f"{icon}  {e.path}",
                    secondary_text=e.message,
                ))
            content = lst

        dlg = MDDialog(
            title="Validation", text=text,
            type="custom" if content else "simple",
            content_cls=content,
            buttons=[MDFlatButton(text="OK",
                                  on_release=lambda *_: dlg.dismiss())],
        )
        dlg.open()
