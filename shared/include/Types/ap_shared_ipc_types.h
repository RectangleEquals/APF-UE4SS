#pragma once

/**
 * @file ap_shared_ipc_types.h
 * @brief IPC message structures and type constants shared by both libraries.
 */

#include <nlohmann/json.hpp>
#include <string>

namespace ap {

// =============================================================================
// IPC Message Structure
// =============================================================================

/**
 * @brief IPC Message structure for framework/client communication.
 *
 * Wire format: 4-byte LE length prefix + JSON body
 */
struct IPCMessage {
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

    static IPCMessage from_json(const nlohmann::json& j) {
        IPCMessage msg;
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
    constexpr const char* AP_MESSAGE            = "ap_message";
    constexpr const char* EXECUTE_ACTION        = "execute_action";
    constexpr const char* LIFECYCLE             = "lifecycle";
    constexpr const char* ERROR_MSG             = "error";  // Note: ERROR conflicts with Windows macro
    constexpr const char* REGISTRATION_RESPONSE = "registration_response";
    constexpr const char* COMMAND_RESPONSE      = "command_response";

    // Client -> Framework
    constexpr const char* REGISTER        = "register";
    constexpr const char* LOCATION_CHECK  = "location_check";
    constexpr const char* LOCATION_SCOUT  = "location_scout";
    constexpr const char* LOG             = "log";
    constexpr const char* ACTION_RESULT   = "action_result";
    constexpr const char* CALLBACK_ERROR  = "callback_error";
    constexpr const char* COMMAND         = "command";

    // Priority Client -> Framework (legacy specific commands)
    constexpr const char* CMD_RESTART             = "cmd_restart";
    constexpr const char* CMD_RESYNC              = "cmd_resync";
    constexpr const char* CMD_RECONNECT           = "cmd_reconnect";
    constexpr const char* GET_MODS                = "get_mods";
    constexpr const char* GET_LOGS                = "get_logs";
    constexpr const char* GET_DATA_PACKAGE        = "get_data_package";
    constexpr const char* SET_CONFIG              = "set_config";
    constexpr const char* SEND_MESSAGE            = "send_message";
    constexpr const char* BROADCAST               = "broadcast";

    // Framework -> Priority Client (legacy responses)
    constexpr const char* GET_MODS_RESPONSE         = "get_mods_response";
    constexpr const char* GET_LOGS_RESPONSE         = "get_logs_response";
    constexpr const char* GET_DATA_PACKAGE_RESPONSE = "get_data_package_response";

    // Tracker Protocol
    constexpr const char* SUBSCRIBE_TRACKER   = "subscribe_tracker";
    constexpr const char* UNSUBSCRIBE_TRACKER = "unsubscribe_tracker";
    constexpr const char* TRACKER_SNAPSHOT    = "tracker_snapshot";
    constexpr const char* TRACKER_UPDATE      = "tracker_update";

    // Cross-Mod API Protocol
    constexpr const char* API_CALL   = "api_call";     // Client -> Framework -> Client
    constexpr const char* API_RESULT = "api_result";   // Client -> Framework -> Client
}

// =============================================================================
// IPC Target Constants
// =============================================================================

namespace IPCTarget {
    constexpr const char* FRAMEWORK = "framework";
    constexpr const char* BROADCAST = "broadcast";
    constexpr const char* PRIORITY  = "priority";
}

} // namespace ap