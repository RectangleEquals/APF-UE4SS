# Palworld TechShuffle — Setup Guide

TechShuffle shuffles Palworld's technology tree into the Archipelago item pool. Researching
a tech in-game checks the corresponding location; receiving a tech item unlocks it for you.

## Required: PalSchema

TechShuffle requires the **PalSchema** mod to unlock technologies programmatically.

**Installing PalSchema:**
1. Download PalSchema from the UE4SS mod repository or its official release page.
2. Place the `PalSchema` mod folder inside your UE4SS `Mods/` directory.
3. Ensure `PalSchema : 1` is present in `mods.txt` **before** `PalworldTechShuffle`.

> Without PalSchema, tech items received from Archipelago will have no effect.

## Configuration Options

TechShuffle is configured via your Archipelago YAML before generating a seed:

| Option | Values | Description |
|--------|--------|-------------|
| `shuffle_scope` | `key` / `standard` / `full` | Which techs to randomize (~53 / ~205 / all 502) |
| `shuffle_boss_tech` | `true` / `false` | Include boss-gated technologies |
| `tier_progression` | `open` / `keyed` / `strict` | How tier progression is gated |
| `lock_mode` | `lock` / `hide` | How unresearched techs appear |
| `starting_techs` | integer | Number of free techs at game start |

## Troubleshooting

- If techs are not being unlocked, verify PalSchema is installed and listed before TechShuffle in `mods.txt`.
- If `palworld_tech.db` is missing, re-run the deploy from APF Manager.
- Check `ap_framework.log` for `[TechShuffle]` entries to diagnose issues.
