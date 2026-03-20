#include "ap_manager.h"
#include "ap_capabilities.h"
#include "ap_client.h"
#include "ap_config.h"
#include "ap_generated_config.h"
#include "ap_ipc_server.h"
#include "ap_logger.h"
#include "ap_message_router.h"
#include "ap_mod_registry.h"
#include "ap_path_util.h"
#include "ap_polling_thread.h"
#include "ap_state_manager.h"
#include "ap_tracker_engine.h"

#include <chrono>
#include <sstream>
#include <thread>
#include <unordered_map>

namespace ap
{

APManager *APManager::get()
{
    static std::unique_ptr<APManager> instance = std::make_unique<APManager>(ConstructorKey{});
    return instance.get();
}

APManager::APManager(ConstructorKey)
{
    std::cout << "[APFrameworkCore]: AP Manager Initialized.\n";
}

APManager::~APManager()
{
    shutdown();
}

int APManager::init(lua_State *L)
{
    update_cached_lua(L);

    // Register this manager for shared code access (APPathUtil, APLogger, etc.)
    APManagerAccessor::set(this);

    // Initialize logging
    APLogger::get()->set_prefix_tag("APFrameworkCore");
    APLogger::set_thread_name("Main");

    // Transition to INITIALIZATION
    transition_to_unlocked(LifecycleState::INITIALIZATION, "Starting framework");

    // Load configuration (shared singleton)
    if (!APConfig::get()->load_default())
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "Using default configuration");
    }

    // Initialize logger (reads settings from APConfig)
    APLogger::get()->init();

    std::ostringstream oss;
    oss << "init() running on thread: " << std::this_thread::get_id() << " (name: " << APLogger::get_thread_name()
        << ")";
    APLogger::get()->log(LogLevel::Trace, "APManager", oss.str());

    APLogger::get()->log(LogLevel::Info, "APManager", "AP Framework initializing...");

    // Create owned components (all other components are singletons)
    polling_thread_ = std::make_unique<APPollingThread>();

    // Start IPC server
    std::string game_name = APConfig::get()->get_game_name();
    if (game_name.empty())
    {
        game_name = "APFramework";
    }
    APIPCServer::get()->start(game_name);

    // Set up IPC message handler
    APIPCServer::get()->set_message_handler(
        [this](const std::string &client_id, const IPCMessage &msg) { handle_ipc_message(client_id, msg); });

    // Set up connect handler to send current lifecycle state to new clients
    APIPCServer::get()->set_connect_handler([this](const std::string &client_id) {
        APLogger::get()->log(LogLevel::Trace, "APManager", "IPC client connected: " + client_id);

        // Send current lifecycle state to newly connected client
        IPCMessage state_msg;
        state_msg.type = IPCMessageType::LIFECYCLE;
        state_msg.source = IPCTarget::FRAMEWORK;
        state_msg.target = client_id;
        state_msg.payload = {{"state", lifecycle_state_to_string(current_state_.get())},
                             {"message", "Current state on connect"}};
        APIPCServer::get()->send_message(client_id, state_msg);
    });

    // Transition to DISCOVERY
    transition_to_unlocked(LifecycleState::DISCOVERY, "Scanning for mods");

    // Discover manifests
    APModRegistry::get()->discover_manifests();

    // Add manifests to capabilities
    for (const auto &manifest : APModRegistry::get()->get_enabled_manifests())
    {
        APCapabilities::get()->add_manifest(manifest);
    }

    // Apply location overrides (OR-merge cross-mod location logic) — must run after all add_manifest calls
    APCapabilities::get()->apply_location_overrides();

    // Transition to VALIDATION
    transition_to_unlocked(LifecycleState::VALIDATION, "Validating capabilities");

    // Validate for conflicts
    auto validation = APCapabilities::get()->validate();
    if (!validation.valid)
    {
        for (const auto &conflict : validation.conflicts)
        {
            APLogger::get()->log(LogLevel::Error, "APManager", "Conflict: " + conflict.description);
        }
        transition_to_unlocked(LifecycleState::ERROR_STATE, "Capability conflicts detected");

        // Still return module to Lua
        return create_lua_module(L);
    }

    // Transition to GENERATION
    transition_to_unlocked(LifecycleState::GENERATION, "Generating capabilities");

    // Assign IDs (uses APF_GLOBAL_ID_BASE internally)
    APCapabilities::get()->assign_ids();

    // Compute and store checksum (uses APConfig for game_name and slot_name)
    std::string slot_name = APConfig::get()->get_ap_server().slot_name;
    std::string checksum = APCapabilities::get()->compute_checksum();
    APStateManager::get()->set_checksum(checksum);
    APStateManager::get()->set_game_name(game_name);
    APStateManager::get()->set_slot_name(slot_name);

    // Write capabilities config (uses APConfig for slot_name)
    if (!slot_name.empty())
    {
        APCapabilities::get()->write_capabilities_config_default();
    }

    // Transition to PRIORITY_REGISTRATION
    transition_to_unlocked(LifecycleState::PRIORITY_REGISTRATION, "Waiting for priority clients");
    state_entered_at_ = std::chrono::steady_clock::now();

    // Check if any priority clients exist
    if (APModRegistry::get()->get_priority_clients().empty())
    {
        // No priority clients, skip to REGISTRATION
        transition_to_unlocked(LifecycleState::REGISTRATION, "No priority clients");
        state_entered_at_ = std::chrono::steady_clock::now();
    }

    APLogger::get()->log(LogLevel::Info, "APManager", "AP Framework initialized successfully");

    return create_lua_module(L);
}

int APManager::update(lua_State *L)
{
    // Update cached Lua state for APPathUtil and other components
    update_cached_lua(L);

    // Name the update thread (differs from init thread — runs from RegisterHook callback)
    static bool thread_logged = false;
    if (!thread_logged)
    {
        APLogger::set_thread_name("Game");

        std::ostringstream oss;
        oss << "update() running on thread: " << std::this_thread::get_id()
            << " (name: " << APLogger::get_thread_name() << ")";
        APLogger::get()->log(LogLevel::Trace, "APManager", oss.str());
        thread_logged = true;
    }

    // On first update, reinitialize APPathUtil to use debug.getinfo
    if (!first_update_done_)
    {
        APPathUtil::get()->reinitialize_cache();
        first_update_done_ = true;
    }

    // Process IPC messages
    APIPCServer::get()->poll();

    // Process AP client events
    if (polling_thread_->is_running())
    {
        polling_thread_->process_events([this](const FrameworkEvent &event) { handle_framework_event(event); });
    }

    // Handle state-specific logic
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - state_entered_at_).count();

    switch (current_state_.get())
    {
    case LifecycleState::PRIORITY_REGISTRATION:
        handle_priority_registration(elapsed_ms);
        break;

    case LifecycleState::REGISTRATION:
        handle_registration(elapsed_ms);
        break;

    case LifecycleState::CONNECTING:
        handle_connecting(elapsed_ms);
        break;

    case LifecycleState::SYNCING:
        handle_syncing(elapsed_ms);
        break;

    case LifecycleState::ACTIVE:
        handle_active();
        break;

    case LifecycleState::RESYNCING:
        handle_resyncing(elapsed_ms);
        break;

    case LifecycleState::ERROR_STATE:
        // Stay in error state until recovery command
        break;

    default:
        break;
    }

    return 0;
}

void APManager::shutdown()
{
    APLogger::get()->log(LogLevel::Info, "APManager", "AP Framework shutting down...");

    // No save_state() — state is saved eagerly on every meaningful change.
    // Saving during shutdown risks static destruction order issues with APPathUtil.

    // Stop polling thread
    if (polling_thread_)
    {
        polling_thread_->stop(APConfig::get()->get_threading().shutdown_timeout_ms);
    }

    // Disconnect from AP server
    APArchipelagoClient::get()->disconnect();

    // Stop IPC server
    APIPCServer::get()->stop();

    APLogger::get()->log(LogLevel::Info, "APManager", "AP Framework shutdown complete");
}

LifecycleState APManager::get_state() const
{
    return current_state_.get();
}

bool APManager::transition_to(LifecycleState new_state, const std::string &message)
{
    return transition_to_unlocked(new_state, message);
}

bool APManager::is_active() const
{
    auto state = current_state_.get();
    return state == LifecycleState::ACTIVE || state == LifecycleState::RESYNCING;
}

bool APManager::is_error() const
{
    return current_state_.get() == LifecycleState::ERROR_STATE;
}

bool APManager::register_mod(const std::string &mod_id, const std::string &version)
{
    auto state = current_state_.get();
    if (state != LifecycleState::PRIORITY_REGISTRATION && state != LifecycleState::REGISTRATION)
    {
        APLogger::get()->log(LogLevel::Warn, "APManager",
                             "Registration rejected - not in registration phase: " + mod_id);
        return false;
    }

    if (!APModRegistry::get()->mark_registered(mod_id))
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "Unknown mod registration attempt: " + mod_id);
        return false;
    }

    APLogger::get()->log(LogLevel::Info, "APManager", "Mod registered: " + mod_id + " v" + version);

    // Build enriched registration response: include all locations + items for this mod so the
    // client can populate bidirectional lookup maps (get_location / get_item / check_location by ID).
    auto all_locs  = APCapabilities::get()->get_locations_for_mod(mod_id);
    auto all_items = APCapabilities::get()->get_items_for_mod(mod_id);

    // Compute instance count per location name
    std::unordered_map<std::string, int> instance_counts;
    for (const auto &loc : all_locs)
        instance_counts[loc.location_name]++;

    nlohmann::json locations_json = nlohmann::json::array();
    for (const auto &loc : all_locs)
    {
        locations_json.push_back({{"id",             loc.location_id},
                                  {"name",           loc.location_name},
                                  {"instance",       loc.instance},
                                  {"instance_count", instance_counts[loc.location_name]}});
    }

    nlohmann::json items_json = nlohmann::json::array();
    for (const auto &item : all_items)
    {
        items_json.push_back({{"id",   item.item_id},
                              {"name", item.item_name},
                              {"type", item_type_to_string(item.type)}});
    }

    APLogger::get()->log(LogLevel::Debug, "APManager",
                         "Registration response: " + std::to_string(all_locs.size()) +
                         " locations, " + std::to_string(all_items.size()) + " items for " + mod_id);

    // Send registration response
    IPCMessage response;
    response.type = IPCMessageType::REGISTRATION_RESPONSE;
    response.source = IPCTarget::FRAMEWORK;
    response.target = mod_id;
    response.payload = {{"success",   true},
                        {"mod_id",    mod_id},
                        {"locations", std::move(locations_json)},
                        {"items",     std::move(items_json)}};
    APIPCServer::get()->send_message(mod_id, response);

    return true;
}

bool APManager::register_priority_client(const std::string &mod_id, const std::string &version)
{
    if (!APModRegistry::get()->is_priority_client(mod_id))
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "Non-priority mod tried to register as priority: " + mod_id);
        return false;
    }

    return register_mod(mod_id, version);
}

void APManager::cmd_restart()
{
    APLogger::get()->log(LogLevel::Info, "APManager", "Restart command received");

    APMessageRouter::get()->reset_goal_sent();

    // Reset state and restart
    APModRegistry::get()->reset_registrations();
    transition_to_unlocked(LifecycleState::DISCOVERY, "Restarting");
}

void APManager::cmd_resync()
{
    APLogger::get()->log(LogLevel::Info, "APManager", "Resync command received");

    transition_to_unlocked(LifecycleState::RESYNCING, "Manual resync requested");
}

void APManager::cmd_reconnect()
{
    APLogger::get()->log(LogLevel::Info, "APManager", "Reconnect command received");

    APMessageRouter::get()->reset_goal_sent();

    APArchipelagoClient::get()->disconnect();
    transition_to_unlocked(LifecycleState::CONNECTING, "Reconnecting to AP server");
    state_entered_at_ = std::chrono::steady_clock::now();
}

sol::state_view *APManager::get_cached_lua()
{
    return cached_lua_.get();
}

bool APManager::transition_to_unlocked(LifecycleState new_state, const std::string &message)
{
    LifecycleState old_state = current_state_.get();
    current_state_.set(new_state);
    state_entered_at_ = std::chrono::steady_clock::now();

    APLogger::get()->log(LogLevel::Info, "APManager",
                         "State: " + lifecycle_state_to_string(old_state) + " -> " +
                             lifecycle_state_to_string(new_state) + (message.empty() ? "" : " (" + message + ")"));

    // Clean up on ERROR_STATE: stop polling and disconnect AP server
    if (new_state == LifecycleState::ERROR_STATE)
    {
        if (polling_thread_ && polling_thread_->is_running())
        {
            polling_thread_->stop(APConfig::get()->get_threading().shutdown_timeout_ms);
        }
        APArchipelagoClient::get()->disconnect();
    }

    // Broadcast lifecycle change
    APMessageRouter::get()->broadcast_lifecycle(new_state, message);

    return true;
}

int APManager::create_lua_module(lua_State *L)
{
    sol::state_view lua(L);
    sol::table module = lua.create_table();

    // Register update function
    module["update"] = [](lua_State *L) { return APManager::get()->update(L); };

    // Register shutdown
    module["shutdown"] = []() { APManager::get()->shutdown(); };

    auto return_value = sol::stack::push(L, module);
    update_cached_lua(L);

    return return_value;
}

int APManager::update_cached_lua(lua_State *L)
{
    if (!cached_lua_ || cached_lua_->lua_state() != L)
    {
        if (cached_lua_)
        {
            cached_lua_.reset();
        }
        cached_lua_ = std::make_unique<sol::state_view>(L);
    }

    return 0;
}

void APManager::handle_ipc_message(const std::string &client_id, const IPCMessage &msg)
{
    APLogger::get()->log(LogLevel::Debug, "APManager", "IPC message from " + client_id + ": " + msg.type);

    if (msg.type == IPCMessageType::REGISTER)
    {
        std::string mod_id = msg.payload.value("mod_id", "");
        std::string version = msg.payload.value("version", "1.0.0");
        register_mod(mod_id, version);
    }
    else if (msg.type == IPCMessageType::LOCATION_CHECK)
    {
        if (msg.payload.contains("location_id"))
        {
            // Integer ID path — from polymorphic check_location(integer)
            int64_t loc_id = msg.payload.value("location_id", int64_t(0));
            APLogger::get()->log(LogLevel::Debug, "APManager",
                                 "check_location_by_id: " + std::to_string(loc_id) +
                                 " from " + client_id);
            APMessageRouter::get()->route_location_check_by_id(client_id, loc_id);
        }
        else
        {
            // Name string path — from check_location(name, instance?)
            std::string location_name = msg.payload.value("location", "");
            int instance = msg.payload.value("instance", 1);
            APLogger::get()->log(LogLevel::Debug, "APManager",
                                 "check_location: '" + location_name + "' #" +
                                 std::to_string(instance) + " from " + client_id);
            APMessageRouter::get()->route_location_check(client_id, location_name, instance);
        }
    }
    else if (msg.type == IPCMessageType::LOCATION_SCOUT)
    {
        std::vector<std::string> locations;
        if (msg.payload.contains("locations") && msg.payload["locations"].is_array())
        {
            for (const auto &loc : msg.payload["locations"])
            {
                locations.push_back(loc.get<std::string>());
            }
        }
        APMessageRouter::get()->route_location_scouts(client_id, locations, false);
    }
    else if (msg.type == IPCMessageType::ACTION_RESULT)
    {
        ActionResult result;
        result.mod_id = client_id;
        result.item_id = msg.payload.value("item_id", 0LL);
        result.item_name = msg.payload.value("item_name", "");
        result.success = msg.payload.value("success", false);
        result.error = msg.payload.value("error", "");
        APMessageRouter::get()->handle_action_result(client_id, result);
    }
    else if (msg.type == IPCMessageType::LOG)
    {
        std::string level_str = msg.payload.value("level", "info");
        std::string message = msg.payload.value("message", "");
        LogLevel level = LogLevel::Info;
        if (level_str == "debug")
            level = LogLevel::Debug;
        else if (level_str == "warn")
            level = LogLevel::Warn;
        else if (level_str == "error")
            level = LogLevel::Error;
        APLogger::get()->log(level, "APManager", "[" + client_id + "] " + message);
    }
    // Priority client commands
    else if (msg.type == IPCMessageType::CMD_RESTART)
    {
        if (APModRegistry::get()->is_priority_client(client_id))
        {
            cmd_restart();
        }
    }
    else if (msg.type == IPCMessageType::CMD_RESYNC)
    {
        if (APModRegistry::get()->is_priority_client(client_id))
        {
            cmd_resync();
        }
    }
    else if (msg.type == IPCMessageType::CMD_RECONNECT)
    {
        if (APModRegistry::get()->is_priority_client(client_id))
        {
            cmd_reconnect();
        }
    }
    // Tracker subscription
    else if (msg.type == IPCMessageType::SUBSCRIBE_TRACKER)
    {
        auto *tracker = APTrackerEngine::get();
        tracker->add_subscriber(client_id);
        APLogger::get()->log(LogLevel::Info, "APManager", "Tracker subscriber added: " + client_id);

        // Send full snapshot if tracker is initialized and pre-computation is ready
        if (tracker->is_initialized())
        {
            // Retrieve cached JSON from async computation (non-blocking check)
            if (!snapshot_cache_.has_value() && snapshot_cache_future_.valid() &&
                snapshot_cache_future_.wait_for(std::chrono::milliseconds(0)) ==
                    std::future_status::ready)
            {
                snapshot_cache_ = snapshot_cache_future_.get();
            }

            if (snapshot_cache_.has_value())
            {
                IPCMessage response;
                response.type = IPCMessageType::TRACKER_SNAPSHOT;
                response.source = IPCTarget::FRAMEWORK;
                response.target = client_id;
                response.payload = *snapshot_cache_;
                APIPCServer::get()->send_message(client_id, response);
                APLogger::get()->log(LogLevel::Info, "APManager",
                                     "Tracker snapshot sent to " + client_id);
            }
            else
            {
                APLogger::get()->log(LogLevel::Debug, "APManager",
                                     "Snapshot still computing — deferring for " + client_id);
                pending_snapshot_subscribers_.push_back(client_id);
            }
        }
    }
    else if (msg.type == IPCMessageType::UNSUBSCRIBE_TRACKER)
    {
        APTrackerEngine::get()->remove_subscriber(client_id);
        APLogger::get()->log(LogLevel::Info, "APManager", "Tracker subscriber removed: " + client_id);
    }
    // Item subscription protocol
    else if (msg.type == IPCMessageType::SUBSCRIBE_ITEMS)
    {
        bool all = msg.payload.value("all", false);
        if (all)
        {
            APMessageRouter::get()->subscribe_all_items(client_id);
        }
        else
        {
            std::vector<int64_t> ids = msg.payload.value("item_ids", std::vector<int64_t>{});

            // Resolve names to IDs (for foreign items the client can't resolve locally)
            for (const auto &name_val : msg.payload.value("item_names", nlohmann::json::array()))
            {
                const std::string name = name_val.get<std::string>();
                for (const auto &item : APCapabilities::get()->get_all_items())
                {
                    if (item.item_name == name) { ids.push_back(item.item_id); break; }
                }
            }
            APMessageRouter::get()->subscribe_items(client_id, ids);
        }
    }
    else if (msg.type == IPCMessageType::UNSUBSCRIBE_ITEMS)
    {
        bool all = msg.payload.value("all", false);
        if (all)
        {
            APMessageRouter::get()->unsubscribe_all_items(client_id);
        }
        else
        {
            std::vector<int64_t> ids = msg.payload.value("item_ids", std::vector<int64_t>{});
            APMessageRouter::get()->unsubscribe_items(client_id, ids);
        }
    }
    else if (msg.type == IPCMessageType::ITEM_HANDLED)
    {
        std::string item_name_str = msg.payload.value("item_name", "");
        int64_t item_id = msg.payload.value("item_id", int64_t(-1));
        if (item_id < 0 && !item_name_str.empty())
        {
            auto cap_item = APCapabilities::get()->get_item_by_name(item_name_str);
            if (cap_item.has_value())
                item_id = cap_item->item_id;
        }
        if (item_id >= 0)
        {
            if (item_name_str.empty())
            {
                auto cap = APCapabilities::get()->get_item_by_id(item_id);
                if (cap.has_value()) item_name_str = cap->item_name;
            }
            bool silence = msg.payload.value("silence", false);
            int delivery_index = msg.payload.value("delivery_index", -1);
            APStateManager::get()->mark_item_handled(item_id, client_id, silence, delivery_index);
            APLogger::get()->log(LogLevel::Debug, "APManager",
                client_id + " handled item " + std::to_string(item_id)
                + " \"" + item_name_str + "\"");
        }
    }
    // Generic command system
    else if (msg.type == IPCMessageType::COMMAND)
    {
        handle_command(client_id, msg);
    }
    // Cross-mod API protocol
    else if (msg.type == IPCMessageType::API_CALL)
    {
        handle_api_call(client_id, msg);
    }
    else if (msg.type == IPCMessageType::API_RESULT)
    {
        handle_api_result(client_id, msg);
    }
}

void APManager::handle_command(const std::string &client_id, const IPCMessage &msg)
{
    std::string command = msg.payload.value("command", "");

    APLogger::get()->log(LogLevel::Debug, "APManager", "Command received from " + client_id + ": " + command);

    // --- Messaging tier: any registered client ---
    if (command == "send_to" || command == "broadcast")
    {
        if (!APModRegistry::get()->is_registered(client_id))
        {
            APLogger::get()->log(LogLevel::Warn, "APManager",
                                 "Messaging command rejected - not registered: " + client_id);

            IPCMessage response;
            response.type = IPCMessageType::COMMAND_RESPONSE;
            response.source = IPCTarget::FRAMEWORK;
            response.target = client_id;
            response.payload = {{"command", command}, {"success", false}, {"error", "Not a registered client"}};
            APIPCServer::get()->send_message(client_id, response);
            return;
        }

        // Handle messaging commands (send_to / broadcast) below in the main dispatch
    }
    // --- Admin tier: priority clients only ---
    else if (!APModRegistry::get()->is_priority_client(client_id))
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "Command rejected - not a priority client: " + client_id);

        IPCMessage response;
        response.type = IPCMessageType::COMMAND_RESPONSE;
        response.source = IPCTarget::FRAMEWORK;
        response.target = client_id;
        response.payload = {{"command", command}, {"success", false}, {"error", "Not a priority client"}};
        APIPCServer::get()->send_message(client_id, response);
        return;
    }

    // Execute command
    nlohmann::json result;

    if (command == "restart")
    {
        cmd_restart();
        result = {{"success", true}};
    }
    else if (command == "resync")
    {
        cmd_resync();
        result = {{"success", true}};
    }
    else if (command == "reconnect")
    {
        cmd_reconnect();
        result = {{"success", true}};
    }
    else if (command == "status")
    {
        size_t total = APModRegistry::get()->count();
        size_t pending = APModRegistry::get()->get_pending_registrations().size();
        size_t registered = total - pending;

        result = {{"success", true},
                  {"data",
                   {{"state", lifecycle_state_to_string(current_state_.get())},
                    {"connected_clients", APIPCServer::get()->get_client_count()},
                    {"ap_connected", APArchipelagoClient::get()->is_slot_connected()},
                    {"registered_mods", registered},
                    {"total_mods", total}}}};
    }
    else if (command == "get_mods")
    {
        auto manifests = APModRegistry::get()->get_enabled_manifests();
        nlohmann::json mods_arr = nlohmann::json::array();
        for (const auto &m : manifests)
        {
            mods_arr.push_back({{"mod_id", m.mod_id},
                                {"name", m.name},
                                {"version", m.version},
                                {"registered", APModRegistry::get()->is_registered(m.mod_id)}});
        }
        result = {{"success", true}, {"data", {{"mods", mods_arr}}}};
    }
    else if (command == "regenerate")
    {
        // Re-read current capabilities and update APGeneratedConfig (preserves option modifications)
        std::string caps_json = APCapabilities::get()->generate_capabilities_config().to_json().dump(2);
        APGeneratedConfig::get()->set_capabilities_from_json(caps_json);

        if (APGeneratedConfig::get()->save_yaml())
        {
            result = {{"success", true}};
        }
        else
        {
            result = {{"success", false}, {"error", "Failed to save YAML (no path set or write failed)"}};
        }
    }
    else if (command == "send_to")
    {
        // User payload is nested under msg.payload["payload"] by the Lua command() function
        nlohmann::json params = msg.payload.value("payload", nlohmann::json::object());
        std::string target_mod = params.value("target_mod", "");

        if (target_mod.empty())
        {
            result = {{"success", false}, {"error", "Missing 'target_mod' in payload"}};
        }
        else
        {
            // Forward all params except routing fields as the message payload
            nlohmann::json fwd_payload = params;
            fwd_payload.erase("target_mod");
            fwd_payload["_source"] = client_id;

            IPCMessage forwarded;
            forwarded.type = IPCMessageType::AP_MESSAGE;
            forwarded.source = client_id;
            forwarded.target = target_mod;
            forwarded.payload = fwd_payload;

            bool sent = APIPCServer::get()->send_message(target_mod, forwarded);
            result = {{"success", sent}};
            if (!sent)
                result["error"] = "Failed to send to mod: " + target_mod;
        }
    }
    else if (command == "broadcast")
    {
        nlohmann::json params = msg.payload.value("payload", nlohmann::json::object());
        params["_source"] = client_id;

        IPCMessage forwarded;
        forwarded.type = IPCMessageType::AP_MESSAGE;
        forwarded.source = client_id;
        forwarded.target = IPCTarget::BROADCAST;
        forwarded.payload = params;

        APIPCServer::get()->broadcast_except(forwarded, client_id);
        result = {{"success", true}};
    }
    else
    {
        result = {{"success", false}, {"error", "Unknown command: " + command}};
    }

    // Send response
    IPCMessage response;
    response.type = IPCMessageType::COMMAND_RESPONSE;
    response.source = IPCTarget::FRAMEWORK;
    response.target = client_id;
    response.payload = result;
    response.payload["command"] = command;
    APIPCServer::get()->send_message(client_id, response);
}

void APManager::handle_api_call(const std::string &client_id, const IPCMessage &msg)
{
    std::string target_mod = msg.payload.value("target_mod", "");
    uint64_t call_id = msg.payload.value("call_id", uint64_t(0));
    bool wants_result = msg.payload.value("wants_result", false);

    // 1. Validate caller is registered
    if (!APModRegistry::get()->is_registered(client_id))
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "API call rejected - not registered: " + client_id);
        if (wants_result)
        {
            IPCMessage err_msg;
            err_msg.type = IPCMessageType::API_RESULT;
            err_msg.source = IPCTarget::FRAMEWORK;
            err_msg.target = client_id;
            err_msg.payload = {{"call_id", call_id}, {"error", "Not a registered client"}};
            APIPCServer::get()->send_message(client_id, err_msg);
        }
        return;
    }

    // 2. Validate depends relationship
    auto caller_manifest = APModRegistry::get()->get_manifest(client_id);
    bool has_dependency = false;
    if (caller_manifest)
    {
        for (const auto &dep : caller_manifest->depends)
        {
            if (dep.mod_id == target_mod)
            {
                has_dependency = true;
                break;
            }
        }
    }
    if (!has_dependency)
    {
        APLogger::get()->log(LogLevel::Warn, "APManager",
                             "API call rejected - '" + client_id + "' does not depend on '" + target_mod + "'");
        if (wants_result)
        {
            IPCMessage err_msg;
            err_msg.type = IPCMessageType::API_RESULT;
            err_msg.source = IPCTarget::FRAMEWORK;
            err_msg.target = client_id;
            err_msg.payload = {{"call_id", call_id},
                               {"error", "Mod '" + client_id + "' does not declare dependency on '" + target_mod + "'"}};
            APIPCServer::get()->send_message(client_id, err_msg);
        }
        return;
    }

    // 3. Validate target is connected
    if (!APModRegistry::get()->is_registered(target_mod))
    {
        APLogger::get()->log(LogLevel::Warn, "APManager", "API call rejected - target not connected: " + target_mod);
        if (wants_result)
        {
            IPCMessage err_msg;
            err_msg.type = IPCMessageType::API_RESULT;
            err_msg.source = IPCTarget::FRAMEWORK;
            err_msg.target = client_id;
            err_msg.payload = {{"call_id", call_id}, {"error", "Target mod not connected: " + target_mod}};
            APIPCServer::get()->send_message(client_id, err_msg);
        }
        return;
    }

    // 4. Forward to target with _source injected
    IPCMessage forwarded;
    forwarded.type = IPCMessageType::API_CALL;
    forwarded.source = client_id;
    forwarded.target = target_mod;
    forwarded.payload = msg.payload;
    forwarded.payload["_source"] = client_id;
    forwarded.payload.erase("target_mod");

    APIPCServer::get()->send_message(target_mod, forwarded);

    APLogger::get()->log(LogLevel::Debug, "APManager",
                         "API call forwarded: " + client_id + " -> " + target_mod + "::" +
                             msg.payload.value("function", "?"));
}

void APManager::handle_api_result(const std::string &client_id, const IPCMessage &msg)
{
    std::string target_mod = msg.payload.value("target_mod", "");

    // Forward result back to the original caller
    IPCMessage forwarded;
    forwarded.type = IPCMessageType::API_RESULT;
    forwarded.source = client_id;
    forwarded.target = target_mod;
    forwarded.payload = msg.payload;
    forwarded.payload.erase("target_mod");

    APIPCServer::get()->send_message(target_mod, forwarded);

    APLogger::get()->log(LogLevel::Trace, "APManager",
                         "API result forwarded: " + client_id + " -> " + target_mod);
}

void APManager::handle_framework_event(const FrameworkEvent &event)
{
    std::visit(
        [this](auto &&arg) {
            using T = std::decay_t<decltype(arg)>;

            if constexpr (std::is_same_v<T, ItemReceivedEvent>)
            {
                int delivery_index = APStateManager::get()->get_received_item_index();
                APMessageRouter::get()->route_item_receipt(arg.item_id, arg.item_name, arg.sender,
                                                           arg.location_id, arg.is_self, delivery_index);
                APStateManager::get()->increment_received_item_index();
                // Guard: don't overwrite the session file before load_state() has run.
                // AP server replays items during CONNECTING before handle_syncing() loads state.
                if (APStateManager::get()->is_loaded())
                    APStateManager::get()->save_state();
            }
            else if constexpr (std::is_same_v<T, LocationScoutEvent>)
            {
                // Scout results handled in message router
            }
            else if constexpr (std::is_same_v<T, LifecycleEvent>)
            {
                // State changes from polling thread
                if (arg.new_state == LifecycleState::ERROR_STATE)
                {
                    transition_to_unlocked(LifecycleState::ERROR_STATE, arg.message);
                }
            }
            else if constexpr (std::is_same_v<T, ErrorEvent>)
            {
                APMessageRouter::get()->broadcast_error(arg.code, arg.message, arg.details);
            }
            else if constexpr (std::is_same_v<T, APMessageEvent>)
            {
                APMessageRouter::get()->broadcast_ap_message(arg.type, arg.message);
            }
        },
        event);
}

void APManager::handle_priority_registration(int64_t elapsed_ms)
{
    // Check if all priority clients registered
    auto priority_clients = APModRegistry::get()->get_priority_clients();
    bool all_priority_registered = true;
    for (const auto &mod_id : priority_clients)
    {
        if (!APModRegistry::get()->is_registered(mod_id))
        {
            all_priority_registered = false;
            break;
        }
    }

    if (all_priority_registered)
    {
        transition_to_unlocked(LifecycleState::REGISTRATION, "All priority clients registered");
        state_entered_at_ = std::chrono::steady_clock::now();
        return;
    }

    // Check timeout
    if (elapsed_ms >= APConfig::get()->get_timeouts().priority_registration_ms)
    {
        // Log which priority clients are still pending to aid diagnosis
        std::string pending_ids;
        for (const auto &mod_id : priority_clients)
        {
            if (!APModRegistry::get()->is_registered(mod_id))
            {
                if (!pending_ids.empty())
                    pending_ids += ", ";
                pending_ids += mod_id;
            }
        }
        APLogger::get()->log(LogLevel::Warn, "APManager",
                             "Priority registration timeout — pending: [" + pending_ids + "]");
        transition_to_unlocked(LifecycleState::REGISTRATION, "Priority timeout");
        state_entered_at_ = std::chrono::steady_clock::now();
    }
}

void APManager::handle_registration(int64_t elapsed_ms)
{
    // Check if all mods registered
    if (APModRegistry::get()->all_registered())
    {
        transition_to_unlocked(LifecycleState::CONNECTING, "All mods registered");
        state_entered_at_ = std::chrono::steady_clock::now();
        start_ap_connection();
        return;
    }

    // Check timeout
    if (elapsed_ms >= APConfig::get()->get_timeouts().registration_ms)
    {
        auto pending = APModRegistry::get()->get_pending_registrations();
        std::string pending_ids;
        for (const auto &mod_id : pending)
        {
            if (!pending_ids.empty())
                pending_ids += ", ";
            pending_ids += mod_id;
        }
        APLogger::get()->log(LogLevel::Warn, "APManager",
                             "Registration timeout — pending: [" + pending_ids + "]");
        transition_to_unlocked(LifecycleState::CONNECTING, "Registration timeout");
        state_entered_at_ = std::chrono::steady_clock::now();
        start_ap_connection();
    }
}

void APManager::handle_connecting(int64_t elapsed_ms)
{
    // Check if connected
    if (APArchipelagoClient::get()->is_slot_connected())
    {
        // Retrieve slot info stored by APArchipelagoClient when slot connected
        auto slot_info = APArchipelagoClient::get()->get_slot_info();
        if (slot_info.has_value())
        {
            APLogger::get()->log(LogLevel::Info, "APManager",
                                 "Slot connected: " + slot_info->slot_name);

            // Sync checked locations from server
            std::set<int64_t> server_checked(slot_info->checked_locations.begin(),
                                             slot_info->checked_locations.end());
            APStateManager::get()->set_checked_locations(server_checked);

            // Initialize tracker engine with option values from slot_data
            APTrackerEngine::get()->initialize(slot_info->option_values);
            APLogger::get()->log(LogLevel::Info, "APManager",
                                 "Tracker engine initialized with " +
                                     std::to_string(slot_info->option_values.size()) +
                                     " option values");

        }

        transition_to_unlocked(LifecycleState::SYNCING, "Connected to AP server");
        state_entered_at_ = std::chrono::steady_clock::now();
        return;
    }

    // Check timeout
    if (elapsed_ms >= APConfig::get()->get_timeouts().connection_ms)
    {
        transition_to_unlocked(LifecycleState::ERROR_STATE, "Connection timeout");
        APMessageRouter::get()->broadcast_error(ErrorCode::CONNECTION_FAILED, "Failed to connect to AP server",
                                                "Connection timed out");
    }
}

void APManager::handle_syncing(int64_t elapsed_ms)
{
    // Load existing state if available
    if (!state_loaded_)
    {
        APStateManager::get()->load_state();
        state_loaded_ = true;

        // Start snapshot computation NOW — after load_state() restores checked_locations
        // and after replayed items have been processed (both happen before handle_syncing()).
        // Computing here ensures the snapshot sees the correct item state and checked set.
        snapshot_cache_future_ = std::async(std::launch::async, []() -> nlohmann::json {
            APLogger::set_thread_name("Snap-Worker");
            APLogger::get()->log(LogLevel::Debug, "APManager",
                                 "Tracker snapshot computation starting");
            auto result = APTrackerEngine::get()->compute_snapshot().to_json();
            APLogger::get()->log(LogLevel::Debug, "APManager",
                                 "Tracker snapshot computation complete");
            return result;
        });
        APLogger::get()->log(LogLevel::Debug, "APManager",
                             "Tracker snapshot pre-computation started (async)");
    }

    // Validate checksum (compute_checksum uses APConfig internally)
    std::string current_checksum = APCapabilities::get()->compute_checksum();

    if (!APStateManager::get()->validate_checksum(current_checksum))
    {
        transition_to_unlocked(LifecycleState::ERROR_STATE, "Checksum mismatch");
        APMessageRouter::get()->broadcast_error(ErrorCode::CHECKSUM_MISMATCH, "Mod ecosystem changed since generation",
                                                "Please regenerate the AP World");
        return;
    }

    // Update checksum if this is first run
    if (APStateManager::get()->get_checksum().empty())
    {
        APStateManager::get()->set_checksum(current_checksum);
    }

    // Persist synced state (checksum, server info, locations) before going active
    APStateManager::get()->touch();
    APStateManager::get()->save_state();

    // Sync complete
    transition_to_unlocked(LifecycleState::ACTIVE, "Sync complete");
    APArchipelagoClient::get()->send_status_update(ClientStatus::Playing);
}

void APManager::handle_active()
{
    // Deliver deferred tracker snapshots once async pre-computation completes
    if (!pending_snapshot_subscribers_.empty())
    {
        if (!snapshot_cache_.has_value() && snapshot_cache_future_.valid() &&
            snapshot_cache_future_.wait_for(std::chrono::milliseconds(0)) ==
                std::future_status::ready)
        {
            snapshot_cache_ = snapshot_cache_future_.get();
        }

        if (snapshot_cache_.has_value())
        {
            for (const auto &subscriber : pending_snapshot_subscribers_)
            {
                IPCMessage response;
                response.type = IPCMessageType::TRACKER_SNAPSHOT;
                response.source = IPCTarget::FRAMEWORK;
                response.target = subscriber;
                response.payload = *snapshot_cache_;
                APIPCServer::get()->send_message(subscriber, response);
                APLogger::get()->log(LogLevel::Info, "APManager",
                                     "Tracker snapshot sent to " + subscriber);
            }
            pending_snapshot_subscribers_.clear();
        }
    }

    // Normal operation - events are processed in update()
    // Periodically save state
    static auto last_save = std::chrono::steady_clock::now();
    auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::seconds>(now - last_save).count() >= 30)
    {
        APStateManager::get()->touch();
        APStateManager::get()->save_state();
        last_save = now;
    }
}

void APManager::handle_resyncing(int64_t elapsed_ms)
{
    // Similar to CONNECTING but for reconnection
    if (APArchipelagoClient::get()->is_slot_connected())
    {
        transition_to_unlocked(LifecycleState::ACTIVE, "Reconnected");
        return;
    }

    // Try to reconnect
    if (!reconnect_attempted_)
    {
        start_ap_connection();
        reconnect_attempted_ = true;
    }

    // Check timeout
    if (elapsed_ms >= APConfig::get()->get_timeouts().connection_ms * 2)
    {
        transition_to_unlocked(LifecycleState::ERROR_STATE, "Reconnection failed");
    }
}

void APManager::start_ap_connection()
{
    const auto &ap_config = APConfig::get()->get_ap_server();

    // Record server info in session state so it persists to session_state.json
    APStateManager::get()->set_server_info(ap_config.host, ap_config.port);

    // Generate UUID for this client
    std::string uuid = "APFramework_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());

    // Set up AP client callbacks
    APArchipelagoClient::get()->set_room_info_callback([](const RoomInfo &info) {
        APLogger::get()->log(LogLevel::Debug, "APManager", "Room info received");

        // Connect to slot after room info
        const auto &ap = APConfig::get()->get_ap_server();
        APArchipelagoClient::get()->connect_slot(ap.slot_name, ap.password, 0x7);
    });

    APArchipelagoClient::get()->set_slot_refused_callback([](const std::vector<std::string> &errors) {
        std::string error_msg = errors.empty() ? "Unknown error" : errors[0];
        APLogger::get()->log(LogLevel::Error, "APManager", "Slot refused: " + error_msg);
    });

    // Connect using the AP World name (e.g., "APFramework"), not the actual game name (e.g., "Palworld")
    // The AP server expects the game field to match the AP World's game class variable
    // cert_store: empty string = use Windows system CA store (wswrap handles this automatically)
    APArchipelagoClient::get()->connect(ap_config.host, ap_config.port,
                                        APGeneratedConfig::get()->get_ap_world_name(), uuid, "");

    // Start polling thread
    polling_thread_->start(APConfig::get()->get_threading().polling_interval_ms);
}

} // namespace ap