#pragma once

/**
 * @file ap_shared_manifest_types.h
 * @brief Manifest structures shared by both libraries.
 *
 * APFrameworkCore needs: Full manifest for discovery, validation, mod registration
 * APClientLib needs: Only subset for self-identification (mod_id, version, enabled, actions)
 *
 * The full Manifest type is defined here so both can parse manifest.json,
 * but APClientLib only uses the fields it needs.
 */

#include "ap_shared_enums.h"
#include "ap_version.h"

#include <nlohmann/json.hpp>
#include <string>
#include <vector>

namespace ap {

// =============================================================================
// Action Argument (used in item definitions)
// =============================================================================

struct ActionArg {
    std::string name;
    ArgType type = ArgType::String;
    nlohmann::json value;
};

// =============================================================================
// Action Result (shared between framework and client)
// =============================================================================

/**
 * @brief Result of executing an item action.
 *
 * Used by client to report action execution results,
 * and by framework to track and route those results.
 */
struct ActionResult {
    std::string mod_id;         ///< ID of the mod that executed the action
    int64_t item_id = 0;        ///< Item that triggered the action
    std::string item_name;      ///< Name of the item
    bool success = false;       ///< Whether the action succeeded
    std::string error;          ///< Error message if failed
};

// =============================================================================
// Region Definition (capabilities)
// =============================================================================

struct RegionDef {
    std::string name;
    std::string logic;                       // Logic expression string
    std::string requires_option;             // Option conditional
};

// =============================================================================
// Location Definition (capabilities)
// =============================================================================

struct LocationDef {
    std::string name;
    int amount = 1;
    std::string region;                      // Region this location belongs to
    std::string logic;                       // Logic expression string
    std::string requires_option;             // Option conditional
};

// =============================================================================
// Item Definition (capabilities)
// =============================================================================

struct ItemDef {
    std::string name;
    ItemType type = ItemType::Filler;
    int amount = 1;
    std::string action;
    std::vector<ActionArg> args;
    std::string requires_option;             // Option conditional
};

// =============================================================================
// Manifest Option Definition (declared by mods in their manifests)
// =============================================================================

struct ManifestOptionDef {
    std::string key;
    std::string type;                        // "toggle", "range", "text_choice"
    std::string default_value;               // Stored as string for uniformity
    int range_start = 0;                     // For "range" type
    int range_end = 100;                     // For "range" type
    std::vector<std::string> choices;        // For "text_choice" type (required)
    std::string description;
};

// =============================================================================
// Goal Definition (declared by mods — aggregated across all mods)
// =============================================================================

struct GoalDef {
    std::string name;                        // Unique identifier (e.g., "all_bosses")
    std::string display;                     // Display name (e.g., "Defeat All Tower Bosses")
    std::string description;                 // Description shown to player
    std::string logic;                       // Logic expression for completion condition
};

// =============================================================================
// Item Override Definition (Mod B conditionally changes Mod A's item type)
// =============================================================================

struct ItemOverrideDef {
    std::string target_item;                 // Item name to override
    std::string target_mod;                  // Mod that owns the target item
    std::string type;                        // New item type (e.g., "filler", "progression")
    std::string requires_option;             // Only apply when this option condition is met
};

// NOTE: IncompatibilityRule removed — both `depends` and `incompatible` now use
// the unified Dependency struct from ap_version.h which supports semver constraints.

// =============================================================================
// Manifest (full structure)
// =============================================================================

/**
 * @brief Full manifest structure from manifest.json.
 *
 * APFrameworkCore uses all fields for discovery, validation, and registration.
 * APClientLib only uses: mod_id, name, version, enabled, and item action names.
 */
struct Manifest {
    std::string mod_id;
    std::string name;
    std::string version;
    bool enabled = true;
    std::string description;
    bool vocab_validation = false;           // Opt-in vocabulary validation
    std::vector<Dependency> depends;             // Mod dependencies with optional semver constraints
    std::vector<Dependency> incompatible;        // Incompatible mods with optional semver constraints
    std::vector<RegionDef> regions;
    std::vector<LocationDef> locations;
    std::vector<ItemDef> items;
    std::vector<ManifestOptionDef> options;
    std::vector<GoalDef> goals;              // Completion goals declared by this mod
    std::vector<ItemOverrideDef> item_overrides; // Cross-mod item type overrides
};

} // namespace ap