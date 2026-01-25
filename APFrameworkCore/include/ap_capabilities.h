#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <memory>
#include <cstdint>

namespace ap {

/**
 * @brief Manages the capabilities system for all registered mods.
 *
 * Handles:
 * - Aggregating capabilities from all manifests
 * - Conflict detection between mods
 * - ID assignment (locations first, then items)
 * - Checksum generation
 * - Capabilities config file generation
 */
class AP_API APCapabilities {
public:
    APCapabilities();
    ~APCapabilities();

    // Delete copy/move
    APCapabilities(const APCapabilities&) = delete;
    APCapabilities& operator=(const APCapabilities&) = delete;
    APCapabilities(APCapabilities&&) = delete;
    APCapabilities& operator=(APCapabilities&&) = delete;

    // ==========================================================================
    // Registration
    // ==========================================================================

    /**
     * @brief Add a manifest's capabilities.
     * @param manifest Manifest to add.
     *
     * Should be called during DISCOVERY phase for each discovered manifest.
     */
    void add_manifest(const Manifest& manifest);

    /**
     * @brief Clear all registered capabilities.
     */
    void clear();

    // ==========================================================================
    // Validation
    // ==========================================================================

    /**
     * @brief Validate all capabilities for conflicts.
     * @return Validation result with any conflicts and warnings.
     */
    ValidationResult validate() const;

    /**
     * @brief Get list of detected conflicts.
     * @return Vector of conflicts.
     */
    std::vector<Conflict> get_conflicts() const;

    /**
     * @brief Check if there are any conflicts.
     * @return true if conflicts exist.
     */
    bool has_conflicts() const;

    // ==========================================================================
    // ID Assignment
    // ==========================================================================

    /**
     * @brief Assign IDs to all locations and items.
     * @param base_id Base ID for assignment (default: 6942067).
     *
     * IDs are assigned in order: locations first, then items.
     * Multi-instance locations/items get sequential IDs.
     */
    void assign_ids(int64_t base_id = 6942067);

    /**
     * @brief Get location ID by mod and name.
     * @param mod_id Mod identifier.
     * @param location_name Location name.
     * @param instance Instance number (1-based, for multi-instance locations).
     * @return Location ID, or 0 if not found.
     */
    int64_t get_location_id(const std::string& mod_id,
                            const std::string& location_name,
                            int instance = 1) const;

    /**
     * @brief Get item ID by mod and name.
     * @param mod_id Mod identifier.
     * @param item_name Item name.
     * @return Item ID, or 0 if not found.
     */
    int64_t get_item_id(const std::string& mod_id,
                        const std::string& item_name) const;

    /**
     * @brief Get location ownership info by ID.
     * @param location_id Location ID.
     * @return LocationOwnership if found.
     */
    std::optional<LocationOwnership> get_location_by_id(int64_t location_id) const;

    /**
     * @brief Get item ownership info by ID.
     * @param item_id Item ID.
     * @return ItemOwnership if found.
     */
    std::optional<ItemOwnership> get_item_by_id(int64_t item_id) const;

    // ==========================================================================
    // Checksum
    // ==========================================================================

    /**
     * @brief Compute checksum for the current capabilities.
     * @param game_name Game name.
     * @param slot_name Slot name.
     * @return SHA-1 checksum string.
     *
     * Algorithm: SHA-1(sorted_mod_ids + versions + capabilities_hash + game + slot)
     */
    std::string compute_checksum(const std::string& game_name,
                                 const std::string& slot_name) const;

    // ==========================================================================
    // Config Generation
    // ==========================================================================

    /**
     * @brief Generate capabilities config JSON.
     * @param slot_name Slot name for the config.
     * @param game_name Game name.
     * @return CapabilitiesConfig structure.
     */
    CapabilitiesConfig generate_capabilities_config(const std::string& slot_name,
                                                    const std::string& game_name) const;

    /**
     * @brief Write capabilities config to file.
     * @param output_path Path to output file.
     * @param slot_name Slot name.
     * @param game_name Game name.
     * @return true if written successfully.
     *
     * Creates parent directories if needed.
     * Filename: AP_Capabilities_<slot_name>.json
     */
    bool write_capabilities_config(const std::filesystem::path& output_path,
                                   const std::string& slot_name,
                                   const std::string& game_name) const;

    /**
     * @brief Write capabilities config to default output folder.
     * @param slot_name Slot name.
     * @param game_name Game name.
     * @return Path to written file, or empty path on failure.
     *
     * Output: <framework_mod>/output/AP_Capabilities_<slot_name>.json
     */
    std::filesystem::path write_capabilities_config_default(const std::string& slot_name,
                                                            const std::string& game_name) const;

    // ==========================================================================
    // Queries
    // ==========================================================================

    /**
     * @brief Get all location ownerships.
     * @return Vector of location ownership records.
     */
    std::vector<LocationOwnership> get_all_locations() const;

    /**
     * @brief Get all item ownerships.
     * @return Vector of item ownership records.
     */
    std::vector<ItemOwnership> get_all_items() const;

    /**
     * @brief Get locations for a specific mod.
     * @param mod_id Mod identifier.
     * @return Vector of location ownerships for that mod.
     */
    std::vector<LocationOwnership> get_locations_for_mod(const std::string& mod_id) const;

    /**
     * @brief Get items for a specific mod.
     * @param mod_id Mod identifier.
     * @return Vector of item ownerships for that mod.
     */
    std::vector<ItemOwnership> get_items_for_mod(const std::string& mod_id) const;

    /**
     * @brief Get total number of locations.
     * @return Location count.
     */
    size_t get_location_count() const;

    /**
     * @brief Get total number of items.
     * @return Item count.
     */
    size_t get_item_count() const;

    /**
     * @brief Get the base ID used for assignment.
     * @return Base ID.
     */
    int64_t get_base_id() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
