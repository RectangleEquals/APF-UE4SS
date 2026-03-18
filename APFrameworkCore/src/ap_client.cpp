#include "ap_client.h"
#include "ap_capabilities.h"
#include "ap_logger.h"

#include <apclient.hpp>
#include <list>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APArchipelagoClient *APArchipelagoClient::get()
{
    static std::unique_ptr<APArchipelagoClient> instance = std::make_unique<APArchipelagoClient>(ConstructorKey{});
    return instance.get();
}

APArchipelagoClient::APArchipelagoClient(ConstructorKey)
{
    // Default initialization
}

APArchipelagoClient::~APArchipelagoClient()
{
    disconnect();
}

// =============================================================================
// Connection
// =============================================================================

bool APArchipelagoClient::connect(const std::string &server, int port, const std::string &game,
                                   const std::string &uuid, const std::string &cert_store)
{
    if (client_)
    {
        disconnect();
    }

    game_ = game;
    uuid_ = uuid;

    // Build URI WITHOUT scheme prefix — apclientpp auto-tries wss:// then ws://
    std::string uri = server + ":" + std::to_string(port);

    try
    {
        client_ = std::make_unique<::APClient>(uuid, game, uri, cert_store);

        // Set up callbacks
        setup_callbacks();

        APLogger::get()->log(LogLevel::Info, "APArchipelagoClient",
                             "AP Client connecting to: " + uri + " (TLS auto-negotiation enabled)");

        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APArchipelagoClient",
                             "Failed to create AP client: " + std::string(e.what()));
        return false;
    }
}

bool APArchipelagoClient::connect_slot(const std::string &slot_name, const std::string &password, int items_handling)
{
    if (!client_)
    {
        return false;
    }

    slot_name_ = slot_name;
    password_ = password;

    try
    {
        // Items handling: 0x1 = remote_items, 0x2 = remote_items_all, 0x4 = receive_own_world
        client_->ConnectSlot(slot_name, password, items_handling, {"Lua"}, {0, 5, 0});

        APLogger::get()->log(LogLevel::Info, "APArchipelagoClient", "Connecting to slot: " + slot_name);

        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APArchipelagoClient",
                             "Failed to connect slot: " + std::string(e.what()));
        return false;
    }
}

void APArchipelagoClient::disconnect()
{
    if (client_)
    {
        client_.reset();
    }
    slot_connected_ = false;
    slot_info_.reset();
}

bool APArchipelagoClient::is_connected() const
{
    return client_ && client_->get_state() != ::APClient::State::DISCONNECTED;
}

bool APArchipelagoClient::is_slot_connected() const
{
    return slot_connected_;
}

// =============================================================================
// Polling
// =============================================================================

void APArchipelagoClient::poll()
{
    if (client_)
    {
        client_->poll();
    }
}

// =============================================================================
// Outgoing Messages
// =============================================================================

void APArchipelagoClient::send_location_checks(const std::vector<int64_t> &location_ids)
{
    if (client_ && slot_connected_)
    {
        std::list<int64_t> ids_list;
        for (int64_t id : location_ids)
            ids_list.push_back(remap_location_to_ap(id));
        client_->LocationChecks(ids_list);
    }
}

void APArchipelagoClient::send_location_scouts(const std::vector<int64_t> &location_ids, bool create_as_hint)
{
    if (client_ && slot_connected_)
    {
        std::list<int64_t> ids_list(location_ids.begin(), location_ids.end());
        client_->LocationScouts(ids_list, create_as_hint ? 2 : 0);
    }
}

void APArchipelagoClient::send_status_update(ClientStatus status)
{
    if (client_ && slot_connected_)
    {
        client_->StatusUpdate(static_cast<::APClient::ClientStatus>(status));
    }
}

void APArchipelagoClient::send_say(const std::string &message)
{
    if (client_ && slot_connected_)
    {
        client_->Say(message);
    }
}

void APArchipelagoClient::send_bounce(const std::vector<std::string> &games, const std::vector<int> &slots,
                                      const std::vector<std::string> &tags, const nlohmann::json &data)
{
    if (client_ && slot_connected_)
    {
        std::list<std::string> games_list(games.begin(), games.end());
        std::list<int> slots_list(slots.begin(), slots.end());
        std::list<std::string> tags_list(tags.begin(), tags.end());
        client_->Bounce(data, games_list, slots_list, tags_list);
    }
}

// =============================================================================
// Data Access
// =============================================================================

std::optional<SlotInfo> APArchipelagoClient::get_slot_info() const
{
    return slot_info_;
}

std::string APArchipelagoClient::get_location_name(int64_t location_id) const
{
    if (client_)
    {
        std::string name = client_->get_location_name(location_id, game_);
        if (name == "Unknown")
        {
            // DP not yet valid — fall back to local capabilities registry
            auto cap_loc = APCapabilities::get()->get_location_by_id(location_id);
            if (cap_loc.has_value())
                return cap_loc->location_name;
            APLogger::get()->log(LogLevel::Warn, "APArchipelagoClient",
                                 "Location name lookup FAILED for ID " + std::to_string(location_id) +
                                     " (game='" + game_ + "', dp_valid=" +
                                     std::string(client_->is_data_package_valid() ? "true" : "false") + ")");
        }
        return name;
    }
    return "";
}

std::string APArchipelagoClient::get_item_name(int64_t item_id) const
{
    if (client_)
    {
        std::string name = client_->get_item_name(item_id, game_);
        if (name == "Unknown")
        {
            // DP not yet valid — fall back to local capabilities registry
            auto cap_item = APCapabilities::get()->get_item_by_id(item_id);
            if (cap_item.has_value())
                return cap_item->item_name;
            APLogger::get()->log(LogLevel::Warn, "APArchipelagoClient",
                                 "Item name lookup FAILED for ID " + std::to_string(item_id) +
                                     " (game='" + game_ + "', dp_valid=" +
                                     std::string(client_->is_data_package_valid() ? "true" : "false") + ")");
        }
        return name;
    }
    return "";
}

std::string APArchipelagoClient::get_player_name(int player_id) const
{
    if (client_)
    {
        return client_->get_player_alias(player_id);
    }
    return "";
}

int APArchipelagoClient::get_player_number() const
{
    if (client_)
    {
        return client_->get_player_number();
    }
    return -1;
}

int APArchipelagoClient::get_received_item_index() const
{
    return received_item_index_;
}

int64_t APArchipelagoClient::remap_location_to_ap(int64_t local_id) const
{
    auto it = id_remap_.find(local_id);
    return (it != id_remap_.end()) ? it->second : local_id;
}

int64_t APArchipelagoClient::remap_item_to_local(int64_t ap_id) const
{
    auto it = id_reverse_remap_.find(ap_id);
    return (it != id_reverse_remap_.end()) ? it->second : ap_id;
}

// =============================================================================
// Callback Setters
// =============================================================================

void APArchipelagoClient::set_room_info_callback(RoomInfoCallback callback)
{
    room_info_callback_ = std::move(callback);
}

void APArchipelagoClient::set_slot_connected_callback(SlotConnectedCallback callback)
{
    slot_connected_callback_ = std::move(callback);
}

void APArchipelagoClient::set_slot_refused_callback(SlotRefusedCallback callback)
{
    slot_refused_callback_ = std::move(callback);
}

void APArchipelagoClient::set_item_received_callback(ItemReceivedCallback callback)
{
    item_received_callback_ = std::move(callback);
}

void APArchipelagoClient::set_location_scouted_callback(LocationScoutedCallback callback)
{
    location_scouted_callback_ = std::move(callback);
}

void APArchipelagoClient::set_disconnected_callback(DisconnectedCallback callback)
{
    disconnected_callback_ = std::move(callback);
}

void APArchipelagoClient::set_print_callback(PrintCallback callback)
{
    print_callback_ = std::move(callback);
}

void APArchipelagoClient::set_print_json_callback(PrintJsonCallback callback)
{
    print_json_callback_ = std::move(callback);
}

void APArchipelagoClient::set_bounced_callback(BouncedCallback callback)
{
    bounced_callback_ = std::move(callback);
}

// =============================================================================
// Private Methods
// =============================================================================

void APArchipelagoClient::setup_callbacks()
{
    if (!client_)
        return;

    // Room info - fires when WebSocket connects
    client_->set_room_info_handler([this]() {
        APLogger::get()->log(LogLevel::Debug, "APArchipelagoClient", "Received room_info");

        RoomInfo info;
        // Note: apclientpp doesn't expose all room info fields directly
        // We'll populate what we can

        if (room_info_callback_)
            room_info_callback_(info);
    });

    // Slot connected
    client_->set_slot_connected_handler([this](const nlohmann::json &slot_data) {
        APLogger::get()->log(LogLevel::Info, "APArchipelagoClient", "Slot connected");

        SlotInfo info;
        info.slot_id = client_->get_player_number();
        info.slot_name = slot_name_;
        info.game = game_;

        // Extract checked locations
        if (slot_data.contains("checked_locations"))
        {
            for (const auto &loc : slot_data["checked_locations"])
            {
                info.checked_locations.push_back(loc.get<int64_t>());
            }
        }

        // Extract missing locations
        if (slot_data.contains("missing_locations"))
        {
            for (const auto &loc : slot_data["missing_locations"])
            {
                info.missing_locations.push_back(loc.get<int64_t>());
            }
        }

        // Extract option values (from fill_slot_data in Python apworld)
        if (slot_data.contains("option_values") && slot_data["option_values"].is_object())
        {
            for (const auto &[key, val] : slot_data["option_values"].items())
            {
                if (val.is_string())
                {
                    info.option_values[key] = val.get<std::string>();
                }
                else
                {
                    info.option_values[key] = val.dump();
                }
            }
            APLogger::get()->log(LogLevel::Debug, "APArchipelagoClient",
                                 "Extracted " + std::to_string(info.option_values.size()) + " option values from slot_data");
        }

        // Extract ID remapping tables (populated for player 2+ by the Python apworld)
        id_remap_.clear();
        id_reverse_remap_.clear();
        if (slot_data.contains("id_remapping") && slot_data["id_remapping"].is_object())
        {
            for (const auto &[k, v] : slot_data["id_remapping"].items())
            {
                try { id_remap_[std::stoll(k)] = v.get<int64_t>(); } catch (...) {}
            }
        }
        if (slot_data.contains("id_reverse_remap") && slot_data["id_reverse_remap"].is_object())
        {
            for (const auto &[k, v] : slot_data["id_reverse_remap"].items())
            {
                try { id_reverse_remap_[std::stoll(k)] = v.get<int64_t>(); } catch (...) {}
            }
        }
        if (!id_remap_.empty())
        {
            APLogger::get()->log(LogLevel::Info, "APArchipelagoClient",
                                 "ID remap loaded: " + std::to_string(id_remap_.size()) + " entries");
        }

        // Publish slot_info_ BEFORE setting slot_connected_ = true.
        // The atomic write acts as a release fence: any thread that reads
        // slot_connected_ = true is guaranteed to see the fully-populated slot_info_.
        slot_info_ = info;
        slot_connected_ = true;

        APLogger::get()->log(LogLevel::Info, "APArchipelagoClient",
                             "Data package valid at slot connect: " +
                                 std::string(client_->is_data_package_valid() ? "true" : "false") +
                                 ", game: " + game_);

        if (slot_connected_callback_)
        {
            slot_connected_callback_(info);
        }
    });

    // Slot refused
    client_->set_slot_refused_handler([this](const std::list<std::string> &errors) {
        APLogger::get()->log(LogLevel::Error, "APArchipelagoClient", "Slot connection refused");

        slot_connected_ = false;
        std::vector<std::string> error_vec(errors.begin(), errors.end());

        if (slot_refused_callback_)
        {
            slot_refused_callback_(error_vec);
        }
    });

    // Items received
    client_->set_items_received_handler([this](const std::list<::APClient::NetworkItem> &items) {
        for (const auto &item : items)
        {
            ReceivedItem received;
            received.item_id = item.item;
            received.location_id = item.location;
            received.player_id = item.player;
            received.item_name = get_item_name(item.item);
            received.player_name = get_player_name(item.player);
            received.index = received_item_index_++;

            APLogger::get()->log(LogLevel::Debug, "APArchipelagoClient",
                                 "Received item: " + received.item_name + " from " + received.player_name);

            if (item_received_callback_)
            {
                item_received_callback_(received);
            }
        }
    });

    // Location info (scout results)
    client_->set_location_info_handler([this](const std::list<::APClient::NetworkItem> &items) {
        std::vector<ScoutResult> results;
        for (const auto &item : items)
        {
            ScoutResult result;
            result.location_id = item.location;
            result.item_id = item.item;
            result.player_id = item.player;
            result.item_name = get_item_name(item.item);
            result.player_name = get_player_name(item.player);
            results.push_back(result);
        }

        if (location_scouted_callback_ && !results.empty())
        {
            location_scouted_callback_(results);
        }
    });

    // Socket disconnected
    client_->set_socket_disconnected_handler([this]() {
        APLogger::get()->log(LogLevel::Warn, "APArchipelagoClient", "Socket disconnected");
        slot_connected_ = false;

        if (disconnected_callback_)
        {
            disconnected_callback_();
        }
    });

    // Print messages
    client_->set_print_handler([this](const std::string &msg) {
        if (print_callback_)
        {
            print_callback_(msg);
        }
    });

    // Print JSON messages
    client_->set_print_json_handler([this](const std::list<::APClient::TextNode> &msg) {
        // Convert to JSON for callback
        nlohmann::json data = nlohmann::json::array();
        for (const auto &node : msg)
        {
            nlohmann::json obj;
            obj["type"] = node.type;
            obj["text"] = node.text;
            // Additional fields based on type could be added
            data.push_back(obj);
        }

        if (print_json_callback_)
        {
            print_json_callback_("print", data);
        }
    });

    // Bounced packets
    client_->set_bounced_handler([this](const nlohmann::json &data) {
        if (bounced_callback_)
        {
            bounced_callback_(data);
        }
    });

    // Data package changed - signals that item/location name resolution is ready
    // (Designed in Phase06 but was missing from implementation)
    client_->set_data_package_changed_handler([this](const nlohmann::json &data) {
        if (data.contains("games"))
        {
            for (auto &[game_name, game_data] : data["games"].items())
            {
                int item_count = game_data.contains("item_name_to_id")
                                     ? static_cast<int>(game_data["item_name_to_id"].size())
                                     : 0;
                int location_count = game_data.contains("location_name_to_id")
                                         ? static_cast<int>(game_data["location_name_to_id"].size())
                                         : 0;
                APLogger::get()->log(LogLevel::Debug, "APArchipelagoClient",
                                     "Data package for '" + game_name + "': " +
                                         std::to_string(item_count) + " items, " +
                                         std::to_string(location_count) + " locations");
            }
        }
        APLogger::get()->log(LogLevel::Info, "APArchipelagoClient",
                             "Data package updated (" +
                                 std::to_string(data.contains("games") ? data["games"].size() : 0) +
                                 " game(s)), valid=" +
                                 std::string(client_->is_data_package_valid() ? "true" : "false"));
    });
}

} // namespace ap
