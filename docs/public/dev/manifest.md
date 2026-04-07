# manifest.json Reference

Every AP Framework mod is declared through a `manifest.json` file in its mod folder. The framework scans all mod directories on startup and identifies AP mods by the presence of a `mod_id` field. Mods without `mod_id` are treated as regular UE4SS mods with no framework involvement.

---

## File Location

```
Mods/
└── YourModName/
    ├── manifest.json      ← this file
    └── Scripts/
        └── main.lua
```

Mod folder names should begin with the game name to avoid collisions when multiple games are supported (e.g., `MygameItemShuffle/`, `MygameTracker/`). The `mod_id` follows the pattern `author.gamename.modname`.

> **APFrameworkMod is a special case.** The framework always looks for a mod folder named exactly `APFrameworkMod`. Because it must register game-specific tick hooks (the exact hook paths differ per game's Blueprint class hierarchy), a separate `APFrameworkMod` exists for each supported game. They share the same folder name but contain game-specific Lua hook registrations.

---

## Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mod_id` | string | **Yes** | Unique identifier. Format: `author.game.modname`. Presence of this field marks the mod as an AP Framework mod. |
| `name` | string | No | Human-readable display name |
| `version` | string | No | Semantic version string (e.g., `"1.0.0"`) |
| `enabled` | bool | No | If `false`, the mod is skipped entirely. Default: `true` |
| `description` | string | No | Short description shown in APF Manager |
| `vocab_validation` | bool | No | If `true`, item/location/region names are validated against game vocabulary files in `Templates/`. Default: `false` |
| `depends` | array | No | Hard dependencies — other mods that must be present and registered first |
| `incompatible` | array | No | Mods that cannot be active at the same time as this one |
| `options` | object | No | Player-configurable options contributed to Archipelago generation |
| `goals` | array | No | Completion conditions for this mod |
| `capabilities` | object | No | Items, locations, regions, and overrides contributed to AP generation |

---

## mod_id Conventions

The `mod_id` uniquely identifies a mod across all games and authors:

```
author.game.modname
```

- `author`: your username or organization handle
- `game`: the target game (short identifier, e.g., `mygame`, `zephyr`)
- `modname`: short mod identifier

**Priority mods** use the prefix `archipelago.<game_name>.*` (e.g., `archipelago.mygame.tracker`). This prefix causes the framework to treat the mod as a priority client — it connects during an earlier registration phase and receives special access. **Priority clients must not declare any capabilities (items, locations, regions, goals).** They exist for framework integration purposes — tracker UIs, admin tools, cross-mod coordinators — not for contributing randomization content.

Game mods that contribute items/locations should use the regular `author.game.modname` pattern.

---

## Dependencies

```json
"depends": ["author.mygame.basemod"],
"incompatible": ["thirdparty.mygame.alternatemode (>=2.0.0)"]
```

- `depends`: mods that must be registered before this one. If a dependency is missing or fails registration, this mod is skipped with a warning.
- `incompatible`: mods that cannot be active simultaneously. If both are present, the later-registered one is rejected with an error.

Both fields accept strings of the form `"mod_id"` or `"mod_id (OP version)"` where `OP` is a semver operator (`>=`, `<=`, `>`, `<`, `==`, `!=`).

---

## Options

Options declared in `manifest.json` become player-configurable settings in the Archipelago YAML. Players set these before generating a multiworld.

```json
"options": {
    "option_key": {
        "type": "toggle | range | text_choice",
        ...
    }
}
```

### Toggle

A boolean on/off switch.

```json
"include_traps": {
    "type": "toggle",
    "default": false,
    "description": "Include trap items in the item pool"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `"toggle"` | Required |
| `default` | bool | Default value |
| `description` | string | Shown to player in YAML documentation |

### Range

An integer slider between two bounds.

```json
"key_count": {
    "type": "range",
    "range_start": 1,
    "range_end": 10,
    "default": "3",
    "description": "Number of keys required to complete the goal"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `"range"` | Required |
| `range_start` | int | Minimum value (inclusive) |
| `range_end` | int | Maximum value (inclusive) |
| `default` | string or int | Default value |
| `description` | string | Shown to player |

### Text Choice

A dropdown with a fixed set of string values.

```json
"logic_difficulty": {
    "type": "text_choice",
    "choices": ["easy", "standard", "expert"],
    "default": "standard",
    "description": "Logic difficulty level"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `"text_choice"` | Required |
| `choices` | string array | The allowed values |
| `default` | string | Default choice (must be in `choices`) |
| `description` | string | Shown to player |

### Using Options in Logic

Options can be referenced in logic expressions on any entry type:

```
(Option: include_traps)                       // toggle: true if enabled
(Option: logic_difficulty == standard)        // text_choice: equality check
(Option: key_count >= 3)                      // range: numeric comparison
```

See [logic.md](logic.md) for the full option expression reference.

---

## Goals

Goals define completion conditions for the multiworld. Each goal is an Archipelago "goal" that a player can be assigned.

```json
"goals": [
    {
        "name": "any_key",
        "display": "Acquire Any Key",
        "description": "Collect at least one Key item",
        "logic": "(Item: Iron Key) OR (Item: Crystal Key)"
    },
    {
        "name": "all_keys",
        "display": "Acquire All Keys",
        "description": "Collect all Key items",
        "logic": "(Item: Iron Key) AND (Item: Crystal Key)"
    }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique identifier (used as option value in YAML) |
| `display` | string | Human-readable name |
| `description` | string | Description shown to player |
| `logic` | string | Logic expression evaluated as the completion condition |

When goals are declared, the apworld generates a `goal` option as a `text_choice` listing each goal's `name` as a valid value. Players set `goal: <name>` in their YAML before generating.

**If `goal` is left empty or not set**, the completion requirement falls back to the default: **all accessible in-logic locations checked**. This produces a warning both during generation (Archipelago output) and at runtime (framework log). If you intended to pick a specific goal, set the option explicitly.

**If the specified `goal` name does not match any declared goal**, a warning is emitted with a fuzzy suggestion if one exists (e.g. `Did you mean 'all_keys'?`), and the default applies. Check for typos in the goal name.

Goal logic supports the full expression grammar — `(Item:)`, `(Can Access:)`, `(Option:)`, `(Checked:)`, `AND`, `OR`. The `(Checked: LocationName)` predicate is available exclusively in goal logic and evaluates to true when the named location has been actually sent as a check to the AP server. See [logic.md — Checked Predicate](logic.md#checked-predicate--checked-x) for details and two-phase behavior.

A common pattern is pairing `(Can Access: X)` (ensures region reachability for fill) with `(Checked: X: Boss)` (ensures the in-game event actually occurred before the goal fires):

```json
{
    "name": "defeat_boss",
    "display": "Defeat the Boss",
    "description": "Obtain the Boss Key and defeat the final boss",
    "logic": "(Can Access: Boss Room) AND (Checked: Boss: Defeated)"
}
```

### Using `(Goal: X)` in region and item logic

The special `(Goal: goal_name)` expression lets other logic strings react to the player's active goal. It is syntactic sugar for `(Option: goal == goal_name)` and can appear anywhere an option expression is valid.

```json
"regions": [
    { "name": "Zone Beta", "logic": "(Item: Iron Key) OR (Goal: any_key)" }
]
```

With `goal: any_key`, `(Goal: any_key)` resolves to `True` at generation — Zone Beta is always accessible. With any other goal it requires Iron Key, unchanged. This is the recommended pattern for preventing goal-specific generation deadlocks.

Three forms are supported:

| Form | True when |
|---|---|
| `(Goal: name)` | The player selected this goal exactly (case-insensitive) |
| `(Goal: none)` | No goal is selected (all-locations completion mode) |
| `(Goal: ?)` | Any goal is set (not the no-goal default) |

> **Reserved name:** `none` must not be used as a goal `name`. The framework logs a warning if it is.

See [logic.md — Goal Selector](logic.md#goal-selector--goal-x) for the complete reference including case sensitivity, valid placement contexts, and evaluation semantics.

---

## Capabilities

The `capabilities` object declares the mod's contribution to AP generation: items, locations, regions, and cross-mod overrides.

```json
"capabilities": {
    "include": ["mymod/regions.json"],
    "regions": [ ... ],
    "items": [ ... ],
    "locations": [ ... ],
    "overrides": {
        "items": [ ... ],
        "locations": [ ... ]
    }
}
```

### `include`

Paths to template JSON files that are merged into this mod's capabilities before processing. Paths are relative to `Templates/<GameName>/`. See [templates.md](templates.md) for details.

```json
"include": ["mymod/regions.json"]
```

### Regions

Regions are named areas of the game world with optional access requirements.

```json
"regions": [
    { "name": "Mountain Pass" },
    { "name": "Deep Caves", "logic": "(Item: Iron Key)" },
    { "name": "Crystal Sanctum", "logic": "(Item: Iron Key) AND (Item: Crystal Key)" }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique region name |
| `logic` | string | Access requirement. Omit or leave empty for always-accessible regions. |

Regions form the graph that the tracker engine uses to compute reachable areas. A region with no `logic` (or empty logic) is always reachable from the start.

### Locations

Locations are check points in the game that the player fulfills to receive items.

```json
"locations": [
    { "name": "Mountain Pass: Supply Cache" },
    { "name": "Caves: Hidden Alcove", "logic": "(Can Access: Deep Caves)" },
    { "name": "Sanctum: Altar Chest", "logic": "(Can Access: Crystal Sanctum) AND (Item: Lantern)" },
    { "name": "Boss Chamber: Reward",
      "logic": "(Can Access: Boss Chamber) AND (Option: include_traps)" }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Location name — must be unique within this mod |
| `logic` | string | Access requirement. The first `(Can Access: R)` node determines both the AP sphere region and the tracker display group. |
| `priority` | `true` or option-logic | Location will always contain a progression item. Cannot be combined with `exclude` (priority wins if both active). |
| `exclude` | `true` or option-logic | Location will not contain progression items (gets filler or useful). Cannot be combined with `priority`. |

Locations with no `logic` are always accessible (sphere 0).

### Items

Items are the things that are shuffled into the multiworld item pool.

```json
"items": [
    { "name": "Iron Key",    "type": "progression", "amount": 1 },
    { "name": "Lantern",     "type": "useful",      "amount": 1 },
    { "name": "Data Shard",  "type": "filler",      "amount": 5 },
    { "name": "Trap Bomb",   "type": "trap",        "amount": 2,
      "logic": "(Option: include_traps)" },
    { "name": "Power Cell",  "type": "useful",      "amount": 1,
      "action": "MyMod.GrantPowerCell", "args": [] }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Item name — must be unique within this mod |
| `type` | string | `"progression"`, `"useful"`, `"filler"`, or `"trap"` |
| `amount` | int **or** string expression | Number of copies in the pool. Accepts an integer literal (legacy) or a string expression for option-driven quantity control. Use `"fill"` instead of the deprecated `-1` for the auto-balance filler. See [Expressive Item Quantities](#expressive-item-quantities) below. |
| `logic` | string | **Option-only** condition for including the item in the pool. `(Item:)` and `(Can Access:)` nodes are invalid here and evaluate to false with a warning. |
| `early` | `true` or option-logic | Request one copy be placed in sphere 1 (best-effort). Warning logged for filler/trap items. |
| `start` | `true` or option-logic | Give one copy to the player at game start. That copy is never placed in the pool. If `amount > 1`, remaining copies still go to pool. Requires a filler template (`amount: "fill"`) so auto-balance can fill the gap. |
| `local` | `true` or option-logic | Item must be placed in this player's world, not sent to another game. |
| `action` | string | Handler to call when this item is received. Format: `"ModName.HandlerName"`. If omitted, the framework calls `on_item_received` with no custom action. |
| `args` | array | Arguments passed to the action handler. See [Item Actions](#item-actions) below. |

**Item types:**
- `progression` — required for game completion; AP's sphere logic uses these to unlock checks
- `useful` — helpful but not required for completion; not critical for sphere balance
- `filler` — generic filler to pad the item pool
- `trap` — negative or annoying effect; AP can route these to other players

**Item logic** is option-only because items must be included or excluded before randomization begins, at which point only option values are known. See [logic.md — Scope Rules](logic.md#scope-rules-by-entry-type) for the restriction details.

---

## Expressive Item Quantities

The `"amount"` field accepts an integer literal **or** a string expression for option-driven quantity control.

**String expression forms:**

| Form | Example | Meaning |
|---|---|---|
| `"fill"` | `"amount": "fill"` | Auto-balance: fill all remaining pool slots. Preferred over deprecated `-1`. |
| `{key}` | `"amount": "{trap_count}"` | Option's integer value — `range` → int, `toggle` → 0/1. |
| `{key}%` | `"amount": "{bonus_fill_pct}%"` | `floor(location_count × value / 100)` copies, where `location_count` is the total number of in-logic locations for this generation. |
| Ternary | `"amount": "<condition> ? <value> : <value>"` | Conditional count. Condition = any boolean logic expression; values = any of the above forms or an integer literal. |

**`{key}` vs `(Option: key)`:**
- `{key}` — the option's **integer value**. Use in value positions (standalone or ternary branches).
- `(Option: key)` — a **boolean/comparison expression**. Use in ternary condition positions only.

`(Option: key)` as a standalone `"amount"` value is not valid — use `{key}` instead.

**Examples:**

```json
// Fixed count (unchanged behavior)
{ "name": "Iron Key", "type": "progression", "amount": 1 }

// Auto-balance filler
{ "name": "Data Shard", "type": "filler", "amount": "fill" }

// Count driven by a range option
{ "name": "Trap Bomb", "type": "trap", "amount": "{trap_count}" }

// Conditional count — include traps only when enabled
{ "name": "Trap Bomb", "type": "trap", "amount": "(Option: include_traps) ? {trap_count} : 0" }

// Compound condition — traps only when enabled AND count > 0
{ "name": "Trap Bomb", "type": "trap",
  "amount": "((Option: include_traps) AND (Option: trap_count > 0)) ? {trap_count} : 0" }

// Percentage of pool (requires a range option 0–100)
{ "name": "Trap Bomb", "type": "trap", "amount": "{trap_fill_pct}%" }
```

**Rules and anti-patterns:**

**Auto-balance + expression on the same item is a no-op.** If the auto-balance filler item and an option expression are both on the same item, the expression has no effect — auto-balance always compensates to maintain pool balance. Use a separate item:

```json
// ✗ WRONG — expression on fill item is a permanent no-op
{ "name": "Data Shard", "type": "filler", "amount": "{extra_count}" }

// ✓ CORRECT — separate fixed-count item from the auto-balance filler
{ "name": "Bonus Token", "type": "filler", "amount": "{extra_count}" }
{ "name": "Data Shard",  "type": "filler", "amount": "fill" }
```

**Pool overflow is clamped.** If an expression evaluates to more items than fit in the remaining pool, a warning is logged and the count is clamped. Design `range_end` values conservatively.

**Zero is valid.** `{key}` with a value of `0` produces zero copies — equivalent to exclusion. No warning.

**Unknown option → 0 + warning.** More conservative than the `"logic"` field behavior (which defaults permissive). An unexpected non-zero item count is more disruptive than an unexpectedly included item.

**Text-choice options have no integer value.** `{key}` where `key` is a `text_choice` → warning and returns 0. Use a comparison in a ternary condition instead: `"(Option: scope == hard) ? 3 : 1"`.

**`"fill"` + `"logic"` interaction:** `"logic"` controls whether the item is included at all. If `"logic"` evaluates to false, `"amount"` is irrelevant — item is excluded from the pool regardless.

**Multiple `"fill"` items are allowed.** Any number of mods may declare fill items. Remaining pool slots are distributed by random draw — each slot independently picks from all fill candidates (uniform probability). With two fill items, each gets roughly 50% of fill slots.

**Not supported (and will warn + return 0):**
- `(Item: X)` or `(Can Access: Region)` in amount conditions — runtime concepts, not known at generation
- `(Option: key)` as standalone amount (use `{key}` instead)
- Nested ternaries — use `"logic"` field + multiple items instead
- `{key}` where `key` is a `text_choice` option

---

## Placement Hints

Placement hints let mod authors influence *where in the generation sphere* their items and locations land. They map directly to Archipelago generation mechanisms and are evaluated at generation time using the player's current option values.

**Hint value semantics** (same for all 5 hint fields):
- **Omitted or `false`** — Hint inactive. No effect on generation.
- **`true`** (JSON bool) — Hint always active, regardless of player options.
- **Logic expression string** (e.g. `"(Option: ensure_early_keys)"`) — Hint active only when the expression evaluates to true given the player's chosen YAML options. Only `(Option:)`, `AND`, `OR`, `NOT`, `True`, `False` are valid — `(Item:)` and `(Can Access:)` are invalid in hint expressions and evaluate to `False` (hint inactive).

**Item hints (`early`, `start`, `local`):**

```json
{ "name": "Gate Key", "type": "progression", "amount": 1,
  "early": "(Option: ensure_early_gate)",
  "local": "(Option: keep_keys_local)" }

{ "name": "Starting Compass", "type": "useful", "amount": 1,
  "start": true }
```

| Hint | AP Mechanism | Effect |
|---|---|---|
| `early` | `local_early_items[player][name] += 1` | Best-effort: one copy placed in sphere 1. Warning if applied to a filler or trap item. |
| `start` | `push_precollected(item)` + reduce pool count by 1 | One copy given at game start; that copy never enters the pool. Requires a filler template (`amount: "fill"`) so auto-balance fills the gap. |
| `local` | `local_items[player].add(item_id)` | Item must be placed in this player's world, not sent to other games. |

**Location hints (`priority`, `exclude`):**

```json
{ "name": "Main Story Vault", "priority": true }
{ "name": "Optional Bonus Cache", "exclude": "(Option: skip_bonus)" }
```

| Hint | AP Mechanism | Effect |
|---|---|---|
| `priority` | `options.priority_locations.value.add(name)` | Location will always contain a progression item. |
| `exclude` | `options.exclude_locations.value.add(name)` | Location will not contain progression items (gets filler or useful). |

**Key rules:**
- `early` + `local` together gives the strongest early-game guarantee: sphere-1 AND in this world.
- `start` + `amount: 1` produces zero copies in the pool. The filler template compensates.
- `priority` and `exclude` on the same location: warning logged, `priority` takes precedence.
- Hints are generation-time only and have no effect on the C++ tracker's access-rule logic.

---

## Item Actions

When a player receives an item, the framework sends an `EXECUTE_ACTION` message to the mod. If `action` is specified, the mod's registered handler is called; otherwise only `on_item_received` fires.

```json
{
    "name": "Power Cell",
    "type": "useful",
    "amount": 1,
    "action": "MyMod.GrantPowerCell",
    "args": [
        { "name": "tier", "type": "number", "value": 2 },
        { "name": "permanent", "type": "boolean", "value": true },
        { "name": "player_level", "type": "property", "value": "MyMod.state.player_level" }
    ]
}
```

The `action` string format is `"ModName.HandlerName"` — the framework routes the call to the mod whose Lua module registered the handler under that name.

### Action Argument Types

| Type | JSON value | Description |
|---|---|---|
| `"string"` | `"some text"` | Plain string |
| `"number"` | `42` or `3.14` | Numeric value |
| `"boolean"` | `true` or `false` | Boolean |
| `"property"` | `"MyMod.state.player_level"` | A dot-separated path into the Lua global state. The framework navigates the path at call time and passes the resolved Lua value as the argument. Returns `nil` if the path doesn't exist. Useful for passing live game state to action handlers. |

Arguments are passed to the Lua handler in order. The handler receives them as standard Lua values.

---

## Cross-Mod Overrides

The `overrides` section inside `capabilities` allows one mod to modify another mod's items or locations. This is the mechanism for cross-mod integration.

### Item Overrides

Change the type classification of an item defined in another mod, conditionally based on options:

```json
"overrides": {
    "items": [
        {
            "target_item": "Crystal Key",
            "target_mod": "author.mygame.basemod",
            "type": "filler",
            "logic": "(Option: logic_difficulty == easy)"
        }
    ]
}
```

| Field | Type | Description |
|---|---|---|
| `target_item` | string | Name of the item to override |
| `target_mod` | string | `mod_id` of the mod that owns the item |
| `type` | string | New item type (`"progression"`, `"useful"`, `"filler"`, `"trap"`) |
| `logic` | string | Option-only condition. Override applies only when this evaluates to `true`. |

**Use case:** A companion mod downgrades a key item from `progression` to `filler` when easy mode is active, because that item is no longer needed for the easy-mode game flow.

### Location Overrides

Add an alternative access path to a location defined in another mod:

```json
"overrides": {
    "locations": [
        {
            "name": "Caves: Hidden Alcove",
            "target_mod": "author.mygame.basemod",
            "logic": "(Item: Lantern)"
        }
    ]
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Name of the target location |
| `target_mod` | string | `mod_id` of the mod that owns the location |
| `logic` | string | Additional access logic, OR-merged with the existing logic |

The resulting combined logic is `(original_logic) OR (override_logic)`. Multiple mods can each add their own OR branch. This enables easy-mode variants or cross-game item integrations without modifying the original mod.

---

## Vocabulary Validation

When `"vocab_validation": true`, all item, location, and region names are validated against game-specific vocabulary files in `Templates/<GameName>/`. If a name is not recognized, the framework logs a warning during manifest loading.

This opt-in feature catches typos in large manifests early, before generation. See [templates.md](templates.md) for how vocabulary files are structured.

---

## Best Practices: Avoiding Deadlocks and Softlocks

Archipelago's fill algorithm requires at least one location to be reachable with no items, and every progression item must be placeable in a reachable location before the items that gate further locations are distributed. Violations produce a `FillError` at generation time. The patterns below describe how each manifest feature can go wrong and how to prevent it.

### Sphere-0 minimum

Archipelago requires at least one location to be accessible from the starting state (no items collected). If every location in your mod is gated by at least one item, generation will always fail. Ensure at least one location has no `logic` or has logic that simplifies to `True` before any items are placed.

```json
// BAD — all locations require items; nothing accessible at generation start
{ "name": "Zone Alpha: Chest", "logic": "(Item: Iron Key)" }

// GOOD — one free location always accessible
{ "name": "Zone Alpha: Free Chest" }                     // no logic
{ "name": "Zone Alpha: Key Cache", "logic": "(Item: Iron Key)" }
```

### Option-conditional items and location consistency

If a location's logic requires an item that is conditionally excluded from the pool via `"logic"`, that location becomes unfillable when the option that removes the item is active. Always apply the same option condition to the location or keep the item unconditional.

```json
// BAD — SpecialKey excluded when vault_mode=false, but Vault requires it unconditionally
{ "name": "SpecialKey", "type": "progression", "logic": "(Option: vault_mode)" }
{ "name": "Vault: Access", "logic": "(Item: SpecialKey)" }

// GOOD — location excluded when item is excluded
{ "name": "Vault: Access", "logic": "(Option: vault_mode) AND (Item: SpecialKey)" }
```

### Option-conditional regions

All locations inside a region become out-of-logic when the region itself is inaccessible. If those locations hold progression items needed by other logic paths, you can create a deadlock where the items required to open the region are locked inside it.

When a region's logic is option-conditional (e.g., `"logic": "(Option: hard_mode)"`), ensure that every progression item inside that region is either also option-conditional or exists in a copy outside the region. Otherwise the fill algorithm will find no valid placement.

### Goal-conditional region access and sphere-0 deadlocks

When a region's access logic is keyed to an item, every progression item needed to access that region must be reachable from sphere 0 locations. If the only sphere-0 location receives the "wrong" key (a key that doesn't open the region), the fill algorithm cannot place the remaining keys anywhere accessible and fails.

The `(Goal: X)` expression solves this class of problem for goal-dependent regions. If a region requires `(Item: Iron Key)` to prevent trivial access, but the `any_key` goal makes Iron Key non-special, you can write:

```json
{ "name": "Zone Beta", "logic": "(Item: Iron Key) OR (Goal: any_key)" }
```

With `goal: any_key` active, Zone Beta becomes sphere-0 accessible, providing additional fill locations and eliminating the deadlock. With all other goals, Zone Beta still requires Iron Key.

### `start` hint and item count

`"start": true` removes one copy from the pool before randomization. If `"amount": 1` and `"start": true`, zero copies remain in the pool. Ensure a filler template (`"amount": "fill"`) exists to absorb the missing slot; without it, the item pool will be one item short and generation will fail.

```json
// amount: 1 + start: true → pool count = 0 → filler template required
{ "name": "Compass", "type": "useful", "amount": 1, "start": true }
{ "name": "Data Shard", "type": "filler", "amount": "fill" }   // auto-fills the gap
```

### `early` hint (best-effort, not guaranteed)

`"early"` requests that one copy land in sphere 1, but Archipelago makes no hard guarantee — if sphere 1 is too constrained, the request may not be satisfied. It will not cause a `FillError`; it simply may not be honored. For a hard sphere-1 guarantee, `"local"` combined with `"early"` is the strongest available hint, but neither prevents the fill from placing the item later if necessary.

### `priority` and `exclude` on the same location

Declaring both `"priority"` and `"exclude"` on the same location (by having both evaluate to `true` simultaneously) is a contradiction. The framework logs a warning and `priority` takes precedence. Avoid writing logic where this can occur.

### Cross-region logic and circular dependencies

Region logic should form a directed acyclic graph. If Region A requires Region B to be reachable, and Region B requires Region A, neither can ever become reachable — all locations inside both regions are permanently blocked. Always ensure there is a directed path from the always-reachable starting regions to every other region.

```json
// BAD — circular dependency; neither region is ever reachable
{ "name": "Zone A", "logic": "(Can Access: Zone B)" }
{ "name": "Zone B", "logic": "(Can Access: Zone A)" }
```

### Goal-conditional content consistency

`(Goal: X)` creates goal-specific items or locations. When the wrong goal is active, those items are excluded from the pool and those locations are out-of-logic. Apply the goal condition consistently:

```json
// BAD — location requires GoalItem, but GoalItem excluded when goal != special_goal
{ "name": "GoalItem", "type": "progression", "logic": "(Goal: special_goal)" }
{ "name": "Vault: Boss Chamber", "logic": "(Item: GoalItem)" }

// GOOD — location also conditional on the same goal
{ "name": "Vault: Boss Chamber", "logic": "(Goal: special_goal) AND (Item: GoalItem)" }
```

`(Goal: X) OR (Goal: Y)` is valid and expresses "open when either of these goals is selected."

### Accessibility checker

Archipelago checks location accessibility at generation time. A "Could not access required locations for accessibility check" error means at least one location is unreachable under the generated option/goal combination. Check the generator log carefully — it lists the specific locations that failed, which identifies which option or item gate is incorrectly configured.

---

## Full Example

The following manifest exercises every feature: options, goals, regions, locations with access logic, items with option gating and actions, and cross-mod overrides.

```json
{
    "mod_id": "author.mygame.mymod",
    "name": "My Game Mod",
    "version": "1.0.0",
    "enabled": true,
    "description": "A complete example mod demonstrating all manifest features",
    "depends": ["author.mygame.basemod"],

    "options": {
        "logic_difficulty": {
            "type": "text_choice",
            "default": "standard",
            "choices": ["easy", "standard", "expert"],
            "description": "Logic difficulty level"
        },
        "include_traps": {
            "type": "toggle",
            "default": false,
            "description": "Include trap items in the pool"
        },
        "key_count": {
            "type": "range",
            "default": 3,
            "range_start": 1,
            "range_end": 10,
            "description": "Number of keys required"
        }
    },

    "goals": [
        {
            "name": "any_key",
            "display": "Acquire Any Key",
            "description": "Collect at least one Key",
            "logic": "(Item: Iron Key) OR (Item: Crystal Key)"
        },
        {
            "name": "all_keys",
            "display": "Acquire All Keys",
            "description": "Collect all Keys",
            "logic": "(Item: Iron Key) AND (Item: Crystal Key)"
        }
    ],

    "capabilities": {
        "regions": [
            { "name": "Mountain Pass" },
            { "name": "Deep Caves",      "logic": "(Item: Iron Key)" },
            { "name": "Crystal Sanctum", "logic": "(Item: Iron Key) AND (Item: Crystal Key)" }
        ],

        "items": [
            { "name": "Iron Key",    "type": "progression", "amount": 1 },
            { "name": "Crystal Key", "type": "progression", "amount": 1 },
            { "name": "Lantern",     "type": "useful",      "amount": 1,
              "action": "MyMod.GrantLantern", "args": [] },
            { "name": "Data Shard",  "type": "filler",      "amount": "fill" },
            { "name": "Trap Bomb",   "type": "trap",        "amount": 2,
              "logic": "(Option: include_traps)" }
        ],

        "locations": [
            { "name": "Mountain Pass: Supply Cache" },
            { "name": "Mountain Pass: Key Cache",
              "logic": "(Item: Iron Key)" },
            { "name": "Caves: Hidden Alcove",
              "logic": "(Can Access: Deep Caves)" },
            { "name": "Caves: Deep Vault",
              "logic": "(Can Access: Deep Caves) AND (Item: Crystal Key)" },
            { "name": "Sanctum: Altar Chest",
              "logic": "(Can Access: Crystal Sanctum)" },
            { "name": "Sanctum: Difficulty Bonus",
              "logic": "(Can Access: Crystal Sanctum) AND ((Option: logic_difficulty == standard) OR (Option: logic_difficulty == expert))" }
        ],

        "overrides": {
            "items": [
                {
                    "target_item": "Some Base Item",
                    "target_mod": "author.mygame.basemod",
                    "type": "filler",
                    "logic": "(Option: logic_difficulty == easy)"
                }
            ],
            "locations": [
                {
                    "name": "Mountain Pass: Key Cache",
                    "target_mod": "author.mygame.basemod",
                    "logic": "(Item: Crystal Key)"
                }
            ]
        }
    }
}
```

---

*See also: [logic.md](logic.md) for the full logic expression reference | [templates.md](templates.md) for the `include` field and vocabulary validation | [mods.md](mods.md) for how Lua registers item action handlers | [publishing.md](publishing.md) for versioning and registry publishing*
