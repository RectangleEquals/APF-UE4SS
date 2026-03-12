"""
ui/panels/options_panel.py
"""
from __future__ import annotations
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.textfield import MDTextField

from ...core.manifest_model import (
    ManifestModel, ToggleOption, RangeOption, TextChoiceOption,
)
from ...core.mod_registry import ModRegistry

_TYPE_COLORS = {
    "toggle":      [0.29, 0.56, 0.89, 1],
    "range":       [0.48, 0.76, 0.47, 1],
    "text_choice": [0.96, 0.65, 0.14, 1],
}
_TYPE_LABELS = {"toggle": "Toggle", "range": "Range", "text_choice": "Text Choice"}


def _make_card(key, opt, panel):
    card = MDCard(orientation="vertical", padding="12dp", spacing="4dp",
                  size_hint_y=None, elevation=2, radius=[8])
    card.bind(minimum_height=card.setter("height"))

    header = BoxLayout(size_hint_y=None, height="36dp", spacing="8dp")
    header.add_widget(MDLabel(
        text=_TYPE_LABELS.get(opt.type, opt.type),
        theme_text_color="Custom",
        text_color=_TYPE_COLORS.get(opt.type, [1, 1, 1, 1]),
        bold=True, size_hint_x=None, width="120dp",
    ))
    header.add_widget(MDLabel(text=key, bold=True))
    header.add_widget(MDIconButton(icon="delete", size_hint_x=None, width="48dp",
                                   on_release=lambda _, k=key: panel._delete(k)))
    card.add_widget(header)
    card.add_widget(MDLabel(text=opt.description or "(no description)",
                            theme_text_color="Hint",
                            size_hint_y=None, height="24dp"))
    if isinstance(opt, ToggleOption):
        row = BoxLayout(size_hint_y=None, height="32dp", spacing="8dp")
        row.add_widget(MDLabel(text="default:", size_hint_x=None, width="80dp"))
        row.add_widget(MDCheckbox(active=opt.default, size_hint_x=None, width="48dp"))
        card.add_widget(row)
    elif isinstance(opt, RangeOption):
        card.add_widget(MDLabel(
            text=f"Range: [{opt.range_start}, {opt.range_end}]  Default: {opt.default}",
            size_hint_y=None, height="32dp"))
    elif isinstance(opt, TextChoiceOption):
        card.add_widget(MDLabel(
            text=f"Choices: {', '.join(opt.choices)}  Default: {opt.default}",
            size_hint_y=None, height="32dp"))
    return card


class OptionsPanel(BoxLayout):
    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model
        self._dlg  = None
        self._list = None
        self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Options", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Add Option",
                                      size_hint_x=None, width="160dp",
                                      on_release=lambda _: self._add_dialog()))
        self.add_widget(top)
        scroll = ScrollView()
        self._list = BoxLayout(orientation="vertical", spacing="10dp",
                               padding="4dp", size_hint_y=None)
        self._list.bind(minimum_height=self._list.setter("height"))
        scroll.add_widget(self._list)
        self.add_widget(scroll)
        self._refresh()

    def _refresh(self):
        self._list.clear_widgets()
        for key, opt in self.model.options.items():
            self._list.add_widget(_make_card(key, opt, self))

    def _delete(self, key):
        self.model.options.pop(key, None)
        self._refresh()

    def _add_dialog(self):
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="280dp", padding="8dp")
        key_f  = MDTextField(hint_text="option key", mode="rectangle",
                             size_hint_y=None, height="56dp")
        desc_f = MDTextField(hint_text="description", mode="rectangle",
                             size_hint_y=None, height="56dp")
        type_f = MDTextField(hint_text="type: toggle | range | text_choice",
                             mode="rectangle", size_hint_y=None, height="56dp")
        extra_f = MDTextField(
            hint_text="toggle: true/false  |  range: start,end,default  |  text_choice: a,b,c,default",
            mode="rectangle", size_hint_y=None, height="56dp")
        for w in (key_f, desc_f, type_f, extra_f):
            content.add_widget(w)

        def _create(*_):
            key, t, desc, extra = (key_f.text.strip(), type_f.text.strip().lower(),
                                   desc_f.text.strip(), extra_f.text.strip())
            if not key or t not in ("toggle", "range", "text_choice"):
                key_f.error = True; return
            if t == "toggle":
                opt = ToggleOption(default=(extra.lower() == "true"), description=desc)
            elif t == "range":
                p = [x.strip() for x in extra.split(",")]
                opt = RangeOption(range_start=int(p[0]) if p else 0,
                                  range_end=int(p[1]) if len(p) > 1 else 10,
                                  default=p[2] if len(p) > 2 else "0",
                                  description=desc)
            else:
                p = [x.strip() for x in extra.split(",")]
                opt = TextChoiceOption(choices=p[:-1] if len(p) > 1 else p,
                                       default=p[-1] if p else "",
                                       description=desc)
            self.model.options[key] = opt
            self._dlg.dismiss()
            self._refresh()

        self._dlg = MDDialog(
            title="Add Option", type="custom", content_cls=content,
            buttons=[MDFlatButton(text="CANCEL",
                                  on_release=lambda *_: self._dlg.dismiss()),
                     MDRaisedButton(text="ADD", on_release=_create)],
        )
        self._dlg.open()

    def flush(self):
        pass
