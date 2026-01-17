# Design06: Priority Clients

> Special mods with elevated privileges but no capabilities.

---

## What Are Priority Clients?

Priority Clients are mods with `mod_id` matching the pattern `archipelago.<game_name>.*`.

**Key characteristics:**
- Elevated privileges within the framework
- Do NOT contribute capabilities to generation
- Register before regular clients (PRIORITY_REGISTRATION phase)
- Can issue commands that regular clients cannot

---

## Purpose

Priority Clients extend the framework's functionality without affecting randomization.

### Example Use Cases

| Mod | Purpose |
|-----|---------|
| `archipelago.palworld.ui` | Display framework status, connection info, item queue |
| `archipelago.palworld.debug` | Developer tools, logging interface, state inspection |
| `archipelago.palworld.controller` | Manual connection controls, resync buttons |
| `archipelago.palworld.overlay` | HUD overlay showing AP status |
| `archipelago.palworld.tracker` | Location/item tracking integration |

---

## Manifest Differences

Priority Client manifests:

- **Must have** `mod_id` matching `archipelago.<game_name>.*`
- **Must NOT have** a `capabilities` field
- Have same other fields as regular clients

### Example Priority Client Manifest

```json
{
  "mod_id": "archipelago.palworld.framework_ui",
  "name": "AP Framework UI",
  "version": "1.0.0",
  "description": "UI overlay for Archipelago Framework status"
}
```

### Comparison

| Field | Regular Client | Priority Client |
|-------|---------------|-----------------|
| `mod_id` | `author.game.mod` | `archipelago.game.mod` |
| `capabilities` | Required | Must NOT exist |
| `incompatible` | Optional | Optional |

---

## Privileges

Priority Clients can do things regular clients cannot:

### Query Privileges

| Privilege | IPC Message | Description |
|-----------|-------------|-------------|
| Get all mods | `get_mods` filter: `"all"` | List of all mods with manifests |
| Get registered mods | `get_mods` filter: `"registered"` | List of currently registered mods |
| Get discovered mods | `get_mods` filter: `"discovered"` | List of discovered but not yet registered |
| Get conflicting mods | `get_mods` filter: `"conflicting"` | List of mods that failed validation |
| Get logs | `get_logs` | Filtered access to log entries |
| Get data package | `get_data_package` | Full AP server data package |

### Command Privileges

| Privilege | IPC Message | Description |
|-----------|-------------|-------------|
| Force restart | `cmd_restart` | Return to INITIALIZATION state |
| Force resync | `cmd_resync` | Re-register and reconnect |
| Force reconnect | `cmd_reconnect` | Reconnect to AP server only |
| Change config | `set_config` | Modify framework settings at runtime |

### Communication Privileges

| Privilege | IPC Message | Description |
|-----------|-------------|-------------|
| Send to specific | `send_message` | Send IPC to specific client(s) |
| Broadcast | `broadcast` | Broadcast to all clients |

---

## Registration Flow

Priority Clients register before regular clients:

```
GENERATION
    │
    ▼
PRIORITY_REGISTRATION  ◄── Priority clients register here
    │
    ▼
REGISTRATION           ◄── Regular clients register here
    │
    ▼
CONNECTING
```

### Why Register First?

1. **Control:** Priority clients can observe and control the registration process
2. **Logging:** Can capture registration events for UI/debugging
3. **Intervention:** Can handle errors before regular clients start

---

## Example Priority Client Implementation

### manifest.json

```json
{
  "mod_id": "archipelago.palworld.debug_ui",
  "name": "AP Debug UI",
  "version": "1.0.0",
  "description": "Debug interface for AP Framework"
}
```

### main.lua

```lua
-- archipelago.palworld.debug_ui/Scripts/main.lua
print("[AP Debug UI] Loading...\n")

local APClientLib = require("APClientLib")

-- Track state
local framework_state = "UNKNOWN"
local registered_mods = {}

-- Listen for lifecycle changes
APClientLib.on_lifecycle(function(state, message)
    framework_state = state
    print("[AP Debug UI] State: " .. state .. " - " .. message .. "\n")

    -- Register when priority registration starts
    if state == "PRIORITY_REGISTRATION" then
        APClientLib.register()
    end

    -- Fetch mod list when registration starts
    if state == "REGISTRATION" then
        fetch_mod_list()
    end
end)

-- Listen for errors
APClientLib.on_error(function(code, message)
    print("[AP Debug UI] ERROR: " .. code .. " - " .. message .. "\n")
    -- Could display error popup here
end)

-- Query mod list
function fetch_mod_list()
    APClientLib.send_message({
        type = "get_mods",
        target = "framework",
        payload = { filter = "all" }
    })
end

-- Handle responses
APClientLib.on_message(function(message)
    if message.type == "get_mods_response" then
        registered_mods = message.payload.mods
        print("[AP Debug UI] Mods: " .. #registered_mods .. "\n")
    end
end)

-- Commands exposed to game UI
DebugUI = {
    restart = function()
        APClientLib.send_message({
            type = "cmd_restart",
            target = "framework",
            payload = {}
        })
    end,

    resync = function()
        APClientLib.send_message({
            type = "cmd_resync",
            target = "framework",
            payload = {}
        })
    end,

    get_state = function()
        return framework_state
    end,

    get_mods = function()
        return registered_mods
    end
}

print("[AP Debug UI] Initialized\n")
```

---

## get_mods Response Format

```json
{
  "type": "get_mods_response",
  "source": "framework",
  "target": "archipelago.palworld.debug_ui",
  "payload": {
    "mods": [
      {
        "mod_id": "mymod.palworld.items",
        "version": "1.0.0",
        "name": "Item Mod",
        "status": "registered",
        "type": "regular",
        "capabilities": {
          "locations": 5,
          "items": 10
        }
      },
      {
        "mod_id": "other.palworld.enemies",
        "version": "0.5.0",
        "name": "Enemy Mod",
        "status": "discovered",
        "type": "regular",
        "capabilities": {
          "locations": 3,
          "items": 2
        }
      },
      {
        "mod_id": "archipelago.palworld.debug_ui",
        "version": "1.0.0",
        "name": "AP Debug UI",
        "status": "registered",
        "type": "priority",
        "capabilities": null
      }
    ]
  }
}
```

---

## get_logs Response Format

```json
{
  "type": "get_logs_response",
  "source": "framework",
  "target": "archipelago.palworld.debug_ui",
  "payload": {
    "logs": [
      {
        "timestamp": "2024-01-15T12:30:45.123Z",
        "level": "info",
        "source": "framework",
        "message": "Framework initialized"
      },
      {
        "timestamp": "2024-01-15T12:30:46.456Z",
        "level": "error",
        "source": "mymod.palworld.items",
        "message": "Action execution failed: function not found"
      }
    ],
    "total": 250,
    "returned": 100
  }
}
```

---

## set_config Options

Priority clients can modify these settings at runtime:

| Key | Type | Description |
|-----|------|-------------|
| `log_level` | string | Minimum log level (`trace`, `debug`, `info`, `warn`, `error`) |
| `ipc_timeout_ms` | number | IPC message timeout |
| `registration_timeout_ms` | number | Registration phase timeout |
| `auto_reconnect` | boolean | Auto-reconnect to AP server |

### Example

```json
{
  "type": "set_config",
  "source": "archipelago.palworld.debug_ui",
  "target": "framework",
  "payload": {
    "key": "log_level",
    "value": "debug"
  }
}
```

---

## Error Forwarding

All errors are automatically forwarded to priority clients:

```json
{
  "type": "error",
  "source": "framework",
  "target": "priority",
  "payload": {
    "code": "ACTION_FAILED",
    "message": "MyUserObj.GiveItem: function not found",
    "context": {
      "mod_id": "mymod.palworld.items",
      "item_id": 6942100,
      "item_name": "Speed Boots"
    }
  }
}
```

This allows priority clients to:
- Display errors to users
- Log to external systems
- Take corrective action
- Alert developers

---

## Best Practices

### Do

- Register during PRIORITY_REGISTRATION
- Log important events for debugging
- Provide user-friendly error messages
- Implement graceful degradation

### Don't

- Include capabilities in manifest
- Block on long operations
- Spam command messages
- Assume other mods are registered