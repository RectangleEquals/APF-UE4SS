# Design03: Lifecycle State Machine

> The framework operates as a finite state machine with well-defined states and transitions.

---

## State Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LIFECYCLE STATES                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐                                                           │
│  │ UNINITIALIZED│                                                           │
│  └──────┬───────┘                                                           │
│         │ Game launches, UE4SS loads APFrameworkMod                         │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │INITIALIZATION│ Load config, set up logging, create IPC server            │
│  └──────┬───────┘                                                           │
│         │ Success                                                           │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │  DISCOVERY   │ Scan for mod manifests in ue4ss/Mods/*/                   │
│  └──────┬───────┘                                                           │
│         │ Manifests found                                                   │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │  VALIDATION  │ Validate manifests, detect conflicts                      │
│  └──────┬───────┘                                                           │
│         │ No conflicts ──────────────────────────────────┐                  │
│         ▼                                                │ Conflicts found  │
│  ┌──────────────┐                                        ▼                  │
│  │  GENERATION  │ Generate capabilities config    ┌─────────────┐           │
│  └──────┬───────┘                                 │ ERROR_STATE │◄─────┐    │
│         │ Config generated                        └──────┬──────┘      │    │
│         ▼                                                │              │    │
│  ┌──────────────┐                                        │ CMD_RESTART  │    │
│  │PRIORITY_REG  │ Await priority client registration     │              │    │
│  └──────┬───────┘                                        ▼              │    │
│         │ All priority clients registered ───────► (back to INIT)      │    │
│         │ Timeout ───────────────────────────────────────┼──────────────┘    │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │ REGISTRATION │ Await regular client registration                         │
│  └──────┬───────┘                                                           │
│         │ All clients registered                                            │
│         │ Timeout ───────────────────────────────────────► ERROR_STATE      │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │  CONNECTING  │ Connect to AP server                                      │
│  └──────┬───────┘                                                           │
│         │ Connected                                                         │
│         │ Failed ────────────────────────────────────────► ERROR_STATE      │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │   SYNCING    │ Cache data packages, sync state with AP server            │
│  └──────┬───────┘                                                           │
│         │ Synced                                                            │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │    ACTIVE    │ Main game loop, process items/locations                   │
│  └──────┬───────┘                                                           │
│         │ CMD_RESYNC from priority client                                   │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │  RESYNCING   │ Broadcast RESYNC to clients, re-register, reconnect       │
│  └──────────────┘                                                           │
│         │                                                                    │
│         └──────────────────────► (back to PRIORITY_REG)                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## State Descriptions

| State | Description | Exit Conditions |
|-------|-------------|-----------------|
| `UNINITIALIZED` | Framework not yet loaded | APFrameworkMod calls `initialize()` |
| `INITIALIZATION` | Loading config, logging, IPC server | Success → DISCOVERY, Failure → ERROR_STATE |
| `DISCOVERY` | Scanning `ue4ss/Mods/*/manifest.json` | Manifests found → VALIDATION |
| `VALIDATION` | Validating manifests, checking conflicts | No conflicts → GENERATION, Conflicts → ERROR_STATE |
| `GENERATION` | Generating capabilities config file | Config generated → PRIORITY_REGISTRATION |
| `PRIORITY_REGISTRATION` | Awaiting priority client registration | All registered → REGISTRATION, Timeout → ERROR_STATE |
| `REGISTRATION` | Awaiting regular client registration | All registered → CONNECTING, Timeout → ERROR_STATE |
| `CONNECTING` | Establishing AP server connection | Connected → SYNCING, Failed → ERROR_STATE |
| `SYNCING` | Caching data packages, syncing state | Synced → ACTIVE |
| `ACTIVE` | Main loop - processing items/locations | CMD_RESYNC → RESYNCING, Error → ERROR_STATE |
| `RESYNCING` | Re-registering mods, reconnecting | Complete → PRIORITY_REGISTRATION |
| `ERROR_STATE` | Paused, awaiting recovery command | CMD_RESTART → INITIALIZATION |

---

## Discovery vs. Mod Loading

**Important:** The framework discovers manifests by **filesystem scan** — mods don't need to be loaded by UE4SS yet.

Discovery happens during APFrameworkMod's top-level execution, before UE4SS begins its event loop.

### Discovery Process

1. Scan `ue4ss/Mods/*/manifest.json` for all manifest files
2. Parse each manifest and check `enabled` field
3. **Skip manifests with `"enabled": false`** — they are completely ignored
4. Collect enabled manifests for validation

**Note:** Disabling a mod in UE4SS (`mods.txt` or `mods.json`) does NOT prevent discovery. To exclude a mod from AP Framework, set `"enabled": false` in its `manifest.json`.

### Why This Approach?

1. APFrameworkMod can "consume" UE4SS's event loop during early lifecycle states
2. Prevents race conditions from mods attempting to connect prematurely
3. Client mods trying to connect before IPC server is ready simply fail and retry
4. Client mods trying to register before REGISTRATION state receive rejection responses
5. State machine ensures orderly progression regardless of mod load timing

### Premature Registration Handling

If a client mod loads and tries to register too early:
- Framework sends rejection response with current state
- Mod can listen for `lifecycle` messages and retry when appropriate
- This is expected behavior, not an error condition

---

## Registration Mechanism

The framework uses a **hybrid registration approach**:

### How It Works

1. **Explicit Call:** Mods must call `APClientLib.register()` explicitly
2. **Lifecycle Awareness:** Mods should await `lifecycle` IPC message first

### Recommended Pattern

```lua
local APClientLib = require("APClientLib")

APClientLib.on_lifecycle(function(state, message)
    if state == "REGISTRATION" then
        APClientLib.register()
    end
end)
```

### Why Hybrid?

- **Explicit call** gives mods control over timing
- **Lifecycle message** ensures registration at correct time
- Early attempts are rejected with clear error
- Flexible yet safe

---

## State Transitions

### Normal Flow

```
1. Game launches
   └─► INITIALIZATION
        └─► DISCOVERY
             └─► VALIDATION
                  └─► GENERATION
                       └─► PRIORITY_REGISTRATION
                            └─► REGISTRATION
                                 └─► CONNECTING
                                      └─► SYNCING
                                           └─► ACTIVE
```

### Error Recovery

```
ACTIVE ──(error)──► ERROR_STATE ──(CMD_RESTART)──► INITIALIZATION
                                                        │
                                                        └──► (normal flow)
```

### Resync Flow

```
ACTIVE ──(CMD_RESYNC)──► RESYNCING ──► PRIORITY_REGISTRATION
                                             │
                                             └──► (normal flow continues)
```

---

## Transition Triggers

### INITIALIZATION → DISCOVERY

**Trigger:** Config and IPC server successfully initialized

**Actions:**
1. Load `framework_config.json`
2. Initialize logging
3. Create IPC server on `\\.\pipe\APFramework_<game_name>`
4. Transition to DISCOVERY

### DISCOVERY → VALIDATION

**Trigger:** Filesystem scan complete

**Actions:**
1. Scan `ue4ss/Mods/*/manifest.json`
2. Parse all found manifests
3. Identify priority clients vs regular clients
4. Transition to VALIDATION

### VALIDATION → GENERATION

**Trigger:** All manifests valid, no conflicts

**Actions:**
1. Validate each manifest against schema
2. Check for unique capability conflicts
3. Check incompatibility rules
4. If conflicts: → ERROR_STATE
5. If valid: → GENERATION

### GENERATION → PRIORITY_REGISTRATION

**Trigger:** Capabilities config generated

**Actions:**
1. Assign IDs to all locations and items
2. Generate `AP_Capabilities_<slot_name>.json`
3. Write to configured output directory
4. Transition to PRIORITY_REGISTRATION

### PRIORITY_REGISTRATION → REGISTRATION

**Trigger:** All discovered priority clients registered OR timeout

**Actions:**
1. Broadcast `lifecycle: PRIORITY_REGISTRATION` message
2. Wait for registration from `archipelago.<game>.*` mods
3. On all registered: → REGISTRATION
4. On timeout: → ERROR_STATE (if priority clients expected but missing)

### REGISTRATION → CONNECTING

**Trigger:** All discovered regular clients registered

**Actions:**
1. Broadcast `lifecycle: REGISTRATION` message
2. Wait for registration from all discovered manifests
3. On all registered: → CONNECTING
4. On timeout: → ERROR_STATE

### CONNECTING → SYNCING

**Trigger:** WebSocket connection established

**Actions:**
1. Connect to AP server with slot/password
2. Handle connection failure → ERROR_STATE
3. On connected: → SYNCING

### SYNCING → ACTIVE

**Trigger:** Data packages cached, state reconciled

**Actions:**
1. Receive and cache data packages
2. Load `session_state.json` if exists
3. Validate checksum
4. Reconcile local state with server state
5. Request any missing items
6. Transition to ACTIVE

### ACTIVE → RESYNCING

**Trigger:** `CMD_RESYNC` from priority client

**Actions:**
1. Broadcast `lifecycle: RESYNCING` to all clients
2. Clear registration state
3. Transition to RESYNCING

### RESYNCING → PRIORITY_REGISTRATION

**Trigger:** Resync preparation complete

**Actions:**
1. Disconnect from AP server
2. Clear session state
3. Transition to PRIORITY_REGISTRATION
4. Begin normal flow from there

---

## Timeouts

| Phase | Default Timeout | Configurable |
|-------|-----------------|--------------|
| Priority Registration | 30 seconds | Yes |
| Regular Registration | 60 seconds | Yes |
| AP Connection | 30 seconds | Yes |
| IPC Message | 5 seconds | Yes |
| Action Execution | 5 seconds | Yes |

Timeouts are configured in `framework_config.json`:

```json
{
  "timeouts": {
    "priority_registration_ms": 30000,
    "registration_ms": 60000,
    "ap_connection_ms": 30000,
    "ipc_message_ms": 5000,
    "action_execution_ms": 5000
  }
}
```

### Timeout Behavior: Registration

**Critical Rule:** If ANY discovered mod (with `enabled: true` in its manifest) fails to register before timeout, the framework enters `ERROR_STATE`.

This applies regardless of:
- Whether the mod is a priority client or regular client
- Whether the mod is disabled in UE4SS (`mods.txt` / `mods.json`)
- How many other mods successfully registered

**Rationale:** The framework discovers manifests by filesystem scan, not by checking UE4SS's load list. If a manifest exists and is enabled, the framework expects that mod to register. A partial registration indicates a misconfiguration that must be resolved.

**Examples:**

| Scenario | Result |
|----------|--------|
| 6/6 mods register before timeout | → CONNECTING |
| 5/6 mods register, timeout expires | → ERROR_STATE |
| 0/6 mods register, timeout expires | → ERROR_STATE |
| Mod disabled in UE4SS but enabled in manifest | → ERROR_STATE (mod won't register) |
| Mod disabled in manifest | → Not expected to register (skipped during discovery) |

**Resolution:** If a mod's manifest exists but the mod should not participate:
1. Set `"enabled": false` in the mod's `manifest.json`, OR
2. Delete the `manifest.json` file

### Timeout Behavior: Action Execution

If a mod receives `execute_action` but fails to send `action_result` within the timeout:
1. Framework logs the timeout with item ID and mod ID
2. Framework enters `ERROR_STATE`
3. Priority clients are notified

**Rationale:** A missing action result indicates the mod failed to fulfill its "contract" (the capability it promised in its manifest). This is a critical error that requires investigation. The AP Server remains the source of truth, so a resync or restart can recover the session.

See [Design10_Threading.md](Design10_Threading.md) for implementation details.

---

## Lifecycle Messages

When transitioning states, the framework broadcasts `lifecycle` IPC messages:

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

### States Broadcasted

| State | Message |
|-------|---------|
| `PRIORITY_REGISTRATION` | "Awaiting priority client registration" |
| `REGISTRATION` | "Ready for client registration" |
| `CONNECTING` | "Connecting to AP server" |
| `SYNCING` | "Synchronizing with AP server" |
| `ACTIVE` | "Framework active" |
| `RESYNCING` | "Resync in progress" |
| `ERROR_STATE` | "Error occurred: {details}" |