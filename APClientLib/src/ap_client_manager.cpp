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

    // Only do full initialization once
    if (!initialized_)
    {
        // 3. Set prefix tag and load framework config
        APLogger::get()->set_prefix_tag("APClientLib");
        APConfig::get()->load_default();

        // 4. Initialize logger (reads settings from APConfig)
        APLogger::get()->init();

        std::ostringstream oss;
        oss << "init() running on thread: " << std::this_thread::get_id() << " (name: " << APLogger::get_thread_name()
            << ")";
        APLogger::get()->log(LogLevel::Trace, "APClientManager", oss.str());

        // 5. Load this mod's manifest using APPathUtil::find_current_mod_folder()
        APLogger::get()->log(LogLevel::Trace, "APClientManager", "Loading manifest via find_current_mod_folder()...");
        if (!manifest_.load_current())
        {
            APLogger::get()->log(LogLevel::Warn, "APClientManager", "Failed to load manifest - mod identity unknown");
        }
        else
        {
            APLogger::get()->log(LogLevel::Debug, "APClientManager",
                                 "Manifest loaded: mod_id=" + manifest_.get_mod_id() + " from " +
                                     manifest_.get_manifest_path().string());
        }

        // 6. Set up IPC handlers (delegates to handle_ipc_message)
        APIPCClient::get()->set_message_handler([this](const ap::ClientIPCMessage &msg) { handle_ipc_message(msg); });

        APIPCClient::get()->set_connect_handler([]() { APCallbacks::get()->invoke_connect(); });

        APIPCClient::get()->set_disconnect_handler([]() { APCallbacks::get()->invoke_disconnect(); });

        initialized_ = true;

        APLogger::get()->log(LogLevel::Info, "APClientManager",
                             "Initialized successfully for mod: " + manifest_.get_mod_id());
    }

    // 8. Create and return the Lua module
    return create_lua_module(L);
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

    // Clear callbacks
    APCallbacks::get()->clear_all();

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
}

int APClientManager::create_lua_module(lua_State *L)
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

    module["register_mod"] = []() -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        const auto &manifest = APClientManager::get()->get_manifest();
        const auto &mod_id = manifest.get_mod_id();
        if (mod_id.empty())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::REGISTER;
        msg.source = mod_id;
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"mod_id", mod_id}, {"version", manifest.get_version()}};

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Location Functions
    // =========================================================================

    module["check_location"] = [](const std::string &location_name, sol::optional<int> instance) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_CHECK;
        msg.source = APClientManager::get()->get_manifest().get_mod_id();
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"location", location_name}, {"instance", instance.value_or(1)}};

        return APIPCClient::get()->send_message(msg);
    };

    module["scout_locations"] = [](sol::table locations) -> bool {
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
        msg.source = APClientManager::get()->get_manifest().get_mod_id();
        msg.target = IPCTarget::FRAMEWORK;
        msg.payload = {{"locations", location_names}};

        return APIPCClient::get()->send_message(msg);
    };

    // =========================================================================
    // Logging Functions (delegate to APLogger)
    // =========================================================================

    module["log"] = [](const std::string &level, const std::string &message) {
        LogLevel log_level = log_level_from_string(level);
        APLogger::get()->log(log_level, APClientManager::get()->get_manifest().get_mod_id(), message);
    };

    // =========================================================================
    // Command Functions (Priority Client Only)
    // =========================================================================

    module["command"] = [](const std::string &command, sol::optional<sol::table> payload) -> bool {
        if (!APIPCClient::get()->is_connected())
            return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::COMMAND;
        msg.source = APClientManager::get()->get_manifest().get_mod_id();
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

    return sol::stack::push(L, module);
}

} // namespace ap::client