#include "ap_message_router.h"
#include "ap_capabilities.h"
#include "ap_client.h"
#include "ap_ipc_server.h"
#include "ap_logger.h"
#include "ap_logic_evaluator.h"
#include "ap_state_manager.h"
#include "ap_tracker_engine.h"

#include <chrono>
#include <nlohmann/json.hpp>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APMessageRouter *APMessageRouter::get()
{
    static std::unique_ptr<APMessageRouter> instance = std::make_unique<APMessageRouter>(ConstructorKey{});
    return instance.get();
}

APMessageRouter::APMessageRouter(ConstructorKey)
{
    // Default initialization
}

APMessageRouter::~APMessageRouter() = default;

// =============================================================================
// Item Receipt Routing
// =============================================================================

std::optional<PendingAction> APMessageRouter::route_item_receipt(int64_t item_id, const std::string &item_name,
                                                                 const std::string &sender_name)
{
    // Translate AP server item ID to local (C++) ID (no-op for player 1 / single-player)
    int64_t local_id = APArchipelagoClient::get()->remap_item_to_local(item_id);

    // Look up item ownership
    auto item_opt = APCapabilities::get()->get_item_by_id(local_id);
    if (!item_opt)
    {
        APLogger::get()->log(LogLevel::Warn, "APMessageRouter", "Unknown item ID: " + std::to_string(item_id));
        return std::nullopt;
    }

    const auto &item = *item_opt;

    // Check if item has an action to execute
    if (item.action.empty())
    {
        APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                             "Item received (no action, counting at receipt): " + item_name);

        // Count immediately — no action means nothing to confirm later
        APStateManager::get()->increment_item_progression_count(local_id);
        // Guard: don't overwrite the session file before load_state() has run.
        // Items replayed by the AP server on reconnect arrive during CONNECTING,
        // before handle_syncing() loads the persisted checked_locations.
        if (APStateManager::get()->is_loaded())
            APStateManager::get()->save_state();

        // Notify owning mod (+ opt-in subscribers) so Lua on_item_received fires
        send_item_received(local_id, item_name, sender_name);

        // Recompute tracker so (Item: X) logic nodes reflect the newly received item
        broadcast_tracker_update();

        return std::nullopt;
    }

    // Resolve arguments
    auto resolved_args = resolve_arguments(item);

    // Create pending action
    PendingAction pending;
    pending.mod_id = item.mod_id;
    pending.item_id = local_id;
    pending.item_name = item_name;
    pending.action = item.action;
    pending.resolved_args = resolved_args;
    pending.started_at = std::chrono::steady_clock::now();

    // Send EXECUTE_ACTION message to owning mod
    IPCMessage msg;
    msg.type = IPCMessageType::EXECUTE_ACTION;
    msg.source = IPCTarget::FRAMEWORK;
    msg.target = item.mod_id;

    nlohmann::json args_json = nlohmann::json::array();
    for (const auto &arg : resolved_args)
    {
        args_json.push_back({{"name", arg.name}, {"type", arg_type_to_string(arg.type)}, {"value", arg.value}});
    }

    msg.payload = {{"item_id", local_id},
                   {"item_name", item_name},
                   {"action", item.action},
                   {"args", args_json},
                   {"sender", sender_name}};

    APIPCServer::get()->send_message(item.mod_id, msg);

    APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                         "Routed item to " + item.mod_id + ": " + item_name + " (action: " + item.action + ")");

    return pending;
}

std::vector<ActionArg> APMessageRouter::resolve_arguments(const ItemOwnership &item)
{
    std::vector<ActionArg> resolved;
    resolved.reserve(item.args.size());

    for (const auto &arg : item.args)
    {
        ActionArg resolved_arg;
        resolved_arg.name = arg.name;
        resolved_arg.type = arg.type;

        // Check for special placeholders
        if (arg.value.is_string())
        {
            std::string val = arg.value.get<std::string>();

            if (val == "<GET_ITEM_ID>")
            {
                resolved_arg.value = item.item_id;
            }
            else if (val == "<GET_ITEM_NAME>")
            {
                resolved_arg.value = item.item_name;
            }
            else if (val == "<GET_PROGRESSION_COUNT>")
            {
                int count = APStateManager::get()->get_item_progression_count(item.item_id);
                resolved_arg.value = count;
            }
            else
            {
                resolved_arg.value = arg.value;
            }
        }
        else
        {
            resolved_arg.value = arg.value;
        }

        resolved.push_back(resolved_arg);
    }

    return resolved;
}

// =============================================================================
// Location Check Routing
// =============================================================================

int64_t APMessageRouter::route_location_check(const std::string &mod_id, const std::string &location_name, int instance)
{
    // Look up location ID
    int64_t location_id = APCapabilities::get()->get_location_id(mod_id, location_name, instance);
    if (location_id == 0)
    {
        bool looks_like_id = !location_name.empty() &&
                             location_name.find_first_not_of("0123456789") == std::string::npos;
        std::string hint = looks_like_id
                               ? " (looks like a location ID — pass integer directly to check_location)"
                               : "";
        APLogger::get()->log(LogLevel::Warn, "APMessageRouter",
                             "Unknown location: " + mod_id + "/" + location_name + " #" +
                             std::to_string(instance) + hint);
        return 0;
    }

    // Check if already checked
    if (APStateManager::get()->is_location_checked(location_id))
    {
        APLogger::get()->log(LogLevel::Debug, "APMessageRouter", "Location already checked: " + location_name);
        return 0;
    }

    // Mark as checked
    APStateManager::get()->add_checked_location(location_id);

    // Send to AP server
    APArchipelagoClient::get()->send_location_checks({location_id});

    // Persist state immediately
    APStateManager::get()->save_state();

    APLogger::get()->log(LogLevel::Info, "APMessageRouter",
                         "Location checked: " + location_name + " (ID: " + std::to_string(location_id) + ")");

    // Recompute tracker after location checked
    broadcast_tracker_update();

    return location_id;
}

int64_t APMessageRouter::route_location_check_by_id(const std::string &mod_id, int64_t location_id)
{
    auto loc = APCapabilities::get()->get_location_by_id(location_id);
    if (!loc.has_value())
    {
        APLogger::get()->log(LogLevel::Warn, "APMessageRouter",
                             "check_location_by_id: unknown ID " + std::to_string(location_id) +
                             " from " + mod_id);
        return 0;
    }

    if (loc->mod_id != mod_id)
    {
        APLogger::get()->log(LogLevel::Warn, "APMessageRouter",
                             "check_location_by_id: ID " + std::to_string(location_id) +
                             " belongs to " + loc->mod_id + ", not " + mod_id);
        return 0;
    }

    if (APStateManager::get()->is_location_checked(location_id))
    {
        APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                             "Location already checked: " + loc->location_name);
        return 0;
    }

    APStateManager::get()->add_checked_location(location_id);
    APArchipelagoClient::get()->send_location_checks({location_id});
    APStateManager::get()->save_state();

    APLogger::get()->log(LogLevel::Info, "APMessageRouter",
                         "Location checked: " + loc->location_name +
                         " (ID: " + std::to_string(location_id) + ")");

    broadcast_tracker_update();
    return location_id;
}

void APMessageRouter::route_location_checks(const std::vector<int64_t> &location_ids)
{
    std::vector<int64_t> new_checks;

    for (int64_t id : location_ids)
    {
        if (!APStateManager::get()->is_location_checked(id))
        {
            APStateManager::get()->add_checked_location(id);
            new_checks.push_back(id);
        }
    }

    if (!new_checks.empty())
    {
        APArchipelagoClient::get()->send_location_checks(new_checks);
        APStateManager::get()->save_state();

        // Recompute tracker after location checks
        broadcast_tracker_update();
    }
}

// =============================================================================
// Location Scout Routing
// =============================================================================

std::vector<int64_t> APMessageRouter::route_location_scouts(const std::string &mod_id,
                                                            const std::vector<std::string> &location_names,
                                                            bool create_hints)
{
    std::vector<int64_t> location_ids;

    for (const auto &name : location_names)
    {
        int64_t id = APCapabilities::get()->get_location_id(mod_id, name, 1);
        if (id != 0)
        {
            location_ids.push_back(id);
        }
    }

    if (!location_ids.empty())
    {
        // Store pending scout request
        {
            std::lock_guard<std::mutex> lock(scout_mutex_);
            for (int64_t id : location_ids)
            {
                pending_scouts_[id] = mod_id;
            }
        }

        APArchipelagoClient::get()->send_location_scouts(location_ids, create_hints);
    }

    return location_ids;
}

void APMessageRouter::route_scout_results(const std::string &mod_id, const std::vector<ScoutResult> &results)
{
    if (results.empty())
    {
        return;
    }

    IPCMessage msg;
    msg.type = "scout_results";
    msg.source = IPCTarget::FRAMEWORK;
    msg.target = mod_id;

    nlohmann::json results_json = nlohmann::json::array();
    for (const auto &result : results)
    {
        results_json.push_back({{"location_id", result.location_id},
                                {"item_id", result.item_id},
                                {"item_name", result.item_name},
                                {"player_name", result.player_name}});
    }

    msg.payload = {{"results", results_json}};

    APIPCServer::get()->send_message(mod_id, msg);
}

// =============================================================================
// Action Result Handling
// =============================================================================

void APMessageRouter::handle_action_result(const std::string &mod_id, const ActionResult &result)
{
    if (result.success)
    {
        APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                             "Action succeeded for " + mod_id + ": " + result.item_name);

        // Update progression count
        if (result.item_id != 0)
        {
            APStateManager::get()->increment_item_progression_count(result.item_id);
            APStateManager::get()->save_state();

            // Recompute tracker after item progression change
            broadcast_tracker_update();
        }
    }
    else
    {
        APLogger::get()->log(LogLevel::Warn, "APMessageRouter",
                             "Action failed for " + mod_id + ": " + result.item_name + " - " + result.error);
    }
}

// =============================================================================
// Lifecycle & Error Broadcasting
// =============================================================================

void APMessageRouter::broadcast_lifecycle(LifecycleState state, const std::string &message)
{
    IPCMessage msg;
    msg.type = IPCMessageType::LIFECYCLE;
    msg.source = IPCTarget::FRAMEWORK;
    msg.target = IPCTarget::BROADCAST;
    msg.payload = {{"state", lifecycle_state_to_string(state)}, {"message", message}};

    APIPCServer::get()->broadcast(msg);

    APLogger::get()->log(LogLevel::Info, "APMessageRouter",
                         "Lifecycle -> " + lifecycle_state_to_string(state) + (message.empty() ? "" : ": " + message));
}

void APMessageRouter::broadcast_error(const std::string &code, const std::string &message, const std::string &details)
{
    IPCMessage msg;
    msg.type = IPCMessageType::ERROR_MSG;
    msg.source = IPCTarget::FRAMEWORK;
    msg.target = IPCTarget::BROADCAST;
    msg.payload = {{"code", code}, {"message", message}, {"details", details}};

    APIPCServer::get()->broadcast(msg);

    APLogger::get()->log(LogLevel::Error, "APMessageRouter",
                         "Error [" + code + "]: " + message + (details.empty() ? "" : " (" + details + ")"));
}

void APMessageRouter::broadcast_ap_message(const std::string &type, const std::string &message)
{
    IPCMessage msg;
    msg.type = IPCMessageType::AP_MESSAGE;
    msg.source = IPCTarget::FRAMEWORK;
    msg.target = IPCTarget::BROADCAST;
    msg.payload = {{"type", type}, {"message", message}};

    APIPCServer::get()->broadcast(msg);
}

// =============================================================================
// Tracker Broadcasting
// =============================================================================

void APMessageRouter::broadcast_tracker_update()
{
    auto *tracker = APTrackerEngine::get();
    if (!tracker->is_initialized())
        return;

    if (tracker->has_subscribers())
    {
        auto update = tracker->compute_update();
        auto update_json = update.to_json();

        auto subscribers = tracker->get_subscribers();
        for (const auto &mod_id : subscribers)
        {
            IPCMessage msg;
            msg.type = IPCMessageType::TRACKER_UPDATE;
            msg.source = IPCTarget::FRAMEWORK;
            msg.target = mod_id;
            msg.payload = update_json;

            APIPCServer::get()->send_message(mod_id, msg);
        }

        APLogger::get()->log(LogLevel::Trace, "APMessageRouter",
                             "Tracker update broadcast to " + std::to_string(subscribers.size()) + " subscriber(s)");
    }

    check_and_send_goal_completion();
}

void APMessageRouter::check_and_send_goal_completion()
{
    if (goal_sent_.load())
        return;

    auto *tracker = APTrackerEngine::get();
    if (!tracker->is_initialized())
        return;
    bool goal_achieved = false;

    if (tracker->is_no_goal_mode())
    {
        // Completion = all in-logic locations checked
        auto ool_ids = tracker->get_out_of_logic_location_ids();
        const auto checked = APStateManager::get()->get_checked_locations();
        bool all_checked = true;
        for (const auto &loc : APCapabilities::get()->get_all_locations())
        {
            if (ool_ids.count(loc.location_id))
                continue; // skip out-of-logic (pruned at generation)
            if (!checked.count(loc.location_id))
            {
                all_checked = false;
                break;
            }
        }
        goal_achieved = all_checked;
    }
    else
    {
        auto active_goal = tracker->get_active_goal();
        if (!active_goal.has_value() || active_goal->logic.empty())
            return;

        // Parse and evaluate goal logic against current item state (item-only logic)
        auto node = parse_logic(active_goal->logic);
        node = evaluate_options(node, {}); // goals have no (Option:) nodes — pass empty map
        node = simplify(node);

        TrackerState eval_state;
        auto counts = APStateManager::get()->get_all_item_progression_counts();
        auto *caps = APCapabilities::get();
        for (const auto &[id, count] : counts)
        {
            // Convert item ID -> name for evaluate_bool (TrackerState uses names)
            auto item_opt = caps->get_item_by_id(id);
            if (item_opt)
                eval_state.received_items[item_opt->item_name] = count;
        }

        goal_achieved = evaluate_bool(node, eval_state);
    }

    if (!goal_achieved)
        return;

    // Atomic race guard — only one thread sends the goal status
    if (goal_sent_.exchange(true))
        return;

    APArchipelagoClient::get()->send_status_update(ClientStatus::Goal);

    auto active_goal = tracker->get_active_goal();
    std::string label = active_goal.has_value()
                            ? "'" + active_goal->name + "' — " + active_goal->display
                            : "all-locations (" + tracker->get_no_goal_label() + ")";
    APLogger::get()->log(LogLevel::Info, "APMessageRouter",
                         "Goal achieved: " + label + " — status update sent to AP server");
}

void APMessageRouter::reset_goal_sent()
{
    goal_sent_.store(false);
}

// =============================================================================
// Item Notification & Subscription
// =============================================================================

void APMessageRouter::send_item_received(int64_t item_id, const std::string &item_name,
                                         const std::string &sender)
{
    std::unordered_set<std::string> recipients;

    // Always: owning mod
    auto ownership = APCapabilities::get()->get_item_by_id(item_id);
    if (ownership.has_value())
        recipients.insert(ownership->mod_id);

    // Opt-in: all-items subscribers + specific item subscribers
    {
        std::lock_guard<std::mutex> lock(item_subscription_mutex_);
        for (const auto &sub : all_item_subscribers_)
            recipients.insert(sub);
        auto it = item_id_subscribers_.find(item_id);
        if (it != item_id_subscribers_.end())
            for (const auto &sub : it->second)
                recipients.insert(sub);
    }

    IPCMessage msg;
    msg.type    = IPCMessageType::ITEM_RECEIVED;
    msg.source  = IPCTarget::FRAMEWORK;
    msg.payload = {{"item_id", item_id}, {"item_name", item_name}, {"sender", sender}};

    for (const auto &recipient : recipients)
    {
        msg.target = recipient;
        APIPCServer::get()->send_message(recipient, msg);
    }

    APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                         "ITEM_RECEIVED sent for '" + item_name + "' to " +
                         std::to_string(recipients.size()) + " recipient(s)");
}

void APMessageRouter::subscribe_items(const std::string &mod_id,
                                      const std::vector<int64_t> &item_ids)
{
    std::lock_guard<std::mutex> lock(item_subscription_mutex_);
    for (int64_t id : item_ids)
    {
        // Guard: skip own-mod items (always delivered automatically)
        auto ownership = APCapabilities::get()->get_item_by_id(id);
        if (ownership.has_value() && ownership->mod_id == mod_id)
            continue;
        item_id_subscribers_[id].insert(mod_id);
    }
    APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                         mod_id + " subscribed to " + std::to_string(item_ids.size()) + " item(s)");
}

void APMessageRouter::subscribe_all_items(const std::string &mod_id)
{
    std::lock_guard<std::mutex> lock(item_subscription_mutex_);
    all_item_subscribers_.insert(mod_id);
    APLogger::get()->log(LogLevel::Debug, "APMessageRouter",
                         mod_id + " subscribed to all items");
}

void APMessageRouter::unsubscribe_items(const std::string &mod_id,
                                        const std::vector<int64_t> &item_ids)
{
    std::lock_guard<std::mutex> lock(item_subscription_mutex_);
    for (int64_t id : item_ids)
    {
        auto it = item_id_subscribers_.find(id);
        if (it != item_id_subscribers_.end())
            it->second.erase(mod_id);
    }
}

void APMessageRouter::unsubscribe_all_items(const std::string &mod_id)
{
    std::lock_guard<std::mutex> lock(item_subscription_mutex_);
    all_item_subscribers_.erase(mod_id);
}

} // namespace ap
