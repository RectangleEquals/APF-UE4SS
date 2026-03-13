"""
ui/canvas/connector.py

Draws Bézier connector wires between blocks on the logic canvas.
Rendered directly onto the parent widget's canvas.before layer so
they always appear beneath block widgets.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from kivy.graphics import Color, Line
from kivy.metrics import dp

if TYPE_CHECKING:
    from .logic_block import LogicBlockWidget


def _bezier_points(x0, y0, x1, y1, steps=20):
    """
    Return a flat list of (x, y) ... for a cubic Bézier curve
    from (x0,y0) to (x1,y1) with horizontal control handles.
    """
    cx0 = x0 + (x1 - x0) * 0.5
    cy0 = y0
    cx1 = x0 + (x1 - x0) * 0.5
    cy1 = y1
    pts = []
    for i in range(steps + 1):
        t  = i / steps
        t2 = t * t
        t3 = t2 * t
        mt  = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        x = mt3 * x0 + 3 * mt2 * t * cx0 + 3 * mt * t2 * cx1 + t3 * x1
        y = mt3 * y0 + 3 * mt2 * t * cy0 + 3 * mt * t2 * cy1 + t3 * y1
        pts.extend([x, y])
    return pts


class ConnectorLayer:
    """
    Manages all connector wires for a canvas widget.
    Call `redraw(blocks_dict, block_widgets)` whenever the layout changes.
    """

    def __init__(self, canvas_widget):
        """
        canvas_widget: the Kivy Widget whose canvas.before we draw on.
        """
        self._widget = canvas_widget
        self._instr  = []   # kivy graphics instructions added

    def clear(self):
        for instr in self._instr:
            try:
                self._widget.canvas.before.remove(instr)
            except Exception:
                pass
        self._instr.clear()

    def redraw(self, blocks: dict, block_widgets: dict):
        """
        blocks       : dict[id, LogicBlock]
        block_widgets: dict[id, LogicBlockWidget]
        """
        self.clear()
        with self._widget.canvas.before:
            for bid, blk in blocks.items():
                if not blk.children:
                    continue
                parent_w = block_widgets.get(bid)
                if parent_w is None:
                    continue
                # Output port: right-centre of parent block
                ox = parent_w.x + parent_w.width
                oy = parent_w.y + parent_w.height * 0.5
                for cid in blk.children:
                    child_w = block_widgets.get(cid)
                    if child_w is None:
                        continue
                    # Input port: left-centre of child block
                    ix = child_w.x
                    iy = child_w.y + child_w.height * 0.5
                    ci = Color(0.7, 0.7, 0.7, 0.85)
                    pts = _bezier_points(ox, oy, ix, iy)
                    li = Line(points=pts, width=dp(1.5))
                    self._instr.extend([ci, li])
