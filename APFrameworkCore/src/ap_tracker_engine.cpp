#include "ap_tracker_engine.h"
#include "ap_capabilities.h"
#include "ap_logger.h"
#include "ap_mod_registry.h"
#include "ap_state_manager.h"

#include <algorithm>
#include <chrono>
#include <vector>

namespace ap {

// =============================================================================
// JSON Serialization Helpers
// =============================================================================

namespace {

nlohmann::json scored_node_to_json(const ScoredNode &node)
{
    nlohmann::json j;

    // Map type enum to string
    switch (node.type)
    {
    case LogicNodeType::Const:
        j["type"] = "const";
        break;
    case LogicNodeType::Item:
        j["type"] = "item";
        break;
    case LogicNodeType::CanAccess:
        j["type"] = "can_access";
        break;
    case LogicNodeType::Option:
        j["type"] = "option";
        break;
    case LogicNodeType::Checked:
        j["type"] = "checked";
        break;
    case LogicNodeType::And:
        j["type"] = "and";
        break;
    case LogicNodeType::Or:
        j["type"] = "or";
        break;
    }

    j["score"] = node.score;
    j["display"] = node.display;

    if (!node.children.empty())
    {
        nlohmann::json children = nlohmann::json::array();
        for (const auto &child : node.children)
        {
            children.push_back(scored_node_to_json(child));
        }
        j["children"] = children;
    }
    else
    {
        j["children"] = nlohmann::json::array();
    }

    return j;
}

} // anonymous namespace

nlohmann::json TrackerUpdate::to_json() const
{
    nlohmann::json j;

    // Locations
    nlohmann::json locs = nlohmann::json::array();
    for (const auto &loc : locations)
    {
        nlohmann::json l;
        l["id"] = loc.location_id;
        l["name"] = loc.name;
        l["display_region"] = loc.display_region;
        l["score"] = loc.score;
        l["checked"] = loc.checked;
        l["out_of_logic"] = loc.out_of_logic;
        l["scored_tree"] = scored_node_to_json(loc.scored_tree);
        locs.push_back(l);
    }
    j["locations"] = locs;

    // Regions
    nlohmann::json regs = nlohmann::json::array();
    for (const auto &reg : regions)
    {
        nlohmann::json r;
        r["name"] = reg.name;
        r["score"] = reg.score;
        r["reachable"] = reg.reachable;
        r["scored_tree"] = scored_node_to_json(reg.scored_tree);
        regs.push_back(r);
    }
    j["regions"] = regs;

    // Received items
    j["received_items"] = received_items;

    // Checked locations
    nlohmann::json checked = nlohmann::json::array();
    for (int64_t id : checked_locations)
    {
        checked.push_back(id);
    }
    j["checked_locations"] = checked;

    // Goal status
    j["goal"] = {{"name",         goal.name},
                 {"display",      goal.display},
                 {"description",  goal.description},
                 {"score",        goal.score},
                 {"no_goal_mode", goal.no_goal_mode}};

    return j;
}

nlohmann::json TrackerSnapshot::to_json() const
{
    nlohmann::json j;

    // --- Ecosystem metadata ---

    // Mods
    nlohmann::json mods_arr = nlohmann::json::array();
    for (const auto &mod : mods)
    {
        mods_arr.push_back({{"mod_id", mod.mod_id},
                            {"name", mod.name},
                            {"version", mod.version},
                            {"location_count", mod.location_count},
                            {"item_count", mod.item_count},
                            {"region_count", mod.region_count},
                            {"goal_count", mod.goal_count},
                            {"override_count", mod.override_count}});
    }
    j["mods"] = mods_arr;

    // Regions metadata
    nlohmann::json regs_meta = nlohmann::json::array();
    for (const auto &reg : regions_meta)
    {
        nlohmann::json contribs = nlohmann::json::array();
        for (const auto &c : reg.contributions)
        {
            contribs.push_back({{"mod_id", c.mod_id}, {"logic", c.logic}});
        }
        regs_meta.push_back(
            {{"name", reg.name}, {"merged_logic", reg.merged_logic}, {"contributions", contribs}});
    }
    j["regions_meta"] = regs_meta;

    // Locations metadata
    nlohmann::json locs_meta = nlohmann::json::array();
    for (const auto &loc : locations_meta)
    {
        locs_meta.push_back({{"id", loc.location_id},
                             {"name", loc.name},
                             {"display_region", loc.display_region},
                             {"mod_id", loc.mod_id},
                             {"logic", loc.logic}});
    }
    j["locations_meta"] = locs_meta;

    // Items metadata
    nlohmann::json items_meta_arr = nlohmann::json::array();
    for (const auto &item : items_meta)
    {
        nlohmann::json overrides = nlohmann::json::array();
        for (const auto &ovr : item.overrides)
        {
            overrides.push_back({{"source_mod", ovr.source_mod},
                                 {"new_type", ovr.new_type},
                                 {"logic", ovr.logic},
                                 {"applied", ovr.applied}});
        }
        items_meta_arr.push_back({{"id", item.item_id},
                                  {"name", item.name},
                                  {"type", item.type},
                                  {"original_type", item.original_type},
                                  {"mod_id", item.mod_id},
                                  {"logic", item.logic},
                                  {"overrides", overrides}});
    }
    j["items_meta"] = items_meta_arr;

    // Options
    j["options"] = options;

    // --- Dynamic state (same as TrackerUpdate) ---
    nlohmann::json locs = nlohmann::json::array();
    for (const auto &loc : locations)
    {
        nlohmann::json l;
        l["id"] = loc.location_id;
        l["name"] = loc.name;
        l["display_region"] = loc.display_region;
        l["score"] = loc.score;
        l["checked"] = loc.checked;
        l["out_of_logic"] = loc.out_of_logic;
        l["scored_tree"] = scored_node_to_json(loc.scored_tree);
        locs.push_back(l);
    }
    j["locations"] = locs;

    nlohmann::json regs = nlohmann::json::array();
    for (const auto &reg : regions)
    {
        nlohmann::json r;
        r["name"] = reg.name;
        r["score"] = reg.score;
        r["reachable"] = reg.reachable;
        r["scored_tree"] = scored_node_to_json(reg.scored_tree);
        regs.push_back(r);
    }
    j["regions"] = regs;

    j["received_items"] = received_items;

    nlohmann::json checked = nlohmann::json::array();
    for (int64_t id : checked_locations)
    {
        checked.push_back(id);
    }
    j["checked_locations"] = checked;

    // Goal status
    j["goal"] = {{"name",         goal.name},
                 {"display",      goal.display},
                 {"description",  goal.description},
                 {"score",        goal.score},
                 {"no_goal_mode", goal.no_goal_mode}};

    return j;
}

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APTrackerEngine *APTrackerEngine::get()
{
    static std::unique_ptr<APTrackerEngine> instance =
        std::make_unique<APTrackerEngine>(ConstructorKey{});
    return instance.get();
}

APTrackerEngine::APTrackerEngine(ConstructorKey)
{
}

APTrackerEngine::~APTrackerEngine() = default;

// =============================================================================
// Initialization Helpers
// =============================================================================

namespace {

/// Derive a display region name for grouping in the tracker UI.
/// Scans the logic string for the first "(Can Access: R)" pattern — returns R.
/// Falls back to the prefix before ": " in the location name, then "Main".
std::string derive_display_region(const std::string &logic, const std::string &name)
{
    static const std::string prefix = "(Can Access: ";
    size_t pos = logic.find(prefix);
    if (pos != std::string::npos)
    {
        size_t start = pos + prefix.size();
        size_t end = logic.find(')', start);
        if (end != std::string::npos)
            return logic.substr(start, end - start);
    }
    // Fallback: prefix before ": " in name (e.g. "Tech: Workbench" → "Tech")
    size_t colon = name.find(": ");
    if (colon != std::string::npos)
        return name.substr(0, colon);
    return "Main";
}

} // anonymous namespace

// =============================================================================
// Goal Helpers
// =============================================================================

// Returns the closest matching goal name within edit distance ≤ 3, or "" if none.
static std::string fuzzy_goal_suggestion(
    const std::string &query,
    const std::vector<GoalDef> &goals)
{
    // Simple Levenshtein distance (DP, O(m*n))
    auto lev = [](const std::string &a, const std::string &b) -> int {
        int m = static_cast<int>(a.size());
        int n = static_cast<int>(b.size());
        std::vector<std::vector<int>> dp(m + 1, std::vector<int>(n + 1));
        for (int i = 0; i <= m; ++i) dp[i][0] = i;
        for (int j = 0; j <= n; ++j) dp[0][j] = j;
        for (int i = 1; i <= m; ++i)
            for (int j = 1; j <= n; ++j)
                dp[i][j] = std::min({dp[i-1][j] + 1,
                                     dp[i][j-1] + 1,
                                     dp[i-1][j-1] + (a[i-1] != b[j-1] ? 1 : 0)});
        return dp[m][n];
    };

    std::string best;
    int best_dist = 4; // only suggest if within 3 edits
    for (const auto &g : goals)
    {
        int d = lev(query, g.name);
        if (d < best_dist)
        {
            best_dist = d;
            best = g.name;
        }
    }
    return best;
}

// =============================================================================
// Initialization
// =============================================================================

void APTrackerEngine::initialize(const std::map<std::string, std::string> &option_values)
{
    option_values_ = option_values;

    APLogger::get()->log(LogLevel::Info, "APTrackerEngine",
                         "Initializing with " + std::to_string(option_values.size()) + " option values");

    // Build item ID -> name mapping from capabilities
    item_id_to_name_.clear();
    auto all_items = APCapabilities::get()->get_all_items();
    for (const auto &item : all_items)
    {
        item_id_to_name_[item.item_id] = item.item_name;
    }

    // Build location ID -> name mapping (needed to populate checked_locations in TrackerState)
    location_id_to_name_.clear();

    // Pre-parse location logic
    parsed_locations_.clear();
    auto all_locations = APCapabilities::get()->get_all_locations();
    for (const auto &loc : all_locations)
    {
        ParsedLocation parsed;
        parsed.location_id = loc.location_id;
        parsed.name = loc.location_name;
        parsed.display_region = derive_display_region(loc.logic, loc.location_name);

        try
        {
            auto ast = parse_logic(loc.logic);
            ast = evaluate_options(ast, option_values);
            ast = simplify(ast);
            parsed.out_of_logic = (ast.type == LogicNodeType::Const && !ast.const_value);
            parsed.logic = std::move(ast);
        }
        catch (const std::exception &e)
        {
            APLogger::get()->log(LogLevel::Warn, "APTrackerEngine",
                                 "Failed to parse location logic for '" + loc.location_name +
                                     "': " + e.what());
            parsed.logic = LogicNode::make_const(true);
        }

        location_id_to_name_[parsed.location_id] = parsed.name;
        parsed_locations_.push_back(std::move(parsed));
    }

    // Log out-of-logic count
    {
        int ool_count = 0;
        for (const auto &p : parsed_locations_)
            if (p.out_of_logic) ++ool_count;
        if (ool_count > 0)
            APLogger::get()->log(LogLevel::Info, "APTrackerEngine",
                                 std::to_string(ool_count) +
                                     " out-of-logic location(s) excluded from this multiworld "
                                     "(option-pruned at generation; shown in tracker as unavailable)");
    }

    // Resolve active goal
    auto goals = APCapabilities::get()->get_goals();
    if (goals.empty())
    {
        no_goal_mode_ = true;
        no_goal_label_ = "no goals declared in manifest";
        APLogger::get()->log(LogLevel::Info, "APTrackerEngine",
                             "No goals defined — completion mode: all in-logic locations checked");
    }
    else
    {
        // Build comma-separated list of available goal names for diagnostic messages
        std::string available_goals;
        for (const auto &g : goals)
            available_goals += (available_goals.empty() ? "" : ", ") + g.name;

        std::string selected_name;
        auto it = option_values.find("goal");
        if (it != option_values.end())
            selected_name = it->second;

        if (selected_name.empty())
        {
            // No goal specified — warn and use all-locations-checked default
            no_goal_mode_ = true;
            no_goal_label_ = "no goal specified in YAML";
            APLogger::get()->log(LogLevel::Warn, "APTrackerEngine",
                                 "No goal specified — falling back to default of "
                                 "'all in-logic locations checked'. "
                                 "Set the 'goal' option in your YAML to choose from: "
                                 + available_goals);
        }
        else
        {
            // Search for exact match
            for (const auto &g : goals)
            {
                if (g.name == selected_name)
                {
                    active_goal_ = g;
                    break;
                }
            }

            if (active_goal_.has_value())
            {
                no_goal_mode_ = false;
                APLogger::get()->log(LogLevel::Info, "APTrackerEngine",
                                     "Active goal: '" + active_goal_->name
                                     + "' — " + active_goal_->display);
            }
            else
            {
                // Goal name not found — fuzzy suggestion + all-locations-checked default
                std::string suggestion = fuzzy_goal_suggestion(selected_name, goals);
                std::string hint = suggestion.empty()
                    ? ""
                    : " — Did you mean '" + suggestion + "'?";
                no_goal_mode_ = true;
                no_goal_label_ = "goal '" + selected_name + "' unrecognized";
                APLogger::get()->log(LogLevel::Warn, "APTrackerEngine",
                                     "Goal '" + selected_name + "' not found in declared goals"
                                     + hint + ". Falling back to default of "
                                     "'all in-logic locations checked'. "
                                     "(Available goals: " + available_goals + ")");
            }
        }
    }

    // Pre-parse goal logic node for scored evaluation on each tracker tick
    goal_logic_node_ = LogicNode::make_const(false);
    if (active_goal_.has_value() && !active_goal_->logic.empty())
    {
        try
        {
            auto ast = parse_logic(active_goal_->logic);
            ast = evaluate_options(ast, option_values);
            ast = simplify(ast);
            goal_logic_node_ = std::move(ast);
        }
        catch (const std::exception &e)
        {
            APLogger::get()->log(LogLevel::Warn, "APTrackerEngine",
                                 "Failed to parse goal logic: " + std::string(e.what()));
        }
    }

    // Pre-parse region logic
    parsed_regions_.clear();
    auto all_regions = APCapabilities::get()->get_regions();
    for (const auto &reg : all_regions)
    {
        RegionInfo info;
        info.name = reg.name;

        try
        {
            auto ast = parse_logic(reg.logic);
            ast = evaluate_options(ast, option_values);
            ast = simplify(ast);
            info.access_logic = std::move(ast);
        }
        catch (const std::exception &e)
        {
            APLogger::get()->log(LogLevel::Warn, "APTrackerEngine",
                                 "Failed to parse region logic for '" + reg.name +
                                     "': " + e.what());
            info.access_logic = LogicNode::make_const(true);
        }

        parsed_regions_.push_back(std::move(info));
    }

    // Build ecosystem metadata
    build_ecosystem_metadata();

    initialized_ = true;

    APLogger::get()->log(LogLevel::Info, "APTrackerEngine",
                         "Initialized: " + std::to_string(parsed_locations_.size()) +
                             " locations, " + std::to_string(parsed_regions_.size()) + " regions");
}

bool APTrackerEngine::is_initialized() const
{
    return initialized_;
}

// =============================================================================
// Computation
// =============================================================================

TrackerState APTrackerEngine::build_tracker_state() const
{
    TrackerState state;

    // Convert item progression counts (id->count) to (name->count)
    auto counts = APStateManager::get()->get_all_item_progression_counts();
    for (const auto &[id, count] : counts)
    {
        auto it = item_id_to_name_.find(id);
        if (it != item_id_to_name_.end())
        {
            state.received_items[it->second] = count;
        }
    }

    // Convert checked location IDs to names (for (Checked: X) predicate in goal logic)
    auto checked_ids = APStateManager::get()->get_checked_locations();
    for (int64_t id : checked_ids)
    {
        auto it = location_id_to_name_.find(id);
        if (it != location_id_to_name_.end())
            state.checked_locations.insert(it->second);
    }

    return state;
}

void APTrackerEngine::compute_results(
    const TrackerState &state,
    std::vector<TrackerLocationResult> &loc_results,
    std::vector<TrackerRegionResult> &reg_results,
    TrackerState *out_full_state) const
{
    auto snap_start = std::chrono::steady_clock::now();
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "compute_results: " + std::to_string(parsed_regions_.size()) +
                             " regions, " + std::to_string(parsed_locations_.size()) + " locations");

    // First compute region reachability
    auto t0 = std::chrono::steady_clock::now();
    auto reachable = compute_reachable_regions(parsed_regions_, state);
    auto t1 = std::chrono::steady_clock::now();
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Reachability done: " + std::to_string(reachable.size()) + "/" +
                             std::to_string(parsed_regions_.size()) + " reachable in " +
                             std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count()) +
                             "ms");

    // Build full state with reachable regions
    TrackerState full_state = state;
    full_state.reachable_regions = reachable;

    if (out_full_state)
        *out_full_state = full_state;

    // Compute region results (with scored trees)
    reg_results.clear();
    for (const auto &region : parsed_regions_)
    {
        TrackerRegionResult result;
        result.name = region.name;
        result.reachable = reachable.count(region.name) > 0;
        result.scored_tree = evaluate_scored(region.access_logic, full_state);
        result.score = result.scored_tree.score;
        reg_results.push_back(std::move(result));
    }

    auto t2 = std::chrono::steady_clock::now();
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Region scoring done in " +
                             std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(t2 - t1).count()) +
                             "ms");

    // Compute location results
    auto checked = APStateManager::get()->get_checked_locations();

    loc_results.clear();
    int loc_done = 0;
    int loc_total = static_cast<int>(parsed_locations_.size());
    auto last_log = std::chrono::steady_clock::now();

    for (const auto &loc : parsed_locations_)
    {
        TrackerLocationResult result;
        result.location_id = loc.location_id;
        result.name = loc.name;
        result.display_region = loc.display_region;
        result.checked = checked.count(loc.location_id) > 0;
        result.out_of_logic = loc.out_of_logic;
        result.scored_tree = evaluate_scored(loc.logic, full_state);
        result.score = result.scored_tree.score;
        loc_results.push_back(std::move(result));

        loc_done++;
        auto now_t = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now_t - last_log).count() >= 1)
        {
            last_log = now_t;
            auto elapsed_ms =
                std::chrono::duration_cast<std::chrono::milliseconds>(now_t - t2).count();
            int pct = loc_total > 0 ? static_cast<int>(100.0 * loc_done / loc_total) : 0;
            double rate = elapsed_ms > 0 ? (loc_done * 1000.0 / elapsed_ms) : 0.0;
            int eta_s = (rate > 0.0 && loc_done < loc_total)
                            ? static_cast<int>((loc_total - loc_done) / rate)
                            : 0;
            APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                                 "Location scoring: " + std::to_string(loc_done) + "/" +
                                     std::to_string(loc_total) + " (" + std::to_string(pct) +
                                     "%) rate=" + std::to_string(static_cast<int>(rate)) +
                                     "/s ETA=" + std::to_string(eta_s) + "s");
        }
    }

    auto t3 = std::chrono::steady_clock::now();
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Location scoring done: " + std::to_string(loc_done) + " in " +
                             std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(t3 - t2).count()) +
                             "ms (total: " +
                             std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(t3 - snap_start).count()) +
                             "ms)");
}

TrackerSnapshot APTrackerEngine::compute_snapshot()
{
    TrackerSnapshot snapshot;

    // Ecosystem metadata
    snapshot.mods = ecosystem_mods_;
    snapshot.regions_meta = ecosystem_regions_;
    snapshot.locations_meta = ecosystem_locations_;
    snapshot.items_meta = ecosystem_items_;
    snapshot.options = option_values_;

    // Dynamic state
    auto state = build_tracker_state();
    TrackerState full_state;
    compute_results(state, snapshot.locations, snapshot.regions, &full_state);
    snapshot.received_items = state.received_items;
    snapshot.checked_locations = APStateManager::get()->get_checked_locations();
    snapshot.goal = compute_goal_status(full_state, snapshot.locations);

    return snapshot;
}

TrackerUpdate APTrackerEngine::compute_update()
{
    TrackerUpdate update;

    auto state = build_tracker_state();
    TrackerState full_state;
    compute_results(state, update.locations, update.regions, &full_state);
    update.received_items = state.received_items;
    update.checked_locations = APStateManager::get()->get_checked_locations();
    update.goal = compute_goal_status(full_state, update.locations);

    return update;
}

GoalStatus APTrackerEngine::compute_goal_status(
    const TrackerState &full_state,
    const std::vector<TrackerLocationResult> &loc_results) const
{
    GoalStatus gs;
    gs.no_goal_mode = no_goal_mode_;

    if (no_goal_mode_)
    {
        // Score = fraction of in-logic locations that have been checked
        int total = 0, checked_count = 0;
        for (const auto &loc : loc_results)
        {
            if (!loc.out_of_logic)
            {
                ++total;
                if (loc.checked) ++checked_count;
            }
        }
        gs.score = (total > 0) ? static_cast<float>(checked_count) / static_cast<float>(total)
                               : 1.0f;
    }
    else if (active_goal_.has_value())
    {
        gs.name = active_goal_->name;
        gs.display = active_goal_->display;
        gs.description = active_goal_->description;
        gs.score = evaluate_scored(goal_logic_node_, full_state).score;
    }

    return gs;
}

// =============================================================================
// Subscriber Management
// =============================================================================

void APTrackerEngine::add_subscriber(const std::string &mod_id)
{
    std::lock_guard<std::mutex> lock(subscriber_mutex_);
    subscribers_.insert(mod_id);
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Subscriber added: " + mod_id + " (total: " +
                             std::to_string(subscribers_.size()) + ")");
}

void APTrackerEngine::remove_subscriber(const std::string &mod_id)
{
    std::lock_guard<std::mutex> lock(subscriber_mutex_);
    subscribers_.erase(mod_id);
    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Subscriber removed: " + mod_id + " (total: " +
                             std::to_string(subscribers_.size()) + ")");
}

bool APTrackerEngine::has_subscribers() const
{
    std::lock_guard<std::mutex> lock(subscriber_mutex_);
    return !subscribers_.empty();
}

std::set<std::string> APTrackerEngine::get_subscribers() const
{
    std::lock_guard<std::mutex> lock(subscriber_mutex_);
    return subscribers_;
}

std::optional<GoalDef> APTrackerEngine::get_active_goal() const
{
    return active_goal_;
}

bool APTrackerEngine::is_no_goal_mode() const
{
    return no_goal_mode_;
}

const std::string& APTrackerEngine::get_no_goal_label() const
{
    return no_goal_label_;
}

std::unordered_set<int64_t> APTrackerEngine::get_out_of_logic_location_ids() const
{
    std::unordered_set<int64_t> result;
    for (const auto &loc : parsed_locations_)
        if (loc.out_of_logic)
            result.insert(loc.location_id);
    return result;
}

const LogicNode *APTrackerEngine::get_goal_logic_node() const
{
    // goal_logic_node_ defaults to make_const(false) — only valid when initialized and goal is active
    if (!initialized_ || !active_goal_.has_value())
        return nullptr;
    return &goal_logic_node_;
}

// =============================================================================
// Ecosystem Metadata Building
// =============================================================================

void APTrackerEngine::build_ecosystem_metadata()
{
    auto *caps = APCapabilities::get();

    // Mods
    ecosystem_mods_.clear();
    auto manifests = APModRegistry::get()->get_enabled_manifests();
    for (const auto &manifest : manifests)
    {
        EcosystemMod mod;
        mod.mod_id = manifest.mod_id;
        mod.name = manifest.name;
        mod.version = manifest.version;
        mod.location_count = static_cast<int>(manifest.locations.size());
        mod.item_count = static_cast<int>(manifest.items.size());
        mod.region_count = static_cast<int>(manifest.regions.size());
        mod.goal_count = static_cast<int>(manifest.goals.size());
        mod.override_count = static_cast<int>(manifest.item_overrides.size());
        ecosystem_mods_.push_back(std::move(mod));
    }

    // Regions with per-mod contributions
    ecosystem_regions_.clear();
    auto merged_regions = caps->get_regions();
    auto all_contributions = caps->get_all_region_contributions();

    for (const auto &reg : merged_regions)
    {
        EcosystemRegion eco_reg;
        eco_reg.name = reg.name;
        eco_reg.merged_logic = reg.logic;

        // Collect contributions for this region
        for (const auto &contrib : all_contributions)
        {
            if (contrib.region_name == reg.name)
            {
                eco_reg.contributions.push_back({contrib.mod_id, contrib.logic});
            }
        }

        ecosystem_regions_.push_back(std::move(eco_reg));
    }

    // Locations
    ecosystem_locations_.clear();
    auto all_locations = caps->get_all_locations();
    for (const auto &loc : all_locations)
    {
        EcosystemLocation eco_loc;
        eco_loc.location_id = loc.location_id;
        eco_loc.name = loc.location_name;
        eco_loc.display_region = derive_display_region(loc.logic, loc.location_name);
        eco_loc.mod_id = loc.mod_id;
        eco_loc.logic = loc.logic;
        ecosystem_locations_.push_back(std::move(eco_loc));
    }

    // Items with override history
    ecosystem_items_.clear();
    auto all_items = caps->get_all_items();
    auto all_overrides = caps->get_item_overrides();

    for (const auto &item : all_items)
    {
        EcosystemItem eco_item;
        eco_item.item_id = item.item_id;
        eco_item.name = item.item_name;
        eco_item.type = item_type_to_string(item.type);
        eco_item.original_type = item_type_to_string(item.type); // Will be updated below
        eco_item.mod_id = item.mod_id;
        eco_item.logic = item.logic;

        // Find overrides targeting this item
        for (const auto &ovr : all_overrides)
        {
            bool name_match = ovr.target_item == item.item_name;
            bool mod_match = ovr.target_mod.empty() || ovr.target_mod == item.mod_id;
            if (name_match && mod_match)
            {
                EcosystemItem::OverrideEntry entry;
                entry.source_mod = ovr.source_mod;
                entry.new_type = ovr.type;
                entry.logic = ovr.logic;

                // Check if the override's option-only logic evaluates to true
                if (ovr.logic.empty())
                {
                    entry.applied = true;
                }
                else
                {
                    try
                    {
                        auto ast = parse_logic(ovr.logic);
                        ast = evaluate_options(ast, option_values_);
                        ast = simplify(ast);
                        // A const-true node means the option condition is satisfied
                        entry.applied = (ast.type == LogicNodeType::Const && ast.const_value);
                    }
                    catch (...)
                    {
                        entry.applied = false;
                    }
                }

                eco_item.overrides.push_back(std::move(entry));
            }
        }

        ecosystem_items_.push_back(std::move(eco_item));
    }

    APLogger::get()->log(LogLevel::Debug, "APTrackerEngine",
                         "Built ecosystem: " + std::to_string(ecosystem_mods_.size()) + " mods, " +
                             std::to_string(ecosystem_regions_.size()) + " regions, " +
                             std::to_string(ecosystem_locations_.size()) + " locations, " +
                             std::to_string(ecosystem_items_.size()) + " items");
}

} // namespace ap
