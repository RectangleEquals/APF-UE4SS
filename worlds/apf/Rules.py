"""
Access rules for the AP Framework World.

Rules are built from declarative requirements in the capabilities config:
- requires (AND): All listed items must be collected
- requires_any (OR): At least one listed item must be collected
- requires_count: N copies of a specific item must be collected

Logic is only applied when logic_mode is "basic". When "none", all locations
are accessible from the start (Sphere 0 behavior).
"""

from typing import TYPE_CHECKING, Callable, Dict, List
from BaseClasses import CollectionState
from worlds.generic.Rules import set_rule

if TYPE_CHECKING:
    from . import APFrameworkWorld
    from .Locations import CountRequirement


def build_rule(
    player: int,
    requires_all: List[str],
    requires_any: List[str],
    requires_count: List["CountRequirement"],
) -> Callable[[CollectionState], bool]:
    """
    Build a combined access rule lambda from declarative requirements.

    Args:
        player: Player number
        requires_all: Items that ALL must be collected (AND)
        requires_any: Items where at least ONE must be collected (OR)
        requires_count: Items where N copies must be collected

    Returns:
        Lambda that checks the CollectionState
    """
    def rule(state: CollectionState) -> bool:
        # Check AND requirements
        for item_name in requires_all:
            if not state.has(item_name, player):
                return False

        # Check OR requirements
        if requires_any:
            if not any(state.has(item_name, player) for item_name in requires_any):
                return False

        # Check count requirements
        for cr in requires_count:
            if not state.has(cr.item, player, cr.count):
                return False

        return True

    return rule


def has_requirements(
    requires_all: List[str],
    requires_any: List[str],
    requires_count: list,
) -> bool:
    """Check if any requirements are specified."""
    return bool(requires_all or requires_any or requires_count)


def set_rules(world: "APFrameworkWorld") -> None:
    """
    Set access rules for regions and locations based on capabilities config.

    Only applies rules when logic_mode is "basic". When "none", all locations
    remain accessible from the start.
    """
    # Check logic mode
    if world.options.logic_mode.value == 0:  # none
        return

    # Apply region entrance rules
    for region_name, region_data in world.region_table.items():
        if region_name == "Menu":
            continue

        if has_requirements(
            region_data.get("requires_all", []),
            region_data.get("requires_any", []),
            region_data.get("requires_count", []),
        ):
            # Find the entrance to this region
            region = world.multiworld.get_region(region_name, world.player)
            for entrance in region.entrances:
                set_rule(
                    entrance,
                    build_rule(
                        world.player,
                        region_data.get("requires_all", []),
                        region_data.get("requires_any", []),
                        region_data.get("requires_count", []),
                    ),
                )

    # Apply per-location rules
    for loc_name, loc_data in world.location_table.items():
        if has_requirements(loc_data.requires_all, loc_data.requires_any, loc_data.requires_count):
            location = world.multiworld.get_location(loc_name, world.player)
            set_rule(
                location,
                build_rule(
                    world.player,
                    loc_data.requires_all,
                    loc_data.requires_any,
                    loc_data.requires_count,
                ),
            )


def set_completion_rules(world: "APFrameworkWorld") -> None:
    """
    Set the completion condition for the world.

    Looks for a well-known completion location (Victory, Goal, etc.).
    Falls back to requiring the Main region to be reachable.
    """
    completion_location_names = ["Victory", "Goal", "Completion", "Win"]

    for name in completion_location_names:
        if name in world.location_table:
            world.multiworld.completion_condition[world.player] = \
                lambda state, loc_name=name: state.can_reach(loc_name, "Location", world.player)
            return

    # Fallback: completion when Main region is reachable
    world.multiworld.completion_condition[world.player] = \
        lambda state: state.can_reach_region("Main", world.player)
