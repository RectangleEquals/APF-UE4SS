# AP Framework

AP Framework connects games running on UE4SS to [Archipelago Multiworld Randomizer](https://archipelago.gg). It installs alongside your game as a set of UE4SS mods and handles everything needed to participate in a multiworld — AP server connection, item routing, location checks, and real-time accessibility tracking.

---

## For Developers

Building a mod for a new game, or extending AP Framework? See the [developer documentation](dev/README.md).

---

## Quick Start (Players)

1. **Install UE4SS** in your game root if you haven't already
2. **Download AP Framework** from the releases page and extract it
3. **Run APF Manager** and open the **Setup tab** — enter your game root folder. APF Manager detects your UE4SS installation and attempts to determine the game name; verify and correct it if needed.
4. In APF Manager, **download game-specific mods** for your game from the configured repository.
5. In the **Deploy tab**, click **Deploy Selected** — APF Manager copies all mods and updates `mods.txt`
6. **Verify `game_name`** in `framework_config.json` before first launch (see [Configuring the Framework](#configuring-the-framework))
7. **Generate and host a multiworld** with `apf.apworld` installed (see [Generating a Multiworld](#generating-a-multiworld))
8. **Connect** — enter your server, slot name, and password via APF Manager's Config tab or by editing `framework_config.json` directly
9. Launch the game — the framework connects and item/location routing begins

For detailed setup instructions, see the [APF Manager guide](apf_manager.md).

---

## What Is Included

### Game-Agnostic Core (always deployed)

| Component | Description |
|---|---|
| **APFrameworkCore.dll** | Core orchestrator — manages mod discovery, AP server connection, item routing, and IPC server |
| **APClientLib.dll** | Per-mod Lua API — each mod that calls `require("APClientLib")` gets its own independent context |
| **apf.apworld** | The Archipelago world file — reads capabilities from player YAMLs and builds items/locations/regions dynamically |

### Game-Specific Mods (vary by game)

| Component | Description |
|---|---|
| **APFrameworkMod** | Required UE4SS mod — registers game-specific tick hooks and loads the framework DLLs. A version must exist for your specific game; no guarantee one has been developed for every game. |

Additional mods — UI panels, tracker overlays, randomizer content mods — depend entirely on what has been developed for the selected game. APF Manager shows what is available for the game you have configured.

---

## Configuring the Framework

Before launching the game for the first time, verify `framework_config.json` is correct. This file is located at:

```
ue4ss/Mods/APFrameworkMod/framework_config.json
```

> **Important:** APF Manager only copies this file on first deploy (subsequent deploys preserve your existing config). If `game_name` doesn't match your game, the framework's IPC pipe will be misconfigured and no mods will connect.

Key settings to verify:

| Setting | Description |
|---|---|
| `game_name` | Must match your game's internal name. Controls the IPC pipe (`APFramework_{game_name}`). |
| `ap_server.host` | Archipelago server hostname or IP |
| `ap_server.port` | Server port (default `38281`) |
| `ap_server.slot_name` | Your player slot name |
| `ap_server.password` | Slot password, if any |

APF Manager's **Config tab** edits `ap_server` connection settings without opening the file manually. `game_name` must be set by hand if it needs to change.

---

## Generating a Multiworld

A multiworld must be generated and hosted before players can connect. **Only the person generating needs `apf.apworld` installed** — other players only provide their YAML config file.

1. **Install `apf.apworld`** — double-click to let Archipelago install it automatically, or copy it to `Archipelago/custom_worlds/`.

2. **Get your YAML** — on first launch, the framework generates a template YAML in `ue4ss/Mods/APFrameworkMod/output/`. Edit any options you want to change, then send it to the person generating the multiworld. They place it in `Archipelago/players/` alongside all other players' YAMLs.

3. **Generate** — run Archipelago's generator with all player YAMLs. It produces `AP_<SEED>.zip` in `Archipelago/output/` (containing `AP_<SEED>.archipelago` and `AP_<SEED>_Spoiler.txt`).

4. **Host** — open the `.zip` file in the Archipelago app to host locally, or upload it to Archipelago's website. All players connect to the same hosted session.

5. **Connect** — once the session is live, enter the server details in APF Manager's Config tab (or `framework_config.json`) and launch the game.

> **Note:** Some games may have UI mods that provide an in-game connection panel. Check what mods are available for your specific game.

---

## Troubleshooting

Log output is written to two places:

- **UE4SS.log** — at `<GameName>/Binaries/<Platform>/ue4ss/UE4SS.log`. Contains UE4SS output and framework messages forwarded to the console (controlled by `logging.console` in `framework_config.json`).
- **Framework log** — path set by `logging.file` in `framework_config.json` (defaults to `ap_framework.log` in the APFrameworkMod folder). Contains framework-level diagnostics only.

For more help, see the [APF Manager guide — Troubleshooting](apf_manager.md#troubleshooting).
