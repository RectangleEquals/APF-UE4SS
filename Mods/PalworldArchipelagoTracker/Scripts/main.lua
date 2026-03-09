--[[
    PalworldArchipelagoTracker - Main Script (Task 10 redesign)

    Subscribes to the AP Framework tracker engine.
    Owns merge logic (converting IPC array format to map format) and
    delegates all UI to tracker_ui.lua.

    tracker_data structure (maps, not arrays):
        tracker_data.locations = { [id] = {name, region, score, checked, logic_tree} }
        tracker_data.regions   = { [name] = {score, reachable, logic_tree, total, checked} }
        tracker_data.received_items = { [name] = count }
        tracker_data.checked_locations = { [id] = true }

    checked_set: local offline checks { [id] = true } — overlays server-side checked field
    so UI reflects checks immediately before the server confirms via TRACKER_UPDATE.
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

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APTracker] CRITICAL: registry_helper.lua not found\n")
    return
end

local success_ui, tracker_ui = pcall(require, "tracker_ui")
if not success_ui then
    print("[APTracker] WARNING: Failed to load tracker_ui.lua\n")
    print("[APTracker] Error: " .. tostring(tracker_ui) .. "\n")
    tracker_ui = nil
end

local success_json, lunajson = pcall(require, "lunajson")
if not success_json then
    lunajson = nil
end

print("[APTracker] Libraries loaded successfully\n")

local obj_WebBrowser     = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
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
local tracker_data  = nil   -- map-format tracker data (see module header)
local checked_set      = {}    -- local offline checks {[id]=true}

-- ============================================================================
-- Update Loop
-- ============================================================================

local tick_time_last = os.clock()
local TICK_UPDATE_INTERVAL = 0.5  -- seconds between APClient.update() calls

local function update()
    if not APClient then return end
    local now = os.clock()
    if now - tick_time_last < TICK_UPDATE_INTERVAL then return end
    tick_time_last = now
    APClient.update()
end

-- ============================================================================
-- Hook Registration (3 ticks: title news, title screen, in-world)
-- ============================================================================

local function on_tick() update() end

RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News.WBP_WebBrowser_News_C:Tick", on_tick)
RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick",                    on_tick)
RH.add_function(obj_PalTimeManager, "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C:Tick_BP",   on_tick)

-- ============================================================================
-- Tracker Data Merge Helpers
-- ============================================================================

--- Recompute total/checked location counts for all regions from the locations map.
local function recompute_region_counts(td)
    for _, rdata in pairs(td.regions) do
        rdata.total   = 0
        rdata.checked = 0
    end
    for _, ldata in pairs(td.locations) do
        local rdata = td.regions[ldata.region]
        if rdata then
            rdata.total = rdata.total + 1
            if ldata.checked then rdata.checked = rdata.checked + 1 end
        end
    end
end

--- Convert a full IPC tracker snapshot (array format) to map-format tracker_data.
--- @param payload table  Raw IPC TRACKER_SNAPSHOT payload
--- @return table         tracker_data in map format
local function merge_snapshot(payload)
    local td = {
        locations         = {},
        regions           = {},
        received_items    = payload.received_items or {},
        checked_locations = {},
    }

    -- Index regions by name
    for _, reg in ipairs(payload.regions or {}) do
        td.regions[reg.name] = {
            score      = reg.score,
            reachable  = reg.reachable,
            logic_tree = reg.logic_tree,
            total      = 0,
            checked    = 0,
        }
    end

    -- Index locations by id
    for _, loc in ipairs(payload.locations or {}) do
        td.locations[loc.id] = {
            name       = loc.name,
            region     = loc.display_region or "Main",
            score      = loc.score,
            checked    = loc.checked or false,
            logic_tree = loc.logic_tree,
        }
    end

    -- Build checked_locations set from snapshot array
    for _, id in ipairs(payload.checked_locations or {}) do
        td.checked_locations[id] = true
    end

    recompute_region_counts(td)
    return td
end

--- Merge a TRACKER_UPDATE delta into existing map-format tracker_data.
--- @param td    table  Existing tracker_data (map format)
--- @param delta table  Raw IPC TRACKER_UPDATE payload
--- @return table       Updated tracker_data
local function merge_update(td, delta)
    if not td then return merge_snapshot(delta) end

    -- Update changed locations
    for _, loc in ipairs(delta.locations or {}) do
        td.locations[loc.id] = {
            name       = loc.name,
            region     = loc.display_region or "Main",
            score      = loc.score,
            checked    = loc.checked or false,
            logic_tree = loc.logic_tree,
        }
    end

    -- Update changed regions (preserve existing total/checked; recompute below)
    for _, reg in ipairs(delta.regions or {}) do
        local rdata = td.regions[reg.name]
        if rdata then
            rdata.score      = reg.score
            rdata.reachable  = reg.reachable
            rdata.logic_tree = reg.logic_tree
        else
            td.regions[reg.name] = {
                score      = reg.score,
                reachable  = reg.reachable,
                logic_tree = reg.logic_tree,
                total      = 0,
                checked    = 0,
            }
        end
    end

    -- Update received_items if present in delta
    if delta.received_items then
        td.received_items = delta.received_items
    end

    -- Update checked_locations set from delta array (newly checked this update)
    for _, id in ipairs(delta.checked_locations or {}) do
        td.checked_locations[id] = true
    end

    recompute_region_counts(td)
    return td
end

-- ============================================================================
-- Logging Helper
-- ============================================================================

local function log_tracker_summary()
    if not tracker_data or not tracker_data.locations then return end
    local green, yellow, red, checked_count = 0, 0, 0, 0
    for _, ldata in pairs(tracker_data.locations) do
        if ldata.checked then
            checked_count = checked_count + 1
        elseif ldata.score >= 1.0 then
            green = green + 1
        elseif ldata.score > 0.0 then
            yellow = yellow + 1
        else
            red = red + 1
        end
    end
    APClient.log("info", string.format(
        "Tracker: %d accessible, %d partial, %d blocked, %d checked",
        green, yellow, red, checked_count))
end

-- ============================================================================
-- Tracker Callbacks
-- ============================================================================

APClient.on_tracker_snapshot(function(snapshot)
    APClient.log("info", "Tracker snapshot received\n")
    tracker_data = merge_snapshot(snapshot)
    log_tracker_summary()
    if tracker_ui then tracker_ui.push_all_data(tracker_data, checked_set) end
end)

APClient.on_tracker_update(function(delta)
    APClient.log("trace", "Tracker update received\n")
    if not tracker_data then
        -- No snapshot yet — request one
        APClient.subscribe_tracker()
        return
    end
    tracker_data = merge_update(tracker_data, delta)
    log_tracker_summary()
    if tracker_ui then tracker_ui.push_all_data(tracker_data, checked_set) end
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
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    -- Tracker matches the archipelago.*.* priority regex → register during PRIORITY_REGISTRATION
    if state == "PRIORITY_REGISTRATION" and not is_registered then
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
    APClient.log("info", "Framework ACTIVE — subscribing to tracker\n")
    if APClient.subscribe_tracker() then
        APClient.log("info", "Tracker subscription sent\n")
    else
        APClient.log("warn", "Failed to subscribe to tracker\n")
    end
end)

APClient.on_state_error(function(message)
    APClient.log("error", "Framework ERROR: " .. (message or "unknown") .. "\n")
end)

APClient.on_error(function(code, message)
    APClient.log("error", "Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- ============================================================================
-- Keybinds
-- ============================================================================

local DEFAULT_KEYBINDS = {
    toggle_panel = "F1",
    force_repush = "F5",
}

local function register_keybinds(config)
    local kb = config and config.keybinds or DEFAULT_KEYBINDS

    local toggle_key = Key[kb.toggle_panel] or Key.F1
    RegisterKeyBind(toggle_key, function()
        ExecuteInGameThread(function()
            if tracker_ui then tracker_ui.toggle_visible() end
        end)
    end)

    local repush_key = Key[kb.force_repush] or Key.F5
    RegisterKeyBind(repush_key, function()
        ExecuteInGameThread(function()
            if tracker_ui then tracker_ui.repush() end
        end)
    end)
end

-- ============================================================================
-- Actor Bridge — receives ModActor from BP InitLuaInterop custom event
-- ============================================================================

RegisterCustomEvent("APTracker_ToLua_InitUI", function(actor)
    if tracker_ui then tracker_ui.init(actor) end
end)

-- ============================================================================
-- Initialization
-- ============================================================================

register_keybinds(tracker_config)
APClient.log("info", "Tracker keybinds registered\n")

if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed — framework may not be ready yet\n")
end
