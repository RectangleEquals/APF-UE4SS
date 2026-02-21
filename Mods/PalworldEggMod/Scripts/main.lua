--[[
    PalworldEggMod - Main Script

    Replaces Pal capturing with egg hatching/breeding when egg_mode is enabled.
    When active:
    - Pal Spheres are disabled (framework handles item type override)
    - Player receives a Pal Breeding License to enable breeding
    - Paldex entries are earned by hatching eggs at specific locations

    Requires: APClientLib, lunajson, registry_helper
    Depends: spectrecular.palworld.techshuffle (uses shared regions)
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success_json, json = pcall(require, "lunajson")
if not success_json then
    print("[EggMod] CRITICAL: lunajson not found\n")
    return
end

local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[EggMod] CRITICAL: Failed to load APClientLib.dll\n")
    print("[EggMod] Error: " .. tostring(APClient) .. "\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[EggMod] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[EggMod] APClientLib loaded successfully\n")

-- ============================================================================
-- Registry Helper Objects
-- ============================================================================

local obj_WebBrowser = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
local obj_PalTimeManager = RH.add_object(
    "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C")

-- ============================================================================
-- Namespace & State
-- ============================================================================

EggMod = EggMod or {}

local is_connected = false
local is_registered = false
local is_active = false
local has_breeding_license = false

-- ============================================================================
-- Action Handlers
-- ============================================================================

--- Grant the Pal Breeding License.
--- Enables the breeding farm and egg incubation mechanics.
EggMod.GrantBreedingLicense = function()
    if has_breeding_license then
        APClient.log("debug", "Breeding License already granted\n")
        return
    end

    has_breeding_license = true
    APClient.log("info", "Pal Breeding License granted!\n")

    -- TODO: UE4SS implementation
    -- Possible approaches:
    -- 1. Unlock breeding farm tech via PalSchema if not already unlocked
    -- 2. Set a game flag that enables breeding interactions
    -- 3. Modify player's breeding permission state
end

--- Disable pal sphere throwing when egg_mode is active.
--- Called during state sync to enforce the egg-only rule.
local function disable_pal_captures()
    -- TODO: UE4SS implementation
    -- Possible approaches:
    -- 1. Hook the sphere throw function and block it
    -- 2. Remove sphere items from inventory on pickup
    -- 3. Set capture success rate to 0
    APClient.log("info",
        "Pal capture disabled (pending UE4SS implementation)\n")
end

--- Re-enable pal sphere throwing (cleanup/disconnect).
local function enable_pal_captures()
    -- TODO: Mirror disable_pal_captures
    APClient.log("info",
        "Pal capture re-enabled (pending UE4SS implementation)\n")
end

-- ============================================================================
-- Update Loop
-- ============================================================================

local tick_time_now = os.clock()
local tick_time_last = tick_time_now
local TICK_UPDATE_INTERVAL = 1.0

local update = function()
    if not APClient then return end

    tick_time_now = os.clock()
    if tick_time_now - tick_time_last < TICK_UPDATE_INTERVAL then
        return
    end
    tick_time_last = tick_time_now

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

RH.add_function(obj_WebBrowser,
    "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News" ..
    ".WBP_WebBrowser_News_C:Tick", on_news_tick)
RH.add_function(obj_WebBrowser,
    "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick", on_title_tick)
RH.add_function(obj_PalTimeManager,
    "/Game/Pal/Blueprint/System/BP_PalTimeManager" ..
    ".BP_PalTimeManager_C:Tick_BP", on_ptm_tick)

-- ============================================================================
-- APClientLib Callbacks
-- ============================================================================

APClient.on_connect(function()
    is_connected = true
    APClient.log("info", "Connected to AP Framework\n")
end)

APClient.on_disconnect(function()
    is_connected = false
    is_registered = false
    is_active = false
    enable_pal_captures()
    APClient.log("warn", "Disconnected from AP Framework\n")
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    if state == "REGISTRATION" then
        if not is_registered then
            if APClient.register_mod() then
                APClient.log("info", "Registration request sent\n")
            end
        end
    elseif state == "ACTIVE" or state == "RESYNCING" then
        is_active = true
        -- When egg_mode is active, the framework will have filtered items
        -- accordingly. Disable captures if we're in egg mode.
        -- TODO: Check if egg_mode is active (infer from received items
        -- or wait for runtime option awareness feature)
        disable_pal_captures()
    elseif state == "ERROR_STATE" or state == "SHUTDOWN" then
        is_active = false
        enable_pal_captures()
    end
end)

APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "Successfully registered with AP Framework\n")
end)

APClient.on_registration_rejected(function(reason)
    APClient.log("error",
        "Registration rejected: " .. (reason or "unknown") .. "\n")
end)

APClient.on_item_received(function(item_id, item_name, sender)
    APClient.log("info", "Item received: " .. item_name ..
        " from " .. sender .. "\n")
    -- Action handlers are invoked automatically by APClientLib's action
    -- executor based on the manifest's action definitions.
end)

APClient.on_state_active(function()
    is_active = true
end)

APClient.on_state_error(function(error_info)
    APClient.log("error",
        "Framework error: " .. (error_info or "unknown") .. "\n")
    is_active = false
end)

APClient.on_error(function(code, message)
    APClient.log("error",
        "Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- ============================================================================
-- Initialization
-- ============================================================================

if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - will retry\n")
end
