#include <windows.h>
#include <sol/sol.hpp>
#include <nlohmann/json.hpp>
#include "ap_clientlib_exports.h"
#include "ap_ipc_client.h"
#include "ap_action_executor.h"
#include "ap_path_util.h"

#include <memory>
#include <string>
#include <fstream>
#include <mutex>
#include <optional>

namespace ap::client {

// =============================================================================
// Forward Declarations
// =============================================================================

void update_cached_lua(lua_State* L);
sol::state_view* get_cached_lua();

// =============================================================================
// Configuration Structures
// =============================================================================

struct LoggingConfig {
    std::string level = "info";
    std::string file = "ap_framework.log";
    bool console = true;
};

struct FrameworkConfig {
    std::string game_name;
    std::string version;
    LoggingConfig logging;
    bool loaded = false;
};

// =============================================================================
// Global State
// =============================================================================

static std::unique_ptr<ap::APIPCClient> g_ipc_client;
static std::unique_ptr<APActionExecutor> g_action_executor;
static std::string g_mod_id;
static std::string g_mod_version;
static std::filesystem::path g_mod_folder;
static FrameworkConfig g_framework_config;
static std::ofstream g_log_file;
static std::mutex g_log_mutex;

// =============================================================================
// Callback Storage
// =============================================================================

// Generic callbacks
static std::optional<sol::protected_function> g_callback_lifecycle;
static std::optional<sol::protected_function> g_callback_message;
static std::optional<sol::protected_function> g_callback_error;

// Specific callbacks
static std::optional<sol::protected_function> g_callback_connect;
static std::optional<sol::protected_function> g_callback_disconnect;
static std::optional<sol::protected_function> g_callback_registration_success;
static std::optional<sol::protected_function> g_callback_registration_rejected;
static std::optional<sol::protected_function> g_callback_item_received;
static std::optional<sol::protected_function> g_callback_state_active;
static std::optional<sol::protected_function> g_callback_state_error;

// =============================================================================
// Message Type Constants (must match APFrameworkCore)
// =============================================================================

namespace IPCMessageType {
    constexpr const char* REGISTER = "register";
    constexpr const char* REGISTRATION_RESPONSE = "registration_response";
    constexpr const char* LOCATION_CHECK = "location_check";
    constexpr const char* LOCATION_SCOUT = "location_scout";
    constexpr const char* LOG = "log";
    constexpr const char* ACTION_RESULT = "action_result";
    constexpr const char* EXECUTE_ACTION = "execute_action";
    constexpr const char* LIFECYCLE = "lifecycle";
    constexpr const char* AP_MESSAGE = "ap_message";
    constexpr const char* ERROR_MSG = "error";
    constexpr const char* CALLBACK_ERROR = "callback_error";
}

// =============================================================================
// Logging Functions
// =============================================================================

static int get_log_level_priority(const std::string& level) {
    if (level == "trace") return 0;
    if (level == "debug") return 1;
    if (level == "info") return 2;
    if (level == "warn" || level == "warning") return 3;
    if (level == "error") return 4;
    return 2; // default to info
}

static void log_internal(const std::string& level, const std::string& message) {
    // Check if we should log at this level
    int msg_priority = get_log_level_priority(level);
    int config_priority = get_log_level_priority(g_framework_config.logging.level);

    if (msg_priority < config_priority) {
        return;
    }

    std::string formatted = "[" + level + "] [" + g_mod_id + "] " + message;

    std::lock_guard<std::mutex> lock(g_log_mutex);

    // Write to file if enabled
    if (g_log_file.is_open()) {
        g_log_file << formatted << std::endl;
        g_log_file.flush();
    }

    // Write to UE4SS console if enabled
    if (g_framework_config.logging.console) {
        sol::state_view* lua = get_cached_lua();
        if (lua) {
            try {
                sol::protected_function print_fn = (*lua)["print"];
                if (print_fn.valid()) {
                    print_fn(formatted);
                }
            } catch (...) {
                // Ignore print errors
            }
        }
    }
}

// =============================================================================
// Framework Notification
// =============================================================================

static void notify_framework_of_error(const std::string& error_type, const std::string& details) {
    if (!g_ipc_client || !g_ipc_client->is_connected()) return;

    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::CALLBACK_ERROR;
    msg.source = g_mod_id;
    msg.target = "framework";
    msg.payload = {
        {"error_type", error_type},
        {"details", details},
        {"mod_id", g_mod_id}
    };

    g_ipc_client->send_message(msg);
}

// =============================================================================
// Callback Invocation
// =============================================================================

/**
 * Invoke an optional callback. Returns true if called successfully.
 * Silently skips if callback not registered.
 */
static bool invoke_optional_callback(
    const std::optional<sol::protected_function>& callback,
    const std::string& callback_name,
    const std::function<sol::protected_function_result(sol::protected_function&)>& caller
) {
    if (!callback || !callback->valid()) {
        return false; // Not registered - OK
    }

    try {
        sol::protected_function cb = *callback;
        sol::protected_function_result result = caller(cb);

        if (!result.valid()) {
            sol::error err = result;
            std::string error_msg = err.what();
            log_internal("error", "Callback error in " + callback_name + ": " + error_msg);
            notify_framework_of_error("callback_error", callback_name + ": " + error_msg);
            return false;
        }
        return true;

    } catch (const std::exception& e) {
        log_internal("error", "Callback exception in " + callback_name + ": " + std::string(e.what()));
        notify_framework_of_error("callback_exception", callback_name + ": " + e.what());
        return false;
    }
}

// =============================================================================
// Message Handling
// =============================================================================

/**
 * Handle incoming messages from the framework.
 */
void handle_message(const ap::ClientIPCMessage& msg) {
    // Generic message callback
    invoke_optional_callback(g_callback_message, "on_message", [&](sol::protected_function& cb) {
        return cb(msg.type, msg.payload.dump());
    });

    // Handle specific message types
    if (msg.type == IPCMessageType::EXECUTE_ACTION) {
        // Execute the action using the action executor
        if (g_action_executor) {
            auto result = g_action_executor->execute_from_payload(msg.payload);

            // Invoke item received callback
            int64_t item_id = msg.payload.value("item_id", int64_t(0));
            std::string item_name = msg.payload.value("item_name", "");
            std::string sender = msg.payload.value("sender", "");

            invoke_optional_callback(g_callback_item_received, "on_item_received", [&](sol::protected_function& cb) {
                return cb(item_id, item_name, sender);
            });

            // Send result back to framework
            if (g_ipc_client && g_ipc_client->is_connected()) {
                ap::ClientIPCMessage response;
                response.type = IPCMessageType::ACTION_RESULT;
                response.source = g_mod_id;
                response.target = "framework";
                response.payload = {
                    {"item_id", result.item_id},
                    {"item_name", result.item_name},
                    {"success", result.success},
                    {"error", result.error}
                };
                g_ipc_client->send_message(response);
            }

            // If action failed, log it
            if (!result.success) {
                log_internal("error", "Action execution failed for " + item_name + ": " + result.error);
                notify_framework_of_error("action_failed", result.error);
            }
        } else {
            log_internal("error", "Action executor not initialized");
            notify_framework_of_error("action_executor_missing", "APActionExecutor not initialized");
        }

    } else if (msg.type == IPCMessageType::LIFECYCLE) {
        std::string state = msg.payload.value("state", "");
        std::string message = msg.payload.value("message", "");

        // Generic lifecycle callback
        invoke_optional_callback(g_callback_lifecycle, "on_lifecycle", [&](sol::protected_function& cb) {
            return cb(state, message);
        });

        // Specific lifecycle callbacks
        if (state == "ACTIVE") {
            invoke_optional_callback(g_callback_state_active, "on_state_active", [](sol::protected_function& cb) {
                return cb();
            });
        } else if (state == "ERROR_STATE") {
            invoke_optional_callback(g_callback_state_error, "on_state_error", [&](sol::protected_function& cb) {
                return cb(message);
            });
        }

    } else if (msg.type == IPCMessageType::REGISTRATION_RESPONSE) {
        bool success = msg.payload.value("success", false);
        std::string reason = msg.payload.value("reason", "");

        if (success) {
            invoke_optional_callback(g_callback_registration_success, "on_registration_success", [](sol::protected_function& cb) {
                return cb();
            });
        } else {
            invoke_optional_callback(g_callback_registration_rejected, "on_registration_rejected", [&](sol::protected_function& cb) {
                return cb(reason);
            });
        }

    } else if (msg.type == IPCMessageType::AP_MESSAGE) {
        // AP server messages are passed through to the generic message callback
        // which was already invoked above

    } else if (msg.type == IPCMessageType::ERROR_MSG) {
        std::string code = msg.payload.value("code", "");
        std::string error_message = msg.payload.value("message", "");

        invoke_optional_callback(g_callback_error, "on_error", [&](sol::protected_function& cb) {
            return cb(code, error_message);
        });
    }
}

// =============================================================================
// Configuration Loading
// =============================================================================

static bool load_framework_config() {
    auto framework_folder = APPathUtil::find_framework_mod_folder();
    if (!framework_folder) {
        return false;
    }

    auto config_path = *framework_folder / "framework_config.json";
    std::string content = APPathUtil::read_file(config_path);
    if (content.empty()) {
        return false;
    }

    try {
        auto json = nlohmann::json::parse(content);

        g_framework_config.game_name = json.value("game_name", "UnknownGame");
        g_framework_config.version = json.value("version", "1.0.0");

        if (json.contains("logging")) {
            auto& logging = json["logging"];
            g_framework_config.logging.level = logging.value("level", "info");
            g_framework_config.logging.file = logging.value("file", "ap_framework.log");
            g_framework_config.logging.console = logging.value("console", true);
        }

        g_framework_config.loaded = true;

        // Open log file if specified
        if (!g_framework_config.logging.file.empty()) {
            auto log_path = *framework_folder / g_framework_config.logging.file;
            g_log_file.open(log_path, std::ios::app);
        }

        return true;

    } catch (const std::exception& e) {
        return false;
    }
}

static bool load_mod_manifest() {
    if (g_mod_folder.empty()) {
        return false;
    }

    auto manifest_path = g_mod_folder / "manifest.json";
    std::string content = APPathUtil::read_file(manifest_path);
    if (content.empty()) {
        return false;
    }

    try {
        auto json = nlohmann::json::parse(content);

        g_mod_id = json.value("mod_id", "");
        g_mod_version = json.value("version", "1.0.0");

        return !g_mod_id.empty();

    } catch (const std::exception& e) {
        return false;
    }
}

// =============================================================================
// Script Path Discovery
// =============================================================================

/**
 * Find the calling mod's folder using debug.getinfo.
 * This must be called during require("APClientLib") to get the correct path.
 */
static std::filesystem::path discover_mod_folder_from_lua(lua_State* L) {
    sol::state_view lua(L);

    try {
        // Execute: debug.getinfo(level, "S").source
        sol::table debug_table = lua["debug"];
        sol::protected_function getinfo = debug_table["getinfo"];

        // Try different stack levels to find the calling script
        for (int level = 2; level <= 10; ++level) {
            auto result = getinfo(level, "S");
            if (!result.valid()) continue;

            sol::table info = result;
            sol::optional<std::string> source = info["source"];

            if (source && source->length() > 1 && (*source)[0] == '@') {
                std::string path = source->substr(1); // Remove leading @
                std::filesystem::path script_path(path);

                // Script should be in <ModFolder>/Scripts/main.lua
                // So mod folder is script_path.parent_path().parent_path()
                if (script_path.has_parent_path()) {
                    auto scripts_folder = script_path.parent_path();
                    if (scripts_folder.filename() == "Scripts" && scripts_folder.has_parent_path()) {
                        return scripts_folder.parent_path();
                    }
                }
            }
        }
    } catch (...) {
        // Fallback to path util
    }

    return {};
}

// =============================================================================
// Lua Module Creation
// =============================================================================

/**
 * Create the Lua module exposed by APClientLib.
 */
int create_lua_module(lua_State* L) {
    sol::state_view lua(L);
    sol::table module = lua.create_table();

    // Update cached Lua state immediately
    update_cached_lua(L);

    // Discover mod folder from calling script
    g_mod_folder = discover_mod_folder_from_lua(L);

    // Initialize cache with the Lua state
    APPathUtil::reinitialize_cache();

    // Load configurations
    load_framework_config();
    load_mod_manifest();

    // Initialize the client library
    if (!g_ipc_client) {
        g_ipc_client = std::make_unique<ap::APIPCClient>();
    }
    if (!g_action_executor) {
        g_action_executor = std::make_unique<APActionExecutor>();
    }

    // Set up message handler
    g_ipc_client->set_message_handler(handle_message);

    // Set up connection/disconnection callbacks
    g_ipc_client->set_connect_handler([]() {
        invoke_optional_callback(g_callback_connect, "on_connect", [](sol::protected_function& cb) {
            return cb();
        });
    });

    g_ipc_client->set_disconnect_handler([]() {
        invoke_optional_callback(g_callback_disconnect, "on_disconnect", [](sol::protected_function& cb) {
            return cb();
        });
    });

    // =========================================================================
    // Connection Functions
    // =========================================================================

    // connect() -> boolean (uses game_name from config)
    module["connect"] = []() -> bool {
        if (!g_ipc_client) return false;
        if (!g_framework_config.loaded) {
            load_framework_config();
        }
        return g_ipc_client->connect(g_framework_config.game_name);
    };

    // disconnect()
    module["disconnect"] = []() {
        if (g_ipc_client) {
            g_ipc_client->disconnect();
        }
    };

    // is_connected() -> boolean
    module["is_connected"] = []() -> bool {
        return g_ipc_client && g_ipc_client->is_connected();
    };

    // update() - Must be called every tick
    module["update"] = [](sol::this_state ts) {
        // Update cached Lua state using sol::this_state to get the lua_State*
        lua_State* L = ts.lua_state();
        update_cached_lua(L);

        // Poll for IPC messages (will trigger handle_message for each)
        if (g_ipc_client) {
            g_ipc_client->poll();
        }
    };

    // =========================================================================
    // Registration Functions
    // =========================================================================

    // register_mod() -> boolean (uses mod_id/version from manifest)
    module["register_mod"] = []() -> bool {
        if (!g_ipc_client || !g_ipc_client->is_connected()) return false;
        if (g_mod_id.empty()) return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::REGISTER;
        msg.source = g_mod_id;
        msg.target = "framework";
        msg.payload = {
            {"mod_id", g_mod_id},
            {"version", g_mod_version}
        };

        return g_ipc_client->send_message(msg);
    };

    // =========================================================================
    // Location Functions
    // =========================================================================

    // check_location(location_name, instance?) -> boolean
    module["check_location"] = [](const std::string& location_name, sol::optional<int> instance) -> bool {
        if (!g_ipc_client || !g_ipc_client->is_connected()) return false;

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_CHECK;
        msg.source = g_mod_id;
        msg.target = "framework";
        msg.payload = {
            {"location", location_name},
            {"instance", instance.value_or(1)}
        };

        return g_ipc_client->send_message(msg);
    };

    // scout_locations(locations_table) -> boolean
    module["scout_locations"] = [](sol::table locations) -> bool {
        if (!g_ipc_client || !g_ipc_client->is_connected()) return false;

        std::vector<std::string> location_names;
        for (auto& pair : locations) {
            if (pair.second.is<std::string>()) {
                location_names.push_back(pair.second.as<std::string>());
            }
        }

        ap::ClientIPCMessage msg;
        msg.type = IPCMessageType::LOCATION_SCOUT;
        msg.source = g_mod_id;
        msg.target = "framework";
        msg.payload = {
            {"locations", location_names}
        };

        return g_ipc_client->send_message(msg);
    };

    // =========================================================================
    // Logging Functions
    // =========================================================================

    // log(level, message) - Writes to file/console per config
    module["log"] = [](const std::string& level, const std::string& message) {
        log_internal(level, message);
    };

    // =========================================================================
    // Callback Registration - Generic
    // =========================================================================

    module["on_lifecycle"] = [](sol::protected_function callback) {
        g_callback_lifecycle = callback;
    };

    module["on_message"] = [](sol::protected_function callback) {
        g_callback_message = callback;
    };

    module["on_error"] = [](sol::protected_function callback) {
        g_callback_error = callback;
    };

    // =========================================================================
    // Callback Registration - Specific
    // =========================================================================

    module["on_connect"] = [](sol::protected_function callback) {
        g_callback_connect = callback;
    };

    module["on_disconnect"] = [](sol::protected_function callback) {
        g_callback_disconnect = callback;
    };

    module["on_registration_success"] = [](sol::protected_function callback) {
        g_callback_registration_success = callback;
    };

    module["on_registration_rejected"] = [](sol::protected_function callback) {
        g_callback_registration_rejected = callback;
    };

    module["on_item_received"] = [](sol::protected_function callback) {
        g_callback_item_received = callback;
    };

    module["on_state_active"] = [](sol::protected_function callback) {
        g_callback_state_active = callback;
    };

    module["on_state_error"] = [](sol::protected_function callback) {
        g_callback_state_error = callback;
    };

    return sol::stack::push(L, module);
}

} // namespace ap::client

// =============================================================================
// DLL Entry Points
// =============================================================================

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hModule);
            break;
        case DLL_PROCESS_DETACH:
            // Clean up
            if (ap::client::g_log_file.is_open()) {
                ap::client::g_log_file.close();
            }
            ap::client::g_action_executor.reset();
            ap::client::g_ipc_client.reset();
            break;
    }
    return TRUE;
}

extern "C" APCLIENT_API int luaopen_APClientLib(lua_State* L) {
    return ap::client::create_lua_module(L);
}
