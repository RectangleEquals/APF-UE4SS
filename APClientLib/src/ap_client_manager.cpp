#include "ap_client_manager.h"
#include "ap_action_executor.h"
#include "ap_callbacks.h"
#include "ap_config.h"
#include "ap_database.h"
#include "ap_ipc_client.h"
#include "ap_logger.h"

#include <sol/sol.hpp>
#include <sstream>
#include <thread>

namespace ap::client
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APClientManager *APClientManager::get()
{
    static std::unique_ptr<APClientManager> instance = std::make_unique<APClientManager>(ConstructorKey{});
    return instance.get();
}

APClientManager::APClientManager(ConstructorKey)
{
    // Default initialization
}

APClientManager::~APClientManager()
{
    shutdown();
}

// =============================================================================
// Initialization
// =============================================================================

int APClientManager::init(lua_State *L)
{
    // 1. Cache the Lua state first (we own this)
    update_cached_lua(L);

    // Set thread name for this DLL's Lua thread
    APLogger::set_thread_name("Main");

    // 2. Register with APManagerAccessor so shared singletons can access Lua
    APManagerAccessor::set(this);

    // 3. Per-require: resolve this mod's identity by inspecting the Lua call stack.
    //    When multiple mods share one APClientLib.dll (Win64/ placement), each mod's
    //    require("APClientLib") call must receive a Lua module bound to its own manifest.
    //    load_current() uses debug.getinfo to find the requiring script's path.
    APManifest current_manifest;
    current_manifest.load_current();
    std::string current_mod_id = current_manifest.get_mod_id();
    std::string current_version = current_manifest.get_version();

    // 4. One-time setup (logger, config, IPC handlers — runs only on the first require)
    if (!initialized_)
    {
        APLogger::get()->set_prefix_tag("APClientLib");
        APConfig::get()->load_default();
        APLogger::get()->init();

        std::ostringstream oss;
        oss << "init() running on thread: " << std::this_thread::get_id() << " (name: " << APLogger::get_thread_name()
            << ")";
        APLogger::get()->log(LogLevel::Trace, "APClientManager", oss.str());

        // Retain the first mod's manifest as a fallback for handle_ipc_message reply sources
        manifest_ = current_manifest;

        // Set up IPC handlers (registered once — shared across all mods' Lua modules)
        APIPCClient::get()->set_message_handler([this](const ap::ClientIPCMessage &msg) { handle_ipc_message(msg); });
        APIPCClient::get()->set_connect_handler([]() { APCallbacks::get()->invoke_connect(); });
        APIPCClient::get()->set_disconnect_handler([]() { APCallbacks::get()->invoke_disconnect(); });

        initialized_ = true;
    }

    // 5. Log this mod's identity (logger guaranteed initialized at this point)
    if (current_mod_id.empty())
    {
        APLogger::get()->log(LogLevel::Warn, "APClientManager",
                             "Per-require manifest load failed — mod identity unknown for this require() caller");
    }
    else
    {
        APLogger::get()->log(LogLevel::Info, "APClientManager", "Module created for mod: " + current_mod_id);
    }

    // 6. Create and return the Lua module bound to this mod's identity
    return create_lua_module_impl(L, current_mod_id, current_version);
}

void APClientManager::update(lua_State *L)
{
    // Update cached Lua state
    update_cached_lua(L);

    // Name the update thread (differs from init thread — runs from RegisterHook callback)
    static bool thread_logged = false;
    if (!thread_logged)
    {
        APLogger::set_thread_name("Game");
        std::ostringstream oss;
        oss << "update() running on thread: " << std::this_thread::get_id() << " (name: " << APLogger::get_thread_name()
            << ")";
        APLogger::get()->log(LogLevel::Trace, "APClientManager", oss.str());
        thread_logged = true;
    }

    // Poll for IPC messages
    APIPCClient::get()->poll();

    // Periodically clean up stale API callbacks
    if (!pending_api_calls_.empty())
    {
        cleanup_stale_api_calls();
    }
}

void APClientManager::shutdown()
{
    if (!initialized_)
    {
        return;
    }

    APLogger::get()->log(LogLevel::Trace, "APClientManager", "Shutting down");

    // Disconnect IPC
    APIPCClient::get()->disconnect();

    // Clear callbacks and API state
    APCallbacks::get()->clear_all();
    api_callbacks_.clear();
    pending_api_calls_.clear();

    // Reset state
    current_lifecycle_state_ = "UNINITIALIZED";
    initialized_ = false;

    APLogger::get()->log(LogLevel::Info, "APClientManager", "Shutdown complete");
}

// =============================================================================
// IAPManager Interface
// =============================================================================

sol::state_view *APClientManager::get_cached_lua()
{
    return cached_lua_.get();
}

// =============================================================================
// Manifest Access
// =============================================================================

const APManifest &APClientManager::get_manifest() const
{
    return manifest_;
}

// =============================================================================
// Lifecycle State
// =============================================================================

const std::string &APClientManager::get_current_lifecycle_state() const
{
    return current_lifecycle_state_;
}

void APClientManager::set_current_lifecycle_state(const std::string &state)
{
    current_lifecycle_state_ = state;
}

// =============================================================================
// Private Methods
// =============================================================================

void APClientManager::update_cached_lua(lua_State *L)
{
    if (L)
    {
        cached_lua_ = std::make_unique<sol::state_view>(L);
    }
}

void APClientManager::handle_ipc_message(const ap::ClientIPCMessage &msg)
{
    auto *callbacks = APCallbacks::get();

    // Generic message callback
    callbacks->invoke_message(msg.type, msg.payload.dump());

    // Handle specific message types
    if (msg.type == IPCMessageType::EXECUTE_ACTION)
    {
        auto result = APActionExecutor::get()->execute_from_payload(msg.payload);

        // Invoke item received callback
        int64_t item_id = msg.payload.value("item_id", int64_t(0));
        std::string item_name = msg.payload.value("item_name", "");
        std::string sender = msg.payload.value("sender", "");

        callbacks->invoke_item_received(item_id, item_name, sender);

        // Send result back to framework
        if (APIPCClient::get()->is_connected())
        {
            ap::ClientIPCMessage response;
            response.type = IPCMessageType::ACTION_RESULT;
            response.source = manifest_.get_mod_id();
            response.target = IPCTarget::FRAMEWORK;
            response.payload = {{"item_id", result.item_id},
                                {"item_name", result.item_name},
                                {"success", result.success},
                                {"error", result.error}};
            APIPCClient::get()->send_message(response);
        }

        if (!result.success)
        {
            APLogger::get()->log(LogLevel::Error, "APClientManager",
                                 "Action failed for " + item_name + ": " + result.error);
        }
    }
    else if (msg.type == IPCMessageType::LIFECYCLE)
    {
        std::string state = msg.payload.value("state", "");
        std::string message = msg.payload.value("message", "");

        // Update cached state
        set_current_lifecycle_state(state);

        callbacks->invoke_lifecycle(state, message);

        if (state == "ACTIVE")
        {
            callbacks->invoke_state_active();
        }
        else if (state == "ERROR_STATE")
        {
            callbacks->invoke_state_error(message);
        }
    }
    else if (msg.type == IPCMessageType::REGISTRATION_RESPONSE)
    {
        bool success = msg.payload.value("success", false);
        std::string reason = msg.payload.value("reason", "");

        if (success)
        {
            callbacks->invoke_registration_success();
        }
        else
        {
            callbacks->invoke_registration_rejected(reason);
        }
    }
    else if (msg.type == IPCMessageType::ERROR_MSG)
    {
        std::string code = msg.payload.value("code", "");
        std::string error_message = msg.payload.value("message", "");

        callbacks->invoke_error(code, error_message);
    }
    else if (msg.type == IPCMessageType::COMMAND_RESPONSE)
    {
        std::string command = msg.payload.value("command", "");
        bool success = msg.payload.value("success", false);
        std::string error = msg.payload.value("error", "");
        nlohmann::json data = msg.payload.value("data", nlohmann::json::object());

        callbacks->invoke_command_response(command, success, error, data.dump());
    }
    else if (msg.type == IPCMessageType::TRACKER_SNAPSHOT)
    {
        callbacks->invoke_tracker_snapshot(msg.payload);
    }
    else if (msg.type == IPCMessageType::TRACKER_UPDATE)
    {
        callbacks->invoke_tracker_update(msg.payload);
    }
    else if (msg.type == IPCMessageType::API_CALL)
    {
        std::string func_name = msg.payload.value("function", "");
        std::string caller = msg.payload.value("_source", "");
        uint64_t call_id = msg.payload.value("call_id", uint64_t(0));
        bool wants_result = msg.payload.value("wants_result", false);

        auto it = api_callbacks_.find(func_name);
        if (it == api_callbacks_.end())
        {
            APLogger::get()->log(LogLevel::Warn, "APClientManager",
                                 "API function not found: " + func_name + " (from " + caller + ")");
            if (wants_result)
                send_api_error(caller, call_id, "Function '" + func_name + "' not registered");
            return;
        }

        // Convert JSON args to Lua and call the function
        sol::state_view *lua = get_cached_lua();
        if (!lua)
            return;

        nlohmann::json args = msg.payload.value("args", nlohmann::json::array());
        std::vector<sol::object> lua_args;
        for (const auto &arg : args)
            lua_args.push_back(APCallbacks::get()->json_to_lua(*lua, arg));

        // pcall the handler with up to 8 args
        sol::protected_function &handler = it->second;
        sol::protected_function_result result;
        switch (lua_args.size())
        {
        case 0:
            result = handler();
            break;
        case 1:
            result = handler(lua_args[0]);
            break;
        case 2:
            result = handler(lua_args[0], lua_args[1]);
            break;
        case 3:
            result = handler(lua_args[0], lua_args[1], lua_args[2]);
            break;
        case 4:
            result = handler(lua_args[0], lua_args[1], lua_args[2], lua_args[3]);
            break;
        case 5:
            result = handler(lua_args[0], lua_args[1], lua_args[2], lua_args[3], lua_args[4]);
            break;
        case 6:
            result = handler(lua_args[0], lua_args[1], lua_args[2], lua_args[3], lua_args[4], lua_args[5]);
            break;
        case 7:
            result = handler(lua_args[0], lua_args[1], lua_args[2], lua_args[3], lua_args[4], lua_args[5],
                             lua_args[6]);
            break;
        case 8:
            result = handler(lua_args[0], lua_args[1], lua_args[2], lua_args[3], lua_args[4], lua_args[5],
                             lua_args[6], lua_args[7]);
            break;
        default:
            APLogger::get()->log(LogLevel::Error, "APClientManager",
                                 "API call with too many args (" + std::to_string(lua_args.size()) +
                                     ") - max 8. Use a table parameter instead.");
            if (wants_result)
                send_api_error(caller, call_id, "Too many arguments (max 8)");
            return;
        }

        if (wants_result)
        {
            if (result.valid())
            {
                sol::object ret = result;
                nlohmann::json result_json = APCallbacks::lua_to_json(ret);
                send_api_result(caller, call_id, result_json);
            }
            else
            {
                sol::error err = result;
                send_api_error(caller, call_id, err.what());
            }
        }
    }
    else if (msg.type == IPCMessageType::API_RESULT)
    {
        uint64_t call_id = msg.payload.value("call_id", uint64_t(0));
        auto it = pending_api_calls_.find(call_id);
        if (it == pending_api_calls_.end())
            return;

        sol::protected_function callback = it->second.callback;
        pending_api_calls_.erase(it);

        sol::state_view *lua = get_cached_lua();
        if (!lua)
            return;

        if (msg.payload.contains("error"))
        {
            std::string err = msg.payload["error"];
            callback(err, sol::nil);
        }
        else
        {
            sol::object result_obj =
                APCallbacks::get()->json_to_lua(*lua, msg.payload.value("result", nlohmann::json()));
            callback(sol::nil, result_obj);
        }
    }
}

int APClientManager::create_lua_module(lua_State *L)
{
    // Fallback override — should not normally be called externally.
    // init() calls create_lua_module_impl() directly with the per-require mod identity.
    return create_lua_module_impl(L, manifest_.get_mod_id(), manifest_.get_version());
}

int APClientManager::create_lua_module_impl(lua_State *L, const std::string &current_mod_id,
                                            const std::string &current_version)
{
    sol::state_view lua(L);
    sol::table module = lua.create_table();

    auto *callbacks = APCallbacks::get();

    // =========================================================================
    // Connection Functions
    // =========================================================================

    module["connect"] = []() -> bool { return APIPCClient::get()->connect(APConfig::get()->get_game_name()); };

    module["disconnect"] = []() { APIPCClient::get()->disconnect(); };

    module["is_connected"] = []() -> bool { return APIPCClient::get()->is_connected(); };

    module["get_current_state"] = []() -> std::string { return APClientManager::get()->get_current_lifecycle_state(); };

    module["update"] = [](sol::this_state ts) {
        lua_State *L = ts.lua_state();
        APClientManager::get()->update(L);
    };

    // =========================================================================
    // Registration Functions
    // =========================================================================

    module["register_mod"] = [current_mod_id, current_version]() -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        if (current_mod_id.empty())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::REGISTER;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"mod_id", current_mod_id}, {"version", current_version}};

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Location Functions
    // =========================================================================

    module["check_location"] = [current_mod_id](const std::string &location_name, sol::optional<int> instance) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_CHECK;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"location", location_name}, {"instance", instance.value_or(1)}};

        return APIPCClient::get()->send_message(msg);
    };

    module["scout_locations"] = [current_mod_id](sol::table locations) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        std::vector<std::string> location_names;
        for (auto &pair : locations)
        {
            if (pair.second.is<std::string>())
            {
                location_names.push_back(pair.second.as<std::string>());
            }
        }

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_SCOUT;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"locations", location_names}};

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Logging Functions (delegate to APLogger)
    // =========================================================================

    module["log"] = [current_mod_id](const std::string &level, const std::string &message) {
        LogLevel log_level = log_level_from_string(level);
        APLogger::get()->log(log_level, current_mod_id, message);
    };

    // =========================================================================
    // Command Functions (Priority Client Only)
    // =========================================================================

    module["command"] = [current_mod_id](const std::string &command, sol::optional<sol::table> payload) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"command", command}};

        if (payload && payload->valid())
        {
            for (auto &pair : *payload)
            {
                std::string key = pair.first.as<std::string>();
                if (pair.second.is<std::string>())
                {
                    msg.payload["payload"][key] = pair.second.as<std::string>();
                }
                else if (pair.second.is<double>())
                {
                    msg.payload["payload"][key] = pair.second.as<double>();
                }
                else if (pair.second.is<bool>())
                {
                    msg.payload["payload"][key] = pair.second.as<bool>();
                }
                else if (pair.second.is<int>())
                {
                    msg.payload["payload"][key] = pair.second.as<int>();
                }
            }
        }

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Tracker Functions
    // =========================================================================

    module["subscribe_tracker"] = [current_mod_id]() -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::SUBSCRIBE_TRACKER;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = nlohmann::json::object();

        return APIPCClient::get()->send_message(msg);
    };

    module["unsubscribe_tracker"] = [current_mod_id]() -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::UNSUBSCRIBE_TRACKER;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = nlohmann::json::object();

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Database Functions (SQLite query interface for mods)
    // =========================================================================

    module["db_open"] = [](const std::string &path) -> bool {
        return APDatabase::get()->open(path);
    };

    module["db_query"] = [](const std::string &sql, sol::this_state ts) -> sol::object {
        auto *db = APDatabase::get();
        if (!db->is_open())
        {
            APLogger::get()->log(LogLevel::Error, "APDatabase",
                                 "db_query called but no database is open");
            return sol::make_object(ts.lua_state(), sol::nil);
        }

        auto rows = db->query(sql);
        sol::state_view lua(ts.lua_state());
        sol::table result = lua.create_table();

        for (size_t i = 0; i < rows.size(); ++i)
        {
            sol::table row_table = lua.create_table();
            for (const auto &[col, val] : rows[i])
            {
                row_table[col] = val;
            }
            result[static_cast<int>(i + 1)] = row_table;
        }

        return result;
    };

    module["db_close"] = []() {
        APDatabase::get()->close();
    };

    module["db_is_open"] = []() -> bool {
        return APDatabase::get()->is_open();
    };

    // =========================================================================
    // Cross-Mod API Functions
    // =========================================================================

    module["register_api"] = [this](sol::table api_table) {
        api_table.for_each([this](sol::object key, sol::object val) {
            if (key.is<std::string>() && val.is<sol::protected_function>())
            {
                api_callbacks_[key.as<std::string>()] = val.as<sol::protected_function>();
            }
        });
        APLogger::get()->log(LogLevel::Info, "APClientManager",
                             "API registered with " + std::to_string(api_callbacks_.size()) + " functions");
    };

    module["get_api"] = [this, current_mod_id](sol::this_state ts, const std::string &target_mod) -> sol::object {
        sol::state_view lua(ts);

        // Create proxy table with __index metamethod
        sol::table proxy = lua.create_table();
        sol::table mt = lua.create_table();

        mt[sol::meta_function::index] = [target_mod, this, current_mod_id](
                                            sol::this_state ts2, sol::table /*self*/,
                                            const std::string &func_name) -> sol::object {
            sol::state_view lua2(ts2);

            // Return a function that sends an API_CALL when invoked
            return sol::make_object(lua2, [target_mod, func_name, this, current_mod_id](sol::variadic_args va) {
                invoke_api_call(current_mod_id, target_mod, func_name, va);
            });
        };

        proxy[sol::metatable_key] = mt;
        return proxy;
    };

    module["send_to"] = [this, current_mod_id](const std::string &target_mod, sol::table payload) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"command", "send_to"}, {"payload", {{"target_mod", target_mod}}}};

        // Merge Lua table into payload
        nlohmann::json lua_payload = APCallbacks::lua_to_json(payload);
        if (lua_payload.is_object())
        {
            for (auto &[key, val] : lua_payload.items())
            {
                msg.payload["payload"][key] = val;
            }
        }

        return APIPCClient::get()->send_message(msg);
    };

    module["broadcast"] = [this, current_mod_id](sol::table payload) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = current_mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"command", "broadcast"}, {"payload", APCallbacks::lua_to_json(payload)}};

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Callback Registration (delegates to APCallbacks singleton)
    // =========================================================================

    module["on_lifecycle"] = [callbacks](sol::protected_function cb) { callbacks->set_lifecycle_callback(cb); };
    module["on_message"] = [callbacks](sol::protected_function cb) { callbacks->set_message_callback(cb); };
    module["on_error"] = [callbacks](sol::protected_function cb) { callbacks->set_error_callback(cb); };
    module["on_connect"] = [callbacks](sol::protected_function cb) { callbacks->set_connect_callback(cb); };
    module["on_disconnect"] = [callbacks](sol::protected_function cb) { callbacks->set_disconnect_callback(cb); };
    module["on_registration_success"] = [callbacks](sol::protected_function cb) {
        callbacks->set_registration_success_callback(cb);
    };
    module["on_registration_rejected"] = [callbacks](sol::protected_function cb) {
        callbacks->set_registration_rejected_callback(cb);
    };
    module["on_item_received"] = [callbacks](sol::protected_function cb) { callbacks->set_item_received_callback(cb); };
    module["on_state_active"] = [callbacks](sol::protected_function cb) { callbacks->set_state_active_callback(cb); };
    module["on_state_error"] = [callbacks](sol::protected_function cb) { callbacks->set_state_error_callback(cb); };
    module["on_command_response"] = [callbacks](sol::protected_function cb) {
        callbacks->set_command_response_callback(cb);
    };
    module["on_tracker_snapshot"] = [callbacks](sol::protected_function cb) {
        callbacks->set_tracker_snapshot_callback(cb);
    };
    module["on_tracker_update"] = [callbacks](sol::protected_function cb) {
        callbacks->set_tracker_update_callback(cb);
    };

    return sol::stack::push(L, module);
}

// =============================================================================
// Cross-Mod API Helpers
// =============================================================================

void APClientManager::invoke_api_call(const std::string &mod_id, const std::string &target_mod,
                                      const std::string &func_name, sol::variadic_args va)
{
    if (!APIPCClient::get()->is_connected())
        return;

    // Check if last arg is a callback function
    sol::optional<sol::protected_function> callback;
    size_t arg_count = va.size();
    if (arg_count > 0 && va[static_cast<int>(arg_count - 1)].get_type() == sol::type::function)
    {
        callback = va[static_cast<int>(arg_count - 1)].as<sol::protected_function>();
        arg_count--;
    }

    // Serialize args to JSON array
    nlohmann::json args_json = nlohmann::json::array();
    for (size_t i = 0; i < arg_count; ++i)
    {
        args_json.push_back(APCallbacks::lua_to_json(va[static_cast<int>(i)]));
    }

    uint64_t call_id = next_call_id_++;
    bool wants_result = callback.has_value();

    // Store pending callback (if any)
    if (wants_result)
    {
        pending_api_calls_[call_id] = {*callback, std::chrono::steady_clock::now()};
    }

    // Send API_CALL
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_CALL;
    msg.source = mod_id;
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"function", func_name},   {"args", args_json},
                   {"call_id", call_id},       {"wants_result", wants_result}};
    APIPCClient::get()->send_message(msg);
}

void APClientManager::send_api_result(const std::string &target_mod, uint64_t call_id,
                                      const nlohmann::json &result_json)
{
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_RESULT;
    msg.source = manifest_.get_mod_id();
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"call_id", call_id}, {"result", result_json}};
    APIPCClient::get()->send_message(msg);
}

void APClientManager::send_api_error(const std::string &target_mod, uint64_t call_id, const std::string &error)
{
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_RESULT;
    msg.source = manifest_.get_mod_id();
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"call_id", call_id}, {"error", error}};
    APIPCClient::get()->send_message(msg);
}

void APClientManager::cleanup_stale_api_calls()
{
    static constexpr auto TIMEOUT = std::chrono::seconds(10);
    auto now = std::chrono::steady_clock::now();

    auto it = pending_api_calls_.begin();
    while (it != pending_api_calls_.end())
    {
        if (now - it->second.created_at > TIMEOUT)
        {
            APLogger::get()->log(LogLevel::Warn, "APClientManager",
                                 "API call timed out (call_id=" + std::to_string(it->first) + ")");

            // Invoke callback with timeout error
            try
            {
                it->second.callback("Request timed out", sol::nil);
            }
            catch (const std::exception &e)
            {
                APLogger::get()->log(LogLevel::Error, "APClientManager",
                                     "Error invoking timeout callback: " + std::string(e.what()));
            }

            it = pending_api_calls_.erase(it);
        }
        else
        {
            ++it;
        }
    }
}

} // namespace ap::client