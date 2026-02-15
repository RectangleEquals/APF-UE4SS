"""
Location definitions for the AP Framework World.

Locations are dynamically created from the capabilities config file.
"""

from typing import Dict, List, NamedTuple, Optional
from BaseClasses import Location


class APFrameworkLocation(Location):
    """
    A location in the AP Framework world.

    Locations are defined by the mods running in-game and their definitions
    come from the capabilities config file.
    """
    game: str = "APFramework"  # Will be overridden per-game


class CountRequirement(NamedTuple):
    """Requirement for N of a specific item."""
    item: str
    count: int


class LocationData(NamedTuple):
    """Data structure for location definitions."""
    code: int
    name: str
    mod_id: str
    instance: int  # Instance number for multi-instance locations
    region: str  # Region this location belongs to (default: "Main")
    requires_all: List[str] = []     # ALL required items (AND)
    requires_any: List[str] = []     # ANY required items (OR)
    requires_count: List[CountRequirement] = []  # N of item required
    requires_option: str = ""        # Option conditional


def build_location_table(capabilities: dict) -> Dict[str, LocationData]:
    """
    Build the location table from capabilities config.

    Uses a two-pass approach to handle multi-instance locations:
    locations with the same name get suffixed with #1, #2, etc.

    Args:
        capabilities: The loaded capabilities config dict

    Returns:
        Dict mapping location display name to LocationData
    """
    location_table: Dict[str, LocationData] = {}
    locations = capabilities.get("locations", [])

    # First pass: count instances per name
    name_counts: Dict[str, int] = {}
    for loc_data in locations:
        name = loc_data["name"]
        name_counts[name] = name_counts.get(name, 0) + 1

    # Second pass: build table with unique display names
    for loc_data in locations:
        name = loc_data["name"]
        instance = loc_data.get("instance", 1)
        display_name = f"{name} #{instance}" if name_counts[name] > 1 else name

        # Parse requires_count entries
        requires_count_raw = loc_data.get("requires_count", [])
        requires_count = [
            CountRequirement(item=rc["item"], count=rc.get("count", 1))
            for rc in requires_count_raw
        ]

        location_table[display_name] = LocationData(
            code=loc_data["id"],
            name=display_name,
            mod_id=loc_data.get("mod_id", ""),
            instance=instance,
            region=loc_data.get("region", "Main"),
            requires_all=loc_data.get("requires", []),
            requires_any=loc_data.get("requires_any", []),
            requires_count=requires_count,
            requires_option=loc_data.get("requires_option", "")
        )

    return location_table


def get_locations_by_region(location_table: Dict[str, LocationData]) -> Dict[str, list]:
    """
    Group locations by their region.

    Args:
        location_table: The location table

    Returns:
        Dict mapping region name to list of location names
    """
    regions: Dict[str, list] = {}

    for name, data in location_table.items():
        region = data.region
        if region not in regions:
            regions[region] = []
        regions[region].append(name)

    return regions


def get_locations_by_mod(location_table: Dict[str, LocationData]) -> Dict[str, list]:
    """
    Group locations by their source mod.

    Args:
        location_table: The location table

    Returns:
        Dict mapping mod_id to list of location names
    """
    mods: Dict[str, list] = {}

    for name, data in location_table.items():
        mod_id = data.mod_id
        if mod_id not in mods:
            mods[mod_id] = []
        mods[mod_id].append(name)

    return mods
