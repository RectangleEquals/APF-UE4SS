#pragma once

#include "thread_safe_queue.h"
#include "ap_types.h"

#include <string>
#include <functional>
#include <variant>

namespace ap {

// =============================================================================
// Queue Type Aliases
// =============================================================================

/**
 * @brief Queue for IPC messages between framework and client mods.
 */
using IPCMessageQueue = ThreadSafeQueue<IPCMessage>;

/**
 * @brief Queue for action results from client mods.
 */
using ActionResultQueue = ThreadSafeQueue<ActionResult>;

// =============================================================================
// Event Types for Main Thread Dispatch
// =============================================================================

/**
 * @brief Event dispatched when an item is received from AP server.
 */
struct ItemReceivedEvent {
    int64_t item_id;
    std::string item_name;
    std::string sender;
    int64_t location_id;
    bool is_self;  // true if item was sent by this player
};

/**
 * @brief Event dispatched when a location is scouted.
 */
struct LocationScoutEvent {
    int64_t location_id;
    std::string location_name;
    int64_t item_id;
    std::string item_name;
    std::string player_name;  // Player who will receive this item
};

/**
 * @brief Event dispatched for lifecycle state changes.
 */
struct LifecycleEvent {
    LifecycleState old_state;
    LifecycleState new_state;
    std::string message;
};

/**
 * @brief Event dispatched for errors.
 */
struct ErrorEvent {
    std::string code;
    std::string message;
    std::string details;
};

/**
 * @brief Event dispatched for chat/hint messages from AP server.
 */
struct APMessageEvent {
    std::string type;  // "chat", "hint", "system", etc.
    std::string message;
    nlohmann::json data;  // Additional data if needed
};

/**
 * @brief Variant type for all framework events.
 */
using FrameworkEvent = std::variant<
    ItemReceivedEvent,
    LocationScoutEvent,
    LifecycleEvent,
    ErrorEvent,
    APMessageEvent
>;

/**
 * @brief Queue for events to be dispatched on main thread.
 */
using EventQueue = ThreadSafeQueue<FrameworkEvent>;

// =============================================================================
// Callback Types
// =============================================================================

/**
 * @brief Callback for item received events.
 */
using ItemCallback = std::function<void(const ItemReceivedEvent&)>;

/**
 * @brief Callback for location scout events.
 */
using ScoutCallback = std::function<void(const LocationScoutEvent&)>;

/**
 * @brief Callback for lifecycle events.
 */
using LifecycleCallback = std::function<void(LifecycleState, const std::string&)>;

/**
 * @brief Callback for error events.
 */
using ErrorCallback = std::function<void(const std::string&, const std::string&)>;

/**
 * @brief Callback for AP messages.
 */
using APMessageCallback = std::function<void(const std::string&, const std::string&)>;

// =============================================================================
// Pending Action Tracking
// =============================================================================

/**
 * @brief Queue for pending actions awaiting execution.
 */
using PendingActionQueue = ThreadSafeQueue<PendingAction>;

// =============================================================================
// Location Check Types
// =============================================================================

/**
 * @brief Request to check a location.
 */
struct LocationCheckRequest {
    std::string mod_id;
    std::string location_name;
    int instance = 1;  // For multi-instance locations
};

/**
 * @brief Request to scout locations.
 */
struct LocationScoutRequest {
    std::string mod_id;
    std::vector<std::string> location_names;
};

/**
 * @brief Queue for location check requests from client mods.
 */
using LocationCheckQueue = ThreadSafeQueue<LocationCheckRequest>;

/**
 * @brief Queue for location scout requests from client mods.
 */
using LocationScoutQueue = ThreadSafeQueue<LocationScoutRequest>;

} // namespace ap
