#pragma once

/**
 * @file ap_generated_config.h
 * @brief Generated YAML configuration manager for the AP Framework.
 *
 * Handles:
 * - Loading option definitions from template files (data-driven defaults)
 * - Generating Archipelago YAML files with base64-encoded capabilities data
 * - Reading/modifying YAML files (for priority clients)
 * - Storing slot_data received from the AP server (for regular clients)
 *
 * Singleton Pattern: Pass-Key + Meyers
 *
 * Template resolution order:
 *   1. Templates/<game_name>_options.json (game-specific overrides)
 *   2. Templates/default_options.json (universal defaults)
 *   3. Merge: game-specific entries override/extend defaults
 */

#include "Types/ap_shared_manifest_types.h"

#include <filesystem>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace ap
{

// =============================================================================
// Option metadata loaded from template files
// =============================================================================

struct OptionDefinition
{
    std::string key;
    std::string type;                        // "toggle", "range", "text_choice"
    std::string default_value;               // stored as string for uniformity
    int range_start = 0;                     // for "range" type
    int range_end = 100;                     // for "range" type
    std::vector<std::string> choices;        // for "text_choice" type (required)
    std::string description;
};

// =============================================================================
// APGeneratedConfig Singleton
// =============================================================================

class APGeneratedConfig
{
  public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APGeneratedConfig;
        explicit ConstructorKey() = default;
    };

    explicit APGeneratedConfig(ConstructorKey);
    ~APGeneratedConfig();

    APGeneratedConfig(const APGeneratedConfig &) = delete;
    APGeneratedConfig &operator=(const APGeneratedConfig &) = delete;
    APGeneratedConfig(APGeneratedConfig &&) = delete;
    APGeneratedConfig &operator=(APGeneratedConfig &&) = delete;

    static APGeneratedConfig *get();

    // =========================================================================
    // Template Loading
    // =========================================================================

    /**
     * @brief Load option definitions from template file(s).
     *
     * Searches for Templates/<game_name>_options.json first (game-specific),
     * then falls back to Templates/default_options.json (universal defaults).
     * Game-specific entries override/extend defaults.
     */
    bool load_templates(const std::filesystem::path &templates_dir, const std::string &game_name);

    /**
     * @brief Get loaded option definitions.
     *
     * Useful for UI mods to discover available options and their constraints.
     */
    std::vector<OptionDefinition> get_option_definitions() const;

    /**
     * @brief Merge option definitions declared by mods into the config.
     *
     * Called after load_templates(). Mod-declared options have highest priority:
     * default_options.json < game_options.json < manifest options.
     */
    void merge_mod_options(const std::vector<ManifestOptionDef> &mod_options);

    // =========================================================================
    // YAML Generation
    // =========================================================================

    /**
     * @brief Generate a complete Archipelago YAML from a capabilities JSON file.
     *
     * Reads the JSON, base64-encodes it, and writes a YAML with default options
     * from the loaded templates.
     */
    bool generate_yaml(const std::filesystem::path &capabilities_json_path,
                       const std::filesystem::path &output_yaml_path);

    /**
     * @brief Generate a complete Archipelago YAML from a JSON string.
     */
    bool generate_yaml(const std::string &capabilities_json, const std::filesystem::path &output_yaml_path);

    // =========================================================================
    // YAML Read/Write (for priority clients)
    // =========================================================================

    bool load_yaml(const std::filesystem::path &yaml_path);
    bool save_yaml(const std::filesystem::path &yaml_path);
    bool save_yaml(); // save to last loaded path

    // =========================================================================
    // Option Management (generic, game-agnostic)
    // =========================================================================

    std::string get_option(const std::string &key) const;
    void set_option(const std::string &key, const std::string &value);
    std::map<std::string, std::string> get_all_options() const;

    // =========================================================================
    // Identity
    // =========================================================================

    /** Player name for YAML name/description fields. */
    std::string get_player_name() const;
    void set_player_name(const std::string &name);

    /**
     * @brief AP World game identifier for the YAML "game:" field.
     *
     * This is the AP World name (e.g., "APFramework"), NOT the framework
     * config's game_name (e.g., "Palworld"). This component only owns
     * the YAML-level identity.
     */
    std::string get_ap_world_name() const;
    void set_ap_world_name(const std::string &name);

    // =========================================================================
    // Capabilities Data
    // =========================================================================

    std::string get_capabilities_base64() const;
    void set_capabilities_from_json(const std::string &json_string);

    // =========================================================================
    // Slot Data (received from AP server after generation)
    // =========================================================================

    void set_slot_data(const nlohmann::json &slot_data);
    nlohmann::json get_slot_data() const;

  private:
    std::string capabilities_base64_;
    std::string player_name_;                  // populated from APConfig slot_name
    std::string ap_world_name_ = "APFramework";
    std::string requires_version_ = "0.6.5";
    std::map<std::string, std::string> options_;
    std::vector<OptionDefinition> option_definitions_;
    nlohmann::json slot_data_;
    std::filesystem::path last_yaml_path_;

    void populate_defaults();
    bool load_template_file(const std::filesystem::path &path);
    std::string serialize_to_yaml() const;
    bool deserialize_from_yaml(const std::string &yaml_content);
};

} // namespace ap
