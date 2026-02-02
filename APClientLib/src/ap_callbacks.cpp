#include "ap_callbacks.h"
#include "ap_client_manager.h"
#include "ap_logger.h"

namespace ap::client
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APCallbacks *APCallbacks::get()
{
    static std::unique_ptr<APCallbacks> instance = std::make_unique<APCallbacks>(ConstructorKey{});
    return instance.get();
}

APCallbacks::APCallbacks(ConstructorKey)
{
    // Default initialization
}

APCallbacks::~APCallbacks()
{
    clear_all();
}

// =============================================================================
// Callback Registration
// =============================================================================

void APCallbacks::set_lifecycle_callback(sol::protected_function callback)
{
    callback_lifecycle_ = callback;
}

void APCallbacks::set_message_callback(sol::protected_function callback)
{
    callback_message_ = callback;
}

void APCallbacks::set_error_callback(sol::protected_function callback)
{
    callback_error_ = callback;
}

void APCallbacks::set_connect_callback(sol::protected_function callback)
{
    callback_connect_ = callback;
}

void APCallbacks::set_disconnect_callback(sol::protected_function callback)
{
    callback_disconnect_ = callback;
}

void APCallbacks::set_registration_success_callback(sol::protected_function callback)
{
    callback_registration_success_ = callback;
}

void APCallbacks::set_registration_rejected_callback(sol::protected_function callback)
{
    callback_registration_rejected_ = callback;
}

void APCallbacks::set_item_received_callback(sol::protected_function callback)
{
    callback_item_received_ = callback;
}

void APCallbacks::set_state_active_callback(sol::protected_function callback)
{
    callback_state_active_ = callback;
}

void APCallbacks::set_state_error_callback(sol::protected_function callback)
{
    callback_state_error_ = callback;
}

void APCallbacks::set_command_response_callback(sol::protected_function callback)
{
    callback_command_response_ = callback;
}

// =============================================================================
// Callback Invocation
// =============================================================================

void APCallbacks::invoke_lifecycle(const std::string &state, const std::string &message)
{
    invoke_callback(callback_lifecycle_, "on_lifecycle",
                    [&](sol::protected_function &cb) { return cb(state, message); });
}

void APCallbacks::invoke_message(const std::string &type, const std::string &payload_json)
{
    invoke_callback(callback_message_, "on_message",
                    [&](sol::protected_function &cb) { return cb(type, payload_json); });
}

void APCallbacks::invoke_error(const std::string &code, const std::string &message)
{
    invoke_callback(callback_error_, "on_error", [&](sol::protected_function &cb) { return cb(code, message); });
}

void APCallbacks::invoke_connect()
{
    invoke_callback(callback_connect_, "on_connect", [](sol::protected_function &cb) { return cb(); });
}

void APCallbacks::invoke_disconnect()
{
    invoke_callback(callback_disconnect_, "on_disconnect", [](sol::protected_function &cb) { return cb(); });
}

void APCallbacks::invoke_registration_success()
{
    invoke_callback(callback_registration_success_, "on_registration_success",
                    [](sol::protected_function &cb) { return cb(); });
}

void APCallbacks::invoke_registration_rejected(const std::string &reason)
{
    invoke_callback(callback_registration_rejected_, "on_registration_rejected",
                    [&](sol::protected_function &cb) { return cb(reason); });
}

void APCallbacks::invoke_item_received(int64_t item_id, const std::string &item_name, const std::string &sender)
{
    invoke_callback(callback_item_received_, "on_item_received",
                    [&](sol::protected_function &cb) { return cb(item_id, item_name, sender); });
}

void APCallbacks::invoke_state_active()
{
    invoke_callback(callback_state_active_, "on_state_active", [](sol::protected_function &cb) { return cb(); });
}

void APCallbacks::invoke_state_error(const std::string &message)
{
    invoke_callback(callback_state_error_, "on_state_error", [&](sol::protected_function &cb) { return cb(message); });
}

void APCallbacks::invoke_command_response(const std::string &command, bool success, const std::string &error,
                                          const std::string &data_json)
{
    invoke_callback(callback_command_response_, "on_command_response", [&](sol::protected_function &cb) {
        sol::state_view *lua = APClientManager::get()->get_cached_lua();
        if (!lua)
            return sol::protected_function_result();

        sol::table result = lua->create_table();
        result["success"] = success;
        result["error"] = error;
        result["data"] = data_json;

        return cb(command, result);
    });
}

// =============================================================================
// Clear All Callbacks
// =============================================================================

void APCallbacks::clear_all()
{
    callback_lifecycle_.reset();
    callback_message_.reset();
    callback_error_.reset();
    callback_connect_.reset();
    callback_disconnect_.reset();
    callback_registration_success_.reset();
    callback_registration_rejected_.reset();
    callback_item_received_.reset();
    callback_state_active_.reset();
    callback_state_error_.reset();
    callback_command_response_.reset();
}

// =============================================================================
// Private Helpers
// =============================================================================

bool APCallbacks::invoke_callback(
    const std::optional<sol::protected_function> &callback, const std::string &callback_name,
    const std::function<sol::protected_function_result(sol::protected_function &)> &caller)
{
    if (!callback || !callback->valid())
    {
        return false;
    }

    try
    {
        sol::protected_function cb = *callback;
        sol::protected_function_result result = caller(cb);

        if (!result.valid())
        {
            sol::error err = result;
            APLogger::get()->log(LogLevel::Error, "APCallbacks",
                                 "Callback error in " + callback_name + ": " + err.what());
            return false;
        }
        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APCallbacks",
                             "Callback exception in " + callback_name + ": " + e.what());
        return false;
    }
}

} // namespace ap::client