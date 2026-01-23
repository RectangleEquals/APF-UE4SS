#include <windows.h>
#include <sol/sol.hpp>
#include "ap_exports.h"
#include "ap_manager.h"

BOOL APIENTRY DllMain(HMODULE hModule, DWORD  ul_reason_for_call, LPVOID lpReserved) {
    return TRUE;
}

extern "C" AP_API int luaopen_APFrameworkCore(lua_State* L) {
    return ap::APManager::get()->init(L);
}