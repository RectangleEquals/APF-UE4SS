# Archipelago Framework Architecture

> A modular system enabling UE4SS mods to integrate with Archipelago Multiworld randomizers.

---

## Overview

The Archipelago Framework is a middleware system that bridges UE4SS Lua mods and the Archipelago Multiworld randomizer. It allows mod developers to declare "capabilities" (locations and items their mod can handle), and the framework aggregates these into a configuration that drives randomization.

**Design Philosophy:** *"If a mod can't do it, then it can't be randomized."*

Rather than predetermining what can be shuffled, the framework empowers the modding community to define and extend randomization possibilities dynamically.

---

## Architecture Documents

| Document | Description |
|----------|-------------|
| [Design01_SystemComponents.md](Design01_SystemComponents.md) | Core components (APFrameworkCore, APClientLib, APFrameworkMod) and their responsibilities |
| [Design02_CapabilitiesSystem.md](Design02_CapabilitiesSystem.md) | Capabilities design, manifest schema, conflict detection, and ID assignment |
| [Design03_LifecycleStateMachine.md](Design03_LifecycleStateMachine.md) | State machine, transitions, discovery, registration, and connection flow |
| [Design04_IPCProtocol.md](Design04_IPCProtocol.md) | Named pipes IPC, message format, and all message types |
| [Design05_MessageRouting.md](Design05_MessageRouting.md) | Item receipt flow, location check flow, and action execution |
| [Design06_PriorityClients.md](Design06_PriorityClients.md) | Priority client privileges, commands, and use cases |
| [Design07_APWorldIntegration.md](Design07_APWorldIntegration.md) | Capability config distribution, YAML configuration, and AP World reading |
| [Design08_ErrorHandling.md](Design08_ErrorHandling.md) | Error response protocol, ERROR_STATE behavior, and recovery commands |
| [Design09_Dependencies.md](Design09_Dependencies.md) | Full dependency tree, CMake configuration, and folder structures |
| [Design10_Threading.md](Design10_Threading.md) | Thread model, synchronization primitives, and race condition prevention |
| [InitialDesign.md](InitialDesign.md) | Original comprehensive design document with all details |

---

## System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ARCHIPELAGO FRAMEWORK                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     │
│  │  APFrameworkMod  │     │   APClientLib    │     │   APClientLib    │     │
│  │     (Lua)        │     │   (C++ DLL)      │     │   (C++ DLL)      │     │
│  │                  │     │                  │     │                  │     │
│  │  Entry point,    │     │  IPC Client for  │     │  IPC Client for  │     │
│  │  loads core      │     │  Client Mod A    │     │  Client Mod B    │     │
│  └────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘     │
│           │                        │                        │               │
│           │ require()              │                        │               │
│           ▼                        │                        │               │
│  ┌──────────────────┐              │ Named Pipes IPC        │               │
│  │ APFrameworkCore  │◄─────────────┴────────────────────────┘               │
│  │   (C++ DLL)      │                                                       │
│  │                  │                                                       │
│  │  - APManager     │                                                       │
│  │  - APClient      │◄────────────── WebSocket ──────────────►  AP Server   │
│  │  - APIPCServer   │                                                       │
│  │  - APCapabilities│                                                       │
│  │  - APModRegistry │                                                       │
│  │  - APStateManager│                                                       │
│  └──────────────────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**See:** [Design01_SystemComponents.md](Design01_SystemComponents.md) for full details.

---

## Lifecycle State Machine

```
UNINITIALIZED → INITIALIZATION → DISCOVERY → VALIDATION → GENERATION
                                                              ↓
    ERROR_STATE ◄── (any failure)                    PRIORITY_REGISTRATION
         │                                                    ↓
         └─── CMD_RESTART ──► INITIALIZATION           REGISTRATION
                                                              ↓
                                                         CONNECTING
                                                              ↓
                                                          SYNCING
                                                              ↓
                                                           ACTIVE
                                                              │
                                                    CMD_RESYNC │
                                                              ↓
                                                         RESYNCING
                                                              │
                                                              └──► PRIORITY_REGISTRATION
```

**See:** [Design03_LifecycleStateMachine.md](Design03_LifecycleStateMachine.md) for state descriptions and transitions.

---

## Capabilities System

Mods declare capabilities in their `manifest.json`:

```json
{
  "mod_id": "myname.palworld.speedmod",
  "name": "Speed Mod",
  "version": "1.0.0",
  "enabled": true,
  "capabilities": {
    "locations": [
      { "name": "Defeat Forest Boss", "amount": 1, "unique": true }
    ],
    "items": [
      {
        "name": "Speed Boots",
        "type": "progression",
        "amount": 2,
        "action": "MyUserObj.UnlockTech",
        "args": [{ "name": "tier", "type": "number", "value": "<GET_PROGRESSION_COUNT>" }]
      }
    ]
  }
}
```

**Note:** Set `"enabled": false` to exclude a mod from AP Framework without deleting its manifest.

**See:** [Design02_CapabilitiesSystem.md](Design02_CapabilitiesSystem.md) for full schema and semantics.

---

## IPC Protocol

Communication uses Windows Named Pipes (`\\.\pipe\APFramework_<game_name>`).

**Message Format:**
```json
{
  "type": "execute_action",
  "source": "framework",
  "target": "myname.palworld.speedmod",
  "payload": { ... }
}
```

**See:** [Design04_IPCProtocol.md](Design04_IPCProtocol.md) for all message types.

---

## Message Flows

### Item Receipt (AP Server → Mod)
```
AP Server ──ReceivedItems──► APClient ──► APMessageRouter ──► APIPCServer ──► APClientLib ──► Lua Action
```

### Location Check (Mod → AP Server)
```
Mod Event ──► APClientLib ──► APIPCServer ──► APMessageRouter ──► APClient ──LocationChecks──► AP Server
```

**See:** [Design05_MessageRouting.md](Design05_MessageRouting.md) for detailed flow diagrams.

---

## Priority Clients

Mods with `mod_id` matching `archipelago.<game>.*` are Priority Clients. They have elevated privileges but contribute no capabilities:

- Get lists of all/registered/conflicting mods
- Access logs and IPC traffic
- Force resync, reconnect, restart
- Send messages to specific clients
- Modify framework config at runtime

**See:** [Design06_PriorityClients.md](Design06_PriorityClients.md) for full privilege list.

---

## AP World Integration

1. Framework generates `AP_Capabilities_<slot_name>.json`
2. Player copies to `Archipelago/Players/`
3. Player references in their YAML:
   ```yaml
   Palworld:
     capabilities_file: "AP_Capabilities_PlayerName.json"
   ```
4. AP World reads capabilities and creates dynamic items/locations

**See:** [Design07_APWorldIntegration.md](Design07_APWorldIntegration.md) for workflow details.

---

## Error Handling

On any runtime error:
1. Log full details
2. Forward to priority clients
3. Notify regular clients with shutdown message
4. Enter `ERROR_STATE`

Recovery via priority client commands:
- `CMD_RESTART` → Full re-initialization
- `CMD_RESYNC` → Re-register and reconnect
- `CMD_RECONNECT` → Reconnect only

**See:** [Design08_ErrorHandling.md](Design08_ErrorHandling.md) for recovery protocols.

---

## Dependencies

**APFrameworkCore:**
- apclientpp (wswrap, asio, websocketpp, valijson)
- nlohmann::json
- sol2
- lua-5.4.7

**APClientLib:**
- nlohmann::json
- sol2
- lua-5.4.7

**See:** [Design09_Dependencies.md](Design09_Dependencies.md) for full dependency tree and CMake setup.

---

## Quick Reference

| Concept | Key Points |
|---------|------------|
| **Capabilities** | Locations (events mod detects) + Items (things mod can apply) |
| **Manifest** | `manifest.json` in mod folder declares capabilities |
| **Enabled** | Set `"enabled": false` in manifest to exclude mod from framework |
| **Unique** | If `unique: true`, no other mod can claim same name |
| **Amount (Location)** | Generates N separate LocationIDs |
| **Amount (Item)** | Progression tiers or max receipt count |
| **ID Base** | Default `6942067`, configurable in `framework_config.json` |
| **Checksum** | SHA-1 of (mod IDs + versions + capabilities hash + game + slot) |
| **Registration** | Explicit `APClientLib.register()` after `lifecycle` message |
| **Priority Client** | `archipelago.<game>.*` pattern, no capabilities, elevated privileges |
| **Conflict Resolution** | Use `"enabled": false` in manifest (UE4SS disable doesn't work) |

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Initial | Initial architecture documentation |