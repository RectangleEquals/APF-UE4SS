#include "ap_exports.h"
#include "ap_manager.h"

#include <sol/sol.hpp>

namespace ap {

// Cached Lua state for accessing UE4SS functions like IterateGameDirectories
static std::unique_ptr<sol::state_view> g_cached_lua = nullptr;

void update_cached_lua(lua_State* L) {
    if (L) {
        g_cached_lua = std::make_unique<sol::state_view>(L);
    }
}

sol::state_view* get_cached_lua() {
    return g_cached_lua.get();
}

} // namespace ap
