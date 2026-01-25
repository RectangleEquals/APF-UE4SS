#pragma once

#ifdef _WIN32
    #ifdef AP_CLIENTLIB_EXPORTS
        #define APCLIENT_API __declspec(dllexport)
    #else
        #define APCLIENT_API __declspec(dllimport)
    #endif
#else
    #define APCLIENT_API
#endif

// Forward declarations for Lua and sol2
struct lua_State;
namespace sol { class state_view; }

namespace ap::client {

    /**
     * Update the cached Lua state.
     * Should be called from the client library's update() function every tick.
     * @param L The current Lua state from UE4SS
     */
    APCLIENT_API void update_cached_lua(lua_State* L);

    /**
     * Get the cached Lua state for accessing UE4SS functions.
     * @return Pointer to cached sol::state_view, or nullptr if not initialized
     */
    APCLIENT_API sol::state_view* get_cached_lua();

} // namespace ap::client