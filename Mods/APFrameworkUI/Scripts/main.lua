--[[
    APFrameworkUI - Main Script

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

-- Load the client library (to register as a priority client)
local success_client, APClient = pcall(require, "APClientLib")
if not success_client then
    print("[APFrameworkUI] CRITICAL: Failed to load APClientLib.dll\n")
    print("[APFrameworkUI] Error: " .. tostring(APClient) .. "\n")
    return
end

-- Load registry helper for game-specific hooks
local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APFrameworkUI] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[APFrameworkUI] Libraries loaded successfully\n")
local obj_WebBrowser = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
local obj_PalTimeManager = RH.add_object("/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C")

-- ============================================================================
-- Update Loop
-- ============================================================================
local tick_time_now = os.clock()
local tick_time_last = tick_time_now
local tick_time_elapsed = 0
local TICK_UPDATE_INTERVAL = 1.0

local update = function()
    if not APClient then return end
    
    tick_time_now = os.clock()
    tick_time_elapsed = tick_time_now - tick_time_last
    if tick_time_elapsed < TICK_UPDATE_INTERVAL then
        -- print("[TICK]: " .. tick_time_elapsed .. "\n")
        return
    end
    
    tick_time_last = tick_time_now
    tick_time_elapsed = 0

    -- Uncomment for testing
    -- print("[APFrameworkUI]: Updating...\n")
    
    -- Update client lib (processes IPC messages, triggers callbacks)
    APClient.update()
end

-- ============================================================================
-- Hook Registration
-- ============================================================================
local on_news_tick = function(self, obj, geom, deltaTime)
	update()
end

local on_title_tick = function(self, obj, geom, deltaTime)
	update()
end

local on_ptm_tick = function(self, PalTimeManagerObj, deltaTime)
    update()
end

RH.add_function(obj_WebBrowser, "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News.WBP_WebBrowser_News_C:Tick", on_news_tick)
RH.add_function(obj_WebBrowser, "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick", on_title_tick)
RH.add_function(obj_PalTimeManager, "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C:Tick_BP", on_ptm_tick)

-- ============================================================================
-- State
-- ============================================================================

local is_registered = false
local framework_state = "UNINITIALIZED"

-- ============================================================================
-- Client Callbacks
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

-- Called when a command response is received from the framework
APClient.on_command_response(function(command, result)
    local success = result and result.success
    local err = result and result.error or ""
    if success then
        APClient.log("info", "Command '" .. command .. "' succeeded\n")
    else
        APClient.log("warn", "Command '" .. command .. "' failed: " .. err .. "\n")
    end
end)

-- ============================================================================
-- Keybind Hooks (Testing / Priority Client Commands)
-- ============================================================================

-- Target mod for simulation messages
local EXAMPLE_MOD_ID = "example.mygame.clientmod"

-- Location list for cycling through with keybinds
local test_locations = {
    { name = "Starting Chest",  instance = 1 },
    { name = "Boss Reward",     instance = 1 },
    { name = "Hidden Alcove",   instance = 1 },
    { name = "Shop Purchase",   instance = 1 },
    { name = "Shop Purchase",   instance = 2 },
    { name = "Shop Purchase",   instance = 3 },
}
local next_location_index = 1

-- F5: Resync with AP server
RegisterKeyBind(Key.F5, function()
    APClient.log("info", "[Keybind F5] Resync\n")
    APClient.command("resync")
end)

-- F6: Restart framework (back to DISCOVERY)
RegisterKeyBind(Key.F6, function()
    APClient.log("info", "[Keybind F6] Restart\n")
    APClient.command("restart")
end)

-- F7: Reconnect to AP server
RegisterKeyBind(Key.F7, function()
    APClient.log("info", "[Keybind F7] Reconnect\n")
    APClient.command("reconnect")
end)

-- F8: Regenerate YAML (re-export current config state)
RegisterKeyBind(Key.F8, function()
    APClient.log("info", "[Keybind F8] Regenerate YAML\n")
    APClient.command("regenerate")
end)

-- F9: Tell ExampleClientMod to check the next location
RegisterKeyBind(Key.F9, function()
    local loc = test_locations[next_location_index]
    if not loc then
        APClient.log("info", "[Keybind F9] All locations already sent, resetting index\n")
        next_location_index = 1
        loc = test_locations[next_location_index]
    end

    APClient.log("info", "[Keybind F9] Sending check_location: " .. loc.name .. " #" .. loc.instance .. "\n")
    APClient.command("send_to", {
        target_mod = EXAMPLE_MOD_ID,
        action = "check_location",
        location = loc.name,
        instance = loc.instance,
    })
    next_location_index = next_location_index + 1
end)

-- F10: Tell ExampleClientMod to check ALL remaining locations
RegisterKeyBind(Key.F10, function()
    APClient.log("info", "[Keybind F10] Sending check_all_locations to ExampleClientMod\n")
    APClient.command("send_to", {
        target_mod = EXAMPLE_MOD_ID,
        action = "check_all_locations",
    })
end)

-- ============================================================================
-- Initialization
-- ============================================================================

-- Connect to framework IPC (to self, as priority client)
if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - framework may not be ready yet\n")
end
