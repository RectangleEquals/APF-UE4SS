#pragma once

#include <string>
#include <cstdint>
#include <nlohmann/json.hpp>

namespace ap {

// =============================================================================
// Log Level Enumeration
// =============================================================================

enum class ClientLogLevel {
    Trace = 0,
    Debug = 1,
    Info = 2,
    Warn = 3,
    Error = 4
};

inline std::string client_log_level_to_string(ClientLogLevel level) {
    switch (level) {
        case ClientLogLevel::Trace: return "trace";
        case ClientLogLevel::Debug: return "debug";
        case ClientLogLevel::Info: return "info";
        case ClientLogLevel::Warn: return "warn";
        case ClientLogLevel::Error: return "error";
        default: return "info";
    }
}

inline ClientLogLevel client_log_level_from_string(const std::string& str) {
    if (str == "trace") return ClientLogLevel::Trace;
    if (str == "debug") return ClientLogLevel::Debug;
    if (str == "info") return ClientLogLevel::Info;
    if (str == "warn" || str == "warning") return ClientLogLevel::Warn;
    if (str == "error") return ClientLogLevel::Error;
    return ClientLogLevel::Info;
}

inline int client_log_level_priority(ClientLogLevel level) {
    return static_cast<int>(level);
}

inline int client_log_level_priority(const std::string& level) {
    return client_log_level_priority(client_log_level_from_string(level));
}

// =============================================================================
// IPC Message Structure
// =============================================================================

/**
 * @brief IPC Message structure for client-side communication.
 *
 * Wire format: 4-byte LE length prefix + JSON body
 * Matches the server-side IPCMessage format.
 */
struct ClientIPCMessage {
    std::string type;
    std::string source;
    std::string target;
    nlohmann::json payload;

    nlohmann::json to_json() const {
        return {
            {"type", type},
            {"source", source},
            {"target", target},
            {"payload", payload}
        };
    }

    static ClientIPCMessage from_json(const nlohmann::json& j) {
        ClientIPCMessage msg;
        msg.type = j.value("type", "");
        msg.source = j.value("source", "");
        msg.target = j.value("target", "");
        msg.payload = j.value("payload", nlohmann::json::object());
        return msg;
    }
};

// =============================================================================
// IPC Message Type Constants
// =============================================================================

namespace IPCMessageType {
    // Framework -> Client
    constexpr const char* AP_MESSAGE = "ap_message";
    constexpr const char* EXECUTE_ACTION = "execute_action";
    constexpr const char* LIFECYCLE = "lifecycle";
    constexpr const char* ERROR_MSG = "error";
    constexpr const char* REGISTRATION_RESPONSE = "registration_response";
    constexpr const char* COMMAND_RESPONSE = "command_response";

    // Client -> Framework
    constexpr const char* REGISTER = "register";
    constexpr const char* LOCATION_CHECK = "location_check";
    constexpr const char* LOCATION_SCOUT = "location_scout";
    constexpr const char* LOG = "log";
    constexpr const char* ACTION_RESULT = "action_result";
    constexpr const char* CALLBACK_ERROR = "callback_error";
    constexpr const char* COMMAND = "command";
}

// =============================================================================
// IPC Target Constants
// =============================================================================

namespace IPCTarget {
    constexpr const char* FRAMEWORK = "framework";
    constexpr const char* BROADCAST = "broadcast";
    constexpr const char* PRIORITY = "priority";
}

// =============================================================================
// Action Result Structure
// =============================================================================

/**
 * @brief Result of executing an item action.
 */
struct ClientActionResult {
    int64_t item_id = 0;
    std::string item_name;
    bool success = false;
    std::string error;
};

} // namespace ap