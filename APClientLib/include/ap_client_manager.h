#pragma once

#include "ap_client_context.h"
#include "ap_client_types.h"
#include "ap_exports.h"
#include "ap_manager_base.h"
#include "ap_manifest.h"

#include <memory>
#include <nlohmann/json.hpp>
#include <sol/sol.hpp>
#include <string>
#include <vector>

namespace ap::client
{

/**
 * @brief Global singleton coordinating APClientLib state across all loaded mods.
 *
 * APClientManager is the central coordinator for the shared APClientLib.dll. It:
 * - Owns a vector of APClientContext (one per require("APClientLib") call)
 * - Handles one-time setup: logger, config, IPC message/connect/disconnect handlers
 * - Dispatches incoming IPC messages to all relevant contexts
 * - Implements IAPManager for APManagerAccessor compatibility (APPathUtil, APLogger)
 *
 * Per-mod state (callbacks, lifecycle, API calls) lives in APClientContext — NOT here.
 *
 * Singleton Pattern: Pass-Key + Meyers
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
     */
    static APClientManager *get();

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * @brief Initialize for this require() caller and create its Lua module.
     * @param L Lua state from UE4SS.
     * @return Number of return values pushed to Lua stack (1 = the module table).
     *
     * Creates a new APClientContext for the calling mod (identified via debug.getinfo
     * on the Lua call stack). One-time setup (logger, IPC handlers) runs only on the
     * first call. Returns a Lua module table bound to this mod's context.
     */
    int init(lua_State *L);

    /**
     * @brief Poll IPC and clean up stale API calls (called each tick from Lua).
     */
    void update();

    /**
     * @brief Shutdown: disconnect IPC and clear all context callbacks.
     */
    void shutdown();

    // =========================================================================
    // IAPManager Interface
    // =========================================================================

    /**
     * @brief Get a Lua state for shared-singleton use (APPathUtil, APLogger).
     * @return Pointer to the first context's cached sol::state_view, or nullptr.
     *
     * Returns the first-loaded mod's (APFrameworkMod's) Lua state, which is correct
     * for the path/logger use cases that call this via APManagerAccessor.
     */
    sol::state_view *get_cached_lua() override;

    // =========================================================================
    // Manifest Access (first mod's manifest — kept for backward compat)
    // =========================================================================

    const APManifest &get_manifest() const;

  protected:
    // =========================================================================
    // Protected Methods (IAPManager)
    // =========================================================================

    int create_lua_module(lua_State *L) override;

  private:
    // =========================================================================
    // Private Methods
    // =========================================================================

    // Per-context IPC message dispatch (called from each context's ipc_client handler)
    void handle_ipc_message_for_context(APClientContext *ctx, const ap::ClientIPCMessage &msg);

    // Find a context by mod_id (returns nullptr if not found)
    APClientContext *find_context(const std::string &mod_id);

    // Per-mod Lua module creation
    int create_lua_module_impl(lua_State *L, APClientContext *ctx);

    // Cross-mod API helpers
    void invoke_api_call(APClientContext *ctx, const std::string &target_mod,
                         const std::string &func_name, sol::variadic_args va);
    void send_api_result(APClientContext *ctx, const std::string &target_mod,
                         uint64_t call_id, const nlohmann::json &result_json);
    void send_api_error(APClientContext *ctx, const std::string &target_mod,
                        uint64_t call_id, const std::string &error);
    static void cleanup_stale_api_calls(APClientContext &ctx);

    // =========================================================================
    // Private Member Variables
    // =========================================================================

    // One context per require("APClientLib") call — indexed by load order
    std::vector<std::unique_ptr<APClientContext>> contexts_;

    // First mod's manifest (kept for get_manifest() and ACTION_RESULT source fallback)
    APManifest manifest_;

    // One-time setup flag
    bool initialized_ = false;

    // Temporary Lua state for get_cached_lua() during init() before the first context
    // is pushed to contexts_. APPathUtil calls get_cached_lua() via APManagerAccessor
    // during load_current(), which runs before the context is created.
    std::unique_ptr<sol::state_view> temp_lua_;
};

} // namespace ap::client
