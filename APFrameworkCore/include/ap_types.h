#pragma once

#include <chrono>
#include <cstdint>
#include <map>
#include <nlohmann/json.hpp>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace ap {

// =============================================================================
// Enumerations
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

enum class LogLevel {
  Trace = 0,
  Debug = 1,
  Info = 2,
  Warn = 3,
  Error = 4,
  Fatal = 5
};

enum class ModType { Regular, Priority };

enum class ItemType { Progression, Useful, Filler, Trap };

enum class ArgType { String, Number, Boolean, Property };

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

inline std::string log_level_to_string(LogLevel level) {
  switch (level) {
  case LogLevel::Trace:
    return "TRACE";
  case LogLevel::Debug:
    return "DEBUG";
  case LogLevel::Info:
    return "INFO";
  case LogLevel::Warn:
    return "WARN";
  case LogLevel::Error:
    return "ERROR";
  case LogLevel::Fatal:
    return "FATAL";
  default:
    return "UNKNOWN";
  }
}

inline std::string item_type_to_string(ItemType type) {
  switch (type) {
  case ItemType::Progression:
    return "progression";
  case ItemType::Useful:
    return "useful";
  case ItemType::Filler:
    return "filler";
  case ItemType::Trap:
    return "trap";
  default:
    return "unknown";
  }
}

inline ItemType item_type_from_string(const std::string &str) {
  if (str == "progression")
    return ItemType::Progression;
  if (str == "useful")
    return ItemType::Useful;
  if (str == "filler")
    return ItemType::Filler;
  if (str == "trap")
    return ItemType::Trap;
  return ItemType::Filler;
}

inline std::string arg_type_to_string(ArgType type) {
  switch (type) {
  case ArgType::String:
    return "string";
  case ArgType::Number:
    return "number";
  case ArgType::Boolean:
    return "boolean";
  case ArgType::Property:
    return "property";
  default:
    return "unknown";
  }
}

inline ArgType arg_type_from_string(const std::string &str) {
  if (str == "string")
    return ArgType::String;
  if (str == "number")
    return ArgType::Number;
  if (str == "boolean")
    return ArgType::Boolean;
  if (str == "property")
    return ArgType::Property;
  return ArgType::String;
}

// =============================================================================
// Manifest Structures (Design02)
// =============================================================================

struct ActionArg {
  std::string name;
  ArgType type = ArgType::String;
  nlohmann::json value;
};

struct LocationDef {
  std::string name;
  int amount = 1;
  bool unique = false;
};

struct ItemDef {
  std::string name;
  ItemType type = ItemType::Filler;
  int amount = 1;
  std::string action;
  std::vector<ActionArg> args;
};

struct IncompatibilityRule {
  std::string id;
  std::vector<std::string> versions;
};

struct Manifest {
  std::string mod_id;
  std::string name;
  std::string version;
  bool enabled = true;
  std::string description;
  std::vector<IncompatibilityRule> incompatible;
  std::vector<LocationDef> locations;
  std::vector<ItemDef> items;
};

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
// IPC Message Structure (Design04)
// =============================================================================

struct IPCMessage {
  std::string type;
  std::string source;
  std::string target;
  nlohmann::json payload;

  nlohmann::json to_json() const {
    return {{"type", type},
            {"source", source},
            {"target", target},
            {"payload", payload}};
  }

  static IPCMessage from_json(const nlohmann::json &j) {
    IPCMessage msg;
    msg.type = j.value("type", "");
    msg.source = j.value("source", "");
    msg.target = j.value("target", "");
    msg.payload = j.value("payload", nlohmann::json::object());
    return msg;
  }
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

// =============================================================================
// Configuration Structures (Design03)
// =============================================================================

struct TimeoutConfig {
  int priority_registration_ms = 30000;
  int registration_ms = 60000;
  int connection_ms = 30000;
  int ipc_message_ms = 5000;
  int action_execution_ms = 5000;
};

struct RetryConfig {
  int max_retries = 3;
  int initial_delay_ms = 1000;
  double backoff_multiplier = 2.0;
  int max_delay_ms = 10000;
};

struct ThreadingConfig {
  int polling_interval_ms = 16;
  int ipc_poll_interval_ms = 10;
  int queue_max_size = 1000;
  int shutdown_timeout_ms = 5000;
};

struct APServerConfig {
  std::string server = "localhost";
  int port = 38281;
  std::string slot_name;
  std::string password;
  bool auto_reconnect = true;
};

struct FrameworkConfig {
  int64_t id_base = 6942067;
  std::string game_name;
  LogLevel log_level = LogLevel::Info;
  std::string log_file = "ap_framework.log";
  bool log_to_console = true;
  TimeoutConfig timeouts;
  RetryConfig retry;
  ThreadingConfig threading;
  APServerConfig ap_server;
};

// =============================================================================
// IPC Message Type Constants (Design04)
// =============================================================================

namespace IPCMessageType {
// Framework -> Client
constexpr const char *AP_MESSAGE = "ap_message";
constexpr const char *EXECUTE_ACTION = "execute_action";
constexpr const char *LIFECYCLE = "lifecycle";
constexpr const char *ERROR_MSG =
    "error"; // Note: ERROR conflicts with Windows macro
constexpr const char *REGISTRATION_RESPONSE = "registration_response";

// Client -> Framework
constexpr const char *REGISTER = "register";
constexpr const char *LOCATION_CHECK = "location_check";
constexpr const char *LOCATION_SCOUT = "location_scout";
constexpr const char *LOG = "log";
constexpr const char *ACTION_RESULT = "action_result";

// Priority Client -> Framework (legacy specific commands)
constexpr const char *CMD_RESTART = "cmd_restart";
constexpr const char *CMD_RESYNC = "cmd_resync";
constexpr const char *CMD_RECONNECT = "cmd_reconnect";
constexpr const char *GET_MODS = "get_mods";
constexpr const char *GET_LOGS = "get_logs";
constexpr const char *GET_DATA_PACKAGE = "get_data_package";
constexpr const char *SET_CONFIG = "set_config";
constexpr const char *SEND_MESSAGE = "send_message";
constexpr const char *BROADCAST = "broadcast";

// Framework -> Priority Client (legacy responses)
constexpr const char *GET_MODS_RESPONSE = "get_mods_response";
constexpr const char *GET_LOGS_RESPONSE = "get_logs_response";
constexpr const char *GET_DATA_PACKAGE_RESPONSE = "get_data_package_response";

// Generic Command System (new)
constexpr const char *COMMAND = "command"; // Client -> Framework
constexpr const char *COMMAND_RESPONSE =
    "command_response"; // Framework -> Client
} // namespace IPCMessageType

// =============================================================================
// IPC Target Constants (Design04)
// =============================================================================

namespace IPCTarget {
constexpr const char *FRAMEWORK = "framework";
constexpr const char *BROADCAST = "broadcast";
constexpr const char *PRIORITY = "priority";
} // namespace IPCTarget

} // namespace ap
