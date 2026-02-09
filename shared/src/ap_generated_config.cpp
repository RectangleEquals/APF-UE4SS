#include "ap_generated_config.h"
#include "ap_base64.h"
#include "ap_config.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <fstream>
#include <sstream>

#include <ryml.hpp>
#include <ryml_std.hpp>
#include <c4/format.hpp>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APGeneratedConfig *APGeneratedConfig::get()
{
    static std::unique_ptr<APGeneratedConfig> instance = std::make_unique<APGeneratedConfig>(ConstructorKey{});
    return instance.get();
}

APGeneratedConfig::APGeneratedConfig(ConstructorKey)
{
    // Read player name from APConfig if available
    auto *config = APConfig::get();
    if (config && config->is_loaded())
    {
        player_name_ = config->get_slot_name();
    }

    if (player_name_.empty())
    {
        player_name_ = "Player1";
    }
}

APGeneratedConfig::~APGeneratedConfig() = default;

// =============================================================================
// Template Loading
// =============================================================================

bool APGeneratedConfig::load_templates(const std::filesystem::path &templates_dir, const std::string &game_name)
{
    option_definitions_.clear();
    options_.clear();

    bool loaded_any = false;

    // 1. Load default template first
    auto default_path = templates_dir / "default_options.json";
    if (load_template_file(default_path))
    {
        loaded_any = true;
        APLogger::get()->log(LogLevel::Debug, "APGeneratedConfig",
                             "Loaded default option template: " + default_path.string());
    }

    // 2. Load game-specific template (overrides/extends defaults)
    if (!game_name.empty())
    {
        // Normalize game name for filename (lowercase, replace spaces)
        std::string filename = game_name;
        for (auto &c : filename)
        {
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            if (c == ' ')
            {
                c = '_';
            }
        }
        filename += "_options.json";

        auto game_path = templates_dir / filename;
        if (load_template_file(game_path))
        {
            loaded_any = true;
            APLogger::get()->log(LogLevel::Debug, "APGeneratedConfig",
                                 "Loaded game-specific option template: " + game_path.string());
        }
    }

    // Apply defaults from loaded definitions
    populate_defaults();

    if (!loaded_any)
    {
        APLogger::get()->log(LogLevel::Warn, "APGeneratedConfig",
                             "No option templates found in: " + templates_dir.string());
    }

    return loaded_any;
}

bool APGeneratedConfig::load_template_file(const std::filesystem::path &path)
{
    if (!APPathUtil::get()->file_exists(path))
    {
        return false;
    }

    std::string content = APPathUtil::get()->read_file(path);
    if (content.empty())
    {
        return false;
    }

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);

        // Read yaml_metadata if present
        if (j.contains("yaml_metadata"))
        {
            auto &meta = j["yaml_metadata"];
            if (meta.contains("requires_version"))
            {
                requires_version_ = meta["requires_version"].get<std::string>();
            }
        }

        // Read option definitions
        if (j.contains("options") && j["options"].is_object())
        {
            for (auto &[key, value] : j["options"].items())
            {
                OptionDefinition def;
                def.key = key;
                def.type = value.value("type", "text_choice");
                def.description = value.value("description", "");

                // Parse default value to string
                if (value.contains("default"))
                {
                    auto &d = value["default"];
                    if (d.is_boolean())
                    {
                        def.default_value = d.get<bool>() ? "true" : "false";
                    }
                    else if (d.is_number_integer())
                    {
                        def.default_value = std::to_string(d.get<int>());
                    }
                    else
                    {
                        def.default_value = d.get<std::string>();
                    }
                }

                def.range_start = value.value("range_start", 0);
                def.range_end = value.value("range_end", 100);

                // Check if this key already exists (game-specific overrides default)
                bool found = false;
                for (auto &existing : option_definitions_)
                {
                    if (existing.key == key)
                    {
                        existing = def;
                        found = true;
                        break;
                    }
                }

                if (!found)
                {
                    option_definitions_.push_back(def);
                }
            }
        }

        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APGeneratedConfig",
                             "Failed to parse template: " + path.string() + " - " + std::string(e.what()));
        return false;
    }
}

void APGeneratedConfig::populate_defaults()
{
    for (const auto &def : option_definitions_)
    {
        // Only set default if not already set (e.g., from a loaded YAML)
        if (options_.find(def.key) == options_.end())
        {
            options_[def.key] = def.default_value;
        }
    }
}

std::vector<OptionDefinition> APGeneratedConfig::get_option_definitions() const
{
    return option_definitions_;
}

// =============================================================================
// YAML Generation
// =============================================================================

bool APGeneratedConfig::generate_yaml(const std::filesystem::path &capabilities_json_path,
                                      const std::filesystem::path &output_yaml_path)
{
    std::string json_content = APPathUtil::get()->read_file(capabilities_json_path);
    if (json_content.empty())
    {
        APLogger::get()->log(LogLevel::Error, "APGeneratedConfig",
                             "Failed to read capabilities file: " + capabilities_json_path.string());
        return false;
    }

    return generate_yaml(json_content, output_yaml_path);
}

bool APGeneratedConfig::generate_yaml(const std::string &capabilities_json,
                                      const std::filesystem::path &output_yaml_path)
{
    // Base64-encode the capabilities JSON
    capabilities_base64_ = base64_encode(capabilities_json);

    // Update player name from APConfig if available
    auto *config = APConfig::get();
    if (config && config->is_loaded() && !config->get_slot_name().empty())
    {
        player_name_ = config->get_slot_name();
    }

    // Serialize to YAML
    std::string yaml_content = serialize_to_yaml();

    // Write to file
    if (APPathUtil::get()->write_file(output_yaml_path, yaml_content))
    {
        last_yaml_path_ = output_yaml_path;
        APLogger::get()->log(LogLevel::Info, "APGeneratedConfig",
                             "Generated YAML: " + output_yaml_path.string());
        return true;
    }

    APLogger::get()->log(LogLevel::Error, "APGeneratedConfig",
                         "Failed to write YAML: " + output_yaml_path.string());
    return false;
}

// =============================================================================
// YAML Read/Write
// =============================================================================

bool APGeneratedConfig::load_yaml(const std::filesystem::path &yaml_path)
{
    std::string content = APPathUtil::get()->read_file(yaml_path);
    if (content.empty())
    {
        APLogger::get()->log(LogLevel::Error, "APGeneratedConfig",
                             "Failed to read YAML: " + yaml_path.string());
        return false;
    }

    if (deserialize_from_yaml(content))
    {
        last_yaml_path_ = yaml_path;
        APLogger::get()->log(LogLevel::Debug, "APGeneratedConfig",
                             "Loaded YAML: " + yaml_path.string());
        return true;
    }

    return false;
}

bool APGeneratedConfig::save_yaml(const std::filesystem::path &yaml_path)
{
    std::string yaml_content = serialize_to_yaml();

    if (APPathUtil::get()->write_file(yaml_path, yaml_content))
    {
        last_yaml_path_ = yaml_path;
        APLogger::get()->log(LogLevel::Debug, "APGeneratedConfig",
                             "Saved YAML: " + yaml_path.string());
        return true;
    }

    return false;
}

bool APGeneratedConfig::save_yaml()
{
    if (last_yaml_path_.empty())
    {
        APLogger::get()->log(LogLevel::Error, "APGeneratedConfig", "No YAML path set for save");
        return false;
    }

    return save_yaml(last_yaml_path_);
}

// =============================================================================
// Option Management
// =============================================================================

std::string APGeneratedConfig::get_option(const std::string &key) const
{
    auto it = options_.find(key);
    return (it != options_.end()) ? it->second : "";
}

void APGeneratedConfig::set_option(const std::string &key, const std::string &value)
{
    options_[key] = value;
}

std::map<std::string, std::string> APGeneratedConfig::get_all_options() const
{
    return options_;
}

// =============================================================================
// Identity
// =============================================================================

std::string APGeneratedConfig::get_player_name() const
{
    return player_name_;
}

void APGeneratedConfig::set_player_name(const std::string &name)
{
    player_name_ = name;
}

std::string APGeneratedConfig::get_ap_world_name() const
{
    return ap_world_name_;
}

void APGeneratedConfig::set_ap_world_name(const std::string &name)
{
    ap_world_name_ = name;
}

// =============================================================================
// Capabilities Data
// =============================================================================

std::string APGeneratedConfig::get_capabilities_base64() const
{
    return capabilities_base64_;
}

void APGeneratedConfig::set_capabilities_from_json(const std::string &json_string)
{
    capabilities_base64_ = base64_encode(json_string);
}

// =============================================================================
// Slot Data
// =============================================================================

void APGeneratedConfig::set_slot_data(const nlohmann::json &slot_data)
{
    slot_data_ = slot_data;
}

nlohmann::json APGeneratedConfig::get_slot_data() const
{
    return slot_data_;
}

// =============================================================================
// YAML Serialization (using rapidyaml)
// =============================================================================

std::string APGeneratedConfig::serialize_to_yaml() const
{
    // Build YAML manually with ryml
    ryml::Tree tree;
    ryml::NodeRef root = tree.rootref();
    root |= ryml::MAP;

    // Top-level fields
    root["description"] << player_name_;
    root["name"] << player_name_;
    root["game"] << ap_world_name_;

    // requires section
    auto requires_node = root["requires"];
    requires_node |= ryml::MAP;
    requires_node["version"] << requires_version_;

    // Game options section (under the AP world name)
    auto game_node = root[ryml::to_csubstr(ap_world_name_)];
    game_node |= ryml::MAP;

    // capabilities_data (always first)
    game_node["capabilities_data"] << capabilities_base64_;

    // Template-driven options
    for (const auto &def : option_definitions_)
    {
        auto it = options_.find(def.key);
        std::string value = (it != options_.end()) ? it->second : def.default_value;

        auto key = ryml::to_csubstr(def.key);

        if (def.type == "toggle")
        {
            // Write as YAML boolean
            if (value == "true" || value == "1")
            {
                game_node[key] << true;
            }
            else
            {
                game_node[key] << false;
            }
        }
        else if (def.type == "range")
        {
            // Write as integer
            try
            {
                int int_val = std::stoi(value);
                game_node[key] << int_val;
            }
            catch (...)
            {
                game_node[key] << value;
            }
        }
        else
        {
            // Write as string
            game_node[key] << value;
        }
    }

    // Emit YAML to string
    std::string output;
    output.reserve(capabilities_base64_.size() + 512);

    // Add header comment
    output = "# Generated by AP Framework\n";
    output += "# Modify options below, then provide this file to Archipelago for generation\n\n";

    // Emit the tree
    ryml::emitrs_yaml(tree, &output, /* append */ true);

    return output;
}

bool APGeneratedConfig::deserialize_from_yaml(const std::string &yaml_content)
{
    try
    {
        // Parse YAML
        ryml::Tree tree = ryml::parse_in_arena(ryml::to_csubstr(yaml_content));
        ryml::ConstNodeRef root = tree.rootref();

        if (!root.is_map())
        {
            APLogger::get()->log(LogLevel::Error, "APGeneratedConfig", "YAML root is not a map");
            return false;
        }

        // Read top-level fields
        if (root.has_child("name"))
        {
            root["name"] >> player_name_;
        }

        if (root.has_child("game"))
        {
            root["game"] >> ap_world_name_;
        }

        if (root.has_child("requires"))
        {
            auto req = root["requires"];
            if (req.has_child("version"))
            {
                req["version"] >> requires_version_;
            }
        }

        // Read game options section
        auto game_key = ryml::to_csubstr(ap_world_name_);
        if (root.has_child(game_key))
        {
            auto game_node = root[game_key];
            if (game_node.is_map())
            {
                // Read capabilities_data
                if (game_node.has_child("capabilities_data"))
                {
                    game_node["capabilities_data"] >> capabilities_base64_;
                }

                // Read all other options into the map
                for (auto child : game_node)
                {
                    std::string key;
                    child >> ryml::key(key);

                    if (key == "capabilities_data")
                    {
                        continue; // already handled
                    }

                    std::string value;
                    child >> value;
                    options_[key] = value;
                }
            }
        }

        APLogger::get()->log(LogLevel::Trace, "APGeneratedConfig",
                             "Deserialized YAML: player=" + player_name_ + ", game=" + ap_world_name_ +
                                 ", options=" + std::to_string(options_.size()));

        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APGeneratedConfig",
                             "Failed to parse YAML: " + std::string(e.what()));
        return false;
    }
}

} // namespace ap
