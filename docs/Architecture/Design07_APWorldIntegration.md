# Design07: AP World Integration

> How the framework integrates with Archipelago's Python-based world packages.

---

## Overview

The framework generates a capabilities config file that the AP World reads during generation. This bridges the runtime mod system with Archipelago's static generation process.

---

## Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPABILITY CONFIG WORKFLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ 1. Framework     │                                                       │
│  │    generates     │──► AP_Capabilities_<slot_name>.json                   │
│  │    config        │                                                       │
│  └──────────────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ 2. Player copies │                                                       │
│  │    to Players/   │──► Archipelago/Players/AP_Capabilities_Player1.json  │
│  │    directory     │                                                       │
│  └──────────────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ 3. Player        │                                                       │
│  │    updates YAML  │──► Player1.yaml references the config file           │
│  │                  │                                                       │
│  └──────────────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ 4. AP World      │                                                       │
│  │    reads config  │──► Creates items/locations dynamically                │
│  │                  │                                                       │
│  └──────────────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ 5. Generation    │                                                       │
│  │    produces      │──► Multiworld .zip file                               │
│  │    output        │                                                       │
│  └──────────────────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Capabilities Config File

### Location

Generated to: `ue4ss/Mods/APFrameworkMod/output/AP_Capabilities_<slot_name>.json`

Player copies to: `Archipelago/Players/AP_Capabilities_<slot_name>.json`

### Format

```json
{
  "version": "1.0.0",
  "game": "Palworld",
  "slot_name": "Player1",
  "checksum": "a1b2c3d4e5f6...",
  "id_base": 6942067,
  "generated_at": "2024-01-15T12:30:45Z",
  "mods": [
    {
      "mod_id": "mymod.palworld.items",
      "version": "1.0.0",
      "name": "Item Mod"
    }
  ],
  "locations": [
    {
      "id": 6942067,
      "name": "Defeat Forest Boss",
      "mod_id": "mymod.palworld.items",
      "instance": 1
    },
    {
      "id": 6942068,
      "name": "Kill 20 Enemies #1",
      "mod_id": "mymod.palworld.items",
      "instance": 1
    },
    {
      "id": 6942069,
      "name": "Kill 20 Enemies #2",
      "mod_id": "mymod.palworld.items",
      "instance": 2
    }
  ],
  "items": [
    {
      "id": 6942100,
      "name": "Speed Boots",
      "type": "progression",
      "mod_id": "mymod.palworld.items",
      "count": 2
    },
    {
      "id": 6942101,
      "name": "Wood",
      "type": "filler",
      "mod_id": "mymod.palworld.items",
      "count": -1
    }
  ]
}
```

### Fields

| Field | Description |
|-------|-------------|
| `version` | Config schema version |
| `game` | Game identifier |
| `slot_name` | Player's slot name |
| `checksum` | Ecosystem checksum for validation |
| `id_base` | Base ID used for assignment |
| `generated_at` | Generation timestamp |
| `mods` | List of contributing mods |
| `locations` | All locations with assigned IDs |
| `items` | All items with assigned IDs |

---

## YAML Configuration

### Player's YAML

```yaml
name: Player1
game: Palworld
description: My Palworld randomizer slot

Palworld:
  capabilities_file: "AP_Capabilities_Player1.json"
  # Game-specific options...
  starting_inventory:
    "Basic Pickaxe": 1
```

### Required Option

The AP World must define `capabilities_file` as an option:

```python
# In options.py
from Options import TextChoice

class CapabilitiesFile(TextChoice):
    """Path to the capabilities config file."""
    display_name = "Capabilities File"
    default = ""
```

---

## AP World Reading Capabilities

### generate_early Hook

```python
# In __init__.py
from BaseClasses import Item, Location, Region, MultiWorld
from .Items import PalworldItem
from .Locations import PalworldLocation
import json
import os

class PalworldWorld(World):
    game = "Palworld"

    def generate_early(self):
        # Get capabilities file path from options
        cap_filename = self.options.capabilities_file.value
        if not cap_filename:
            raise Exception("capabilities_file option is required")

        # Build full path
        players_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "Players"
        )
        cap_path = os.path.join(players_dir, cap_filename)

        # Load capabilities
        if not os.path.exists(cap_path):
            raise Exception(f"Capabilities file not found: {cap_path}")

        with open(cap_path) as f:
            self.capabilities = json.load(f)

        # Validate checksum matches expected
        self.validate_capabilities()
```

### Creating Items

```python
def create_items(self):
    for item_data in self.capabilities["items"]:
        # Determine count
        count = item_data["count"]
        if count == -1:
            count = self.calculate_filler_count(item_data)

        # Create item instances
        for i in range(count):
            item = PalworldItem(
                name=item_data["name"],
                classification=self.get_classification(item_data["type"]),
                code=item_data["id"],
                player=self.player
            )
            self.multiworld.itempool.append(item)

def get_classification(self, type_str):
    mapping = {
        "progression": ItemClassification.progression,
        "useful": ItemClassification.useful,
        "filler": ItemClassification.filler,
        "trap": ItemClassification.trap
    }
    return mapping.get(type_str, ItemClassification.filler)
```

### Creating Locations

```python
def create_regions(self):
    # Create main region
    menu = Region("Menu", self.player, self.multiworld)
    main = Region("Main", self.player, self.multiworld)

    # Add locations to main region
    for loc_data in self.capabilities["locations"]:
        location = PalworldLocation(
            player=self.player,
            name=loc_data["name"],
            address=loc_data["id"],
            parent=main
        )
        main.locations.append(location)

    # Connect regions
    menu.connect(main)

    # Add to multiworld
    self.multiworld.regions.append(menu)
    self.multiworld.regions.append(main)
```

---

## ID Conflict Handling

### Detection

The AP World detects conflicts during generation:

```python
def validate_capabilities(self):
    # Check for conflicts with other games
    for game_world in self.multiworld.worlds.values():
        if game_world.player == self.player:
            continue

        # Check location ID overlap
        their_locations = set(loc.address for loc in game_world.get_locations())
        my_locations = set(loc["id"] for loc in self.capabilities["locations"])

        conflicts = their_locations & my_locations
        if conflicts:
            self.remap_ids(conflicts)
```

### Remapping

```python
def remap_ids(self, conflicting_ids):
    # Find safe range
    all_used = self.get_all_used_ids()
    safe_start = max(all_used) + 1000

    # Remap conflicting locations
    remap = {}
    for old_id in sorted(conflicting_ids):
        remap[old_id] = safe_start
        safe_start += 1

    # Apply remapping
    for loc_data in self.capabilities["locations"]:
        if loc_data["id"] in remap:
            loc_data["id"] = remap[loc_data["id"]]

    # Store remapping for data packages
    self.id_remapping = remap
```

### Data Package Communication

The remapping is communicated via data packages:

```python
def fill_slot_data(self):
    return {
        "id_remapping": getattr(self, "id_remapping", {}),
        "capabilities_checksum": self.capabilities["checksum"]
    }
```

The framework reads this during SYNCING and updates its internal tables.

---

## Multi-Slot Support

### Policy

- **One machine = one slot**
- No support for co-op/split-screen within a single slot
- Each player generates their own capability config

### Multiple Players

```
Player 1's Machine:
  └── AP_Capabilities_Player1.json

Player 2's Machine:
  └── AP_Capabilities_Player2.json

Player 3's Machine:
  └── AP_Capabilities_Player3.json
```

### Generation

Each player's YAML references their own config:

```yaml
# Player1.yaml
name: Player1
game: Palworld
Palworld:
  capabilities_file: "AP_Capabilities_Player1.json"

# Player2.yaml
name: Player2
game: Palworld
Palworld:
  capabilities_file: "AP_Capabilities_Player2.json"
```

---

## Default Workflow

The standard workflow requires a game restart to apply new capabilities:

```
1. Player installs mods
2. Player launches game
3. Framework discovers mods, generates config
4. Player exits game
5. Player copies config to Players/
6. Player updates YAML
7. Host generates multiworld
8. Player launches game
9. Framework validates checksum
10. Game proceeds with AP session
```

### Priority Client Optimization

A priority client could potentially optimize this workflow by:
- Detecting when capabilities change
- Notifying player to regenerate
- Automating file copying
- Triggering game restart

However, the default workflow still requires restart because:
- UE4SS loads mods at game start
- Mod capabilities are baked into save state
- Mid-game capability changes could corrupt saves

---

## Error Handling

### Missing Capabilities File

```python
if not os.path.exists(cap_path):
    raise Exception(
        f"Capabilities file not found: {cap_path}\n"
        f"Please copy your AP_Capabilities file to the Players directory."
    )
```

### Checksum Mismatch

```python
def validate_checksum_on_connect(self, received_checksum):
    if received_checksum != self.capabilities["checksum"]:
        raise Exception(
            "Mod configuration has changed since generation.\n"
            "Please regenerate the multiworld or restore original mods."
        )
```

### Invalid Capabilities Format

```python
def load_capabilities(self, path):
    try:
        with open(path) as f:
            data = json.load(f)

        # Validate required fields
        required = ["version", "game", "locations", "items", "checksum"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        return data
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in capabilities file: {e}")
```