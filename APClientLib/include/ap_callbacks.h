#pragma once

#include "ap_exports.h"

#include <functional>
#include <nlohmann/json.hpp>
#include <optional>
#include <sol/sol.hpp>
#include <string>

namespace ap::client
{

/**
 * @brief Singleton managing Lua callbacks for APClientLib.
 *
 * The APCallbacks singleton owns all registered Lua callbacks and provides
 * methods to invoke them safely. This separates callback management from
 * the manager's core responsibilities.
 *
 * Singleton Pattern: Pass-Key + Meyers
 */
class AP_API APCallbacks
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APCallbacks;
        explicit ConstructorKey() = default;
    };

    explicit APCallbacks(ConstructorKey);
    ~APCallbacks();

    APCallbacks(const APCallbacks &) = delete;
    APCallbacks &operator=(const APCallbacks &) = delete;

    static APCallbacks *get();

    // =========================================================================
    // Callback Registration
    // =========================================================================

    void set_lifecycle_callback(sol::protected_function callback);
    void set_message_callback(sol::protected_function callback);
    void set_error_callback(sol::protected_function callback);
    void set_connect_callback(sol::protected_function callback);
    void set_disconnect_callback(sol::protected_function callback);
    void set_registration_success_callback(sol::protected_function callback);
    void set_registration_rejected_callback(sol::protected_function callback);
    void set_item_received_callback(sol::protected_function callback);
    void set_state_active_callback(sol::protected_function callback);
    void set_state_error_callback(sol::protected_function callback);
    void set_command_response_callback(sol::protected_function callback);
    void set_tracker_snapshot_callback(sol::protected_function callback);
    void set_tracker_update_callback(sol::protected_function callback);

    // =========================================================================
    // Callback Invocation
    // =========================================================================

    void invoke_lifecycle(const std::string &state, const std::string &message);
    void invoke_message(const std::string &type, const std::string &payload_json);
    void invoke_error(const std::string &code, const std::string &message);
    void invoke_connect();
    void invoke_disconnect();
    void invoke_registration_success();
    void invoke_registration_rejected(const std::string &reason);
    void invoke_item_received(int64_t item_id, const std::string &item_name, const std::string &sender);
    void invoke_state_active();
    void invoke_state_error(const std::string &message);
    void invoke_command_response(const std::string &command, bool success, const std::string &error,
                                 const std::string &data_json);
    void invoke_tracker_snapshot(const nlohmann::json &payload);
    void invoke_tracker_update(const nlohmann::json &payload);

    // =========================================================================
    // Clear All Callbacks
    // =========================================================================

    void clear_all();

  private:
    // Helper to invoke callbacks safely
    bool invoke_callback(const std::optional<sol::protected_function> &callback, const std::string &callback_name,
                         const std::function<sol::protected_function_result(sol::protected_function &)> &caller);

    // Callback storage
    std::optional<sol::protected_function> callback_lifecycle_;
    std::optional<sol::protected_function> callback_message_;
    std::optional<sol::protected_function> callback_error_;
    std::optional<sol::protected_function> callback_connect_;
    std::optional<sol::protected_function> callback_disconnect_;
    std::optional<sol::protected_function> callback_registration_success_;
    std::optional<sol::protected_function> callback_registration_rejected_;
    std::optional<sol::protected_function> callback_item_received_;
    std::optional<sol::protected_function> callback_state_active_;
    std::optional<sol::protected_function> callback_state_error_;
    std::optional<sol::protected_function> callback_command_response_;
    std::optional<sol::protected_function> callback_tracker_snapshot_;
    std::optional<sol::protected_function> callback_tracker_update_;

    /// Recursively convert a JSON value to a Lua object
    sol::object json_to_lua(sol::state_view &lua, const nlohmann::json &j);
};

} // namespace ap::client