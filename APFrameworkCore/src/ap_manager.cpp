#include "ap_manager.h"
#include "ap_config.h"
#include "ap_logger.h"
#include "ap_path_util.h"
#include "ap_ipc_server.h"
#include "ap_client.h"
#include "ap_polling_thread.h"
#include "ap_mod_registry.h"
#include "ap_capabilities.h"
#include "ap_state_manager.h"
#include "ap_message_router.h"
#include "ap_exports.h"

#include <sol/sol.hpp>
#include <chrono>
#include <mutex>

namespace ap {

// Global singleton instance
std::unique_ptr<APManager> g_ap_manager;

class APManager::Impl {
public:
    Impl() = default;

    ~Impl() {
        shutdown();
    }

    int init(lua_State* L) {
        std::lock_guard<std::mutex> lock(mutex_);

        lua_state_ = L;
        sol::state_view lua(L);

        // Initialize logging
        APLogger::set_thread_name("Main");

        // Transition to INITIALIZATION
        transition_to_unlocked(LifecycleState::INITIALIZATION, "Starting framework");

        // Load configuration
        if (!APConfig::instance().load_default()) {
            APLogger::instance().log(LogLevel::Warn,
                "Using default configuration");
        }
        config_ = &APConfig::instance();

        // Initialize logger with config
        APLogger::instance().init(
            config_->get_log_level(),
            APPathUtil::get_log_path().string(),
            config_->get_log_to_console()
        );

        APLogger::instance().log(LogLevel::Info,
            "AP Framework initializing...");

        // Create components
        ipc_server_ = std::make_unique<APIPCServer>();
        ap_client_ = std::make_unique<APClient>();
        polling_thread_ = std::make_unique<APPollingThread>();
        mod_registry_ = std::make_unique<APModRegistry>();
        capabilities_ = std::make_unique<APCapabilities>();
        state_manager_ = std::make_unique<APStateManager>();
        message_router_ = std::make_unique<APMessageRouter>();

        // Wire up message router
        message_router_->set_capabilities(capabilities_.get());
        message_router_->set_state_manager(state_manager_.get());
        message_router_->set_ipc_send_callback([this](const std::string& target, const IPCMessage& msg) {
            return ipc_server_->send_message(target, msg);
        });
        message_router_->set_ipc_broadcast_callback([this](const IPCMessage& msg) {
            ipc_server_->broadcast(msg);
        });
        message_router_->set_ap_location_check_callback([this](const std::vector<int64_t>& ids) {
            ap_client_->send_location_checks(ids);
        });
        message_router_->set_ap_location_scout_callback([this](const std::vector<int64_t>& ids, bool hints) {
            ap_client_->send_location_scouts(ids, hints);
        });

        // Start IPC server
        std::string game_name = config_->get_game_name();
        if (game_name.empty()) {
            game_name = "APFramework";
        }
        ipc_server_->start(game_name);

        // Set up IPC message handler
        ipc_server_->set_message_handler([this](const std::string& client_id, const IPCMessage& msg) {
            handle_ipc_message(client_id, msg);
        });

        // Transition to DISCOVERY
        transition_to_unlocked(LifecycleState::DISCOVERY, "Scanning for mods");

        // Discover manifests
        auto mods_folder = APPathUtil::find_mods_folder();
        if (mods_folder) {
            mod_registry_->discover_manifests(*mods_folder);
        }

        // Add manifests to capabilities
        for (const auto& manifest : mod_registry_->get_enabled_manifests()) {
            capabilities_->add_manifest(manifest);
        }

        // Transition to VALIDATION
        transition_to_unlocked(LifecycleState::VALIDATION, "Validating capabilities");

        // Validate for conflicts
        auto validation = capabilities_->validate();
        if (!validation.valid) {
            for (const auto& conflict : validation.conflicts) {
                APLogger::instance().log(LogLevel::Error,
                    "Conflict: " + conflict.description);
            }
            transition_to_unlocked(LifecycleState::ERROR_STATE, "Capability conflicts detected");

            // Still return module to Lua
            return create_lua_module(L);
        }

        // Transition to GENERATION
        transition_to_unlocked(LifecycleState::GENERATION, "Generating capabilities");

        // Assign IDs
        capabilities_->assign_ids(config_->get_id_base());

        // Compute and store checksum
        std::string slot_name = config_->get_ap_server().slot_name;
        std::string checksum = capabilities_->compute_checksum(game_name, slot_name);
        state_manager_->set_checksum(checksum);
        state_manager_->set_game_name(game_name);
        state_manager_->set_slot_name(slot_name);

        // Write capabilities config
        if (!slot_name.empty()) {
            capabilities_->write_capabilities_config_default(slot_name, game_name);
        }

        // Transition to PRIORITY_REGISTRATION
        transition_to_unlocked(LifecycleState::PRIORITY_REGISTRATION, "Waiting for priority clients");
        state_entered_at_ = std::chrono::steady_clock::now();

        // Check if any priority clients exist
        if (mod_registry_->get_priority_clients().empty()) {
            // No priority clients, skip to REGISTRATION
            transition_to_unlocked(LifecycleState::REGISTRATION, "No priority clients");
            state_entered_at_ = std::chrono::steady_clock::now();
        }

        APLogger::instance().log(LogLevel::Info,
            "AP Framework initialized successfully");

        return create_lua_module(L);
    }

    int update(lua_State* L) {
        std::lock_guard<std::mutex> lock(mutex_);

        lua_state_ = L;

        // Update cached Lua state for APPathUtil and other components
        update_cached_lua(L);

        // On first update, reinitialize APPathUtil to use IterateGameDirectories
        if (!first_update_done_) {
            APPathUtil::reinitialize_cache();
            first_update_done_ = true;
        }

        // Process IPC messages
        ipc_server_->poll();

        // Process AP client events
        if (polling_thread_->is_running()) {
            polling_thread_->process_events([this](const FrameworkEvent& event) {
                handle_framework_event(event);
            });
        }

        // Handle state-specific logic
        auto now = std::chrono::steady_clock::now();
        auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - state_entered_at_).count();

        switch (current_state_.get()) {
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

    void shutdown() {
        APLogger::instance().log(LogLevel::Info, "AP Framework shutting down...");

        // Save state
        if (state_manager_) {
            state_manager_->touch();
            state_manager_->save_state();
        }

        // Stop polling thread
        if (polling_thread_) {
            polling_thread_->stop(config_ ? config_->get_threading().shutdown_timeout_ms : 5000);
        }

        // Disconnect from AP server
        if (ap_client_) {
            ap_client_->disconnect();
        }

        // Stop IPC server
        if (ipc_server_) {
            ipc_server_->stop();
        }

        APLogger::instance().log(LogLevel::Info, "AP Framework shutdown complete");
    }

    LifecycleState get_state() const {
        return current_state_.get();
    }

    bool transition_to(LifecycleState new_state, const std::string& message) {
        std::lock_guard<std::mutex> lock(mutex_);
        return transition_to_unlocked(new_state, message);
    }

    bool is_active() const {
        auto state = current_state_.get();
        return state == LifecycleState::ACTIVE || state == LifecycleState::RESYNCING;
    }

    bool is_error() const {
        return current_state_.get() == LifecycleState::ERROR_STATE;
    }

    bool register_mod(const std::string& mod_id, const std::string& version) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto state = current_state_.get();
        if (state != LifecycleState::PRIORITY_REGISTRATION &&
            state != LifecycleState::REGISTRATION) {
            APLogger::instance().log(LogLevel::Warn,
                "Registration rejected - not in registration phase: " + mod_id);
            return false;
        }

        if (!mod_registry_->mark_registered(mod_id)) {
            APLogger::instance().log(LogLevel::Warn,
                "Unknown mod registration attempt: " + mod_id);
            return false;
        }

        APLogger::instance().log(LogLevel::Info,
            "Mod registered: " + mod_id + " v" + version);

        // Send registration response
        IPCMessage response;
        response.type = IPCMessageType::REGISTRATION_RESPONSE;
        response.source = IPCTarget::FRAMEWORK;
        response.target = mod_id;
        response.payload = {
            {"success", true},
            {"mod_id", mod_id}
        };
        ipc_server_->send_message(mod_id, response);

        return true;
    }

    bool register_priority_client(const std::string& mod_id, const std::string& version) {
        if (!mod_registry_->is_priority_client(mod_id)) {
            APLogger::instance().log(LogLevel::Warn,
                "Non-priority mod tried to register as priority: " + mod_id);
            return false;
        }

        return register_mod(mod_id, version);
    }

    void cmd_restart() {
        std::lock_guard<std::mutex> lock(mutex_);
        APLogger::instance().log(LogLevel::Info, "Restart command received");

        // Reset state and restart
        mod_registry_->reset_registrations();
        transition_to_unlocked(LifecycleState::DISCOVERY, "Restarting");
    }

    void cmd_resync() {
        std::lock_guard<std::mutex> lock(mutex_);
        APLogger::instance().log(LogLevel::Info, "Resync command received");

        transition_to_unlocked(LifecycleState::RESYNCING, "Manual resync requested");
    }

    void cmd_reconnect() {
        std::lock_guard<std::mutex> lock(mutex_);
        APLogger::instance().log(LogLevel::Info, "Reconnect command received");

        ap_client_->disconnect();
        transition_to_unlocked(LifecycleState::CONNECTING, "Reconnecting to AP server");
        state_entered_at_ = std::chrono::steady_clock::now();
    }

    APConfig* get_config() { return config_; }
    APModRegistry* get_mod_registry() { return mod_registry_.get(); }
    APCapabilities* get_capabilities() { return capabilities_.get(); }
    APStateManager* get_state_manager() { return state_manager_.get(); }
    APMessageRouter* get_message_router() { return message_router_.get(); }
    APIPCServer* get_ipc_server() { return ipc_server_.get(); }
    APClient* get_ap_client() { return ap_client_.get(); }

private:
    bool transition_to_unlocked(LifecycleState new_state, const std::string& message) {
        LifecycleState old_state = current_state_.get();
        current_state_.set(new_state);
        state_entered_at_ = std::chrono::steady_clock::now();

        APLogger::instance().log(LogLevel::Info,
            "State: " + lifecycle_state_to_string(old_state) +
            " -> " + lifecycle_state_to_string(new_state) +
            (message.empty() ? "" : " (" + message + ")"));

        // Broadcast lifecycle change
        if (message_router_) {
            message_router_->broadcast_lifecycle(new_state, message);
        }

        return true;
    }

    int create_lua_module(lua_State* L) {
        sol::state_view lua(L);
        sol::table module = lua.create_table();

        // Register update function
        module["update"] = [](lua_State* L) {
            return APManager::get()->update(L);
        };

        // Register state query
        module["get_state"] = []() {
            return lifecycle_state_to_string(APManager::get()->get_state());
        };

        // Register shutdown
        module["shutdown"] = []() {
            APManager::get()->shutdown();
        };

        return sol::stack::push(L, module);
    }

    void handle_ipc_message(const std::string& client_id, const IPCMessage& msg) {
        APLogger::instance().log(LogLevel::Debug,
            "IPC message from " + client_id + ": " + msg.type);

        if (msg.type == IPCMessageType::REGISTER) {
            std::string mod_id = msg.payload.value("mod_id", "");
            std::string version = msg.payload.value("version", "1.0.0");
            register_mod(mod_id, version);
        }
        else if (msg.type == IPCMessageType::LOCATION_CHECK) {
            std::string location_name = msg.payload.value("location", "");
            int instance = msg.payload.value("instance", 1);
            message_router_->route_location_check(client_id, location_name, instance);
        }
        else if (msg.type == IPCMessageType::LOCATION_SCOUT) {
            std::vector<std::string> locations;
            if (msg.payload.contains("locations") && msg.payload["locations"].is_array()) {
                for (const auto& loc : msg.payload["locations"]) {
                    locations.push_back(loc.get<std::string>());
                }
            }
            message_router_->route_location_scouts(client_id, locations, false);
        }
        else if (msg.type == IPCMessageType::ACTION_RESULT) {
            ActionResult result;
            result.mod_id = client_id;
            result.item_id = msg.payload.value("item_id", 0LL);
            result.item_name = msg.payload.value("item_name", "");
            result.success = msg.payload.value("success", false);
            result.error = msg.payload.value("error", "");
            message_router_->handle_action_result(client_id, result);
        }
        else if (msg.type == IPCMessageType::LOG) {
            std::string level_str = msg.payload.value("level", "info");
            std::string message = msg.payload.value("message", "");
            LogLevel level = LogLevel::Info;
            if (level_str == "debug") level = LogLevel::Debug;
            else if (level_str == "warn") level = LogLevel::Warn;
            else if (level_str == "error") level = LogLevel::Error;
            APLogger::instance().log(level, "[" + client_id + "] " + message);
        }
        // Priority client commands
        else if (msg.type == IPCMessageType::CMD_RESTART) {
            if (mod_registry_->is_priority_client(client_id)) {
                cmd_restart();
            }
        }
        else if (msg.type == IPCMessageType::CMD_RESYNC) {
            if (mod_registry_->is_priority_client(client_id)) {
                cmd_resync();
            }
        }
        else if (msg.type == IPCMessageType::CMD_RECONNECT) {
            if (mod_registry_->is_priority_client(client_id)) {
                cmd_reconnect();
            }
        }
    }

    void handle_framework_event(const FrameworkEvent& event) {
        std::visit([this](auto&& arg) {
            using T = std::decay_t<decltype(arg)>;

            if constexpr (std::is_same_v<T, ItemReceivedEvent>) {
                message_router_->route_item_receipt(arg.item_id, arg.item_name, arg.sender);
                state_manager_->increment_received_item_index();
                state_manager_->save_state();
            }
            else if constexpr (std::is_same_v<T, LocationScoutEvent>) {
                // Scout results handled in message router
            }
            else if constexpr (std::is_same_v<T, LifecycleEvent>) {
                // State changes from polling thread
                if (arg.new_state == LifecycleState::ERROR_STATE) {
                    transition_to_unlocked(LifecycleState::ERROR_STATE, arg.message);
                }
            }
            else if constexpr (std::is_same_v<T, ErrorEvent>) {
                message_router_->broadcast_error(arg.code, arg.message, arg.details);
            }
            else if constexpr (std::is_same_v<T, APMessageEvent>) {
                message_router_->broadcast_ap_message(arg.type, arg.message);
            }
        }, event);
    }

    void handle_priority_registration(int64_t elapsed_ms) {
        // Check if all priority clients registered
        auto priority_clients = mod_registry_->get_priority_clients();
        bool all_priority_registered = true;
        for (const auto& mod_id : priority_clients) {
            if (!mod_registry_->is_registered(mod_id)) {
                all_priority_registered = false;
                break;
            }
        }

        if (all_priority_registered) {
            transition_to_unlocked(LifecycleState::REGISTRATION, "All priority clients registered");
            state_entered_at_ = std::chrono::steady_clock::now();
            return;
        }

        // Check timeout
        if (elapsed_ms >= config_->get_timeouts().priority_registration_ms) {
            APLogger::instance().log(LogLevel::Warn,
                "Priority registration timeout, continuing anyway");
            transition_to_unlocked(LifecycleState::REGISTRATION, "Priority timeout");
            state_entered_at_ = std::chrono::steady_clock::now();
        }
    }

    void handle_registration(int64_t elapsed_ms) {
        // Check if all mods registered
        if (mod_registry_->all_registered()) {
            transition_to_unlocked(LifecycleState::CONNECTING, "All mods registered");
            state_entered_at_ = std::chrono::steady_clock::now();
            start_ap_connection();
            return;
        }

        // Check timeout
        if (elapsed_ms >= config_->get_timeouts().registration_ms) {
            auto pending = mod_registry_->get_pending_registrations();
            APLogger::instance().log(LogLevel::Warn,
                "Registration timeout. Pending: " + std::to_string(pending.size()) + " mods");
            transition_to_unlocked(LifecycleState::CONNECTING, "Registration timeout");
            state_entered_at_ = std::chrono::steady_clock::now();
            start_ap_connection();
        }
    }

    void handle_connecting(int64_t elapsed_ms) {
        // Check if connected
        if (ap_client_->is_slot_connected()) {
            transition_to_unlocked(LifecycleState::SYNCING, "Connected to AP server");
            state_entered_at_ = std::chrono::steady_clock::now();
            return;
        }

        // Check timeout
        if (elapsed_ms >= config_->get_timeouts().connection_ms) {
            transition_to_unlocked(LifecycleState::ERROR_STATE, "Connection timeout");
            message_router_->broadcast_error(
                ErrorCode::CONNECTION_FAILED,
                "Failed to connect to AP server",
                "Connection timed out"
            );
        }
    }

    void handle_syncing(int64_t elapsed_ms) {
        // Load existing state if available
        if (!state_loaded_) {
            state_manager_->load_state();
            state_loaded_ = true;
        }

        // Validate checksum
        std::string current_checksum = capabilities_->compute_checksum(
            config_->get_game_name(),
            config_->get_ap_server().slot_name
        );

        if (!state_manager_->validate_checksum(current_checksum)) {
            transition_to_unlocked(LifecycleState::ERROR_STATE, "Checksum mismatch");
            message_router_->broadcast_error(
                ErrorCode::CHECKSUM_MISMATCH,
                "Mod ecosystem changed since generation",
                "Please regenerate the AP World"
            );
            return;
        }

        // Update checksum if this is first run
        if (state_manager_->get_checksum().empty()) {
            state_manager_->set_checksum(current_checksum);
        }

        // Sync complete
        transition_to_unlocked(LifecycleState::ACTIVE, "Sync complete");
        ap_client_->send_status_update(ClientStatus::Playing);
    }

    void handle_active() {
        // Normal operation - events are processed in update()
        // Periodically save state
        static auto last_save = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_save).count() >= 30) {
            state_manager_->touch();
            state_manager_->save_state();
            last_save = now;
        }
    }

    void handle_resyncing(int64_t elapsed_ms) {
        // Similar to CONNECTING but for reconnection
        if (ap_client_->is_slot_connected()) {
            transition_to_unlocked(LifecycleState::ACTIVE, "Reconnected");
            return;
        }

        // Try to reconnect
        if (!reconnect_attempted_) {
            start_ap_connection();
            reconnect_attempted_ = true;
        }

        // Check timeout
        if (elapsed_ms >= config_->get_timeouts().connection_ms * 2) {
            transition_to_unlocked(LifecycleState::ERROR_STATE, "Reconnection failed");
        }
    }

    void start_ap_connection() {
        const auto& ap_config = config_->get_ap_server();

        // Generate UUID for this client
        std::string uuid = "APFramework_" + std::to_string(
            std::chrono::system_clock::now().time_since_epoch().count()
        );

        // Set up AP client callbacks
        ap_client_->set_room_info_callback([this](const RoomInfo& info) {
            APLogger::instance().log(LogLevel::Debug, "Room info received");

            // Connect to slot after room info
            const auto& ap = config_->get_ap_server();
            ap_client_->connect_slot(ap.slot_name, ap.password, 0x7);
        });

        ap_client_->set_slot_connected_callback([this](const SlotInfo& info) {
            APLogger::instance().log(LogLevel::Info,
                "Slot connected: " + info.slot_name);

            // Sync checked locations from server
            std::set<int64_t> server_checked(
                info.checked_locations.begin(),
                info.checked_locations.end()
            );
            state_manager_->set_checked_locations(server_checked);
        });

        ap_client_->set_slot_refused_callback([this](const std::vector<std::string>& errors) {
            std::string error_msg = errors.empty() ? "Unknown error" : errors[0];
            APLogger::instance().log(LogLevel::Error, "Slot refused: " + error_msg);
        });

        // Connect
        ap_client_->connect(
            ap_config.server,
            ap_config.port,
            config_->get_game_name(),
            uuid
        );

        // Start polling thread
        polling_thread_->start(ap_client_.get(), config_->get_threading().polling_interval_ms);
    }

    std::mutex mutex_;
    lua_State* lua_state_ = nullptr;
    AtomicState current_state_;
    std::chrono::steady_clock::time_point state_entered_at_;

    APConfig* config_ = nullptr;
    std::unique_ptr<APIPCServer> ipc_server_;
    std::unique_ptr<APClient> ap_client_;
    std::unique_ptr<APPollingThread> polling_thread_;
    std::unique_ptr<APModRegistry> mod_registry_;
    std::unique_ptr<APCapabilities> capabilities_;
    std::unique_ptr<APStateManager> state_manager_;
    std::unique_ptr<APMessageRouter> message_router_;

    bool state_loaded_ = false;
    bool reconnect_attempted_ = false;
    bool first_update_done_ = false;
};

// =============================================================================
// Public API
// =============================================================================

APManager* APManager::get() {
    if (!g_ap_manager) {
        g_ap_manager = std::unique_ptr<APManager>(new APManager());
    }
    return g_ap_manager.get();
}

APManager::APManager() : impl_(std::make_unique<Impl>()) {}
APManager::~APManager() = default;

int APManager::init(lua_State* L) {
    return impl_->init(L);
}

int APManager::update(lua_State* L) {
    return impl_->update(L);
}

void APManager::shutdown() {
    impl_->shutdown();
}

LifecycleState APManager::get_state() const {
    return impl_->get_state();
}

bool APManager::transition_to(LifecycleState new_state, const std::string& message) {
    return impl_->transition_to(new_state, message);
}

bool APManager::is_active() const {
    return impl_->is_active();
}

bool APManager::is_error() const {
    return impl_->is_error();
}

bool APManager::register_mod(const std::string& mod_id, const std::string& version) {
    return impl_->register_mod(mod_id, version);
}

bool APManager::register_priority_client(const std::string& mod_id, const std::string& version) {
    return impl_->register_priority_client(mod_id, version);
}

void APManager::cmd_restart() {
    impl_->cmd_restart();
}

void APManager::cmd_resync() {
    impl_->cmd_resync();
}

void APManager::cmd_reconnect() {
    impl_->cmd_reconnect();
}

APConfig* APManager::get_config() {
    return impl_->get_config();
}

APModRegistry* APManager::get_mod_registry() {
    return impl_->get_mod_registry();
}

APCapabilities* APManager::get_capabilities() {
    return impl_->get_capabilities();
}

APStateManager* APManager::get_state_manager() {
    return impl_->get_state_manager();
}

APMessageRouter* APManager::get_message_router() {
    return impl_->get_message_router();
}

APIPCServer* APManager::get_ipc_server() {
    return impl_->get_ipc_server();
}

APClient* APManager::get_ap_client() {
    return impl_->get_ap_client();
}

} // namespace ap
