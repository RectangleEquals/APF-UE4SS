#pragma once

#include "ap_exports.h"
#include "ap_types.h"
#include "atomic_state.h"

#include <memory>
#include <string>
#include <functional>

// Forward declarations for Lua
struct lua_State;

namespace ap {

// Forward declarations
class APClient;
class APIPCServer;
class APCapabilities;
class APModRegistry;
class APMessageRouter;
class APStateManager;
class APConfig;
class APPollingThread;

/**
 * @brief Global singleton managing the lifecycle of all AP Framework components.
 *
 * The APManager is the central orchestrator that:
 * - Manages the 11-state lifecycle state machine
 * - Coordinates all sub-components (IPC, AP client, registry, etc.)
 * - Handles state transitions and timeout monitoring
 * - Processes events from background threads on main thread
 *
 * Lifecycle States:
 * - UNINITIALIZED: Initial state before init()
 * - INITIALIZATION: Loading config, setting up components
 * - DISCOVERY: Scanning for mod manifests
 * - VALIDATION: Checking for conflicts
 * - GENERATION: Assigning IDs, generating capabilities config
 * - PRIORITY_REGISTRATION: Waiting for priority clients (30s timeout)
 * - REGISTRATION: Waiting for regular mods (60s timeout)
 * - CONNECTING: Establishing AP server connection (30s timeout)
 * - SYNCING: Validating checksum, reconciling state with server
 * - ACTIVE: Normal operation, processing items/locations
 * - RESYNCING: Reconnecting after disconnect
 * - ERROR_STATE: Error occurred, waiting for recovery
 */
class AP_API APManager {
public:
    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APManager singleton.
     */
    static APManager* get();

    /**
     * @brief Initialize the framework (called from luaopen_APFrameworkCore).
     * @param L Lua state from UE4SS.
     * @return Number of return values pushed to Lua stack.
     *
     * This starts the lifecycle state machine and returns a Lua module table.
     */
    int init(lua_State* L);

    /**
     * @brief Update the framework (called each tick from Lua).
     * @param L Lua state.
     * @return Number of return values pushed to Lua stack.
     *
     * Processes queued events, handles state transitions, and monitors timeouts.
     */
    int update(lua_State* L);

    /**
     * @brief Shutdown the framework.
     *
     * Stops all threads, saves state, and cleans up resources.
     */
    void shutdown();

    // ==========================================================================
    // State Machine
    // ==========================================================================

    /**
     * @brief Get the current lifecycle state.
     * @return Current state.
     */
    LifecycleState get_state() const;

    /**
     * @brief Transition to a new state.
     * @param new_state Target state.
     * @param message Optional message for the transition.
     * @return true if transition was allowed.
     */
    bool transition_to(LifecycleState new_state, const std::string& message = "");

    /**
     * @brief Check if currently in an active state.
     * @return true if in ACTIVE or RESYNCING state.
     */
    bool is_active() const;

    /**
     * @brief Check if in error state.
     * @return true if in ERROR_STATE.
     */
    bool is_error() const;

    // ==========================================================================
    // Registration
    // ==========================================================================

    /**
     * @brief Register a mod with the framework.
     * @param mod_id Mod identifier.
     * @param version Mod version string.
     * @return true if registration was accepted.
     *
     * Called by client mods during REGISTRATION phase.
     */
    bool register_mod(const std::string& mod_id, const std::string& version);

    /**
     * @brief Register a priority client with the framework.
     * @param mod_id Mod identifier (must match pattern archipelago.<game>.*).
     * @param version Mod version string.
     * @return true if registration was accepted.
     */
    bool register_priority_client(const std::string& mod_id, const std::string& version);

    // ==========================================================================
    // Priority Client Commands
    // ==========================================================================

    /**
     * @brief Restart the framework (from priority client).
     */
    void cmd_restart();

    /**
     * @brief Resync with AP server (from priority client).
     */
    void cmd_resync();

    /**
     * @brief Reconnect to AP server (from priority client).
     */
    void cmd_reconnect();

    // ==========================================================================
    // Component Access
    // ==========================================================================

    APConfig* get_config();
    APModRegistry* get_mod_registry();
    APCapabilities* get_capabilities();
    APStateManager* get_state_manager();
    APMessageRouter* get_message_router();
    APIPCServer* get_ipc_server();
    APClient* get_ap_client();

private:
    APManager();
    ~APManager();

    // Delete copy/move
    APManager(const APManager&) = delete;
    APManager& operator=(const APManager&) = delete;

    // For singleton access
    friend struct std::default_delete<APManager>;

    class Impl;
    std::unique_ptr<Impl> impl_;
};

// Global singleton instance (defined in ap_exports.cpp)
extern std::unique_ptr<APManager> g_ap_manager;

} // namespace ap
