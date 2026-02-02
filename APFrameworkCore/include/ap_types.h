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
};

struct ItemOwnership {
  std::string mod_id;
  std::string item_name;
  int64_t item_id = 0;
  ItemType type = ItemType::Filler;
  std::string action;
  std::vector<ActionArg> args;
  int max_count = 1;
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

struct ActionResult {
  std::string mod_id;
  int64_t item_id = 0;
  std::string item_name;
  bool success = false;
  std::string error;
};

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
};

struct CapabilitiesConfigItem {
  int64_t id = 0;
  std::string name;
  std::string type;
  std::string mod_id;
  int count = 1;
};

struct CapabilitiesConfig {
  std::string version;
  std::string game;
  std::string slot_name;
  std::string checksum;
  int64_t id_base = 6942067;
  std::string generated_at;
  std::vector<ModInfo> mods;
  std::vector<CapabilitiesConfigLocation> locations;
  std::vector<CapabilitiesConfigItem> items;

  nlohmann::json to_json() const {
    nlohmann::json mods_arr = nlohmann::json::array();
    for (const auto &mod : mods) {
      mods_arr.push_back({{"mod_id", mod.mod_id},
                          {"name", mod.name},
                          {"version", mod.version}});
    }

    nlohmann::json locs_arr = nlohmann::json::array();
    for (const auto &loc : locations) {
      locs_arr.push_back({{"id", loc.id},
                          {"name", loc.name},
                          {"mod_id", loc.mod_id},
                          {"instance", loc.instance}});
    }

    nlohmann::json items_arr = nlohmann::json::array();
    for (const auto &item : items) {
      items_arr.push_back({{"id", item.id},
                           {"name", item.name},
                           {"type", item.type},
                           {"mod_id", item.mod_id},
                           {"count", item.count}});
    }

    return {{"version", version},     {"game", game},
            {"slot_name", slot_name}, {"checksum", checksum},
            {"id_base", id_base},     {"generated_at", generated_at},
            {"mods", mods_arr},       {"locations", locs_arr},
            {"items", items_arr}};
  }
};

} // namespace ap