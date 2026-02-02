#pragma once

/**
 * @file ap_manifest.h
 * @brief Manifest loader and accessor for mod manifests.
 *
 * NOT a singleton - APFrameworkCore loads multiple manifests during discovery,
 * while APClientLib only loads its own manifest.
 *
 * Usage:
 * - Framework: APManifest m; m.load(mod_folder_path);
 * - Client: APManifest m; m.load_current();  // Uses APPathUtil to find own folder
 *
 * The manifest is loaded from manifest.json in the mod folder:
 * {
 *     "mod_id": "my_mod",
 *     "name": "My Mod",
 *     "version": "1.0.0",
 *     "enabled": true,
 *     "description": "...",
 *     "incompatible": [...],
 *     "locations": [...],
 *     "items": [...]
 * }
 */

#include "Types/ap_shared_manifest_types.h"

#include <filesystem>
#include <string>
#include <vector>

namespace ap {

class APManifest {
public:
    /**
     * @brief Default constructor - creates an unloaded manifest.
     *
     * Call load() or load_current() after construction.
     */
    APManifest() = default;
    ~APManifest() = default;

    // Allow copy and move
    APManifest(const APManifest&) = default;
    APManifest& operator=(const APManifest&) = default;
    APManifest(APManifest&&) = default;
    APManifest& operator=(APManifest&&) = default;

    // =========================================================================
    // Loading
    // =========================================================================

    /**
     * @brief Load manifest from a specific mod folder.
     * @param mod_folder Path to the mod folder containing manifest.json.
     * @return true if loading succeeded, false otherwise.
     *
     * Use this when you know the mod folder path (e.g., during discovery).
     */
    bool load(const std::filesystem::path& mod_folder);

    /**
     * @brief Load manifest for the current mod using path discovery.
     * @return true if loading succeeded, false otherwise.
     *
     * Uses APPathUtil::get()->find_current_mod_folder() to discover the path.
     * Intended for use by APClientLib to find its own manifest.
     */
    bool load_current();

    /**
     * @brief Check if the manifest is loaded.
     * @return true if loaded, false otherwise.
     */
    bool is_loaded() const { return loaded_; }

    /**
     * @brief Check if the manifest indicates the mod is enabled.
     * @return true if enabled (or if enabled field is missing), false otherwise.
     */
    bool is_enabled() const { return manifest_.enabled; }

    // =========================================================================
    // Path Accessors
    // =========================================================================

    /**
     * @brief Get the mod folder path.
     * @return Path to the mod folder, or empty if not loaded.
     */
    const std::filesystem::path& get_mod_folder() const { return mod_folder_; }

    /**
     * @brief Get the manifest file path.
     * @return Path to manifest.json, or empty if not loaded.
     */
    std::filesystem::path get_manifest_path() const;

    // =========================================================================
    // Manifest Accessors
    // =========================================================================

    /**
     * @brief Get the mod ID.
     * @return Mod ID string, or empty if not loaded.
     */
    const std::string& get_mod_id() const { return manifest_.mod_id; }

    /**
     * @brief Get the mod name.
     * @return Mod name string, or empty if not loaded.
     */
    const std::string& get_name() const { return manifest_.name; }

    /**
     * @brief Get the mod version.
     * @return Version string, or empty if not loaded.
     */
    const std::string& get_version() const { return manifest_.version; }

    /**
     * @brief Get the mod description.
     * @return Description string, or empty if not loaded.
     */
    const std::string& get_description() const { return manifest_.description; }

    /**
     * @brief Get the full manifest structure.
     * @return Reference to the Manifest struct.
     */
    const Manifest& get_manifest() const { return manifest_; }

    /**
     * @brief Get location definitions.
     * @return Vector of LocationDef.
     */
    const std::vector<LocationDef>& get_locations() const { return manifest_.locations; }

    /**
     * @brief Get item definitions.
     * @return Vector of ItemDef.
     */
    const std::vector<ItemDef>& get_items() const { return manifest_.items; }

    /**
     * @brief Get incompatibility rules.
     * @return Vector of IncompatibilityRule.
     */
    const std::vector<IncompatibilityRule>& get_incompatible() const { return manifest_.incompatible; }

    /**
     * @brief Get action names defined by this mod's items.
     * @return Vector of unique action names.
     */
    std::vector<std::string> get_action_names() const;

private:
    bool loaded_ = false;
    std::filesystem::path mod_folder_;
    Manifest manifest_;
};

} // namespace ap