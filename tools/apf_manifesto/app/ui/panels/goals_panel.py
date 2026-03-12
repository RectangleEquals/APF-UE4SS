"""
ui/panels/goals_panel.py
"""
from __future__ import annotations
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from ...core.manifest_model import Goal, ManifestModel
from ...core.mod_registry import ModRegistry
from ...core.logic_parser import parse


def _logic_err(text):
    if not text.strip():
        return ""
    try:
        parse(text)
        return ""
    except ValueError as e:
        return str(e)


def _make_card(goal, idx, panel):
    card = MDCard(orientation="vertical", padding="12dp", spacing="4dp",
                  size_hint_y=None, elevation=2, radius=[8])
    card.bind(minimum_height=card.setter("height"))
    header = BoxLayout(size_hint_y=None, height="36dp", spacing="8dp")
    header.add_widget(MDLabel(text=goal.name or "(unnamed)", bold=True))
    header.add_widget(MDIconButton(icon="pencil", size_hint_x=None, width="48dp",
                                   on_release=lambda _, i=idx: panel._dialog(i)))
    header.add_widget(MDIconButton(icon="delete", size_hint_x=None, width="48dp",
                                   on_release=lambda _, i=idx: panel._delete(i)))
    card.add_widget(header)
    if goal.display:
        card.add_widget(MDLabel(text=goal.display, theme_text_color="Hint",
                                size_hint_y=None, height="24dp"))
    logic_row = BoxLayout(size_hint_y=None, height="28dp", spacing="8dp")
    logic_row.add_widget(MDLabel(text="Logic:", size_hint_x=None, width="60dp",
                                 theme_text_color="Secondary"))
    logic_row.add_widget(MDLabel(text=goal.logic or "(always true)",
                                 theme_text_color="Secondary"))
    card.add_widget(logic_row)
    return card


class GoalsPanel(BoxLayout):
    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model
        self._dlg  = None
        self._list = None
        self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Goals", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Add Goal",
                                      size_hint_x=None, width="150dp",
                                      on_release=lambda _: self._dialog(None)))
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
        for i, g in enumerate(self.model.goals):
            self._list.add_widget(_make_card(g, i, self))

    def _delete(self, idx):
        self.model.goals.pop(idx)
        self._refresh()

    def _dialog(self, idx):
        editing = idx is not None
        obj = self.model.goals[idx] if editing else Goal()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="320dp", padding="8dp")
        name_f  = MDTextField(hint_text="name", mode="rectangle",
                              size_hint_y=None, height="56dp", text=obj.name)
        disp_f  = MDTextField(hint_text="display", mode="rectangle",
                              size_hint_y=None, height="56dp", text=obj.display)
        desc_f  = MDTextField(hint_text="description", mode="rectangle",
                              size_hint_y=None, height="56dp", text=obj.description)
        logic_f = MDTextField(hint_text="logic  e.g. (Item: Key) AND (Can Access: Zone)",
                              mode="rectangle", size_hint_y=None, height="56dp",
                              text=obj.logic)
        err_lbl = MDLabel(text="", theme_text_color="Error",
                          size_hint_y=None, height="24dp")
        logic_f.bind(text=lambda _, t: setattr(err_lbl, "text", _logic_err(t)))
        for w in (name_f, disp_f, desc_f, logic_f, err_lbl):
            content.add_widget(w)

        def _save(*_):
            if err_lbl.text:
                return
            obj.name = name_f.text.strip(); obj.display = disp_f.text.strip()
            obj.description = desc_f.text.strip(); obj.logic = logic_f.text.strip()
            if not editing:
                self.model.goals.append(obj)
            self._dlg.dismiss()
            self._refresh()

        self._dlg = MDDialog(
            title="Edit Goal" if editing else "Add Goal",
            type="custom", content_cls=content,
            buttons=[MDFlatButton(text="CANCEL",
                                  on_release=lambda *_: self._dlg.dismiss()),
                     MDRaisedButton(text="SAVE", on_release=_save)],
        )
        self._dlg.open()

    def flush(self):
        pass
