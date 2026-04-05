# Developer Documentation

AP Framework is a middleware system that connects UE4SS game mods to [Archipelago Multiworld Randomizer](https://archipelago.gg). With it, you can build a Lua (or Blueprint) UE4SS mod for any game that integrates natively with Archipelago — without implementing any AP server communication yourself.

---

## For Players

Looking to install and play? See the [player guide](../README.md).

---

## What Can You Build?

Using AP Framework, you can create mods that:

- Add items and locations from your game into an Archipelago multiworld
- Receive items sent by other players and apply them in-game
- Report location checks back to the AP server
- Display real-time accessibility information via the tracker engine
- Interact with other mods via a cross-mod API

**Supported mod types:**

| Type | Description |
|---|---|
| **Non-AP UE4SS mods** | Regular UE4SS mods with no framework involvement. May still affect AP mod behavior. Document any interactions if relevant. |
| **AP game mods** | Have `manifest.json` with `capabilities` — contribute items, locations, and regions to AP generation. Register during the `REGISTRATION` phase. |
| **AP priority clients** | `mod_id` starts with `archipelago.<game_name>.*` (e.g., `archipelago.mygame.tracker`). Connect during `PRIORITY_REGISTRATION` (earlier window). Receive admin command access. **Must NOT declare capabilities** — they have no items, locations, or regions. They connect for admin access, UI, or tooling purposes only. Examples: tracker mods, UI mods, admin tools. |

> **Note:** C++ UE4SS mods may also be supportable via direct APClientLib linkage, but this is currently untested and undocumented.

---

## Architecture at a Glance

```
Game (UE4SS)
├── APFrameworkCore.dll     ← Orchestrator: lifecycle, IPC server, AP connection, tracker engine
│   └── APShared (static)  ← Shared types: logic evaluator, IPC types, manifest types
└── APClientLib.dll         ← Per-mod Lua API: one context per require("APClientLib")
    └── APShared (static)

Named Pipe IPC  ←→  APFramework_{GameName}
(JSON over 4-byte length-prefixed frames; large messages auto-split with zlib + base64)

Archipelago Server
└── apf.apworld             ← Python world: reads capabilities_data YAML option,
                               builds items/locations/regions dynamically per player
```

Each mod that calls `require("APClientLib")` gets its own independent context — separate IPC connection, separate callback slots, separate mod identity. Multiple mods can coexist without interfering.

---

## Quick Start

1. Create a `Mods/YourModName/` folder
2. Write `manifest.json` with a `mod_id` and declare your items and locations
3. Write `Scripts/main.lua` to register callbacks and call `APClient.connect()`
4. Write an `install.json` deployment descriptor for your mod, then configure APF Manager's **Setup tab** (game root, mode) and use **Deploy** — it copies all files and updates `mods.txt`. See [apf_manager.md](../apf_manager.md) for details.
5. Generate a multiworld with `apf.apworld` installed — your mod's items and locations appear automatically
6. Launch the game — the framework connects to the AP server using settings from `framework_config.json`

---

## Documentation Index

| Document | Description |
|---|---|
| [logic.md](logic.md) | **Logic expressions** — the declarative syntax for declaring access requirements in manifests. Same grammar used by both the Python apworld (AP generation) and C++ tracker engine (real-time scoring). Start here if you are writing location or region logic. |
| [manifest.md](manifest.md) | **manifest.json schema** — complete reference for all fields: `mod_id`, options, goals, regions, locations, items, item actions, cross-mod overrides. |
| [framework.md](framework.md) | **Framework system overview** — architecture, components, 12-state lifecycle, registration phases, IPC protocol, all message types, configuration, session state, cross-mod API. |
| [mods.md](mods.md) | **Building a game mod** — step-by-step getting started, full Lua API reference, all 13 callbacks, lifecycle pattern, item receiving, cross-mod API usage, priority vs regular mods. |
| [world.md](world.md) | **The apworld** — how `apf.apworld` generates multiworlds from capabilities data, logic modes, option pruning, ID assignment, multi-mod composition. |
| [tracker.md](tracker.md) | **Tracker engine** — subscribing to real-time tracker data, full snapshot and update schemas, the `ScoredNode` AST tree structure, display region derivation. |
| [templates.md](templates.md) | **Template system** — reusable JSON fragments via the `include` field, vocabulary validation, directory structure, how to add templates for a new game. |
| [publishing.md](publishing.md) | **Publishing a registry** — how to structure a GitHub registry repo, `mod_id` and folder conventions, `ue4ss.json` reference, GitHub topic tags for discovery, versioning, CI testing, and release checklist. |

---

## Contributing

| Document | Description |
|---|---|
| [dev_setup.md](dev_setup.md) | **Source build + contribution setup** — prerequisites (Git, VS 2022, CMake, vcpkg), SQLite3, CMake configure, clangd, Python/APF Manager environment, `__version__.py`, versioning strategy. *Not required for mod development* — mod developers only need sections 6–8. |
