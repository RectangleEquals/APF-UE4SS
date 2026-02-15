"""
Options for the AP Framework World.

This module defines the configuration options that can be set in the player's YAML file.
"""

from dataclasses import dataclass
from Options import Choice, PerGameCommonOptions, TextChoice, Range


class LogicMode(Choice):
    """
    Logic mode for the AP Framework.

    none: All locations are accessible from the start (Sphere 0). No logic enforcement.
    basic: Regions and item requirements are enforced based on the capabilities config.
           Locations may require specific items or region access.
    """
    display_name = "Logic Mode"
    option_none = 0
    option_basic = 1
    default = 1


class CapabilitiesData(TextChoice):
    """
    Base64-encoded capabilities JSON data.

    The AP Framework generates this value automatically in your YAML file.
    You can also manually base64-encode your AP_Capabilities JSON file.
    """
    display_name = "Capabilities Data (Base64)"
    default = ""


class FillerItemWeight(Range):
    """
    Weight multiplier for filler items.

    Higher values will generate more filler items to fill extra locations.
    This is useful when you have more locations than useful items.
    """
    display_name = "Filler Item Weight"
    range_start = 1
    range_end = 10
    default = 5


class TrapItemChance(Range):
    """
    Percentage chance for filler items to become traps (if trap items are defined).

    0 = no traps, 100 = all filler becomes traps
    """
    display_name = "Trap Item Chance"
    range_start = 0
    range_end = 100
    default = 10


@dataclass
class APFrameworkOptions(PerGameCommonOptions):
    """Options dataclass for AP Framework worlds."""
    capabilities_data: CapabilitiesData
    logic_mode: LogicMode
    filler_item_weight: FillerItemWeight
    trap_item_chance: TrapItemChance
