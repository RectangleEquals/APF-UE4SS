#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <string>
#include <memory>
#include <functional>
#include <vector>
#include <optional>
#include <cstdint>

namespace ap {

/**
 * @brief Received item information.
 */
struct ReceivedItem {
    int64_t item_id = 0;
    int64_t location_id = 0;
    int player_id = 0;
    std::string item_name;
    std::string player_name;
    int index = 0;  // Position in items list
};

/**
 * @brief Location scout result.
 */
struct ScoutResult {
    int64_t location_id = 0;
    int64_t item_id = 0;
    int player_id = 0;
    std::string item_name;
    std::string player_name;
};

/**
 * @brief Room information from AP server.
 */
struct RoomInfo {
    std::string version;
    std::vector<std::string> tags;
    std::string seed_name;
    bool password_required = false;
};

/**
 * @brief Slot connection result.
 */
struct SlotInfo {
    int slot_id = 0;
    std::string slot_name;
    std::string game;
    std::vector<int64_t> checked_locations;
    std::vector<int64_t> missing_locations;
};

/**
 * @brief Wrapper around apclientpp for AP server communication.
 *
 * Uses PIMPL pattern to hide apclientpp implementation details.
 *
 * CRITICAL FLOW:
 * 1. Create APClient and call connect()
 * 2. Set ALL handlers BEFORE any polling
 * 3. Call poll() repeatedly - room_info_callback fires when server responds
 * 4. In room_info_callback, call connect_slot() with credentials
 * 5. slot_connected_callback or slot_refused_callback fires
 * 6. Continue polling to receive items/messages
 */
class AP_API APClient {
public:
    // Callback types
    using RoomInfoCallback = std::function<void(const RoomInfo&)>;
    using SlotConnectedCallback = std::function<void(const SlotInfo&)>;
    using SlotRefusedCallback = std::function<void(const std::vector<std::string>&)>;
    using ItemReceivedCallback = std::function<void(const ReceivedItem&)>;
    using LocationScoutedCallback = std::function<void(const std::vector<ScoutResult>&)>;
    using DisconnectedCallback = std::function<void()>;
    using PrintCallback = std::function<void(const std::string&)>;
    using PrintJsonCallback = std::function<void(const std::string& type, const nlohmann::json& data)>;
    using BouncedCallback = std::function<void(const nlohmann::json& data)>;

    APClient();
    ~APClient();

    // Delete copy/move
    APClient(const APClient&) = delete;
    APClient& operator=(const APClient&) = delete;
    APClient(APClient&&) = delete;
    APClient& operator=(APClient&&) = delete;

    // ==========================================================================
    // Connection
    // ==========================================================================

    /**
     * @brief Connect to an AP server (WebSocket connection only).
     * @param server Server hostname.
     * @param port Server port.
     * @param game Game name.
     * @param uuid Unique identifier for this client.
     * @return true if connection initiated.
     *
     * NOTE: This only establishes the WebSocket connection.
     * After room_info is received, call connect_slot() to authenticate.
     */
    bool connect(const std::string& server, int port,
                 const std::string& game, const std::string& uuid);

    /**
     * @brief Connect to a slot after room_info is received.
     * @param slot_name Player slot name.
     * @param password Server password (empty if none).
     * @param items_handling Bitmask for item handling (0x7 = all).
     * @return true if slot connection request sent.
     */
    bool connect_slot(const std::string& slot_name,
                      const std::string& password = "",
                      int items_handling = 0x7);

    /**
     * @brief Disconnect from the server.
     */
    void disconnect();

    /**
     * @brief Check if WebSocket is connected.
     * @return true if WebSocket connection is active.
     */
    bool is_connected() const;

    /**
     * @brief Check if slot is connected (authenticated).
     * @return true if authenticated with a slot.
     */
    bool is_slot_connected() const;

    // ==========================================================================
    // Polling
    // ==========================================================================

    /**
     * @brief Poll for messages from the server.
     *
     * MUST be called regularly (e.g., every frame) to process incoming messages.
     * Callbacks are invoked from within this function.
     */
    void poll();

    // ==========================================================================
    // Outgoing Messages
    // ==========================================================================

    /**
     * @brief Send location check(s) to the server.
     * @param location_ids Vector of location IDs to mark as checked.
     */
    void send_location_checks(const std::vector<int64_t>& location_ids);

    /**
     * @brief Scout location(s) to see what items they contain.
     * @param location_ids Vector of location IDs to scout.
     * @param create_as_hint If true, creates hints for scouted items.
     */
    void send_location_scouts(const std::vector<int64_t>& location_ids,
                              bool create_as_hint = false);

    /**
     * @brief Update client status.
     * @param status New client status.
     */
    void send_status_update(ClientStatus status);

    /**
     * @brief Say something in chat.
     * @param message Message to send.
     */
    void send_say(const std::string& message);

    /**
     * @brief Send a bounce packet.
     * @param games Target games (empty for all).
     * @param slots Target slots (empty for all).
     * @param tags Target tags (empty for all).
     * @param data Custom data to include.
     */
    void send_bounce(const std::vector<std::string>& games,
                     const std::vector<int>& slots,
                     const std::vector<std::string>& tags,
                     const nlohmann::json& data);

    // ==========================================================================
    // Data Access
    // ==========================================================================

    /**
     * @brief Get the current slot info.
     * @return SlotInfo if connected to a slot.
     */
    std::optional<SlotInfo> get_slot_info() const;

    /**
     * @brief Get location name from ID.
     * @param location_id Location ID.
     * @return Location name, or empty string if not found.
     */
    std::string get_location_name(int64_t location_id) const;

    /**
     * @brief Get item name from ID.
     * @param item_id Item ID.
     * @return Item name, or empty string if not found.
     */
    std::string get_item_name(int64_t item_id) const;

    /**
     * @brief Get player name from ID.
     * @param player_id Player ID.
     * @return Player name, or empty string if not found.
     */
    std::string get_player_name(int player_id) const;

    /**
     * @brief Get the current player's slot number.
     * @return Slot number, or -1 if not connected.
     */
    int get_player_number() const;

    /**
     * @brief Get the index of the last received item.
     * @return Item index, or -1 if none received.
     */
    int get_received_item_index() const;

    // ==========================================================================
    // Callbacks
    // ==========================================================================

    /**
     * @brief Set callback for room info (received after WebSocket connects).
     *
     * IMPORTANT: In this callback, call connect_slot() to authenticate.
     */
    void set_room_info_callback(RoomInfoCallback callback);

    /**
     * @brief Set callback for successful slot connection.
     */
    void set_slot_connected_callback(SlotConnectedCallback callback);

    /**
     * @brief Set callback for refused slot connection.
     */
    void set_slot_refused_callback(SlotRefusedCallback callback);

    /**
     * @brief Set callback for received items.
     */
    void set_item_received_callback(ItemReceivedCallback callback);

    /**
     * @brief Set callback for scouted locations.
     */
    void set_location_scouted_callback(LocationScoutedCallback callback);

    /**
     * @brief Set callback for disconnection.
     */
    void set_disconnected_callback(DisconnectedCallback callback);

    /**
     * @brief Set callback for print messages.
     */
    void set_print_callback(PrintCallback callback);

    /**
     * @brief Set callback for print_json messages.
     */
    void set_print_json_callback(PrintJsonCallback callback);

    /**
     * @brief Set callback for bounced packets.
     */
    void set_bounced_callback(BouncedCallback callback);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
