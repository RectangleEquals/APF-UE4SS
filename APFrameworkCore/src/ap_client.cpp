#include "ap_client.h"
#include "ap_logger.h"

#include <apclient.hpp>
#include <mutex>
#include <atomic>
#include <list>

// Type alias for the external APClient library (avoids collision with ap::APClient)
using APClientLib = ::APClient;

namespace ap {

// =============================================================================
// Implementation
// =============================================================================

class APClient::Impl {
public:
    Impl() = default;

    ~Impl() {
        disconnect();
    }

    bool connect(const std::string& server, int port,
                 const std::string& game, const std::string& uuid) {
        if (client_) {
            disconnect();
        }

        game_ = game;
        uuid_ = uuid;

        // Build URI
        std::string uri = "ws://" + server + ":" + std::to_string(port);

        try {
            client_ = std::make_unique<APClientLib>(uuid, game, uri);

            // Set up callbacks
            setup_callbacks();

            APLogger::instance().log(LogLevel::Info,
                "AP Client connecting to: " + uri);

            return true;

        } catch (const std::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to create AP client: " + std::string(e.what()));
            return false;
        }
    }

    bool connect_slot(const std::string& slot_name,
                      const std::string& password,
                      int items_handling) {
        if (!client_) {
            return false;
        }

        slot_name_ = slot_name;
        password_ = password;

        try {
            // Items handling: 0x1 = remote_items, 0x2 = remote_items_all, 0x4 = receive_own_world
            client_->ConnectSlot(slot_name, password, items_handling, {"Lua"}, {0, 5, 0});

            APLogger::instance().log(LogLevel::Info,
                "Connecting to slot: " + slot_name);

            return true;

        } catch (const std::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to connect slot: " + std::string(e.what()));
            return false;
        }
    }

    void disconnect() {
        if (client_) {
            client_.reset();
        }
        slot_connected_ = false;
        slot_info_.reset();
    }

    bool is_connected() const {
        return client_ && client_->get_state() != APClientLib::State::DISCONNECTED;
    }

    bool is_slot_connected() const {
        return slot_connected_;
    }

    void poll() {
        if (client_) {
            client_->poll();
        }
    }

    void send_location_checks(const std::vector<int64_t>& location_ids) {
        if (client_ && slot_connected_) {
            std::list<int64_t> ids_list(location_ids.begin(), location_ids.end());
            client_->LocationChecks(ids_list);
        }
    }

    void send_location_scouts(const std::vector<int64_t>& location_ids,
                              bool create_as_hint) {
        if (client_ && slot_connected_) {
            std::list<int64_t> ids_list(location_ids.begin(), location_ids.end());
            client_->LocationScouts(ids_list, create_as_hint ? 2 : 0);
        }
    }

    void send_status_update(ClientStatus status) {
        if (client_ && slot_connected_) {
            client_->StatusUpdate(static_cast<APClientLib::ClientStatus>(status));
        }
    }

    void send_say(const std::string& message) {
        if (client_ && slot_connected_) {
            client_->Say(message);
        }
    }

    void send_bounce(const std::vector<std::string>& games,
                     const std::vector<int>& slots,
                     const std::vector<std::string>& tags,
                     const nlohmann::json& data) {
        if (client_ && slot_connected_) {
            std::list<std::string> games_list(games.begin(), games.end());
            std::list<int> slots_list(slots.begin(), slots.end());
            std::list<std::string> tags_list(tags.begin(), tags.end());
            client_->Bounce(data, games_list, slots_list, tags_list);
        }
    }

    std::optional<SlotInfo> get_slot_info() const {
        return slot_info_;
    }

    std::string get_location_name(int64_t location_id) const {
        if (client_) {
            return client_->get_location_name(location_id, game_);
        }
        return "";
    }

    std::string get_item_name(int64_t item_id) const {
        if (client_) {
            return client_->get_item_name(item_id, game_);
        }
        return "";
    }

    std::string get_player_name(int player_id) const {
        if (client_) {
            return client_->get_player_alias(player_id);
        }
        return "";
    }

    int get_player_number() const {
        if (client_) {
            return client_->get_player_number();
        }
        return -1;
    }

    int get_received_item_index() const {
        // Track this ourselves since apclientpp doesn't directly expose it
        return received_item_index_;
    }

    // Callback setters
    void set_room_info_callback(RoomInfoCallback callback) {
        room_info_callback_ = std::move(callback);
    }

    void set_slot_connected_callback(SlotConnectedCallback callback) {
        slot_connected_callback_ = std::move(callback);
    }

    void set_slot_refused_callback(SlotRefusedCallback callback) {
        slot_refused_callback_ = std::move(callback);
    }

    void set_item_received_callback(ItemReceivedCallback callback) {
        item_received_callback_ = std::move(callback);
    }

    void set_location_scouted_callback(LocationScoutedCallback callback) {
        location_scouted_callback_ = std::move(callback);
    }

    void set_disconnected_callback(DisconnectedCallback callback) {
        disconnected_callback_ = std::move(callback);
    }

    void set_print_callback(PrintCallback callback) {
        print_callback_ = std::move(callback);
    }

    void set_print_json_callback(PrintJsonCallback callback) {
        print_json_callback_ = std::move(callback);
    }

    void set_bounced_callback(BouncedCallback callback) {
        bounced_callback_ = std::move(callback);
    }

private:
    void setup_callbacks() {
        if (!client_) return;

        // Room info - fires when WebSocket connects
        client_->set_room_info_handler([this]() {
            APLogger::instance().log(LogLevel::Debug, "Received room_info");

            RoomInfo info;
            // Note: apclientpp doesn't expose all room info fields directly
            // We'll populate what we can

            if (room_info_callback_) {
                room_info_callback_(info);
            }

            // Auto-connect to slot if credentials are stored
            if (!slot_name_.empty()) {
                connect_slot(slot_name_, password_, 0x7);
            }
        });

        // Slot connected
        client_->set_slot_connected_handler([this](const nlohmann::json& slot_data) {
            APLogger::instance().log(LogLevel::Info, "Slot connected");

            slot_connected_ = true;

            SlotInfo info;
            info.slot_id = client_->get_player_number();
            info.slot_name = slot_name_;
            info.game = game_;

            // Extract checked locations
            if (slot_data.contains("checked_locations")) {
                for (const auto& loc : slot_data["checked_locations"]) {
                    info.checked_locations.push_back(loc.get<int64_t>());
                }
            }

            // Extract missing locations
            if (slot_data.contains("missing_locations")) {
                for (const auto& loc : slot_data["missing_locations"]) {
                    info.missing_locations.push_back(loc.get<int64_t>());
                }
            }

            slot_info_ = info;

            if (slot_connected_callback_) {
                slot_connected_callback_(info);
            }
        });

        // Slot refused
        client_->set_slot_refused_handler([this](const std::list<std::string>& errors) {
            APLogger::instance().log(LogLevel::Error, "Slot connection refused");

            slot_connected_ = false;
            std::vector<std::string> error_vec(errors.begin(), errors.end());

            if (slot_refused_callback_) {
                slot_refused_callback_(error_vec);
            }
        });

        // Items received
        client_->set_items_received_handler([this](const std::list<APClientLib::NetworkItem>& items) {
            for (const auto& item : items) {
                ReceivedItem received;
                received.item_id = item.item;
                received.location_id = item.location;
                received.player_id = item.player;
                received.item_name = get_item_name(item.item);
                received.player_name = get_player_name(item.player);
                received.index = received_item_index_++;

                APLogger::instance().log(LogLevel::Debug,
                    "Received item: " + received.item_name +
                    " from " + received.player_name);

                if (item_received_callback_) {
                    item_received_callback_(received);
                }
            }
        });

        // Location info (scout results)
        client_->set_location_info_handler([this](const std::list<APClientLib::NetworkItem>& items) {
            std::vector<ScoutResult> results;
            for (const auto& item : items) {
                ScoutResult result;
                result.location_id = item.location;
                result.item_id = item.item;
                result.player_id = item.player;
                result.item_name = get_item_name(item.item);
                result.player_name = get_player_name(item.player);
                results.push_back(result);
            }

            if (location_scouted_callback_ && !results.empty()) {
                location_scouted_callback_(results);
            }
        });

        // Socket disconnected
        client_->set_socket_disconnected_handler([this]() {
            APLogger::instance().log(LogLevel::Warn, "Socket disconnected");
            slot_connected_ = false;

            if (disconnected_callback_) {
                disconnected_callback_();
            }
        });

        // Print messages
        client_->set_print_handler([this](const std::string& msg) {
            if (print_callback_) {
                print_callback_(msg);
            }
        });

        // Print JSON messages
        client_->set_print_json_handler([this](const std::list<APClientLib::TextNode>& msg) {
            // Convert to JSON for callback
            nlohmann::json data = nlohmann::json::array();
            for (const auto& node : msg) {
                nlohmann::json obj;
                obj["type"] = node.type;
                obj["text"] = node.text;
                // Additional fields based on type could be added
                data.push_back(obj);
            }

            if (print_json_callback_) {
                print_json_callback_("print", data);
            }
        });

        // Bounced packets
        client_->set_bounced_handler([this](const nlohmann::json& data) {
            if (bounced_callback_) {
                bounced_callback_(data);
            }
        });
    }

    std::unique_ptr<APClientLib> client_;

    std::string game_;
    std::string uuid_;
    std::string slot_name_;
    std::string password_;

    std::atomic<bool> slot_connected_{false};
    std::optional<SlotInfo> slot_info_;
    std::atomic<int> received_item_index_{0};

    // Callbacks
    RoomInfoCallback room_info_callback_;
    SlotConnectedCallback slot_connected_callback_;
    SlotRefusedCallback slot_refused_callback_;
    ItemReceivedCallback item_received_callback_;
    LocationScoutedCallback location_scouted_callback_;
    DisconnectedCallback disconnected_callback_;
    PrintCallback print_callback_;
    PrintJsonCallback print_json_callback_;
    BouncedCallback bounced_callback_;
};

// =============================================================================
// Public API
// =============================================================================

APClient::APClient() : impl_(std::make_unique<Impl>()) {}
APClient::~APClient() = default;

bool APClient::connect(const std::string& server, int port,
                       const std::string& game, const std::string& uuid) {
    return impl_->connect(server, port, game, uuid);
}

bool APClient::connect_slot(const std::string& slot_name,
                            const std::string& password,
                            int items_handling) {
    return impl_->connect_slot(slot_name, password, items_handling);
}

void APClient::disconnect() {
    impl_->disconnect();
}

bool APClient::is_connected() const {
    return impl_->is_connected();
}

bool APClient::is_slot_connected() const {
    return impl_->is_slot_connected();
}

void APClient::poll() {
    impl_->poll();
}

void APClient::send_location_checks(const std::vector<int64_t>& location_ids) {
    impl_->send_location_checks(location_ids);
}

void APClient::send_location_scouts(const std::vector<int64_t>& location_ids,
                                    bool create_as_hint) {
    impl_->send_location_scouts(location_ids, create_as_hint);
}

void APClient::send_status_update(ClientStatus status) {
    impl_->send_status_update(status);
}

void APClient::send_say(const std::string& message) {
    impl_->send_say(message);
}

void APClient::send_bounce(const std::vector<std::string>& games,
                           const std::vector<int>& slots,
                           const std::vector<std::string>& tags,
                           const nlohmann::json& data) {
    impl_->send_bounce(games, slots, tags, data);
}

std::optional<SlotInfo> APClient::get_slot_info() const {
    return impl_->get_slot_info();
}

std::string APClient::get_location_name(int64_t location_id) const {
    return impl_->get_location_name(location_id);
}

std::string APClient::get_item_name(int64_t item_id) const {
    return impl_->get_item_name(item_id);
}

std::string APClient::get_player_name(int player_id) const {
    return impl_->get_player_name(player_id);
}

int APClient::get_player_number() const {
    return impl_->get_player_number();
}

int APClient::get_received_item_index() const {
    return impl_->get_received_item_index();
}

void APClient::set_room_info_callback(RoomInfoCallback callback) {
    impl_->set_room_info_callback(std::move(callback));
}

void APClient::set_slot_connected_callback(SlotConnectedCallback callback) {
    impl_->set_slot_connected_callback(std::move(callback));
}

void APClient::set_slot_refused_callback(SlotRefusedCallback callback) {
    impl_->set_slot_refused_callback(std::move(callback));
}

void APClient::set_item_received_callback(ItemReceivedCallback callback) {
    impl_->set_item_received_callback(std::move(callback));
}

void APClient::set_location_scouted_callback(LocationScoutedCallback callback) {
    impl_->set_location_scouted_callback(std::move(callback));
}

void APClient::set_disconnected_callback(DisconnectedCallback callback) {
    impl_->set_disconnected_callback(std::move(callback));
}

void APClient::set_print_callback(PrintCallback callback) {
    impl_->set_print_callback(std::move(callback));
}

void APClient::set_print_json_callback(PrintJsonCallback callback) {
    impl_->set_print_json_callback(std::move(callback));
}

void APClient::set_bounced_callback(BouncedCallback callback) {
    impl_->set_bounced_callback(std::move(callback));
}

} // namespace ap
