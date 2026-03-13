"""
ui/canvas/logic_canvas.py

LogicCanvas — the primary drag-and-drop canvas widget.
"""
from __future__ import annotations
from typing import Callable, Optional

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivymd.uix.button import MDIconButton, MDFlatButton, MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.dialog import MDDialog

from .canvas_controller import CanvasController
from .connector import ConnectorLayer
from .logic_block import LogicBlockWidget, BLOCK_W, BLOCK_H
from ...core.block_model import LogicBlock


# ---------------------------------------------------------------------------
# Edit dialog
# ---------------------------------------------------------------------------

def _edit_dialog(blk: LogicBlock, controller: CanvasController, on_done: Callable):
    content = BoxLayout(orientation="vertical", spacing="8dp",
                        size_hint_y=None, height="280dp", padding="8dp")
    fields: dict[str, MDTextField] = {}

    def _field(hint, val):
        f = MDTextField(hint_text=hint, mode="rectangle",
                        size_hint_y=None, height="52dp", text=str(val))
        content.add_widget(f)
        return f

    if blk.node_type == "item":
        fields["item_name"]  = _field("Item name", blk.item_name)
        fields["item_count"] = _field("Count (default 1)", str(blk.item_count))
    elif blk.node_type == "can_access":
        fields["region_name"] = _field("Region name", blk.region_name)
    elif blk.node_type == "option":
        fields["option_key"]   = _field("Option key", blk.option_key)
        fields["option_op"]    = _field("Operator (== != > < >= <= or blank)", blk.option_op)
        fields["option_value"] = _field("Value (blank for toggle)", blk.option_value)
    elif blk.node_type == "const":
        fields["const_value"] = _field("Value (True / False)", str(blk.const_value))
    else:
        content.add_widget(MDLabel(text=f"{blk.node_type.upper()} — no editable params.",
                                   size_hint_y=None, height="40dp"))
    dlg = [None]

    def _save(*_):
        kwargs = {}
        for k, f in fields.items():
            v = f.text.strip()
            if k == "item_count":
                try: kwargs[k] = int(v)
                except ValueError: kwargs[k] = 1
            elif k == "const_value":
                kwargs[k] = v.lower() == "true"
            else:
                kwargs[k] = v
        controller.update_block(blk.id, **kwargs)
        dlg[0].dismiss()
        on_done()

    dlg[0] = MDDialog(
        title=f"Edit {blk.node_type.replace('_', ' ').title()} Block",
        type="custom", content_cls=content,
        buttons=[MDFlatButton(text="CANCEL", on_release=lambda *_: dlg[0].dismiss()),
                 MDRaisedButton(text="SAVE", on_release=_save)],
    )
    dlg[0].open()


# ---------------------------------------------------------------------------
# Inner canvas surface
# ---------------------------------------------------------------------------

class _CanvasSurface(Widget):
    def __init__(self, controller: CanvasController, own_mod_id: str, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(2000), dp(1600)), **kwargs)
        self._controller  = controller
        self._own_mod_id  = own_mod_id
        self._block_widgets: dict[str, LogicBlockWidget] = {}
        self._connector   = ConnectorLayer(self)

        with self.canvas.before:
            Color(0.10, 0.10, 0.12, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)
        self._sync_widgets()

    def _redraw_bg(self, *_):
        self._bg.pos  = self.pos
        self._bg.size = self.size

    def _sync_widgets(self):
        for bid in list(self._block_widgets):
            if bid not in self._controller.blocks:
                self.remove_widget(self._block_widgets.pop(bid))
        for bid, blk in self._controller.blocks.items():
            if bid not in self._block_widgets:
                w = LogicBlockWidget(blk, self._own_mod_id,
                                     on_edit=self._on_edit,
                                     on_delete=self._on_delete,
                                     pos=(blk.x, blk.y))
                self._block_widgets[bid] = w
                self.add_widget(w)
            else:
                w = self._block_widgets[bid]
                w.pos = (blk.x, blk.y)
                w.update_label()
        self.redraw_connectors()

    def redraw_connectors(self):
        self._connector.redraw(self._controller.blocks, self._block_widgets)

    def _on_edit(self, blk_widget: LogicBlockWidget):
        if blk_widget.block.owner_mod_id != self._own_mod_id:
            return
        _edit_dialog(blk_widget.block, self._controller,
                     on_done=lambda: (blk_widget.update_label(),
                                      self.redraw_connectors()))

    def _on_delete(self, blk_widget: LogicBlockWidget):
        if blk_widget.block.owner_mod_id != self._own_mod_id:
            return
        self._controller.remove_block(blk_widget.block.id)
        self._sync_widgets()

    def add_dropped_block(self, node_type: str, x: float, y: float, **kwargs):
        blk = self._controller.add_block(node_type, x=x, y=y, **kwargs)
        w = LogicBlockWidget(blk, self._own_mod_id,
                             on_edit=self._on_edit,
                             on_delete=self._on_delete,
                             pos=(blk.x, blk.y))
        self._block_widgets[blk.id] = w
        self.add_widget(w)
        self.redraw_connectors()


# ---------------------------------------------------------------------------
# Public LogicCanvas
# ---------------------------------------------------------------------------

class LogicCanvas(BoxLayout):
    """
    Full canvas widget: toolbar + drawing surface + logic preview bar.
    Embed this in any panel that needs a logic editor.
    """

    def __init__(self, mod_id: str, initial_logic: str = "",
                 on_change: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(orientation="vertical", spacing="4dp",
                         padding="0dp", **kwargs)
        self._mod_id    = mod_id
        self._on_change = on_change
        self._controller = CanvasController(
            mod_id=mod_id,
            initial_logic=initial_logic,
            on_change=self._on_logic_changed,
        )
        self._build()

    def _build(self):
        # Toolbar — tooltip_text is NOT supported in KivyMD 1.2.0
        toolbar = BoxLayout(size_hint_y=None, height="44dp", spacing="4dp",
                            padding=("4dp", "2dp"))
        toolbar.add_widget(MDIconButton(icon="undo",
                                        on_release=lambda _: self._undo()))
        toolbar.add_widget(MDIconButton(icon="redo",
                                        on_release=lambda _: self._redo()))
        toolbar.add_widget(MDIconButton(icon="trash-can-outline",
                                        on_release=lambda _: self._clear()))
        toolbar.add_widget(Widget())
        self.add_widget(toolbar)

        self._surface = _CanvasSurface(self._controller, self._mod_id)
        scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        scroll.add_widget(self._surface)
        self.add_widget(scroll)

        preview_row = BoxLayout(size_hint_y=None, height="44dp",
                                spacing="8dp", padding=("8dp", "4dp"))
        preview_row.add_widget(MDLabel(text="Logic:", size_hint_x=None,
                                       width="60dp", theme_text_color="Secondary"))
        self._preview = MDLabel(
            text=self._controller.logic_string() or "(empty — always True)",
            theme_text_color="Hint",
        )
        preview_row.add_widget(self._preview)
        self.add_widget(preview_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def drop_block(self, node_type: str, x: float = 200, y: float = 200, **kwargs):
        sx, sy = self._surface.to_widget(x, y, relative=False)
        self._surface.add_dropped_block(node_type, sx, sy, **kwargs)

    def logic_string(self) -> str:
        return self._controller.logic_string()

    def _undo(self):
        self._controller.undo()
        self._surface._sync_widgets()

    def _redo(self):
        self._controller.redo()
        self._surface._sync_widgets()

    def _clear(self):
        self._controller.snapshot()
        self._controller.blocks.clear()
        self._surface._sync_widgets()
        self._on_logic_changed("")

    def _on_logic_changed(self, logic_str: str):
        if hasattr(self, "_preview"):
            self._preview.text = logic_str or "(empty — always True)"
        if self._on_change:
            self._on_change(logic_str)
