# Design05: Message Routing

> How messages flow between AP server, framework, and client mods.

---

## Overview

The framework routes messages in three primary flows:

1. **Item Receipt:** AP Server → Framework → Mod
2. **Location Check:** Mod → Framework → AP Server
3. **Location Scout:** Mod ↔ Framework ↔ AP Server

---

## Item Receipt Flow

When the AP server sends items to the player:

```
┌─────────────┐    ReceivedItems    ┌─────────────────┐
│  AP Server  │ ──────────────────► │   APClient      │
└─────────────┘                     └────────┬────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ APMessageRouter │
                                    │  (lookup owner) │
                                    └────────┬────────┘
                                             │ execute_action
                                             ▼
                                    ┌─────────────────┐    IPC     ┌─────────────┐
                                    │  APIPCServer    │ ─────────► │ APIPCClient │
                                    └─────────────────┘            └──────┬──────┘
                                                                          │
                                                                          ▼
                                                                 ┌─────────────────┐
                                                                 │ APActionExecutor│
                                                                 │ (call Lua func) │
                                                                 └─────────────────┘
```

### Step-by-Step

1. **AP Server sends `ReceivedItems`** packet via WebSocket
2. **APClient receives** and queues the message
3. **APPollingThread** retrieves message and passes to router
4. **APMessageRouter** looks up which mod owns the item via capabilities
5. **Framework constructs `execute_action`** message with resolved arguments
6. **APIPCServer sends** message to owning mod's APIPCClient
7. **APIPCClient receives** and passes to APActionExecutor
8. **APActionExecutor calls** the Lua function from manifest
9. **Mod executes** its "promise" (e.g., unlocks tech, spawns item)
10. **APClientLib sends `action_result`** back to framework

### execute_action Message

```json
{
  "type": "execute_action",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": {
    "item_id": 6942100,
    "item_name": "Speed Boots",
    "action": "MyUserObj.UnlockTechnology",
    "args": [
      { "name": "id", "type": "string", "value": "6942100" },
      { "name": "tier", "type": "number", "value": 2 },
      { "name": "position", "type": "property", "value": "MyPlayerObj.player_pos" }
    ]
  }
}
```

### Argument Resolution (Two-Stage)

Arguments are resolved at **two different stages**:

**Stage 1: Framework-Resolved (before IPC send)**

These special variables are replaced by the framework before sending:

| Variable | Resolution |
|----------|------------|
| `<GET_ITEM_ID>` | Assigned item ID |
| `<GET_ITEM_NAME>` | Item name from manifest |
| `<GET_PROGRESSION_COUNT>` | Current tier (tracked by framework) |

**Stage 2: Client-Resolved (at execution time)**

Arguments with `"type": "property"` are **NOT** resolved by the framework. APClientLib resolves them from the mod's Lua state at action execution time:

```json
{ "name": "position", "type": "property", "value": "MyPlayerObj.player_pos" }
```

This enables dynamic values (player position, game state) that may change between item receipt and action execution.

---

## Location Check Flow

When a mod detects a location event:

```
┌─────────────┐                     ┌─────────────────┐
│  Client Mod │                     │  APIPCClient    │
│  (detects   │  location_check     │                 │
│   event)    │ ──────────────────► │                 │
└─────────────┘                     └────────┬────────┘
                                             │ IPC
                                             ▼
                                    ┌─────────────────┐
                                    │  APIPCServer    │
                                    └────────┬────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ APMessageRouter │
                                    │ (lookup ID)     │
                                    └────────┬────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐   LocationChecks   ┌─────────────┐
                                    │    APClient     │ ─────────────────► │  AP Server  │
                                    └─────────────────┘                    └─────────────┘
```

### Step-by-Step

1. **Mod detects** game event (chest opened, boss defeated, etc.)
2. **Mod is responsible** for detecting locations it declared in capabilities
3. **Mod sends `location_check`** IPC message to framework
4. **APIPCServer receives** and passes to router
5. **APMessageRouter** looks up LocationID for this capability
6. **APStateManager** records the check locally
7. **APClient sends `LocationChecks`** packet to AP server
8. **Server processes** check and notifies other games about sent items

### location_check Message

Simple location (amount = 1):

```json
{
  "type": "location_check",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "location_name": "Defeat Forest Boss",
    "count": 1
  }
}
```

Multi-instance location (amount > 1):

```json
{
  "type": "location_check",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "location_name": "Kill 20 Enemies",
    "count": 3
  }
}
```

### Count-to-ID Mapping

For location with `amount: 5`:

| Count | Generated Name | Location ID |
|-------|----------------|-------------|
| 1 | Kill 20 Enemies #1 | base + 0 |
| 2 | Kill 20 Enemies #2 | base + 1 |
| 3 | Kill 20 Enemies #3 | base + 2 |
| 4 | Kill 20 Enemies #4 | base + 3 |
| 5 | Kill 20 Enemies #5 | base + 4 |

---

## Location Scout Flow

When a mod wants to peek at what's in a location:

```
┌─────────────┐   location_scout   ┌─────────────────┐
│  Client Mod │ ─────────────────► │  APIPCClient    │
└─────────────┘                    └────────┬────────┘
      ▲                                     │ IPC
      │                                     ▼
      │                            ┌─────────────────┐
      │                            │  APIPCServer    │
      │                            └────────┬────────┘
      │                                     │
      │                                     ▼
      │                            ┌─────────────────┐
      │                            │ APMessageRouter │
      │                            └────────┬────────┘
      │                                     │
      │                                     ▼
      │                            ┌─────────────────┐
      │                            │    APClient     │
      │                            └────────┬────────┘
      │                                     │ LocationScouts
      │                                     ▼
      │                            ┌─────────────────┐
      │                            │   AP Server     │
      │                            └────────┬────────┘
      │                                     │ LocationInfo
      │                                     ▼
      │   ap_message               ┌─────────────────┐
      └──────────────────────────  │  (route back)   │
                                   └─────────────────┘
```

### Step-by-Step

1. **Mod sends `location_scout`** IPC message with location names
2. **Framework translates** names to LocationIDs
3. **APClient sends `LocationScouts`** packet to AP server
4. **Server responds** with `LocationInfo` packet containing item details
5. **Framework routes** response back to requesting mod via `ap_message`
6. **Mod displays/uses** the scouted information

### location_scout Message

```json
{
  "type": "location_scout",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "location_names": ["Chest A", "Chest B", "Boss Reward"]
  }
}
```

### Scout Response

```json
{
  "type": "ap_message",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": {
    "ap_type": "LocationInfo",
    "data": {
      "locations": [
        { "location": 6942067, "item": 6942100, "player": 2 },
        { "location": 6942068, "item": 6942150, "player": 1 },
        { "location": 6942069, "item": 6942200, "player": 3 }
      ]
    }
  }
}
```

---

## Action Execution

### APActionExecutor Process

1. **Parse action path** (e.g., `MyUserObj.UnlockTechnology`)
2. **Resolve property chain** from mod's Lua state
3. **Resolve property-type arguments** at execution time
4. **Call the function** with resolved arguments
5. **Catch any errors** during execution
6. **Send result** back to framework

### Success Path

```lua
-- Manifest: action = "MyUserObj.UnlockTechnology"
-- Args: id = "6942100", tier = 2

-- APActionExecutor resolves:
local func = MyUserObj.UnlockTechnology
func("6942100", 2)
-- Returns success
```

### Failure Scenarios

| Failure | Cause | Action |
|---------|-------|--------|
| Invalid path | `MyUserObj` is nil | Send error, framework logs |
| Function not found | `UnlockTechnology` doesn't exist | Send error, framework logs |
| Type mismatch | Wrong argument types | Send error, framework logs |
| Runtime error | Function throws exception | Catch, send error |
| Property not found | Property path invalid | Send error (property args only) |

### Error Reporting

```json
{
  "type": "action_result",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "success": false,
    "item_id": 6942100,
    "error": "Function MyUserObj.UnlockTechnology not found"
  }
}
```

### Framework Response to Errors

1. **Log the error** to log file
2. **Forward to priority clients** for visibility
3. **Priority client decides** recovery action:
   - Retry with different arguments
   - Skip item and continue
   - Enter ERROR_STATE if critical
   - Request mod re-registration

---

## Routing Tables

### Item Ownership Lookup

Framework maintains mapping from ItemID to owning mod:

```cpp
struct ItemOwnership {
    std::string mod_id;
    std::string item_name;
    std::string action;
    std::vector<ActionArg> args;
};

std::unordered_map<int64_t, ItemOwnership> item_ownership_;
```

### Location Ownership Lookup

Framework maintains mapping from location name to LocationID:

```cpp
struct LocationOwnership {
    std::string mod_id;
    int64_t location_id;
    int instance;  // For amount > 1
};

std::unordered_map<std::string, std::vector<LocationOwnership>> location_ownership_;
```

### Mod Connection Lookup

Framework tracks connected mods:

```cpp
struct ModConnection {
    std::string mod_id;
    HANDLE pipe_handle;
    bool is_priority;
    bool is_registered;
};

std::unordered_map<std::string, ModConnection> mod_connections_;
```

---

## Broadcast Routing

### To All Clients

```json
{
  "type": "lifecycle",
  "source": "framework",
  "target": "broadcast",
  "payload": { ... }
}
```

Framework iterates all connected mods and sends message to each.

### To Priority Clients Only

```json
{
  "type": "error",
  "source": "framework",
  "target": "priority",
  "payload": { ... }
}
```

Framework iterates only mods where `is_priority == true`.

---

## Message Queue Management

### Incoming Queue (per client)

- FIFO order
- Processed during `APManager::update()`
- Bounded size (configurable, default 1000)
- Overflow: drop oldest, log warning

### Outgoing Queue (per client)

- FIFO order
- Processed by IPC thread
- Bounded size (configurable, default 1000)
- Overflow: drop oldest, log warning

### Broadcast Queue

- Single queue for broadcast messages
- Copied to each client's outgoing queue
- Processed after individual messages