#include "ap_client_manager.h"
#include "ap_action_executor.h"
#include "ap_ipc_client.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <sol/sol.hpp>

#include <fstream>
#include <mutex>

namespace ap::client
{

// =============================================================================
// Implementation Class
// =============================================================================

class APClientManager::Impl
{
  public:
    // Lua state
    std::unique_ptr<sol::state_view> cached_lua;

    // Mod identity
    std::string mod_id;
    std::string mod_version;
    std::filesystem::path mod_folder;

    // Configuration
    FrameworkConfig framework_config;

    // Lifecycle state (cached from framework)
    std::string current_lifecycle_state = "UNINITIALIZED";

    // Components
    std::unique_ptr<ap::APIPCClient> ipc_client;
    std::unique_ptr<APActionExecutor> action_executor;

    // Logging
    std::ofstream log_file;
    std::mutex log_mutex;

    // State
    bool initialized = false;

    Impl() = default;
    ~Impl()
    {
        if (log_file.is_open())
        {
            log_file.close();
        }
    }

    // =========================================================================
    // Configuration Loading
    // =========================================================================

    bool load_framework_config()
    {
        auto framework_folder = APPathUtil::find_framework_mod_folder();
        if (!framework_folder)
        {
            return false;
        }

        auto config_path = *framework_folder / "framework_config.json";
        std::string content = APPathUtil::read_file(config_path);
        if (content.empty())
        {
            return false;
        }

        try
        {
            auto json = nlohmann::json::parse(content);

            framework_config.game_name = json.value("game_name", "UnknownGame");
            framework_config.version = json.value("version", "1.0.0");

            if (json.contains("logging"))
            {
                auto &logging = json["logging"];
                framework_config.logging.level = logging.value("level", "info");
                framework_config.logging.file = logging.value("file", "ap_framework.log");
                framework_config.logging.console = logging.value("console", true);
            }

            framework_config.loaded = true;

            // Open log file if specified
            if (!framework_config.logging.file.empty())
            {
                auto log_path = *framework_folder / framework_config.logging.file;
                log_file.open(log_path, std::ios::app);
            }

            return true;
        }
        catch (const std::exception &)
        {
            return false;
        }
    }

    bool load_mod_manifest()
    {
        if (mod_folder.empty())
        {
            return false;
        }

        auto manifest_path = mod_folder / "manifest.json";
        std::string content = APPathUtil::read_file(manifest_path);
        if (content.empty())
        {
            return false;
        }

        try
        {
            auto json = nlohmann::json::parse(content);

            mod_id = json.value("mod_id", "");
            mod_version = json.value("version", "1.0.0");

            return !mod_id.empty();
        }
        catch (const std::exception &)
        {
            return false;
        }
    }

    // =========================================================================
    // Mod Folder Discovery via debug.getinfo
    // =========================================================================

    std::filesystem::path discover_mod_folder_from_lua(lua_State *L)
    {
        if (!L)
        {
            return {};
        }

        sol::state_view lua(L);

        try
        {
            // Execute: debug.getinfo(level, "S").source
            sol::table debug_table = lua["debug"];
            sol::protected_function getinfo = debug_table["getinfo"];

            // Try different stack levels to find the calling script
            for (int level = 2; level <= 10; ++level)
            {
                auto result = getinfo(level, "S");
                if (!result.valid())
                    continue;

                sol::table info = result;
                sol::optional<std::string> source = info["source"];

                if (source && source->length() > 1 && (*source)[0] == '@')
                {
                    std::string path = source->substr(1); // Remove leading @
                    std::filesystem::path script_path(path);

                    // Script should be in <ModFolder>/Scripts/main.lua
                    // So mod folder is script_path.parent_path().parent_path()
                    if (script_path.has_parent_path())
                    {
                        auto scripts_folder = script_path.parent_path();
                        if (scripts_folder.filename() == "Scripts" && scripts_folder.has_parent_path())
                        {
                            return scripts_folder.parent_path();
                        }
                    }
                }
            }
        }
        catch (...)
        {
            // Fallback handled by caller
        }

        return {};
    }
};

// =============================================================================
// Singleton Instance
// =============================================================================

APClientManager &APClientManager::instance()
{
    static APClientManager instance;
    return instance;
}

APClientManager::APClientManager() : impl_(std::make_unique<Impl>())
{
}

APClientManager::~APClientManager()
{
    shutdown();
}

// =============================================================================
// Initialization
// =============================================================================

bool APClientManager::init(lua_State *L)
{
    if (impl_->initialized)
    {
        // Already initialized - just update Lua state
        update_lua_state(L);
        return true;
    }

    // Cache the Lua state
    update_lua_state(L);

    // Discover mod folder from calling script using debug.getinfo
    impl_->mod_folder = impl_->discover_mod_folder_from_lua(L);

    // Reinitialize path cache now that we have Lua state
    APPathUtil::reinitialize_cache();

    // Load configurations
    impl_->load_framework_config();
    impl_->load_mod_manifest();

    // Initialize IPC client
    if (!impl_->ipc_client)
    {
        impl_->ipc_client = std::make_unique<ap::APIPCClient>();
    }

    // Initialize action executor
    if (!impl_->action_executor)
    {
        impl_->action_executor = std::make_unique<APActionExecutor>();
    }

    impl_->initialized = true;

    log("trace", "APClientManager initialized for mod: " + impl_->mod_id);

    return true;
}

void APClientManager::update(lua_State *L)
{
    // Update cached Lua state
    update_lua_state(L);

    // Poll for IPC messages
    if (impl_->ipc_client)
    {
        impl_->ipc_client->poll();
    }
}

void APClientManager::shutdown()
{
    log("trace", "APClientManager shutting down");

    // Disconnect IPC
    if (impl_->ipc_client)
    {
        impl_->ipc_client->disconnect();
    }

    // Close log file
    if (impl_->log_file.is_open())
    {
        impl_->log_file.close();
    }

    // Reset state
    impl_->current_lifecycle_state = "UNINITIALIZED";
    impl_->initialized = false;
}

// =============================================================================
// Lua State Management
// =============================================================================

void APClientManager::update_lua_state(lua_State *L)
{
    if (L)
    {
        impl_->cached_lua = std::make_unique<sol::state_view>(L);
    }
}

sol::state_view *APClientManager::get_lua_state() const
{
    return impl_->cached_lua.get();
}

bool APClientManager::has_lua_state() const
{
    return impl_->cached_lua != nullptr;
}

// =============================================================================
// Mod Identity
// =============================================================================

const std::string &APClientManager::get_mod_id() const
{
    return impl_->mod_id;
}

const std::string &APClientManager::get_mod_version() const
{
    return impl_->mod_version;
}

const std::filesystem::path &APClientManager::get_mod_folder() const
{
    return impl_->mod_folder;
}

// =============================================================================
// Framework Configuration
// =============================================================================

const FrameworkConfig &APClientManager::get_framework_config() const
{
    return impl_->framework_config;
}

const std::string &APClientManager::get_game_name() const
{
    return impl_->framework_config.game_name;
}

// =============================================================================
// Lifecycle State
// =============================================================================

const std::string &APClientManager::get_current_lifecycle_state() const
{
    return impl_->current_lifecycle_state;
}

void APClientManager::set_current_lifecycle_state(const std::string &state)
{
    impl_->current_lifecycle_state = state;
}

// =============================================================================
// Component Access
// =============================================================================

ap::APIPCClient *APClientManager::get_ipc_client() const
{
    return impl_->ipc_client.get();
}

APActionExecutor *APClientManager::get_action_executor() const
{
    return impl_->action_executor.get();
}

// =============================================================================
// Logging
// =============================================================================

void APClientManager::log(const std::string &level, const std::string &message)
{
    // Check if we should log at this level
    int msg_priority = client_log_level_priority(level);
    int config_priority = client_log_level_priority(impl_->framework_config.logging.level);

    if (msg_priority < config_priority)
    {
        return;
    }

    std::string formatted = "[" + level + "] [" + impl_->mod_id + "] " + message;

    std::lock_guard<std::mutex> lock(impl_->log_mutex);

    // Write to file if enabled
    if (impl_->log_file.is_open())
    {
        impl_->log_file << formatted << std::endl;
        impl_->log_file.flush();
    }

    // Write to UE4SS console if enabled
    if (impl_->framework_config.logging.console && impl_->cached_lua)
    {
        try
        {
            sol::protected_function print_fn = (*impl_->cached_lua)["print"];
            if (print_fn.valid())
            {
                print_fn(formatted);
            }
        }
        catch (...)
        {
            // Ignore print errors
        }
    }
}

void APClientManager::notify_framework_of_error(const std::string &error_type, const std::string &details)
{
    if (!impl_->ipc_client || !impl_->ipc_client->is_connected())
        return;

    ap::ClientIPCMessage msg;
    msg.type = IPCMessageType::CALLBACK_ERROR;
    msg.source = impl_->mod_id;
    msg.target = IPCTarget::FRAMEWORK;
    msg.payload = {{"error_type", error_type}, {"details", details}, {"mod_id", impl_->mod_id}};

    impl_->ipc_client->send_message(msg);
}

// =============================================================================
// IPC Helpers
// =============================================================================

bool APClientManager::is_connected() const
{
    return impl_->ipc_client && impl_->ipc_client->is_connected();
}

bool APClientManager::connect()
{
    if (!impl_->ipc_client)
        return false;
    if (!impl_->framework_config.loaded)
    {
        impl_->load_framework_config();
    }
    return impl_->ipc_client->connect(impl_->framework_config.game_name);
}

void APClientManager::disconnect()
{
    if (impl_->ipc_client)
    {
        impl_->ipc_client->disconnect();
    }
}

bool APClientManager::send_message(const ap::ClientIPCMessage &msg)
{
    if (!impl_->ipc_client || !impl_->ipc_client->is_connected())
    {
        return false;
    }
    return impl_->ipc_client->send_message(msg);
}

} // namespace ap::client