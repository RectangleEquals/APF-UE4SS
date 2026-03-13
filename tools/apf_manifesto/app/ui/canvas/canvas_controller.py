"""
ui/canvas/canvas_controller.py

Owns the authoritative block graph for one logic-canvas instance and provides:
  - Adding / removing / editing blocks
  - Wiring (connect child to AND/OR parent)
  - AST rebuild and logic-string serialisation
  - Undo / redo stack (snapshots of the block dict)
  - Notification callback whenever the logic string changes
"""
from __future__ import annotations
import copy
import uuid
from typing import Callable, Optional

from ...core.block_model import (
    LogicBlock, ast_to_blocks, blocks_to_logic_string,
)
from ...core.logic_parser import parse


class CanvasController:
    """
    Manages the block graph for a single logic canvas.
    `on_change(logic_str)` is called after every mutation.
    """

    MAX_UNDO = 50

    def __init__(
        self,
        mod_id: str,
        initial_logic: str = "",
        on_change: Optional[Callable[[str], None]] = None,
    ):
        self.mod_id    = mod_id
        self.on_change = on_change
        # blocks: dict[id → LogicBlock]
        self.blocks: dict[str, LogicBlock] = {}
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

        if initial_logic.strip():
            try:
                ast = parse(initial_logic)
                self.blocks = ast_to_blocks(ast, owner_mod_id=mod_id)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Block CRUD
    # ------------------------------------------------------------------

    def add_block(self, node_type: str, x: float = 100, y: float = 100, **kwargs) -> LogicBlock:
        """Create a new leaf block and add it to the graph."""
        blk = LogicBlock(
            id=str(uuid.uuid4()),
            node_type=node_type,
            owner_mod_id=self.mod_id,
            x=x, y=y,
            **kwargs,
        )
        self.snapshot()
        self.blocks[blk.id] = blk
        self._notify()
        return blk

    def remove_block(self, block_id: str):
        """Remove a block and detach it from any parent/children."""
        blk = self.blocks.pop(block_id, None)
        if blk is None:
            return
        self.snapshot()
        # Detach from parent
        if blk.parent_id and blk.parent_id in self.blocks:
            parent = self.blocks[blk.parent_id]
            if block_id in parent.children:
                parent.children.remove(block_id)
        # Orphan children
        for cid in list(blk.children):
            if cid in self.blocks:
                self.blocks[cid].parent_id = None
        self._notify()

    def update_block(self, block_id: str, **kwargs):
        """Update fields on a block (item_name, option_key, etc.)."""
        blk = self.blocks.get(block_id)
        if blk is None:
            return
        self.snapshot()
        for k, v in kwargs.items():
            if hasattr(blk, k):
                setattr(blk, k, v)
        self._notify()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def connect(self, parent_id: str, child_id: str):
        """Add child_id as a child of parent_id (parent must be AND/OR)."""
        parent = self.blocks.get(parent_id)
        child  = self.blocks.get(child_id)
        if parent is None or child is None:
            return
        if parent.node_type not in ("and", "or"):
            return
        if child_id in parent.children:
            return
        self.snapshot()
        # Remove child from its old parent
        if child.parent_id and child.parent_id in self.blocks:
            old_parent = self.blocks[child.parent_id]
            if child_id in old_parent.children:
                old_parent.children.remove(child_id)
        parent.children.append(child_id)
        child.parent_id = parent_id
        self._notify()

    def disconnect(self, parent_id: str, child_id: str):
        parent = self.blocks.get(parent_id)
        child  = self.blocks.get(child_id)
        if parent and child_id in parent.children:
            self.snapshot()
            parent.children.remove(child_id)
            child.parent_id = None
            self._notify()

    # ------------------------------------------------------------------
    # Logic string
    # ------------------------------------------------------------------

    def logic_string(self) -> str:
        return blocks_to_logic_string(self.blocks)

    def _notify(self):
        if self.on_change:
            self.on_change(self.logic_string())

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def snapshot(self):
        """Push a deep-copy of the current block graph onto the undo stack."""
        self._undo_stack.append(copy.deepcopy(self.blocks))
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self.blocks))
        self.blocks = self._undo_stack.pop()
        self._notify()

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self.blocks))
        self.blocks = self._redo_stack.pop()
        self._notify()
