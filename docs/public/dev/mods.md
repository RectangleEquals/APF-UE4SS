# Building a Game Mod

This guide covers how to create an AP Framework game mod — a UE4SS mod that integrates a game with Archipelago Multiworld Randomizer. The framework handles AP server communication; your mod handles game-specific logic.

> **Note:** AP Framework currently supports Lua and Blueprint UE4SS mods. C++ UE4SS mods may also be supportable via direct APClientLib linkage, but this is currently untested and undocumented.

---

## What is an AP Mod?

An AP mod is any UE4SS mod folder that contains a `manifest.json` with a `mod_id` field. The framework discovers these manifests on startup, aggregates their items/locations/regions into the Archipelago data package, and routes items and location checks to the correct mod.

Minimum required structure:

```
Mods/
└── YourModName/
    ├── manifest.json    ← declares mod_id and capabilities
    └── Scripts/
        └── main.lua    ← Lua mod entry point
```

---

## Quick Start

### 1. Create `manifest.json`

```json
{
    "mod_id": "yourname.yourgame.yourmod",
    "name": "Your Game Mod",
    "version": "1.0.0",
    "enabled": true,
    "capabilities": {
        "items": [
            { "name": "Key", "type": "progression", "amount": 1 },
            { "name": "Coin", "type": "filler", "amount": 10 }
        ],
        "locations": [
            { "name": "World 1: Chest" },
            { "name": "World 1: Boss Reward", "logic": "(Item: Key)" }
        ]
    }
}
```

### 2. Create `Scripts/main.lua`

```lua
local ok, APClient = pcall(require, "APClientLib")
if not ok then print("[MyMod] Failed to load APClientLib") return end

local is_registered = false

-- Tick hook: call APClient.update() regularly
RegisterHook("/Game/.../SomeFrequentlyCalledBP:Tick", function()
    APClient.update()
end)

-- Register when the framework asks
APClient.on_lifecycle(function(state, message)
    if state == "REGISTRATION" and not is_registered then
        APClient.register_mod()
        is_registered = true
    end
end)

APClient.on_registration_success(function()
    print("[MyMod] Registered with framework")
end)

-- Receive items and apply them in-game
APClient.on_item_received(function(item_id, item_name, sender, meta)
    print("[MyMod] Received: " .. item_name .. " from " .. sender)
    -- Apply the item to the game here
    game_give_item(item_name)
end)

APClient.on_state_active(function()
    print("[MyMod] Connected and active")
end)

-- Connect to the framework IPC
APClient.connect()
```

### 3. Deploy

Use APF Manager to deploy your mod. It adds your mod to `mods.txt` and copies the framework DLLs alongside it.

### 4. Generate

Run the Archipelago generator with `apf.apworld` installed. Your mod's items and locations will appear in the output.

### 5. Play

Launch the game. The framework connects to the AP server automatically using settings from `APFramework.json` (configured via the in-game UI widget).

> **Want to publish your mod?** See [publishing.md](publishing.md) for how to create a GitHub registry that players can add directly in APF Manager.

---

## mod_id Conventions

```
author.game.modname
```

Examples:
- `author.mygame.mymod` — regular game mod
- `author.mygame.companion` — another game mod
- `archipelago.mygame.tracker` — priority client (tracker mod)
- `archipelago.mygame.framework` — priority client (framework UI mod)

**Priority mods** use the prefix `archipelago.<game_name>.*`. This causes the framework to:
- Register them during `PRIORITY_REGISTRATION` (earlier phase, 30-second window)
- Grant access to admin commands (`cmd_restart`, `get_mods`, `get_logs`, `set_config`, etc.)
- **Must NOT declare capabilities** — priority clients have no items, locations, or regions. They connect for admin access, UI, or tooling purposes only.

Use the priority prefix only if your mod is an infrastructure mod (tracker, UI, admin tools). Game content mods should use the regular `author.game.modname` format.

> **Publishing:** The `mod_id` format is also used for dependency declarations and conflict detection when installing from a registry. See [publishing.md](publishing.md).

---

## Lua API Reference

`APClient` is the module returned by `require("APClientLib")`. Each `require` call creates an independent per-mod context — callbacks and IPC attribution are isolated.

### Connection

| Function | Returns | Description |
|---|---|---|
| `APClient.connect()` | `bool` | Connect to the framework IPC pipe. Should be called at the end of `main.lua` after all callbacks are registered. |
| `APClient.disconnect()` | — | Disconnect from the IPC pipe. |
| `APClient.is_connected()` | `bool` | True if the IPC pipe is currently connected. |
| `APClient.update()` | — | Poll the IPC pipe and dispatch queued messages. Must be called regularly (every tick or sub-second interval). |
| `APClient.get_current_state()` | `string` | The last lifecycle state string received from the framework. |

### Registration

| Function | Returns | Description |
|---|---|---|
| `APClient.register_mod()` | `bool` | Send a registration request to the framework. Call this when you receive `PRIORITY_REGISTRATION` (priority mods) or `REGISTRATION` (regular mods) in `on_lifecycle`. |

### Locations

| Function | Returns | Description |
|---|---|---|
| `APClient.check_location(name)` | `bool` | Report a location as checked. |
| `APClient.get_location(id_or_name)` | table or `nil` | Look up a location by ID (integer) or name (string). Returns `nil` if not found. |
| `APClient.scout_locations(names_table)` | `bool` | Scout a list of locations (learn their contents without checking). The result arrives via `on_message` with type `"location_info"`. |

**`get_location` return table fields:**

| Field | Type | Description |
|---|---|---|
| `id` | int64 | Unique location ID. |
| `name` | string | Location name. |
| `checked` | bool | `true` if this location has been sent as a check (either this session via `check_location`, or as reported by the framework via a tracker snapshot/update). |

### Tracker

| Function | Returns | Description |
|---|---|---|
| `APClient.subscribe_tracker()` | `bool` | Subscribe to tracker engine updates. Call after `ACTIVE`. You will receive a `TRACKER_SNAPSHOT` followed by `TRACKER_UPDATE` messages as state changes. |
| `APClient.unsubscribe_tracker()` | `bool` | Stop receiving tracker updates. |

### Cross-Mod API

| Function | Returns | Description |
|---|---|---|
| `APClient.register_api(table)` | — | Publish functions for other mods to call. Keys are function names; values are Lua functions. |
| `APClient.get_api(target_mod_id)` | proxy table | Get a proxy for another mod's registered API. Calling `proxy.func(args)` routes through the framework to the target mod and returns the result synchronously (with a timeout). |

### Messaging (Priority Mods)

| Function | Returns | Description |
|---|---|---|
| `APClient.command(cmd, payload?)` | `bool` | Send an admin command to the framework. Only works for priority clients. |
| `APClient.send_to(target_mod_id, payload_table)` | `bool` | Send a custom message to a specific mod. Arrives as `on_message` with the payload. |
| `APClient.broadcast(payload_table)` | `bool` | Send a custom message to all connected mods. |

### Database

| Function | Returns | Description |
|---|---|---|
| `APClient.db_open(path)` | `bool` | Open an SQLite database at the given path. |
| `APClient.db_query(sql)` | table or nil | Execute a SQL query and return results as a Lua table. |
| `APClient.db_close()` | — | Close the current database. |
| `APClient.db_is_open()` | `bool` | True if a database is currently open. |

### Logging

| Function | Returns | Description |
|---|---|---|
| `APClient.log(level, message)` | — | Write a log entry through the framework logger. `level` is one of `"trace"`, `"debug"`, `"info"`, `"warn"`, `"error"`, `"fatal"`. Appears in `ap_framework.log` attributed to your mod_id. |

### Item Notifications

| Function | Returns | Description |
|---|---|---|
| `APClient.item_handled(id_or_name [, silence [, delivery_index]])` | — | Mark an item as handled by this mod. `id_or_name` is the item ID (int64) or item name (string). All future `on_item_received` callbacks for this item (to all mods) will have `meta.handled_by` set to this mod's `mod_id`. If `silence` is `true` and `delivery_index` is provided, that specific delivery is permanently suppressed for this mod (persisted across reconnects). `delivery_index` is required for silencing — without it, `silence=true` is a no-op. Default: `silence = false`. |

**`on_item_received` `meta` table fields:**

| Field | Type | Description |
|---|---|---|
| `meta.location_id` | int64 | The location ID where this item was placed in the multiworld. |
| `meta.is_self` | bool | `true` if this player placed the item themselves (found it in their own world). |
| `meta.handled_by` | string | The `mod_id` of the first mod that called `item_handled()` for this item, or `""` if no mod has handled it yet. |
| `meta.delivery_index` | int | Position of this delivery in AP's items array. Pass to `item_handled()` as the third argument to silence this specific delivery. `-1` if unknown. |

**`sender` values:**

| Value | Meaning |
|---|---|
| Another player's slot name | That player sent this item to you. |
| Your own slot name | You sent this item to yourself; check `meta.is_self` (will be `true`). |
| `"Server"` | Server-placed item — start inventory or similar (player 0 in apclientpp). |

**Popup / Notification Pattern:**

Use `item_handled(id, true, meta.delivery_index)` when your mod shows a notification for a received item. Silencing is per-delivery — each copy of the same item type is tracked independently, so all 10 Data Shards will show in your popup even though they share an item ID. The silence persists across reconnects, so the notification won't re-fire if the player restarts or reconnects.

```lua
APClient.on_item_received(function(item_id, item_name, sender, meta)
    -- Only show notification if not already handled by another mod
    if meta.handled_by == "" then
        show_item_popup(item_name, sender, meta.is_self)
        -- Silence this specific delivery so it doesn't re-fire on reconnect
        APClient.item_handled(item_id, true, meta.delivery_index)
    end
end)
```

---

## Callbacks

Register callbacks before calling `APClient.connect()`. Each mod has its own callback slots — registering a callback in your mod does not affect other mods.

| Callback | Signature | When it fires |
|---|---|---|
| `on_connect(fn)` | `fn()` | IPC pipe connection established |
| `on_disconnect(fn)` | `fn()` | IPC pipe disconnected (game close, framework restart) |
| `on_lifecycle(fn)` | `fn(state, message)` | Any lifecycle state change. `state` is one of the 12 state strings. |
| `on_registration_success(fn)` | `fn()` | Framework accepted your `register_mod()` call |
| `on_registration_rejected(fn)` | `fn(reason)` | Framework rejected your registration |
| `on_item_received(fn)` | `fn(item_id, item_name, sender, meta)` | An item was received from the AP server and routed to your mod. See [Item Notifications](#item-notifications) for `meta` fields and notification helpers. |
| `on_state_active(fn)` | `fn()` | Framework reached ACTIVE or RESYNCING state — safe to call `subscribe_tracker()` and other actions |
| `on_state_error(fn)` | `fn(message)` | Framework entered ERROR_STATE |
| `on_error(fn)` | `fn(code, message)` | A framework error occurred. Error codes: `CONFIG_INVALID`, `CONNECTION_FAILED`, `ACTION_FAILED`, etc. |
| `on_message(fn)` | `fn(type, payload_json)` | Any raw IPC message received (all types, useful for debugging) |
| `on_command_response(fn)` | `fn(command, success, error, data)` | Reply to a `command()` call (priority mods) |
| `on_tracker_snapshot(fn)` | `fn(snapshot_table)` | Full tracker state snapshot (after `subscribe_tracker()`) |
| `on_tracker_update(fn)` | `fn(delta_table)` | Incremental tracker state update |

---

## Lifecycle and Registration Pattern

The recommended lifecycle pattern:

```lua
local ok, APClient = pcall(require, "APClientLib")
if not ok then return end

local is_registered = false

-- ── Tick hooks ──────────────────────────────────────────────────────────────
-- Call APClient.update() from a frequently-fired game hook.
-- Choose hooks that fire from: title screen → lobby → in-world, so the mod
-- is polled throughout the entire game session.
RegisterHook("/Game/.../SomeWidget:Tick", function()
    APClient.update()
end)

-- ── Lifecycle ───────────────────────────────────────────────────────────────
APClient.on_lifecycle(function(state, message)
    -- Regular mods register during REGISTRATION
    -- Priority mods (archipelago.*) register during PRIORITY_REGISTRATION
    if state == "REGISTRATION" and not is_registered then
        APClient.register_mod()
        is_registered = true
    end
end)

APClient.on_registration_success(function()
    APClient.log("info", "Registered successfully")
end)

APClient.on_registration_rejected(function(reason)
    APClient.log("error", "Registration rejected: " .. (reason or ""))
end)

APClient.on_state_active(function()
    -- Framework is connected to AP server and ready
    -- Subscribe to tracker, sync game state, etc.
    APClient.subscribe_tracker()
end)

APClient.on_disconnect(function()
    is_registered = false
end)

-- ── Items ───────────────────────────────────────────────────────────────────
APClient.on_item_received(function(item_id, item_name, sender, meta)
    -- meta.location_id:    where the item was placed
    -- meta.is_self:        true if this player placed the item themselves
    -- meta.handled_by:     mod_id of the first mod to call item_handled(), or ""
    -- meta.delivery_index: position in AP's items array (for per-delivery silencing)
    apply_item(item_name)
end)

-- ── Connect ─────────────────────────────────────────────────────────────────
-- Call at the END of main.lua, after all callbacks are set.
APClient.connect()
```

---

## Receiving Items

When the AP server sends an item to your slot, the framework routes it to your mod via `EXECUTE_ACTION`:

1. Framework receives item from AP server
2. Looks up the item in your mod's capabilities
3. If the item has an `action` field, calls that handler
4. Always fires `on_item_received` with `(item_id, item_name, sender, meta)`

**Simple pattern (no action handler):**

```lua
APClient.on_item_received(function(item_id, item_name, sender, meta)
    if item_name == "Key" then give_player_key()
    elseif item_name == "Coin" then give_player_coins(10)
    end
end)
```

**Action handler pattern (declared in manifest):**

```json
{
    "name": "Crystal Key",
    "type": "progression",
    "amount": 1,
    "action": "MyMod.GrantCrystalKey",
    "args": [{ "name": "tier", "type": "number", "value": 2 }]
}
```

The framework calls the Lua function registered under `"MyMod.GrantCrystalKey"`. Register it by name in your Lua:

```lua
-- Action handlers are registered via register_api with the mod's prefix
APClient.register_api({
    GrantCrystalKey = function(tier)
        game.grant_key(tier)
    end
})
```

---

## Cross-Mod API

The cross-mod API lets mods communicate without knowing about each other's existence at load time.

**Publishing an API (mod A):**

```lua
APClient.register_api({
    get_tier_count = function() return game.get_current_tier() end,
    unlock_tier    = function(n) game.unlock_tier(n) end
})
```

**Calling another mod's API (mod B):**

```lua
APClient.on_state_active(function()
    local proxy = APClient.get_api("author.mygame.basemod")
    if proxy then
        local count = proxy.get_unlock_count()
        print("Unlocks: " .. tostring(count))
    end
end)
```

**How it works:**
1. Mod B calls `proxy.get_tier_count()` → APClient sends `api_call` to framework
2. Framework routes to Mod A's connection, fires registered function
3. Mod A returns result → framework routes `api_result` back to Mod B
4. Mod B's `proxy.get_tier_count()` call returns the value

If Mod A is not yet registered, the call is queued until it registers (with a timeout). This makes ordering between mods less critical.

**Use cases:**
- Tracker mod querying custom game state from a game mod
- One mod querying another mod's progression state
- Admin/UI mods reading any mod's status

---

## Priority vs Regular Mods

| Feature | Regular mod | Priority mod (`archipelago.*`) |
|---|---|---|
| Registration phase | REGISTRATION (60s window) | PRIORITY_REGISTRATION (30s window) |
| Admin commands | No | Yes (`cmd_restart`, `get_mods`, `get_logs`, `set_config`, etc.) |
| Capabilities (items/locations) | Expected | Must NOT declare |
| Typical use case | Game content mod | Tracker, UI widget, admin tool |

Most game mods should be regular mods. Use the priority prefix only for infrastructure that needs earlier registration or admin access.

---

*See also: [manifest.md](manifest.md) for the full manifest schema | [framework.md](framework.md) for lifecycle states and IPC protocol | [tracker.md](tracker.md) for subscribing to tracker data*
