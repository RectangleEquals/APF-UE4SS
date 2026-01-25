"""
Location definitions for the AP Framework World.

Locations are dynamically created from the capabilities config file.
"""

from typing import Dict, NamedTuple, Optional
from BaseClasses import Location


class APFrameworkLocation(Location):
    """
    A location in the AP Framework world.

    Locations are defined by the mods running in-game and their definitions
    come from the capabilities config file.
    """
    game: str = "APFramework"  # Will be overridden per-game


class LocationData(NamedTuple):
    """Data structure for location definitions."""
    code: int
    name: str
    mod_id: str
    instance: int  # Instance number for multi-instance locations
    region: str  # Region this location belongs to (default: "Main")


def build_location_table(capabilities: dict) -> Dict[str, LocationData]:
    """
    Build the location table from capabilities config.

    Args:
        capabilities: The loaded capabilities config dict

    Returns:
        Dict mapping location name to LocationData
    """
    location_table: Dict[str, LocationData] = {}

    for loc_data in capabilities.get("locations", []):
        name = loc_data["name"]

        # Handle instance numbering in name
        instance = loc_data.get("instance", 1)
        if instance > 1:
            # Name already includes instance number from framework
            display_name = name
        else:
            display_name = name

        location_table[display_name] = LocationData(
            code=loc_data["id"],
            name=display_name,
            mod_id=loc_data.get("mod_id", ""),
            instance=instance,
            region=loc_data.get("region", "Main")
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
