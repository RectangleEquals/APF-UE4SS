# Design08: Error Handling

> Error response protocol, ERROR_STATE behavior, and recovery commands.

---

## Error Response Protocol

When any runtime error occurs, the framework follows this protocol:

### Step 1: Log the Error

Full details written to log file:

```
[2024-01-15T12:30:45.123] [ERROR] [APActionExecutor]
  Action execution failed for item 6942100 (Speed Boots)
  Mod: mymod.palworld.items
  Action: MyUserObj.UnlockTechnology
  Error: Function not found - MyUserObj is nil
  Stack trace:
    ...
```

### Step 2: Forward to Priority Clients

All connected priority clients receive error notification:

```json
{
  "type": "error",
  "source": "framework",
  "target": "priority",
  "payload": {
    "code": "ACTION_FAILED",
    "message": "Function not found - MyUserObj is nil",
    "severity": "error",
    "context": {
      "component": "APActionExecutor",
      "mod_id": "mymod.palworld.items",
      "item_id": 6942100,
      "item_name": "Speed Boots",
      "action": "MyUserObj.UnlockTechnology"
    }
  }
}
```

### Step 3: Notify Regular Clients

Send shutdown message if entering ERROR_STATE:

```json
{
  "type": "lifecycle",
  "source": "framework",
  "target": "broadcast",
  "payload": {
    "state": "ERROR_STATE",
    "message": "Framework entering error state due to action execution failure"
  }
}
```

### Step 4: Enter ERROR_STATE

Framework pauses all execution until recovery command received.

---

## Error Codes

| Code | Severity | Description |
|------|----------|-------------|
| `CONFIG_INVALID` | fatal | Configuration file invalid or missing |
| `IPC_FAILED` | fatal | IPC server failed to start |
| `CONFLICT_DETECTED` | fatal | Capability conflicts between mods |
| `REGISTRATION_TIMEOUT` | error | Mods didn't register in time |
| `CONNECTION_FAILED` | error | AP server connection failed |
| `SYNC_FAILED` | error | State synchronization failed |
| `ACTION_FAILED` | warning | Action execution failed |
| `PROPERTY_FAILED` | warning | Property resolution failed |
| `MESSAGE_DROPPED` | warning | Message queue overflow |

### Severity Levels

| Severity | Behavior |
|----------|----------|
| `fatal` | Immediately enter ERROR_STATE |
| `error` | Enter ERROR_STATE after retries exhausted |
| `warning` | Log and continue, forward to priority clients |
| `info` | Log only |

---

## ERROR_STATE Behavior

While in `ERROR_STATE`:

### Active Components

- **IPC Server:** Remains active to receive commands from priority clients
- **Logging:** Continues to log all events
- **Priority Client Communication:** Still functional

### Paused Components

- **AP Server Connection:** Disconnected
- **Location Check Processing:** Stopped
- **Item Receipt Processing:** Stopped
- **Action Execution:** Stopped
- **Regular Client Communication:** Limited to error messages

### What Framework Does

```cpp
void APManager::enter_error_state(const std::string& error_code,
                                   const std::string& message) {
    // 1. Log the error
    AP_LOG_ERROR("Entering ERROR_STATE: " + error_code + " - " + message);

    // 2. Disconnect from AP server
    ap_client_->disconnect();

    // 3. Forward to priority clients
    broadcast_to_priority({
        {"type", "error"},
        {"code", error_code},
        {"message", message}
    });

    // 4. Notify all clients
    broadcast({
        {"type", "lifecycle"},
        {"state", "ERROR_STATE"},
        {"message", message}
    });

    // 5. Update state
    current_state_ = LifecycleState::ERROR_STATE;
}
```

### What Framework Accepts

In ERROR_STATE, framework only processes:

1. `cmd_restart` from priority clients
2. `cmd_reconnect` from priority clients (if error was connection-related)
3. `get_logs` from priority clients
4. `get_mods` from priority clients

All other messages are rejected with:

```json
{
  "type": "error",
  "source": "framework",
  "target": "<sender>",
  "payload": {
    "code": "STATE_ERROR",
    "message": "Framework is in ERROR_STATE. Use cmd_restart to recover."
  }
}
```

---

## Recovery Commands

### cmd_restart

Return to `INITIALIZATION` state, full rediscovery.

**Trigger:**
```json
{
  "type": "cmd_restart",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

**Effect:**
1. Clear all registration state
2. Clear capability tables
3. Clear session state
4. Transition to INITIALIZATION
5. Begin full lifecycle from scratch

**Use When:**
- Mod configuration has changed
- Unrecoverable error occurred
- Need fresh start

### cmd_resync

Return to `PRIORITY_REGISTRATION` state, re-register mods.

**Trigger:**
```json
{
  "type": "cmd_resync",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

**Effect:**
1. Disconnect from AP server
2. Clear registration state (keep discovery)
3. Clear session state
4. Transition to PRIORITY_REGISTRATION
5. Re-register all mods
6. Reconnect to AP server
7. Re-sync state

**Use When:**
- Mods lost sync
- Need to re-authenticate
- Checksum mismatch

### cmd_reconnect

Attempt to reconnect to AP server only.

**Trigger:**
```json
{
  "type": "cmd_reconnect",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

**Effect:**
1. Disconnect (if connected)
2. Attempt connection with same settings
3. If successful: transition to SYNCING → ACTIVE
4. If failed: remain in ERROR_STATE

**Use When:**
- Network hiccup
- Server temporarily unavailable
- Connection dropped

---

## State Persistence

The framework persists session progress to enable recovery.

### Persisted Data

Stored in `ue4ss/Mods/APFrameworkMod/session_state.json`:

```json
{
  "version": "1.0.0",
  "checksum": "a1b2c3d4e5f6...",
  "slot_name": "Player1",
  "received_item_index": 42,
  "checked_locations": [6942067, 6942068, 6942069],
  "last_active": "2024-01-15T12:30:45Z",
  "ap_server": "archipelago.gg",
  "ap_port": 38281
}
```

### When Saved

- After each received item is processed
- After each location check is sent
- On graceful shutdown
- Periodically (configurable interval)

### When Loaded

- During SYNCING state
- Only if checksum matches current ecosystem

### Resync Behavior

1. Load `session_state.json`
2. Validate checksum against current mod ecosystem
3. If checksums match:
   - Set received item index
   - Mark checked locations as complete
   - Request only items after index from server
4. If checksums don't match:
   - Warn player
   - Start fresh (items re-sent from index 0)
   - AP Server is source of truth anyway

---

## Action Execution Failures

### Types of Failures

| Failure | Cause | Severity |
|---------|-------|----------|
| Invalid function path | Lua object is nil | warning |
| Function not found | Method doesn't exist | warning |
| Type mismatch | Wrong argument types | warning |
| Runtime error | Function throws | warning |
| Property not found | Invalid property path | warning |
| Stale Lua state | Mod unloaded | error |

### Handling Protocol

```cpp
ActionResult APActionExecutor::execute(const std::string& action,
                                       const std::vector<ActionArg>& args) {
    try {
        // 1. Resolve function path
        sol::function func = find_function(action);
        if (!func.valid()) {
            return ActionResult::error("Function not found: " + action);
        }

        // 2. Resolve property arguments
        std::vector<sol::object> resolved_args;
        for (const auto& arg : args) {
            if (arg.type == "property") {
                auto prop = resolve_property(arg.value);
                if (!prop.valid()) {
                    return ActionResult::error("Property not found: " + arg.value);
                }
                resolved_args.push_back(prop);
            } else {
                resolved_args.push_back(convert_arg(arg));
            }
        }

        // 3. Call function
        sol::protected_function_result result = func(sol::as_args(resolved_args));

        if (!result.valid()) {
            sol::error err = result;
            return ActionResult::error("Runtime error: " + std::string(err.what()));
        }

        return ActionResult::success();

    } catch (const std::exception& e) {
        return ActionResult::error("Exception: " + std::string(e.what()));
    }
}
```

### Error Reporting

```cpp
void APClientLib::report_action_result(int64_t item_id,
                                       const ActionResult& result) {
    json message = {
        {"type", "action_result"},
        {"source", mod_id_},
        {"target", "framework"},
        {"payload", {
            {"success", result.success},
            {"item_id", item_id}
        }}
    };

    if (!result.success) {
        message["payload"]["error"] = result.error_message;
    }

    ipc_client_->send(message);
}
```

### Framework Response

When framework receives action failure:

1. **Log the error** with full context
2. **Forward to priority clients**
3. **Continue processing** (action failures are warnings, not fatal)
4. Priority clients can decide:
   - Retry with CMD_RESYNC
   - Ignore and continue
   - Display error to user

---

## Retry Configuration

In `framework_config.json`:

```json
{
  "retries": {
    "ipc_max_retries": 3,
    "ipc_retry_delay_ms": 1000,
    "ipc_backoff_multiplier": 2.0,
    "ap_connection_max_retries": 5,
    "ap_connection_retry_delay_ms": 5000,
    "action_max_retries": 0
  }
}
```

### Retry Behavior

```cpp
template<typename Func>
bool retry_with_backoff(Func operation, const RetryConfig& config) {
    int attempts = 0;
    int delay = config.initial_delay_ms;

    while (attempts <= config.max_retries) {
        if (operation()) {
            return true;
        }

        attempts++;
        if (attempts <= config.max_retries) {
            AP_LOG_WARN("Retry " + std::to_string(attempts) +
                       "/" + std::to_string(config.max_retries));
            std::this_thread::sleep_for(std::chrono::milliseconds(delay));
            delay = static_cast<int>(delay * config.backoff_multiplier);
        }
    }

    return false;
}
```

---

## Logging Best Practices

### What to Log

| Level | When to Use |
|-------|-------------|
| `trace` | Detailed debugging info |
| `debug` | Development debugging |
| `info` | Normal operational events |
| `warn` | Recoverable issues |
| `error` | Non-recoverable issues |
| `fatal` | System-breaking failures |

### Log Format

```
[TIMESTAMP] [LEVEL] [COMPONENT] Message
  Context: key=value, key=value
  Stack: (if applicable)
```

### Example Log Output

```
[2024-01-15T12:30:45.123] [INFO] [APManager] Framework initialized
[2024-01-15T12:30:45.456] [INFO] [APModRegistry] Discovered 3 manifests
[2024-01-15T12:30:46.789] [WARN] [APIPCServer] Client connection timeout
  Context: mod_id=mymod.game.test, attempt=2/3
[2024-01-15T12:30:47.012] [ERROR] [APActionExecutor] Action execution failed
  Context: item_id=6942100, action=MyObj.Give, error=MyObj is nil
[2024-01-15T12:30:47.345] [FATAL] [APManager] Entering ERROR_STATE
  Context: trigger=IPC_FAILED, retries_exhausted=true
```