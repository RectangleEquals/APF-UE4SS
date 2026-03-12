"""
ui/panels/capabilities_panel.py

Sub-panel for Capabilities: Regions | Locations | Items | Overrides.
Uses a manual tab-button bar instead of MDTabs to avoid KV factory issues.
"""
from __future__ import annotations
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.stacklayout import StackLayout
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton, MDTextButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from ...core.manifest_model import (
    ManifestModel, RegionDef, LocationDef, ItemDef,
    ItemOverride, LocationOverride,
)
from ...core.mod_registry import ModRegistry
from ...core.logic_parser import parse, validate_scope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _logic_err(text, entry_type):
    if not text.strip():
        return ""
    try:
        node = parse(text)
        errs = validate_scope(node, entry_type)
        return "; ".join(errs) if errs else ""
    except ValueError as e:
        return str(e)


def _scroll_list():
    scroll = ScrollView()
    lst = BoxLayout(orientation="vertical", spacing="10dp",
                    padding="4dp", size_hint_y=None)
    lst.bind(minimum_height=lst.setter("height"))
    scroll.add_widget(lst)
    return scroll, lst


def _entry_card(primary, secondary, on_edit, on_delete):
    card = MDCard(orientation="horizontal", padding="10dp", spacing="8dp",
                  size_hint_y=None, height="72dp", elevation=2, radius=[8])
    info = BoxLayout(orientation="vertical")
    info.add_widget(MDLabel(text=primary, bold=True,
                            size_hint_y=None, height="30dp"))
    info.add_widget(MDLabel(text=secondary or "(no logic)",
                            theme_text_color="Hint",
                            size_hint_y=None, height="22dp"))
    card.add_widget(info)
    card.add_widget(MDIconButton(icon="pencil", on_release=on_edit,
                                 size_hint_x=None, width="48dp"))
    card.add_widget(MDIconButton(icon="delete", on_release=on_delete,
                                 size_hint_x=None, width="48dp"))
    return card


def _lf(hint, text=""):
    return MDTextField(hint_text=hint, helper_text="APF logic expression",
                       helper_text_mode="on_focus", mode="rectangle",
                       size_hint_y=None, height="56dp", text=text)


def _dialog(title, content, on_save, dlg_holder):
    dlg = MDDialog(
        title=title, type="custom", content_cls=content,
        buttons=[MDFlatButton(text="CANCEL",
                              on_release=lambda *_: dlg.dismiss()),
                 MDRaisedButton(text="SAVE", on_release=on_save)],
    )
    dlg_holder[0] = dlg
    dlg.open()


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

class _RegionsPanel(BoxLayout):
    def __init__(self, model, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model; self._dlg = [None]; self._list = None; self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Regions", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Add Region", size_hint_x=None,
                                      width="160dp",
                                      on_release=lambda _: self._show(None)))
        self.add_widget(top)
        s, self._list = _scroll_list(); self.add_widget(s); self._refresh()

    def _refresh(self):
        self._list.clear_widgets()
        for i, r in enumerate(self.model.capabilities.regions):
            self._list.add_widget(_entry_card(
                r.name, r.logic,
                on_edit=lambda _, i=i: self._show(i),
                on_delete=lambda _, i=i: (
                    self.model.capabilities.regions.pop(i), self._refresh()),
            ))

    def _show(self, idx):
        editing = idx is not None
        obj = self.model.capabilities.regions[idx] if editing else RegionDef()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="180dp", padding="8dp")
        nf = MDTextField(hint_text="region name", mode="rectangle",
                         size_hint_y=None, height="56dp", text=obj.name)
        lf = _lf("logic  (optional)", obj.logic)
        el = MDLabel(text="", theme_text_color="Error",
                     size_hint_y=None, height="24dp")
        lf.bind(text=lambda _, t: setattr(el, "text", _logic_err(t, "region")))
        content.add_widget(nf); content.add_widget(lf); content.add_widget(el)

        def _save(*_):
            if el.text: return
            obj.name = nf.text.strip(); obj.logic = lf.text.strip()
            if not editing: self.model.capabilities.regions.append(obj)
            self._dlg[0].dismiss(); self._refresh()

        _dialog("Edit Region" if editing else "Add Region",
                content, _save, self._dlg)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

class _LocationsPanel(BoxLayout):
    def __init__(self, model, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model; self._dlg = [None]; self._list = None; self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Locations", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Add Location", size_hint_x=None,
                                      width="170dp",
                                      on_release=lambda _: self._show(None)))
        self.add_widget(top)
        s, self._list = _scroll_list(); self.add_widget(s); self._refresh()

    def _refresh(self):
        self._list.clear_widgets()
        for i, lc in enumerate(self.model.capabilities.locations):
            self._list.add_widget(_entry_card(
                lc.name, lc.logic,
                on_edit=lambda _, i=i: self._show(i),
                on_delete=lambda _, i=i: (
                    self.model.capabilities.locations.pop(i), self._refresh()),
            ))

    def _show(self, idx):
        editing = idx is not None
        obj = self.model.capabilities.locations[idx] if editing else LocationDef()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="240dp", padding="8dp")
        nf = MDTextField(hint_text="location name", mode="rectangle",
                         size_hint_y=None, height="56dp", text=obj.name)
        lf = _lf("logic  (optional)", obj.logic)
        af = MDTextField(hint_text="amount (default 1)", mode="rectangle",
                         size_hint_y=None, height="56dp",
                         input_filter="int", text=str(obj.amount))
        el = MDLabel(text="", theme_text_color="Error",
                     size_hint_y=None, height="24dp")
        lf.bind(text=lambda _, t: setattr(el, "text", _logic_err(t, "location")))
        for w in (nf, lf, af, el): content.add_widget(w)

        def _save(*_):
            if el.text: return
            obj.name = nf.text.strip(); obj.logic = lf.text.strip()
            obj.amount = int(af.text or "1")
            if not editing: self.model.capabilities.locations.append(obj)
            self._dlg[0].dismiss(); self._refresh()

        _dialog("Edit Location" if editing else "Add Location",
                content, _save, self._dlg)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

_ITEM_TYPES = ["progression", "useful", "filler", "trap"]
_ITEM_COLORS = {"progression": [0.29,0.56,0.89,1], "useful": [0.48,0.76,0.47,1],
                "filler": [0.70,0.70,0.70,1], "trap": [0.90,0.30,0.30,1]}


class _ItemsPanel(BoxLayout):
    def __init__(self, model, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model; self._dlg = [None]; self._list = None; self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Items", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Add Item", size_hint_x=None,
                                      width="140dp",
                                      on_release=lambda _: self._show(None)))
        self.add_widget(top)
        s, self._list = _scroll_list(); self.add_widget(s); self._refresh()

    def _refresh(self):
        self._list.clear_widgets()
        for i, it in enumerate(self.model.capabilities.items):
            tc = _ITEM_COLORS.get(it.type, [1, 1, 1, 1])
            card = MDCard(orientation="horizontal", padding="10dp", spacing="8dp",
                          size_hint_y=None, height="64dp", elevation=2, radius=[8])
            card.add_widget(MDLabel(text=it.type, theme_text_color="Custom",
                                    text_color=tc, bold=True,
                                    size_hint_x=None, width="120dp"))
            info = BoxLayout(orientation="vertical")
            info.add_widget(MDLabel(text=it.name, bold=True,
                                    size_hint_y=None, height="28dp"))
            info.add_widget(MDLabel(
                text=f"x{it.amount}  {it.logic or '(no gate)'}",
                theme_text_color="Hint", size_hint_y=None, height="22dp"))
            card.add_widget(info)
            card.add_widget(MDIconButton(icon="pencil", size_hint_x=None, width="48dp",
                                         on_release=lambda _, i=i: self._show(i)))
            card.add_widget(MDIconButton(icon="delete", size_hint_x=None, width="48dp",
                                         on_release=lambda _, i=i: (
                                             self.model.capabilities.items.pop(i),
                                             self._refresh())))
            self._list.add_widget(card)

    def _show(self, idx):
        editing = idx is not None
        obj = self.model.capabilities.items[idx] if editing else ItemDef()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="340dp", padding="8dp")
        nf = MDTextField(hint_text="item name", mode="rectangle",
                         size_hint_y=None, height="56dp", text=obj.name)
        tf = MDTextField(hint_text="type: progression | useful | filler | trap",
                         mode="rectangle", size_hint_y=None, height="56dp",
                         text=obj.type)
        af = MDTextField(hint_text="amount  (-1 = fill slots)", mode="rectangle",
                         size_hint_y=None, height="56dp",
                         input_filter="int", text=str(obj.amount))
        lf = _lf("logic (option-only gate)", obj.logic)
        acf = MDTextField(hint_text="action  e.g. MyMod.Grant  (optional)",
                          mode="rectangle", size_hint_y=None, height="56dp",
                          text=obj.action or "")
        el = MDLabel(text="", theme_text_color="Error",
                     size_hint_y=None, height="24dp")
        lf.bind(text=lambda _, t: setattr(el, "text", _logic_err(t, "item")))
        for w in (nf, tf, af, lf, acf, el): content.add_widget(w)

        def _save(*_):
            if el.text: return
            t = tf.text.strip().lower()
            if t not in _ITEM_TYPES: tf.error = True; return
            obj.name = nf.text.strip(); obj.type = t
            obj.amount = int(af.text or "1")
            obj.logic = lf.text.strip(); obj.action = acf.text.strip() or None
            if not editing: self.model.capabilities.items.append(obj)
            self._dlg[0].dismiss(); self._refresh()

        _dialog("Edit Item" if editing else "Add Item", content, _save, self._dlg)


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

class _OverridesPanel(BoxLayout):
    def __init__(self, model, **kwargs):
        super().__init__(orientation="vertical", padding="16dp",
                         spacing="8dp", **kwargs)
        self.model = model; self._dlg = [None]; self._list = None; self._build()

    def _build(self):
        top = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        top.add_widget(MDLabel(text="Overrides", font_style="H6"))
        top.add_widget(MDRaisedButton(text="+ Item Ov.", size_hint_x=None,
                                      width="130dp",
                                      on_release=lambda _: self._item_dlg(None)))
        top.add_widget(MDRaisedButton(text="+ Loc. Ov.", size_hint_x=None,
                                      width="130dp",
                                      on_release=lambda _: self._loc_dlg(None)))
        self.add_widget(top)
        s, self._list = _scroll_list(); self.add_widget(s); self._refresh()

    def _refresh(self):
        self._list.clear_widgets()
        ov = self.model.capabilities.overrides
        for i, o in enumerate(ov.items):
            self._list.add_widget(_entry_card(
                f"[Item] {o.target_item}  \u2192  {o.type}",
                f"mod: {o.target_mod}  |  {o.logic or '(always)'}",
                on_edit=lambda _, i=i: self._item_dlg(i),
                on_delete=lambda _, i=i: (ov.items.pop(i), self._refresh()),
            ))
        for i, o in enumerate(ov.locations):
            self._list.add_widget(_entry_card(
                f"[Loc] {o.name}",
                f"mod: {o.target_mod}  |  {o.logic or '(always)'}",
                on_edit=lambda _, i=i: self._loc_dlg(i),
                on_delete=lambda _, i=i: (ov.locations.pop(i), self._refresh()),
            ))

    def _item_dlg(self, idx):
        ov = self.model.capabilities.overrides
        editing = idx is not None
        obj = ov.items[idx] if editing else ItemOverride()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="300dp", padding="8dp")
        itmf = MDTextField(hint_text="target_item", mode="rectangle",
                           size_hint_y=None, height="56dp", text=obj.target_item)
        modf = MDTextField(hint_text="target_mod (mod_id)", mode="rectangle",
                           size_hint_y=None, height="56dp", text=obj.target_mod)
        typf = MDTextField(hint_text="new type: progression|useful|filler|trap",
                           mode="rectangle", size_hint_y=None, height="56dp",
                           text=obj.type)
        lf   = _lf("logic (option-only)", obj.logic)
        el   = MDLabel(text="", theme_text_color="Error",
                       size_hint_y=None, height="24dp")
        lf.bind(text=lambda _, t: setattr(el, "text",
                                          _logic_err(t, "item_override")))
        for w in (itmf, modf, typf, lf, el): content.add_widget(w)

        def _save(*_):
            if el.text: return
            obj.target_item = itmf.text.strip(); obj.target_mod = modf.text.strip()
            obj.type = typf.text.strip().lower(); obj.logic = lf.text.strip()
            if not editing: ov.items.append(obj)
            self._dlg[0].dismiss(); self._refresh()

        _dialog("Edit Item Override" if editing else "Add Item Override",
                content, _save, self._dlg)

    def _loc_dlg(self, idx):
        ov = self.model.capabilities.overrides
        editing = idx is not None
        obj = ov.locations[idx] if editing else LocationOverride()
        content = BoxLayout(orientation="vertical", spacing="10dp",
                            size_hint_y=None, height="240dp", padding="8dp")
        nf   = MDTextField(hint_text="location name (from other mod)",
                           mode="rectangle", size_hint_y=None, height="56dp",
                           text=obj.name)
        modf = MDTextField(hint_text="target_mod (mod_id)", mode="rectangle",
                           size_hint_y=None, height="56dp", text=obj.target_mod)
        lf   = _lf("logic (OR-merged with existing)", obj.logic)
        el   = MDLabel(text="", theme_text_color="Error",
                       size_hint_y=None, height="24dp")
        lf.bind(text=lambda _, t: setattr(el, "text", _logic_err(t, "location")))
        for w in (nf, modf, lf, el): content.add_widget(w)

        def _save(*_):
            if el.text: return
            obj.name = nf.text.strip(); obj.target_mod = modf.text.strip()
            obj.logic = lf.text.strip()
            if not editing: ov.locations.append(obj)
            self._dlg[0].dismiss(); self._refresh()

        _dialog("Edit Loc Override" if editing else "Add Loc Override",
                content, _save, self._dlg)


# ---------------------------------------------------------------------------
# Root CapabilitiesPanel -- manual tab-bar (avoids MDTabs KV issues)
# ---------------------------------------------------------------------------

class CapabilitiesPanel(BoxLayout):
    def __init__(self, model: ManifestModel, registry: ModRegistry, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.model    = model
        self.registry = registry
        self._sub     = {}
        self._active  = None
        self._content = None
        self._build()

    def _build(self):
        # Tab button bar
        tab_bar = BoxLayout(size_hint_y=None, height="48dp", spacing="4dp",
                            padding=["4dp", "4dp", "4dp", "0dp"])
        self._tab_btns = {}
        for label in ("Regions", "Locations", "Items", "Overrides"):
            btn = MDRaisedButton(text=label, on_release=lambda _, l=label: self._switch(l))
            tab_bar.add_widget(btn)
            self._tab_btns[label] = btn
        self.add_widget(tab_bar)

        # Content area — one panel per tab, swap visibility
        self._content = BoxLayout()
        self.add_widget(self._content)

        cls_map = {
            "Regions":   _RegionsPanel,
            "Locations": _LocationsPanel,
            "Items":     _ItemsPanel,
            "Overrides": _OverridesPanel,
        }
        for label, Cls in cls_map.items():
            panel = Cls(model=self.model, size_hint=(1, 1))
            self._sub[label] = panel

        self._switch("Regions")

    def _switch(self, label):
        self._content.clear_widgets()
        self._content.add_widget(self._sub[label])
        self._active = label

    def flush(self):
        pass

    def on_show(self):
        pass
