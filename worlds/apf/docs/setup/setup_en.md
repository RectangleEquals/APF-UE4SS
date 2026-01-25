# AP Framework Multiworld Setup Guide

## Overview

This guide explains how to set up your AP Framework-enabled game for Archipelago Multiworld randomization.

## Prerequisites

1. **Archipelago Installation**: Download and install Archipelago from [archipelago.gg](https://archipelago.gg)
2. **UE4SS**: Your game must have UE4SS installed with the AP Framework mod
3. **Game with AP Framework Mod**: A game running the APFrameworkMod and at least one client mod

## Step 1: Generate Your Capabilities File

Before generating a multiworld, you need a capabilities file that describes your game's items and locations.

1. Launch your game with APFrameworkMod installed
2. The framework will automatically generate `AP_Capabilities_<slot>.json` in the mod folder
3. Copy this file to Archipelago's `Players` directory

The capabilities file contains:
- All available items (progression, useful, filler, traps)
- All check locations in the game
- A checksum for validation

## Step 2: Configure Your YAML

Create a YAML configuration file in Archipelago's `Players` directory:

```yaml
name: YourPlayerName
game: APFramework  # Or your game's specific name

APFramework:
  # Path to your capabilities file (relative to Players folder or absolute)
  capabilities_file: "AP_Capabilities_Player1.json"

  # Validate checksum matches between generation and runtime
  validate_checksum: true

  # Weight for filler items (higher = more likely vs other fillers)
  filler_item_weight: 50

  # Chance (0-100) that a filler slot becomes a trap instead
  trap_item_chance: 10
```

## Step 3: Generate the Multiworld

1. Open Archipelago Launcher
2. Click "Generate"
3. Select your YAML file(s)
4. Click "Generate Game"
5. The output will be in the `output` folder

## Step 4: Connect Your Game

1. Start the Archipelago server with your generated multiworld
2. Launch your game
3. The APFrameworkMod will automatically connect to the server
4. Start playing!

## Troubleshooting

### "Capabilities file not found"

Make sure your capabilities file is:
- In the Archipelago `Players` directory, or
- Specified with an absolute path in your YAML

### "Checksum mismatch"

Your game's mods have changed since generating the multiworld. Either:
- Regenerate with the new capabilities file, or
- Set `validate_checksum: false` (not recommended)

### "ID conflict detected"

This can happen when playing with other games that use similar ID ranges. The framework will automatically remap conflicting IDs - no action needed.

### Connection Issues

Verify:
- The Archipelago server is running
- Your game is on the same network as the server
- The connection settings in `framework_config.json` are correct

## Advanced Configuration

### Custom Item Classifications

Items in your capabilities file can have these classifications:
- `progression`: Required to complete the game
- `useful`: Helpful but not required
- `filler`: Basic items to fill remaining slots
- `trap`: Negative effects (based on trap_item_chance)

### Multiple Instances

If your game has multiple instances of the same location (e.g., repeatable checks), the capabilities file tracks instance counts automatically.

## For Mod Developers

See the [Mod Development Guide](../dev/mod_guide.md) for information on:
- Creating client mods that work with AP Framework
- Defining items and locations in your manifest
- Handling received items and location checks
