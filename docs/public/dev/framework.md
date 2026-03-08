# AP Framework — System Overview

AP Framework is middleware that connects UE4SS game mods to [Archipelago Multiworld Randomizer](https://archipelago.gg). It handles the full pipeline from AP server connection through item routing, location checking, and tracker data delivery — so that individual game mods only need to handle game-specific logic.

---

## What It Does

Without AP Framework, each game mod would need to independently implement AP client connection, WebSocket communication, multiworld protocol handling, state persistence, and cross-mod coordination. AP Framework centralizes all of this:

- Discovers mod manifests and aggregates their items, locations, and regions into a unified AP capabilities package
- Manages the connection to the Archipelago server
- Routes received items to the correct mod's action handler
- Accepts location check reports from mods and forwards them to the AP server
- Broadcasts lifecycle state changes so all mods can react to connection/disconnection
- Computes per-location accessibility scores in real-time for tracker subscriptions
- Provides a cross-mod API call system for inter-mod communication

---

## Components

### Server-Side (APFrameworkCore.dll)

| Component | Role |
|---|---|
| **APManager** | Central orchestrator — owns the 12-state lifecycle state machine, drives all transitions, processes events from background threads on the game thread |
| **APIPCServer** | Named pipe server — accepts connections from APClientLib instances, routes messages, manages per-connection overlapped I/O and dedicated write thread |
| **APModRegistry** | Discovers and parses `manifest.json` files, validates dependencies and conflicts, assigns stable AP item/location IDs |
| **APCapabilities** | Aggregates capabilities from all registered mods, merges region/location/item overrides, produces the JSON config sent to the apworld |
| **APPollingThread** | Dedicated thread running apclientpp — handles the AP server WebSocket connection, pushes received items and connection events to a thread-safe queue |
| **APStateManager** | Persists checked locations and server connection info to `session_state.json` — survives disconnects and restarts |
| **APTrackerEngine** | Computes 0.0–1.0 accessibility scores for all locations and regions on a background thread; delivers snapshots and incremental updates to subscriber mods |
| **APMessageRouter** | Routes outgoing IPC messages to the correct client connection(s); handles broadcast vs targeted delivery |

### Client-Side (APClientLib.dll)

| Component | Role |
|---|---|
| **APClientManager** | Singleton coordinator — manages all per-mod contexts, polls IPC, dispatches incoming messages to the correct mod's callbacks |
| **APIPCClient** | Named pipe client — one instance per mod (per `require("APClientLib")` call), handles overlapped read/write with ERROR_MORE_DATA accumulation |
| **APClientContext** | Per-mod state: mod_id, cached Lua state, callback table, lifecycle state, cross-mod API registry |
| **APCallbacks** | Per-mod callback table — 13 slots for Lua functions registered via `on_lifecycle`, `on_item_received`, etc. |

---

## UE4SS Integration

AP Framework loads as two UE4SS C++ mods (`APFrameworkCore` and `APClientLib`), placed in the UE4SS binaries directory. UE4SS calls `luaopen_APFrameworkCore(L)` and `luaopen_APClientLib(L)` during mod startup.

**Threading model:**

| Thread | Who runs it | What it does |
|---|---|---|
| Main (init) | UE4SS mod loader | `init()` — one-time setup per DLL load |
| Game (update) | UE4SS game tick hook | `update()` — called every game tick by registered Lua hooks |
| IPC-Server | APIPCServer | Accepts pipe connections, reads messages, drains per-connection send queues |
| IPC-Write | APIPCServer | Dedicated write thread — all WriteFile calls go here, never blocks game thread |
| AP-Polling | APPollingThread | apclientpp event loop — WebSocket I/O with the Archipelago server |
| Snap-Worker | APTrackerEngine | Computes tracker snapshot asynchronously (~18ms for 500+ locations) |

Named Pipes are used for IPC rather than direct function calls because APFrameworkCore and APClientLib are separate DLL processes and each has independent singleton instances in APShared. The pipe is a well-defined boundary with no shared memory, enabling proper lifetime management and clear attribution of messages.

---

## Lifecycle States

The framework progresses through 12 states from startup to active gameplay. All mods receive a `LIFECYCLE` IPC message on every state transition.

| State | String sent to mods | Typical duration | Description |
|---|---|---|---|
| `UNINITIALIZED` | `"UNINITIALIZED"` | Milliseconds | Before `init()` is called |
| `INITIALIZATION` | `"INITIALIZATION"` | Milliseconds | Loading config, starting IPC server |
| `DISCOVERY` | `"DISCOVERY"` | Milliseconds | Scanning `Mods/` directories for `manifest.json` files |
| `VALIDATION` | `"VALIDATION"` | Milliseconds | Checking dependency/incompatibility constraints |
| `GENERATION` | `"GENERATION"` | Milliseconds | Assigning stable AP IDs, generating capabilities config |
| `PRIORITY_REGISTRATION` | `"PRIORITY_REGISTRATION"` | Up to 30s | Waiting for priority clients to connect and register |
| `REGISTRATION` | `"REGISTRATION"` | Up to 60s | Waiting for all regular mods to connect and register |
| `CONNECTING` | `"CONNECTING"` | Up to 30s | Establishing WebSocket connection to the AP server |
| `SYNCING` | `"SYNCING"` | Seconds | Validating data package checksum, reconciling checked locations |
| `ACTIVE` | `"ACTIVE"` | Indefinite | Normal operation — items flow, location checks are accepted |
| `RESYNCING` | `"RESYNCING"` | Seconds | Reconnecting after a disconnect — same as ACTIVE for most mods |
| `ERROR_STATE` | `"ERROR_STATE"` | Until resolved | Configuration error, failed connection, or unrecoverable fault |

Mods should call `APClient.register_mod()` when they receive `PRIORITY_REGISTRATION` (priority mods) or `REGISTRATION` (regular mods). Mods should call `APClient.subscribe_tracker()` and other setup when they receive `ACTIVE`. After `RESYNCING`, mods can resume normal operation — the framework re-sends any items received during the disconnect.

---

## Registration Phases

**PRIORITY_REGISTRATION (30-second window):**
Mods whose `mod_id` matches the pattern `^archipelago\.[^.]+\..*` (e.g., `archipelago.mygame.framework`, `archipelago.mygame.tracker`) are priority clients. They connect during this phase and receive special access — they can send admin commands (`cmd_restart`, `cmd_resync`, `get_mods`, `get_logs`, `set_config`) and receive priority responses. Priority clients must NOT declare capabilities — they have no items, locations, or regions.

**REGISTRATION (60-second window):**
All other AP mods (with `mod_id`) register during this phase. The framework accepts their registration, validates that their mod_id is known from manifest discovery, and records them as active. Mods that miss this window stay connected but cannot participate in the current session's item routing.

Both windows start counting from when the framework broadcasts that state, not from game launch. If all expected mods register before the timeout, the framework advances early.

---

## IPC Protocol

**Pipe name:** `\\.\pipe\APFramework_{game_name}` (e.g., `\\.\pipe\APFramework_YourGame`)

**Wire format:** 4-byte little-endian length prefix followed by a UTF-8 JSON body.

```
[uint32 length][{type, source, target, payload JSON}]
```

**Large message transport:** Messages larger than 48 KB are automatically split by the sender into `multipart_chunk` frames using zlib compression + base64 encoding. The receiver reassembles them transparently before dispatching. Callers never need to handle chunking — it is invisible to both the framework and client code.

**Overlapped I/O:** All pipe handles use `FILE_FLAG_OVERLAPPED`. The server has a dedicated write thread that drains per-connection send queues; the game thread only enqueues serialized buffers and never calls `WriteFile` directly.

---

## IPC Message Types

All messages follow `{type, source, target, payload}`. The `source` is the sender's `mod_id` (or `"framework"`); the `target` is either a specific `mod_id`, `"framework"`, or `"broadcast"`.

### Framework → All Clients

| Type | Description |
|---|---|
| `lifecycle` | State transition broadcast — `{state, message}`. All connected mods receive this. |
| `error` | Error notification — `{code, message}`. Error codes: `CONFIG_INVALID`, `IPC_FAILED`, `CONFLICT_DETECTED`, `REGISTRATION_TIMEOUT`, `CONNECTION_FAILED`, `SYNC_FAILED`, `CHECKSUM_MISMATCH`, `ACTION_FAILED`, `ACTION_TIMEOUT`. |
| `ap_message` | Raw AP server message forwarded verbatim — `{cmd, ...AP fields}` |
| `multipart_chunk` | One chunk of a large split message — assembled transparently by APIPCClient |

### Framework → Specific Client

| Type | Description |
|---|---|
| `registration_response` | Reply to `register` — `{success, reason}` |
| `execute_action` | Item received — `{item_id, item_name, sender, action, args}`. Triggers `on_item_received` callback and the registered action handler. |
| `command_response` | Reply to a `command` — `{command, success, error, data}` |
| `tracker_snapshot` | Full scored tracker state — sent once on `subscribe_tracker`. See [tracker.md](tracker.md). |
| `tracker_update` | Incremental tracker update — sent when item state or region reachability changes. Same schema as snapshot but only changed entries. |
| `api_result` | Cross-mod API return value — `{call_id, result, success, error}` |
| `api_call` | Cross-mod API call routed from another mod — `{function, call_id, _source, ...args}` |

### Client → Framework

| Type | Description |
|---|---|
| `register` | Register this mod — `{mod_id, version, type}`. Type: `"regular"` or `"priority"`. |
| `location_check` | Mark a location as checked — `{location_id}` |
| `location_scout` | Scout a location without checking — `{location_ids[]}` |
| `action_result` | Report item action outcome — `{item_id, item_name, success, error}` |
| `log` | Forward a log entry to the framework log — `{level, message}` |
| `command` | Send a game command (priority mods only) — `{command, ...args}` |
| `callback_error` | Report a Lua callback exception — `{callback, error}` |
| `subscribe_tracker` | Begin receiving tracker updates |
| `unsubscribe_tracker` | Stop receiving tracker updates |
| `api_call` | Call a function registered by another mod — `{target, function, call_id, ...args}` |
| `api_result` | Return value from a cross-mod API call |

### Priority Client → Framework (admin commands)

| Type | Description |
|---|---|
| `cmd_restart` | Restart the framework state machine from INITIALIZATION |
| `cmd_resync` | Force a resync with the AP server |
| `cmd_reconnect` | Force a reconnection attempt |
| `get_mods` | Request the current mod list |
| `get_logs` | Request recent log entries |
| `get_data_package` | Request the current data package (capabilities config) |
| `set_config` | Update framework configuration at runtime |
| `send_message` | Send a raw message to a specific mod |
| `broadcast` | Broadcast a message to all mods |

---

## Configuration

On first launch, the framework creates `APFramework.json` in the UE4SS binaries directory alongside the DLL. This file persists connection settings across sessions.

```json
{
    "ap_host": "archipelago.gg",
    "ap_port": 38281,
    "ap_slot_name": "",
    "ap_password": "",
    "priority_registration_timeout_ms": 30000,
    "registration_timeout_ms": 60000,
    "connecting_timeout_ms": 30000
}
```

Players typically configure `ap_host`, `ap_port`, `ap_slot_name`, and `ap_password` via the in-game UI widget provided by the framework mod, which writes back to this file.

---

## Session State

`session_state.json` persists the minimal state needed to resume a session after a restart or disconnect, without requiring a full re-sync:

- Which locations have been checked (set of location IDs)
- The AP server host and port from the last successful connection
- The data package schema version

On startup, the framework loads this file and merges it with the server's authoritative state during the SYNCING phase. If the server has newer information (e.g., locations checked on another client), the server's state wins.

---

## Cross-Mod API

Any mod can expose functions to other mods through the framework's `api_call` / `api_result` routing:

**Registering a function (in Lua):**
```lua
APClient.register_api({
    get_player_level = function() return game.get_level() end,
    set_difficulty = function(d) game.set_difficulty(d) end
})
```

**Calling another mod's function (in Lua):**
```lua
local proxy = APClient.get_api("target.mod.id")
local level = proxy.get_player_level()
```

The framework routes the call:
1. Caller sends `api_call` → framework
2. Framework routes to target mod's connection
3. Target mod executes and sends `api_result` → framework
4. Framework routes result back to caller

If the target mod is not yet registered, the call is queued until it registers (up to a configurable timeout). This enables mods to call each other's APIs during initialization without strict ordering requirements.

---

## Feature Summary

- Named pipe IPC with overlapped I/O and dedicated write thread (no game-thread blocking)
- 12-state lifecycle with configurable timeouts; all states broadcast to all mods
- Two-phase registration (priority and regular) with independent timeouts
- AP server connection via apclientpp (WebSocket, SSL/TLS)
- Per-mod IPC connections (each mod has its own pipe; connection renaming does not affect attribution)
- Automatic large message splitting: zlib compression + base64 + chunked reassembly, transparent to callers
- Session state persistence: checked locations and server info survive restarts
- Real-time tracker scoring: pre-parsed AST + fixed-point region reachability + `evaluate_scored()` on Snap-Worker thread
- Incremental tracker updates: only changed entries sent after initial snapshot
- Cross-mod API routing: any mod can publish and call functions on other mods
- Vocabulary validation: optional item/location/region name validation against game data
- Data package integrity: checksum-based validation with AP server
- Goal aggregation: mods declare completion conditions; `goal` option auto-generated when multiple exist
- Item override system: mods can change another mod's item types conditionally
- Location logic overrides: mods can add alternative access paths to another mod's locations (OR-merged)

---

*See also: [mods.md](mods.md) for the Lua mod API | [tracker.md](tracker.md) for the tracker engine and snapshot schema | [manifest.md](manifest.md) for mod capabilities declaration*
