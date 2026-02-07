#pragma once

#include "ap_client_types.h"
#include "ap_exports.h"
#include "ap_manager_base.h"
#include "ap_manifest.h"

#include <memory>
#include <string>

namespace ap::client
{

/**
 * @brief Global singleton managing APClientLib state and components.
 *
 * The APClientManager is the central orchestrator for client mods that:
 * - Manages the cached Lua state (implements IAPManager)
 * - Owns an APManifest instance for this mod's manifest
 * - Tracks lifecycle state from framework messages
 *
 * Data Ownership:
 * - Lua state: Owned by this manager (implements IAPManager)
 * - Mod identity: Accessed via owned APManifest instance
 * - Config: Accessed via APConfig singleton (NOT owned)
 * - Logging: Delegated to APLogger singleton (NOT owned)
 * - IPC: Delegated to APIPCClient singleton (NOT owned)
 * - Actions: Delegated to APActionExecutor singleton (NOT owned)
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APClientManager : public IAPManager
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APClientManager;
        explicit ConstructorKey() = default;
    };

    explicit APClientManager(ConstructorKey);
    ~APClientManager();

    // Delete copy/move
    APClientManager(const APClientManager &) = delete;
    APClientManager &operator=(const APClientManager &) = delete;
    APClientManager(APClientManager &&) = delete;
    APClientManager &operator=(APClientManager &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APClientManager singleton.
     */
    static APClientManager *get();

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * @brief Initialize the manager and create Lua module (called from luaopen_APClientLib).
     * @param L Lua state from UE4SS.
     * @return Number of return values pushed to Lua stack (1 = the module table).
     *
     * This method:
     * - Caches the Lua state
     * - Registers with APManagerAccessor
     * - Loads config and manifest via shared singletons
     * - Initializes components
     * - Creates and returns the Lua module table
     */
    int init(lua_State *L);

    /**
     * @brief Update the manager (called each tick from Lua).
     * @param L Lua state.
     */
    void update(lua_State *L);

    /**
     * @brief Shutdown the manager.
     */
    void shutdown();

    // =========================================================================
    // IAPManager Interface
    // =========================================================================

    /**
     * @brief Get the cached Lua state (implements IAPManager).
     * @return Pointer to cached sol::state_view, or nullptr if not initialized.
     */
    sol::state_view *get_cached_lua() override;

    // =========================================================================
    // Manifest Access (owned instance)
    // =========================================================================

    /**
     * @brief Get this mod's manifest.
     * @return Reference to the manifest.
     */
    const APManifest &get_manifest() const;

    // =========================================================================
    // Lifecycle State (cached from framework)
    // =========================================================================

    const std::string &get_current_lifecycle_state() const;
    void set_current_lifecycle_state(const std::string &state);

  protected:
    // =========================================================================
    // Protected Methods
    // =========================================================================

    int create_lua_module(lua_State *L) override;

  private:
    // =========================================================================
    // Private Methods
    // =========================================================================

    void update_cached_lua(lua_State *L);
    void handle_ipc_message(const ap::ClientIPCMessage &msg);

    // =========================================================================
    // Private Member Variables (only data this manager OWNS)
    // =========================================================================

    // Lua state (implements IAPManager)
    std::unique_ptr<sol::state_view> cached_lua_;

    // Manifest for this mod (each client owns its own)
    APManifest manifest_;

    // Lifecycle state (cached from framework messages)
    std::string current_lifecycle_state_ = "UNINITIALIZED";

    // State
    bool initialized_ = false;
};

} // namespace ap::client