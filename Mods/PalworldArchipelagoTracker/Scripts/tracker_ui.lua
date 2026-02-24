--[[
    tracker_ui.lua — UI Bridge Module for APTracker

    Handles all communication between Lua and the Blueprint ModActor:
    - ModActor discovery with race condition handling
    - Rich text formatting for scored logic trees
    - Snapshot/delta push to Blueprint widgets
    - Configurable keybind registration

    Separated from main.lua to keep IPC/callback logic clean.
]]

local TrackerUI = {}

-- ============================================================================
-- Private State
-- ============================================================================

local APClient = nil
local tracker_actor = nil
local actor_ready = false
local pending_snapshot = nil -- Buffered snapshot if data arrives before ModActor
local tracker_data_ref = nil -- Reference to main.lua's tracker_data (set via set_data_ref)

-- ============================================================================
-- Rich Text Formatting
-- ============================================================================

--- Map a score (0.0-1.0) to a DT_TrackerStyles row name.
local function score_to_style(score)
    if score >= 1.0 then
        return "Green"
    elseif score > 0.0 then
        return "Yellow"
    else
        return "Red"
    end
end

--- Format a scored logic tree as single-line rich text.
--- Used for compact status/summary display.
--- @param node table|nil  Scored tree node {type, score, display, children}
--- @param depth number    Current recursion depth (default 0)
--- @return string         Rich text markup
function TrackerUI.format_scored_tree(node, depth)
    depth = depth or 0
    if not node then return "" end
    local children = node.children

    -- Leaf node: colored by its individual score
    if not children or #children == 0 then
        local style = score_to_style(node.score or 0)
        return "<" .. style .. ">" .. (node.display or "") .. "</>"
    end

    -- Compound node: join children with styled operator
    local op = " <Operator>" .. (node.type == "and" and "AND" or "OR") .. "</> "
    local parts = {}
    for _, child in ipairs(children) do
        local t = TrackerUI.format_scored_tree(child, depth + 1)
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

--- Format a scored logic tree as multiline indented rich text.
--- Used for expandable logic detail panels.
--- @param node table|nil  Scored tree node
--- @param indent number   Current indentation level (default 0)
--- @return string         Rich text markup with newlines
function TrackerUI.format_scored_tree_multiline(node, indent)
    indent = indent or 0
    if not node then return "" end
    local prefix = string.rep("  ", indent)
    local children = node.children

    -- Leaf node
    if not children or #children == 0 then
        local style = score_to_style(node.score or 0)
        return prefix .. "<" .. style .. ">" .. (node.display or "") .. "</>"
    end

    -- Compound node: header line + indented children
    local label = (node.type == "and") and "ALL of:" or "ANY of:"
    local style = score_to_style(node.score or 0)
    local lines = { prefix .. "<" .. style .. ">" .. label .. "</>" }
    for _, child in ipairs(children) do
        table.insert(lines, TrackerUI.format_scored_tree_multiline(child, indent + 1))
    end
    return table.concat(lines, "\n")
end

--- Format a scored logic tree as plain text (no rich text tags).
--- Used for search matching against logic content.
--- @param node table|nil  Scored tree node
--- @param indent number   Current indentation level (default 0)
--- @return string         Plain text
function TrackerUI.format_scored_tree_plain(node, indent)
    indent = indent or 0
    if not node then return "" end
    local prefix = string.rep("  ", indent)
    local children = node.children

    -- Leaf node
    if not children or #children == 0 then
        return prefix .. (node.display or "")
    end

    -- Compound node
    local label = (node.type == "and") and "ALL of:" or "ANY of:"
    local lines = { prefix .. label }
    for _, child in ipairs(children) do
        table.insert(lines, TrackerUI.format_scored_tree_plain(child, indent + 1))
    end
    return table.concat(lines, "\n")
end

-- ============================================================================
-- Score Counting Helper
-- ============================================================================

--- Count locations by accessibility score (excludes checked).
--- @param locations table  Array of location data
--- @return number, number, number  green, yellow, red counts
local function count_by_score(locations)
    if not locations then return 0, 0, 0 end
    local green, yellow, red = 0, 0, 0
    for _, loc in ipairs(locations) do
        if loc.checked then
            -- Skip checked locations
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

-- ============================================================================
-- ModActor Discovery + Race Condition Handling
-- ============================================================================

--- Initialize the UI module.
--- Sets up ModActor discovery via NotifyOnNewObject and FindFirstOf fallback.
--- @param client table  APClient reference (from APClientLib)
function TrackerUI.init(client)
    APClient = client
    
    RegisterHook("/Script/Engine.PlayerController:ClientRestart", function (Context)
        if player_controller == nil or not player_controller:IsValid() then
            player_controller = Context:get()

            RegisterHook("/Game/Mods/APTracker/ModActor.ModActor_C:InitLuaInterop", function (Context)
                tracker_actor = Context:get()
                actor_ready = tracker_actor:IsValid()
                if actor_ready then
                    APClient.log("info", "Found existing Tracker ModActor\n")
                    
                    -- If we already have tracker data buffered, push it now
                    if pending_snapshot then
                        TrackerUI.push_full_snapshot(pending_snapshot)
                        pending_snapshot = nil
                    end
                end
            end)
        end
    end)

    -- Register for sort mode changes from Blueprint
    RegisterCustomEvent("APTracker_ToLua_OnSortModeChanged", function(_widget, mode)
        TrackerUI.apply_sort(mode:get())
    end)
end

--- Set the tracker data reference (called from main.lua after snapshot).
--- @param data table  Reference to the main tracker_data table
function TrackerUI.set_data_ref(data)
    tracker_data_ref = data
end

-- ============================================================================
-- Blueprint Push Functions
-- ============================================================================

--- Push a full tracker snapshot to the Blueprint ModActor.
--- Groups locations by region and creates all entries via ModActor functions.
--- If ModActor isn't ready yet, buffers the data for later.
--- @param data table  Full tracker snapshot {locations, regions, ...}
function TrackerUI.push_full_snapshot(data)
    if not actor_ready or not tracker_actor or not tracker_actor:IsValid() then
        pending_snapshot = data
        return
    end
    if not data or not data.locations then return end

    tracker_actor["Batch Begin"](tracker_actor)
    tracker_actor["Clear All"](tracker_actor)

    -- Group locations by region, preserving order
    local regions_locs = {}
    local region_order = {}
    for _, loc in ipairs(data.locations) do
        local r = loc.region or "Unknown"
        if not regions_locs[r] then
            regions_locs[r] = {}
            table.insert(region_order, r)
        end
        table.insert(regions_locs[r], loc)
    end

    -- Build region metadata lookup
    local region_data = {}
    if data.regions then
        for _, reg in ipairs(data.regions) do
            region_data[reg.name] = reg
        end
    end

    -- Add regions and their locations
    for _, rname in ipairs(region_order) do
        local reg = region_data[rname]
        local locs = regions_locs[rname]

        -- Count checked locations in this region
        local checked = 0
        for _, l in ipairs(locs) do
            if l.checked then checked = checked + 1 end
        end

        -- Format region logic tree
        local reg_rt = ""
        if reg and reg.scored_tree then
            reg_rt = TrackerUI.format_scored_tree_multiline(reg.scored_tree)
        end

        tracker_actor["Add Region"](tracker_actor,
            FText(rname),
            reg and reg.score or 0,
            reg and reg.reachable or false,
            FText(reg_rt),
            #locs,
            checked)

        -- Add each location under this region
        for _, loc in ipairs(locs) do
            local loc_rt = ""
            local loc_plain = ""
            if loc.scored_tree then
                loc_rt = TrackerUI.format_scored_tree_multiline(loc.scored_tree)
                loc_plain = TrackerUI.format_scored_tree_plain(loc.scored_tree)
            end

            tracker_actor["Add Location"](tracker_actor,
                FText(rname),
                loc.id,
                FText(loc.name),
                loc.score,
                loc.checked or false,
                FText(loc_rt),
                FText(loc_plain))
        end
    end

    tracker_actor["Batch End"](tracker_actor)
    TrackerUI.update_status_text(data)
end

--- Push a delta update to the Blueprint ModActor.
--- Updates existing regions and locations in-place (no widget recreation).
--- @param data table   Full merged tracker data (for region checked counts)
--- @param delta table  Delta update {regions, locations, ...}
function TrackerUI.push_delta_update(data, delta)
    if not actor_ready or not tracker_actor or not tracker_actor:IsValid() then
        return
    end

    -- Update changed regions
    if delta.regions then
        for _, reg in ipairs(delta.regions) do
            -- Recount checked/total from merged data
            local checked, total = 0, 0
            if data and data.locations then
                for _, l in ipairs(data.locations) do
                    if l.region == reg.name then
                        total = total + 1
                        if l.checked then checked = checked + 1 end
                    end
                end
            end

            local rt = ""
            if reg.scored_tree then
                rt = TrackerUI.format_scored_tree_multiline(reg.scored_tree)
            end

            tracker_actor["Update Region"](tracker_actor,
                FText(reg.name),
                reg.score,
                reg.reachable,
                FText(rt),
                total,
                checked)
        end
    end

    -- Update changed locations
    if delta.locations then
        for _, loc in ipairs(delta.locations) do
            local rt = ""
            local plain = ""
            if loc.scored_tree then
                rt = TrackerUI.format_scored_tree_multiline(loc.scored_tree)
                plain = TrackerUI.format_scored_tree_plain(loc.scored_tree)
            end

            tracker_actor["Update Location"](tracker_actor,
                loc.id,
                loc.score,
                loc.checked or false,
                FText(rt),
                FText(plain))
        end
    end

    TrackerUI.update_status_text(data)
end

--- Update the status text summary line with color-coded accessibility counts.
--- @param data table  Full tracker data with locations
function TrackerUI.update_status_text(data)
    if not actor_ready or not tracker_actor or not tracker_actor:IsValid() then
        return
    end
    if not data or not data.locations then return end

    local green, yellow, red = count_by_score(data.locations)
    local total_checked = 0
    for _, loc in ipairs(data.locations) do
        if loc.checked then total_checked = total_checked + 1 end
    end

    local status = string.format(
        "<Green>%d accessible</> | <Yellow>%d partial</> | <Red>%d blocked</> | <Checked>%d checked</>",
        green, yellow, red, total_checked)
    tracker_actor["Set Status Text"](tracker_actor, FText(status))
end

-- ============================================================================
-- Keybind Registration
-- ============================================================================

local DEFAULT_KEYBINDS = {
    toggle_panel = "F1",
    cycle_filter = "F2"
}

--- Register keyboard shortcuts for tracker UI control.
--- Reads keybind config, falls back to defaults.
--- @param config table|nil  Parsed config.json content
function TrackerUI.register_keybinds(config)
    local kb = config and config.keybinds or DEFAULT_KEYBINDS

    -- Toggle tracker panel visibility
    local toggle_key = Key[kb.toggle_panel] or Key.F1
    RegisterKeyBind(toggle_key, function()
        if tracker_actor and tracker_actor:IsValid() then
            tracker_actor["Toggle Panel"](tracker_actor)
        end
    end)

    -- Cycle filter mode: All → Unchecked → In Logic → All ...
    local filter_key = Key[kb.cycle_filter] or Key.F2
    local current_filter = 0
    RegisterKeyBind(filter_key, function()
        if tracker_actor and tracker_actor:IsValid() then
            current_filter = (current_filter + 1) % 3
            tracker_actor["Set Filter Mode"](tracker_actor, current_filter)
        end
    end)
end

-- ============================================================================
-- Sort Implementation
-- ============================================================================

--- Re-sort tracker data and push a full snapshot.
--- Called via RegisterCustomEvent when BP sort button is pressed.
--- @param mode number  Sort mode: 0=Default, 1=Alphabetical, 2=ByScore
function TrackerUI.apply_sort(mode)
    if not tracker_data_ref or not tracker_data_ref.locations then return end

    if mode == 0 then
        -- Default: restore original order (by region order, then original index)
        table.sort(tracker_data_ref.locations, function(a, b)
            if a.region ~= b.region then return a.region < b.region end
            return (a._sort_index or 0) < (b._sort_index or 0)
        end)
    elseif mode == 1 then
        -- Alphabetical within each region
        table.sort(tracker_data_ref.locations, function(a, b)
            if a.region ~= b.region then return a.region < b.region end
            return a.name < b.name
        end)
    elseif mode == 2 then
        -- By score descending within each region
        table.sort(tracker_data_ref.locations, function(a, b)
            if a.region ~= b.region then return a.region < b.region end
            return (a.score or 0) > (b.score or 0)
        end)
    end

    TrackerUI.push_full_snapshot(tracker_data_ref)
end

-- ============================================================================
-- Utility: Check if ModActor is available
-- ============================================================================

--- Returns true if the Blueprint ModActor is discovered and valid.
function TrackerUI.is_ready()
    return actor_ready and tracker_actor ~= nil and tracker_actor:IsValid()
end

--- Returns the raw ModActor reference (for direct calls if needed).
function TrackerUI.get_actor()
    return tracker_actor
end

return TrackerUI