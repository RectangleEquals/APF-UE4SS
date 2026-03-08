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

When more than one goal is declared (across all mods in a multiworld), the apworld automatically generates a `goal` option as a `text_choice` with each goal's `name` as a choice. Players select their goal in their YAML before generating. If only one goal exists, it is used unconditionally.

Goal logic supports the full expression grammar — `(Item:)`, `(Can Access:)`, `(Option:)`, `AND`, `OR`.

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
    { "name": "Boss Chamber: Reward", "amount": 3,
      "logic": "(Can Access: Boss Chamber) AND (Option: include_traps)" }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Location name — must be unique within this mod |
| `amount` | int | Number of separate check instances. Default: `1`. Use when the same "location type" occurs N times. Checks as `"Location Name 1"` through `"Location Name N"`. |
| `logic` | string | Access requirement. The first `(Can Access: R)` node determines both the AP sphere region and the tracker display group. |

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
| `amount` | int | Number of copies in the pool. `-1` signals a filler template: the apworld fills remaining item slots with copies of this item after all other items are placed. |
| `logic` | string | **Option-only** condition for including the item in the pool. `(Item:)` and `(Can Access:)` nodes are invalid here and evaluate to false with a warning. |
| `action` | string | Handler to call when this item is received. Format: `"ModName.HandlerName"`. If omitted, the framework calls `on_item_received` with no custom action. |
| `args` | array | Arguments passed to the action handler. See [Item Actions](#item-actions) below. |

**Item types:**
- `progression` — required for game completion; AP's sphere logic uses these to unlock checks
- `useful` — helpful but not required for completion; not critical for sphere balance
- `filler` — generic filler to pad the item pool
- `trap` — negative or annoying effect; AP can route these to other players

**Item logic** is option-only because items must be included or excluded before randomization begins, at which point only option values are known. See [logic.md — Scope Rules](logic.md#scope-rules-by-entry-type) for the restriction details.

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
            { "name": "Data Shard",  "type": "filler",      "amount": -1 },
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

*See also: [logic.md](logic.md) for the full logic expression reference | [templates.md](templates.md) for the `include` field and vocabulary validation | [mods.md](mods.md) for how Lua registers item action handlers*
