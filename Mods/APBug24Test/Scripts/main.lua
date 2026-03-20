--[[
    APBug24Test/Scripts/main.lua

    Minimal test mod for Bug 24 canonical union ID mapping verification.
    Has 3 items and 3 locations with different names from APLogicTest, but starting
    from the same id_base — so all IDs collide when both mods are in the same
    multiworld. Bug 24 fix must resolve these via canonical union mapping.

    Controls:
      F6 — check the next unchecked location sequentially (cycles through all 3)

    No UI widget, no tracker subscription.
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success_client, APClient = pcall(require, "APClientLib")
if not success_client then
    print("[APBug24Test] CRITICAL: Failed to load APClientLib.dll\n")
    print("[APBug24Test] Error: " .. tostring(APClient) .. "\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[APBug24Test] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[APBug24Test] Libraries loaded successfully\n")

-- ============================================================================
-- Tick Hooks
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

-- Location check cycling state
local location_names = {
    "B24: Station Alpha",
    "B24: Station Beta",
    "B24: Station Gamma",
}
local next_check_idx = 1

-- ============================================================================
-- Client Callbacks
-- ============================================================================

APClient.on_connect(function()
    APClient.log("info", "[APBug24Test] Connected to framework IPC\n")
end)

APClient.on_disconnect(function()
    APClient.log("warn", "[APBug24Test] Disconnected from framework IPC\n")
    is_registered = false
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "[APBug24Test] Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    if state == "REGISTRATION" and not is_registered then
        if APClient.register_mod() then
            APClient.log("info", "[APBug24Test] Registration request sent\n")
        end
    end
end)

APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "[APBug24Test] Registered with framework\n")
end)

APClient.on_registration_rejected(function(reason)
    APClient.log("error", "[APBug24Test] Registration rejected: " .. (reason or "unknown") .. "\n")
end)

APClient.on_state_active(function()
    APClient.log("info", "[APBug24Test] Framework ACTIVE — ready\n")
end)

APClient.on_item_received(function(item_id, item_name, sender, meta)
    local delivery_idx = meta and meta.delivery_index or "N/A"
    APClient.log("info", "[APBug24Test] Item received: " .. (item_name or tostring(item_id))
        .. " from " .. (sender or "?")
        .. " (delivery_index=" .. tostring(delivery_idx) .. ")\n")
end)

APClient.on_state_error(function(message)
    APClient.log("error", "[APBug24Test] Framework ERROR: " .. (message or "unknown") .. "\n")
end)

APClient.on_error(function(code, message)
    APClient.log("error", "[APBug24Test] Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- ============================================================================
-- Keybind — F6 checks the next location sequentially
-- ============================================================================

RegisterKeyBind(Key.F6, function()
    ExecuteInGameThread(function()
        if next_check_idx > #location_names then
            APClient.log("info", "[APBug24Test] All locations already checked!\n")
            return
        end

        local name = location_names[next_check_idx]
        APClient.log("info", "[APBug24Test] Checking location: " .. name
            .. " (" .. next_check_idx .. "/" .. #location_names .. ")\n")

        APClient.check_location(name)
        next_check_idx = next_check_idx + 1

        if next_check_idx > #location_names then
            APClient.log("info", "[APBug24Test] All locations checked!\n")
        end
    end)
end)

-- ============================================================================
-- Initialization
-- ============================================================================

APClient.log("info", "[APBug24Test] Keybinds registered (F6=check next location)\n")

if APClient.connect() then
    APClient.log("info", "[APBug24Test] IPC connection initiated\n")
else
    APClient.log("warn", "[APBug24Test] IPC connection failed — framework may not be ready yet\n")
end
