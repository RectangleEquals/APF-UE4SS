"""
Access rules for the AP Framework World.

Rules are built from logic expression strings parsed by LogicParser.
Logic expressions support:
- (Item: Name)              — has at least 1 of item
- (Item: Name OP N)         — item count satisfies OP (>=, >, <=, <, ==, !=) against N
- (Item: Name OP {key})     — item count satisfies OP against option key's integer value
- (Can Access: Region)      — can reach a region
- (Option: Name)            — boolean option check (resolved at generation time)
- (Option: Name OP Val)     — option comparison (resolved at generation time)
- AND, OR, True, False, grouping with ()

Logic is only applied when logic_mode is "basic". When "none", all locations
are accessible from the start (Sphere 0 behavior).
"""

import difflib
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


def _walk_ast_items_with_option(node):
    """Yield all ItemNode instances in the AST that have a count_option set."""
    if isinstance(node, LogicParser.ItemNode) and node.count_option:
        yield node
    if isinstance(node, (LogicParser.AndNode, LogicParser.OrNode)):
        for child in node.children:
            yield from _walk_ast_items_with_option(child)


def validate_item_count_options(world: "APFrameworkWorld") -> None:
    """Pre-generation validation for {option_key} usage in Item count expressions.

    Called from generate_early() after item_table is built, before create_regions().

    Raises ValueError if:
    - An option key referenced as a count threshold doesn't exist on world.options
    - The option is a Choice or TextChoice (enum indices/strings, not meaningful counts)

    Emits log.warning() (but does NOT block) if:
    - The option is a Toggle (valid values 0/1 but unusual as a count threshold)
    - In goal logic: the option's range_end exceeds the planned item pool count for that item
      (Archipelago's own can_beat_game() will also catch this at fill time with a generic error;
       this warning provides earlier, actionable diagnostics.)

    Note: Region/location gates with item thresholds are not checked for softlocks here —
    Archipelago's fill algorithm detects unreachable regions naturally.
    """
    from Options import Range, Toggle  # Archipelago base option types

    all_logic: list = []  # list of (label: str, logic_str: str, is_goal: bool)
    for rname, rlogic in world.region_table.items():
        if rlogic:
            all_logic.append((f"region '{rname}'", rlogic, False))
    for lname, ldata in world.location_table.items():
        if ldata.logic:
            all_logic.append((f"location '{lname}'", ldata.logic, False))
    for goal in world.capabilities.get("goals", []):
        if goal.get("logic"):
            all_logic.append((f"goal '{goal['name']}'", goal["logic"], True))

    for label, logic_str, is_goal in all_logic:
        try:
            ast = LogicParser.parse(logic_str)
        except ValueError:
            continue  # Parse errors are reported separately
        for inode in _walk_ast_items_with_option(ast):
            key = inode.count_option
            opt_obj = getattr(world.options, key, None)

            if opt_obj is None or not hasattr(opt_obj, "value"):
                raise ValueError(
                    f"In {label}: (Item: {inode.name} {inode.op} {{{key}}}) — "
                    f"unknown option '{key}'. "
                    f"Check that it is declared in your manifest's 'options' array."
                )

            if isinstance(opt_obj, Toggle):
                world.log.warning(
                    f"In {label}: (Item: {inode.name} {inode.op} {{{key}}}) — "
                    f"'{key}' is a Toggle option (values: 0 or 1). "
                    f"The count threshold will be 0 or 1. If intentional, ignore this warning.",
                    "Rules",
                )
            elif not isinstance(opt_obj, Range):
                # Choice, TextChoice, or any other non-numeric type
                raise ValueError(
                    f"In {label}: (Item: {inode.name} {inode.op} {{{key}}}) — "
                    f"option '{key}' is a {type(opt_obj).__name__}, not a Range or Toggle option. "
                    f"Item count thresholds require an option with a numeric integer value. "
                    f"'choice' and 'text_choice' options store enum indices or strings, "
                    f"not meaningful item counts. Use a 'range' option instead."
                )
            else:
                # Range (or NamedRange which extends Range) — check softlock for goals
                if is_goal and inode.op in (">=", ">"):
                    range_end = getattr(opt_obj, "range_end", None)
                    if range_end is not None:
                        item_entry = world.item_table.get(inode.name)
                        pool_count = item_entry.count if item_entry and item_entry.count >= 0 else 0
                        effective = range_end + (1 if inode.op == ">" else 0)
                        if effective > pool_count:
                            world.log.warning(
                                f"In {label}: (Item: {inode.name} {inode.op} {{{key}}}) — "
                                f"option '{key}' range_end ({range_end}) exceeds the planned item "
                                f"pool count for '{inode.name}' ({pool_count}). "
                                f"Players who set '{key}' > {pool_count} will never complete this goal. "
                                f"Archipelago will also report a fill error if this makes the game unbeatable. "
                                f"Reduce range_end to ≤ {pool_count}, or add more '{inode.name}' items.",
                                "Rules",
                            )


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

        ast = LogicParser.parse(region_logic)

        # Warn and replace (Checked:) nodes — only valid in goal logic
        checked_nodes = LogicParser._collect_checked_nodes(ast)
        if checked_nodes:
            names = [n.location for n in checked_nodes]
            log.warning(
                f"'(Checked:)' found in region logic for '{region_name}' — "
                f"this predicate is only valid in goal logic. "
                f"Affected: {names}. Treating as unreachable during fill.",
                "Rules",
            )
            ast = LogicParser._replace_checked_with_false(ast)

        if options:
            ast = LogicParser.evaluate_options(ast, options)
            ast = LogicParser.simplify(ast)

        if isinstance(ast, LogicParser.ConstNode):
            continue  # Always or never accessible — no rule to set

        rule = LogicParser.compile_rule(ast, world.player)
        region = world.multiworld.get_region(region_name, world.player)

        # Register indirect conditions for (Can Access: ...) references
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

        ast = LogicParser.parse(loc_data.logic)

        # Warn and replace (Checked:) nodes — only valid in goal logic
        checked_nodes = LogicParser._collect_checked_nodes(ast)
        if checked_nodes:
            names = [n.location for n in checked_nodes]
            log.warning(
                f"'(Checked:)' found in location logic for '{loc_name}' — "
                f"this predicate is only valid in goal logic. "
                f"Affected: {names}. Treating as unreachable during fill.",
                "Rules",
            )
            ast = LogicParser._replace_checked_with_false(ast)

        if options:
            ast = LogicParser.evaluate_options(ast, options)
            ast = LogicParser.simplify(ast)

        if isinstance(ast, LogicParser.ConstNode):
            continue  # Always or never accessible — no rule to set

        rule = LogicParser.compile_rule(ast, world.player)
        location = world.multiworld.get_location(loc_name, world.player)

        # Register indirect conditions for (Can Access: ...) references
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
    1. Goal system — if goals are defined and the player selected a valid goal name,
       use that goal's logic expression as the completion condition.
    2. If goals are defined but no goal is selected (or the name is unrecognised),
       warn and fall back to all in-logic locations checked (lambda state: True).
    3. If no goals are defined at all, fall back to:
       a. Well-known completion location (Victory, Goal, Completion, Win).
       b. Reaching the Main region.
    """
    log = world.log

    # Check for goal system
    goals = world.capabilities.get("goals", [])
    if goals:
        goal_names = [g["name"] for g in goals]
        available_str = ", ".join(goal_names)

        # Resolve the player's selected goal name
        selected_goal_name = ""
        goal_opt = getattr(world.options, "goal", None)
        if goal_opt is not None and hasattr(goal_opt, "value"):
            val = goal_opt.value
            if isinstance(val, int):
                # Legacy Choice option — resolve index to name
                if 0 <= val < len(goal_names):
                    selected_goal_name = goal_names[val]
            else:
                selected_goal_name = str(val).strip()

        # --- Case 1: No goal specified ---
        if not selected_goal_name:
            log.warn(
                f"Unspecified Goal — Falling back to default of 'all locations checked'. "
                f"Set the 'goal' option in your YAML to choose from: {available_str}",
                "Rules",
            )
            world.multiworld.completion_condition[world.player] = lambda state: True
            return

        # --- Case 2: Exact goal match ---
        for goal in goals:
            if goal["name"] == selected_goal_name:
                logic = goal.get("logic", "")
                combined_logics = goal.get("combined_logics", [])

                # Combine logic from multiple mods contributing to this goal (AND).
                # A "goal_<name>_combinator" option (choices: and/or) can change this,
                # but reading YAML options dynamically is not yet supported; "and" is used.
                if combined_logics:
                    all_logics = [l for l in [logic] + combined_logics if l and l != "True"]
                    if len(all_logics) > 1:
                        logic = "(" + ") AND (".join(all_logics) + ")"
                        log.debug(
                            f"Goal '{selected_goal_name}' has {len(combined_logics)} "
                            f"extra logic contributions — combined with AND: {logic}",
                            "Rules",
                        )
                    elif all_logics:
                        logic = all_logics[0]

                if logic and logic != "True":
                    options = _collect_option_values(world)
                    rule = LogicParser.parse_and_compile(logic, world.player, options)
                    if rule is not None:
                        world.multiworld.completion_condition[world.player] = rule
                        log.info(
                            f"Completion: goal '{selected_goal_name}' with logic: {logic}",
                            "Rules",
                        )
                        return
                # logic is "True" or empty — any state completes
                world.multiworld.completion_condition[world.player] = lambda state: True
                log.info(f"Completion: goal '{selected_goal_name}' (always true)", "Rules")
                return

        # --- Case 3: Goal name specified but not found — fuzzy suggestion ---
        close = difflib.get_close_matches(selected_goal_name, goal_names, n=1, cutoff=0.6)
        hint = f" — Did you mean '{close[0]}'?" if close else ""
        log.warn(
            f"Goal '{selected_goal_name}' not found in declared goals{hint} "
            f"(Falling back to default of 'all locations checked'. "
            f"Available goals: {available_str})",
            "Rules",
        )
        world.multiworld.completion_condition[world.player] = lambda state: True
        return

    # No goals defined at all — fall back to well-known completion locations or Main region.
    completion_location_names = ["Victory", "Goal", "Completion", "Win"]
    for name in completion_location_names:
        if name in world.location_table:
            world.multiworld.completion_condition[world.player] = \
                lambda state, loc_name=name: state.can_reach(loc_name, "Location", world.player)
            log.info(f"Completion: well-known location '{name}'", "Rules")
            return

    world.multiworld.completion_condition[world.player] = \
        lambda state: state.can_reach_region("Main", world.player)
    log.debug("Completion: fallback to Main region reachable", "Rules")