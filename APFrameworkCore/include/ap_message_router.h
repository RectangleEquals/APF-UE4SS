#pragma once

#include "ap_exports.h"
#include "ap_types.h"
#include "ap_client.h"
#include "ap_capabilities.h"
#include "ap_state_manager.h"

#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <optional>

namespace ap {

/**
 * @brief Routes messages between framework, AP server, and client mods.
 *
 * Handles:
 * - Item receipt routing (AP server -> framework -> client mod)
 * - Location check routing (client mod -> framework -> AP server)
 * - Location scout routing (client mod -> framework -> AP server -> client mod)
 * - Argument resolution for item actions
 * - Message dispatch to correct targets
 */
class AP_API APMessageRouter {
public:
    /**
     * @brief Callback for sending messages via IPC.
     */
    using IPCSendCallback = std::function<bool(const std::string& target, const IPCMessage&)>;

    /**
     * @brief Callback for broadcasting messages via IPC.
     */
    using IPCBroadcastCallback = std::function<void(const IPCMessage&)>;

    /**
     * @brief Callback for sending location checks to AP server.
     */
    using APLocationCheckCallback = std::function<void(const std::vector<int64_t>&)>;

    /**
     * @brief Callback for sending location scouts to AP server.
     */
    using APLocationScoutCallback = std::function<void(const std::vector<int64_t>&, bool)>;

    APMessageRouter();
    ~APMessageRouter();

    // Delete copy/move
    APMessageRouter(const APMessageRouter&) = delete;
    APMessageRouter& operator=(const APMessageRouter&) = delete;
    APMessageRouter(APMessageRouter&&) = delete;
    APMessageRouter& operator=(APMessageRouter&&) = delete;

    // ==========================================================================
    // Initialization
    // ==========================================================================

    /**
     * @brief Set the capabilities reference for ID lookups.
     * @param capabilities Pointer to capabilities system.
     */
    void set_capabilities(APCapabilities* capabilities);

    /**
     * @brief Set the state manager reference for progression tracking.
     * @param state_manager Pointer to state manager.
     */
    void set_state_manager(APStateManager* state_manager);

    /**
     * @brief Set IPC send callback.
     * @param callback Function to send IPC messages.
     */
    void set_ipc_send_callback(IPCSendCallback callback);

    /**
     * @brief Set IPC broadcast callback.
     * @param callback Function to broadcast IPC messages.
     */
    void set_ipc_broadcast_callback(IPCBroadcastCallback callback);

    /**
     * @brief Set AP location check callback.
     * @param callback Function to send location checks to AP server.
     */
    void set_ap_location_check_callback(APLocationCheckCallback callback);

    /**
     * @brief Set AP location scout callback.
     * @param callback Function to send location scouts to AP server.
     */
    void set_ap_location_scout_callback(APLocationScoutCallback callback);

    // ==========================================================================
    // Item Receipt Routing
    // ==========================================================================

    /**
     * @brief Route a received item to the owning mod.
     * @param item_id Item ID from AP server.
     * @param item_name Item name.
     * @param sender_name Name of the player who sent the item.
     * @return PendingAction if item has an action to execute.
     *
     * Flow:
     * 1. Look up item ownership by ID
     * 2. Resolve arguments with special placeholders
     * 3. Send EXECUTE_ACTION message to owning mod
     * 4. Return PendingAction for tracking
     */
    std::optional<PendingAction> route_item_receipt(int64_t item_id,
                                                    const std::string& item_name,
                                                    const std::string& sender_name);

    /**
     * @brief Resolve arguments for an item action.
     * @param item Item ownership with action definition.
     * @return Resolved arguments with placeholders replaced.
     *
     * Resolves:
     * - <GET_ITEM_ID> -> item.item_id
     * - <GET_ITEM_NAME> -> item.item_name
     * - <GET_PROGRESSION_COUNT> -> current progression count
     */
    std::vector<ActionArg> resolve_arguments(const ItemOwnership& item);

    // ==========================================================================
    // Location Check Routing
    // ==========================================================================

    /**
     * @brief Route a location check from a client mod.
     * @param mod_id Source mod ID.
     * @param location_name Location name.
     * @param instance Instance number (for multi-instance locations).
     * @return Location ID if found and not already checked, 0 otherwise.
     *
     * Flow:
     * 1. Look up location ID
     * 2. Check if already checked (state_manager)
     * 3. Mark as checked in state_manager
     * 4. Send to AP server via callback
     */
    int64_t route_location_check(const std::string& mod_id,
                                 const std::string& location_name,
                                 int instance = 1);

    /**
     * @brief Route multiple location checks at once.
     * @param location_ids Vector of location IDs to check.
     */
    void route_location_checks(const std::vector<int64_t>& location_ids);

    // ==========================================================================
    // Location Scout Routing
    // ==========================================================================

    /**
     * @brief Route a location scout request from a client mod.
     * @param mod_id Source mod ID.
     * @param location_names Locations to scout.
     * @param create_hints If true, creates hints for scouted items.
     * @return Vector of location IDs being scouted.
     *
     * Scout results will be routed back via route_scout_results().
     */
    std::vector<int64_t> route_location_scouts(const std::string& mod_id,
                                               const std::vector<std::string>& location_names,
                                               bool create_hints = false);

    /**
     * @brief Route scout results back to the requesting mod.
     * @param mod_id Target mod ID.
     * @param results Scout results from AP server.
     */
    void route_scout_results(const std::string& mod_id,
                             const std::vector<ScoutResult>& results);

    // ==========================================================================
    // Action Result Handling
    // ==========================================================================

    /**
     * @brief Handle an action result from a client mod.
     * @param mod_id Source mod ID.
     * @param result Action execution result.
     */
    void handle_action_result(const std::string& mod_id, const ActionResult& result);

    // ==========================================================================
    // Lifecycle & Error Broadcasting
    // ==========================================================================

    /**
     * @brief Broadcast a lifecycle state change to all mods.
     * @param state New lifecycle state.
     * @param message Optional message.
     */
    void broadcast_lifecycle(LifecycleState state, const std::string& message = "");

    /**
     * @brief Broadcast an error to all mods.
     * @param code Error code.
     * @param message Error message.
     * @param details Additional details.
     */
    void broadcast_error(const std::string& code,
                         const std::string& message,
                         const std::string& details = "");

    /**
     * @brief Send an AP message to all mods.
     * @param type Message type.
     * @param message Message content.
     */
    void broadcast_ap_message(const std::string& type, const std::string& message);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
