"""
ui/panels/goals_panel.py

Goals editor.  Each goal gets:
  - Name / display / description fields
  - A LogicCanvas + PalettePanel for the goal's logic

The "Edit Goal" dialog was replaced with an inline expand-on-click
detail view so the canvas has room to breathe.
"""
from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from ...core.manifest_model import Goal, ManifestModel
from ...core.mod_registry import ModRegistry


class GoalsPanel(BoxLayout):
    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model    = model
        self.registry = registry
        self._dlg     = None
        self._list    = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Goals", font_style="H6"))
        top.add_widget(MDRaisedButton(
            text="+ Add Goal", size_hint_x=None, width="150dp",
            on_release=lambda _: self._open_goal_dialog(None),
        ))
        self.add_widget(top)

        scroll = ScrollView()
        self._list = BoxLayout(orientation="vertical", spacing="10dp",
                               padding="4dp", size_hint_y=None)
        self._list.bind(minimum_height=self._list.setter("height"))
        scroll.add_widget(self._list)
        self.add_widget(scroll)
        self._refresh()

    # ------------------------------------------------------------------
    def _refresh(self):
        self._list.clear_widgets()
        for i, goal in enumerate(self.model.goals):
            self._list.add_widget(self._make_card(goal, i))

    def _make_card(self, goal: Goal, idx: int) -> MDCard:
        card = MDCard(orientation="vertical", padding="12dp", spacing="4dp",
                      size_hint_y=None, elevation=2, radius=[8])
        card.bind(minimum_height=card.setter("height"))

        header = BoxLayout(size_hint_y=None, height="36dp", spacing="8dp")
        header.add_widget(MDLabel(text=goal.name or "(unnamed)", bold=True))
        header.add_widget(MDIconButton(
            icon="pencil", size_hint_x=None, width="48dp",
            on_release=lambda _, i=idx: self._open_goal_dialog(i),
        ))
        header.add_widget(MDIconButton(
            icon="delete", size_hint_x=None, width="48dp",
            on_release=lambda _, i=idx: self._delete(i),
        ))
        card.add_widget(header)

        if goal.display:
            card.add_widget(MDLabel(text=goal.display, theme_text_color="Hint",
                                    size_hint_y=None, height="24dp"))

        logic_row = BoxLayout(size_hint_y=None, height="28dp", spacing="8dp")
        logic_row.add_widget(MDLabel(text="Logic:", size_hint_x=None,
                                     width="60dp", theme_text_color="Secondary"))
        logic_row.add_widget(MDLabel(
            text=goal.logic or "(always true)",
            theme_text_color="Secondary",
        ))
        card.add_widget(logic_row)
        return card

    def _delete(self, idx: int):
        self.model.goals.pop(idx)
        self._refresh()

    # ------------------------------------------------------------------
    def _open_goal_dialog(self, idx):
        """
        Full-height dialog with text fields + embedded LogicCanvas + PalettePanel.
        """
        from ..canvas.logic_canvas import LogicCanvas
        from .palette_panel import PalettePanel

        editing = idx is not None
        goal    = self.model.goals[idx] if editing else Goal()

        name_f = MDTextField(hint_text="name", mode="rectangle",
                             size_hint_y=None, height="52dp", text=goal.name)
        disp_f = MDTextField(hint_text="display", mode="rectangle",
                             size_hint_y=None, height="52dp", text=goal.display)
        desc_f = MDTextField(hint_text="description", mode="rectangle",
                             size_hint_y=None, height="52dp", text=goal.description)

        logic_str = [goal.logic]

        canvas_widget = LogicCanvas(
            mod_id=self.model.mod_id,
            initial_logic=goal.logic,
            on_change=lambda s: logic_str.__setitem__(0, s),
            size_hint=(1, None),
            height=dp(340),
        )
        # Do NOT pass width= or size_hint= — PalettePanel sets its own width
        palette = PalettePanel(
            model=self.model,
            registry=self.registry,
            canvas=canvas_widget,
            scope="region",
        )
        palette.height = dp(340)

        canvas_row = BoxLayout(size_hint_y=None, height=dp(340), spacing=dp(4))
        canvas_row.add_widget(palette)
        canvas_row.add_widget(canvas_widget)

        content = BoxLayout(
            orientation="vertical", spacing="8dp", padding="8dp",
            size_hint_y=None, height=dp(560),
        )
        for w in (name_f, disp_f, desc_f, canvas_row):
            content.add_widget(w)

        dlg = [None]

        def _save(*_):
            goal.name        = name_f.text.strip()
            goal.display     = disp_f.text.strip()
            goal.description = desc_f.text.strip()
            goal.logic       = logic_str[0]
            if not editing:
                self.model.goals.append(goal)
            dlg[0].dismiss()
            self._refresh()

        dlg[0] = MDDialog(
            title="Edit Goal" if editing else "Add Goal",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="CANCEL",
                             on_release=lambda *_: dlg[0].dismiss()),
                MDRaisedButton(text="SAVE", on_release=_save),
            ],
        )
        dlg[0].open()

    def flush(self):
        pass
