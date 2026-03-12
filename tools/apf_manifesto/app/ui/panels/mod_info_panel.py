"""
ui/panels/mod_info_panel.py
"""
from __future__ import annotations
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDCheckbox

from ...core.manifest_model import ManifestModel
from ...core.mod_registry import ModRegistry

_KV_LOADED = False
KV = """
<_LabeledCheck>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(48)
    spacing: dp(12)
    MDCheckbox:
        id: chk
        size_hint_x: None
        width: dp(48)
    MDLabel:
        id: lbl
        valign: 'middle'
"""


def _ensure_kv():
    global _KV_LOADED
    if not _KV_LOADED:
        from kivy.lang import Builder
        Builder.load_string(KV)
        _KV_LOADED = True


class _LabeledCheck(BoxLayout):
    pass


class ModInfoPanel(BoxLayout):
    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        _ensure_kv()
        super().__init__(orientation="vertical", padding="24dp",
                         spacing="8dp", **kwargs)
        self.model    = model
        self.registry = registry
        self._fields  = {}
        self._build()

    def _tf(self, hint, helper="", attr=""):
        tf = MDTextField(hint_text=hint, helper_text=helper,
                         helper_text_mode="on_focus", mode="rectangle",
                         size_hint_y=None, height="56dp",
                         text=str(getattr(self.model, attr, "") or ""))
        self._fields[attr] = tf
        return tf

    def _build(self):
        scroll = ScrollView()
        inner  = BoxLayout(orientation="vertical", spacing="12dp",
                           padding="8dp", size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))

        m = self.model
        inner.add_widget(MDLabel(text="Mod Identity", font_style="Subtitle1",
                                 size_hint_y=None, height="32dp"))
        for hint, helper, attr in [
            ("mod_id  *",    "author.game.modname",  "mod_id"),
            ("name",         "Display name",          "name"),
            ("version",      "e.g. 1.0.0",            "version"),
            ("description",  "Short description",     "description"),
        ]:
            inner.add_widget(self._tf(hint, helper, attr))

        inner.add_widget(MDLabel(text="Flags", font_style="Subtitle1",
                                 size_hint_y=None, height="32dp"))
        for flag_attr, label in [("enabled", "enabled"),
                                  ("vocab_validation", "vocab_validation")]:
            row = _LabeledCheck()
            row.ids.lbl.text = label
            row.ids.chk.active = bool(getattr(m, flag_attr))
            self._fields[flag_attr] = row.ids.chk
            inner.add_widget(row)

        inner.add_widget(MDLabel(text="Dependencies", font_style="Subtitle1",
                                 size_hint_y=None, height="32dp"))
        for hint, attr, value in [
            ("depends  (space-separated mod_ids)",       "depends",
             " ".join(m.depends)),
            ("incompatible  (space-separated mod_ids)",  "incompatible",
             " ".join(m.incompatible)),
        ]:
            tf = MDTextField(hint_text=hint, mode="rectangle",
                             size_hint_y=None, height="56dp", text=value)
            self._fields[attr] = tf
            inner.add_widget(tf)

        scroll.add_widget(inner)
        self.add_widget(scroll)

    def flush(self):
        m = self.model
        for attr in ("mod_id", "name", "version", "description"):
            tf = self._fields.get(attr)
            if tf:
                setattr(m, attr, tf.text.strip())
        m.enabled          = self._fields["enabled"].active
        m.vocab_validation = self._fields["vocab_validation"].active
        m.depends     = [x for x in self._fields["depends"].text.split() if x]
        m.incompatible = [x for x in
                          self._fields["incompatible"].text.split() if x]
