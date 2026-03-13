"""
core/block_model.py

LogicBlock dataclass (the canvas counterpart to AST nodes)
and AST <-> block graph conversion utilities.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .logic_parser import (
    ASTNode, AndNode, OrNode, ItemNode,
    CanAccessNode, OptionNode, ConstNode,
    serialize,
)


# ---------------------------------------------------------------------------
# Block dataclass
# ---------------------------------------------------------------------------

@dataclass
class LogicBlock:
    """A single draggable block on the logic canvas."""
    id: str
    node_type: str          # "item"|"can_access"|"option"|"const"|"and"|"or"

    # Leaf payloads
    item_name:    str = ""
    item_count:   int = 1
    region_name:  str = ""
    option_key:   str = ""
    option_op:    str = ""   # "=="|"!="|">"|"<"|">="|"<="  or "" for toggle
    option_value: str = ""
    const_value:  bool = True

    # Ownership (which mod declared the underlying entity)
    owner_mod_id: str = ""

    # Canvas position (cosmetic only – not persisted to manifest)
    x: float = 0.0
    y: float = 0.0

    # Wiring: AND/OR node children, leaf node parent
    children:  list[str]    = field(default_factory=list)   # child block IDs
    parent_id: Optional[str] = None

    # -----------------------------------------------------------------------

    def label(self) -> str:
        """Human-readable label shown on the block face."""
        if self.node_type == "item":
            suffix = f" ×{self.item_count}" if self.item_count != 1 else ""
            return f"Item: {self.item_name or '?'}{suffix}"
        if self.node_type == "can_access":
            return f"Can Access: {self.region_name or '?'}"
        if self.node_type == "option":
            if self.option_op:
                return f"Option: {self.option_key} {self.option_op} {self.option_value}"
            return f"Option: {self.option_key or '?'}"
        if self.node_type == "const":
            return "True" if self.const_value else "False"
        if self.node_type == "and":
            return "AND"
        if self.node_type == "or":
            return "OR"
        return self.node_type

    def color(self) -> list:
        """RGBA color for this block type."""
        return _BLOCK_COLORS.get(self.node_type, [0.5, 0.5, 0.5, 1])


_BLOCK_COLORS = {
    "item":      [0.29, 0.56, 0.89, 1],   # #4A90E2 blue
    "can_access":[0.48, 0.41, 0.93, 1],   # #7B68EE violet
    "option":    [0.96, 0.65, 0.14, 1],   # #F5A623 amber
    "const":     [0.36, 0.72, 0.36, 1],   # #5CB85C green (True) – False overrides below
    "and":       [0.18, 0.25, 0.34, 1],   # #2E4057 dark slate
    "or":        [0.43, 0.36, 0.59, 1],   # #6D5B97 purple
}


# ---------------------------------------------------------------------------
# AST  →  flat block dict
# ---------------------------------------------------------------------------

def _mk(node_type: str, **kwargs) -> LogicBlock:
    return LogicBlock(id=str(uuid.uuid4()), node_type=node_type, **kwargs)


def ast_to_blocks(
    node: ASTNode,
    owner_mod_id: str = "",
    parent_id: Optional[str] = None,
    blocks: Optional[dict[str, LogicBlock]] = None,
    x: float = 0.0,
    y: float = 0.0,
    x_step: float = 220.0,
    y_step: float = 90.0,
) -> dict[str, LogicBlock]:
    """
    Recursively convert an ASTNode tree to a flat {id: LogicBlock} dict.
    Computes a simple left-to-right tree layout.
    """
    if blocks is None:
        blocks = {}

    if isinstance(node, ItemNode):
        b = _mk("item", item_name=node.name, item_count=node.count,
                owner_mod_id=owner_mod_id, x=x, y=y, parent_id=parent_id)
    elif isinstance(node, CanAccessNode):
        b = _mk("can_access", region_name=node.region,
                owner_mod_id=owner_mod_id, x=x, y=y, parent_id=parent_id)
    elif isinstance(node, OptionNode):
        b = _mk("option", option_key=node.key,
                option_op=node.op or "", option_value=node.value or "",
                owner_mod_id=owner_mod_id, x=x, y=y, parent_id=parent_id)
    elif isinstance(node, ConstNode):
        b = _mk("const", const_value=node.value,
                owner_mod_id=owner_mod_id, x=x, y=y, parent_id=parent_id)
    elif isinstance(node, (AndNode, OrNode)):
        ntype = "and" if isinstance(node, AndNode) else "or"
        b = _mk(ntype, owner_mod_id=owner_mod_id,
                x=x, y=y, parent_id=parent_id)
        child_y = y
        for child_node in node.children:
            child_blocks = ast_to_blocks(
                child_node, owner_mod_id=owner_mod_id,
                parent_id=b.id, blocks=blocks,
                x=x + x_step, y=child_y,
                x_step=x_step, y_step=y_step,
            )
            # find the root of the subtree just added
            child_root = next(
                bid for bid, blk in child_blocks.items()
                if blk.parent_id == b.id
            )
            b.children.append(child_root)
            # advance y by subtree height
            child_y += _subtree_height(child_root, child_blocks) * y_step
    else:
        b = _mk("const", const_value=True, x=x, y=y, parent_id=parent_id)

    blocks[b.id] = b
    return blocks


def _subtree_height(root_id: str, blocks: dict[str, LogicBlock]) -> int:
    b = blocks[root_id]
    if not b.children:
        return 1
    return sum(_subtree_height(c, blocks) for c in b.children)


# ---------------------------------------------------------------------------
# Flat block dict  →  AST
# ---------------------------------------------------------------------------

def blocks_to_ast(root_id: str, blocks: dict[str, LogicBlock]) -> ASTNode:
    """Reconstruct an ASTNode tree from the flat block dict."""
    b = blocks[root_id]
    if b.node_type == "item":
        return ItemNode(name=b.item_name or "?", count=b.item_count)
    if b.node_type == "can_access":
        return CanAccessNode(region=b.region_name or "?")
    if b.node_type == "option":
        return OptionNode(key=b.option_key or "?",
                          op=b.option_op or None,
                          value=b.option_value or None)
    if b.node_type == "const":
        return ConstNode(value=b.const_value)
    if b.node_type in ("and", "or"):
        children = [blocks_to_ast(cid, blocks) for cid in b.children]
        if not children:
            return ConstNode(value=True)
        if len(children) == 1:
            return children[0]
        cls = AndNode if b.node_type == "and" else OrNode
        return cls(children=children)
    return ConstNode(value=True)


def blocks_to_logic_string(
    blocks: dict[str, LogicBlock],
    root_id: Optional[str] = None,
) -> str:
    """
    Convert the current block graph to a canonical logic string.
    If root_id is None, find the root automatically (block with no parent).
    Returns "" for an empty or trivially-True graph.
    """
    if not blocks:
        return ""
    if root_id is None:
        roots = [b for b in blocks.values() if b.parent_id is None]
        if not roots:
            return ""
        root_id = roots[0].id
    try:
        ast = blocks_to_ast(root_id, blocks)
        s = serialize(ast)
        return "" if s in ("True", "False") else s
    except Exception:
        return ""
