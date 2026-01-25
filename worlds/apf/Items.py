"""
Item definitions for the AP Framework World.

Items are dynamically created from the capabilities config file.
"""

from typing import Dict, NamedTuple, Optional
from BaseClasses import Item, ItemClassification


class APFrameworkItem(Item):
    """
    An item in the AP Framework world.

    Items are defined by the mods running in-game and their definitions
    come from the capabilities config file.
    """
    game: str = "APFramework"  # Will be overridden per-game


class ItemData(NamedTuple):
    """Data structure for item definitions."""
    code: int
    name: str
    classification: ItemClassification
    mod_id: str
    count: int  # -1 means filler (fill remaining slots)


def get_classification(type_str: str) -> ItemClassification:
    """Convert item type string to ItemClassification."""
    mapping = {
        "progression": ItemClassification.progression,
        "useful": ItemClassification.useful,
        "filler": ItemClassification.filler,
        "trap": ItemClassification.trap,
    }
    return mapping.get(type_str.lower(), ItemClassification.filler)


def build_item_table(capabilities: dict) -> Dict[str, ItemData]:
    """
    Build the item table from capabilities config.

    Args:
        capabilities: The loaded capabilities config dict

    Returns:
        Dict mapping item name to ItemData
    """
    item_table: Dict[str, ItemData] = {}

    for item_data in capabilities.get("items", []):
        name = item_data["name"]
        item_table[name] = ItemData(
            code=item_data["id"],
            name=name,
            classification=get_classification(item_data.get("type", "filler")),
            mod_id=item_data.get("mod_id", ""),
            count=item_data.get("count", 1)
        )

    return item_table


def get_filler_items(item_table: Dict[str, ItemData]) -> list:
    """Get list of filler item names."""
    return [name for name, data in item_table.items()
            if data.classification == ItemClassification.filler]


def get_trap_items(item_table: Dict[str, ItemData]) -> list:
    """Get list of trap item names."""
    return [name for name, data in item_table.items()
            if data.classification == ItemClassification.trap]


def get_progression_items(item_table: Dict[str, ItemData]) -> list:
    """Get list of progression item names."""
    return [name for name, data in item_table.items()
            if data.classification == ItemClassification.progression]


def get_useful_items(item_table: Dict[str, ItemData]) -> list:
    """Get list of useful item names."""
    return [name for name, data in item_table.items()
            if data.classification == ItemClassification.useful]
