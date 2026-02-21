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
    log = world.log

    if world.options.logic_mode.value == 0:  # none
        log.debug("Logic mode is 'none' — skipping rules", "Rules")
        return

    options = _collect_option_values(world)
    region_rule_count = 0
    location_rule_count = 0

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
        region_rule_count += 1
        log.trace(f"Region rule: {region_name} <- {region_logic}", "Rules")

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
        location_rule_count += 1
        log.trace(f"Location rule: {loc_name} <- {loc_data.logic}", "Rules")

    log.info(
        f"Applied {region_rule_count} region rules, "
        f"{location_rule_count} location rules",
        "Rules",
    )


def set_completion_rules(world: "APFrameworkWorld") -> None:
    """
    Set the completion condition for the world.

    Priority:
    1. Goal system — if goals are defined in capabilities and a goal option exists,
       use the selected goal's logic expression as the completion condition.
    2. Well-known completion location (Victory, Goal, Completion, Win).
    3. Fallback: reaching the Main region.
    """
    log = world.log

    # Check for goal system
    goals = world.capabilities.get("goals", [])
    if goals:
        selected_goal_name = None

        # Check if a goal option was set by the player
        goal_opt = getattr(world.options, "goal", None)
        if goal_opt is not None and hasattr(goal_opt, "value"):
            # The option value might be an int index or a string name
            val = goal_opt.value
            if isinstance(val, int):
                # Choice options store the index — find the matching name
                goal_names = [g["name"] for g in goals]
                if 0 <= val < len(goal_names):
                    selected_goal_name = goal_names[val]
            else:
                selected_goal_name = str(val)
        elif len(goals) == 1:
            # Only one goal — use it directly
            selected_goal_name = goals[0]["name"]

        if selected_goal_name:
            # Find the matching goal's logic
            for goal in goals:
                if goal["name"] == selected_goal_name:
                    logic = goal.get("logic", "")
                    if logic and logic != "True":
                        options = _collect_option_values(world)
                        rule = LogicParser.parse_and_compile(
                            logic, world.player, options)
                        if rule is not None:
                            world.multiworld.completion_condition[world.player] = rule
                            log.info(
                                f"Completion: goal '{selected_goal_name}' "
                                f"with logic: {logic}",
                                "Rules",
                            )
                            return
                    # logic is "True" or empty — any state completes
                    world.multiworld.completion_condition[world.player] = \
                        lambda state: True
                    log.info(
                        f"Completion: goal '{selected_goal_name}' (always true)",
                        "Rules",
                    )
                    return

        log.debug(
            f"{len(goals)} goals defined but none selected — trying fallbacks",
            "Rules",
        )

    # Fallback: well-known completion locations
    completion_location_names = ["Victory", "Goal", "Completion", "Win"]

    for name in completion_location_names:
        if name in world.location_table:
            world.multiworld.completion_condition[world.player] = \
                lambda state, loc_name=name: state.can_reach(
                    loc_name, "Location", world.player)
            log.info(f"Completion: well-known location '{name}'", "Rules")
            return

    # Final fallback: completion when Main region is reachable
    world.multiworld.completion_condition[world.player] = \
        lambda state: state.can_reach_region("Main", world.player)
    log.debug("Completion: fallback to Main region reachable", "Rules")