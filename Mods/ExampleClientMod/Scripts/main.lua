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

-- ============================================================================
-- Module Loading
-- ============================================================================

-- Load the client library
local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[ExampleClientMod] CRITICAL: Failed to load APClientLib.dll")
    print("[ExampleClientMod] Error: " .. tostring(APClient))
    return
end

-- Load registry helper for game-specific hooks (optional)
local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[ExampleClientMod] Warning: registry_helper.lua not found")
    RH = nil
end

print("[ExampleClientMod] APClientLib loaded successfully")

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

    print("[ExampleClientMod] Received item: " .. item_name .. " from " .. sender)

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
-- In a real implementation, you might want APClientLib to expose these
local LOCATIONS = {
    "town_chest_1",
    "town_chest_2",
    "forest_hidden_item",
    "boss_room_treasure",
    "secret_area_prize"
}

local function check_all_locations()
    if not is_active then
        return  -- Don't check locations until framework is active
    end

    for _, location_id in ipairs(LOCATIONS) do
        if not checked_locations[location_id] then
            if check_location_condition(location_id) then
                -- Report the location check to the framework
                if APClient.check_location(location_id) then
                    checked_locations[location_id] = true
                    APClient.log("info", "Location checked: " .. location_id)
                end
            end
        end
    end
end

-- ============================================================================
-- APClientLib Callbacks
-- ============================================================================

-- Called when IPC connection to framework is established
APClient.on_connect(function()
    is_connected = true
    APClient.log("info", "Connected to AP Framework")
end)

-- Called when IPC connection is lost
APClient.on_disconnect(function()
    is_connected = false
    is_registered = false
    is_active = false
    APClient.log("warn", "Disconnected from AP Framework")
end)

-- Called on lifecycle state changes - this is the key callback for timing
APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or ""))

    if state == "REGISTRATION" then
        -- This is when regular clients should register
        if not is_registered then
            if APClient.register_mod() then
                APClient.log("info", "Registration request sent")
            else
                APClient.log("error", "Failed to send registration request")
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
    APClient.log("info", "Successfully registered with AP Framework")
end)

-- Called when registration is rejected
APClient.on_registration_rejected(function(reason)
    APClient.log("error", "Registration rejected: " .. (reason or "unknown"))
end)

-- Called when an item is received from the multiworld
APClient.on_item_received(function(item_id, item_name, sender)
    APClient.log("info", "Item received: " .. item_name .. " (id=" .. tostring(item_id) .. ") from " .. sender)
    apply_item_to_game(item_id, item_name, sender)
end)

-- Called when framework enters ACTIVE state
APClient.on_state_active(function()
    APClient.log("info", "Framework is now ACTIVE - location checking enabled")
    is_active = true
end)

-- Called when framework enters ERROR_STATE
APClient.on_state_error(function(error_info)
    APClient.log("error", "Framework error: " .. (error_info or "unknown"))
    is_active = false
end)

-- Called on errors
APClient.on_error(function(code, message)
    APClient.log("error", "Error [" .. (code or "?") .. "]: " .. (message or "unknown"))
end)

-- ============================================================================
-- Update Loop
-- ============================================================================

local function on_update()
    -- Process IPC messages and trigger callbacks
    APClient.update()

    -- Check locations (only runs if is_active is true)
    check_all_locations()
end

-- ============================================================================
-- Hook Registration
-- ============================================================================

local tick_registered = false

-- Try to use a standard tick hook
if RegisterHook then
    local success = pcall(function()
        RegisterHook("/Script/Engine.Actor:Tick", function(self, deltaTime)
            on_update()
        end)
    end)

    if success then
        tick_registered = true
        print("[ExampleClientMod] Registered Actor:Tick hook")
    end
end

if not tick_registered and RegisterCustomEvent then
    RegisterCustomEvent("Tick", function()
        on_update()
    end)
    tick_registered = true
    print("[ExampleClientMod] Registered custom Tick event")
end

if not tick_registered then
    print("[ExampleClientMod] WARNING: Could not register tick hook - updates may not work")
end

-- ============================================================================
-- Initialization
-- ============================================================================

-- Connect to framework IPC
-- Note: Connection may fail initially if framework isn't ready yet.
-- The library will handle retries according to framework_config.json timeouts.
if APClient.connect() then
    APClient.log("info", "IPC connection initiated")
else
    APClient.log("warn", "IPC connection failed - will retry")
end

print("[ExampleClientMod] Initialization complete - waiting for REGISTRATION lifecycle")
