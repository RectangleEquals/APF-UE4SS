# Tracker Engine

The AP Framework includes a real-time accessibility tracker that computes 0.0–1.0 scores for every location and region as the player receives items. Mods can subscribe to receive this data and use it to build tracker UIs, drive game behavior, or implement custom logic-based systems.

> **Note:** This document describes the framework-side tracker engine and the data it produces. Individual tracker mods for specific games consume this data to render in-game UIs. This document is relevant to any mod that wants to subscribe to tracker data.

---

## How It Works

The tracker engine (`APTrackerEngine`) runs on the framework side. It:

1. **Initializes** after capabilities are finalized and the AP server connection establishes. It pre-parses all location and region logic strings into ASTs, evaluates option values, and simplifies the trees — this work is done once so per-tick evaluation is fast.

2. **Computes reachability** using fixed-point iteration over the region graph (see [logic.md — Region Reachability](logic.md#region-reachability)).

3. **Scores every location** by calling `evaluate_scored(logic_node, state)` for each location's pre-parsed AST, producing a 0.0–1.0 float and a full `ScoredNode` tree.

4. **Delivers results** to subscribers via IPC:
   - A full `TRACKER_SNAPSHOT` when a mod first subscribes
   - Incremental `TRACKER_UPDATE` messages whenever item state changes (item received or location checked)

5. **Manages subscribers** — mods call `subscribe_tracker()` to join and `unsubscribe_tracker()` to leave.

Computation runs on the `Snap-Worker` background thread to avoid blocking the game thread. Large snapshots are automatically transported via the multipart chunked IPC transport.

---

## Subscribing

```lua
APClient.on_state_active(function()
    APClient.subscribe_tracker()
end)

APClient.on_tracker_snapshot(function(snapshot)
    -- full state — received once on subscribe
    handle_snapshot(snapshot)
end)

APClient.on_tracker_update(function(delta)
    -- incremental update — received when item state changes
    handle_update(delta)
end)
```

- Call `subscribe_tracker()` after `ACTIVE` state is reached.
- You will receive a `TRACKER_SNAPSHOT` soon after subscribing (computation is async, may take up to ~100ms for large games).
- After the snapshot, any time an item is received or a location is checked, you receive a `TRACKER_UPDATE` with only the changed entries.
- On disconnect and reconnect, call `subscribe_tracker()` again during the next `ACTIVE` state to re-subscribe and receive a fresh snapshot.

---

## TRACKER_SNAPSHOT Schema

The snapshot contains two categories of data: **static ecosystem metadata** (does not change during a session) and **dynamic state** (changes as items are received and locations are checked).

### Static Metadata

```json
{
    "mods": [
        {
            "mod_id": "author.mygame.mymod",
            "name": "My Game Mod",
            "version": "1.0.0",
            "location_count": 24,
            "item_count": 8,
            "region_count": 4,
            "goal_count": 2,
            "override_count": 0
        }
    ],
    "regions_meta": [
        {
            "name": "Mountain Pass",
            "merged_logic": "",
            "contributions": [
                { "mod_id": "author.mygame.mymod", "logic": "" }
            ]
        },
        {
            "name": "Deep Caves",
            "merged_logic": "(Item: Iron Key)",
            "contributions": [
                { "mod_id": "author.mygame.mymod", "logic": "(Item: Iron Key)" }
            ]
        }
    ],
    "locations_meta": [
        {
            "id": 6942100,
            "name": "Mountain Pass: Supply Cache",
            "display_region": "Mountain Pass",
            "mod_id": "author.mygame.mymod",
            "logic": "(Can Access: Mountain Pass)"
        }
    ],
    "items_meta": [
        {
            "id": 6942067,
            "name": "Iron Key",
            "type": "progression",
            "original_type": "progression",
            "mod_id": "author.mygame.mymod",
            "logic": ""
        }
    ],
    "options": {
        "logic_difficulty": "standard",
        "include_traps": false
    }
}
```

| Field | Description |
|---|---|
| `mods[]` | Per-mod summary: counts of locations, items, regions, goals, overrides contributed |
| `regions_meta[]` | All declared regions with merged logic and per-mod contributions |
| `locations_meta[]` | All locations with their static metadata (ID, name, display region, owning mod, logic string) |
| `items_meta[]` | All items with type, original type (before overrides), owning mod, and option logic |
| `options{}` | Key-value map of all player option values for this session |

The static metadata arrives once in the snapshot and does not change during a session. Use it to build index tables (location ID → name, name → region, etc.) that you can reference during updates.

### Dynamic State

```json
{
    "locations": [
        {
            "id": 6942100,
            "name": "Mountain Pass: Supply Cache",
            "display_region": "Mountain Pass",
            "score": 1.0,
            "checked": false,
            "out_of_logic": false,
            "logic_tree": { ... }
        }
    ],
    "regions": [
        {
            "name": "Mountain Pass",
            "score": 1.0,
            "reachable": true,
            "logic_tree": { ... }
        },
        {
            "name": "Deep Caves",
            "score": 0.0,
            "reachable": false,
            "logic_tree": { ... }
        }
    ],
    "received_items": {
        "Lantern": 1
    },
    "checked_locations": [6942100],
    "goal": {
        "name": "all_keys",
        "display": "Acquire All Keys",
        "description": "Collect all Key items",
        "score": 0.5,
        "no_goal_mode": false
    }
}
```

| Field | Description |
|---|---|
| `locations[]` | All locations with current score, checked status, out-of-logic flag, and full scored AST tree |
| `regions[]` | All regions with current score, reachability status, and AST |
| `received_items{}` | Map of item name → count received so far |
| `checked_locations[]` | Array of location IDs that have been checked |
| `goal{}` | Current goal status — see [Goal Status Object](#goal-status-object) below |

---

## Dynamic Location Entry

Each entry in `locations[]` and `regions[]`:

| Field | Type | Description |
|---|---|---|
| `id` | int64 | Location ID (matches `locations_meta[i].id`) |
| `name` | string | Location name |
| `display_region` | string | Display group derived from first `(Can Access: R)` in logic |
| `score` | float | 0.0–1.0 accessibility score |
| `checked` | bool | True if this location has been checked |
| `out_of_logic` | bool | True if the location's logic simplified to `Const(false)` at generation — the location was pruned from the multiworld (option-gated content that was turned off). It is never reachable; exclude it from any display or count logic in your UI. |
| `logic_tree` | object | Recursive scored AST — see below |

Region entries use `name` instead of `id` (regions are identified by name), and `reachable` instead of `checked`. Regions do not have an `out_of_logic` field.

---

## ScoredNode Tree

The `logic_tree` field is a recursive tree mirroring the AST structure of the location's logic expression. Every node carries its own score, enabling per-expression color-coding in tracker UIs.

### Node Structure

```json
{
    "type": "and",
    "score": 0.5,
    "display": "(Can Access: Deep Caves) AND (Item: Iron Key)",
    "children": [
        {
            "type": "can_access",
            "score": 0.0,
            "display": "(Can Access: Deep Caves)",
            "children": []
        },
        {
            "type": "item",
            "score": 1.0,
            "display": "(Item: Iron Key)",
            "children": []
        }
    ]
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | Node type: `"const"`, `"item"`, `"can_access"`, `"option"`, `"and"`, `"or"` (all lowercase) |
| `score` | float | 0.0–1.0 score for this node |
| `display` | string | Human-readable text representation of this expression |
| `children` | array | Child nodes (empty for leaf nodes) |

### Score Interpretation

| Score | Typical UI color | Meaning |
|---|---|---|
| `1.0` | Green | Fully satisfied |
| `0 < score < 1.0` | Yellow | Partially satisfied (e.g., 1 of 3 required items) |
| `0.0` | Red | Not satisfied |

### Scoring Rules

| Node type | Score formula |
|---|---|
| `Const(true)` | `1.0` |
| `Const(false)` | `0.0` |
| `Item(name, count)` | `min(received / required, 1.0)` — partial credit |
| `CanAccess(region)` | `1.0` if reachable, `0.0` otherwise |
| `Option(...)` | Always `1.0` at runtime — all option nodes are resolved to `Const` during initialization before scoring begins |
| `And(children)` | average of all children scores |
| `Or(children)` | maximum of all children scores |

See [logic.md — Scored Evaluation](logic.md#runtime-c-tracker) for the full scoring algorithm description.

---

## TRACKER_UPDATE Schema

Updates have the same structure as the dynamic state section of the snapshot. **Every update includes all locations and all regions** — entries are not filtered to only changed ones. Replace your entire cached location and region state on each update; do not attempt to merge individual fields.

The update also includes the current goal status object.

```json
{
    "locations": [
        { "id": 6942101, "name": "Caves: Hidden Alcove", "display_region": "Deep Caves",
          "score": 1.0, "checked": false, "out_of_logic": false, "logic_tree": { ... } }
    ],
    "regions": [
        { "name": "Deep Caves", "score": 1.0, "reachable": true, "logic_tree": { ... } }
    ],
    "received_items": { "Iron Key": 1 },
    "checked_locations": [],
    "goal": {
        "name": "all_keys",
        "display": "Acquire All Keys",
        "description": "Collect all Key items",
        "score": 0.5,
        "no_goal_mode": false
    }
}
```

**Merging updates:** Replace `locations`, `regions`, `received_items`, `checked_locations`, and `goal` in their entirety from each update. The `checked_locations` array is the authoritative source of which locations have been checked — always re-apply it to `locations` entries after merging (a location entry may have `checked: false` if its score changed, but if the ID is in `checked_locations`, treat it as checked).

---

## Goal Status Object

Both `TRACKER_SNAPSHOT` and `TRACKER_UPDATE` include a `goal` object at the top level of the dynamic state payload. It describes the player's active goal and current progress toward it.

```json
{
    "name": "all_keys",
    "display": "Acquire All Keys",
    "description": "Collect all Key items",
    "score": 0.5,
    "no_goal_mode": false
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Internal goal name from manifest (empty string in `no_goal_mode`) |
| `display` | string | Human-readable goal display name (empty in `no_goal_mode`) |
| `description` | string | Goal description text (empty in `no_goal_mode`) |
| `score` | float | 0.0–1.0 progress toward completion |
| `no_goal_mode` | bool | True when no goal is selected or no goals are defined — completion mode is "all in-logic locations checked" |

**Score semantics:**
- When `no_goal_mode: true`: `score = checked_in_logic / total_in_logic` — fraction of non-out-of-logic locations that have been checked
- When `no_goal_mode: false`: `score` = `evaluate_scored(goal_logic_node, state).score` — uses the same `And`/`Or`/`Item`/`CanAccess` scoring rules as location logic

**Example display pattern:**

```lua
local g = snapshot.goal or {}
if g.no_goal_mode then
    -- "All In-Logic Locations: 8/15 (53%)"
    local pct = math.floor((g.score or 0.0) * 100)
    widget:SetGoalStatus("", "All In-Logic Locations", g.score or 0.0)
else
    -- "Acquire All Keys: 50%"
    widget:SetGoalStatus(g.name or "", g.display or "Goal", g.score or 0.0)
end
```

---

## Display Region Derivation

The `display_region` field on each location is computed by the tracker engine from the location's logic — it is not stored in the manifest. The algorithm:

1. Scan the location's logic string for the first `(Can Access: RegionName)` pattern
2. If found, use `RegionName` as the display group
3. If not found: if the location name contains `": "`, use the prefix (e.g., `"Mountain Pass: Supply Cache"` → `"Mountain Pass"`)
4. Final fallback: `"Main"`

This means the display grouping is entirely determined by how you write your location logic. Locations with no `(Can Access:)` reference always appear in the `"Main"` group.

---

## Performance

- Snapshot computation: ~18ms for 500+ locations on typical hardware (runs on Snap-Worker thread, not game thread)
- Update computation: faster than snapshot (skips static metadata rebuild)
- Large snapshots (>48KB): automatically transported via zlib-compressed multipart chunks — transparent to the subscriber
- Updates are incremental: only changed entries are sent, minimizing per-tick IPC traffic

---

## Example: Building a Location Index

```lua
local location_by_id = {}
local location_by_region = {}  -- region_name → list of locations

APClient.on_tracker_snapshot(function(snapshot)
    -- Index static metadata once
    for _, loc_meta in ipairs(snapshot.locations_meta or {}) do
        location_by_id[loc_meta.location_id] = {
            name = loc_meta.name,
            display_region = loc_meta.display_region,
            mod_id = loc_meta.mod_id
        }
    end

    -- Process dynamic state
    apply_dynamic_state(snapshot)
end)

APClient.on_tracker_update(function(delta)
    apply_dynamic_state(delta)
end)

function apply_dynamic_state(data)
    location_by_region = {}
    for _, loc in ipairs(data.locations or {}) do
        local region = loc.display_region or "Main"
        if not location_by_region[region] then
            location_by_region[region] = {}
        end
        table.insert(location_by_region[region], loc)
    end
end
```

---

*See also: [logic.md](logic.md) for the ScoredNode scoring algorithm | [mods.md](mods.md) for the `subscribe_tracker()` Lua API | [framework.md](framework.md) for the IPC message types*
