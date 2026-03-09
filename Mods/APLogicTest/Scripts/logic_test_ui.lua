--[[
    APLogicTest/Scripts/logic_test_ui.lua

    Owns actor/widget discovery and all WBP_LogicTestUI BP widget communication.
    Pattern mirrors tracker_ui.lua.

    Architecture:
    - init(client): called directly from main.lua at startup; stores APClient ref,
      gates ModActor discovery behind ClientRestart → InitLuaInterop hooks
    - on_snapshot(td): full tracker_data (map format) — pushes all locations to widget
    - on_update(td): updated tracker_data — repushes all locations
    - toggle_visible(): show/hide the panel
]] local M = {}

-- ============================================================================
-- Private State
-- ============================================================================

local APClient = nil -- stored from init()
local player_controller = nil -- cached PlayerController (validity-checked)
local widget = nil -- WBP_LogicTestUI (from actor:GetLogicTestUI())
local pending_td = nil -- tracker_data buffered before widget is ready

-- ============================================================================
-- Internal: Push Locations to Widget
-- ============================================================================

--- Push all locations from tracker_data to the widget.
--- @param td table  tracker_data in map format (see main.lua module header)
local function push_locations(td)
    if not widget then
        return
    end
    widget:ClearLocations()

    for loc_id, ldata in pairs(td.locations or {}) do
        -- Lua strings auto-convert to FString; no FText() wrapper needed.
        -- Widget BP converts FString → FText internally for display.
        widget:AddLocation(loc_id, ldata.name or tostring(loc_id), ldata.score or 0.0, ldata.checked or false)
    end

    widget:RefreshStatus()
end

-- ============================================================================
-- Init — Actor Discovery and Event Wiring
-- ============================================================================

--- Initialize the UI module. Called directly from main.lua at startup.
--- Gates ModActor discovery behind ClientRestart → InitLuaInterop hooks so
--- we never try to call BP functions before the world and actor exist.
--- @param client table  APClient reference (from APClientLib)
function M.init(client)
    APClient = client

    -- Location check event: fired by WBP_LogicTestButton when a row is clicked.
    -- Registered here (not top-level) so APClient is guaranteed to be set.
    RegisterCustomEvent("APLogicTest_ToLua_CheckLocation", function(location_id)
        local id = tonumber(location_id)
        if id then
            APClient.check_location(id)
            APClient.log("info", "Checked location: " .. tostring(id) .. "\n")
        end
    end)

    -- Gate ModActor discovery: only register InitLuaInterop hook after a valid
    -- PlayerController exists (i.e. a game session has started).
    RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(Context)
        if player_controller == nil or not player_controller:IsValid() then
            player_controller = Context:get()
            APClient.log("info", "[APLogicTest] Registering ModActor:InitLuaInterop\n")

            RegisterHook("/Game/Mods/APLogicTest/ModActor.ModActor_C:InitLuaInterop", function(actorContext)
                local actor = actorContext:get()
                if not actor or not actor:IsValid() then
                    return
                end

                local ok, w = pcall(function()
                    return actor:GetLogicTestUI()
                end)
                if not ok or not w then
                    return
                end
                widget = w
                APClient.log("info", "[APLogicTest] WBP_LogicTestUI acquired\n")

                -- Flush any tracker data that arrived before the widget was ready
                if pending_td then
                    push_locations(pending_td)
                    pending_td = nil
                end
            end)
        end
    end)
end

-- ============================================================================
-- Visibility
-- ============================================================================

function M.toggle_visible()
    if widget then
        widget:ToggleVisible()
    end
end

-- ============================================================================
-- Public: Tracker Callbacks (called from main.lua)
-- ============================================================================

--- Called by main.lua after a full tracker snapshot is merged.
--- @param td table  Complete tracker_data (map format)
function M.on_snapshot(td)
    if not widget then
        pending_td = td -- defer until init() acquires the widget
        return
    end
    push_locations(td)
end

--- Called by main.lua after a tracker update delta is merged.
--- @param td table  Updated tracker_data (map format, already merged)
function M.on_update(td)
    if not widget then
        pending_td = td -- replace pending with latest; no point buffering stale data
        return
    end
    -- Small location count (~12) — full rebuild on update is acceptable
    push_locations(td)
end

return M
