#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace ap
{

// Forward declarations for types used in callbacks
struct ScoutResult;
struct ItemOwnership;

/**
 * @brief Singleton that routes messages between framework, AP server, and client mods.
 *
 * Handles:
 * - Item receipt routing (AP server -> framework -> client mod)
 * - Location check routing (client mod -> framework -> AP server)
 * - Location scout routing (client mod -> framework -> AP server -> client mod)
 * - Argument resolution for item actions
 * - Message dispatch to correct targets
 *
 * Uses singletons directly:
 * - APCapabilities::get() for ID lookups
 * - APStateManager::get() for progression tracking
 * - APIPCServer::get() for IPC messaging
 * - APArchipelagoClient::get() for AP server communication
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APMessageRouter
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APMessageRouter;
        explicit ConstructorKey() = default;
    };

    explicit APMessageRouter(ConstructorKey);
    ~APMessageRouter();

    // Delete copy/move
    APMessageRouter(const APMessageRouter &) = delete;
    APMessageRouter &operator=(const APMessageRouter &) = delete;
    APMessageRouter(APMessageRouter &&) = delete;
    APMessageRouter &operator=(APMessageRouter &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APMessageRouter singleton.
     */
    static APMessageRouter *get();

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
    std::optional<PendingAction> route_item_receipt(int64_t item_id, const std::string &item_name,
                                                    const std::string &sender_name);

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
    std::vector<ActionArg> resolve_arguments(const ItemOwnership &item);

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
    int64_t route_location_check(const std::string &mod_id, const std::string &location_name, int instance = 1);

    /**
     * @brief Route multiple location checks at once.
     * @param location_ids Vector of location IDs to check.
     */
    void route_location_checks(const std::vector<int64_t> &location_ids);

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
    std::vector<int64_t> route_location_scouts(const std::string &mod_id,
                                               const std::vector<std::string> &location_names,
                                               bool create_hints = false);

    /**
     * @brief Route scout results back to the requesting mod.
     * @param mod_id Target mod ID.
     * @param results Scout results from AP server.
     */
    void route_scout_results(const std::string &mod_id, const std::vector<ScoutResult> &results);

    // ==========================================================================
    // Action Result Handling
    // ==========================================================================

    /**
     * @brief Handle an action result from a client mod.
     * @param mod_id Source mod ID.
     * @param result Action execution result.
     */
    void handle_action_result(const std::string &mod_id, const ActionResult &result);

    // ==========================================================================
    // Lifecycle & Error Broadcasting
    // ==========================================================================

    /**
     * @brief Broadcast a lifecycle state change to all mods.
     * @param state New lifecycle state.
     * @param message Optional message.
     */
    void broadcast_lifecycle(LifecycleState state, const std::string &message = "");

    /**
     * @brief Broadcast an error to all mods.
     * @param code Error code.
     * @param message Error message.
     * @param details Additional details.
     */
    void broadcast_error(const std::string &code, const std::string &message, const std::string &details = "");

    /**
     * @brief Send an AP message to all mods.
     * @param type Message type.
     * @param message Message content.
     */
    void broadcast_ap_message(const std::string &type, const std::string &message);

    // ==========================================================================
    // Tracker Broadcasting
    // ==========================================================================

    /**
     * @brief Recompute tracker state and broadcast updates to subscribers.
     *
     * Call after any state change that affects tracker results
     * (item progression count change, location checked, etc.)
     */
    void broadcast_tracker_update();

  private:
    // =========================================================================
    // Private Member Variables
    // =========================================================================
    std::mutex scout_mutex_;
    std::unordered_map<int64_t, std::string> pending_scouts_; // location_id -> mod_id
};

} // namespace ap
