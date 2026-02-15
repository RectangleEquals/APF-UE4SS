--[[
    SatisfactoryProgressionMod - Main Script

    Example mod demonstrating AP Framework regions and logic:
    - Regions with item requirements (Desert requires Blade Runners, etc.)
    - requires_count on locations (HUB Milestones need N HUB Parts)
    - requires_option conditionals (hard drives, milestones)
    - Manifest-level option declarations (shuffle_hard_drives, milestone_shuffle)

    This is a skeleton — action handlers log messages instead of modifying game state.
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[SatisfactoryMod] CRITICAL: Failed to load APClientLib.dll\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[SatisfactoryMod] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[SatisfactoryMod] APClientLib loaded successfully\n")

-- ============================================================================
-- Action Handlers
-- ============================================================================

Satisfactory = Satisfactory or {}

Satisfactory.UnlockEquipment = function(equipment)
    APClient.log("info", "Unlocked equipment: " .. tostring(equipment) .. "\n")
end

Satisfactory.GrantHubPart = function()
    APClient.log("info", "Received HUB Part\n")
end

Satisfactory.GrantSlug = function(color)
    APClient.log("info", "Received " .. tostring(color) .. " Power Slug\n")
end

Satisfactory.GrantCoupons = function(amount)
    APClient.log("info", "Received " .. tostring(amount) .. " AWESOME Coupons\n")
end

Satisfactory.SpawnHostile = function(creature)
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
