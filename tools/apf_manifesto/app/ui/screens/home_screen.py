"""
ui/screens/home_screen.py
"""
from __future__ import annotations
import traceback
from pathlib import Path
from kivy.app import App
from kivy.uix.screenmanager import Screen

_KV_LOADED = False
KV = """
<HomeScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        md_bg_color: app.theme_cls.bg_darkest

        MDTopAppBar:
            title: "APF Manifesto"
            elevation: 2
            right_action_items: [["refresh", lambda x: root.refresh_mods(), "Refresh"], ["folder-open", lambda x: root.open_mod_dialog(), "Open mod"], ["plus-circle", lambda x: root.new_mod_dialog(), "New mod"]]

        MDBoxLayout:
            orientation: 'vertical'
            padding: dp(24)
            spacing: dp(12)

            MDLabel:
                text: "Mods"
                font_style: "H5"
                size_hint_y: None
                height: self.texture_size[1] + dp(8)

            MDLabel:
                id: empty_label
                text: "No mods found.\\nClick  +  to create your first mod."
                halign: "center"
                theme_text_color: "Hint"
                size_hint_y: None
                height: dp(48)

            ScrollView:
                MDList:
                    id: mod_list
"""


def _ensure_kv():
    global _KV_LOADED
    if not _KV_LOADED:
        from kivy.lang import Builder
        Builder.load_string(KV)
        _KV_LOADED = True


class HomeScreen(Screen):
    _new_dialog = None

    def __init__(self, **kwargs):
        _ensure_kv()
        super().__init__(**kwargs)

    def on_enter(self, *_):
        self.refresh_mods()

    def refresh_mods(self):
        from kivymd.uix.list import TwoLineIconListItem, IconLeftWidget
        app = App.get_running_app()
        app.registry.scan()
        mod_list  = self.ids.mod_list
        mod_list.clear_widgets()
        empty_lbl = self.ids.empty_label
        entries   = app.registry.mods()
        empty_lbl.opacity = 0 if entries else 1
        for entry in entries:
            m = entry.model
            item = TwoLineIconListItem(
                text=m.name or entry.folder_name,
                secondary_text=f"{m.mod_id}   v{m.version}",
                on_release=lambda _, path=m._path: app.open_mod(path),
            )
            item.add_widget(IconLeftWidget(icon="puzzle"))
            mod_list.add_widget(item)

    def new_mod_dialog(self):
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.dialog import MDDialog

        content = BoxLayout(orientation="vertical", spacing="12dp",
                            size_hint_y=None, height="180dp", padding="8dp")
        name_f = MDTextField(hint_text="Mod folder name  (e.g. MygameItemShuffle)",
                             mode="rectangle", size_hint_y=None, height="56dp")
        id_f   = MDTextField(hint_text="mod_id  (e.g. author.game.modname)",
                             helper_text="Leave blank to auto-generate",
                             helper_text_mode="on_focus",
                             mode="rectangle", size_hint_y=None, height="56dp")
        content.add_widget(name_f)
        content.add_widget(id_f)

        def _create(*_):
            name = name_f.text.strip()
            if not name:
                name_f.error = True
                return
            self._new_dialog.dismiss()
            self._do_create(name, id_f.text.strip())

        self._new_dialog = MDDialog(
            title="New Mod", type="custom", content_cls=content,
            buttons=[
                MDFlatButton(text="CANCEL",
                             on_release=lambda *_: self._new_dialog.dismiss()),
                MDRaisedButton(text="CREATE", on_release=_create),
            ],
        )
        self._new_dialog.open()

    def _do_create(self, mod_name, mod_id):
        from ...core.manifest_io import new_manifest
        app = App.get_running_app()
        try:
            model = new_manifest(str(app.registry.mods_dir), mod_name, mod_id)
            app.registry.scan()
            app.open_mod(model._path)
        except Exception:
            app._show_error(
                f"Failed to create mod '{mod_name}':\n\n{traceback.format_exc()}"
            )

    def open_mod_dialog(self):
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.dialog import MDDialog

        app = App.get_running_app()
        fc  = FileChooserListView(path=str(app.registry.mods_dir),
                                  dirselect=True, size_hint=(1, 1))
        content = BoxLayout(orientation="vertical", size_hint=(1, 1))
        content.add_widget(fc)

        def _open(*_):
            sel = fc.selection
            if sel:
                p = Path(sel[0])
                manifest = p / "manifest.json" if p.is_dir() else p
                if manifest.exists():
                    dlg.dismiss()
                    app.open_mod(str(manifest))

        dlg = MDDialog(
            title="Select Mod Folder", type="custom", content_cls=content,
            size_hint=(0.9, 0.8),
            buttons=[
                MDFlatButton(text="CANCEL", on_release=lambda *_: dlg.dismiss()),
                MDRaisedButton(text="OPEN", on_release=_open),
            ],
        )
        dlg.open()
