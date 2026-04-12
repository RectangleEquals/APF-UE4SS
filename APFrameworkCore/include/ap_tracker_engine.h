#pragma once

/**
 * @file ap_tracker_engine.h
 * @brief Tracker engine for computing location accessibility and ecosystem metadata.
 *
 * Singleton that:
 * 1. Initializes after capabilities are finalized — pre-parses all logic
 * 2. Computes TrackerSnapshot/TrackerUpdate on demand
 * 3. Manages subscriber set (mod_ids that want tracker updates)
 * 4. Provides ecosystem metadata for debug UIs
 *
 * Singleton Pattern: Pass-Key + Meyers
 */

#include "ap_exports.h"
#include "ap_logic_evaluator.h"
#include "Types/ap_shared_manifest_types.h"

#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

#include <nlohmann/json.hpp>

namespace ap {

// =============================================================================
// Ecosystem Metadata (static for the session, sent once on subscribe)
// =============================================================================

struct EcosystemMod
{
    std::string mod_id;
    std::string name;
    std::string version;
    int location_count = 0;
    int item_count = 0;
    int region_count = 0;
    int goal_count = 0;
    int override_count = 0;
};

struct ModContribution
{
    std::string mod_id;
    std::string logic;
};

struct EcosystemRegion
{
    std::string name;
    std::string merged_logic;
    std::vector<ModContribution> contributions;
};

struct EcosystemLocation
{
    int64_t location_id = 0;
    std::string name;
    std::string display_region;
    std::string mod_id;
    std::string logic;
};

struct EcosystemItem
{
    int64_t item_id = 0;
    std::string name;
    std::string type;
    std::string original_type;
    std::string mod_id;
    std::string logic;                       // Option-only logic for inclusion

    struct OverrideEntry
    {
        std::string source_mod;
        std::string new_type;
        std::string logic;                   // Option-only logic for this override
        bool applied = false;
    };
    std::vector<OverrideEntry> overrides;
};

// =============================================================================
// Goal Status (changes as items are received)
// =============================================================================

struct GoalStatus
{
    std::string name;        ///< Goal name from manifest (empty in no_goal_mode)
    std::string display;     ///< Human-readable goal display name
    std::string description; ///< Goal description
    float score = 0.0f;      ///< 0.0–1.0 progress toward goal completion
    bool no_goal_mode = false; ///< True = all-locations completion mode
};

// =============================================================================
// Dynamic Results (change on state events)
// =============================================================================

struct TrackerLocationResult
{
    int64_t location_id = 0;
    std::string name;
    std::string display_region;
    float score = 0.0f;
    bool checked = false;
    bool out_of_logic = false; ///< Logic simplified to ConstFalse after option evaluation — location pruned at generation
    ScoredNode scored_tree;
};

struct TrackerRegionResult
{
    std::string name;
    float score = 0.0f;
    bool reachable = false;
    ScoredNode scored_tree;
};

// =============================================================================
// Snapshot and Update Structures
// =============================================================================

struct TrackerUpdate
{
    std::vector<TrackerLocationResult> locations;
    std::vector<TrackerRegionResult> regions;
    std::map<std::string, int> received_items;
    std::set<int64_t> checked_locations;
    GoalStatus goal;

    nlohmann::json to_json() const;
};

struct TrackerSnapshot
{
    // Ecosystem metadata (static for the session)
    std::vector<EcosystemMod> mods;
    std::vector<EcosystemRegion> regions_meta;
    std::vector<EcosystemLocation> locations_meta;
    std::vector<EcosystemItem> items_meta;
    std::map<std::string, std::string> options;

    // Current dynamic state (same shape as TrackerUpdate but full)
    std::vector<TrackerLocationResult> locations;
    std::vector<TrackerRegionResult> regions;
    std::map<std::string, int> received_items;
    std::set<int64_t> checked_locations;
    GoalStatus goal;

    nlohmann::json to_json() const;
};

// =============================================================================
// Tracker Engine Singleton
// =============================================================================

class AP_API APTrackerEngine
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APTrackerEngine;
        explicit ConstructorKey() = default;
    };

    explicit APTrackerEngine(ConstructorKey);
    ~APTrackerEngine();

    APTrackerEngine(const APTrackerEngine &) = delete;
    APTrackerEngine &operator=(const APTrackerEngine &) = delete;
    APTrackerEngine(APTrackerEngine &&) = delete;
    APTrackerEngine &operator=(APTrackerEngine &&) = delete;

    static APTrackerEngine *get();

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * @brief Initialize the tracker engine after capabilities are finalized.
     *
     * Pre-parses all logic strings, evaluates/simplifies options, builds
     * ecosystem metadata. Must be called after APCapabilities::assign_ids()
     * and after receiving slot_data with option_values.
     */
    void initialize(const std::map<std::string, std::string> &option_values);

    /**
     * @brief Check if the tracker engine has been initialized.
     */
    bool is_initialized() const;

    /**
     * @brief Return the goal selected for this session, or nullopt if no goals are defined.
     */
    std::optional<GoalDef> get_active_goal() const;

    /**
     * @brief True when no specific goal is active — completion = all in-logic locations checked.
     */
    bool is_no_goal_mode() const;

    /**
     * @brief Describes why no_goal_mode_ is active (e.g. "no goals declared in manifest",
     *        "no goal specified in YAML", "goal 'X' unrecognized"). Empty when a goal is active.
     */
    const std::string& get_no_goal_label() const;

    /**
     * @brief Returns the set of location IDs whose logic simplified to ConstFalse (pruned at generation).
     */
    std::unordered_set<int64_t> get_out_of_logic_location_ids() const;

    /**
     * @brief Returns a pointer to the pre-parsed, fully resolved goal logic AST.
     *
     * The returned node was built at initialize() time with real option_values — NOT an empty map.
     * Using this avoids the empty-options bug in ap_message_router.cpp where goal logic was
     * re-parsed with evaluate_options(node, {}), leaving {option_key} Item thresholds unresolved.
     *
     * Returns nullptr if the tracker has not been initialized or no goal is active.
     * The pointer is valid for the lifetime of this APTrackerEngine instance.
     */
    const LogicNode *get_goal_logic_node() const;

    // =========================================================================
    // Computation
    // =========================================================================

    /**
     * @brief Compute full snapshot (ecosystem metadata + current state).
     *
     * Used when a new subscriber joins — sends all data at once.
     */
    TrackerSnapshot compute_snapshot();

    /**
     * @brief Compute update (dynamic state only).
     *
     * Used after item_received/location_checked to send deltas.
     */
    TrackerUpdate compute_update();

    // =========================================================================
    // Subscriber Management
    // =========================================================================

    void add_subscriber(const std::string &mod_id);
    void remove_subscriber(const std::string &mod_id);
    bool has_subscribers() const;
    std::set<std::string> get_subscribers() const;

  private:
    // =========================================================================
    // Internal Helpers
    // =========================================================================

    /// Build TrackerState from APStateManager + item name mappings
    TrackerState build_tracker_state() const;

    /// Compute location and region results from current state
    void compute_results(const TrackerState &state,
                         std::vector<TrackerLocationResult> &loc_results,
                         std::vector<TrackerRegionResult> &reg_results,
                         TrackerState *out_full_state = nullptr) const;

    /// Compute goal status from current full state and already-computed location results
    GoalStatus compute_goal_status(const TrackerState &full_state,
                                   const std::vector<TrackerLocationResult> &loc_results) const;

    /// Build ecosystem metadata from APCapabilities/APModRegistry
    void build_ecosystem_metadata();

    // =========================================================================
    // Private Member Variables
    // =========================================================================

    bool initialized_ = false;

    // Goal tracking
    std::optional<GoalDef> active_goal_; ///< Selected goal for this session (nullopt = no goals defined)
    bool no_goal_mode_ = false;           ///< True when no goals — completion = all in-logic locations checked
    std::string no_goal_label_;           ///< Describes why no_goal_mode_ is active (for log messages)
    LogicNode goal_logic_node_;           ///< Pre-parsed goal logic (valid when active_goal_ is set)

    // Pre-parsed location logic (index matches locations_meta_)
    struct ParsedLocation
    {
        int64_t location_id = 0;
        std::string name;
        std::string display_region;
        LogicNode logic;
        bool out_of_logic = false; ///< Logic simplified to ConstFalse — location pruned at generation
    };
    std::vector<ParsedLocation> parsed_locations_;

    // Pre-parsed region logic
    std::vector<RegionInfo> parsed_regions_;

    // Item ID -> item name mapping (for converting progression counts to names)
    std::map<int64_t, std::string> item_id_to_name_;

    // Location ID -> location name mapping (for populating checked_locations in TrackerState)
    std::map<int64_t, std::string> location_id_to_name_;

    // Ecosystem metadata (built once at init)
    std::vector<EcosystemMod> ecosystem_mods_;
    std::vector<EcosystemRegion> ecosystem_regions_;
    std::vector<EcosystemLocation> ecosystem_locations_;
    std::vector<EcosystemItem> ecosystem_items_;
    std::map<std::string, std::string> option_values_;

    // Subscribers
    mutable std::mutex subscriber_mutex_;
    std::set<std::string> subscribers_;
};

} // namespace ap
