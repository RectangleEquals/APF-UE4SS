#pragma once

/**
 * @file ap_logic_evaluator.h
 * @brief Logic expression parser and evaluator for the tracker system.
 *
 * Ports the Python LogicParser (worlds/apf/LogicParser.py) to C++.
 * Lives in APShared so both APFrameworkCore and APClientLib can use it.
 *
 * Grammar:
 *     expression := and_expr ('OR' and_expr)*
 *     and_expr   := primary ('AND' primary)*
 *     primary    := '(' expression ')'
 *                 | '(Item:' NAME ')'
 *                 | '(Item:' NAME ':' INT ')'
 *                 | '(Can Access:' NAME ')'
 *                 | '(Option:' NAME ')'
 *                 | '(Option:' NAME OP VALUE ')'
 *                 | 'True' | 'False'
 *
 * Evaluation modes:
 * - Boolean: returns true/false (is this fully accessible?)
 * - Scored:  returns ScoredNode tree with 0.0-1.0 score at every node
 *            for per-expression UI coloring (green/yellow/red)
 */

#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace ap {

// =============================================================================
// AST Node Types
// =============================================================================

enum class LogicNodeType
{
    Const,     ///< True or False literal
    Item,      ///< (Item: Name) or (Item: Name : Count)
    CanAccess, ///< (Can Access: Region)
    Option,    ///< (Option: Name) or (Option: Name OP Value)
    And,       ///< All children must be satisfied
    Or         ///< At least one child must be satisfied
};

/**
 * @brief AST node for logic expressions.
 *
 * Tagged struct — `type` determines which fields are active.
 * And/Or nodes have children; leaf nodes have specific fields.
 */
struct LogicNode
{
    LogicNodeType type = LogicNodeType::Const;

    // Const
    bool const_value = false;

    // Item
    std::string item_name;
    int item_count = 1;

    // CanAccess
    std::string region;

    // Option
    std::string option_name;
    std::string option_op;    ///< "", ">=", "<=", ">", "<", "==", "!="
    std::string option_value;

    // And/Or
    std::vector<LogicNode> children;

    // -- Factory helpers --
    static LogicNode make_const(bool value);
    static LogicNode make_item(const std::string &name, int count = 1);
    static LogicNode make_can_access(const std::string &region);
    static LogicNode make_option(const std::string &name, const std::string &op = "",
                                 const std::string &value = "");
    static LogicNode make_and(std::vector<LogicNode> children);
    static LogicNode make_or(std::vector<LogicNode> children);
};

// =============================================================================
// Parser
// =============================================================================

/**
 * @brief Parse a logic expression string into an AST.
 *
 * Empty/whitespace strings return Const(true) — always accessible.
 * Throws std::runtime_error on parse failure.
 */
LogicNode parse_logic(const std::string &logic);

// =============================================================================
// Option Evaluation (resolve Option nodes to Const)
// =============================================================================

/**
 * @brief Replace OptionNodes with ConstNodes based on option values.
 *
 * @param node AST to transform.
 * @param options Map of option name to string value.
 * @return New AST with all OptionNodes resolved to Const(true/false).
 *
 * Unknown options default to true (permissive).
 * Mirrors LogicParser.py evaluate_options().
 */
LogicNode evaluate_options(const LogicNode &node, const std::map<std::string, std::string> &options);

// =============================================================================
// Simplification (constant folding)
// =============================================================================

/**
 * @brief Fold constants in the AST after option evaluation.
 *
 * - AND with any False child -> False
 * - AND: remove True children; empty -> True; single child -> unwrap
 * - OR  with any True child  -> True
 * - OR:  remove False children; empty -> False; single child -> unwrap
 *
 * Mirrors LogicParser.py simplify().
 */
LogicNode simplify(const LogicNode &node);

// =============================================================================
// Tracker State (input for evaluation)
// =============================================================================

/**
 * @brief Runtime state used for logic evaluation.
 *
 * Built from APStateManager data at evaluation time.
 */
struct TrackerState
{
    std::map<std::string, int> received_items;  ///< item_name -> count
    std::set<std::string> reachable_regions;
};

// =============================================================================
// Scored Node (output of evaluation)
// =============================================================================

/**
 * @brief A scored AST node — mirrors LogicNode shape with scores at every level.
 *
 * The UI walks this tree to color each sub-expression independently:
 * - score == 1.0: GREEN  (fully satisfied)
 * - 0 < score < 1.0: YELLOW (partially satisfied)
 * - score == 0.0: RED (not satisfied)
 */
struct ScoredNode
{
    LogicNodeType type;
    float score = 0.0f;
    std::string display;                ///< Human-readable text for this node
    std::vector<ScoredNode> children;   ///< For And/Or nodes
};

// =============================================================================
// Evaluation
// =============================================================================

/**
 * @brief Build a scored AST tree for a logic expression.
 *
 * Each node gets its own score:
 * - ItemNode:      min(received / required, 1.0)
 * - CanAccessNode: reachable ? 1.0 : 0.0
 * - ConstNode:     true -> 1.0, false -> 0.0
 * - AndNode:       average of children scores; children individually scored
 * - OrNode:        max of children scores; children individually scored
 */
ScoredNode evaluate_scored(const LogicNode &node, const TrackerState &state);

/**
 * @brief Get just the top-level score (convenience for sorting/filtering).
 */
float evaluate_score(const LogicNode &node, const TrackerState &state);

/**
 * @brief Check if logic is fully satisfied (score == 1.0).
 */
bool evaluate_bool(const LogicNode &node, const TrackerState &state);

// =============================================================================
// Region Graph
// =============================================================================

/**
 * @brief Region with pre-parsed access logic.
 */
struct RegionInfo
{
    std::string name;
    LogicNode access_logic;
};

/**
 * @brief Compute reachable regions using fixed-point iteration.
 *
 * Algorithm:
 * 1. Start with {"Menu"} + any regions without logic (always reachable)
 * 2. For each unreachable region, evaluate its logic with current state
 * 3. If newly reachable, add to set, mark changed
 * 4. Repeat until no changes (fixed-point convergence)
 *
 * @param regions All regions with their access logic.
 * @param state   Current tracker state (items + initial reachable set).
 * @return Set of all reachable region names.
 */
std::set<std::string> compute_reachable_regions(
    const std::vector<RegionInfo> &regions,
    const TrackerState &state);

// =============================================================================
// Display String Generation
// =============================================================================

/**
 * @brief Generate a human-readable display string for a LogicNode.
 *
 * Used to populate ScoredNode::display.
 */
std::string logic_node_to_display(const LogicNode &node);

} // namespace ap
