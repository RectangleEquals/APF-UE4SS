#pragma once

#include <memory>

#ifdef _WIN32
    #ifdef AP_FRAMEWORK_EXPORTS
        #define AP_API __declspec(dllexport)
    #else
        #define AP_API __declspec(dllimport)
    #endif
#else
    #define AP_API
#endif

// Forward declarations for Lua and sol2
struct lua_State;
namespace sol { class state_view; }

namespace ap
{
    class APManager;
    extern std::unique_ptr<ap::APManager> g_ap_manager;

    // =========================================================================
    // Cached Lua State
    // =========================================================================

    /**
     * Update the cached Lua state.
     * Should be called from APManager::update() every tick.
     * @param L The current Lua state from UE4SS
     */
    AP_API void update_cached_lua(lua_State* L);

    /**
     * Get the cached Lua state for accessing UE4SS functions.
     * @return Pointer to cached sol::state_view, or nullptr if not initialized
     */
    AP_API sol::state_view* get_cached_lua();
}