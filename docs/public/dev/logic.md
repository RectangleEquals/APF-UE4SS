# Logic Expressions

Logic expressions are the declarative language used to describe access requirements in AP Framework manifests. They appear on regions, locations, and items, and serve two distinct purposes:

- **AP generation (Python):** Determines which locations are accessible in each randomization sphere, and prunes entries whose conditions can never be met with the current options.
- **Runtime scoring (C++):** The tracker engine evaluates each expression continuously as items are received, producing a 0.0–1.0 score used for UI color-coding.

Both the Python parser (`worlds/apf/LogicParser.py`) and the C++ evaluator (`shared/include/ap_logic_evaluator.h`) implement the same grammar and produce equivalent results. This document is the single reference for both.

---

## Quick Examples

Practical examples showing common patterns at a glance. These use the figurative game vocabulary used throughout the docs (regions: `Mountain Pass`, `Deep Caves`; items: `Iron Key`, `Crystal Key`, `Lantern`; options: `logic_difficulty`, `include_traps`).

| Pattern | Logic string | What it means |
|---|---|---|
| **Free location** | *(empty)* | Always accessible — no requirements |
| **Single item gate** | `(Item: Iron Key)` | Player must have at least 1 Iron Key |
| **Region gate** | `(Can Access: Mountain Pass)` | Mountain Pass must be reachable |
| **Region + item** | `(Can Access: Mountain Pass) AND (Item: Iron Key)` | Both required; AND score = average |
| **Alternate paths** | `(Item: Iron Key) OR (Item: Crystal Key)` | Either key works; OR score = max |
| **Option pruning** | `(Option: include_traps)` | Item dropped from pool when traps disabled |
| **Option value** | `(Option: logic_difficulty == expert)` | Included only when difficulty is `expert` |
| **Multi-option OR** | `(Option: logic_difficulty == standard) OR (Option: logic_difficulty == expert)` | Included for standard or expert |
| **Cross-region** | `(Can Access: Mountain Pass) AND (Can Access: Deep Caves)` | Both regions must be reachable |
| **Nested condition** | `(Can Access: Deep Caves) AND ((Item: Iron Key) OR (Item: Lantern))` | In Deep Caves, and has one of two items |
| **Item count** | `(Item: Crystal Key : 3)` | Player needs at least 3 Crystal Keys |

---

## Grammar

```
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

OP  := '>=' | '<=' | '>' | '<' | '==' | '!='
NAME := any characters up to the closing ')'
INT  := decimal integer
VALUE := any characters up to the closing ')'
```

**Operator precedence:** AND binds more tightly than OR. Use parentheses to override: `A OR (B AND C)` vs `(A OR B) AND C`.

---

## Expression Types

| Expression | Example | Meaning |
|---|---|---|
| `(Item: Name)` | `(Item: Iron Key)` | Player has at least 1 of the named item |
| `(Item: Name : N)` | `(Item: Crystal Key : 3)` | Player has at least N of the named item |
| `(Can Access: Region)` | `(Can Access: Mountain Pass)` | The named region is reachable |
| `(Option: key)` | `(Option: include_traps)` | Toggle option is enabled (truthy) |
| `(Option: key == val)` | `(Option: logic_difficulty == expert)` | Option equals the value |
| `(Option: key >= N)` | `(Option: key_count >= 5)` | Option compares to a numeric value |
| `True` | `True` | Always satisfied |
| `False` | `False` | Never satisfied |
| `A AND B` | `(Item: Iron Key) AND (Can Access: Mountain Pass)` | Both must be satisfied |
| `A OR B` | `(Item: Iron Key) OR (Item: Crystal Key)` | At least one must be satisfied |
| `(A)` | `((Item: Iron Key) OR (Item: Crystal Key))` | Grouping — no semantic effect, just precedence |

Option operators for numeric comparison: `>=`, `<=`, `>`, `<`, `==`, `!=`. String comparison falls back to lexicographic order when the value cannot be parsed as a number.

---

## Scope Rules by Entry Type

Not all expression types are valid everywhere. The framework enforces these restrictions:

| Entry Type | Valid Nodes | Notes |
|---|---|---|
| **Regions** | `Item`, `CanAccess`, `Option`, `And`, `Or`, `Const` | Full logic supported |
| **Locations** | `Item`, `CanAccess`, `Option`, `And`, `Or`, `Const` | Full logic supported; first `CanAccess` determines display group |
| **Items** | `Option`, `And`, `Or`, `Const` | Only option-based conditions; `Item`/`CanAccess` nodes warn + evaluate to false |
| **Item overrides** | `Option`, `And`, `Or`, `Const` | Same restriction as items |

For items and item overrides, `(Item:)` and `(Can Access:)` nodes are structurally invalid — they cannot be evaluated at generation time before items are placed. When the framework encounters these in item logic, it logs a warning and evaluates the node as `false`. OR branches through valid option nodes can still succeed; only AND chains where an invalid node is required will always block the item from the pool.

---

## Evaluation Contexts

The same logic string is used in two completely different ways:

### Generation Time (Python)

During AP world generation, option values are known and the expression can be partially or fully resolved to a constant.

**Pipeline:**

1. **`parse(logic)`** — tokenize and build an AST from the string
2. **`evaluate_options(node, options)`** — replace all `OptionNode` leaves with `Const(true/false)` based on player option values
3. **`simplify(node)`** — constant-fold the result:
   - AND with any `False` child → `False`
   - AND: remove `True` children; empty → `True`; single child → unwrap
   - OR with any `True` child → `True`
   - OR: remove `False` children; empty → `False`; single child → unwrap
4. **Result is one of:**
   - `Const(True)` → entry is always accessible (no rule set in AP)
   - `Const(False)` → entry is pruned from the pool entirely
   - Remaining AST → compiled to a `CollectionState` lambda via `compile_rule(node, player)`

**Pruning:** Any entry whose logic simplifies to `Const(False)` is removed from the generation pool before items are placed. This is how option-gated content works — `"logic": "(Option: include_traps)"` removes trap items when the player disables the option.

**AP region placement:** Location logic is scanned for `(Can Access: RegionName)` nodes. The first match that corresponds to a declared region becomes the AP region the location is placed in. Locations without any `(Can Access:)` reference are placed in the `Menu` region (sphere 0 — always accessible from the start).

### Runtime (C++ Tracker)

At runtime, option values are already baked into the parsed AST (via `evaluate_options` + `simplify` during engine initialization). The remaining `Item` and `CanAccess` nodes are evaluated against the current `TrackerState`:

```cpp
struct TrackerState {
    std::map<std::string, int> received_items;  // item_name -> count received
    std::set<std::string> reachable_regions;    // currently reachable region names
};
```

**`evaluate_scored(node, state)`** returns a `ScoredNode` tree:

```cpp
struct ScoredNode {
    LogicNodeType type;
    float score;                      // 0.0 = blocked, 0.5 = partial, 1.0 = accessible
    std::string display;              // human-readable text for this node
    std::vector<ScoredNode> children; // for And/Or nodes
};
```

**Scoring rules:**

| Node type | Score formula |
|---|---|
| `Const(true)` | `1.0` |
| `Const(false)` | `0.0` |
| `Item(name, count)` | `min(received / required, 1.0)` — partial credit for partial items |
| `CanAccess(region)` | `1.0` if region is reachable, `0.0` otherwise |
| `Option(...)` | `1.0` (options are resolved before scoring; unknown options default to true) |
| `And(children)` | Average of all children scores |
| `Or(children)` | Maximum of all children scores |

The recursive `ScoredNode` tree mirrors the AST shape, so the tracker UI can color each sub-expression independently:
- `score == 1.0` → green (fully satisfied)
- `0 < score < 1.0` → yellow (partially satisfied — relevant for item count requirements)
- `score == 0.0` → red (blocked)

**Boolean evaluation:** `evaluate_bool(node, state)` returns `true` when `score >= 1.0`.

---

## Region Reachability

Region reachability is computed via fixed-point iteration before location scores are evaluated:

1. Start with `{"Menu"}` plus any regions whose logic is `Const(true)` (no requirements)
2. For each unreachable region, evaluate its access logic with the current reachable set
3. If newly reachable, add it to the set and mark a change occurred
4. Repeat until no changes (fixed-point convergence)

This handles chains like: `Mountain Pass (free) → Deep Caves (needs Iron Key) → Crystal Sanctum (needs Iron Key + Crystal Key)`. When the player receives `Iron Key`, both Deep Caves and Crystal Sanctum are checked; Deep Caves becomes reachable, then Crystal Sanctum is checked again with Deep Caves in the reachable set.

> **"Menu" vs "Main":** The `{"Menu"}` seed is the Archipelago graph starting region — the standard AP convention for the root of the reachability graph. "Main" is a separate concept: it is the fallback **display group label** used by the tracker when a location has no `(Can Access: R)` reference in its logic. These are unrelated. See [Display Region Derivation](#display-region-derivation).

---

## Display Region Derivation

The tracker UI groups locations by region for display. The display region is derived automatically from location logic — no separate field is required:

1. Scan the location's logic string for the first `(Can Access: RegionName)` pattern
2. If found, that `RegionName` is the display group
3. Fallback: if the location name contains `": "` (e.g., `"Mountain Pass: Supply Cache"`), use the prefix before it
4. Final fallback: `"Main"`

This means that how you write location logic directly determines how the tracker groups and displays those locations. The `"Main"` fallback label is a display-only concept and has no relationship to the Archipelago graph root region (which is called `"Menu"`).

---

## Examples

### Free location (no logic)
```
(empty)
```
Always accessible. Score: `1.0`. Placed in the `Menu` AP region (sphere 0). Tracker display group falls back to name prefix or `"Main"`.

### Single item requirement
```
(Item: Iron Key)
```
Satisfied when the player has received at least one `Iron Key`. Score: `min(received/1, 1.0)`.

### Item count requirement
```
(Item: Crystal Key : 3)
```
Satisfied when the player has received at least 3 `Crystal Key` items. Score at 1 owned: `0.33`, at 2: `0.67`, at 3: `1.0`.

### Region gate
```
(Can Access: Mountain Pass)
```
Satisfied when `Mountain Pass` is in the reachable set. Binary score — 0.0 or 1.0.

### Region gate with item requirement (AND)
```
(Can Access: Deep Caves) AND (Item: Lantern)
```
AND node score = average of children. At 0 items received with Deep Caves unreachable: `(0.0 + 0.0) / 2 = 0.0`. At Lantern received but Deep Caves still unreachable: `(0.0 + 1.0) / 2 = 0.5`. Both satisfied: `1.0`.

### Alternate paths (OR)
```
(Can Access: Deep Caves) AND ((Item: Iron Key) OR (Item: Crystal Key))
```
The inner OR scores as `max(Iron Key score, Crystal Key score)`. If the player has Crystal Key but not Iron Key, the OR scores `1.0`. The outer AND then averages Deep Caves (0.0 or 1.0) with the OR result.

### Option-gated item (generation time only)
```
(Option: include_traps)
```
If the `include_traps` toggle option is `false`, this resolves to `Const(false)` at generation time and the item is pruned from the pool. If `true`, it resolves to `Const(true)` and the item is unconditionally included.

### Option comparison
```
(Option: logic_difficulty == standard) OR (Option: logic_difficulty == expert)
```
Evaluates based on the player's `logic_difficulty` text choice. If `logic_difficulty` is `"standard"`, the first branch is `true`, the OR is `true`, the item is included.

### Numeric option comparison
```
(Option: key_count >= 3)
```
Includes the entry when `key_count` is 3 or greater. Numeric comparison falls back to string comparison if the value cannot be parsed as a number.

### Location with region and nested OR
```json
{ "name": "Mountain Pass: Supply Cache",
  "logic": "(Can Access: Mountain Pass) AND ((Item: Iron Key) OR (Item: Lantern))" }
```
Located in the `Mountain Pass` region for AP sphere purposes and display grouping. Requires being in Mountain Pass and having at least one of the two items.

### Region declaration
```json
{ "name": "Deep Caves",
  "logic": "(Item: Iron Key) AND (Item: Lantern)" }
```
`Deep Caves` becomes reachable only when the player holds both `Iron Key` and `Lantern`. All locations requiring `(Can Access: Deep Caves)` are unreachable until then.

---

## Notes

**Empty or missing logic:** An entry with no `logic` field (or an empty string) is treated as `Const(true)` — always accessible. In the tracker, it scores `1.0`. In AP generation, it places the location in the `Menu` region with no access rule.

**Unknown options:** If an `(Option: key)` references an option name not present in the player's options, it defaults to `true` (permissive) — the content is included. This ensures that option-gated content is not accidentally hidden when options evolve between mod versions. **A warning is logged in both the C++ framework and the Python apworld** when an unknown option key is encountered at evaluation time.

**`True` / `False` literals:** Explicit constants, rarely used in practice. `False` can be used during development to temporarily disable a location without removing it from the manifest.

**Logic string validation:** The parser throws on malformed expressions (unclosed parentheses, unknown tokens, etc.). The framework catches parse errors at engine initialization and logs them; the affected entry is treated as `Const(false)` (excluded).

---

*See also: [manifest.md](manifest.md) for how logic fields appear in `manifest.json` | [tracker.md](tracker.md) for how `ScoredNode` trees are serialized and consumed*
