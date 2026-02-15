--[[
    DRGProgressionMod - Main Script

    Example mod demonstrating AP Framework advanced features:
    - requires_any on regions (Sandblasted needs Driller OR Engineer)
    - requires + requires_any combined (Magma Core needs Haz4 AND (Driller OR Scout))
    - requires_count on regions (Deep Dive needs 3 Blank Cores)
    - ^-prefixed items (^Blank Core, ^Overclock Token — suppress vocab warnings)
    - requires_option conditionals (overclocks, assignments)
    - Exact-match option conditionals (assignment_mode=All)

    This is a skeleton — action handlers log messages instead of modifying game state.
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[DRGMod] CRITICAL: Failed to load APClientLib.dll\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[DRGMod] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[DRGMod] APClientLib loaded successfully\n")

-- ============================================================================
-- Action Handlers
-- ============================================================================

DRG = DRG or {}

DRG.UnlockClass = function(class)
    APClient.log("info", "Unlocked class: " .. tostring(class) .. "\n")
end

DRG.UnlockHazard = function(level)
    APClient.log("info", "Unlocked Hazard " .. tostring(level) .. "\n")
end

DRG.UnlockEquipment = function(equipment)
    APClient.log("info", "Unlocked equipment: " .. tostring(equipment) .. "\n")
end

DRG.GrantCore = function(type)
    APClient.log("info", "Received " .. tostring(type) .. " core\n")
end

DRG.GrantOverclock = function()
    APClient.log("info", "Received overclock token\n")
end

DRG.GrantCredits = function(amount)
    APClient.log("info", "Received " .. tostring(amount) .. " credits\n")
end

DRG.GrantMinerals = function(amount)
    APClient.log("info", "Received " .. tostring(amount) .. " minerals\n")
end

DRG.SpawnHostile = function(creature)
    APClient.log("info", "TRAP: Spawned " .. tostring(creature) .. "!\n")
end

-- ============================================================================
-- State & Update Loop
-- ============================================================================

local is_active = false
local checked_locations = {}
local tick_time_last = os.clock()

local function update()
    if not APClient then return end
    local now = os.clock()
    if now - tick_time_last < 1.0 then return end
    tick_time_last = now
    APClient.update()
end

-- ============================================================================
-- APClientLib Callbacks
-- ============================================================================

APClient.on_connect(function()
    APClient.log("info", "Connected to AP Framework\n")
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")
    if state == "REGISTRATION" then
        APClient.register_mod()
    elseif state == "ACTIVE" then
        is_active = true
    elseif state == "ERROR_STATE" or state == "SHUTDOWN" then
        is_active = false
    end
end)

APClient.on_registration_success(function()
    APClient.log("info", "Registered with AP Framework\n")
end)

APClient.on_item_received(function(item_id, item_name, sender)
    APClient.log("info", "Item: " .. item_name .. " from " .. sender .. "\n")
end)

-- ============================================================================
-- Initialization
-- ============================================================================

if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - will retry\n")
end
