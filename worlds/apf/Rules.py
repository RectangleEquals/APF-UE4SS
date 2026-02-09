"""
Access rules for the AP Framework World.

Rules define what items are required to access locations.
By default, all locations are accessible (no logic).

Game-specific implementations can override these rules.
"""

from typing import TYPE_CHECKING
from BaseClasses import CollectionState

if TYPE_CHECKING:
    from . import APFrameworkWorld


def set_rules(world: "APFrameworkWorld") -> None:
    """
    Set access rules for all locations.

    By default, the AP Framework uses no logic - all locations are accessible
    from the start. This is because the framework doesn't know the game's
    progression requirements.

    Game-specific AP worlds can override this to implement actual logic by:
    1. Subclassing APFrameworkWorld
    2. Overriding set_rules() to add game-specific requirements
    3. Or defining rules in the capabilities config (future feature)

    Example of adding rules in a subclass:
        def set_rules(world):
            from worlds.generic.Rules import set_rule

            # Require an item to access a location
            set_rule(
                world.multiworld.get_location("Boss Room", world.player),
                lambda state: state.has("Boss Key", world.player)
            )
    """
    # Default: no rules (all locations accessible)
    pass


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
