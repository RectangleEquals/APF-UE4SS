--[[
    PalworldArchipelagoTracker - Main Script

    In-game location accessibility tracker for Archipelago.
    Subscribes to the framework's tracker engine and receives:
    - TRACKER_SNAPSHOT: Full ecosystem metadata + current state (on subscribe)
    - TRACKER_UPDATE: Delta updates (on item received / location checked)

    Each location has a score (0.0-1.0) and a scored logic tree for
    per-expression UI coloring:
    - Green  (1.0): fully accessible
    - Yellow (0-1): partially accessible
    - Red    (0.0): inaccessible
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success_client, APClient = pcall(require, "APClientLib")
if not success_client then
    print("[APTracker] CRITICAL: Failed to load APClientLib.dll\n")
    print("[APTracker] Error: " .. tostring(APClient) .. "\n")
    return
end

-- Load registry helper for game-specific hooks
local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APTracker] CRITICAL: registry_helper.lua not found\n")
    return
end

-- Load UI bridge module
local success_ui, TrackerUI = pcall(require, "tracker_ui")
if not success_ui then
    print("[APTracker] WARNING: Failed to load tracker_ui.lua\n")
    print("[APTracker] Error: " .. tostring(TrackerUI) .. "\n")
    TrackerUI = nil
end

-- Load JSON parser for config file
local success_json, lunajson = pcall(require, "lunajson")
if not success_json then
    lunajson = nil
end

print("[APTracker] Libraries loaded successfully\n")
local obj_WebBrowser    = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
local obj_PalTimeManager = RH.add_object("/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C")

-- ============================================================================
-- Config Loading
-- ============================================================================

local tracker_config = nil
local config_path = "Mods/PalworldArchipelagoTracker/config.json"

local function load_config()
    if not lunajson then return nil end
    local f = io.open(config_path, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    local ok, parsed = pcall(lunajson.decode, content)
    if ok then
        return parsed
    else
        print("[APTracker] WARNING: Failed to parse config.json: " .. tostring(parsed) .. "\n")
        return nil
    end
end

tracker_config = load_config()

-- ============================================================================
-- State
-- ============================================================================

local is_registered = false
local tracker_subscribed = false
local tracker_data = nil  -- Full snapshot data (ecosystem + dynamic state)

-- ============================================================================
-- Update Loop
-- ============================================================================

local tick_time_last = os.clock()
local TICK_UPDATE_INTERVAL = 0.5  -- Faster polling for tracker responsiveness

local update = function()
    if not APClient then return end

    local now = os.clock()
    if now - tick_time_last < TICK_UPDATE_INTERVAL then
        return
    end
    tick_time_last = now

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

RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News.WBP_WebBrowser_News_C:Tick", on_news_tick)
RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick",                    on_title_tick)
RH.add_function(obj_PalTimeManager, "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C:Tick_BP",   on_ptm_tick)

-- ============================================================================
-- Tracker Data Helpers
-- ============================================================================

local function count_by_score(locations)
    if not locations then return 0, 0, 0 end
    local green, yellow, red = 0, 0, 0
    for _, loc in ipairs(locations) do
        if loc.checked then
            -- Skip checked locations from counts
        elseif loc.score >= 1.0 then
            green = green + 1
        elseif loc.score > 0.0 then
            yellow = yellow + 1
        else
            red = red + 1
        end
    end
    return green, yellow, red
end

local function log_tracker_summary()
    if not tracker_data or not tracker_data.locations then return end

    local green, yellow, red = count_by_score(tracker_data.locations)
    local checked = 0
    if tracker_data.checked_locations then
        for _ in pairs(tracker_data.checked_locations) do
            checked = checked + 1
        end
    end

    APClient.log("info", string.format(
        "Tracker: %d accessible, %d partial, %d blocked, %d checked",
        green, yellow, red, checked
    ))
end

-- ============================================================================
-- Tracker Callbacks
-- ============================================================================

APClient.on_tracker_snapshot(function(snapshot)
    APClient.log("info", "Tracker snapshot received\n")

    -- Tag each location with its original index for "Default" sort restoration
    if snapshot.locations then
        for i, loc in ipairs(snapshot.locations) do
            loc._sort_index = i
        end
    end

    tracker_data = snapshot
    log_tracker_summary()

    if TrackerUI then
        TrackerUI.set_data_ref(tracker_data)
        TrackerUI.push_full_snapshot(tracker_data)
    end
end)

APClient.on_tracker_update(function(delta)
    APClient.log("trace", "Tracker update received\n")

    if not tracker_data then
        -- No snapshot yet, request one
        APClient.subscribe_tracker()
        return
    end

    -- Merge delta into tracker_data
    if delta.locations then
        -- Build lookup by location_id for fast merge
        local loc_by_id = {}
        if tracker_data.locations then
            for i, loc in ipairs(tracker_data.locations) do
                loc_by_id[loc.id] = i
            end
        end

        for _, updated_loc in ipairs(delta.locations) do
            local idx = loc_by_id[updated_loc.id]
            if idx then
                tracker_data.locations[idx] = updated_loc
            end
        end
    end

    if delta.regions then
        local reg_by_name = {}
        if tracker_data.regions then
            for i, reg in ipairs(tracker_data.regions) do
                reg_by_name[reg.name] = i
            end
        end

        for _, updated_reg in ipairs(delta.regions) do
            local idx = reg_by_name[updated_reg.name]
            if idx then
                tracker_data.regions[idx] = updated_reg
            end
        end
    end

    if delta.received_items then
        tracker_data.received_items = delta.received_items
    end

    if delta.checked_locations then
        tracker_data.checked_locations = delta.checked_locations
    end

    log_tracker_summary()

    if TrackerUI then
        TrackerUI.push_delta_update(tracker_data, delta)
    end
end)

-- ============================================================================
-- Client Callbacks
-- ============================================================================

APClient.on_connect(function()
    APClient.log("info", "Connected to framework IPC\n")
end)

APClient.on_disconnect(function()
    APClient.log("warn", "Disconnected from framework IPC\n")
    is_registered = false
    tracker_subscribed = false
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    -- Register during REGISTRATION phase
    if state == "REGISTRATION" and not is_registered then
        if APClient.register_mod() then
            APClient.log("info", "Registration request sent\n")
        end
    end
end)

APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "Registered with framework\n")
end)

APClient.on_registration_rejected(function(reason)
    APClient.log("error", "Registration rejected: " .. (reason or "unknown") .. "\n")
end)

APClient.on_state_active(function()
    APClient.log("info", "Framework ACTIVE - subscribing to tracker\n")
    if not tracker_subscribed then
        if APClient.subscribe_tracker() then
            tracker_subscribed = true
            APClient.log("info", "Tracker subscription sent\n")
        else
            APClient.log("warn", "Failed to subscribe to tracker\n")
        end
    end
end)

APClient.on_state_error(function(message)
    APClient.log("error", "Framework ERROR: " .. (message or "unknown") .. "\n")
end)

APClient.on_error(function(code, message)
    APClient.log("error", "Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- ============================================================================
-- UI Initialization
-- ============================================================================

if TrackerUI then
    TrackerUI.init(APClient)
    TrackerUI.register_keybinds(tracker_config)
    APClient.log("info", "TrackerUI module initialized\n")
end

-- ============================================================================
-- IPC Initialization
-- ============================================================================

if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - framework may not be ready yet\n")
end
