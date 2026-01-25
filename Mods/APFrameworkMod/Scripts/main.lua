--[[
    APFrameworkMod - Main Script

    This is the framework mod that:
    1. Initializes APFrameworkCore (the C++ backend for AP server connection)
    2. Loads APClientLib to register as a priority client
    3. Provides console commands via priority client privileges

    Framework-level logic is handled by APFrameworkCore C++.
    This Lua script is minimal - just initialization, hooks, and update calls.
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

-- Load the framework core library (handles AP server connection, IPC server, etc.)
local success_core, APFramework = pcall(require, "APFrameworkCore")
if not success_core then
    print("[APFrameworkMod] CRITICAL: Failed to load APFrameworkCore.dll\n")
    print("[APFrameworkMod] Error: " .. tostring(APFramework) .. "\n")
    return
end

-- Load the client library (to register as a priority client)
local success_client, APClient = pcall(require, "APClientLib")
if not success_client then
    print("[APFrameworkMod] CRITICAL: Failed to load APClientLib.dll\n")
    print("[APFrameworkMod] Error: " .. tostring(APClient) .. "\n")
    return
end

-- Load registry helper for game-specific hooks
local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APFrameworkMod] Warning: registry_helper.lua not found, using fallback tick\n")
    RH = nil
end

print("[APFrameworkMod] Libraries loaded successfully\n")

-- ============================================================================
-- State
-- ============================================================================

local is_registered = false
local framework_state = "UNINITIALIZED"

-- ============================================================================
-- Callbacks
-- ============================================================================

-- Called when IPC connection to framework is established
APClient.on_connect(function()
    APClient.log("info", "Connected to framework IPC\n")
end)

-- Called when IPC connection is lost
APClient.on_disconnect(function()
    APClient.log("warn", "Disconnected from framework IPC\n")
    is_registered = false
end)

-- Called on lifecycle state changes
APClient.on_lifecycle(function(state, message)
    framework_state = state
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    -- Register during PRIORITY_REGISTRATION phase
    if state == "PRIORITY_REGISTRATION" and not is_registered then
        if APClient.register_mod() then
            APClient.log("info", "Registration request sent\n")
        else
            APClient.log("error", "Failed to send registration request\n")
        end
    end
end)

-- Called when registration succeeds
APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "Successfully registered as priority client\n")
end)

-- Called when registration is rejected
APClient.on_registration_rejected(function(reason)
    APClient.log("error", "Registration rejected: " .. (reason or "unknown") .. "\n")
end)

-- Called on errors
APClient.on_error(function(code, message)
    APClient.log("error", "Framework error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- Called when framework enters ACTIVE state
APClient.on_state_active(function()
    APClient.log("info", "Framework is now ACTIVE\n")
end)

-- Called when framework enters ERROR_STATE
APClient.on_state_error(function(error_info)
    APClient.log("error", "Framework entered ERROR_STATE: " .. (error_info or "unknown") .. "\n")
end)

-- ============================================================================
-- Update Loop
-- ============================================================================
local tick_registered = false
local tick_time_now = os.clock()
local tick_time_last = tick_time_now
local tick_time_elapsed = 0
local TICK_UPDATE_INTERVAL = 1.0

local function on_update()
    tick_time_now = os.clock()
    tick_time_elapsed = tick_time_now - tick_time_last
    if tick_time_elapsed < TICK_UPDATE_INTERVAL then
        -- print("[TICK]: " .. tick_time_elapsed .. "\n")
        return
    end
    
    tick_time_last = tick_time_now
    tick_time_elapsed = 0

    print("[APFrameworkMod]: Updating...\n")

    -- print("[APFrameworkMod]: Updating framework core...\n")
    -- Update framework core (processes AP server messages)
    APFramework.update()

    -- print("[APFrameworkMod]: Updating client lib...\n")
    -- Update client lib (processes IPC messages, triggers callbacks)
    APClient.update()
end

-- ============================================================================
-- Hook Registration
-- ============================================================================

-- Try to use a standard tick hook
-- Games may need different hooks - modify as needed for your game
if RegisterHook then
    -- Try Actor Tick hook
    local success = pcall(function()
        RegisterHook("/Script/Engine.Actor:Tick", function(self, deltaTime)
            on_update()
        end)
    end)

    if success then
        tick_registered = true
        print("[APFrameworkMod] Registered Actor:Tick hook\n")
    end
end

if not tick_registered and RegisterCustomEvent then
    -- Fallback to custom Tick event
    RegisterCustomEvent("Tick", function()
        on_update()
    end)
    tick_registered = true
    print("[APFrameworkMod] Registered custom Tick event\n")
end

if not tick_registered then
    print("[APFrameworkMod] WARNING: Could not register tick hook - updates may not work\n")
end

-- ============================================================================
-- Console Commands (Priority Client Privileges)
-- ============================================================================

if RegisterConsoleCommandHandler then
    -- ap_status - Show current framework status
    RegisterConsoleCommandHandler("ap_status", function(FullCommand, Parameters)
        print("[AP] Framework State: " .. framework_state)
        print("[AP] Registered: " .. tostring(is_registered))
        print("[AP] IPC Connected: " .. tostring(APClient.is_connected()))
        return true
    end)

    -- ap_restart - Restart the framework (priority client command)
    RegisterConsoleCommandHandler("ap_restart", function(FullCommand, Parameters)
        print("[AP] Restart command not yet implemented\n")
        return true
    end)

    -- ap_resync - Force resync (priority client command)
    RegisterConsoleCommandHandler("ap_resync", function(FullCommand, Parameters)
        print("[AP] Resync command not yet implemented\n")
        return true
    end)

    print("[APFrameworkMod] Console commands registered\n")
end

-- ============================================================================
-- Initialization
-- ============================================================================

-- Initialize framework core
if APFramework.initialize then
    local init_result = APFramework.initialize()
    if init_result then
        APClient.log("info", "APFrameworkCore initialized\n")
    else
        APClient.log("error", "APFrameworkCore initialization failed\n")
    end
end

-- Connect to framework IPC (to self, as priority client)
if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - framework may not be ready yet\n")
end

print("[APFrameworkMod] Initialization complete\n")
