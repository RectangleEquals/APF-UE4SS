# Design04: IPC Protocol

> Communication between APFrameworkCore and APClientLib using Windows Named Pipes.

---

## Transport Layer

| Property | Value |
|----------|-------|
| **Mechanism** | Windows Named Pipes |
| **Pipe Name** | `\\.\pipe\APFramework_<game_name>` |
| **Mode** | Fully asynchronous |
| **Timeouts** | Configurable (default 5 seconds) |
| **Retries** | Configurable with backoff |
| **Failure** | Log warnings, retry, ERROR_STATE after max retries |

---

## Message Format

All IPC messages are JSON objects:

```json
{
  "type": "string",
  "source": "string",
  "target": "string",
  "payload": {}
}
```

| Field | Description |
|-------|-------------|
| `type` | Message type identifier |
| `source` | Sender's mod_id or `"framework"` |
| `target` | Recipient's mod_id, `"framework"`, `"broadcast"`, or `"priority"` |
| `payload` | Type-specific data object |

### Target Values

| Target | Meaning |
|--------|---------|
| `"framework"` | Message to APFrameworkCore |
| `"<mod_id>"` | Message to specific mod |
| `"broadcast"` | Message to all connected clients |
| `"priority"` | Message to all priority clients only |

---

## Message Types: Framework → Client

### ap_message

Forwards AP server messages to clients.

```json
{
  "type": "ap_message",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": {
    "ap_type": "ReceivedItems",
    "data": {
      "items": [
        { "item": 6942100, "player": 1 }
      ]
    }
  }
}
```

### execute_action

Instructs client to execute a capability action.

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
      { "name": "id", "value": "6942100" },
      { "name": "tier", "value": 2 }
    ]
  }
}
```

**Args are pre-resolved:** Special variables like `<GET_ITEM_ID>` are already replaced.

### lifecycle

Notifies clients of lifecycle state changes.

```json
{
  "type": "lifecycle",
  "source": "framework",
  "target": "broadcast",
  "payload": {
    "state": "REGISTRATION",
    "message": "Ready for client registration"
  }
}
```

### error

Notifies clients of errors.

```json
{
  "type": "error",
  "source": "framework",
  "target": "broadcast",
  "payload": {
    "code": "CONFLICT_DETECTED",
    "message": "Multiple mods claim unique location 'Defeat Boss'"
  }
}
```

### registration_response

Response to client registration request.

```json
{
  "type": "registration_response",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": {
    "success": true,
    "message": "Registration successful"
  }
}
```

Or on failure:

```json
{
  "type": "registration_response",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": {
    "success": false,
    "message": "Registration rejected: framework in DISCOVERY state"
  }
}
```

---

## Message Types: Client → Framework

### register

Client registration request.

```json
{
  "type": "register",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "mod_id": "mymod.game.mod",
    "version": "1.0.0"
  }
}
```

### location_check

Reports a location event.

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

For multi-instance locations:

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

### location_scout

Requests location info from AP server.

```json
{
  "type": "location_scout",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "location_names": ["Location A", "Location B"]
  }
}
```

### log

Sends log message to framework's log file.

```json
{
  "type": "log",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "level": "info",
    "message": "Initialized successfully"
  }
}
```

Valid levels: `trace`, `debug`, `info`, `warn`, `error`, `fatal`

### action_result

Reports result of executed action.

```json
{
  "type": "action_result",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "success": true,
    "item_id": 6942100
  }
}
```

Or on failure:

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

---

## Message Types: Priority Client → Framework

Priority clients (`archipelago.<game>.*`) can send additional commands.

### cmd_restart

Restart framework from INITIALIZATION.

```json
{
  "type": "cmd_restart",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

### cmd_resync

Force full resync.

```json
{
  "type": "cmd_resync",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

### cmd_reconnect

Force AP server reconnection.

```json
{
  "type": "cmd_reconnect",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

### get_mods

Request mod list.

```json
{
  "type": "get_mods",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {
    "filter": "all"
  }
}
```

Filter options: `"all"`, `"registered"`, `"discovered"`, `"conflicting"`

**Response:**

```json
{
  "type": "get_mods_response",
  "source": "framework",
  "target": "archipelago.palworld.ui",
  "payload": {
    "mods": [
      { "mod_id": "mymod.game.mod", "version": "1.0.0", "status": "registered" },
      { "mod_id": "other.game.mod", "version": "0.5.0", "status": "discovered" }
    ]
  }
}
```

### get_logs

Request filtered logs.

```json
{
  "type": "get_logs",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {
    "mod_ids": ["mymod.game.mod"],
    "levels": ["error", "warn"],
    "types": ["action_result"],
    "limit": 100
  }
}
```

### get_data_package

Request AP data package.

```json
{
  "type": "get_data_package",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {}
}
```

### set_config

Modify framework config at runtime.

```json
{
  "type": "set_config",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {
    "key": "log_level",
    "value": "debug"
  }
}
```

### send_message

Send message to specific client(s).

```json
{
  "type": "send_message",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {
    "targets": ["mymod.game.mod"],
    "message": {
      "type": "custom_notification",
      "data": { "text": "Hello from UI" }
    }
  }
}
```

### broadcast

Broadcast to all clients.

```json
{
  "type": "broadcast",
  "source": "archipelago.palworld.ui",
  "target": "framework",
  "payload": {
    "message": {
      "type": "server_announcement",
      "data": { "text": "Game starting in 60 seconds" }
    }
  }
}
```

---

## Error Handling

### Retry Policy

```json
{
  "ipc": {
    "max_retries": 3,
    "retry_delay_ms": 1000,
    "retry_backoff_multiplier": 2.0,
    "timeout_ms": 5000
  }
}
```

### Failure Escalation

1. **First failure:** Log warning, retry after delay
2. **Subsequent failures:** Log error, retry with backoff
3. **Max retries exceeded:** Log fatal, enter ERROR_STATE

### Connection Loss

- APClientLib auto-reconnects on connection loss
- Framework accepts reconnection and re-validates registration
- Pending messages are queued and sent on reconnection

---

## Message Sequencing

Messages are processed in order per connection. The framework maintains separate queues for:

1. **Incoming messages** from each client
2. **Outgoing messages** to each client
3. **Broadcast queue** for bulk sends

### Acknowledgments

Critical messages can request acknowledgment:

```json
{
  "type": "execute_action",
  "source": "framework",
  "target": "mymod.game.mod",
  "payload": { ... },
  "require_ack": true,
  "message_id": "uuid-12345"
}
```

Client responds with:

```json
{
  "type": "ack",
  "source": "mymod.game.mod",
  "target": "framework",
  "payload": {
    "message_id": "uuid-12345"
  }
}
```

---

## Security Considerations

- **Trust model:** Mods are trusted; framework doesn't sandbox actions
- **No authentication:** Pipe access is local only
- **No encryption:** Data stays on local machine
- **Property resolution:** Mods are responsible for valid property paths

The framework provides no security guarantees for malicious mods. This is consistent with UE4SS's general trust model.