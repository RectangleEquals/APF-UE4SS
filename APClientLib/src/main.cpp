#include "ap_client_manager.h"
#include "ap_exports.h"

#include <windows.h>

// =============================================================================
// DLL Entry Points
// =============================================================================

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        break;
    case DLL_PROCESS_DETACH:
        ap::client::APClientManager::get()->shutdown();
        break;
    }
    return TRUE;
}

extern "C" AP_API int luaopen_APClientLib(lua_State *L)
{
    return ap::client::APClientManager::get()->init(L);
}