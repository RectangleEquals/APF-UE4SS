--[[
    PalworldTechShuffle - Main Script

    Tech tree randomizer for Palworld using PalSchema.
    Locks/hides all shuffled technologies on game start, then unlocks them
    individually as AP items are received.

    Modes:
    - locked: Sets LevelCap to 999 (techs visible but unpurchasable)
    - hidden: Deletes tech rows (techs invisible until unlocked)

    Requires: APClientLib, PalSchema, lunajson, registry_helper
]]

-- ============================================================================
-- Module Loading
-- ============================================================================

local success_json, json = pcall(require, "lunajson")
if not success_json then
    print("[TechShuffle] CRITICAL: lunajson not found\n")
    return
end

local success, APClient = pcall(require, "APClientLib")
if not success then
    print("[TechShuffle] CRITICAL: Failed to load APClientLib.dll\n")
    print("[TechShuffle] Error: " .. tostring(APClient) .. "\n")
    return
end

local success_rh, RH = pcall(require, "registry_helper")
if not success_rh then
    print("[TechShuffle] CRITICAL: registry_helper.lua not found\n")
    return
end

print("[TechShuffle] APClientLib loaded successfully\n")

-- ============================================================================
-- Registry Helper Objects
-- ============================================================================

local obj_WebBrowser = RH.add_object("/Script/WebBrowserWidget.WebBrowser")
local obj_PalTimeManager = RH.add_object(
    "/Game/Pal/Blueprint/System/BP_PalTimeManager.BP_PalTimeManager_C")

-- ============================================================================
-- Namespace & State
-- ============================================================================

TechShuffle = TechShuffle or {}

local unlocked_techs = {}       -- { [tech_id] = true }
local all_tech_ids = {}         -- Array of all tech IDs from database
local is_connected = false
local is_registered = false
local is_active = false
local db_ready = false
local palschema_dir = nil       -- Path to PalSchema/mods/TechShuffle/raw/

-- ============================================================================
-- Utilities
-- ============================================================================

local function table_count(t)
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    return count
end

-- ============================================================================
-- Path Resolution
-- ============================================================================

local function resolve_palschema_dir()
    -- PalSchema mods directory is alongside TechShuffle in the Mods folder
    -- Typical: <game>/Pal/Binaries/Win64/Mods/PalSchema/mods/
    local script_dir = debug.getinfo(1, "S").source:match("@?(.+[/\\])")
    if not script_dir then
        APClient.log("warn", "Could not determine script directory\n")
        return nil
    end

    -- Go up from Scripts/ to mod root, then navigate to PalSchema
    local mods_dir = script_dir:match("(.+[/\\])PalworldTechShuffle[/\\]")
    if mods_dir then
        local dir = mods_dir .. "PalSchema\\mods\\TechShuffle\\raw\\"
        return dir
    end

    APClient.log("warn", "Could not resolve PalSchema mods directory\n")
    return nil
end

local function resolve_db_path()
    local script_dir = debug.getinfo(1, "S").source:match("@?(.+[/\\])")
    if script_dir then
        return script_dir .. "palworld_tech.db"
    end
    return nil
end

-- ============================================================================
-- Database Access (requires APClientLib SQLite support — pending)
-- ============================================================================

local function init_database()
    local db_path = resolve_db_path()
    if not db_path then
        APClient.log("warn", "Could not find palworld_tech.db\n")
        return false
    end

    -- db_open/db_query/db_close will be added to APClientLib in a future update
    if not APClient.db_open then
        APClient.log("warn",
            "APClientLib db_open not available yet - database features disabled\n")
        return false
    end

    local ok = APClient.db_open(db_path)
    if not ok then
        APClient.log("error", "Failed to open database: " .. db_path .. "\n")
        return false
    end

    -- Load all tech IDs for initial lock-all
    local results = APClient.db_query(
        "SELECT tech_id, level_cap FROM techs ORDER BY level_cap, tech_id")
    if results then
        all_tech_ids = {}
        for _, row in ipairs(results) do
            table.insert(all_tech_ids, row.tech_id)
        end
        APClient.log("info",
            "Loaded " .. #all_tech_ids .. " tech IDs from database\n")
    end

    return true
end

local function query_tech(tech_id)
    if not APClient.db_query then return nil end
    -- Escape single quotes in tech_id for SQL safety
    local safe_id = tech_id:gsub("'", "''")
    local results = APClient.db_query(
        "SELECT * FROM techs WHERE tech_id = '" .. safe_id .. "' LIMIT 1")
    if results and #results > 0 then
        return results[1]
    end
    return nil
end

-- ============================================================================
-- PalSchema File Management
-- ============================================================================

local function ensure_dir(path)
    os.execute('mkdir "' .. path .. '" 2>NUL')
end

local function write_palschema(filename, content)
    if not palschema_dir then
        APClient.log("warn", "PalSchema directory not resolved - skipping write\n")
        return false
    end

    ensure_dir(palschema_dir)
    local filepath = palschema_dir .. filename
    local file = io.open(filepath, "w")
    if file then
        file:write(content)
        file:close()
        return true
    else
        APClient.log("error", "Failed to write PalSchema file: " .. filepath .. "\n")
        return false
    end
end

--- Rebuild both PalSchema JSON files from current unlock state.
--- Called on ACTIVE/RESYNCING lifecycle and after each unlock.
--- This is the state sync mechanism - guarantees recovery from
--- crashes, disconnects, or stale state.
local function rebuild_palschema_state()
    if #all_tech_ids == 0 then
        APClient.log("warn", "No tech IDs loaded - cannot rebuild PalSchema state\n")
        return
    end

    local locks = {}
    local unlocks = {}

    for _, tech_id in ipairs(all_tech_ids) do
        if unlocked_techs[tech_id] then
            -- Restore this tech to its original level_cap
            local tech_data = query_tech(tech_id)
            if tech_data then
                unlocks[tech_id] = { LevelCap = tech_data.level_cap }
            else
                -- Fallback: set LevelCap to 1 (always purchasable)
                unlocks[tech_id] = { LevelCap = 1 }
            end
        else
            -- Lock: set LevelCap to 999 (visible but unpurchasable)
            locks[tech_id] = { LevelCap = 999 }
        end
    end

    -- PalSchema processes files alphabetically per mod:
    -- tech_locks.json applies first, tech_unlocks.json overrides
    write_palschema("tech_locks.json",
        json.encode({ DT_TechnologyRecipeUnlock = locks }))
    write_palschema("tech_unlocks.json",
        json.encode({ DT_TechnologyRecipeUnlock = unlocks }))

    local unlocked_count = table_count(unlocked_techs)
    APClient.log("info", "PalSchema state rebuilt: " ..
        tostring(#all_tech_ids - unlocked_count) .. " locked, " ..
        tostring(unlocked_count) .. " unlocked\n")

    -- Refresh tech tree UI on game thread
    if ExecuteInGameThread then
        ExecuteInGameThread(TechShuffle.RefreshUI)
    end
end

-- ============================================================================
-- Action Handlers (called by APClientLib action executor)
--
-- The action executor resolves paths like "TechShuffle.UnlockTech" by
-- navigating lua["TechShuffle"]["UnlockTech"] in the global table.
-- Arguments are passed directly from the manifest's action args.
-- ============================================================================

--- Unlock a specific technology by tech_id.
--- Called when player receives a "Tech Unlock: <tech_id>" item.
TechShuffle.UnlockTech = function(tech_id)
    if unlocked_techs[tech_id] then
        APClient.log("debug", "Tech already unlocked: " .. tech_id .. "\n")
        return
    end

    unlocked_techs[tech_id] = true
    APClient.log("info", "Unlocked tech: " .. tech_id .. "\n")

    if is_active and #all_tech_ids > 0 then
        rebuild_palschema_state()
    end
end

--- Tier key received. This is an AP logic item that gates regions in the
--- multiworld. Individual tech unlocks are sent as separate items placed
--- within tier regions.
TechShuffle.UnlockTier = function(tier)
    APClient.log("info", "Tier " .. tostring(tier) .. " key received\n")
end

--- Boss victory registered. This is an AP logic item that gates post-boss
--- regions. Actual boss defeat detection is done via location checking.
TechShuffle.OnBossVictory = function(boss)
    APClient.log("info", "Boss victory registered: " .. tostring(boss) .. "\n")
end

--- Grant tech points to the player (filler item).
TechShuffle.GrantTechPoints = function(amount)
    -- TODO: Find UE4SS function to add tech points to player
    APClient.log("info",
        "Tech Points +" .. tostring(amount) ..
        " (pending UE4SS implementation)\n")
end

--- Trigger a pal raid on the player's base (trap item).
TechShuffle.TriggerRaid = function()
    -- TODO: Find UE4SS function to trigger pal raid
    APClient.log("info",
        "Pal Raid trap triggered! (pending UE4SS implementation)\n")
end

-- ============================================================================
-- Tech Tree UI Refresh
-- ============================================================================

local tech_ui = nil
local player_controller = nil

function TechShuffle.RefreshUI()
    if tech_ui and tech_ui:IsValid() then
        -- Apply a null filter to force the tech tree to re-evaluate all entries
        local item_types = {1, 2, 3, 4, 5, 6, 7, 9, 10, 13}
        local build_types = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
        tech_ui["Apply Technology Filter"](
            tech_ui, FText(""), item_types, build_types, true)
        APClient.log("debug", "Tech tree UI refreshed\n")
    end
end

-- Capture the tech tree UI widget when it's constructed
RegisterHook(
    "/Script/Engine.PlayerController:ClientRestart",
    function(Context)
        if not player_controller or not player_controller:IsValid() then
            player_controller = Context:get()
            RegisterHook(
                "/Game/Pal/Blueprint/UI/UserInterface/MainMenu/Technology/" ..
                "WBP_MainMenu_Technology_00.WBP_MainMenu_Technology_00_C:Construct",
                function(Ctx)
                    tech_ui = Ctx:get()
                    APClient.log("info", "Tech tree UI widget captured\n")
                end)
        end
    end)

-- ============================================================================
-- Update Loop
-- ============================================================================

local tick_time_now = os.clock()
local tick_time_last = tick_time_now
local TICK_UPDATE_INTERVAL = 1.0

local update = function()
    if not APClient then return end

    tick_time_now = os.clock()
    if tick_time_now - tick_time_last < TICK_UPDATE_INTERVAL then
        return
    end
    tick_time_last = tick_time_now

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

RH.add_function(obj_WebBrowser,
    "/Game/Pal/Blueprint/UI/Title/WBP_WebBrowser_News" ..
    ".WBP_WebBrowser_News_C:Tick", on_news_tick)
RH.add_function(obj_WebBrowser,
    "/Game/Pal/Blueprint/UI/Title/WBP_TItle.WBP_TItle_C:Tick", on_title_tick)
RH.add_function(obj_PalTimeManager,
    "/Game/Pal/Blueprint/System/BP_PalTimeManager" ..
    ".BP_PalTimeManager_C:Tick_BP", on_ptm_tick)

-- ============================================================================
-- APClientLib Callbacks
-- ============================================================================

APClient.on_connect(function()
    is_connected = true
    APClient.log("info", "Connected to AP Framework\n")
end)

APClient.on_disconnect(function()
    is_connected = false
    is_registered = false
    is_active = false
    APClient.log("warn", "Disconnected from AP Framework\n")
end)

APClient.on_lifecycle(function(state, message)
    APClient.log("info", "Lifecycle: " .. state .. " - " .. (message or "") .. "\n")

    if state == "REGISTRATION" then
        if not is_registered then
            if APClient.register_mod() then
                APClient.log("info", "Registration request sent\n")
            end
        end
    elseif state == "ACTIVE" or state == "RESYNCING" then
        is_active = true
        -- Sync PalSchema state with AP server's item state
        if db_ready and #all_tech_ids > 0 then
            rebuild_palschema_state()
        end
    elseif state == "ERROR_STATE" or state == "SHUTDOWN" then
        is_active = false
    end
end)

APClient.on_registration_success(function()
    is_registered = true
    APClient.log("info", "Successfully registered with AP Framework\n")
end)

APClient.on_registration_rejected(function(reason)
    APClient.log("error",
        "Registration rejected: " .. (reason or "unknown") .. "\n")
end)

APClient.on_item_received(function(item_id, item_name, sender)
    APClient.log("info", "Item received: " .. item_name ..
        " from " .. sender .. "\n")
    -- Action handlers are invoked automatically by APClientLib's action
    -- executor based on the manifest's action definitions.
end)

APClient.on_state_active(function()
    is_active = true
end)

APClient.on_state_error(function(error_info)
    APClient.log("error",
        "Framework error: " .. (error_info or "unknown") .. "\n")
    is_active = false
end)

APClient.on_error(function(code, message)
    APClient.log("error",
        "Error [" .. (code or "?") .. "]: " .. (message or "unknown") .. "\n")
end)

-- ============================================================================
-- Initialization
-- ============================================================================

palschema_dir = resolve_palschema_dir()
if palschema_dir then
    APClient.log("info", "PalSchema dir: " .. palschema_dir .. "\n")
else
    APClient.log("warn",
        "PalSchema integration disabled - directory not found\n")
end

db_ready = init_database()
if db_ready then
    APClient.log("info",
        "Database ready (" .. #all_tech_ids .. " techs)\n")
else
    APClient.log("warn",
        "Database not available - PalSchema lock/unlock requires db_query\n")
    APClient.log("warn",
        "Action handlers will still work for item tracking\n")
end

-- Connect to framework IPC
if APClient.connect() then
    APClient.log("info", "IPC connection initiated\n")
else
    APClient.log("warn", "IPC connection failed - will retry\n")
end
