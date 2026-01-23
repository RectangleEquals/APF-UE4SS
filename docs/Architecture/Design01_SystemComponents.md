# Design01: System Components

> Detailed breakdown of the core system components and their responsibilities.

---

## Component Overview

The Archipelago Framework consists of five main components:

| Component | Type | Role |
|-----------|------|------|
| **APFrameworkCore** | C++ DLL | Core orchestrator, AP server communication, IPC server |
| **APClientLib** | C++ DLL | Lightweight IPC client for mods, action execution |
| **APFrameworkMod** | Lua | UE4SS entry point, loads APFrameworkCore |
| **ExampleClientMod** | Lua | Reference implementation for AP-enabled mods |
| **AP World** | Python | Archipelago world package for generation |

---

## APFrameworkCore (C++)

The heart and orchestrator of the entire system. It's the middleware between AP-enabled client mods (via APClientLib) and the Archipelago server.

### Responsibilities

- **AP Server Communication:** Uses `apclientpp` for WebSocket connection, polling, data packages
- **JSON Handling:** Uses `nlohmann::json` for all data encoding/decoding
- **Lua Bindings:** Uses `sol2` to expose C++ to Lua via `sol::state_view`
- **IPC Server:** Named pipes server for bidirectional communication with client mods
- **Mod Discovery:** Scans filesystem for valid manifests
- **Registration Management:** Tracks discovered vs. registered mods
- **Capability Aggregation:** Validates, merges, and assigns IDs to all capabilities
- **Checksum Generation:** Creates ecosystem checksum for validation
- **State Persistence:** Saves/restores session progress for resync
- **Logging:** Configurable logging to dedicated log file

### Core Classes

#### APManager

Global singleton managing the lifecycle of all other components.

```cpp
class APManager {
public:
    static APManager& get();

    // Lifecycle
    void init();    // Called from luaopen_APFrameworkCore
    void update();  // Called each tick by APFrameworkMod
    void shutdown();

    // State machine
    LifecycleState get_state() const;
    void transition_to(LifecycleState new_state);

    // Registration
    void register_mod(const std::string& mod_id, const std::string& version);
    void register_priority_client(const std::string& mod_id, const std::string& version);

    // Commands (from priority clients)
    void cmd_restart();
    void cmd_resync();
    void cmd_reconnect();

private:
    std::unique_ptr<APClient> ap_client_;
    std::unique_ptr<APIPCServer> ipc_server_;
    std::unique_ptr<APCapabilities> capabilities_;
    std::unique_ptr<APModRegistry> mod_registry_;
    std::unique_ptr<APMessageRouter> message_router_;
    std::unique_ptr<APStateManager> state_manager_;
    std::unique_ptr<APConfig> config_;
    std::unique_ptr<APPollingThread> polling_thread_;

    LifecycleState current_state_;
};
```

#### APClient

Wrapper around `apclientpp` library.

```cpp
class APClient {
public:
    // Connection
    bool connect(const std::string& server, int port,
                 const std::string& slot, const std::string& password);
    void disconnect();
    bool is_connected() const;

    // Polling
    void poll();
    std::vector<APMessage> get_messages();

    // Outgoing
    void send_location_checks(const std::vector<int64_t>& location_ids);
    void send_location_scouts(const std::vector<int64_t>& location_ids);
    void send_status_update(ClientStatus status);

    // Data
    const DataPackage& get_data_package() const;
};
```

#### APIPCServer

Named pipes server for IPC.

```cpp
class APIPCServer {
public:
    bool start(const std::string& game_name);
    void stop();

    // Message handling
    void send_message(const std::string& target, const IPCMessage& message);
    void broadcast(const IPCMessage& message);
    std::vector<IPCMessage> get_pending_messages();

    // Configuration
    void set_retry_policy(int max_retries, int retry_delay_ms);
    void set_timeout(int timeout_ms);
};
```

#### APCapabilities

Manages the capabilities system.

```cpp
class APCapabilities {
public:
    // Registration
    void add_manifest(const Manifest& manifest);

    // Validation
    ValidationResult validate();
    std::vector<Conflict> get_conflicts() const;

    // ID Assignment
    void assign_ids(int64_t base_id);
    int64_t get_location_id(const std::string& mod_id, const std::string& name) const;
    int64_t get_item_id(const std::string& mod_id, const std::string& name) const;

    // Export
    json generate_capabilities_config(const std::string& slot_name) const;
};
```

#### APModRegistry

Tracks mod discovery and registration.

```cpp
class APModRegistry {
public:
    // Discovery
    void discover_manifests(const std::filesystem::path& mods_folder);
    std::vector<Manifest> get_discovered_manifests() const;

    // Registration
    void mark_registered(const std::string& mod_id);
    bool is_registered(const std::string& mod_id) const;
    bool all_registered() const;

    // Queries
    std::vector<std::string> get_pending_registrations() const;
    std::optional<Manifest> get_manifest(const std::string& mod_id) const;
    ModType get_mod_type(const std::string& mod_id) const;  // Priority or Regular
};
```

#### APStateManager

Persists session progress.

```cpp
class APStateManager {
public:
    // Persistence
    void save_state(const std::filesystem::path& path);
    bool load_state(const std::filesystem::path& path);

    // State tracking
    void set_received_item_index(int index);
    int get_received_item_index() const;
    void add_checked_location(int64_t location_id);
    std::set<int64_t> get_checked_locations() const;

    // Checksum
    void set_checksum(const std::string& checksum);
    std::string get_checksum() const;
    bool validate_checksum(const std::string& current_checksum) const;
};
```

---

## APClientLib (C++)

A lightweight library that acts as an IPC Client, allowing client mods to communicate with the framework.

### Responsibilities

- **JSON Handling:** Uses `nlohmann::json` for message encoding/decoding
- **Lua Bindings:** Uses `sol2` to expose API to Lua via `sol::state_view`
- **IPC Client:** Connects to APFrameworkCore via named pipes
- **Registration:** Sends registration requests to framework
- **Action Execution:** Calls Lua functions when instructed by framework
- **Location Reporting:** Sends location check messages to framework
- **Logging:** Writes to same log file as framework (with mod_id prefix)

### Core Classes

#### APIPCClient

Connects to the framework's IPC server.

```cpp
class APIPCClient {
public:
    bool connect(const std::string& game_name);
    void disconnect();
    bool is_connected() const;

    // Messaging
    void send_message(const IPCMessage& message);
    std::vector<IPCMessage> get_pending_messages();

    // Auto-reconnect
    void set_auto_reconnect(bool enabled);
};
```

#### APActionExecutor

Executes Lua functions from manifests.

```cpp
class APActionExecutor {
public:
    APActionExecutor(sol::state_view lua);

    // Execution
    ActionResult execute(const std::string& action,
                        const std::vector<ActionArg>& args);

private:
    // Property resolution
    sol::object resolve_property(const std::string& property_path);

    // Function lookup
    sol::function find_function(const std::string& function_path);

    sol::state_view lua_;
};
```

### Lua API

The APClientLib exposes the following API to Lua:

```lua
local APClientLib = require("APClientLib")

-- Registration
APClientLib.register()

-- Location checks
APClientLib.location_check("Defeat Forest Boss")
APClientLib.location_check("Kill 20 Enemies", 3)  -- 3rd instance

-- Location scouting
APClientLib.location_scout({"Location A", "Location B"})

-- Logging
APClientLib.log("info", "Something happened")
APClientLib.log("error", "Something went wrong")

-- Callbacks
APClientLib.on_lifecycle(function(state, message)
    -- Handle lifecycle changes
end)

APClientLib.on_item(function(item_id, item_name, sender)
    -- Handle item receipt (optional, actions auto-execute)
end)

APClientLib.on_message(function(message)
    -- Handle other framework messages
end)
```

---

## APFrameworkMod (Lua)

The entry point of the entire system. This UE4SS Lua mod should load before any other AP-enabled mods.

### Responsibilities

- Load APFrameworkCore via `pcall(require, "APFrameworkCore")` with error handling
- Subscribe to events from C++ background thread via global callback functions
- Register game-specific tick callbacks to call `AP.update()`
- Bridge UE4SS's Lua environment and the C++ framework

### Load Order

Configure in `<game_root>/<game_name>/Binaries/Win64/ue4ss/Mods/mods.txt` (mods load in listed order, top-to-bottom):

```
; AP Framework must load first
APFrameworkMod : 1

; Other AP-enabled mods load after
MyAPClientMod : 1
AnotherAPMod : 1

; Built-in keybinds, do not move up!
Keybinds : 1
```

Or in `mods.json` (array order determines load order):

```json
[
    {
        "mod_name": "APFrameworkMod",
        "mod_enabled": true
    },
    {
        "mod_name": "MyAPClientMod",
        "mod_enabled": true
    },
    {
        "mod_name": "AnotherAPMod",
        "mod_enabled": true
    }
]
```

**Important:** APFrameworkMod must appear before any AP-enabled client mods in the load order. UE4SS loads mods sequentially in the order they appear.

### main.lua Structure

```lua
-- APFrameworkMod/Scripts/main.lua
print("[APFramework] Loading...\n")

-- 1. Safe load with error handling
local success, AP = pcall(require, "APFrameworkCore")
local RegistryHelper = require("registry_helper")

if not success then
    print("[APFramework] CRITICAL ERROR: Could not load APFrameworkCore.dll\n")
    print("[APFramework] Error: " .. tostring(AP) .. "\n")
    return
end

-- NOTE: init() is called automatically from luaopen_APFrameworkCore
-- The DLL load triggers background thread startup and Lua environment setup

-- 2. Subscribe to events from the C++ Background Thread (pub-sub style)
function ap_on_event(name, val)
    -- Runs on Main Thread when C++ thread pushes events and Tick hook dispatches
    print(string.format("[APFramework] Event: %s | Value: %d\n", name, val))
    return val + 1
end

-- 3. Register game-specific tick callback via registry_helper
-- This approach allows game-specific object hooks for compatibility across UE4/5 games
RegistryHelper.add_object("Engine.PlayerController")
RegistryHelper.add_function("Engine.PlayerController",
    "/Script/Engine.PlayerController:ClientRestart",
    function(className, obj)
        AP.update()
    end
)

print("[APFramework] Initialized\n")
```

> **Note:** The exact hook path (`/Script/Engine.PlayerController:ClientRestart`) is game-specific and may need adjustment. The registry_helper approach enables per-game customization of the tick callback, which is required because different games expose different hookable functions.

---

## ExampleClientMod (Lua)

A reference implementation demonstrating proper integration.

### Folder Structure

```
ExampleClientMod/
├── Scripts/
│   ├── main.lua
│   ├── APClient.lua (Lua wrapper)
│   ├── APClientLib.dll
│   ├── lunajson.lua
│   └── lunajson/
└── manifest.json
```

### manifest.json

```json
{
  "mod_id": "example.game.testmod",
  "name": "Example Test Mod",
  "version": "1.0.0",
  "capabilities": {
    "locations": [
      { "name": "Test Location", "amount": 1, "unique": true }
    ],
    "items": [
      {
        "name": "Test Item",
        "type": "filler",
        "amount": -1,
        "action": "TestMod.GiveItem",
        "args": [
          { "name": "name", "type": "string", "value": "<GET_ITEM_NAME>" }
        ]
      }
    ]
  }
}
```

### main.lua

```lua
-- ExampleClientMod/Scripts/main.lua
print("[ExampleMod] Loading...\n")

local APClientLib = require("APClientLib")

-- Global object referenced in manifest actions
TestMod = {
    GiveItem = function(name)
        print("[ExampleMod] Received item: " .. name .. "\n")
        -- Actual game logic here
    end
}

-- Wait for registration phase
APClientLib.on_lifecycle(function(state, message)
    if state == "REGISTRATION" then
        print("[ExampleMod] Registering...\n")
        APClientLib.register()
    end
end)

-- Example: Detect location when something happens
function OnBossDefeated()
    APClientLib.location_check("Test Location")
end

print("[ExampleMod] Initialized\n")
```

---

## AP World (Python)

The Archipelago `.apworld` package handles generation/randomization.

### Responsibilities

- Read capability configs from `Archipelago/Players/`
- Dynamically create items and locations from capabilities
- Generate randomized placements respecting logic rules
- Produce multiworld `.zip` for hosting

### Integration Point

```python
# In the AP World's __init__.py
from BaseClasses import Item, Location, Region, MultiWorld
import json
import os

class MyGameWorld(World):
    game = "MyGame"

    def generate_early(self):
        # Read capabilities file
        cap_file = self.multiworld.capabilities_file[self.player].value
        cap_path = os.path.join(os.path.dirname(__file__), "..", "..", "Players", cap_file)

        with open(cap_path) as f:
            capabilities = json.load(f)

        # Create items from capabilities
        for item in capabilities["items"]:
            for i in range(item["amount"] if item["amount"] > 0 else 1):
                self.create_item(item["name"], item["type"])

        # Create locations from capabilities
        for location in capabilities["locations"]:
            for i in range(location["amount"]):
                name = f"{location['name']} #{i+1}" if location["amount"] > 1 else location["name"]
                self.create_location(name, location["id_base"] + i)
```

---

## Component Interaction Summary

```
┌─────────────┐
│   UE4SS     │
│   Game      │
└──────┬──────┘
       │ loads
       ▼
┌──────────────────┐
│ APFrameworkMod   │ ─────────────────────────────────────────┐
│     (Lua)        │                                          │
└────────┬─────────┘                                          │
         │ require()                                          │
         ▼                                                    │
┌──────────────────┐    IPC     ┌──────────────────┐         │
│ APFrameworkCore  │◄──────────►│   APClientLib    │◄────────┤
│   (C++ DLL)      │            │   (C++ DLL)      │         │
│                  │            └────────┬─────────┘         │
│  ┌────────────┐  │                     │                   │ loads
│  │ APManager  │  │                     │ used by           │
│  │ APClient   │──┼── WebSocket ──►  AP Server             │
│  │ APIPCServer│  │                     │                   │
│  └────────────┘  │                     ▼                   │
└──────────────────┘            ┌──────────────────┐         │
                                │  Client Mod A    │◄────────┤
                                │     (Lua)        │         │
                                └──────────────────┘         │
                                                             │
                                ┌──────────────────┐         │
                                │  Client Mod B    │◄────────┘
                                │     (Lua)        │
                                └──────────────────┘
```