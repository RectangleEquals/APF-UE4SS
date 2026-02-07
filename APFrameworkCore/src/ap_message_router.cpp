#include "ap_message_router.h"
#include "ap_capabilities.h"
#include "ap_client.h"
#include "ap_ipc_server.h"
#include "ap_logger.h"
#include "ap_state_manager.h"

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
    // Look up item ownership
    auto item_opt = APCapabilities::get()->get_item_by_id(item_id);
    if (!item_opt)
    {
        APLogger::get()->log(LogLevel::Warn, "Unknown item ID: " + std::to_string(item_id));
        return std::nullopt;
    }

    const auto &item = *item_opt;

    // Check if item has an action to execute
    if (item.action.empty())
    {
        APLogger::get()->log(LogLevel::Debug, "Item has no action: " + item_name);
        return std::nullopt;
    }

    // Resolve arguments
    auto resolved_args = resolve_arguments(item);

    // Create pending action
    PendingAction pending;
    pending.mod_id = item.mod_id;
    pending.item_id = item_id;
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

    msg.payload = {{"item_id", item_id},
                   {"item_name", item_name},
                   {"action", item.action},
                   {"args", args_json},
                   {"sender", sender_name}};

    APIPCServer::get()->send_message(item.mod_id, msg);

    APLogger::get()->log(LogLevel::Debug,
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
        APLogger::get()->log(LogLevel::Warn,
                             "Unknown location: " + mod_id + "/" + location_name + " #" + std::to_string(instance));
        return 0;
    }

    // Check if already checked
    if (APStateManager::get()->is_location_checked(location_id))
    {
        APLogger::get()->log(LogLevel::Debug, "Location already checked: " + location_name);
        return 0;
    }

    // Mark as checked
    APStateManager::get()->add_checked_location(location_id);

    // Send to AP server
    APArchipelagoClient::get()->send_location_checks({location_id});

    APLogger::get()->log(LogLevel::Info,
                         "Location checked: " + location_name + " (ID: " + std::to_string(location_id) + ")");

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
        APLogger::get()->log(LogLevel::Debug, "Action succeeded for " + mod_id + ": " + result.item_name);

        // Update progression count
        if (result.item_id != 0)
        {
            APStateManager::get()->increment_item_progression_count(result.item_id);
        }
    }
    else
    {
        APLogger::get()->log(LogLevel::Warn,
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

    APLogger::get()->log(LogLevel::Info,
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

    APLogger::get()->log(LogLevel::Error,
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

} // namespace ap
