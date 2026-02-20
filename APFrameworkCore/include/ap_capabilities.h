#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace ap
{

/**
 * @brief Singleton managing the capabilities system for all registered mods.
 *
 * Handles:
 * - Aggregating capabilities from manifests (owned by APModRegistry)
 * - Conflict detection between mods
 * - ID assignment (locations first, then items)
 * - Checksum generation
 * - Capabilities config file generation
 *
 * Data Ownership:
 * - Locations/Items with assigned IDs: Owned (computed from manifests)
 * - Manifests: NOT owned - accessed from APModRegistry::get()
 * - Base ID: NOT owned - accessed from APConfig::get()
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APCapabilities
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APCapabilities;
        explicit ConstructorKey() = default;
    };

    explicit APCapabilities(ConstructorKey);
    ~APCapabilities();

    // Delete copy/move
    APCapabilities(const APCapabilities &) = delete;
    APCapabilities &operator=(const APCapabilities &) = delete;
    APCapabilities(APCapabilities &&) = delete;
    APCapabilities &operator=(APCapabilities &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APCapabilities singleton.
     */
    static APCapabilities *get();

    // ==========================================================================
    // Registration
    // ==========================================================================

    /**
     * @brief Add a manifest's capabilities (extracts locations/items).
     * @param manifest Manifest to extract capabilities from.
     *
     * Should be called during DISCOVERY phase for each discovered manifest.
     * The manifest itself is NOT stored - only the location/item data.
     */
    void add_manifest(const Manifest &manifest);

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
     *
     * Accesses manifests from APModRegistry for incompatibility checking.
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
     *
     * Uses base_id from APConfig::get()->get_id_base().
     * IDs are assigned in order: locations first, then items.
     * Multi-instance locations/items get sequential IDs.
     */
    void assign_ids();

    /**
     * @brief Get location ID by mod and name.
     * @param mod_id Mod identifier.
     * @param location_name Location name.
     * @param instance Instance number (1-based, for multi-instance locations).
     * @return Location ID, or 0 if not found.
     */
    int64_t get_location_id(const std::string &mod_id, const std::string &location_name, int instance = 1) const;

    /**
     * @brief Get item ID by mod and name.
     * @param mod_id Mod identifier.
     * @param item_name Item name.
     * @return Item ID, or 0 if not found.
     */
    int64_t get_item_id(const std::string &mod_id, const std::string &item_name) const;

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
     * @return SHA-1 checksum string.
     *
     * Uses game_name and slot_name from APConfig.
     * Accesses manifests from APModRegistry for version info.
     */
    std::string compute_checksum() const;

    // ==========================================================================
    // Config Generation
    // ==========================================================================

    /**
     * @brief Generate capabilities config JSON.
     * @return CapabilitiesConfig structure.
     *
     * Uses game_name and slot_name from APConfig.
     */
    CapabilitiesConfig generate_capabilities_config() const;

    /**
     * @brief Write capabilities config to file.
     * @param output_path Path to output file.
     * @return true if written successfully.
     *
     * Creates parent directories if needed.
     */
    bool write_capabilities_config(const std::filesystem::path &output_path) const;

    /**
     * @brief Write capabilities config to default output folder.
     * @return Path to written file, or empty path on failure.
     *
     * Output: <framework_mod>/output/AP_Capabilities_<slot_name>.json
     */
    std::filesystem::path write_capabilities_config_default() const;

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
    std::vector<LocationOwnership> get_locations_for_mod(const std::string &mod_id) const;

    /**
     * @brief Get items for a specific mod.
     * @param mod_id Mod identifier.
     * @return Vector of item ownerships for that mod.
     */
    std::vector<ItemOwnership> get_items_for_mod(const std::string &mod_id) const;

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
     * @brief Get merged regions from all manifests.
     * @return Vector of region definitions.
     */
    std::vector<RegionDef> get_regions() const;

    /**
     * @brief Get collected option definitions from all manifests.
     * @return Vector of manifest option definitions.
     */
    std::vector<ManifestOptionDef> get_mod_options() const;

  private:
    // =========================================================================
    // Private Member Variables (only data this class OWNS)
    // =========================================================================
    std::vector<LocationOwnership> locations_;
    std::vector<ItemOwnership> items_;
    std::vector<RegionDef> regions_;                    // Merged regions from all manifests
    std::vector<ManifestOptionDef> mod_options_;        // Collected options from all manifests
};

} // namespace ap