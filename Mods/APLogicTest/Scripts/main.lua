--[[
    APLogicTest/Scripts/main.lua

    Lifecycle, tick hooks, and tracker data routing.
    BP widget/actor communication owned by logic_test_ui.lua.

    This mod registers as a regular AP mod (not priority) using REGISTRATION.
    It has a mod_id that does NOT match the priority regex (spectrecular.*),
    so it registers during the normal REGISTRATION phase.
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success_client, APClient = pcall(require, "APClientLib")
if not success_client then
    print("[APLogicTest] CRITICAL: Failed to load APClientLib.dll\n")
    print("[APLogicTest] Error: " .. tostring(APClient) .. "\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APLogicTest] CRITICAL: registry_helper.lua not found\n")
    return
end

local success_ui, LogicTestUI = pcall(require, "logic_test_ui")
if not success_ui then
    print("[APLogicTest] WARNING: Failed to load logic_test_ui.lua\n")
    print("[APLogicTest] Error: " .. tostring(LogicTestUI) .. "\n")
    LogicTestUI = nil
    return
end

print("[APLogicTest] Libraries loaded successfully\n")

-- ============================================================================
-- Tick Hooks — same 3-stage pattern as tracker mod
-- ============================================================================

local obj_WebBrowser     = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
local obj_PalTimeManager = RH.add_object("/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C")

local tick_time_last = os.clock()
local TICK_UPDATE_INTERVAL = 0.5

local function on_tick()
    if not APClient then return end
    local now = os.clock()
    if now - tick_time_last < TICK_UPDATE_INTERVAL then return end
    tick_time_last = now
    APClient.update()
end

RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News.WBP_WebBrowser_News_C:Tick", on_tick)
RH.add_function(obj_WebBrowser,     "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick",                    on_tick)
RH.add_function(obj_PalTimeManager, "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C:Tick_BP",   on_tick)

-- ============================================================================
-- State
-- ============================================================================

local is_registered = false

-- Tracker data: map format (set by merge helpers below)
-- { locations={[id]={name,display_region,score,checked,logic_tree}},
--   regions={[name]={score,reachable,logic_tree,total,checked}},
--   received_items={[name]=count},
--   checked_locations={[id]=true} }
local tracker_data = nil

-- ============================================================================
-- Tracker Data Merge Helpers (same pattern as tracker mod)
-- ============================================================================

local function recompute_region_counts(td)
    for _, rdata in pairs(td.regions) do
        rdata.total   = 0
        rdata.checked = 0
    end
    for _, ldata in pairs(td.locations) do
        if not ldata.out_of_logic then  -- skip OOL locations from region totals
            local rdata = td.regions[ldata.display_region]
            if rdata then
                rdata.total = rdata.total + 1
                if ldata.checked then rdata.checked = rdata.checked + 1 end
            end
        end
    end
end

local function merge_snapshot(payload)
    local td = {
        locations         = {},
        regions           = {},
        received_items    = payload.received_items or {},
        checked_locations = {},
        goal              = payload.goal or { name = "", display = "", description = "", score = 0.0, no_goal_mode = true },
    }

    for _, reg in ipairs(payload.regions or {}) do
        td.regions[reg.name] = {
            score      = reg.score,
            reachable  = reg.reachable,
            logic_tree = reg.logic_tree,
            total      = 0,
            checked    = 0,
        }
    end

    for _, loc in ipairs(payload.locations or {}) do
        td.locations[loc.id] = {
            name           = loc.name,
            display_region = loc.display_region or "Main",
            score          = loc.score,
            checked        = loc.checked or false,
            logic_tree     = loc.logic_tree,
            out_of_logic   = loc.out_of_logic or false,
        }
    end

    for _, id in ipairs(payload.checked_locations or {}) do
        td.checked_locations[id] = true
    end

    -- Re-sync: ensure td.locations reflects checked_locations (snapshot's per-location
    -- checked field may be false even for already-checked locations on reconnect).
    for id, _ in pairs(td.checked_locations) do
        if td.locations[id] then
            td.locations[id].checked = true
        end
    end

    recompute_region_counts(td)
    return td
end

local function merge_update(td, delta)
    if not td then return merge_snapshot(delta) end

    for _, loc in ipairs(delta.locations or {}) do
        td.locations[loc.id] = {
            name           = loc.name,
            display_region = loc.display_region or "Main",
            score          = loc.score,
            checked        = loc.checked or false,
            logic_tree     = loc.logic_tree,
            out_of_logic   = loc.out_of_logic or false,
        }
    end

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

    if delta.received_items then
        td.received_items = delta.received_items
    end

    if delta.goal then
        td.goal = delta.goal
    end

    for _, id in ipairs(delta.checked_locations or {}) do
        td.checked_locations[id] = true
    end

    -- Re-sync: checked_locations is authoritative — a delta replacing a location entry
    -- must not un-check a location the player already checked (C++ sends checked:false
    -- when accessibility changes, not as a statement about prior check state).
    for id, _ in pairs(td.checked_locations) do
        if td.locations[id] then
            td.locations[id].checked = true
        end
    end

    recompute_region_counts(td)
    return td
end

-- ============================================================================
-- Tracker Callbacks
-- ============================================================================

APClient.on_tracker_snapshot(function(snapshot)
    APClient.log("info", "Tracker snapshot received\n")
    tracker_data = merge_snapshot(snapshot)
    if LogicTestUI then LogicTestUI.on_snapshot(tracker_data) end
end)

APClient.on_tracker_update(function(delta)
    APClient.log("trace", "Tracker update received\n")
    tracker_data = merge_update(tracker_data, delta)
    if LogicTestUI then LogicTestUI.on_update(tracker_data) end
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

    -- spectrecular.* mod_id does NOT match priority regex → register during REGISTRATION
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
-- Keybind — F2 toggles the logic test panel
-- ============================================================================

RegisterKeyBind(Key.F2, function()
    ExecuteInGameThread(function()
        APClient.log("debug", "Toggling UI...\n")
        if LogicTestUI then LogicTestUI.toggle_visible() end
    end)
end)

-- ============================================================================
-- Initialization
-- ============================================================================

APClient.log("info", "APLogicTest keybinds registered (F2=toggle)\n")

if LogicTestUI then
    LogicTestUI.init(APClient)
    APClient.log("info", "LogicTestUI module initialized\n")
end

if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed — framework may not be ready yet\n")
end
