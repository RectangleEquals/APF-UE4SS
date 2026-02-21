#pragma once

/**
 * @file ap_client_protocol_types.h
 * @brief Types used for Archipelago server protocol communication.
 *
 * These types represent data structures used when communicating
 * with the Archipelago server (receiving items, scouting locations, etc.)
 */

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace ap
{

/**
 * @brief Received item information from the AP server.
 */
struct ReceivedItem
{
    int64_t item_id = 0;
    int64_t location_id = 0;
    int player_id = 0;
    std::string item_name;
    std::string player_name;
    int index = 0; ///< Position in items list
};

/**
 * @brief Location scout result from the AP server.
 */
struct ScoutResult
{
    int64_t location_id = 0;
    int64_t item_id = 0;
    int player_id = 0;
    std::string item_name;
    std::string player_name;
};

/**
 * @brief Room information from AP server.
 *
 * Received after WebSocket connection is established.
 */
struct RoomInfo
{
    std::string version;
    std::vector<std::string> tags;
    std::string seed_name;
    bool password_required = false;
};

/**
 * @brief Slot connection result from AP server.
 *
 * Received after successful slot authentication.
 */
struct SlotInfo
{
    int slot_id = 0;
    std::string slot_name;
    std::string game;
    std::vector<int64_t> checked_locations;
    std::vector<int64_t> missing_locations;
    std::map<std::string, std::string> option_values;
};

} // namespace ap