#pragma once

#include "ap_callbacks.h"
#include "ap_ipc_client.h"

#include <chrono>
#include <memory>
#include <sol/sol.hpp>
#include <string>
#include <unordered_map>

namespace ap::client
{

/**
 * @brief Per-mod context owning all state associated with one require("APClientLib") call.
 *
 * Each mod that calls require("APClientLib") receives a Lua module bound to its own
 * APClientContext. This ensures callbacks, lifecycle state, and API call tracking are
 * fully isolated between mods, even when they share a single APClientLib.dll.
 *
 * Lifetime: owned by APClientManager::contexts_ (vector of unique_ptr). The raw pointer
 * is captured by Lua module lambdas, which remain valid for the DLL's lifetime.
 */
struct APClientContext
{
    // =========================================================================
    // Mod Identity (set at require() time from manifest)
    // =========================================================================

    std::string mod_id;
    std::string version;

    // =========================================================================
    // Lua State (set once in init(), stable for the mod's lifetime)
    // =========================================================================

    std::unique_ptr<sol::state_view> cached_lua;

    // =========================================================================
    // Per-Mod IPC Connection (each context owns its own pipe connection so the
    // server correctly names and routes messages per-mod, not per-DLL)
    // =========================================================================

    std::unique_ptr<ap::APIPCClient> ipc_client;

    // =========================================================================
    // Callbacks (single-slot: correct since each mod has its own instance)
    // =========================================================================

    APCallbacks callbacks;

    // =========================================================================
    // Lifecycle State (updated from IPC LIFECYCLE messages broadcast to all contexts)
    // =========================================================================

    std::string lifecycle_state = "UNINITIALIZED";

    // =========================================================================
    // Cross-Mod API State
    // =========================================================================

    std::unordered_map<std::string, sol::protected_function> api_callbacks;

    struct PendingCall
    {
        sol::protected_function callback;
        std::chrono::steady_clock::time_point created_at;
    };

    std::unordered_map<uint64_t, PendingCall> pending_api_calls;
    uint64_t next_call_id = 1;

    // =========================================================================

    APClientContext() = default;
    APClientContext(const APClientContext &) = delete;
    APClientContext &operator=(const APClientContext &) = delete;
};

} // namespace ap::client
