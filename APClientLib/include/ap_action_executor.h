#pragma once

#include "ap_clientlib_exports.h"

#include <nlohmann/json.hpp>

#include <string>
#include <vector>
#include <optional>
#include <functional>

// Forward declaration for Lua state
struct lua_State;

namespace ap::client {

/**
 * Result of executing an action.
 */
struct ActionResult {
    bool success = false;
    std::string error;
    int64_t item_id = 0;
    std::string item_name;
};

/**
 * Argument types for action execution.
 */
enum class ArgType {
    String,
    Number,
    Boolean,
    Property  // Evaluated at runtime from Lua state
};

/**
 * An argument passed to an action function.
 */
struct ActionArg {
    std::string name;
    ArgType type;
    nlohmann::json value;  // The value (or property path for Property type)
};

/**
 * Executes Lua functions in the client mod's Lua state when instructed by the framework.
 *
 * Responsibilities:
 * - Resolves function references from manifest action strings (e.g., "MyUserObj.UnlockTechnology")
 * - Evaluates property references for dynamic argument values at runtime
 * - Reports errors back to framework if function not found or execution fails
 */
class APCLIENT_API APActionExecutor {
public:
    APActionExecutor();
    ~APActionExecutor();

    // Non-copyable
    APActionExecutor(const APActionExecutor&) = delete;
    APActionExecutor& operator=(const APActionExecutor&) = delete;

    /**
     * Execute an action with the given parameters.
     *
     * @param action Function path (e.g., "MyUserObj.UnlockTechnology")
     * @param args Arguments to pass to the function
     * @param item_id The item ID being processed (for logging/results)
     * @param item_name The item name being processed (for logging/results)
     * @return ActionResult indicating success/failure
     */
    ActionResult execute(
        const std::string& action,
        const std::vector<ActionArg>& args,
        int64_t item_id = 0,
        const std::string& item_name = ""
    );

    /**
     * Execute an action from an IPC message payload.
     *
     * Expected payload format:
     * {
     *   "item_id": 123,
     *   "item_name": "Speed Boots",
     *   "action": "MyUserObj.UnlockTechnology",
     *   "args": [
     *     {"name": "id", "type": "number", "value": 123},
     *     {"name": "pos", "type": "property", "value": "MyPlayerObj.player_pos"}
     *   ],
     *   "sender": "Player1"
     * }
     *
     * @param payload The IPC message payload
     * @return ActionResult indicating success/failure
     */
    ActionResult execute_from_payload(const nlohmann::json& payload);

    /**
     * Parse an ArgType from its string representation.
     */
    static ArgType parse_arg_type(const std::string& type_str);

    /**
     * Convert an ArgType to its string representation.
     */
    static std::string arg_type_to_string(ArgType type);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap::client
