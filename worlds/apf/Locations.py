"""
Location definitions for the AP Framework World.

Locations are dynamically created from the capabilities config file.
"""

import re
from typing import Dict, List, NamedTuple, Optional
from BaseClasses import Location


def derive_ap_region(logic: str, name: str, known_regions: set = None) -> str:
    """Derive the AP region for this location from its logic expression.

    Scans for the first (Can Access: R) pattern — returns R.
    Falls back to the prefix before ': ' in the name, then 'Main'.
    """
    for match in re.finditer(r'\(Can Access:\s*([^)]+)\)', logic):
        region_name = match.group(1).strip()
        if known_regions is None or region_name in known_regions:
            return region_name
    # Fallback: prefix before ': ' in location name
    if ': ' in name:
        prefix = name.split(': ')[0]
        if known_regions is None or prefix in known_regions:
            return prefix
    return "Main"


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
    region: str    # Display region derived from logic (e.g. first (Can Access: R) pattern)
    logic: str = ""  # Logic expression string


def build_location_table(capabilities: dict, known_regions: set = None) -> Dict[str, LocationData]:
    """
    Build the location table from capabilities config.

    Uses a two-pass approach to handle multi-instance locations:
    locations with the same name get suffixed with #1, #2, etc.

    Region is derived from the logic expression via (Can Access: R) patterns.

    Args:
        capabilities: The loaded capabilities config dict
        known_regions: Set of known region names for derivation (optional)

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
        logic = loc_data.get("logic", "")

        location_table[display_name] = LocationData(
            code=loc_data["id"],
            name=display_name,
            mod_id=loc_data.get("mod_id", ""),
            instance=instance,
            region=derive_ap_region(logic, name, known_regions),
            logic=logic,
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
