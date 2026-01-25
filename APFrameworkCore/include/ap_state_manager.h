#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <string>
#include <set>
#include <map>
#include <filesystem>
#include <memory>
#include <optional>
#include <cstdint>

namespace ap {

/**
 * @brief Manages session state persistence and checksum validation.
 *
 * Handles:
 * - Saving/loading session state to JSON file
 * - Tracking received item progress
 * - Tracking checked locations
 * - Checksum validation during SYNCING
 * - Item progression counts for stackable items
 */
class AP_API APStateManager {
public:
    APStateManager();
    ~APStateManager();

    // Delete copy/move
    APStateManager(const APStateManager&) = delete;
    APStateManager& operator=(const APStateManager&) = delete;
    APStateManager(APStateManager&&) = delete;
    APStateManager& operator=(APStateManager&&) = delete;

    // ==========================================================================
    // Persistence
    // ==========================================================================

    /**
     * @brief Save session state to a file.
     * @param path Path to save file.
     * @return true if saved successfully.
     */
    bool save_state(const std::filesystem::path& path);

    /**
     * @brief Save session state to default path.
     * @return true if saved successfully.
     *
     * Path: <framework_mod>/session_state.json
     */
    bool save_state();

    /**
     * @brief Load session state from a file.
     * @param path Path to load file.
     * @return true if loaded successfully.
     */
    bool load_state(const std::filesystem::path& path);

    /**
     * @brief Load session state from default path.
     * @return true if loaded successfully.
     */
    bool load_state();

    /**
     * @brief Clear all state data.
     */
    void clear();

    /**
     * @brief Check if state has been loaded.
     * @return true if state is loaded.
     */
    bool is_loaded() const;

    // ==========================================================================
    // Item Progress Tracking
    // ==========================================================================

    /**
     * @brief Set the received item index.
     * @param index New index value.
     */
    void set_received_item_index(int index);

    /**
     * @brief Get the received item index.
     * @return Current index.
     */
    int get_received_item_index() const;

    /**
     * @brief Increment the received item index.
     * @return New index value.
     */
    int increment_received_item_index();

    // ==========================================================================
    // Location Tracking
    // ==========================================================================

    /**
     * @brief Add a checked location.
     * @param location_id Location ID.
     */
    void add_checked_location(int64_t location_id);

    /**
     * @brief Check if a location has been checked.
     * @param location_id Location ID.
     * @return true if location was checked.
     */
    bool is_location_checked(int64_t location_id) const;

    /**
     * @brief Get all checked location IDs.
     * @return Set of location IDs.
     */
    std::set<int64_t> get_checked_locations() const;

    /**
     * @brief Get number of checked locations.
     * @return Count of checked locations.
     */
    size_t get_checked_location_count() const;

    /**
     * @brief Set checked locations (for loading from server).
     * @param locations Set of location IDs.
     */
    void set_checked_locations(const std::set<int64_t>& locations);

    // ==========================================================================
    // Item Progression Counts
    // ==========================================================================

    /**
     * @brief Set the progression count for an item.
     * @param item_id Item ID.
     * @param count New count.
     */
    void set_item_progression_count(int64_t item_id, int count);

    /**
     * @brief Get the progression count for an item.
     * @param item_id Item ID.
     * @return Current count (0 if not tracked).
     */
    int get_item_progression_count(int64_t item_id) const;

    /**
     * @brief Increment the progression count for an item.
     * @param item_id Item ID.
     * @return New count.
     */
    int increment_item_progression_count(int64_t item_id);

    /**
     * @brief Get all item progression counts.
     * @return Map of item ID to count.
     */
    std::map<int64_t, int> get_all_item_progression_counts() const;

    // ==========================================================================
    // Checksum Validation
    // ==========================================================================

    /**
     * @brief Set the stored checksum.
     * @param checksum Checksum string.
     */
    void set_checksum(const std::string& checksum);

    /**
     * @brief Get the stored checksum.
     * @return Checksum string.
     */
    std::string get_checksum() const;

    /**
     * @brief Validate against a current checksum.
     * @param current_checksum Checksum to compare.
     * @return true if checksums match.
     *
     * Used during SYNCING to verify mod ecosystem hasn't changed.
     */
    bool validate_checksum(const std::string& current_checksum) const;

    // ==========================================================================
    // Session Info
    // ==========================================================================

    /**
     * @brief Set slot name.
     * @param slot_name Slot name.
     */
    void set_slot_name(const std::string& slot_name);

    /**
     * @brief Get slot name.
     * @return Slot name.
     */
    std::string get_slot_name() const;

    /**
     * @brief Set game name.
     * @param game_name Game name.
     */
    void set_game_name(const std::string& game_name);

    /**
     * @brief Get game name.
     * @return Game name.
     */
    std::string get_game_name() const;

    /**
     * @brief Set AP server info.
     * @param server Server hostname.
     * @param port Server port.
     */
    void set_server_info(const std::string& server, int port);

    /**
     * @brief Get AP server hostname.
     * @return Server hostname.
     */
    std::string get_server() const;

    /**
     * @brief Get AP server port.
     * @return Server port.
     */
    int get_port() const;

    /**
     * @brief Update last active timestamp to now.
     */
    void touch();

    /**
     * @brief Get the full session state.
     * @return SessionState structure.
     */
    SessionState get_state() const;

    /**
     * @brief Set the full session state.
     * @param state SessionState structure.
     */
    void set_state(const SessionState& state);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
