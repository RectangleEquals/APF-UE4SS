# Design02: Capabilities System

> The capabilities system defines what each mod "promises" to handle at runtime.

---

## Design Philosophy

> *"If a mod can't do it, then it can't be randomized."*

The framework empowers the modding community to define randomization possibilities dynamically. Rather than predetermining what can be shuffled, mods declare their capabilities, and the framework aggregates them.

---

## Capability Categories

### Locations

Events triggered by the client mod and reported to the framework.

**Examples:**
- Defeating a boss
- Opening a chest
- Completing a quest
- Reaching a milestone (e.g., "Kill 20 Enemies")

**Responsibility:** The mod is solely responsible for detecting when a location event occurs and reporting it to the framework.

### Items

Things the framework can instruct the client mod to give/apply to the player.

**Types:**

| Type | Description | AP Classification |
|------|-------------|-------------------|
| `progression` | Unlocks abilities, tech tiers, required for logic | Progression |
| `useful` | Helpful but not required | Useful |
| `filler` | Consumables, currency, common drops | Filler |
| `trap` | Negative effects | Trap |

**Responsibility:** The mod must implement the action function that handles receiving the item.

---

## Manifest Schema

Each AP-enabled client mod must have a `manifest.json` in its mod folder.

### Full Schema

```json
{
  "mod_id": "string",
  "name": "string",
  "version": "string",
  "enabled": "boolean",
  "description": "string",
  "incompatible": [
    { "id": "string", "versions": "string | string[]" }
  ],
  "capabilities": {
    "locations": [
      { "name": "string", "amount": "number", "unique": "boolean" }
    ],
    "items": [
      {
        "name": "string",
        "type": "progression | useful | filler | trap",
        "amount": "number",
        "action": "string",
        "args": [
          { "name": "string", "type": "string | number | boolean | property", "value": "any" }
        ]
      }
    ]
  }
}
```

### Field Descriptions

#### Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mod_id` | string | Yes | — | Unique identifier: `author.game.mod_name` |
| `name` | string | Yes | — | Human-readable mod name |
| `version` | string | Yes | — | Semantic version (e.g., `1.0.0`) |
| `enabled` | boolean | No | `true` | If `false`, framework ignores this manifest entirely |
| `description` | string | No | — | Description of the mod |
| `incompatible` | array | No | — | List of incompatible mods |
| `capabilities` | object | No* | — | Locations and items. *Required for regular clients. |

**Note:** Priority Clients (`archipelago.<game>.*`) must NOT have a `capabilities` field.

### The `enabled` Field

The `enabled` field allows players to disable a mod from the AP Framework without deleting the manifest or uninstalling the mod from UE4SS.

**When `enabled: false`:**
- Framework completely ignores this manifest during discovery
- Mod's capabilities are NOT included in generation
- Mod will NOT be expected to register
- Mod will NOT receive IPC messages from framework

**Use Cases:**
- Temporarily disable a mod causing conflicts
- Keep mod installed but exclude from AP session
- Debug by isolating specific mods

**Important:** This is independent of UE4SS's mod loading. A mod can be:
- Loaded by UE4SS but disabled for AP (`enabled: false` in manifest)
- Enabled for AP but not loaded by UE4SS (mod won't register, causing timeout)

For complete mod disabling, players should both set `enabled: false` in the manifest AND disable the mod in UE4SS (`mods.txt` or `mods.json`).

#### Location Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Required | Location name |
| `amount` | number | 1 | How many instances of this location |
| `unique` | boolean | false | If true, no other mod can claim this name |

#### Item Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Required | Item name |
| `type` | string | Required | `progression`, `useful`, `filler`, or `trap` |
| `amount` | number | 1 | Number of instances or `-1` for unlimited |
| `action` | string | Required | Lua function path (e.g., `MyObj.GiveItem`) |
| `args` | array | [] | Arguments to pass to the action |

#### Argument Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Argument name (for docs/debugging) |
| `type` | string | `string`, `number`, `boolean`, or `property` |
| `value` | any | The value or special variable |

---

## Special Argument Values

The framework replaces these placeholders at runtime:

| Variable | Description |
|----------|-------------|
| `<GET_ITEM_ID>` | Assigned item ID |
| `<GET_ITEM_NAME>` | Item name from manifest |
| `<GET_PROGRESSION_COUNT>` | Current progression tier (1 to `amount`) |
| `<GET_LOCATION_ID>` | Assigned location ID |
| `<GET_LOCATION_NAME>` | Location name from manifest |

### Property Type

When `type: "property"`, the value is a Lua property path evaluated at runtime:

```json
{
  "name": "position",
  "type": "property",
  "value": "MyPlayerObj.player_pos"
}
```

APClientLib resolves `MyPlayerObj.player_pos` from the mod's Lua state when executing the action.

---

## Location Amount Semantics

The `amount` field is **syntactic sugar** for generating multiple location IDs.

### Example

```json
{
  "name": "Kill 20 Enemies",
  "amount": 5,
  "unique": false
}
```

**Expansion (with base ID 6942067):**

| Generated Name | Location ID |
|----------------|-------------|
| Kill 20 Enemies #1 | 6942067 |
| Kill 20 Enemies #2 | 6942068 |
| Kill 20 Enemies #3 | 6942069 |
| Kill 20 Enemies #4 | 6942070 |
| Kill 20 Enemies #5 | 6942071 |

### Reporting

The mod uses the `count` parameter to specify which instance:

```lua
APClientLib.location_check("Kill 20 Enemies", 3)  -- Reports #3
```

The framework maps this to the correct LocationID.

---

## Item Amount Semantics

For items, `amount` meaning varies by type:

| Type | Amount Meaning |
|------|---------------|
| `progression` | Number of tiers/levels |
| `useful` | Maximum times receivable |
| `filler` | Maximum times (or `-1` = unlimited) |
| `trap` | Maximum times triggerable |

### Progression Example

```json
{
  "name": "Speed Boots",
  "type": "progression",
  "amount": 3,
  "action": "MyMod.UpgradeBoots",
  "args": [
    { "name": "tier", "type": "number", "value": "<GET_PROGRESSION_COUNT>" }
  ]
}
```

| Receipt | `<GET_PROGRESSION_COUNT>` |
|---------|---------------------------|
| 1st | 1 |
| 2nd | 2 |
| 3rd | 3 |

---

## ID Assignment Strategy

### Configuration

IDs are assigned from a configurable base in `framework_config.json`:

```json
{
  "id_base": 6942067
}
```

### Assignment Process

1. Read `id_base` from config (default: `6942067`)
2. Assign Location IDs sequentially: `id_base + 0`, `id_base + 1`, ...
3. Assign Item IDs after locations: `id_base + location_count + 0`, ...

### Conflict Handling

If the AP World detects ID conflicts with other games:
1. AP World automatically adjusts IDs
2. Communicates remapping via data packages
3. Framework reconciles during `SYNCING` state

---

## Conflict Detection

### Unique Capabilities

If two mods claim the same unique capability name:
- Framework enters `ERROR_STATE`
- Logs detailed conflict information
- Refuses to proceed until manually resolved

### Resolution Options

1. **Disable mod in manifest** — Set `"enabled": false` in the conflicting mod's `manifest.json`
2. **Rename capability** — Change the capability name in one mod's manifest
3. **Mark as non-unique** — If both can coexist, set `"unique": false`

**Important:** Simply disabling a mod in UE4SS (via `mods.txt` or `mods.json`) does **NOT** resolve the conflict. The framework discovers manifests by scanning the filesystem, not by checking which mods UE4SS has loaded. To exclude a mod from AP Framework:

- **Recommended:** Set `"enabled": false` in the mod's `manifest.json`
- **Alternative:** Delete the `manifest.json` file entirely (not recommended)

Players may additionally disable the mod in UE4SS if they don't want it running at all, but this is optional and independent of AP Framework conflict resolution.

### Non-Unique Capabilities

For non-unique capabilities with the same name:
- Framework generates disambiguated IDs
- Each mod instance gets unique LocationID/ItemID
- Both mods can coexist

---

## Incompatibility Rules

```json
{
  "incompatible": [
    { "id": "other.mod.id", "versions": "<=0.1.0" },
    { "id": "another.mod.id", "versions": ["0.0.1", "0.0.2"] },
    { "id": "bad.mod.id" }
  ]
}
```

| Format | Meaning |
|--------|---------|
| Version constraint (`<=0.1.0`) | Incompatible with matching versions |
| Version array | Incompatible with specific versions |
| No versions field | Incompatible with all versions |

---

## Complete Manifest Example

```json
{
  "mod_id": "myname.palworld.speedmod",
  "name": "Speed Mod",
  "version": "1.1.0",
  "enabled": true,
  "description": "Adds speed-related items and locations to Palworld",
  "incompatible": [
    { "id": "other.palworld.movement", "versions": "<=0.5.0" }
  ],
  "capabilities": {
    "locations": [
      {
        "name": "Defeat Forest Boss",
        "amount": 1,
        "unique": true
      },
      {
        "name": "Kill 20 Enemies",
        "amount": 5,
        "unique": false
      }
    ],
    "items": [
      {
        "name": "Speed Boots",
        "type": "progression",
        "amount": 2,
        "action": "MyUserObj.UnlockTechnology",
        "args": [
          { "name": "id", "type": "string", "value": "<GET_ITEM_ID>" },
          { "name": "tier", "type": "number", "value": "<GET_PROGRESSION_COUNT>" }
        ]
      },
      {
        "name": "Wood",
        "type": "filler",
        "amount": -1,
        "action": "MyUserObj.SpawnItem",
        "args": [
          { "name": "id", "type": "string", "value": "<GET_ITEM_ID>" },
          { "name": "where", "type": "property", "value": "MyPlayerObj.player_pos" }
        ]
      }
    ]
  }
}
```

---

## Checksum Composition

The ecosystem checksum validates that the mod configuration matches generation:

**Components:**
1. Sorted mod IDs
2. Corresponding versions
3. SHA-1 hash of aggregated capabilities
4. Game name
5. Slot name

**Formula:**
```
checksum = SHA1(sorted_mod_ids + versions + capabilities_hash + game_name + slot_name)
```

**Usage:**
- Stored in `session_state.json` and capabilities config
- Validated during SYNCING state when reconnecting
- Mismatch triggers ERROR_STATE with `CHECKSUM_MISMATCH` error

**On Mismatch:**
A checksum mismatch indicates the mod ecosystem changed since generation. This is a user error — the framework enters ERROR_STATE and does NOT proceed. See [Design08_ErrorHandling.md](Design08_ErrorHandling.md) for details.