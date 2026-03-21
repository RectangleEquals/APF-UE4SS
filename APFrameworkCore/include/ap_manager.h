#pragma once

#include "ap_exports.h"
#include "ap_manager_base.h"
#include "ap_types.h"
#include "atomic_state.h"
#include "message_queues.h"

#include <future>
#include <memory>
#include <nlohmann/json.hpp>
#include <optional>
#include <sol/sol.hpp>
#include <string>
#include <vector>

namespace ap
{

// Forward declaration
class APPollingThread;

/**
 * @brief Global singleton managing the lifecycle of all AP Framework
 * components.
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
 * - PRIORITY_REGISTRATION: Waiting for priority clients (30s default timeout)
 * - REGISTRATION: Waiting for regular mods (60s default timeout)
 * - CONNECTING: Establishing AP server connection (30s default timeout)
 * - SYNCING: Validating checksum, reconciling state with server
 * - ACTIVE: Normal operation, processing items/locations
 * - RESYNCING: Reconnecting after disconnect
 * - ERROR_STATE: Error occurred, waiting for recovery
 */
class AP_API APManager : public IAPManager
{
  public:
    // Pass-key Idiom for singleton
    struct ConstructorKey
    {
      private:
        friend class APManager;
        explicit ConstructorKey() = default;
    };

    // Public constructor, but unusable without a ConstructorKey
    APManager(ConstructorKey);
    ~APManager();

    // Disable copy and move
    APManager(const APManager &) = delete;
    APManager &operator=(const APManager &) = delete;

    /**
     * @brief Get the singleton instance (using Meyers Singleton pattern).
     * @return Pointer to the APManager singleton.
     */
    static APManager *get();

    /**
     * @brief Initialize the framework (called from luaopen_APFrameworkCore).
     * @param L Lua state from UE4SS.
     * @return Number of return values pushed to Lua stack.
     *
     * This starts the lifecycle state machine and returns a Lua module table.
     */
    int init(lua_State *L);

    /**
     * @brief Update the framework (called each tick from Lua).
     * @param L Lua state.
     * @return Number of return values pushed to Lua stack.
     *
     * Processes queued events, handles state transitions, and monitors timeouts.
     */
    int update(lua_State *L);

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
     * @brief Transition to a new state (thread-safe).
     * @param new_state Target state.
     * @param message Optional message for the transition.
     * @return true if transition was allowed (currently always true).
     */
    bool transition_to(LifecycleState new_state, const std::string &message = "");

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
    bool register_mod(const std::string &mod_id, const std::string &version);

    /**
     * @brief Register a priority client with the framework.
     * @param mod_id Mod identifier (must match pattern archipelago.<game>.*).
     * @param version Mod version string.
     * @return true if registration was accepted.
     */
    bool register_priority_client(const std::string &mod_id, const std::string &version);

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
    // IAPManager Interface
    // ==========================================================================

    /**
     * @brief Get the cached Lua state (implements IAPManager).
     * @return Pointer to the cached sol::state_view.
     */
    sol::state_view *get_cached_lua() override;

  protected:
    /*
    @brief Create a Lua module table.
    @param L Lua state.
    @return Number of return values pushed to Lua stack.
    */
    int create_lua_module(lua_State *L) override;

  private:
    // ==========================================================================
    // Private Methods
    // ==========================================================================

    /*
    @brief Transition to a new state (not thread-safe).
    @param new_state Target state.
    @param message Optional message for the transition.
    @return true if transition was allowed (currently always true).
    */
    bool transition_to_unlocked(LifecycleState new_state, const std::string &message);

    /*
    @brief Update the cached Lua state.
    @param L The current Lua state from UE4SS.
    @return Number of return values pushed to Lua stack.
    */
    int update_cached_lua(lua_State *L);

    /*
    @brief Handle an IPC message.
    @param client_id Mod identifier.
    @param msg IPC message.
    */
    void handle_ipc_message(const std::string &client_id, const IPCMessage &msg);

    /*
    @brief Handle a command message (messaging tier + admin tier).
    @param client_id Mod identifier.
    @param msg IPC message.
    */
    void handle_command(const std::string &client_id, const IPCMessage &msg);

    /*
    @brief Route a cross-mod API call (validates depends, forwards to target).
    @param client_id Calling mod identifier.
    @param msg IPC message with API_CALL payload.
    */
    void handle_api_call(const std::string &client_id, const IPCMessage &msg);

    /*
    @brief Forward a cross-mod API result back to the caller.
    @param client_id Responding mod identifier.
    @param msg IPC message with API_RESULT payload.
    */
    void handle_api_result(const std::string &client_id, const IPCMessage &msg);

    /*
    @brief Handle a framework event.
    @param event Framework event.
    */
    void handle_framework_event(const FrameworkEvent &event);

    /*
    @brief Handle priority client mod registration.
    @param elapsed_ms Current timeout progress in milliseconds.
    */
    void handle_priority_registration(int64_t elapsed_ms);

    /*
    @brief Handle regular client mod registration.
    @param elapsed_ms Current timeout progress in milliseconds.
    */
    void handle_registration(int64_t elapsed_ms);

    /*
    @brief Handle connecting to the AP server.
    @param elapsed_ms Current timeout progress in milliseconds.
    */
    void handle_connecting(int64_t elapsed_ms);

    /*
    @brief Handle syncing with the AP server.
    @param elapsed_ms Current timeout progress in milliseconds (currently unused).
    */
    void handle_syncing(int64_t elapsed_ms);

    /*
    @brief Handle active state.
    */
    void handle_active();

    /*
    @brief Handle resyncing with the AP server.
    @param elapsed_ms Current timeout progress in milliseconds (currently unused).
    */
    void handle_resyncing(int64_t elapsed_ms);

    /*
    * @brief Start the AP client and connect to the AP server.

        This function starts the AP client and connects to the AP server using the
        configuration provided in the FrameworkConfig.

        The AP client is configured with callbacks for room info, slot connected, and
        slot refused events. The callbacks are used to handle the events and start the
        syncing process.

        The function also starts a polling thread to periodically poll the AP server for
        new data.
    */
    void start_ap_connection();

    // ==========================================================================
    // Private Member Variables
    // ==========================================================================
    std::unique_ptr<sol::state_view> cached_lua_ = nullptr;

    AtomicState current_state_;
    std::chrono::steady_clock::time_point state_entered_at_;

    std::unique_ptr<APPollingThread> polling_thread_;

    // Note: APModRegistry, APCapabilities, APStateManager, APIPCServer,
    // APArchipelagoClient, and APMessageRouter are singletons accessed via their static get() methods

    bool state_loaded_ = false;
    bool reconnect_attempted_ = false;
    bool first_update_done_ = false;
    bool server_connected_ = false; // true when slot is connected to AP server

    // Async tracker snapshot — computed on background thread, delivered from handle_active()
    std::future<nlohmann::json> snapshot_cache_future_;
    std::optional<nlohmann::json> snapshot_cache_;
    std::vector<std::string> pending_snapshot_subscribers_;
};

} // namespace ap
