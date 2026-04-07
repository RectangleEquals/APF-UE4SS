"""
Logic expression parser for the AP Framework World.

Parses human-readable logic strings like:
    (Item: Grass Boss Victory) AND (Can Access: Post-Grass Boss)
    (Item: Tech Points : 5)
    (Option: difficulty >= 3) AND (Item: Legendary Weapon)
    ((Item: Jetpack) OR (Item: Grappling Gun Mk3)) AND (Item: Heat Resistant Armor)
    True

Grammar:
    expression := and_expr ('OR' and_expr)*
    and_expr   := primary ('AND' primary)*
    primary    := '(' expression ')'
               | '(Item:' NAME ')'
               | '(Item:' NAME ':' INT ')'
               | '(Can Access:' NAME ')'
               | '(Option:' NAME ')'
               | '(Option:' NAME OP VALUE ')'
               | '(Goal:' NAME ')'
               | '(Goal: none)'
               | '(Goal: ?)'
               | '(Checked:' NAME ')'
               | 'True' | 'False'

Option expressions are evaluated at generation time (static). Item and region
expressions compile to CollectionState lambdas for runtime AP logic.
"""

import logging
import re
from typing import List, Tuple, Optional, Callable, Dict, Any, Union
from dataclasses import dataclass

from BaseClasses import CollectionState


# ============================================================================
# AST Nodes
# ============================================================================

@dataclass
class ItemNode:
    """Has >= count of the named item."""
    name: str
    count: int = 1


@dataclass
class CanAccessNode:
    """Can reach the named region."""
    region: str


@dataclass
class OptionNode:
    """Check a player option value. Resolved at generation time."""
    name: str
    op: Optional[str] = None   # None = boolean check; else >=, <=, >, <, ==, !=
    value: Optional[str] = None


@dataclass
class AndNode:
    """All children must be satisfied."""
    children: list


@dataclass
class OrNode:
    """At least one child must be satisfied."""
    children: list


@dataclass
class ConstNode:
    """Constant True or False."""
    value: bool


@dataclass
class CheckedNode:
    """Location has been sent as a check. Valid in goal logic only."""
    location: str


# ============================================================================
# Token Types
# ============================================================================

ITEM = "ITEM"
CAN_ACCESS = "CAN_ACCESS"
OPTION = "OPTION"
CHECKED = "CHECKED"
AND = "AND"
OR = "OR"
TRUE = "TRUE"
FALSE = "FALSE"
LPAREN = "LPAREN"
RPAREN = "RPAREN"

Token = Tuple[str, Any]


# ============================================================================
# Tokenizer
# ============================================================================

def tokenize(logic: str) -> List[Token]:
    """Tokenize a logic expression string.

    Typed expressions like (Item: ...), (Can Access: ...), (Option: ...)
    are consumed as single tokens including their closing paren.
    Plain '(' and ')' are grouping tokens.
    """
    tokens: List[Token] = []
    i = 0
    n = len(logic)

    while i < n:
        # Skip whitespace
        if logic[i].isspace():
            i += 1
            continue

        # Parenthesized expressions
        if logic[i] == '(':
            rest = logic[i:]

            # (Item: NAME) or (Item: NAME : COUNT)
            if rest.startswith('(Item:'):
                i += len('(Item:')
                close = logic.find(')', i)
                if close == -1:
                    raise ValueError(f"Unclosed '(Item:' starting near position {i}")
                content = logic[i:close].strip()
                # Split on last ':' for optional count
                parts = content.rsplit(':', 1)
                if len(parts) == 2 and parts[1].strip().isdigit():
                    tokens.append((ITEM, (parts[0].strip(), int(parts[1].strip()))))
                else:
                    tokens.append((ITEM, (content, 1)))
                i = close + 1
                continue

            # (Can Access: REGION)
            if rest.startswith('(Can Access:'):
                i += len('(Can Access:')
                close = logic.find(')', i)
                if close == -1:
                    raise ValueError(f"Unclosed '(Can Access:' starting near position {i}")
                region = logic[i:close].strip()
                tokens.append((CAN_ACCESS, region))
                i = close + 1
                continue

            # (Goal: NAME) — syntactic sugar for (Option: goal == NAME)
            # Special reserved values:
            #   (Goal: none) → goal option is empty string (no goal selected / default mode)
            #   (Goal: ?)    → boolean truthy check (any goal is active)
            if rest.startswith('(Goal:'):
                i += len('(Goal:')
                close = logic.find(')', i)
                if close == -1:
                    raise ValueError(f"Unclosed '(Goal:' starting near position {i}")
                goal_name = logic[i:close].strip()
                if goal_name == '?':
                    tokens.append((OPTION, ("goal", None, None)))    # boolean check
                elif goal_name.lower() == 'none':
                    tokens.append((OPTION, ("goal", "==", "")))      # empty = no goal set
                else:
                    tokens.append((OPTION, ("goal", "==", goal_name)))
                i = close + 1
                continue

            # (Checked: LOCATION) — valid in goal logic only
            if rest.startswith('(Checked:'):
                i += len('(Checked:')
                close = logic.find(')', i)
                if close == -1:
                    raise ValueError(f"Unclosed '(Checked:' starting near position {i}")
                location = logic[i:close].strip()
                tokens.append((CHECKED, location))
                i = close + 1
                continue

            # (Option: NAME) or (Option: NAME OP VALUE)
            if rest.startswith('(Option:'):
                i += len('(Option:')
                close = logic.find(')', i)
                if close == -1:
                    raise ValueError(f"Unclosed '(Option:' starting near position {i}")
                content = logic[i:close].strip()
                op_match = re.match(r'^(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)$', content)
                if op_match:
                    tokens.append((OPTION, (
                        op_match.group(1),
                        op_match.group(2),
                        op_match.group(3).strip(),
                    )))
                else:
                    tokens.append((OPTION, (content, None, None)))
                i = close + 1
                continue

            # Plain grouping paren
            tokens.append((LPAREN, None))
            i += 1
            continue

        if logic[i] == ')':
            tokens.append((RPAREN, None))
            i += 1
            continue

        # Keywords — must be followed by non-alpha or end-of-string
        remaining = logic[i:]

        if remaining.startswith('AND') and (len(remaining) == 3 or not remaining[3].isalnum()):
            tokens.append((AND, None))
            i += 3
            continue

        if remaining.startswith('OR') and (len(remaining) == 2 or not remaining[2].isalnum()):
            tokens.append((OR, None))
            i += 2
            continue

        if remaining.startswith('True') and (len(remaining) == 4 or not remaining[4].isalnum()):
            tokens.append((TRUE, None))
            i += 4
            continue

        if remaining.startswith('False') and (len(remaining) == 5 or not remaining[5].isalnum()):
            tokens.append((FALSE, None))
            i += 5
            continue

        raise ValueError(
            f"Unexpected character at position {i}: '{logic[i]}'\n"
            f"  in expression: {logic}"
        )

    return tokens


# ============================================================================
# Parser (recursive descent)
# ============================================================================

class Parser:
    """Recursive-descent parser for logic expressions."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, token_type: str) -> Token:
        token = self.consume()
        if token[0] != token_type:
            raise ValueError(f"Expected {token_type}, got {token[0]}")
        return token

    def parse(self):
        """Parse the full expression."""
        if not self.tokens:
            return ConstNode(value=True)
        result = self._parse_expression()
        if self.pos < len(self.tokens):
            raise ValueError(f"Unexpected token after expression: {self.tokens[self.pos]}")
        return result

    def _parse_expression(self):
        """expression := and_expr ('OR' and_expr)*"""
        parts = [self._parse_and_expr()]
        while self.peek() and self.peek()[0] == OR:
            self.consume()
            parts.append(self._parse_and_expr())
        return parts[0] if len(parts) == 1 else OrNode(children=parts)

    def _parse_and_expr(self):
        """and_expr := primary ('AND' primary)*"""
        parts = [self._parse_primary()]
        while self.peek() and self.peek()[0] == AND:
            self.consume()
            parts.append(self._parse_primary())
        return parts[0] if len(parts) == 1 else AndNode(children=parts)

    def _parse_primary(self):
        """Parse a primary expression (leaf or grouped sub-expression)."""
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of expression")

        typ = token[0]

        if typ == ITEM:
            self.consume()
            name, count = token[1]
            return ItemNode(name=name, count=count)

        if typ == CAN_ACCESS:
            self.consume()
            return CanAccessNode(region=token[1])

        if typ == OPTION:
            self.consume()
            name, op, value = token[1]
            return OptionNode(name=name, op=op, value=value)

        if typ == CHECKED:
            self.consume()
            return CheckedNode(location=token[1])

        if typ == TRUE:
            self.consume()
            return ConstNode(value=True)

        if typ == FALSE:
            self.consume()
            return ConstNode(value=False)

        if typ == LPAREN:
            self.consume()
            expr = self._parse_expression()
            self.expect(RPAREN)
            return expr

        raise ValueError(f"Unexpected token: {token}")


# ============================================================================
# Option Evaluation (generation-time resolution)
# ============================================================================

def evaluate_options(node, options: Dict[str, Any]):
    """Replace OptionNodes with ConstNodes based on player's option values.

    Args:
        node: AST node
        options: Dict mapping option name to its resolved value

    Returns:
        New AST with all OptionNodes resolved to ConstNode(True/False)
    """
    if isinstance(node, OptionNode):
        value = options.get(node.name)
        if value is None:
            # Unknown option — include by default (permissive)
            logging.warning(f"[APF] Unknown option '{node.name}' in logic — treating as true (permissive)")
            return ConstNode(value=True)

        if node.op is None:
            # Boolean check
            return ConstNode(value=bool(value))

        # Comparison — try numeric first, fall back to string
        try:
            left = float(value) if not isinstance(value, (int, float)) else value
            right = float(node.value)
            result = {
                '>=': left >= right,
                '<=': left <= right,
                '>':  left > right,
                '<':  left < right,
                '==': left == right,
                '!=': left != right,
            }[node.op]
        except (ValueError, TypeError):
            left_str = str(value).lower()
            right_str = str(node.value).lower()
            result = {
                '==': left_str == right_str,
                '!=': left_str != right_str,
                '>=': left_str >= right_str,
                '<=': left_str <= right_str,
                '>':  left_str > right_str,
                '<':  left_str < right_str,
            }[node.op]

        return ConstNode(value=result)

    if isinstance(node, AndNode):
        return AndNode(children=[evaluate_options(c, options) for c in node.children])

    if isinstance(node, OrNode):
        return OrNode(children=[evaluate_options(c, options) for c in node.children])

    # ItemNode, CanAccessNode, CheckedNode, ConstNode — unchanged
    return node


# ============================================================================
# AST Simplification (constant folding)
# ============================================================================

def simplify(node):
    """Fold constants in the AST after option evaluation.

    - AND with any False child -> False
    - AND: remove True children; empty -> True; single child -> unwrap
    - OR  with any True child  -> True
    - OR:  remove False children; empty -> False; single child -> unwrap
    """
    if isinstance(node, AndNode):
        children = [simplify(c) for c in node.children]
        if any(isinstance(c, ConstNode) and not c.value for c in children):
            return ConstNode(value=False)
        children = [c for c in children if not (isinstance(c, ConstNode) and c.value)]
        if not children:
            return ConstNode(value=True)
        if len(children) == 1:
            return children[0]
        return AndNode(children=children)

    if isinstance(node, OrNode):
        children = [simplify(c) for c in node.children]
        if any(isinstance(c, ConstNode) and c.value for c in children):
            return ConstNode(value=True)
        children = [c for c in children if not (isinstance(c, ConstNode) and not c.value)]
        if not children:
            return ConstNode(value=False)
        if len(children) == 1:
            return children[0]
        return OrNode(children=children)

    return node


# ============================================================================
# Compiler (AST -> CollectionState lambda)
# ============================================================================

def compile_rule(node, player: int) -> Callable[[CollectionState], bool]:
    """Compile an AST node into a CollectionState predicate.

    All OptionNodes must be resolved before calling this.

    Args:
        node: AST node
        player: Player number

    Returns:
        Callable that checks a CollectionState and returns bool
    """
    if isinstance(node, ConstNode):
        val = node.value
        return lambda state, v=val: v

    if isinstance(node, ItemNode):
        name, count = node.name, node.count
        return lambda state, n=name, c=count, p=player: state.has(n, p, c)

    if isinstance(node, CanAccessNode):
        region = node.region
        return lambda state, r=region, p=player: state.can_reach_region(r, p)

    if isinstance(node, CheckedNode):
        # Generation-time approximation: location must be reachable.
        # Runtime enforcement (actually checked) is handled by the C++ tracker.
        loc = node.location
        return lambda state, l=loc, p=player: state.can_reach(l, "Location", p)

    if isinstance(node, AndNode):
        compiled = [compile_rule(c, player) for c in node.children]
        return lambda state, rules=compiled: all(r(state) for r in rules)

    if isinstance(node, OrNode):
        compiled = [compile_rule(c, player) for c in node.children]
        return lambda state, rules=compiled: any(r(state) for r in rules)

    if isinstance(node, OptionNode):
        raise ValueError(f"Unresolved OptionNode '{node.name}' — call evaluate_options() first")

    raise ValueError(f"Unknown AST node type: {type(node).__name__}")


# ============================================================================
# Region Reference Extraction
# ============================================================================

def extract_region_refs(node) -> List[str]:
    """Extract all region names referenced by (Can Access: ...) nodes.

    Used to register indirect conditions in AP's region graph.

    Args:
        node: AST node

    Returns:
        List of region name strings
    """
    if isinstance(node, CanAccessNode):
        return [node.region]
    if isinstance(node, (AndNode, OrNode)):
        refs = []
        for child in node.children:
            refs.extend(extract_region_refs(child))
        return refs
    return []


# ============================================================================
# Checked Node Helpers
# ============================================================================

def _collect_checked_nodes(node) -> list:
    """Walk AST and return all CheckedNode instances found."""
    if isinstance(node, CheckedNode):
        return [node]
    if isinstance(node, (AndNode, OrNode)):
        result = []
        for child in node.children:
            result.extend(_collect_checked_nodes(child))
        return result
    return []


def _replace_checked_with_false(node):
    """Walk AST and replace all CheckedNode instances with ConstNode(False)."""
    if isinstance(node, CheckedNode):
        return ConstNode(value=False)
    if isinstance(node, AndNode):
        return AndNode(children=[_replace_checked_with_false(c) for c in node.children])
    if isinstance(node, OrNode):
        return OrNode(children=[_replace_checked_with_false(c) for c in node.children])
    return node


# ============================================================================
# Public API
# ============================================================================

def parse(logic: str):
    """Parse a logic string into an AST.

    Empty/whitespace strings return ConstNode(True) (always accessible).
    """
    if not logic or not logic.strip():
        return ConstNode(value=True)
    tokens = tokenize(logic)
    return Parser(tokens).parse()


def parse_and_compile(
    logic: str,
    player: int,
    options: Optional[Dict[str, Any]] = None,
) -> Optional[Callable[[CollectionState], bool]]:
    """Parse a logic string, evaluate options, simplify, and compile.

    Args:
        logic: Logic expression string
        player: Player number
        options: Option name -> value dict for (Option: ...) evaluation

    Returns:
        - None if the logic simplifies to True (always accessible, no rule needed)
        - A CollectionState predicate otherwise
        - Returns a never-satisfiable predicate if logic simplifies to False
    """
    ast = parse(logic)

    if options is not None:
        ast = evaluate_options(ast, options)
        ast = simplify(ast)

    if isinstance(ast, ConstNode):
        if ast.value:
            return None  # Always accessible
        return lambda state: False  # Never accessible

    return compile_rule(ast, player)


def is_always_false(logic: str, options: Optional[Dict[str, Any]] = None) -> bool:
    """Check if a logic string evaluates to False after option resolution.

    Used to filter out locations/regions that should be excluded.
    """
    ast = parse(logic)
    if options is not None:
        ast = evaluate_options(ast, options)
        ast = simplify(ast)
    return isinstance(ast, ConstNode) and not ast.value


# ============================================================================
# Amount Expression Evaluator
# ============================================================================

def _find_ternary_split(expr: str):
    """Locate depth-0 '?' and ':' to split a ternary expression.

    Returns (condition, true_val, false_val) strings, or None if not a ternary.
    """
    depth = 0
    q_pos = None
    for i, c in enumerate(expr):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == '?' and depth == 0:
            q_pos = i
            break
    if q_pos is None:
        return None

    condition = expr[:q_pos].strip()
    rest = expr[q_pos + 1:]

    depth = 0
    c_pos = None
    for i, c in enumerate(rest):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ':' and depth == 0:
            c_pos = i
            break
    if c_pos is None:
        return None

    return condition, rest[:c_pos].strip(), rest[c_pos + 1:].strip()


def _evaluate_amount_value(val_str: str, options: Dict[str, Any], location_count: int) -> int:
    """Evaluate a single value token (integer, {key}, {key}%, fill) to an integer.

    Returns -1 for the auto-balance sentinel ("fill").
    """
    v = val_str.strip()

    if v == 'fill':
        return -1

    if v.endswith('%'):
        inner = v[:-1].strip()
        if inner.startswith('{') and inner.endswith('}'):
            key = inner[1:-1].strip()
            opt_val = options.get(key)
            if opt_val is None:
                logging.warning(f"[APF] Unknown option '{key}' in amount expression — using 0")
                return 0
            if isinstance(opt_val, str):
                logging.warning(
                    f"[APF] text_choice option '{key}' has no integer value for '{{key}}%' — using 0"
                )
                return 0
            return max(0, int(int(opt_val) * location_count // 100))
        else:
            try:
                return max(0, int(float(inner) * location_count // 100))
            except (ValueError, TypeError):
                logging.warning(f"[APF] Invalid percentage '{val_str}' in amount expression — using 0")
                return 0

    if v.startswith('{') and v.endswith('}'):
        key = v[1:-1].strip()
        opt_val = options.get(key)
        if opt_val is None:
            logging.warning(f"[APF] Unknown option '{key}' in amount expression — using 0")
            return 0
        if isinstance(opt_val, str):
            logging.warning(
                f"[APF] text_choice option '{key}' has no integer value in amount expression — using 0"
            )
            return 0
        return max(0, int(opt_val))

    try:
        return max(0, int(v))
    except (ValueError, TypeError):
        logging.warning(f"[APF] Invalid value '{val_str}' in amount expression — using 0")
        return 0


def evaluate_count(expr_str: str, options: Dict[str, Any], location_count: int = 0) -> int:
    """Evaluate an item amount expression string to an integer count.

    Returns -1 for the auto-balance fill sentinel.
    Returns 0 on any error (with a warning logged).

    Supported forms:
      Integer literal:  "3"  → 3
      fill sentinel:    "fill"  → -1  (also legacy -1 int handled by caller)
      {key}:            "{trap_count}"  → option's integer value
      {key}%:           "{pct}%"  → floor(location_count * value / 100)
      Ternary:          "<condition> ? <true_val> : <false_val>"

    Forbidden: (Item:), (Can Access:), (Option:) as standalone (not in ternary condition),
    arithmetic, nested ternaries.
    """
    if not expr_str:
        return 1

    expr = expr_str.strip()

    # Integer literal (including legacy -1)
    try:
        return int(expr)
    except (ValueError, TypeError):
        pass

    # "fill" keyword
    if expr == 'fill':
        return -1

    # Standalone {key} or {key}%
    if expr.startswith('{'):
        return _evaluate_amount_value(expr, options, location_count)

    # Ternary
    parts = _find_ternary_split(expr)
    if parts is not None:
        condition, true_val, false_val = parts

        # Nested ternary guard
        if _find_ternary_split(true_val) is not None or _find_ternary_split(false_val) is not None:
            logging.warning(
                f"[APF] Nested ternary in amount expression '{expr_str}' — not supported, using 0"
            )
            return 0

        # Runtime nodes not valid in amount conditions
        if '(Item:' in condition or '(Can Access:' in condition:
            logging.warning(
                f"[APF] Runtime nodes (Item:/Can Access:) in amount condition '{expr_str}' — using 0"
            )
            return 0

        cond_true = not is_always_false(condition, options)
        return _evaluate_amount_value(true_val if cond_true else false_val, options, location_count)

    # Bare (Option:) or (Goal:) — invalid as standalone amount
    if expr.startswith('(Option:') or expr.startswith('(Goal:'):
        logging.warning(
            f"[APF] '{expr_str}' is a boolean expression, not a count — "
            f"use {{key}} for an option's integer value"
        )
        return 0

    logging.warning(f"[APF] Unrecognized amount expression '{expr_str}' — using 0")
    return 0