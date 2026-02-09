--[[
    ExampleClientMod - Main Script

    This is an example client mod demonstrating proper APClientLib usage:
    1. Event-driven architecture using callbacks
    2. Lifecycle-aware registration (waits for REGISTRATION phase)
    3. Item handling via on_item_received callback
    4. Location checking only after ACTIVE state

    All mod metadata (mod_id, version, capabilities) is read from manifest.json
    by APClientLib internally - no need to hardcode values in Lua.
]]

local check_all_locations = function() end

-- ============================================================================
-- Module Loading
-- ============================================================================

-- Load JSON library for parsing forwarded IPC messages
local success_json, json = pcall(require, "lunajson")
if not success_json then
    print("[ExampleClientMod] WARNING: lunajson not found, IPC message handling disabled\n")
    json = nil
end

-- Load the client library
local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[ExampleClientMod] CRITICAL: Failed to load APClientLib.dll\n")
    print("[ExampleClientMod] Error: " .. tostring(APClient) .. "\n")
    return
end

-- Load registry helper for game-specific hooks (optional)
local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[ExampleClientMod] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[ExampleClientMod] APClientLib loaded successfully\n")
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
    -- print("[ExampleClientMod]: Updating...\n")
    
    -- Update client lib (processes IPC messages, triggers callbacks)
    APClient.update()
    check_all_locations()
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

local is_connected = false
local is_registered = false
local is_active = false  -- Only true when framework is in ACTIVE state

-- Track which locations have been checked (to avoid duplicate checks)
local checked_locations = {}

-- ============================================================================
-- Game Integration Callbacks (Implement these for your game)
-- ============================================================================

-- Called when an item is received from the multiworld
-- This is where you implement the actual game effect
local function apply_item_to_game(item_id, item_name, sender)
    -- TODO: Implement actual item application for your game
    -- Examples:
    -- - Unlock an ability
    -- - Add item to inventory
    -- - Increase a stat

    print("[ExampleClientMod] Received item: " .. item_name .. " from " .. sender .. "\n")

    -- Example implementations (commented out - replace with real game logic):
    -- if item_name == "sword_upgrade" then
    --     local player = get_player()
    --     player.sword_level = player.sword_level + 1
    -- elseif item_name == "double_jump_boots" then
    --     unlock_ability("double_jump")
    -- end
end

-- Called to check if a location has been reached in-game
-- Returns true if the location condition is met
local function check_location_condition(location_id)
    -- TODO: Implement actual location checking for your game
    -- This should check if the player has reached/completed a location

    -- Example implementations (commented out - replace with real game logic):
    -- if location_id == "town_chest_1" then
    --     return has_opened_chest("town_chest_1")
    -- elseif location_id == "boss_room_treasure" then
    --     return is_boss_defeated("first_boss") and has_opened_chest("boss_treasure")
    -- end

    return false  -- Default: location not reached
end

-- ============================================================================
-- Location Checking Logic
-- ============================================================================

-- List of locations this mod handles (from manifest.json capabilities)
local LOCATIONS = {
    { name = "Starting Chest",  instance = 1 },
    { name = "Boss Reward",     instance = 1 },
    { name = "Hidden Alcove",   instance = 1 },
    { name = "Shop Purchase",   instance = 1 },
    { name = "Shop Purchase",   instance = 2 },
    { name = "Shop Purchase",   instance = 3 },
}

-- Build a lookup key for deduplication
local function location_key(name, instance)
    return name .. "#" .. tostring(instance)
end

check_all_locations = function()
    if not is_active then
        return  -- Don't check locations until framework is active
    end

    for _, loc in ipairs(LOCATIONS) do
        local key = location_key(loc.name, loc.instance)
        if not checked_locations[key] then
            if check_location_condition(key) then
                if APClient.check_location(loc.name, loc.instance) then
                    checked_locations[key] = true
                    APClient.log("info", "Location checked: " .. loc.name .. " #" .. loc.instance .. "\n")
                end
            end
        end
    end
end

-- ============================================================================
-- Forwarded Message Handling (from priority clients via send_to/broadcast)
-- ============================================================================

local function handle_forwarded_message(payload)
    local action = payload.action
    if not action then return end

    if action == "check_location" then
        local name = payload.location
        local instance = tonumber(payload.instance) or 1
        if not name then
            APClient.log("warn", "check_location: missing 'location' field\n")
            return
        end

        local key = location_key(name, instance)
        if checked_locations[key] then
            APClient.log("info", "Location already checked: " .. name .. " #" .. instance .. "\n")
            return
        end

        APClient.log("info", "Simulating location check: " .. name .. " #" .. instance .. "\n")
        if APClient.check_location(name, instance) then
            checked_locations[key] = true
            APClient.log("info", "Location checked: " .. name .. " #" .. instance .. "\n")
        else
            APClient.log("warn", "Failed to check location: " .. name .. " #" .. instance .. "\n")
        end

    elseif action == "check_all_locations" then
        APClient.log("info", "Simulating check for all unchecked locations\n")
        for _, loc in ipairs(LOCATIONS) do
            local key = location_key(loc.name, loc.instance)
            if not checked_locations[key] then
                APClient.log("info", "Checking: " .. loc.name .. " #" .. loc.instance .. "\n")
                if APClient.check_location(loc.name, loc.instance) then
                    checked_locations[key] = true
                end
            end
        end

    else
        APClient.log("debug", "Unknown forwarded action: " .. tostring(action) .. "\n")
    end
end

-- ============================================================================
-- APClientLib Callbacks
-- ============================================================================

-- Called when IPC connection to framework is established
APClient.on_connect(function()
    is_connected = true
    APClient.log("info", "Connected to AP Framework\n")
end)

-- Called when IPC connection is lost
APClient.on_disconnect(function()
    is_connected = false
    is_registered = false
    is_active = false
    APClient.log("warn", "Disconnected from AP Framework\n")
end)

-- Called on lifecycle state changes - this is the key callback for timing
APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    if state == "REGISTRATION" then
        -- This is when regular clients should register
        if not is_registered then
            if APClient.register_mod() then
                APClient.log("info", "Registration request sent\n")
            else
                APClient.log("error", "Failed to send registration request\n")
            end
        end
    elseif state == "ACTIVE" then
        -- Framework is now active - safe to check locations
        is_active = true
    elseif state == "ERROR_STATE" or state == "SHUTDOWN" then
        -- Stop checking locations on error or shutdown
        is_active = false
    end
end)

-- Called when registration succeeds
APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "Successfully registered with AP Framework\n")
end)

-- Called when registration is rejected
APClient.on_registration_rejected(function(reason)
    APClient.log("error", "Registration rejected: " .. (reason or "unknown") .. "\n")
end)

-- Called when an item is received from the multiworld
APClient.on_item_received(function(item_id, item_name, sender)
    APClient.log("info", "Item received: " .. item_name .. " (id=" .. tostring(item_id) .. ") from " .. sender .. "\n")
    apply_item_to_game(item_id, item_name, sender)
end)

-- Called when framework enters ACTIVE state
APClient.on_state_active(function()
    APClient.log("info", "Framework is now ACTIVE - location checking enabled\n")
    is_active = true
end)

-- Called when framework enters ERROR_STATE
APClient.on_state_error(function(error_info)
    APClient.log("error", "Framework error: " .. (error_info or "unknown") .. "\n")
    is_active = false
end)

-- Called on errors
APClient.on_error(function(code, message)
    APClient.log("error", "Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- Called for ALL incoming IPC messages (including forwarded messages from priority clients)
APClient.on_message(function(msg_type, payload_json)
    -- Only handle forwarded ap_message types
    if msg_type ~= "ap_message" then return end
    if not json then return end

    local ok, payload = pcall(json.decode, payload_json)
    if not ok or type(payload) ~= "table" then return end

    -- Dispatch forwarded actions
    if payload.action then
        handle_forwarded_message(payload)
    end
end)

-- ============================================================================
-- Initialization
-- ============================================================================

-- Connect to framework IPC
-- Note: Connection may fail initially if framework isn't ready yet.
-- The library will handle retries according to framework_config.json timeouts.
if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - will retry\n")
end
