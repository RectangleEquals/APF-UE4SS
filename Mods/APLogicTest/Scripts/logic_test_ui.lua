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

-- ─── Item Popup ────────────────────────────────────────────────────────────
local POPUP_DISPLAY_TIME = 5       -- seconds the popup remains fully visible

-- Popup state machine: "idle" | "fading_in" | "showing" | "fading_out"
local popup_state      = "idle"
local popup_widget     = nil       -- WBP_ItemPopup reference
local popup_show_time  = nil       -- os.time() when popup entered "showing"
local popup_item_queue = {}        -- items queued before widget is ready

-- ============================================================================
-- Internal: Item Popup Helpers
-- ============================================================================

local function popup_add_item(item_id, item_name, sender, is_self)
    if not popup_widget or not popup_widget:IsValid() then
        table.insert(popup_item_queue, {
            item_id = item_id, item_name = item_name, sender = sender, is_self = is_self
        })
        return
    end
    popup_widget:AddItem(item_id, item_name, sender, is_self)
end

local function popup_start_fade_in()
    if not popup_widget or not popup_widget:IsValid() then return end
    popup_state = "fading_in"
    popup_widget:FadeIn()
end

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
        -- out_of_logic: location pruned at generation (option logic simplified to ConstFalse).
        -- WBP_LogicTestUI:AddLocation must accept this 5th bool param to show grey/N-A/disabled state.
        if not ldata.out_of_logic or ldata.out_of_logic == false then
            widget:AddLocation(loc_id, ldata.name or tostring(loc_id), ldata.score or 0.0, ldata.checked or false)
        else
            APClient.log("debug", "[APLogicTest] Skipping OOL location: " .. (ldata.name or tostring(loc_id)) .. "\n")
        end
    end

    -- Goal status — score sent as 0–100 (Blueprint displays what it receives)
    local g = td.goal or {}
    if g.no_goal_mode then
        widget:SetGoalStatus("", "All In-Logic Locations", (g.score or 0.0) * 100)
    else
        widget:SetGoalStatus(g.name or "", g.display or "Goal", (g.score or 0.0) * 100)
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

    -- Gate ModActor discovery: only register InitLuaInterop hook after a valid
    -- PlayerController exists (i.e. a game session has started).
    RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(Context)
        if player_controller == nil or not player_controller:IsValid() then
            player_controller = Context:get()
            APClient.log("debug", "[APLogicTest] Registering ModActor:InitLuaInterop\n")

            RegisterHook("/Game/Mods/APLogicTest/ModActor.ModActor_C:InitLuaInterop", function(actorContext)
                APClient.log("info", "[APLogicTest] >>> InitLuaInterop (Lua)\n")
                local actor = actorContext:get()
                if not actor or not actor:IsValid() then
                    APClient.log("debug", "[APLogicTest] >>> InitLuaInterop (Lua): Invalid actor\n")
                    return
                end

                local w = actor.WBP_LogicTestUI_Inst
                if not w or not w:IsValid() then
                    APClient.log("debug", "[APLogicTest] >>> InitLuaInterop (Lua): Invalid UI widget\n")
                    return
                end
                widget = w
                APClient.log("info", "[APLogicTest] WBP_LogicTestUI acquired\n")

                -- Flush any tracker data that arrived before the widget was ready
                if pending_td then
                    push_locations(pending_td)
                    pending_td = nil
                end

                -- Acquire popup widget
                local pw = actor.WBP_ItemPopup_Inst
                if pw and pw:IsValid() then
                    popup_widget = pw
                    APClient.log("info", "[APLogicTest] WBP_ItemPopup acquired\n")
                    -- Flush any items received before the widget was ready
                    if #popup_item_queue > 0 then
                        for _, item in ipairs(popup_item_queue) do
                            popup_widget:AddItem(item.item_id, item.item_name, item.sender, item.is_self)
                        end
                        popup_item_queue = {}
                        popup_start_fade_in()
                    end
                end

                -- Animation finished hooks — BP fires these via ExecuteCustomEvent
                RegisterHook("/Game/Mods/APLogicTest/WBP_ItemPopup.WBP_ItemPopup_C:OnFadeInDone",
                    function()
                        if popup_state == "fading_in" then
                            popup_state    = "showing"
                            popup_show_time = os.time()
                        end
                    end)

                RegisterHook("/Game/Mods/APLogicTest/WBP_ItemPopup.WBP_ItemPopup_C:OnFadeOutDone",
                    function()
                        if popup_state == "fading_out" then
                            popup_state    = "idle"
                            popup_show_time = nil
                            if popup_widget and popup_widget:IsValid() then
                                popup_widget:Clear()
                            end
                        end
                    end)
            end)

            -- Location check event: fired by WBP_LogicTestButton when a row is clicked.
            -- Registered here (not top-level) so APClient is guaranteed to be set.
            RegisterHook("/Game/Mods/APLogicTest/WBP_LogicTestButton.WBP_LogicTestButton_C:APLogicTest_ToLua_CheckLocation", function(widgetContext, location_id)
                local id = location_id:get()
                APClient.log("debug", "[APLogicTest] >>> APLogicTest_ToLua_CheckLocation - " .. tostring(id) .. "\n")
                if id and id ~= 0 then
                    APClient.check_location(id)  -- integer; polymorphic check_location routes by ID
                    APClient.log("info", "Checked location: " .. APClient.get_location(id).name .. "\n")
                else
                    APClient.log("warn", "[APLogicTest] Invalid location_id from button\n")
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

-- ============================================================================
-- Public: Item Popup (called from main.lua on_item_received)
-- ============================================================================

--- Called by main.lua when an item is received.
--- Drives the popup state machine and marks the item handled+silenced.
--- @param client  table  APClient reference
--- @param item_id number Item ID
--- @param item_name string Item name
--- @param sender  string Sender slot name
--- @param meta    table  {location_id, is_self, handled_by}
function M.handle_item(client, item_id, item_name, sender, meta)
    if not client then return end

    local is_self = meta and meta.is_self or false

    -- Add item to popup (queued if widget not yet ready)
    popup_add_item(item_id, item_name, sender, is_self)

    -- Drive popup state machine
    if popup_state == "idle" then
        popup_start_fade_in()
    elseif popup_state == "showing" then
        popup_show_time = os.time()  -- reset display timer
    elseif popup_state == "fading_out" then
        popup_start_fade_in()  -- interrupt fade-out, show again with new item
    end
    -- fading_in: item already added; timer starts when FadeIn completes

    -- Mark handled + silence this specific delivery: reconnect/restart won't re-show this notification
    client.item_handled(item_id, true, meta and meta.delivery_index or -1)
end

--- Called every tick from main.lua. Drives popup auto-dismiss timer.
function M.tick()
    if popup_state == "showing" and popup_show_time then
        if os.time() - popup_show_time >= POPUP_DISPLAY_TIME then
            if popup_widget and popup_widget:IsValid() then
                popup_state    = "fading_out"
                popup_show_time = nil
                popup_widget:FadeOut()
            end
        end
    end
end

return M
