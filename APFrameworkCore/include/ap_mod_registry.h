#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <filesystem>
#include <memory>
#include <nlohmann/json.hpp>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace ap
{

/**
 * @brief Singleton registry for discovered and registered mods.
 *
 * Handles:
 * - Manifest discovery from filesystem
 * - Manifest parsing and validation
 * - Registration tracking
 * - Priority client detection (mod_id starting with "archipelago.<game>.")
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APModRegistry
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APModRegistry;
        explicit ConstructorKey() = default;
    };

    explicit APModRegistry(ConstructorKey);
    ~APModRegistry();

    // Delete copy/move
    APModRegistry(const APModRegistry &) = delete;
    APModRegistry &operator=(const APModRegistry &) = delete;
    APModRegistry(APModRegistry &&) = delete;
    APModRegistry &operator=(APModRegistry &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APModRegistry singleton.
     */
    static APModRegistry *get();

    // ==========================================================================
    // Discovery
    // ==========================================================================

    /**
     * @brief Discover manifests from the mods folder.
     * @return Number of manifests discovered.
     *
     * Scans each subdirectory for manifest.json files.
     * Invalid manifests are skipped with warnings.
     */
    size_t discover_manifests();

    /**
     * @brief Add a manifest manually (for testing).
     * @param manifest Manifest to add.
     * @return true if added, false if mod_id already exists.
     */
    bool add_manifest(const Manifest &manifest);

    /**
     * @brief Clear all discovered manifests.
     */
    void clear();

    // ==========================================================================
    // Registration
    // ==========================================================================

    /**
     * @brief Mark a mod as registered.
     * @param mod_id Mod identifier.
     * @return true if mod was found and marked.
     */
    bool mark_registered(const std::string &mod_id);

    /**
     * @brief Check if a mod is registered.
     * @param mod_id Mod identifier.
     * @return true if registered.
     */
    bool is_registered(const std::string &mod_id) const;

    /**
     * @brief Check if all discovered mods are registered.
     * @return true if all mods have registered.
     */
    bool all_registered() const;

    /**
     * @brief Get list of mods pending registration.
     * @return Vector of mod IDs not yet registered.
     */
    std::vector<std::string> get_pending_registrations() const;

    /**
     * @brief Reset registration status of all mods.
     */
    void reset_registrations();

    // ==========================================================================
    // Queries
    // ==========================================================================

    /**
     * @brief Get all discovered manifests.
     * @return Vector of manifests.
     */
    std::vector<Manifest> get_discovered_manifests() const;

    /**
     * @brief Get all enabled manifests (enabled=true).
     * @return Vector of enabled manifests.
     */
    std::vector<Manifest> get_enabled_manifests() const;

    /**
     * @brief Get manifest by mod_id.
     * @param mod_id Mod identifier.
     * @return Manifest if found.
     */
    std::optional<Manifest> get_manifest(const std::string &mod_id) const;

    /**
     * @brief Get mod type (Priority or Regular).
     * @param mod_id Mod identifier.
     * @return ModType::Priority if mod_id matches pattern "archipelago.<game>.*"
     */
    ModType get_mod_type(const std::string &mod_id) const;

    /**
     * @brief Check if a mod is a priority client.
     * @param mod_id Mod identifier.
     * @return true if priority client.
     */
    bool is_priority_client(const std::string &mod_id) const;

    /**
     * @brief Get all priority client mod IDs.
     * @return Vector of priority client mod IDs.
     */
    std::vector<std::string> get_priority_clients() const;

    /**
     * @brief Get all regular (non-priority) mod IDs.
     * @return Vector of regular mod IDs.
     */
    std::vector<std::string> get_regular_mods() const;

    /**
     * @brief Get mod info for all mods.
     * @return Vector of ModInfo structures.
     */
    std::vector<ModInfo> get_mod_infos() const;

    /**
     * @brief Get number of discovered mods.
     * @return Count of discovered manifests.
     */
    size_t count() const;

    // ==========================================================================
    // Manifest Parsing
    // ==========================================================================

    /**
     * @brief Parse a manifest from JSON.
     * @param json_content JSON string content.
     * @return Parsed manifest, or std::nullopt on error.
     */
    std::optional<Manifest> parse_manifest(const std::string &json_content) const;

    /**
     * @brief Parse a manifest from a file.
     * @param file_path Path to manifest.json.
     * @return Parsed manifest, or std::nullopt on error.
     */
    std::optional<Manifest> parse_manifest_file(const std::filesystem::path &file_path) const;

  private:
    // =========================================================================
    // Private Helpers
    // =========================================================================

    /**
     * @brief Resolve include directives in capabilities JSON.
     *
     * Processes "include" arrays, loading external JSON files and merging
     * their regions/locations/items arrays into the capabilities object.
     * Search path: manifest directory first, then Templates/<game>/logic/.
     * Supports transitive includes with circular detection.
     */
    void resolve_includes(nlohmann::json &caps,
                          const std::filesystem::path &manifest_dir,
                          std::set<std::string> &visited) const;

    // =========================================================================
    // Private Member Variables
    // =========================================================================
    std::unordered_map<std::string, Manifest> manifests_;
    std::unordered_set<std::string> registered_;
};

} // namespace ap