#pragma once

#include "ap_clientlib_exports.h"
#include "ap_client_types.h"

#include <memory>
#include <string>
#include <filesystem>
#include <functional>

// Forward declarations
struct lua_State;
namespace sol {
    class state_view;
    struct protected_function_result;
}

namespace ap {
    class APIPCClient;
}

namespace ap::client {

class APActionExecutor;

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
// APClientManager - Singleton
// =============================================================================

/**
 * @brief Global singleton managing APClientLib state and components.
 *
 * The APClientManager is the central orchestrator for client mods that:
 * - Manages the cached Lua state
 * - Owns the IPC client and action executor
 * - Handles configuration loading
 * - Coordinates callback registration and invocation
 * - Tracks mod identity (mod_id, version, folder)
 *
 * This mirrors APFrameworkCore's APManager pattern to provide clear
 * separation of concerns and prepare for future modularization.
 */
class APCLIENT_API APClientManager {
public:
    /**
     * @brief Get the singleton instance.
     * @return Reference to the APClientManager singleton.
     */
    static APClientManager& instance();

    /**
     * @brief Initialize the manager (called from luaopen_APClientLib).
     * @param L Lua state from UE4SS.
     * @return true if initialization succeeded.
     *
     * This method:
     * - Caches the Lua state
     * - Discovers the calling mod's folder via debug.getinfo
     * - Loads framework_config.json
     * - Loads the mod's manifest.json
     * - Initializes IPC client and action executor
     */
    bool init(lua_State* L);

    /**
     * @brief Update the manager (called each tick from Lua).
     * @param L Lua state.
     *
     * This method:
     * - Updates the cached Lua state
     * - Polls the IPC client for messages
     */
    void update(lua_State* L);

    /**
     * @brief Shutdown the manager.
     *
     * Disconnects IPC, closes log file, cleans up resources.
     */
    void shutdown();

    // =========================================================================
    // Lua State Management
    // =========================================================================

    /**
     * @brief Update the cached Lua state.
     * @param L The current Lua state from UE4SS.
     */
    void update_lua_state(lua_State* L);

    /**
     * @brief Get the cached Lua state.
     * @return Pointer to cached sol::state_view, or nullptr if not initialized.
     */
    sol::state_view* get_lua_state() const;

    /**
     * @brief Check if the Lua state is available.
     * @return true if cached Lua state is valid.
     */
    bool has_lua_state() const;

    // =========================================================================
    // Mod Identity
    // =========================================================================

    /**
     * @brief Get the mod ID (from manifest.json).
     * @return Mod identifier string.
     */
    const std::string& get_mod_id() const;

    /**
     * @brief Get the mod version (from manifest.json).
     * @return Version string.
     */
    const std::string& get_mod_version() const;

    /**
     * @brief Get the mod folder path.
     * @return Path to the mod's root folder.
     */
    const std::filesystem::path& get_mod_folder() const;

    // =========================================================================
    // Framework Configuration
    // =========================================================================

    /**
     * @brief Get the framework configuration.
     * @return Reference to loaded framework config.
     */
    const FrameworkConfig& get_framework_config() const;

    /**
     * @brief Get the game name from config.
     * @return Game name string.
     */
    const std::string& get_game_name() const;

    // =========================================================================
    // Lifecycle State
    // =========================================================================

    /**
     * @brief Get the current lifecycle state (cached from framework).
     * @return Lifecycle state string.
     */
    const std::string& get_current_lifecycle_state() const;

    /**
     * @brief Set the current lifecycle state (internal, called on LIFECYCLE messages).
     * @param state New lifecycle state string.
     */
    void set_current_lifecycle_state(const std::string& state);

    // =========================================================================
    // Component Access
    // =========================================================================

    /**
     * @brief Get the IPC client.
     * @return Pointer to IPC client, or nullptr.
     */
    ap::APIPCClient* get_ipc_client() const;

    /**
     * @brief Get the action executor.
     * @return Pointer to action executor, or nullptr.
     */
    APActionExecutor* get_action_executor() const;

    // =========================================================================
    // Logging
    // =========================================================================

    /**
     * @brief Log a message respecting framework config.
     * @param level Log level (trace, debug, info, warn, error).
     * @param message Message to log.
     */
    void log(const std::string& level, const std::string& message);

    /**
     * @brief Notify the framework of an error via IPC.
     * @param error_type Type of error.
     * @param details Error details.
     */
    void notify_framework_of_error(const std::string& error_type, const std::string& details);

    // =========================================================================
    // IPC Helpers
    // =========================================================================

    /**
     * @brief Check if connected to the framework.
     * @return true if IPC client is connected.
     */
    bool is_connected() const;

    /**
     * @brief Connect to the framework IPC server.
     * @return true if connection succeeded.
     */
    bool connect();

    /**
     * @brief Disconnect from the framework.
     */
    void disconnect();

    /**
     * @brief Send a message to the framework.
     * @param msg Message to send.
     * @return true if sent successfully.
     */
    bool send_message(const ap::ClientIPCMessage& msg);

private:
    APClientManager();
    ~APClientManager();

    // Delete copy/move
    APClientManager(const APClientManager&) = delete;
    APClientManager& operator=(const APClientManager&) = delete;
    APClientManager(APClientManager&&) = delete;
    APClientManager& operator=(APClientManager&&) = delete;

    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap::client