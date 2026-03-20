#include "ap_state_manager.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <chrono>
#include <nlohmann/json.hpp>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APStateManager *APStateManager::get()
{
    static std::unique_ptr<APStateManager> instance = std::make_unique<APStateManager>(ConstructorKey{});
    return instance.get();
}

APStateManager::APStateManager(ConstructorKey)
{
    // Default initialization
}

APStateManager::~APStateManager() = default;

// =============================================================================
// Persistence
// =============================================================================

bool APStateManager::save_state(const std::filesystem::path &path)
{
    APLogger::get()->log(LogLevel::Trace, "APStateManager", "Saving state to: " + path.string());

    try
    {
        std::string json_content = state_.to_json().dump(2);
        if (APPathUtil::get()->write_file(path, json_content))
        {
            APLogger::get()->log(LogLevel::Debug, "APStateManager", "Saved session state to: " + path.string());
            return true;
        }
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APStateManager",
                             "Failed to save session state: " + std::string(e.what()));
    }

    return false;
}

bool APStateManager::save_state()
{
    return save_state(APPathUtil::get()->get_session_state_path());
}

bool APStateManager::load_state(const std::filesystem::path &path)
{
    std::string content = APPathUtil::get()->read_file(path);
    if (content.empty())
    {
        APLogger::get()->log(LogLevel::Debug, "APStateManager", "No session state file found: " + path.string());
        return false;
    }

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);
        state_ = SessionState::from_json(j);
        loaded_ = true;

        APLogger::get()->log(LogLevel::Info, "APStateManager",
                             "Loaded session state from: " + path.string() +
                                 " (item_index=" + std::to_string(state_.received_item_index) +
                                 ", locations=" + std::to_string(state_.checked_locations.size()) + ")");

        return true;
    }
    catch (const nlohmann::json::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APStateManager",
                             "Failed to parse session state: " + std::string(e.what()));
        return false;
    }
}

bool APStateManager::load_state()
{
    return load_state(APPathUtil::get()->get_session_state_path());
}

void APStateManager::clear()
{
    state_ = SessionState{};
    loaded_ = false;
}

bool APStateManager::is_loaded() const
{
    return loaded_;
}

// =============================================================================
// Item Progress Tracking
// =============================================================================

void APStateManager::set_received_item_index(int index)
{
    state_.received_item_index = index;
}

int APStateManager::get_received_item_index() const
{
    return state_.received_item_index;
}

int APStateManager::increment_received_item_index()
{
    return ++state_.received_item_index;
}

// =============================================================================
// Location Tracking
// =============================================================================

void APStateManager::add_checked_location(int64_t location_id)
{
    state_.checked_locations.insert(location_id);
}

bool APStateManager::is_location_checked(int64_t location_id) const
{
    return state_.checked_locations.find(location_id) != state_.checked_locations.end();
}

std::set<int64_t> APStateManager::get_checked_locations() const
{
    return state_.checked_locations;
}

size_t APStateManager::get_checked_location_count() const
{
    return state_.checked_locations.size();
}

void APStateManager::set_checked_locations(const std::set<int64_t> &locations)
{
    state_.checked_locations = locations;
}

// =============================================================================
// Item Progression Counts
// =============================================================================

void APStateManager::set_item_progression_count(int64_t item_id, int count)
{
    state_.item_progression_counts[item_id] = count;
}

int APStateManager::get_item_progression_count(int64_t item_id) const
{
    auto it = state_.item_progression_counts.find(item_id);
    return (it != state_.item_progression_counts.end()) ? it->second : 0;
}

int APStateManager::increment_item_progression_count(int64_t item_id)
{
    return ++state_.item_progression_counts[item_id];
}

std::map<int64_t, int> APStateManager::get_all_item_progression_counts() const
{
    return state_.item_progression_counts;
}

// =============================================================================
// Checksum Validation
// =============================================================================

void APStateManager::set_checksum(const std::string &checksum)
{
    state_.checksum = checksum;
}

std::string APStateManager::get_checksum() const
{
    return state_.checksum;
}

bool APStateManager::validate_checksum(const std::string &current_checksum) const
{
    if (state_.checksum.empty())
    {
        // No stored checksum - first run
        return true;
    }

    bool match = (state_.checksum == current_checksum);
    if (!match)
    {
        APLogger::get()->log(LogLevel::Error, "APStateManager",
                             "Checksum mismatch! Stored: " + state_.checksum + ", Current: " + current_checksum);
    }
    return match;
}

// =============================================================================
// Session Info
// =============================================================================

void APStateManager::set_slot_name(const std::string &slot_name)
{
    state_.slot_name = slot_name;
}

std::string APStateManager::get_slot_name() const
{
    return state_.slot_name;
}

void APStateManager::set_game_name(const std::string &game_name)
{
    state_.game_name = game_name;
}

std::string APStateManager::get_game_name() const
{
    return state_.game_name;
}

void APStateManager::set_server_info(const std::string &server, int port)
{
    state_.ap_server = server;
    state_.ap_port = port;
}

std::string APStateManager::get_server() const
{
    return state_.ap_server;
}

int APStateManager::get_port() const
{
    return state_.ap_port;
}

void APStateManager::touch()
{
    state_.last_active = std::chrono::system_clock::now();
}

SessionState APStateManager::get_state() const
{
    return state_;
}

void APStateManager::set_state(const SessionState &state)
{
    state_ = state;
    loaded_ = true;
}

// =============================================================================
// Item Notification Tracking
// =============================================================================

void APStateManager::mark_item_handled(int64_t item_id, const std::string &mod_id, bool silence,
                                        int delivery_index)
{
    // Update handled_by for this item type (first mod wins)
    bool found = false;
    for (const auto &rec : state_.handled_items)
    {
        if (rec.item_id == item_id) { found = true; break; }
    }
    if (!found)
    {
        HandledItemRecord rec;
        rec.item_id    = item_id;
        rec.handled_by = mod_id;
        state_.handled_items.push_back(rec);
    }

    // Per-delivery silence (only when delivery_index is provided)
    if (silence && delivery_index >= 0)
    {
        for (const auto &sr : state_.silenced_deliveries)
        {
            if (sr.delivery_index == delivery_index && sr.mod_id == mod_id)
                return;  // already silenced
        }
        SilencedDeliveryRecord sr;
        sr.delivery_index = delivery_index;
        sr.mod_id         = mod_id;
        state_.silenced_deliveries.push_back(sr);
    }

    save_state();
}

bool APStateManager::is_item_handled(int64_t item_id) const
{
    for (const auto &rec : state_.handled_items)
        if (rec.item_id == item_id) return true;
    return false;
}

bool APStateManager::is_delivery_silenced(int delivery_index, const std::string &mod_id) const
{
    for (const auto &sr : state_.silenced_deliveries)
        if (sr.delivery_index == delivery_index && sr.mod_id == mod_id) return true;
    return false;
}

std::string APStateManager::get_item_handler(int64_t item_id) const
{
    for (const auto &rec : state_.handled_items)
        if (rec.item_id == item_id) return rec.handled_by;
    return "";
}

} // namespace ap