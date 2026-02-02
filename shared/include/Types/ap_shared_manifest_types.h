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
// Location Definition (capabilities)
// =============================================================================

struct LocationDef {
    std::string name;
    int amount = 1;
    bool unique = false;
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
};

// =============================================================================
// Incompatibility Rule
// =============================================================================

struct IncompatibilityRule {
    std::string id;
    std::vector<std::string> versions;
};

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
    std::vector<IncompatibilityRule> incompatible;
    std::vector<LocationDef> locations;
    std::vector<ItemDef> items;
};

} // namespace ap