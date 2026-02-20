"""
Access rules for the AP Framework World.

Rules are built from logic expression strings parsed by LogicParser.
Logic expressions support:
- (Item: Name)          — has at least 1 of item
- (Item: Name : N)      — has at least N of item
- (Can Access: Region)  — can reach a region
- (Option: Name)        — boolean option check (resolved at generation time)
- (Option: Name OP Val) — option comparison (resolved at generation time)
- AND, OR, True, False, grouping with ()

Logic is only applied when logic_mode is "basic". When "none", all locations
are accessible from the start (Sphere 0 behavior).
"""

from typing import TYPE_CHECKING, Dict, Any
from worlds.generic.Rules import set_rule

from . import LogicParser

if TYPE_CHECKING:
    from . import APFrameworkWorld


def _collect_option_values(world: "APFrameworkWorld") -> Dict[str, Any]:
    """Collect all option values into a dict for logic evaluation."""
    options_dict: Dict[str, Any] = {}
    for attr_name in dir(world.options):
        if attr_name.startswith('_'):
            continue
        opt = getattr(world.options, attr_name, None)
        if opt is not None and hasattr(opt, 'value'):
            options_dict[attr_name] = opt.value
    return options_dict


def set_rules(world: "APFrameworkWorld") -> None:
    """
    Set access rules for regions and locations based on logic expressions.

    Only applies rules when logic_mode is "basic". When "none", all locations
    remain accessible from the start.
    """
    if world.options.logic_mode.value == 0:  # none
        return

    options = _collect_option_values(world)

    # Apply region entrance rules
    for region_name, region_logic in world.region_table.items():
        if region_name == "Menu" or not region_logic:
            continue

        rule = LogicParser.parse_and_compile(region_logic, world.player, options)
        if rule is None:
            continue  # Always accessible, no rule needed

        region = world.multiworld.get_region(region_name, world.player)

        # Register indirect conditions for (Can Access: ...) references
        ast = LogicParser.parse(region_logic)
        if options:
            ast = LogicParser.evaluate_options(ast, options)
            ast = LogicParser.simplify(ast)
        for ref_name in LogicParser.extract_region_refs(ast):
            try:
                ref_region = world.multiworld.get_region(ref_name, world.player)
                for entrance in region.entrances:
                    world.multiworld.register_indirect_condition(ref_region, entrance)
            except KeyError:
                pass  # Referenced region doesn't exist — caught by AP validation

        for entrance in region.entrances:
            set_rule(entrance, rule)

    # Apply per-location rules
    for loc_name, loc_data in world.location_table.items():
        if not loc_data.logic:
            continue

        rule = LogicParser.parse_and_compile(loc_data.logic, world.player, options)
        if rule is None:
            continue  # Always accessible

        location = world.multiworld.get_location(loc_name, world.player)

        # Register indirect conditions for (Can Access: ...) references
        ast = LogicParser.parse(loc_data.logic)
        if options:
            ast = LogicParser.evaluate_options(ast, options)
            ast = LogicParser.simplify(ast)
        for ref_name in LogicParser.extract_region_refs(ast):
            try:
                ref_region = world.multiworld.get_region(ref_name, world.player)
                for entrance in location.parent_region.entrances:
                    world.multiworld.register_indirect_condition(ref_region, entrance)
            except KeyError:
                pass

        set_rule(location, rule)


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