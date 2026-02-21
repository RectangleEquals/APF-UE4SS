#pragma once

// Include shared types from APShared library
#include "Types/ap_shared_enums.h"
#include "Types/ap_shared_ipc_types.h"
#include "Types/ap_shared_config_types.h"
#include "Types/ap_shared_manifest_types.h"

#include <chrono>
#include <cstdint>
#include <map>
#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include <vector>

namespace ap {

// =============================================================================
// Framework-Specific Enumerations
// =============================================================================

enum class LifecycleState {
  UNINITIALIZED,
  INITIALIZATION,
  DISCOVERY,
  VALIDATION,
  GENERATION,
  PRIORITY_REGISTRATION,
  REGISTRATION,
  CONNECTING,
  SYNCING,
  ACTIVE,
  RESYNCING,
  ERROR_STATE
};

enum class ModType { Regular, Priority };

enum class ClientStatus {
  Unknown = 0,
  Connected = 5,
  Ready = 10,
  Playing = 20,
  Goal = 30
};

// =============================================================================
// Error Codes
// =============================================================================

namespace ErrorCode {
constexpr const char *CONFIG_INVALID = "CONFIG_INVALID";
constexpr const char *IPC_FAILED = "IPC_FAILED";
constexpr const char *CONFLICT_DETECTED = "CONFLICT_DETECTED";
constexpr const char *REGISTRATION_TIMEOUT = "REGISTRATION_TIMEOUT";
constexpr const char *CONNECTION_FAILED = "CONNECTION_FAILED";
constexpr const char *SYNC_FAILED = "SYNC_FAILED";
constexpr const char *CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH";
constexpr const char *ACTION_FAILED = "ACTION_FAILED";
constexpr const char *ACTION_TIMEOUT = "ACTION_TIMEOUT";
constexpr const char *PROPERTY_FAILED = "PROPERTY_FAILED";
constexpr const char *MESSAGE_DROPPED = "MESSAGE_DROPPED";
} // namespace ErrorCode

// =============================================================================
// Utility Functions
// =============================================================================

inline std::string lifecycle_state_to_string(LifecycleState state) {
  switch (state) {
  case LifecycleState::UNINITIALIZED:
    return "UNINITIALIZED";
  case LifecycleState::INITIALIZATION:
    return "INITIALIZATION";
  case LifecycleState::DISCOVERY:
    return "DISCOVERY";
  case LifecycleState::VALIDATION:
    return "VALIDATION";
  case LifecycleState::GENERATION:
    return "GENERATION";
  case LifecycleState::PRIORITY_REGISTRATION:
    return "PRIORITY_REGISTRATION";
  case LifecycleState::REGISTRATION:
    return "REGISTRATION";
  case LifecycleState::CONNECTING:
    return "CONNECTING";
  case LifecycleState::SYNCING:
    return "SYNCING";
  case LifecycleState::ACTIVE:
    return "ACTIVE";
  case LifecycleState::RESYNCING:
    return "RESYNCING";
  case LifecycleState::ERROR_STATE:
    return "ERROR_STATE";
  default:
    return "UNKNOWN";
  }
}

// =============================================================================
// Registry and Ownership Structures (Design05)
// =============================================================================

struct ModInfo {
  std::string mod_id;
  std::string name;
  std::string version;
  ModType type = ModType::Regular;
  bool is_registered = false;
  bool has_conflict = false;
};

struct LocationOwnership {
  std::string mod_id;
  std::string location_name;
  int64_t location_id = 0;
  int instance = 1;
  std::string region;                                // Region this location belongs to
  std::string logic;                                 // Logic expression string
  std::string requires_option;                       // Option conditional
};

struct ItemOwnership {
  std::string mod_id;
  std::string item_name;
  int64_t item_id = 0;
  ItemType type = ItemType::Filler;
  std::string action;
  std::vector<ActionArg> args;
  int max_count = 1;
  std::string requires_option;                       // Option conditional
};

// =============================================================================
// Action Execution Structures (Design05, Design08)
// =============================================================================

struct PendingAction {
  std::string mod_id;
  int64_t item_id = 0;
  std::string item_name;
  std::string action;
  std::vector<ActionArg> resolved_args;
  std::chrono::steady_clock::time_point started_at;
};

// ActionResult is now defined in shared/include/Types/ap_shared_manifest_types.h

// =============================================================================
// Validation Structures (Design02)
// =============================================================================

struct Conflict {
  std::string capability_name;
  std::string mod_id_1;
  std::string mod_id_2;
  std::string description;
};

struct ValidationResult {
  bool valid = true;
  std::vector<Conflict> conflicts;
  std::vector<std::string> warnings;
};

// =============================================================================
// Session State Structure (Design08)
// =============================================================================

struct SessionState {
  std::string version;
  std::string checksum;
  std::string slot_name;
  std::string game_name;
  int received_item_index = 0;
  std::set<int64_t> checked_locations;
  std::map<int64_t, int> item_progression_counts;
  std::string ap_server;
  int ap_port = 38281;
  std::chrono::system_clock::time_point last_active;

  nlohmann::json to_json() const {
    std::vector<int64_t> checked_vec(checked_locations.begin(),
                                     checked_locations.end());
    nlohmann::json progression_counts = nlohmann::json::object();
    for (const auto &[id, count] : item_progression_counts) {
      progression_counts[std::to_string(id)] = count;
    }

    auto time_t = std::chrono::system_clock::to_time_t(last_active);

    return {{"version", version},
            {"checksum", checksum},
            {"slot_name", slot_name},
            {"game_name", game_name},
            {"received_item_index", received_item_index},
            {"checked_locations", checked_vec},
            {"item_progression_counts", progression_counts},
            {"ap_server", ap_server},
            {"ap_port", ap_port},
            {"last_active", time_t}};
  }

  static SessionState from_json(const nlohmann::json &j) {
    SessionState state;
    state.version = j.value("version", "");
    state.checksum = j.value("checksum", "");
    state.slot_name = j.value("slot_name", "");
    state.game_name = j.value("game_name", "");
    state.received_item_index = j.value("received_item_index", 0);

    if (j.contains("checked_locations") && j["checked_locations"].is_array()) {
      for (const auto &loc : j["checked_locations"]) {
        state.checked_locations.insert(loc.get<int64_t>());
      }
    }

    if (j.contains("item_progression_counts") &&
        j["item_progression_counts"].is_object()) {
      for (const auto &[key, val] : j["item_progression_counts"].items()) {
        state.item_progression_counts[std::stoll(key)] = val.get<int>();
      }
    }

    state.ap_server = j.value("ap_server", "");
    state.ap_port = j.value("ap_port", 38281);

    if (j.contains("last_active")) {
      std::time_t t = j["last_active"].get<std::time_t>();
      state.last_active = std::chrono::system_clock::from_time_t(t);
    }

    return state;
  }
};

// =============================================================================
// Capabilities Config Structure (Design07)
// =============================================================================

struct CapabilitiesConfigLocation {
  int64_t id = 0;
  std::string name;
  std::string mod_id;
  int instance = 1;
  std::string region;                                // Region name
  std::string logic;                                 // Logic expression string
  std::string requires_option;                       // Option conditional
};

struct CapabilitiesConfigItem {
  int64_t id = 0;
  std::string name;
  std::string type;
  std::string mod_id;
  int count = 1;
  std::string requires_option;                       // Option conditional
};

struct CapabilitiesConfigRegion {
  std::string name;
  std::string logic;                                 // Logic expression string
  std::string requires_option;                       // Option conditional
};

struct CapabilitiesConfigGoal {
  std::string name;                                  // Unique identifier
  std::string display;                               // Display name for player
  std::string description;                           // Description shown to player
  std::string logic;                                 // Logic expression for completion
  std::string mod_id;                                // Mod that declared this goal
};

struct CapabilitiesConfigItemOverride {
  std::string target_item;                           // Item name to override
  std::string target_mod;                            // Mod that owns the target item
  std::string type;                                  // New item type
  std::string requires_option;                       // Condition for applying override
  std::string source_mod;                            // Mod that declared this override
};

struct CapabilitiesData {
  std::vector<CapabilitiesConfigRegion> regions;
  std::vector<CapabilitiesConfigLocation> locations;
  std::vector<CapabilitiesConfigItem> items;
  std::vector<CapabilitiesConfigGoal> goals;
  std::vector<CapabilitiesConfigItemOverride> item_overrides;
};

struct CapabilitiesConfig {
  std::string version;
  std::string game;
  std::string slot_name;
  std::string generated_at;
  int64_t id_base = 6942067;
  std::string checksum;
  std::vector<ModInfo> mods;
  CapabilitiesData capabilities;

  nlohmann::ordered_json to_json() const {
    nlohmann::ordered_json j;

    j["version"] = version;
    j["game"] = game;
    j["slot_name"] = slot_name;
    j["generated_at"] = generated_at;
    j["id_base"] = id_base;
    j["checksum"] = checksum;

    nlohmann::ordered_json mods_arr = nlohmann::ordered_json::array();
    for (const auto &mod : mods) {
      nlohmann::ordered_json m;
      m["mod_id"] = mod.mod_id;
      m["name"] = mod.name;
      m["version"] = mod.version;
      mods_arr.push_back(m);
    }
    j["mods"] = mods_arr;

    nlohmann::ordered_json caps;

    // Emit regions
    nlohmann::ordered_json regions_arr = nlohmann::ordered_json::array();
    for (const auto &region : capabilities.regions) {
      nlohmann::ordered_json r;
      r["name"] = region.name;
      if (!region.logic.empty())
        r["logic"] = region.logic;
      if (!region.requires_option.empty())
        r["requires_option"] = region.requires_option;
      regions_arr.push_back(r);
    }
    if (!regions_arr.empty())
      caps["regions"] = regions_arr;

    // Emit locations
    nlohmann::ordered_json locs_arr = nlohmann::ordered_json::array();
    for (const auto &loc : capabilities.locations) {
      nlohmann::ordered_json l;
      l["id"] = loc.id;
      l["name"] = loc.name;
      l["mod_id"] = loc.mod_id;
      l["instance"] = loc.instance;
      if (!loc.region.empty())
        l["region"] = loc.region;
      if (!loc.logic.empty())
        l["logic"] = loc.logic;
      if (!loc.requires_option.empty())
        l["requires_option"] = loc.requires_option;
      locs_arr.push_back(l);
    }
    caps["locations"] = locs_arr;

    // Emit items
    nlohmann::ordered_json items_arr = nlohmann::ordered_json::array();
    for (const auto &item : capabilities.items) {
      nlohmann::ordered_json it;
      it["id"] = item.id;
      it["name"] = item.name;
      it["type"] = item.type;
      it["mod_id"] = item.mod_id;
      it["count"] = item.count;
      if (!item.requires_option.empty())
        it["requires_option"] = item.requires_option;
      items_arr.push_back(it);
    }
    caps["items"] = items_arr;

    // Emit goals
    if (!capabilities.goals.empty()) {
      nlohmann::ordered_json goals_arr = nlohmann::ordered_json::array();
      for (const auto &goal : capabilities.goals) {
        nlohmann::ordered_json g;
        g["name"] = goal.name;
        g["display"] = goal.display;
        if (!goal.description.empty())
          g["description"] = goal.description;
        g["logic"] = goal.logic;
        g["mod_id"] = goal.mod_id;
        goals_arr.push_back(g);
      }
      caps["goals"] = goals_arr;
    }

    // Emit item_overrides
    if (!capabilities.item_overrides.empty()) {
      nlohmann::ordered_json overrides_arr = nlohmann::ordered_json::array();
      for (const auto &ovr : capabilities.item_overrides) {
        nlohmann::ordered_json o;
        o["target_item"] = ovr.target_item;
        o["target_mod"] = ovr.target_mod;
        o["type"] = ovr.type;
        if (!ovr.requires_option.empty())
          o["requires_option"] = ovr.requires_option;
        o["source_mod"] = ovr.source_mod;
        overrides_arr.push_back(o);
      }
      caps["item_overrides"] = overrides_arr;
    }

    j["capabilities"] = caps;

    return j;
  }
};

} // namespace ap