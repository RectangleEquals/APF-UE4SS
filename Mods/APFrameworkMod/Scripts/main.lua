-- 1. Load the C++ Library
-- This call triggers the C++ luaopen function, which:
--   - Starts the background thread
--   - Injects the 'Tick' proxy script into the global environment
local success, AP = pcall(require, "APFrameworkCore")
local RH = require("registry_helper")
local current_time = os.clock()
local last_time = current_time
local is_initialized = false

if not success then
    print("[APFrameworkMod]: CRITICAL ERROR: Could not load APFrameworkCore.dll\n")
    print("[APFrameworkMod]: Error: " .. tostring(AP) .. "\n")
    return
end

is_initialized = true
print("[APFrameworkMod]: Core Library Loaded Successfully.\n")

-- 2. Subscribe to events from the C++ Background Thread
-- This is your "Pub-Sub" style entry point.
function ap_on_event(name, val)
    -- This code runs on the Main Thread whenever the C++ thread 
    -- pushes an event and the Tick hook dispatches it.
    print(string.format("[APFrameworkMod]: Received Event: %s | Value: %d\n", name, val))
    return val + 1
end

-- 3. (Optional) Example of a standard Tick registration
-- This should eventually be replaced with the use of registry_helper
--  (in order to allow for more "game-specific" object hooks), because
--  only one mod is allowed to register this specific hook (which may
--  not even work for every game or for all cases in the first place).
RegisterCustomEvent("Tick", function()
    -- You can still put framework-level Lua logic here if needed

    -- Prevent spamming the log
    current_time = os.clock()
    local delta_time = (current_time - last_time)
    if delta_time >= 1.0 then -- Only triggers once per second
        last_time = current_time
        AP.Update()
    end
end)

print("[APFrameworkMod]: Initialization Complete.\n")
