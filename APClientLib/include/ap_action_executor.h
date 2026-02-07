#pragma once

#include "ap_exports.h"
#include "Types/ap_shared_manifest_types.h"

#include <nlohmann/json.hpp>

#include <string>
#include <vector>

namespace ap::client
{

/**
 * @brief Executes Lua functions in the client mod's Lua state when instructed by the framework.
 *
 * Responsibilities:
 * - Resolves function references from manifest action strings (e.g., "MyUserObj.UnlockTechnology")
 * - Evaluates property references for dynamic argument values at runtime
 * - Reports errors back to framework if function not found or execution fails
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APActionExecutor
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APActionExecutor;
        explicit ConstructorKey() = default;
    };

    explicit APActionExecutor(ConstructorKey);
    ~APActionExecutor() = default;

    // Non-copyable, non-movable
    APActionExecutor(const APActionExecutor &) = delete;
    APActionExecutor &operator=(const APActionExecutor &) = delete;
    APActionExecutor(APActionExecutor &&) = delete;
    APActionExecutor &operator=(APActionExecutor &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APActionExecutor singleton.
     */
    static APActionExecutor *get();

    // =========================================================================
    // Action Execution
    // =========================================================================

    /**
     * Execute an action with the given parameters.
     *
     * @param action Function path (e.g., "MyUserObj.UnlockTechnology")
     * @param args Arguments to pass to the function
     * @param item_id The item ID being processed (for logging/results)
     * @param item_name The item name being processed (for logging/results)
     * @return ActionResult indicating success/failure
     */
    ap::ActionResult execute(const std::string &action, const std::vector<ap::ActionArg> &args, int64_t item_id = 0,
                             const std::string &item_name = "");

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
    ap::ActionResult execute_from_payload(const nlohmann::json &payload);

    /**
     * Parse an ArgType from its string representation.
     */
    static ap::ArgType parse_arg_type(const std::string &type_str);

    /**
     * Convert an ArgType to its string representation.
     */
    static std::string arg_type_to_string(ap::ArgType type);
};

} // namespace ap::client