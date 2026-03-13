"""
ui/canvas/logic_block.py

A single draggable block widget on the logic canvas.
Each block visualises one LogicBlock dataclass and handles:
  - Rounded-rect drawing with type colour
  - Drag repositioning
  - Click-to-edit (opens param popover)
  - Right-click to delete
  - Foreign-block hatch overlay + arrow button
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Optional

from kivy.graphics import Color, RoundedRectangle, Line
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivymd.uix.button import MDIconButton
from kivy.clock import Clock
from kivy.metrics import dp

if TYPE_CHECKING:
    from ...core.block_model import LogicBlock

BLOCK_W = dp(200)
BLOCK_H = dp(60)
RADIUS  = [dp(10)]


class LogicBlockWidget(Widget):
    """Visual representation of one LogicBlock on the canvas."""

    def __init__(
        self,
        block: "LogicBlock",
        own_mod_id: str,
        on_edit: Callable[["LogicBlockWidget"], None],
        on_delete: Callable[["LogicBlockWidget"], None],
        on_open_foreign: Optional[Callable[["LogicBlockWidget"], None]] = None,
        **kwargs,
    ):
        super().__init__(size_hint=(None, None),
                         size=(BLOCK_W, BLOCK_H), **kwargs)
        self.block          = block
        self._own_mod_id    = own_mod_id
        self._on_edit       = on_edit
        self._on_delete     = on_delete
        self._on_open_foreign = on_open_foreign
        self._dragging      = False
        self._drag_offset   = (0, 0)

        self._build()
        self.bind(pos=self._redraw, size=self._redraw)

    # ------------------------------------------------------------------

    def _build(self):
        self.canvas.before.clear()
        with self.canvas.before:
            r, g, b, a = self.block.color()
            self._bg_color_inst = Color(r, g, b, a)
            self._bg_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=RADIUS
            )
            # Foreign hatch overlay
            if self.block.owner_mod_id and self.block.owner_mod_id != self._own_mod_id:
                Color(0, 0, 0, 0.25)
                self._hatch_rect = RoundedRectangle(
                    pos=self.pos, size=self.size, radius=RADIUS
                )
            # Selection outline (initially invisible)
            Color(1, 1, 1, 0)
            self._sel_color = self.canvas.before.children[-1]
            Line(rounded_rectangle=(
                self.x, self.y, self.width, self.height, dp(10)
            ), width=2)

        # Label
        self._label = Label(
            text=self.block.label(),
            color=(1, 1, 1, 1),
            font_size=dp(12),
            bold=True,
            halign="center",
            valign="middle",
        )
        self._label.bind(size=self._label.setter("text_size"))
        self.add_widget(self._label)

        # Foreign arrow button
        if self.block.owner_mod_id and self.block.owner_mod_id != self._own_mod_id:
            btn = MDIconButton(
                icon="arrow-top-right",
                size_hint=(None, None),
                size=(dp(28), dp(28)),
                on_release=lambda _: self._on_open_foreign(self) if self._on_open_foreign else None,
            )
            btn.pos = (self.x + self.width - dp(30), self.y + self.height - dp(30))
            self.add_widget(btn)

    def _redraw(self, *_):
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos  = self.pos
            self._bg_rect.size = self.size
        if hasattr(self, "_hatch_rect"):
            self._hatch_rect.pos  = self.pos
            self._hatch_rect.size = self.size
        # Update label bounds
        self._label.pos  = self.pos
        self._label.size = self.size
        # Reposition foreign arrow if present
        for child in self.children:
            if isinstance(child, MDIconButton):
                child.pos = (self.x + self.width - dp(30), self.y + self.height - dp(30))

    def update_label(self):
        """Call after editing block data to refresh display."""
        self._label.text = self.block.label()

    # ------------------------------------------------------------------
    # Touch / drag

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        # Right-click → delete
        if touch.button == "right":
            self._on_delete(self)
            return True
        touch.grab(self)
        self._dragging     = True
        self._drag_offset  = (self.x - touch.x, self.y - touch.y)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if self._dragging:
            self.x = touch.x + self._drag_offset[0]
            self.y = touch.y + self._drag_offset[1]
            self.block.x = self.x
            self.block.y = self.y
            # Notify canvas to redraw connectors
            if hasattr(self.parent, "redraw_connectors"):
                self.parent.redraw_connectors()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        was_dragging = self._dragging
        self._dragging = False
        if not was_dragging:
            return False
        # If barely moved, treat as click-to-edit
        dx = abs(self.x - (touch.x + self._drag_offset[0]))
        dy = abs(self.y - (touch.y + self._drag_offset[1]))
        if dx < dp(5) and dy < dp(5):
            self._on_edit(self)
        if hasattr(self.parent, "_controller"):
            self.parent._controller.snapshot()
        return True
