#include "ap_message_router.h"
#include "ap_logger.h"

#include <nlohmann/json.hpp>
#include <mutex>
#include <chrono>

namespace ap {

class APMessageRouter::Impl {
public:
    void set_capabilities(APCapabilities* capabilities) {
        capabilities_ = capabilities;
    }

    void set_state_manager(APStateManager* state_manager) {
        state_manager_ = state_manager;
    }

    void set_ipc_send_callback(IPCSendCallback callback) {
        ipc_send_ = std::move(callback);
    }

    void set_ipc_broadcast_callback(IPCBroadcastCallback callback) {
        ipc_broadcast_ = std::move(callback);
    }

    void set_ap_location_check_callback(APLocationCheckCallback callback) {
        ap_location_check_ = std::move(callback);
    }

    void set_ap_location_scout_callback(APLocationScoutCallback callback) {
        ap_location_scout_ = std::move(callback);
    }

    std::optional<PendingAction> route_item_receipt(int64_t item_id,
                                                    const std::string& item_name,
                                                    const std::string& sender_name) {
        if (!capabilities_) {
            APLogger::instance().log(LogLevel::Error,
                "Cannot route item - capabilities not set");
            return std::nullopt;
        }

        // Look up item ownership
        auto item_opt = capabilities_->get_item_by_id(item_id);
        if (!item_opt) {
            APLogger::instance().log(LogLevel::Warn,
                "Unknown item ID: " + std::to_string(item_id));
            return std::nullopt;
        }

        const auto& item = *item_opt;

        // Check if item has an action to execute
        if (item.action.empty()) {
            APLogger::instance().log(LogLevel::Debug,
                "Item has no action: " + item_name);
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
        if (ipc_send_) {
            IPCMessage msg;
            msg.type = IPCMessageType::EXECUTE_ACTION;
            msg.source = IPCTarget::FRAMEWORK;
            msg.target = item.mod_id;

            nlohmann::json args_json = nlohmann::json::array();
            for (const auto& arg : resolved_args) {
                args_json.push_back({
                    {"name", arg.name},
                    {"type", arg_type_to_string(arg.type)},
                    {"value", arg.value}
                });
            }

            msg.payload = {
                {"item_id", item_id},
                {"item_name", item_name},
                {"action", item.action},
                {"args", args_json},
                {"sender", sender_name}
            };

            ipc_send_(item.mod_id, msg);
        }

        APLogger::instance().log(LogLevel::Debug,
            "Routed item to " + item.mod_id + ": " + item_name +
            " (action: " + item.action + ")");

        return pending;
    }

    std::vector<ActionArg> resolve_arguments(const ItemOwnership& item) {
        std::vector<ActionArg> resolved;
        resolved.reserve(item.args.size());

        for (const auto& arg : item.args) {
            ActionArg resolved_arg;
            resolved_arg.name = arg.name;
            resolved_arg.type = arg.type;

            // Check for special placeholders
            if (arg.value.is_string()) {
                std::string val = arg.value.get<std::string>();

                if (val == "<GET_ITEM_ID>") {
                    resolved_arg.value = item.item_id;
                } else if (val == "<GET_ITEM_NAME>") {
                    resolved_arg.value = item.item_name;
                } else if (val == "<GET_PROGRESSION_COUNT>") {
                    int count = 0;
                    if (state_manager_) {
                        count = state_manager_->get_item_progression_count(item.item_id);
                    }
                    resolved_arg.value = count;
                } else {
                    resolved_arg.value = arg.value;
                }
            } else {
                resolved_arg.value = arg.value;
            }

            resolved.push_back(resolved_arg);
        }

        return resolved;
    }

    int64_t route_location_check(const std::string& mod_id,
                                 const std::string& location_name,
                                 int instance) {
        if (!capabilities_) {
            APLogger::instance().log(LogLevel::Error,
                "Cannot route location check - capabilities not set");
            return 0;
        }

        // Look up location ID
        int64_t location_id = capabilities_->get_location_id(mod_id, location_name, instance);
        if (location_id == 0) {
            APLogger::instance().log(LogLevel::Warn,
                "Unknown location: " + mod_id + "/" + location_name +
                " #" + std::to_string(instance));
            return 0;
        }

        // Check if already checked
        if (state_manager_ && state_manager_->is_location_checked(location_id)) {
            APLogger::instance().log(LogLevel::Debug,
                "Location already checked: " + location_name);
            return 0;
        }

        // Mark as checked
        if (state_manager_) {
            state_manager_->add_checked_location(location_id);
        }

        // Send to AP server
        if (ap_location_check_) {
            ap_location_check_({location_id});
        }

        APLogger::instance().log(LogLevel::Info,
            "Location checked: " + location_name + " (ID: " + std::to_string(location_id) + ")");

        return location_id;
    }

    void route_location_checks(const std::vector<int64_t>& location_ids) {
        std::vector<int64_t> new_checks;

        for (int64_t id : location_ids) {
            if (state_manager_ && !state_manager_->is_location_checked(id)) {
                state_manager_->add_checked_location(id);
                new_checks.push_back(id);
            }
        }

        if (!new_checks.empty() && ap_location_check_) {
            ap_location_check_(new_checks);
        }
    }

    std::vector<int64_t> route_location_scouts(const std::string& mod_id,
                                               const std::vector<std::string>& location_names,
                                               bool create_hints) {
        std::vector<int64_t> location_ids;

        if (!capabilities_) {
            return location_ids;
        }

        for (const auto& name : location_names) {
            int64_t id = capabilities_->get_location_id(mod_id, name, 1);
            if (id != 0) {
                location_ids.push_back(id);
            }
        }

        if (!location_ids.empty() && ap_location_scout_) {
            // Store pending scout request
            {
                std::lock_guard<std::mutex> lock(scout_mutex_);
                for (int64_t id : location_ids) {
                    pending_scouts_[id] = mod_id;
                }
            }

            ap_location_scout_(location_ids, create_hints);
        }

        return location_ids;
    }

    void route_scout_results(const std::string& mod_id,
                             const std::vector<ScoutResult>& results) {
        if (!ipc_send_ || results.empty()) {
            return;
        }

        IPCMessage msg;
        msg.type = "scout_results";
        msg.source = IPCTarget::FRAMEWORK;
        msg.target = mod_id;

        nlohmann::json results_json = nlohmann::json::array();
        for (const auto& result : results) {
            results_json.push_back({
                {"location_id", result.location_id},
                {"item_id", result.item_id},
                {"item_name", result.item_name},
                {"player_name", result.player_name}
            });
        }

        msg.payload = {{"results", results_json}};

        ipc_send_(mod_id, msg);
    }

    void handle_action_result(const std::string& mod_id, const ActionResult& result) {
        if (result.success) {
            APLogger::instance().log(LogLevel::Debug,
                "Action succeeded for " + mod_id + ": " + result.item_name);

            // Update progression count
            if (state_manager_ && result.item_id != 0) {
                state_manager_->increment_item_progression_count(result.item_id);
            }
        } else {
            APLogger::instance().log(LogLevel::Warn,
                "Action failed for " + mod_id + ": " + result.item_name +
                " - " + result.error);
        }
    }

    void broadcast_lifecycle(LifecycleState state, const std::string& message) {
        if (!ipc_broadcast_) {
            return;
        }

        IPCMessage msg;
        msg.type = IPCMessageType::LIFECYCLE;
        msg.source = IPCTarget::FRAMEWORK;
        msg.target = IPCTarget::BROADCAST;
        msg.payload = {
            {"state", lifecycle_state_to_string(state)},
            {"message", message}
        };

        ipc_broadcast_(msg);

        APLogger::instance().log(LogLevel::Info,
            "Lifecycle -> " + lifecycle_state_to_string(state) +
            (message.empty() ? "" : ": " + message));
    }

    void broadcast_error(const std::string& code,
                         const std::string& message,
                         const std::string& details) {
        if (!ipc_broadcast_) {
            return;
        }

        IPCMessage msg;
        msg.type = IPCMessageType::ERROR_MSG;
        msg.source = IPCTarget::FRAMEWORK;
        msg.target = IPCTarget::BROADCAST;
        msg.payload = {
            {"code", code},
            {"message", message},
            {"details", details}
        };

        ipc_broadcast_(msg);

        APLogger::instance().log(LogLevel::Error,
            "Error [" + code + "]: " + message +
            (details.empty() ? "" : " (" + details + ")"));
    }

    void broadcast_ap_message(const std::string& type, const std::string& message) {
        if (!ipc_broadcast_) {
            return;
        }

        IPCMessage msg;
        msg.type = IPCMessageType::AP_MESSAGE;
        msg.source = IPCTarget::FRAMEWORK;
        msg.target = IPCTarget::BROADCAST;
        msg.payload = {
            {"type", type},
            {"message", message}
        };

        ipc_broadcast_(msg);
    }

private:
    APCapabilities* capabilities_ = nullptr;
    APStateManager* state_manager_ = nullptr;

    IPCSendCallback ipc_send_;
    IPCBroadcastCallback ipc_broadcast_;
    APLocationCheckCallback ap_location_check_;
    APLocationScoutCallback ap_location_scout_;

    std::mutex scout_mutex_;
    std::unordered_map<int64_t, std::string> pending_scouts_;  // location_id -> mod_id
};

// =============================================================================
// Public API
// =============================================================================

APMessageRouter::APMessageRouter() : impl_(std::make_unique<Impl>()) {}
APMessageRouter::~APMessageRouter() = default;

void APMessageRouter::set_capabilities(APCapabilities* capabilities) {
    impl_->set_capabilities(capabilities);
}

void APMessageRouter::set_state_manager(APStateManager* state_manager) {
    impl_->set_state_manager(state_manager);
}

void APMessageRouter::set_ipc_send_callback(IPCSendCallback callback) {
    impl_->set_ipc_send_callback(std::move(callback));
}

void APMessageRouter::set_ipc_broadcast_callback(IPCBroadcastCallback callback) {
    impl_->set_ipc_broadcast_callback(std::move(callback));
}

void APMessageRouter::set_ap_location_check_callback(APLocationCheckCallback callback) {
    impl_->set_ap_location_check_callback(std::move(callback));
}

void APMessageRouter::set_ap_location_scout_callback(APLocationScoutCallback callback) {
    impl_->set_ap_location_scout_callback(std::move(callback));
}

std::optional<PendingAction> APMessageRouter::route_item_receipt(int64_t item_id,
                                                                 const std::string& item_name,
                                                                 const std::string& sender_name) {
    return impl_->route_item_receipt(item_id, item_name, sender_name);
}

std::vector<ActionArg> APMessageRouter::resolve_arguments(const ItemOwnership& item) {
    return impl_->resolve_arguments(item);
}

int64_t APMessageRouter::route_location_check(const std::string& mod_id,
                                              const std::string& location_name,
                                              int instance) {
    return impl_->route_location_check(mod_id, location_name, instance);
}

void APMessageRouter::route_location_checks(const std::vector<int64_t>& location_ids) {
    impl_->route_location_checks(location_ids);
}

std::vector<int64_t> APMessageRouter::route_location_scouts(const std::string& mod_id,
                                                            const std::vector<std::string>& location_names,
                                                            bool create_hints) {
    return impl_->route_location_scouts(mod_id, location_names, create_hints);
}

void APMessageRouter::route_scout_results(const std::string& mod_id,
                                          const std::vector<ScoutResult>& results) {
    impl_->route_scout_results(mod_id, results);
}

void APMessageRouter::handle_action_result(const std::string& mod_id, const ActionResult& result) {
    impl_->handle_action_result(mod_id, result);
}

void APMessageRouter::broadcast_lifecycle(LifecycleState state, const std::string& message) {
    impl_->broadcast_lifecycle(state, message);
}

void APMessageRouter::broadcast_error(const std::string& code,
                                      const std::string& message,
                                      const std::string& details) {
    impl_->broadcast_error(code, message, details);
}

void APMessageRouter::broadcast_ap_message(const std::string& type, const std::string& message) {
    impl_->broadcast_ap_message(type, message);
}

} // namespace ap
