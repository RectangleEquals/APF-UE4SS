"""
core/logic_parser.py

Python implementation of the APF logic expression grammar.

Grammar (from logic.md):
    expression  := and_expr ('OR' and_expr)*
    and_expr    := primary ('AND' primary)*
    primary     := '(' expression ')'
                 | '(Item:' NAME ')'
                 | '(Item:' NAME ':' INT ')'
                 | '(Can Access:' NAME ')'
                 | '(Option:' NAME ')'
                 | '(Option:' NAME OP VALUE ')'
                 | 'True'
                 | 'False'

This module is intentionally kept free of Archipelago and Kivy dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------

@dataclass
class ItemNode:
    name: str
    count: int = 1

    def __repr__(self):
        return f"ItemNode({self.name!r}, {self.count})"


@dataclass
class CanAccessNode:
    region: str

    def __repr__(self):
        return f"CanAccessNode({self.region!r})"


@dataclass
class OptionNode:
    key: str
    op: Optional[str] = None    # None → toggle check
    value: Optional[str] = None

    def __repr__(self):
        if self.op:
            return f"OptionNode({self.key!r} {self.op} {self.value!r})"
        return f"OptionNode({self.key!r})"



@dataclass
class ConstNode:
    value: bool

    def __repr__(self):
        return f"ConstNode({self.value})"


@dataclass
class AndNode:
    children: list["ASTNode"] = field(default_factory=list)

    def __repr__(self):
        return f"AndNode({self.children})"


@dataclass
class OrNode:
    children: list["ASTNode"] = field(default_factory=list)

    def __repr__(self):
        return f"OrNode({self.children})"


ASTNode = Union[ItemNode, CanAccessNode, OptionNode, ConstNode, AndNode, OrNode]

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_ITEM_RE      = re.compile(r'\(Item:\s*([^:)]+?)(?:\s*:\s*(\d+))?\s*\)')
_CANACCESS_RE = re.compile(r'\(Can Access:\s*([^)]+?)\s*\)')
_OPTION_RE    = re.compile(
    r'\(Option:\s*([^)>=<!]+?)\s*(?:(>=|<=|>|<|==|!=)\s*([^)]+?))?\s*\)'
)
_CONST_TRUE   = re.compile(r'\bTrue\b')
_CONST_FALSE  = re.compile(r'\bFalse\b')

# Tokenisation: split by AND / OR while preserving parenthesised blocks
_AND_SPLIT = re.compile(r'\bAND\b')
_OR_SPLIT  = re.compile(r'\bOR\b')



# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse(logic_str: str) -> ASTNode:
    """
    Parse a logic string into an ASTNode tree.
    Returns ConstNode(True) for empty/whitespace-only strings.
    Raises ValueError on malformed input.
    """
    s = (logic_str or "").strip()
    if not s:
        return ConstNode(True)
    return _parse_expression(s)


def _parse_expression(s: str) -> ASTNode:
    """Top-level: split on OR (lowest precedence)."""
    parts = _split_top_level(s, 'OR')
    if len(parts) > 1:
        children = [_parse_and_expr(p.strip()) for p in parts]
        return OrNode(children)
    return _parse_and_expr(s)


def _parse_and_expr(s: str) -> ASTNode:
    """Split on AND (higher precedence than OR)."""
    parts = _split_top_level(s, 'AND')
    if len(parts) > 1:
        children = [_parse_primary(p.strip()) for p in parts]
        return AndNode(children)
    return _parse_primary(s)


def _parse_primary(s: str) -> ASTNode:
    s = s.strip()

    # Grouping: outer parens that are NOT leaf tokens
    if s.startswith('(') and _matching_close(s) == len(s) - 1:
        # Check if it's a leaf token first
        inner = s[1:-1].strip()
        if not (inner.startswith('Item:') or inner.startswith('Can Access:')
                or inner.startswith('Option:')):
            return _parse_expression(inner)

    # (Item: Name) or (Item: Name : count)
    m = _ITEM_RE.fullmatch(s)
    if m:
        return ItemNode(name=m.group(1).strip(),
                        count=int(m.group(2)) if m.group(2) else 1)

    # (Can Access: Region)
    m = _CANACCESS_RE.fullmatch(s)
    if m:
        return CanAccessNode(region=m.group(1).strip())

    # (Option: key) or (Option: key OP value)
    m = _OPTION_RE.fullmatch(s)
    if m:
        return OptionNode(key=m.group(1).strip(),
                          op=m.group(2),
                          value=m.group(3).strip() if m.group(3) else None)

    if _CONST_TRUE.fullmatch(s):
        return ConstNode(True)
    if _CONST_FALSE.fullmatch(s):
        return ConstNode(False)

    raise ValueError(f"Unrecognised logic token: {s!r}")



def _split_top_level(s: str, keyword: str) -> list[str]:
    """
    Split s on bare AND/OR keywords that are not inside parentheses.
    Returns a list of substrings (at least one element).
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    kw_len = len(keyword)
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
            current.append(ch)
            i += 1
        elif ch == ')':
            depth -= 1
            current.append(ch)
            i += 1
        elif depth == 0 and s[i:i + kw_len] == keyword:
            # Check word boundaries
            before = i == 0 or not s[i - 1].isalnum()
            after = (i + kw_len >= len(s)) or not s[i + kw_len].isalnum()
            if before and after:
                parts.append(''.join(current).strip())
                current = []
                i += kw_len
            else:
                current.append(ch)
                i += 1
        else:
            current.append(ch)
            i += 1
    parts.append(''.join(current).strip())
    return parts


def _matching_close(s: str) -> int:
    """
    Find the index of the closing ')' that matches the opening '(' at index 0.
    Returns -1 if s[0] != '(' or no match found.
    """
    if not s or s[0] != '(':
        return -1
    depth = 0
    for i, ch in enumerate(s):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

def serialize(node: ASTNode) -> str:
    """Rebuild a canonical logic string from an ASTNode tree."""
    if isinstance(node, ConstNode):
        return "True" if node.value else "False"
    if isinstance(node, ItemNode):
        if node.count != 1:
            return f"(Item: {node.name} : {node.count})"
        return f"(Item: {node.name})"
    if isinstance(node, CanAccessNode):
        return f"(Can Access: {node.region})"
    if isinstance(node, OptionNode):
        if node.op:
            return f"(Option: {node.key} {node.op} {node.value})"
        return f"(Option: {node.key})"
    if isinstance(node, AndNode):
        parts = [_wrap_or(c) for c in node.children]
        return " AND ".join(parts)
    if isinstance(node, OrNode):
        parts = [serialize(c) for c in node.children]
        return " OR ".join(parts)
    raise TypeError(f"Unknown node type: {type(node)}")


def _wrap_or(node: ASTNode) -> str:
    """Wrap OrNode in parens when nested inside AND (precedence)."""
    s = serialize(node)
    if isinstance(node, OrNode):
        return f"({s})"
    return s



# ---------------------------------------------------------------------------
# Scope validation (logic.md rules)
# ---------------------------------------------------------------------------

SCOPE_RULES: dict[str, set[str]] = {
    "region":         {"item", "can_access", "option", "and", "or", "const"},
    "location":       {"item", "can_access", "option", "and", "or", "const"},
    "item":           {"option", "and", "or", "const"},
    "item_override":  {"option", "and", "or", "const"},
}


def _node_type(node: ASTNode) -> str:
    return {
        ItemNode: "item", CanAccessNode: "can_access",
        OptionNode: "option", ConstNode: "const",
        AndNode: "and", OrNode: "or",
    }[type(node)]


def validate_scope(node: ASTNode, entry_type: str) -> list[str]:
    """
    Return list of scope-rule violation messages.
    entry_type: 'region' | 'location' | 'item' | 'item_override'
    """
    allowed = SCOPE_RULES.get(entry_type, set())
    errors: list[str] = []
    _check_scope(node, allowed, errors)
    return errors


def _check_scope(node: ASTNode, allowed: set[str], errors: list[str]) -> None:
    nt = _node_type(node)
    if nt not in allowed:
        errors.append(
            f"Node type '{nt}' is not allowed in this context "
            f"(allowed: {sorted(allowed)})"
        )
    if isinstance(node, (AndNode, OrNode)):
        for child in node.children:
            _check_scope(child, allowed, errors)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def collect_region_refs(node: ASTNode) -> list[str]:
    """Return all region names referenced by CanAccess nodes in the tree."""
    refs: list[str] = []
    _collect_regions(node, refs)
    return refs


def _collect_regions(node: ASTNode, out: list[str]) -> None:
    if isinstance(node, CanAccessNode):
        out.append(node.region)
    elif isinstance(node, (AndNode, OrNode)):
        for child in node.children:
            _collect_regions(child, out)


def collect_item_refs(node: ASTNode) -> list[str]:
    """Return all item names referenced by Item nodes in the tree."""
    refs: list[str] = []
    _collect_items(node, refs)
    return refs


def _collect_items(node: ASTNode, out: list[str]) -> None:
    if isinstance(node, ItemNode):
        out.append(node.name)
    elif isinstance(node, (AndNode, OrNode)):
        for child in node.children:
            _collect_items(child, out)

