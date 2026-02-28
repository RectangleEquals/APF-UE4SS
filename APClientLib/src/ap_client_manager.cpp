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
    // Set thread name for this DLL's Lua thread
    APLogger::set_thread_name("Main");

    // Store lua state BEFORE APManagerAccessor::set(this) so that get_cached_lua()
    // returns a valid state when load_current() calls APPathUtil below.
    // (contexts_ is empty at this point — temp_lua_ is the fallback for that window.)
    temp_lua_ = std::make_unique<sol::state_view>(L);

    // Register with APManagerAccessor so shared singletons (APPathUtil, APLogger)
    // can access a Lua state via get_cached_lua() → temp_lua_ (or first context's lua).
    APManagerAccessor::set(this);

    // Per-require: resolve this mod's identity by inspecting the Lua call stack.
    // When multiple mods share one APClientLib.dll (Win64/ placement), each mod's
    // require("APClientLib") call must receive a module bound to its own manifest.
    // load_current() uses debug.getinfo to find the requiring script's path.
    APManifest current_manifest;
    current_manifest.load_current();
    const std::string current_mod_id = current_manifest.get_mod_id();
    const std::string current_version = current_manifest.get_version();

    // One-time setup (logger, config, IPC handlers — runs only on the first require)
    if (!initialized_)
    {
        APLogger::get()->set_prefix_tag("APClientLib");
        APConfig::get()->load_default();
        APLogger::get()->init();

        std::ostringstream oss;
        oss << "init() running on thread: " << std::this_thread::get_id() << " (name: " << APLogger::get_thread_name()
            << ")";
        APLogger::get()->log(LogLevel::Trace, "APClientManager", oss.str());

        // Retain the first mod's manifest as a fallback for ACTION_RESULT reply sources
        manifest_ = current_manifest;

        initialized_ = true;
    }

    // Create a new context for this mod
    auto ctx = std::make_unique<APClientContext>();
    ctx->mod_id = current_mod_id;
    ctx->version = current_version;
    ctx->cached_lua = std::make_unique<sol::state_view>(L);

    APClientContext *ctx_ptr = ctx.get();
    contexts_.push_back(std::move(ctx));

    // Create a dedicated IPC connection for this mod.
    // Each connection is renamed by the server on REGISTER to the mod's ID, so
    // all subsequent messages are correctly attributed to the right mod.
    ctx_ptr->ipc_client = ap::APIPCClient::create_instance();
    ctx_ptr->ipc_client->set_message_handler([this, ctx_ptr](const ap::ClientIPCMessage &msg) {
        handle_ipc_message_for_context(ctx_ptr, msg);
    });
    ctx_ptr->ipc_client->set_connect_handler([ctx_ptr]() { ctx_ptr->callbacks.invoke_connect(); });
    ctx_ptr->ipc_client->set_disconnect_handler([ctx_ptr]() {
        ctx_ptr->lifecycle_state = "UNINITIALIZED";
        ctx_ptr->callbacks.invoke_disconnect();
    });

    // Log this mod's identity (logger guaranteed initialized at this point)
    if (current_mod_id.empty())
    {
        APLogger::get()->log(LogLevel::Warn, "APClientManager",
                             "Per-require manifest load failed — mod identity unknown for this require() caller");
    }
    else
    {
        APLogger::get()->log(LogLevel::Info, "APClientManager", "Module created for mod: " + current_mod_id);
    }

    // Create and return the Lua module bound to this mod's context
    return create_lua_module_impl(L, ctx_ptr);
}

void APClientManager::update()
{
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

    // Poll all per-context IPC connections
    for (auto &ctx : contexts_)
    {
        if (ctx->ipc_client)
            ctx->ipc_client->poll();
    }

    // Periodically clean up stale pending API calls for each context
    for (auto &ctx : contexts_)
    {
        if (!ctx->pending_api_calls.empty())
            cleanup_stale_api_calls(*ctx);
    }
}

void APClientManager::shutdown()
{
    if (!initialized_)
    {
        return;
    }

    APLogger::get()->log(LogLevel::Trace, "APClientManager", "Shutting down");

    // Disconnect all per-context IPC connections
    for (auto &ctx : contexts_)
    {
        if (ctx->ipc_client)
            ctx->ipc_client->disconnect();
    }

    // Clear all per-context callbacks and API state
    for (auto &ctx : contexts_)
    {
        ctx->callbacks.clear_all();
        ctx->api_callbacks.clear();
        ctx->pending_api_calls.clear();
    }

    initialized_ = false;

    APLogger::get()->log(LogLevel::Info, "APClientManager", "Shutdown complete");
}

// =============================================================================
// IAPManager Interface
// =============================================================================

sol::state_view *APClientManager::get_cached_lua()
{
    // Always return temp_lua_ — set to the current init()'s L at the start of every
    // init() call, so during any mod's init() this holds that mod's Lua state.
    // After all inits complete, holds the last mod's L (valid for APPathUtil/APLogger).
    return temp_lua_.get();
}

// =============================================================================
// Manifest Access
// =============================================================================

const APManifest &APClientManager::get_manifest() const
{
    return manifest_;
}

// =============================================================================
// Private Methods
// =============================================================================

APClientContext *APClientManager::find_context(const std::string &mod_id)
{
    for (auto &ctx : contexts_)
    {
        if (ctx->mod_id == mod_id)
            return ctx.get();
    }
    return nullptr;
}

int APClientManager::create_lua_module(lua_State *L)
{
    // Fallback override — should not normally be called externally.
    // init() calls create_lua_module_impl() directly with the per-require context.
    if (!contexts_.empty())
        return create_lua_module_impl(L, contexts_.back().get());
    return 0;
}

// =============================================================================
// Per-Context IPC Message Dispatch
// =============================================================================

void APClientManager::handle_ipc_message_for_context(APClientContext *ctx, const ap::ClientIPCMessage &msg)
{
    // Generic message callback
    ctx->callbacks.invoke_message(msg.type, msg.payload.dump());

    if (msg.type == IPCMessageType::EXECUTE_ACTION)
    {
        int64_t item_id = msg.payload.value("item_id", int64_t(0));
        std::string item_name = msg.payload.value("item_name", "");
        std::string sender = msg.payload.value("sender", "");

        // Only the framework mod (first context) executes actions and sends ACTION_RESULT.
        // This prevents duplicate execution if the server broadcasts to all connections.
        if (!contexts_.empty() && ctx == contexts_.front().get())
        {
            auto result = APActionExecutor::get()->execute_from_payload(msg.payload);
            if (!result.success)
            {
                APLogger::get()->log(LogLevel::Error, "APClientManager",
                                     "Action failed for " + item_name + ": " + result.error);
            }
            if (ctx->ipc_client->is_connected())
            {
                ap::ClientIPCMessage response;
                response.type = IPCMessageType::ACTION_RESULT;
                response.source = ctx->mod_id;
                response.target = IPCTarget::FRAMEWORK;
                response.payload = {{"item_id", result.item_id},
                                    {"item_name", result.item_name},
                                    {"success", result.success},
                                    {"error", result.error}};
                ctx->ipc_client->send_message(response);
            }
        }

        ctx->callbacks.invoke_item_received(item_id, item_name, sender);
    }
    else if (msg.type == IPCMessageType::LIFECYCLE)
    {
        std::string state = msg.payload.value("state", "");
        std::string message = msg.payload.value("message", "");

        ctx->lifecycle_state = state;
        ctx->callbacks.invoke_lifecycle(state, message);

        if (state == "ACTIVE")
            ctx->callbacks.invoke_state_active();
        else if (state == "ERROR_STATE")
            ctx->callbacks.invoke_state_error(message);
    }
    else if (msg.type == IPCMessageType::REGISTRATION_RESPONSE)
    {
        // Server sends this only to the registering connection — no mod_id filter needed
        bool success = msg.payload.value("success", false);
        std::string reason = msg.payload.value("reason", "");

        if (success)
            ctx->callbacks.invoke_registration_success();
        else
            ctx->callbacks.invoke_registration_rejected(reason);
    }
    else if (msg.type == IPCMessageType::ERROR_MSG)
    {
        std::string code = msg.payload.value("code", "");
        std::string error_message = msg.payload.value("message", "");
        ctx->callbacks.invoke_error(code, error_message);
    }
    else if (msg.type == IPCMessageType::COMMAND_RESPONSE)
    {
        // Server routes this to the issuing connection — no mod_id filter needed
        std::string command = msg.payload.value("command", "");
        bool success = msg.payload.value("success", false);
        std::string error = msg.payload.value("error", "");
        nlohmann::json data = msg.payload.value("data", nlohmann::json::object());

        if (ctx->cached_lua)
            ctx->callbacks.invoke_command_response(command, success, error, data.dump(), *ctx->cached_lua);
    }
    else if (msg.type == IPCMessageType::TRACKER_SNAPSHOT)
    {
        if (ctx->cached_lua)
            ctx->callbacks.invoke_tracker_snapshot(msg.payload, *ctx->cached_lua);
    }
    else if (msg.type == IPCMessageType::TRACKER_UPDATE)
    {
        if (ctx->cached_lua)
            ctx->callbacks.invoke_tracker_update(msg.payload, *ctx->cached_lua);
    }
    else if (msg.type == IPCMessageType::API_CALL)
    {
        // Server routes API_CALLs to the target mod's connection — ctx IS the target
        std::string func_name = msg.payload.value("function", "");
        std::string caller = msg.payload.value("_source", "");
        uint64_t call_id = msg.payload.value("call_id", uint64_t(0));
        bool wants_result = msg.payload.value("wants_result", false);

        auto it = ctx->api_callbacks.find(func_name);
        if (it == ctx->api_callbacks.end())
        {
            APLogger::get()->log(LogLevel::Warn, "APClientManager",
                                 "API function not found: " + func_name + " in " + ctx->mod_id +
                                     " (from " + caller + ")");
            if (wants_result)
                send_api_error(ctx, caller, call_id, "Function '" + func_name + "' not registered");
            return;
        }

        if (!ctx->cached_lua)
            return;
        sol::state_view &lua = *ctx->cached_lua;

        nlohmann::json args = msg.payload.value("args", nlohmann::json::array());
        std::vector<sol::object> lua_args;
        for (const auto &arg : args)
            lua_args.push_back(ctx->callbacks.json_to_lua(lua, arg));

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
                send_api_error(ctx, caller, call_id, "Too many arguments (max 8)");
            return;
        }

        if (wants_result)
        {
            if (result.valid())
            {
                sol::object ret = result;
                nlohmann::json result_json = APCallbacks::lua_to_json(ret);
                send_api_result(ctx, caller, call_id, result_json);
            }
            else
            {
                sol::error err = result;
                send_api_error(ctx, caller, call_id, err.what());
            }
        }
    }
    else if (msg.type == IPCMessageType::API_RESULT)
    {
        // Server routes API_RESULTs to the caller's connection — ctx IS the caller
        uint64_t call_id = msg.payload.value("call_id", uint64_t(0));

        auto it = ctx->pending_api_calls.find(call_id);
        if (it == ctx->pending_api_calls.end())
            return;

        sol::protected_function callback = it->second.callback;
        ctx->pending_api_calls.erase(it);

        if (!ctx->cached_lua)
            return;
        sol::state_view &lua = *ctx->cached_lua;

        if (msg.payload.contains("error"))
        {
            std::string err = msg.payload["error"];
            callback(err, sol::nil);
        }
        else
        {
            sol::object result_obj =
                ctx->callbacks.json_to_lua(lua, msg.payload.value("result", nlohmann::json()));
            callback(sol::nil, result_obj);
        }
    }
}

int APClientManager::create_lua_module_impl(lua_State *L, APClientContext *ctx)
{
    sol::state_view lua(L);
    sol::table module = lua.create_table();

    // =========================================================================
    // Connection Functions
    // =========================================================================

    module["connect"] = [ctx]() -> bool { return ctx->ipc_client->connect(APConfig::get()->get_game_name()); };

    module["disconnect"] = [ctx]() { ctx->ipc_client->disconnect(); };

    module["is_connected"] = [ctx]() -> bool { return ctx->ipc_client->is_connected(); };

    module["get_current_state"] = [ctx]() -> std::string { return ctx->lifecycle_state; };

    module["update"] = []() { APClientManager::get()->update(); };

    // =========================================================================
    // Registration Functions
    // =========================================================================

    module["register_mod"] = [ctx]() -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        if (ctx->mod_id.empty())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::REGISTER;
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"mod_id", ctx->mod_id}, {"version", ctx->version}};

        return ctx->ipc_client->send_message(msg);
    };

    // =========================================================================
    // Location Functions
    // =========================================================================

    module["check_location"] = [ctx](const std::string &location_name, sol::optional<int> instance) -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_CHECK;
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"location", location_name}, {"instance", instance.value_or(1)}};

        return ctx->ipc_client->send_message(msg);
    };

    module["scout_locations"] = [ctx](sol::table locations) -> bool {
        if (!ctx->ipc_client->is_connected())
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
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"locations", location_names}};

        return ctx->ipc_client->send_message(msg);
    };

    // =========================================================================
    // Logging Functions (delegate to APLogger)
    // =========================================================================

    module["log"] = [ctx](const std::string &level, const std::string &message) {
        LogLevel log_level = log_level_from_string(level);
        APLogger::get()->log(log_level, ctx->mod_id, message);
    };

    // =========================================================================
    // Command Functions (Priority Client Only)
    // =========================================================================

    module["command"] = [ctx](const std::string &command, sol::optional<sol::table> payload) -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = ctx->mod_id;
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

        return ctx->ipc_client->send_message(msg);
    };

    // =========================================================================
    // Tracker Functions
    // =========================================================================

    module["subscribe_tracker"] = [ctx]() -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::SUBSCRIBE_TRACKER;
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = nlohmann::json::object();

        return ctx->ipc_client->send_message(msg);
    };

    module["unsubscribe_tracker"] = [ctx]() -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::UNSUBSCRIBE_TRACKER;
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = nlohmann::json::object();

        return ctx->ipc_client->send_message(msg);
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

    module["register_api"] = [ctx](sol::table api_table) {
        api_table.for_each([ctx](sol::object key, sol::object val) {
            if (key.is<std::string>() && val.is<sol::protected_function>())
            {
                ctx->api_callbacks[key.as<std::string>()] = val.as<sol::protected_function>();
            }
        });
        APLogger::get()->log(LogLevel::Info, "APClientManager",
                             "[" + ctx->mod_id + "] API registered with " +
                                 std::to_string(ctx->api_callbacks.size()) + " functions");
    };

    module["get_api"] = [ctx](sol::this_state ts, const std::string &target_mod) -> sol::object {
        sol::state_view lua(ts);

        // Create proxy table with __index metamethod
        sol::table proxy = lua.create_table();
        sol::table mt = lua.create_table();

        mt[sol::meta_function::index] = [target_mod, ctx](sol::this_state ts2, sol::table /*self*/,
                                                           const std::string &func_name) -> sol::object {
            sol::state_view lua2(ts2);

            // Return a function that sends an API_CALL when invoked
            return sol::make_object(lua2, [target_mod, func_name, ctx](sol::variadic_args va) {
                APClientManager::get()->invoke_api_call(ctx, target_mod, func_name, va);
            });
        };

        proxy[sol::metatable_key] = mt;
        return proxy;
    };

    module["send_to"] = [ctx](const std::string &target_mod, sol::table payload) -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = ctx->mod_id;
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

        return ctx->ipc_client->send_message(msg);
    };

    module["broadcast"] = [ctx](sol::table payload) -> bool {
        if (!ctx->ipc_client->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = ctx->mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"command", "broadcast"}, {"payload", APCallbacks::lua_to_json(payload)}};

        return ctx->ipc_client->send_message(msg);
    };

    // =========================================================================
    // Callback Registration (routes to this mod's context callbacks)
    // =========================================================================

    module["on_lifecycle"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_lifecycle_callback(cb); };
    module["on_message"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_message_callback(cb); };
    module["on_error"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_error_callback(cb); };
    module["on_connect"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_connect_callback(cb); };
    module["on_disconnect"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_disconnect_callback(cb); };
    module["on_registration_success"] = [ctx](sol::protected_function cb) {
        ctx->callbacks.set_registration_success_callback(cb);
    };
    module["on_registration_rejected"] = [ctx](sol::protected_function cb) {
        ctx->callbacks.set_registration_rejected_callback(cb);
    };
    module["on_item_received"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_item_received_callback(cb); };
    module["on_state_active"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_state_active_callback(cb); };
    module["on_state_error"] = [ctx](sol::protected_function cb) { ctx->callbacks.set_state_error_callback(cb); };
    module["on_command_response"] = [ctx](sol::protected_function cb) {
        ctx->callbacks.set_command_response_callback(cb);
    };
    module["on_tracker_snapshot"] = [ctx](sol::protected_function cb) {
        ctx->callbacks.set_tracker_snapshot_callback(cb);
    };
    module["on_tracker_update"] = [ctx](sol::protected_function cb) {
        ctx->callbacks.set_tracker_update_callback(cb);
    };

    return sol::stack::push(L, module);
}

// =============================================================================
// Cross-Mod API Helpers
// =============================================================================

void APClientManager::invoke_api_call(APClientContext *ctx, const std::string &target_mod,
                                      const std::string &func_name, sol::variadic_args va)
{
    if (!ctx->ipc_client->is_connected())
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

    uint64_t call_id = ctx->next_call_id++;
    bool wants_result = callback.has_value();

    // Store pending callback (if any) in this mod's context
    if (wants_result)
    {
        ctx->pending_api_calls[call_id] = {*callback, std::chrono::steady_clock::now()};
    }

    // Send API_CALL via this mod's own connection
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_CALL;
    msg.source = ctx->mod_id;
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"function", func_name},    {"args", args_json},
                   {"call_id", call_id},        {"wants_result", wants_result}};
    ctx->ipc_client->send_message(msg);
}

void APClientManager::send_api_result(APClientContext *ctx, const std::string &target_mod,
                                      uint64_t call_id, const nlohmann::json &result_json)
{
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_RESULT;
    msg.source = ctx->mod_id;
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"call_id", call_id}, {"result", result_json}};
    ctx->ipc_client->send_message(msg);
}

void APClientManager::send_api_error(APClientContext *ctx, const std::string &target_mod,
                                     uint64_t call_id, const std::string &error)
{
    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::API_RESULT;
    msg.source = ctx->mod_id;
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"target_mod", target_mod}, {"call_id", call_id}, {"error", error}};
    ctx->ipc_client->send_message(msg);
}

void APClientManager::cleanup_stale_api_calls(APClientContext &ctx)
{
    static constexpr auto TIMEOUT = std::chrono::seconds(10);
    auto now = std::chrono::steady_clock::now();

    auto it = ctx.pending_api_calls.begin();
    while (it != ctx.pending_api_calls.end())
    {
        if (now - it->second.created_at > TIMEOUT)
        {
            APLogger::get()->log(LogLevel::Warn, "APClientManager",
                                 "[" + ctx.mod_id + "] API call timed out (call_id=" + std::to_string(it->first) + ")");

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

            it = ctx.pending_api_calls.erase(it);
        }
        else
        {
            ++it;
        }
    }
}

} // namespace ap::client
