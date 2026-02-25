# Palworld Archipelago Tracker — Setup Guide

The Archipelago Tracker has two parts:

1. **PalworldArchipelagoTracker** — the Lua/UE4SS mod (installed automatically by APF Manager)
2. **APTracker.pak** — a Blueprint mod required for the in-game HUD overlay

## Installing APTracker.pak

The `.pak` file must be placed in your game's `LogicMods` folder:

```
<Palworld>/Pal/Content/Paks/LogicMods/APTracker.pak
```

> If the `LogicMods` folder does not exist, create it.

**Where to get APTracker.pak:**
- If you received an APF release zip, it is inside the `LogicMods/` subfolder.
- Otherwise, ask the developer for the latest build.

## Using the Tracker

- Press **F1** in-game to toggle the tracker overlay.
- The tracker shows your current location/item check progress.
- It will remain empty until you connect to an Archipelago server.

## Troubleshooting

- If the overlay doesn't appear, confirm `APTracker.pak` is present in `LogicMods/`.
- If the game crashes on load, the `.pak` file may be corrupt or incompatible — re-download it.
- Confirm `PalworldArchipelagoTracker : 1` appears in `mods.txt` above the Keybinds footer.
- Check `ap_framework.log` for any tracker registration errors.
