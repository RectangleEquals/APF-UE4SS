--[[
    tracker_ui.lua — UI Bridge Module for APTracker (Task 10 redesign)

    Owns sort/filter/search state and all communication with WBP_TrackerUI widget.
    Lua drives sort, filter, and search; BP stores and displays whatever Lua pushes.

    Architecture:
    - push_all_data(td, checked_set): call after snapshot/update; stores refs + calls repush()
    - repush(): applies current sort/filter/search state, pushes to BP widget via structs
    - BP fires custom events when buttons/search change → Lua updates state + repush()
]]

local M = {}

-- ============================================================================
-- Private State
-- ============================================================================

local tracker_widget   = nil  -- WBP_TrackerUI (from actor:GetTrackerUI())
local tracker_data_ref = nil  -- tracker_data table (set via push_all_data)
local checked_set_ref  = nil  -- local offline check set {[id]=true} (set via push_all_data)

-- Sort/filter/search state (owned by Lua)
local sort_mode   = 0   -- 0=Default, 1=Alphabetical, 2=Score descending
local filter_mode = 0   -- 0=All, 1=Unchecked, 2=InLogic (score > 0)
local search_text = ""  -- current case-insensitive filter string

-- ============================================================================
-- Rich Text Formatters (preserved logic from previous tracker_ui.lua)
-- ============================================================================

--- Map a 0.0–1.0 score to a DT_TrackerStyles row name.
local function score_to_style(score)
    if score >= 1.0 then
        return "Green"
    elseif score > 0.0 then
        return "Yellow"
    else
        return "Red"
    end
end

--- Format a scored logic tree as single-line rich text (for LogicRichText field).
--- @param node table|nil  Scored tree node {type, score, display, children}
--- @param depth number    Current recursion depth (start at 0)
--- @return string         Rich text markup
local function format_scored_tree(node, depth)
    depth = depth or 0
    if not node then return "" end
    local children = node.children

    -- Leaf node: color by individual score
    if not children or #children == 0 then
        local style = score_to_style(node.score or 0)
        return "<" .. style .. ">" .. (node.display or "") .. "</>"
    end

    -- Compound node: join children with styled operator
    local op = " <Operator>" .. (node.type == "and" and "AND" or "OR") .. "</> "
    local parts = {}
    for _, child in ipairs(children) do
        local t = format_scored_tree(child, depth + 1)
        if t ~= "" then table.insert(parts, t) end
    end
    if #parts == 0 then return "" end
    if #parts == 1 then return parts[1] end

    local joined = table.concat(parts, op)
    if depth > 0 then
        local s = score_to_style(node.score or 0)
        return "<" .. s .. ">(</>" .. joined .. "<" .. s .. ">)</>"
    end
    return joined
end

--- Format a scored logic tree as plain text (for search matching and debug tooltips).
--- @param node table|nil  Scored tree node
--- @param indent number   Current indentation level (start at 0)
--- @return string         Plain text
local function format_scored_tree_plain(node, indent)
    indent = indent or 0
    if not node then return "" end
    local prefix = string.rep("  ", indent)
    local children = node.children

    if not children or #children == 0 then
        return prefix .. (node.display or "")
    end

    local label = (node.type == "and") and "ALL of:" or "ANY of:"
    local lines = { prefix .. label }
    for _, child in ipairs(children) do
        table.insert(lines, format_scored_tree_plain(child, indent + 1))
    end
    return table.concat(lines, "\n")
end

-- ============================================================================
-- Debug Mode Helper
-- ============================================================================

--- Returns true if the widget's debug checkbox is checked.
--- Protected call — safe if GetDebugMode() hasn't been added to BP yet.
local function debug_mode_enabled()
    if not tracker_widget then return false end
    local ok, val = pcall(function() return tracker_widget:GetDebugMode() end)
    return ok and val
end

-- ============================================================================
-- Filter / Search
-- ============================================================================

local function location_passes_filter(loc_id, ldata)
    local is_checked = (checked_set_ref and checked_set_ref[loc_id]) or ldata.checked or false

    if filter_mode == 1 and is_checked then return false end                       -- Unchecked: skip checked
    if filter_mode == 2 and (ldata.score or 0) <= 0 then return false end          -- InLogic: score > 0

    if search_text ~= "" then
        local name_lower = (ldata.name or ""):lower()
        local colon_idx  = search_text:find(":")
        if colon_idx and debug_mode_enabled() then
            -- "prefix:term" → search logic plain text (debug mode only)
            local term       = search_text:sub(colon_idx + 1)
            local logic_plain = format_scored_tree_plain(ldata.logic_tree or {}):lower()
            if not logic_plain:find(term, 1, true) then return false end
        else
            if not name_lower:find(search_text, 1, true) then return false end
        end
    end

    return true
end

--- Build sorted + filtered list of {id, data} pairs for Repopulate.
local function build_display_list()
    local list = {}
    for loc_id, ldata in pairs((tracker_data_ref and tracker_data_ref.locations) or {}) do
        if location_passes_filter(loc_id, ldata) then
            list[#list + 1] = { id = loc_id, data = ldata }
        end
    end

    if sort_mode == 1 then
        -- Alphabetical by name
        table.sort(list, function(a, b) return (a.data.name or "") < (b.data.name or "") end)
    elseif sort_mode == 2 then
        -- Score descending
        table.sort(list, function(a, b) return (a.data.score or 0) > (b.data.score or 0) end)
    end
    -- sort_mode == 0: Default (iteration order; grouped by region in repush push order)

    return list
end

-- ============================================================================
-- Init — Actor Discovery and Event Wiring
-- ============================================================================

--- Initialize the UI module from the ModActor.
--- Called from main.lua when APTracker_ToLua_InitUI custom event fires.
--- @param actor userdata  ModActor BP reference
function M.init(actor)
    if not actor then return end
    local ok, widget = pcall(function() return actor:GetTrackerUI() end)
    if not ok or not widget then return end
    tracker_widget = widget

    -- Hook: BP sort button clicked → ETrackerSortMode ordinal
    RegisterCustomEvent("APTrackerUI_ToLua_OnSortModeChanged", function(mode)
        sort_mode = tonumber(mode) or 0
        M.repush()
    end)

    -- Hook: BP filter button clicked → ETrackerFilterMode ordinal
    RegisterCustomEvent("APTrackerUI_ToLua_OnFilterModeChanged", function(mode)
        filter_mode = tonumber(mode) or 0
        M.repush()
    end)

    -- Hook: WBP_SearchBoxPanel text committed
    RegisterCustomEvent("APTrackerUI_ToLua_OnTextCommitted", function(text)
        search_text = tostring(text or ""):lower()
        M.repush()
    end)

    -- Flush any tracker data that arrived before the widget was ready
    if tracker_data_ref then M.repush() end
end

-- ============================================================================
-- Visibility
-- ============================================================================

function M.toggle_visible()
    if tracker_widget then tracker_widget:ToggleVisible() end
end

function M.set_visible(visible)
    if tracker_widget then tracker_widget:SetVisible(visible) end
end

-- ============================================================================
-- repush — Clear BP data and repopulate from current state
-- ============================================================================

--- Clear BP widget data and push current tracker state with sort/filter/search applied.
--- Called after every data update or state change (sort/filter/search/F5).
function M.repush()
    if not tracker_widget or not tracker_data_ref then return end

    tracker_widget:ClearData()

    -- Push all regions (Repopulate inserts region headers only for regions with visible locations)
    for region_name, rdata in pairs((tracker_data_ref.regions) or {}) do
        -- Lua strings auto-convert to FString; named table fields auto-convert to BP struct
        tracker_widget:AddRegion({
            RegionName    = region_name,
            Score         = rdata.score    or 0.0,
            bReachable    = rdata.reachable or false,
            LogicRichText = format_scored_tree(rdata.logic_tree or {}, 0),
            TotalCount    = rdata.total    or 0,
            CheckedCount  = rdata.checked  or 0,
        })
    end

    -- Push locations in sorted + filtered order
    local display_list = build_display_list()
    for _, entry in ipairs(display_list) do
        local loc_id = entry.id
        local ldata  = entry.data
        local is_checked = (checked_set_ref and checked_set_ref[loc_id]) or ldata.checked or false
        tracker_widget:AddLocation({
            LocationId     = loc_id,
            RegionName     = ldata.region  or "",
            DisplayName    = ldata.name    or tostring(loc_id),
            Score          = ldata.score   or 0.0,
            bChecked       = is_checked,
            LogicRichText  = format_scored_tree(ldata.logic_tree or {}, 0),
            LogicPlainText = format_scored_tree_plain(ldata.logic_tree or {}),
        })
    end

    tracker_widget:Refresh(true)
end

-- ============================================================================
-- push_all_data — Called by main.lua after snapshot/update merge
-- ============================================================================

--- Store tracker data refs and trigger repush with current sort/filter/search.
--- @param td          table  tracker_data (map-format: locations by id, regions by name)
--- @param checked_set table  local offline checks {[id]=true}
function M.push_all_data(td, checked_set)
    tracker_data_ref = td
    checked_set_ref  = checked_set
    M.repush()
end

return M
