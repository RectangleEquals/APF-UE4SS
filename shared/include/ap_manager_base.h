#pragma once

#include "ap_exports.h"

/**
 * @file ap_manager_base.h
 * @brief Base interface for manager singletons (APManager, APClientManager).
 *
 * Both APFrameworkCore and APClientLib have a manager singleton that owns the Lua state.
 * This interface allows shared code (APPathUtil, APLogger) to access the Lua state
 * without creating circular dependencies.
 *
 * Usage:
 * - APManager (framework) and APClientManager (client) inherit from IAPManager
 * - On init, manager calls APManagerAccessor::set(this)
 * - Shared code calls APManagerAccessor::get()->get_cached_lua() to access Lua
 */

// Forward declare sol types to avoid pulling in full sol.hpp
namespace sol
{
class state_view;
} // namespace sol

struct lua_State;

namespace ap
{

/**
 * @brief Interface for manager singletons.
 *
 * Only manager singletons (APManager, APClientManager) should implement this.
 * They are the ONLY components that own/cache the Lua state.
 */
class AP_API IAPManager
{
  public:
    virtual ~IAPManager() = default;

    /**
     * @brief Get the cached Lua state.
     * @return Pointer to the cached Lua state_view, or nullptr if not available.
     *
     * The returned pointer is valid only while the manager singleton exists.
     * Callers should NEVER cache this pointer - always call get_cached_lua() when needed.
     */
    virtual sol::state_view *get_cached_lua() = 0;

  protected:
    /**
     * @brief Create the Lua module.
     * @param L Pointer to the Lua state.
     * @return Number of return values pushed to Lua stack.
     */
    virtual int create_lua_module(lua_State *L) = 0;
};

/**
 * @brief Accessor for the current manager singleton.
 *
 * This provides a way for shared code to access the manager without knowing
 * whether it's running in APFrameworkCore or APClientLib context.
 *
 * Thread Safety:
 * - set() should only be called once during initialization from the main thread
 * - get() can be called from any thread (returns the same pointer)
 * - The manager itself handles thread safety for Lua access
 */
class AP_API APManagerAccessor
{
  public:
    /**
     * @brief Set the current manager instance.
     * @param manager Pointer to the manager singleton.
     *
     * Should be called by the manager's init() method:
     *   APManagerAccessor::set(this);
     */
    static void set(IAPManager *manager)
    {
        instance_ = manager;
    }

    /**
     * @brief Get the current manager instance.
     * @return Pointer to the manager, or nullptr if not set.
     */
    static IAPManager *get()
    {
        return instance_;
    }

    /**
     * @brief Check if a manager is available.
     * @return true if set() has been called with a non-null manager.
     */
    static bool is_available()
    {
        return instance_ != nullptr;
    }

  private:
    static inline IAPManager *instance_ = nullptr;
};

} // namespace ap