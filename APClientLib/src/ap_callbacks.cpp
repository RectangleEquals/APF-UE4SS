#include "ap_callbacks.h"
#include "ap_logger.h"

namespace ap::client
{

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

void APCallbacks::set_tracker_snapshot_callback(sol::protected_function callback)
{
    callback_tracker_snapshot_ = callback;
}

void APCallbacks::set_tracker_update_callback(sol::protected_function callback)
{
    callback_tracker_update_ = callback;
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
                                          const std::string &data_json, sol::state_view &lua)
{
    invoke_callback(callback_command_response_, "on_command_response", [&](sol::protected_function &cb) {
        sol::table result = lua.create_table();
        result["success"] = success;
        result["error"] = error;
        result["data"] = data_json;

        return cb(command, result);
    });
}

void APCallbacks::invoke_tracker_snapshot(const nlohmann::json &payload, sol::state_view &lua)
{
    invoke_callback(callback_tracker_snapshot_, "on_tracker_snapshot", [&](sol::protected_function &cb) {
        sol::object lua_table = json_to_lua(lua, payload);
        return cb(lua_table);
    });
}

void APCallbacks::invoke_tracker_update(const nlohmann::json &payload, sol::state_view &lua)
{
    invoke_callback(callback_tracker_update_, "on_tracker_update", [&](sol::protected_function &cb) {
        sol::object lua_table = json_to_lua(lua, payload);
        return cb(lua_table);
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
    callback_tracker_snapshot_.reset();
    callback_tracker_update_.reset();
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

sol::object APCallbacks::json_to_lua(sol::state_view &lua, const nlohmann::json &j)
{
    if (j.is_null())
    {
        return sol::make_object(lua.lua_state(), sol::nil);
    }
    if (j.is_boolean())
    {
        return sol::make_object(lua.lua_state(), j.get<bool>());
    }
    if (j.is_number_integer())
    {
        return sol::make_object(lua.lua_state(), j.get<int64_t>());
    }
    if (j.is_number_float())
    {
        return sol::make_object(lua.lua_state(), j.get<double>());
    }
    if (j.is_string())
    {
        return sol::make_object(lua.lua_state(), j.get<std::string>());
    }
    if (j.is_array())
    {
        sol::table tbl = lua.create_table();
        for (size_t i = 0; i < j.size(); ++i)
        {
            tbl[static_cast<int>(i + 1)] = json_to_lua(lua, j[i]);
        }
        return tbl;
    }
    if (j.is_object())
    {
        sol::table tbl = lua.create_table();
        for (const auto &[key, val] : j.items())
        {
            tbl[key] = json_to_lua(lua, val);
        }
        return tbl;
    }

    return sol::make_object(lua.lua_state(), sol::nil);
}

// =============================================================================
// Lua -> JSON Conversion
// =============================================================================

nlohmann::json APCallbacks::lua_to_json(const sol::object &obj)
{
    switch (obj.get_type())
    {
    case sol::type::nil:
    case sol::type::none:
        return nullptr;
    case sol::type::boolean:
        return obj.as<bool>();
    case sol::type::number:
        if (obj.is<int64_t>())
            return obj.as<int64_t>();
        return obj.as<double>();
    case sol::type::string:
        return obj.as<std::string>();
    case sol::type::table:
    {
        sol::table tbl = obj.as<sol::table>();

        // Detect array vs object: check if sequential integer keys 1..N
        bool is_array = true;
        size_t count = 0;
        tbl.for_each([&](sol::object key, sol::object) {
            count++;
            if (!key.is<int>() || key.as<int>() != static_cast<int>(count))
                is_array = false;
        });

        if (is_array && count > 0)
        {
            nlohmann::json arr = nlohmann::json::array();
            for (size_t i = 1; i <= count; ++i)
                arr.push_back(lua_to_json(tbl[static_cast<int>(i)]));
            return arr;
        }
        else
        {
            nlohmann::json obj_json = nlohmann::json::object();
            tbl.for_each([&](sol::object key, sol::object val) {
                if (key.is<std::string>())
                    obj_json[key.as<std::string>()] = lua_to_json(val);
                else if (key.is<int>())
                    obj_json[std::to_string(key.as<int>())] = lua_to_json(val);
            });
            return obj_json;
        }
    }
    default:
        return nullptr; // userdata, function, etc. -> null
    }
}

} // namespace ap::client
