# APF Manager

APF Manager is the installation and deployment tool for AP Framework. It handles downloading mods, copying files to the correct locations, managing `mods.txt` load order, and editing connection settings — so you don't have to do any of it by hand.

> **Note:** APF Manager is currently distributed as a Python package (`tools/apf_manager/`). A standalone `apf.exe` executable is planned for future releases. Until then, see [Running from Source](#running-from-source) below.

---

## What It Does

- Detects your UE4SS installation from the game root folder
- Deploys AP Framework mods (DLLs, Lua scripts, Blueprint paks) to the correct locations
- Manages `mods.txt` — adds AP mods in the correct load order, preserves existing entries
- Validates your installation and reports problems with color-coded status indicators
- Edits AP server connection settings in `framework_config.json` via the Config tab
- Checks for updates from a GitHub release feed (player mode)

---

## Prerequisites

Before using APF Manager:

1. **UE4SS installed** — UE4SS must already be installed in your game's root folder. APF Manager detects UE4SS automatically by scanning from the game root for `dwmapi.dll`.

2. **An Archipelago server** — a running Archipelago multiworld with `apf.apworld` installed. See the [Archipelago documentation](https://archipelago.gg) for setting up a server.

3. **Python 3.10+** (until standalone exe is available) — with `kivy`, `kivymd`, and dependencies installed.

---

## Running from Source

```
cd path/to/project/tools
python apf_manager
```

Or from the project root:
```
python tools/apf_manager
```

A GUI window opens. On first launch, the Setup tab appears automatically.

---

## Setup Tab

The Setup tab is where you configure APF Manager before deploying anything.

### Mode

| Mode | Use when |
|---|---|
| **Player** | You downloaded AP Framework from a release. APF Manager can check for updates from the configured repo URL. |
| **Developer** | You are building from source. APF Manager deploys from your local build output. |

Click **Player** or **Developer** to switch modes. Developer-only fields (source project, build dir) are hidden in Player mode.

### Game Root

Enter the top-level folder of your game installation. For example:

```
E:/SteamLibrary/steamapps/common/YourGame
```

APF Manager scans this folder recursively to find `dwmapi.dll` (the UE4SS DLL) and derive all other paths from it:

- `binaries_dir` — where `dwmapi.dll` lives and where framework DLLs are placed
- `mods_dir` — `Mods/` subfolder where Lua mods are deployed
- `logicmods_dir` — `Content/Paks/LogicMods/` where Blueprint `.pak` files go

As you type, APF Manager validates the path and shows:
- **Green checkmark** — UE4SS detected; shows the resolved `Mods/` path
- **Red X** — detection failed; shows which component was not found

Use **Browse...** to select the folder with a file picker.

### Repository URL (Player mode)

The GitHub repository URL for the AP Framework release feed. Enter either format:

```
https://github.com/owner/repo
https://api.github.com/repos/owner/repo
```

APF Manager normalizes both formats automatically when you click **Save Settings**.

### Developer Settings (Dev mode only)

| Field | Description |
|---|---|
| **Source project root** | Root of the AP Framework source. Defaults to the project root detected from the tool's location. |
| **Build output directory** | Where compiled DLLs are. Defaults to `{source_project}/build/Release/bin`. |

### Saving Settings

Click **Save Settings** to persist configuration to disk. Settings are saved to `.apf_manager_config.json` alongside the tool. You only need to do this once; settings persist across launches.

---

## Deploy Tab

The Deploy tab shows your full mod list and provides the main deployment controls.

### Mod List

The list shows all mods APF Manager knows about, with status indicators:

| Appearance | Meaning |
|---|---|
| Normal | AP mod — managed by APF Manager |
| Dimmed | Non-AP mod — present in `mods.txt` but not managed here |
| Yellow | Warning — missing dependency or configuration issue |
| Red | Error — missing required mod or incompatibility |
| Grey | Disabled — present but not enabled in `mods.txt` |

Non-AP mods are shown for context but cannot be deployed or removed from this tab.

### Deploy Selected

Click **Deploy Selected** to install all AP mods:

1. Copies Lua mod folders to `Mods/`
2. Copies framework DLLs (`APFrameworkCore.dll`, `APClientLib.dll`) to the UE4SS binaries directory
3. Copies Blueprint `.pak` files to `Content/Paks/LogicMods/`
4. Adds each mod to `mods.txt` in the correct order (APFrameworkMod always first among AP mods)
5. Shows any manual steps required (e.g. installing a third-party dependency)

The log panel at the bottom shows progress and any warnings or errors.

### Clean

Removes all deployed AP mod folders from `Mods/`. Use this to do a clean reinstall. DLLs and non-AP mods are not affected.

### Validate

Runs deployment validation checks and logs results. Checks include:

- UE4SS detection valid
- All AP mod folders present in `Mods/`
- `mods.txt` contains all required entries in correct order
- No dependency conflicts

### Check for Updates (Player mode only)

Queries the configured GitHub release feed for the latest version and logs the result. Does not automatically download or install — just reports what is available.

---

## Config Tab

The Config tab reads and writes the AP server connection settings in the deployed `framework_config.json`. This is the recommended way to update connection details without editing the file by hand.

| Setting | Description |
|---|---|
| `Host` | Archipelago server hostname or IP |
| `Port` | Server port (default `38281`) |
| `Slot name` | Your player slot name |
| `Password` | Slot password, if any |

Click **Save** to write the changes to `framework_config.json` in the deployed APFrameworkMod folder.

> **Important:** `game_name` is **not** editable from the Config tab. APF Manager uses `copy_preserve` for `framework_config.json` — the file is only copied from source on the first deploy and preserved unchanged on all subsequent deploys. This means `game_name` must be set correctly **before the game is launched for the first time**. If `game_name` is wrong, the IPC pipe name (`\\.\pipe\APFramework_{game_name}`) will be incorrect and no mods will connect. Edit `ue4ss/Mods/APFrameworkMod/framework_config.json` manually to correct it.

---

## Connecting to Archipelago

After deploying, launch the game. The AP Framework loads automatically with UE4SS.

How you configure the connection depends on what is available for your game:

- **If the game has a UI mod** — use the in-game connection panel to enter the server address, port, slot name, and password. Settings are saved to `framework_config.json` automatically.

- **If no UI mod exists** — use APF Manager's **Config tab** (see above) to edit the `ap_server` connection settings, or edit `ue4ss/Mods/APFrameworkMod/framework_config.json` directly in a text editor.

> **Note:** A multiworld must already be generated and hosted before you can connect. See [Generating a Multiworld](README.md#generating-a-multiworld) in the main README for the full workflow, including how to install `apf.apworld` and submit your YAML.

---

## Troubleshooting

### "UE4SS not detected" in the Setup tab

APF Manager scans from the game root for `dwmapi.dll`. If detection fails:

- Verify UE4SS is installed — `dwmapi.dll` should exist in the same folder as the game executable
- Make sure the game root points to the top-level game folder, not a subfolder
- Try entering the path manually rather than using Browse if there are symlinks

### Mods not appearing in-game

- Check that `mods.txt` contains each AP mod and that it is enabled (`:1` suffix)
- `APFrameworkMod` must be first among AP mods — check the mod list order in the Deploy tab
- Ensure UE4SS is actually loaded by checking for `UE4SS.log` in the game binaries directory

### Game crashes on launch after deploying

- Check `UE4SS.log` for errors during mod load
- Verify that the framework DLLs (`APFrameworkCore.dll`, `APClientLib.dll`) are present in the UE4SS binaries directory alongside `dwmapi.dll`
- If using Blueprint mods, verify the `.pak` files are in `Content/Paks/LogicMods/` and `BPModLoaderMod` is enabled in `mods.txt`

### Connection fails (game reaches ERROR_STATE)

- Confirm the Archipelago server is running and accessible
- Check the framework log file for the specific error — the path is set by `logging.file` in `framework_config.json` (default: `ap_framework.log` in the APFrameworkMod folder). The log includes the error code and message.
- Common causes: wrong port, firewall blocking WebSocket connection, slot name mismatch

### No mods connect after launch (`game_name` mismatch)

- The IPC pipe is named `\\.\pipe\APFramework_{game_name}`. If `game_name` in `framework_config.json` does not match what the mods expect, nothing will connect.
- Edit `ue4ss/Mods/APFrameworkMod/framework_config.json` and correct `game_name`. This file is preserved on every deploy — APF Manager will not overwrite your change.

### Registration timeout (mods time out during startup)

- If a mod times out during REGISTRATION, it will not receive items for this session. Restart the game and ensure mods load quickly (no heavy initialization before `register_mod()`).
- The timeout log lists which mod IDs were still pending — check the framework log for `"Registration timeout — pending: [...]"`.

---

## Log Locations

Log output is written to two places:

- **UE4SS.log** — at `<GameName>/Binaries/<Platform>/ue4ss/UE4SS.log`. Contains UE4SS output and framework messages forwarded to the console (controlled by `logging.console` in `framework_config.json`).
- **Framework log** — path set by `logging.file` in `framework_config.json` (default: `ap_framework.log` in the APFrameworkMod folder). Contains framework-level diagnostics only.

---

## CLI Mode

APF Manager can be run headless for scripting or CI:

```
python tools/apf_manager --cli [--deploy] [--validate] [--package] [--version TAG]
```

| Flag | Effect |
|---|---|
| `--deploy` | Deploy all mods (reads saved config) |
| `--validate` | Run validation checks; exits with code 1 if any errors |
| `--package` | Build a release zip |
| `--version TAG` | Version tag for the package (e.g. `v0.1.0`) |

CLI mode reads configuration from the same `.apf_manager_config.json` file as the GUI. Configure game root and paths via the GUI first, then use CLI for automation.

---

*See also: [README.md](README.md) for installation overview | [dev/README.md](dev/README.md) for building mods*
