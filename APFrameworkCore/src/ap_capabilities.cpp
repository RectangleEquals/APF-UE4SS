#include "ap_capabilities.h"
#include "ap_config.h"
#include "ap_generated_config.h"
#include "ap_logger.h"
#include "ap_mod_registry.h"
#include "ap_path_util.h"
#include "ap_vocabulary.h"

#include <algorithm>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <map>
#include <nlohmann/json.hpp>
#include <sstream>

// Simple SHA-1 implementation for checksum generation
namespace
{

class SHA1
{
  public:
    SHA1()
    {
        reset();
    }

    void reset()
    {
        h_[0] = 0x67452301;
        h_[1] = 0xEFCDAB89;
        h_[2] = 0x98BADCFE;
        h_[3] = 0x10325476;
        h_[4] = 0xC3D2E1F0;
        bit_count_ = 0;
        buffer_size_ = 0;
    }

    void update(const std::string &data)
    {
        update(reinterpret_cast<const uint8_t *>(data.data()), data.size());
    }

    void update(const uint8_t *data, size_t length)
    {
        for (size_t i = 0; i < length; ++i)
        {
            buffer_[buffer_size_++] = data[i];
            if (buffer_size_ == 64)
            {
                process_block();
                buffer_size_ = 0;
            }
        }
        bit_count_ += length * 8;
    }

    std::string final_hex()
    {
        // Padding
        uint64_t bit_count = bit_count_;
        buffer_[buffer_size_++] = 0x80;

        while (buffer_size_ != 56)
        {
            if (buffer_size_ == 64)
            {
                process_block();
                buffer_size_ = 0;
            }
            buffer_[buffer_size_++] = 0x00;
        }

        // Append length in bits (big-endian)
        for (int i = 7; i >= 0; --i)
        {
            buffer_[buffer_size_++] = static_cast<uint8_t>((bit_count >> (i * 8)) & 0xFF);
        }
        process_block();

        // Convert to hex string
        std::ostringstream oss;
        for (int i = 0; i < 5; ++i)
        {
            oss << std::hex << std::setfill('0') << std::setw(8) << h_[i];
        }
        return oss.str();
    }

  private:
    void process_block()
    {
        uint32_t w[80];

        // Break chunk into 16 32-bit big-endian words
        for (int i = 0; i < 16; ++i)
        {
            w[i] = (static_cast<uint32_t>(buffer_[i * 4]) << 24) | (static_cast<uint32_t>(buffer_[i * 4 + 1]) << 16) |
                   (static_cast<uint32_t>(buffer_[i * 4 + 2]) << 8) | (static_cast<uint32_t>(buffer_[i * 4 + 3]));
        }

        // Extend to 80 words
        for (int i = 16; i < 80; ++i)
        {
            w[i] = rotate_left(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        }

        uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3], e = h_[4];

        for (int i = 0; i < 80; ++i)
        {
            uint32_t f, k;
            if (i < 20)
            {
                f = (b & c) | ((~b) & d);
                k = 0x5A827999;
            }
            else if (i < 40)
            {
                f = b ^ c ^ d;
                k = 0x6ED9EBA1;
            }
            else if (i < 60)
            {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8F1BBCDC;
            }
            else
            {
                f = b ^ c ^ d;
                k = 0xCA62C1D6;
            }

            uint32_t temp = rotate_left(a, 5) + f + e + k + w[i];
            e = d;
            d = c;
            c = rotate_left(b, 30);
            b = a;
            a = temp;
        }

        h_[0] += a;
        h_[1] += b;
        h_[2] += c;
        h_[3] += d;
        h_[4] += e;
    }

    static uint32_t rotate_left(uint32_t value, int bits)
    {
        return (value << bits) | (value >> (32 - bits));
    }

    uint32_t h_[5];
    uint8_t buffer_[64];
    size_t buffer_size_;
    uint64_t bit_count_;
};

} // anonymous namespace

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APCapabilities *APCapabilities::get()
{
    static std::unique_ptr<APCapabilities> instance = std::make_unique<APCapabilities>(ConstructorKey{});
    return instance.get();
}

APCapabilities::APCapabilities(ConstructorKey)
{
    // Default initialization
}

APCapabilities::~APCapabilities() = default;

// =============================================================================
// Registration
// =============================================================================

void APCapabilities::add_manifest(const Manifest &manifest)
{
    // Merge regions by name using OR-merge:
    // When multiple mods contribute logic to the same region, their expressions
    // are OR'd together. Each mod provides an alternative access path.
    for (const auto &reg : manifest.regions)
    {
        // Store per-mod contribution before merging (for tracker ecosystem metadata)
        if (!reg.logic.empty())
        {
            region_contributions_.push_back({reg.name, manifest.mod_id, reg.logic});
        }

        bool merged = false;
        for (auto &existing : regions_)
        {
            if (existing.name == reg.name)
            {
                // OR-merge logic strings
                if (!reg.logic.empty())
                {
                    if (existing.logic.empty())
                    {
                        existing.logic = reg.logic;
                    }
                    else
                    {
                        existing.logic = "(" + existing.logic + ") OR (" + reg.logic + ")";
                    }
                    APLogger::get()->log(LogLevel::Info, "APCapabilities",
                                         "Region '" + reg.name + "' logic OR-merged from mod: " + manifest.mod_id);
                }
                merged = true;
                break;
            }
        }
        if (!merged)
        {
            regions_.push_back(reg);
        }
    }

    // Add locations
    for (const auto &loc : manifest.locations)
    {
        for (int i = 1; i <= loc.amount; ++i)
        {
            LocationOwnership ownership;
            ownership.mod_id = manifest.mod_id;
            ownership.location_name = loc.name;
            ownership.instance = i;
            ownership.logic = loc.logic;
            ownership.priority = loc.priority;
            ownership.exclude  = loc.exclude;
            locations_.push_back(ownership);
        }
    }

    // Add items
    for (const auto &item : manifest.items)
    {
        ItemOwnership ownership;
        ownership.mod_id = manifest.mod_id;
        ownership.item_name = item.name;
        ownership.type = item.type;
        ownership.action = item.action;
        ownership.args = item.args;
        ownership.max_count = (item.amount < 0) ? -1 : item.amount;
        ownership.count_expr = item.amount_expr;
        ownership.logic = item.logic;
        ownership.early = item.early;
        ownership.start = item.start;
        ownership.local = item.local;
        items_.push_back(ownership);
    }

    // Collect mod-declared options (last-wins on key conflict)
    for (const auto &opt : manifest.options)
    {
        bool replaced = false;
        for (auto &existing : mod_options_)
        {
            if (existing.key == opt.key)
            {
                existing = opt;
                replaced = true;
                break;
            }
        }
        if (!replaced)
        {
            mod_options_.push_back(opt);
        }
    }

    // Collect goals: first declaration wins for display/description; logic conflicts OR-merged.
    for (const auto &goal : manifest.goals)
    {
        bool found = false;
        for (auto &existing : goals_)
        {
            if (existing.name == goal.name)
            {
                found = true;
                // Display/description conflict: keep first declaration, log a warning.
                if (existing.display != goal.display || existing.description != goal.description)
                {
                    APLogger::get()->log(
                        LogLevel::Warn, "APCapabilities",
                        "Goal '" + goal.name + "' declared by multiple mods with conflicting "
                        "display/description — using first declaration from " +
                        (existing.source_mods.empty() ? "unknown" : existing.source_mods.front()));
                }
                // Logic conflict: accumulate in combined_logics if different.
                if (!goal.logic.empty() && goal.logic != existing.logic)
                    existing.combined_logics.push_back(goal.logic);
                // Track all contributing mods.
                existing.source_mods.push_back(manifest.mod_id);
                break;
            }
        }
        if (!found)
        {
            GoalDef g = goal;
            g.source_mods.push_back(manifest.mod_id);
            goals_.push_back(std::move(g));
        }
    }

    // Collect item overrides (source_mod set here since it isn't in the JSON)
    for (auto ovr : manifest.item_overrides)
    {
        ovr.source_mod = manifest.mod_id;
        item_overrides_.push_back(ovr);
    }

    // Collect location overrides (source_mod set here since it isn't in the JSON)
    for (auto ovr : manifest.location_overrides)
    {
        ovr.source_mod = manifest.mod_id;
        location_overrides_.push_back(ovr);
    }

    APLogger::get()->log(LogLevel::Debug, "APCapabilities",
                         "Added " + manifest.mod_id + ": " +
                             std::to_string(manifest.items.size()) + " items, " +
                             std::to_string(manifest.locations.size()) + " locs, " +
                             std::to_string(manifest.regions.size()) + " regions, " +
                             std::to_string(manifest.goals.size()) + " goals");
}

void APCapabilities::clear()
{
    locations_.clear();
    items_.clear();
    regions_.clear();
    mod_options_.clear();
    goals_.clear();
    item_overrides_.clear();
    location_overrides_.clear();
    region_contributions_.clear();
}

// =============================================================================
// Validation
// =============================================================================

ValidationResult APCapabilities::validate() const
{
    ValidationResult result;
    result.valid = true;

    // Get manifests from registry for incompatibility checking
    auto manifests = APModRegistry::get()->get_enabled_manifests();
    std::map<std::string, Manifest> manifest_map;
    for (const auto &m : manifests)
    {
        manifest_map[m.mod_id] = m;
    }

    APLogger::get()->log(LogLevel::Debug, "APCapabilities",
                         "Validating " + std::to_string(manifest_map.size()) + " manifests");

    // Check for incompatibilities between mods (using semver constraints)
    for (const auto &[mod_id, manifest] : manifest_map)
    {
        for (const auto &inc : manifest.incompatible)
        {
            auto it = manifest_map.find(inc.mod_id);
            if (it != manifest_map.end())
            {
                // No constraints: incompatible with ALL versions of the target mod
                // With constraints: incompatible only with matching versions
                if (inc.constraints.empty() || inc.version_satisfied(it->second.version))
                {
                    Conflict conflict;
                    conflict.capability_name = "mod_incompatibility";
                    conflict.mod_id_1 = mod_id;
                    conflict.mod_id_2 = inc.mod_id;
                    std::string desc = mod_id + " is incompatible with " + inc.mod_id;
                    if (!inc.constraints.empty())
                    {
                        desc += " (" + inc.constraint_string() + "), found v" + it->second.version;
                    }
                    conflict.description = desc;
                    result.conflicts.push_back(conflict);
                    result.valid = false;
                }
            }
        }
    }

    // Validate dependencies — mod must exist and satisfy version constraints
    for (const auto &[mod_id, manifest] : manifest_map)
    {
        for (const auto &dep : manifest.depends)
        {
            auto it = manifest_map.find(dep.mod_id);
            if (it == manifest_map.end())
            {
                Conflict conflict;
                conflict.capability_name = "missing_dependency";
                conflict.mod_id_1 = mod_id;
                conflict.mod_id_2 = dep.mod_id;
                conflict.description = mod_id + " depends on " + dep.mod_id + " which is not discovered/enabled";
                result.conflicts.push_back(conflict);
                result.valid = false;
            }
            else if (!dep.version_satisfied(it->second.version))
            {
                Conflict conflict;
                conflict.capability_name = "version_mismatch";
                conflict.mod_id_1 = mod_id;
                conflict.mod_id_2 = dep.mod_id;
                conflict.description = mod_id + " depends on " + dep.mod_id +
                    " (" + dep.constraint_string() + ") but found v" + it->second.version;
                result.conflicts.push_back(conflict);
                result.valid = false;
            }
        }
    }

    // Check for duplicate location names across mods (warn for visibility)
    std::map<std::string, std::string> location_owners;
    for (const auto &loc : locations_)
    {
        std::string key = loc.location_name + "#" + std::to_string(loc.instance);
        auto it = location_owners.find(key);
        if (it != location_owners.end() && it->second != loc.mod_id)
        {
            result.warnings.push_back(
                "Location '" + loc.location_name + "' defined by both " +
                it->second + " and " + loc.mod_id);
        }
        else
        {
            location_owners[key] = loc.mod_id;
        }
    }

    // Check for duplicate item names across mods
    std::map<std::string, std::string> item_owners;
    for (const auto &item : items_)
    {
        auto it = item_owners.find(item.item_name);
        if (it != item_owners.end() && it->second != item.mod_id)
        {
            result.warnings.push_back(
                "Item '" + item.item_name + "' defined by both " +
                it->second + " and " + item.mod_id);
        }
        else
        {
            item_owners[item.item_name] = item.mod_id;
        }
    }

    // Vocabulary validation (advisory, opt-in per manifest)
    auto framework_folder = APPathUtil::get()->find_framework_mod_folder();
    if (framework_folder)
    {
        std::string game_name = APConfig::get()->get_game_name();
        auto vocab_dir = *framework_folder / "Templates" / game_name;

        APVocabulary vocab;
        if (vocab.load(vocab_dir))
        {
            // Only validate manifests that opted in with vocab_validation: true
            for (const auto &[mod_id, manifest] : manifest_map)
            {
                if (manifest.vocab_validation)
                {
                    auto vocab_warnings = vocab.validate_manifest(manifest);
                    result.warnings.insert(result.warnings.end(),
                                           vocab_warnings.begin(), vocab_warnings.end());
                }
            }
        }
    }

    APLogger::get()->log(result.valid ? LogLevel::Info : LogLevel::Warn, "APCapabilities",
                         "Validation: " + std::string(result.valid ? "passed" : "FAILED") +
                             " (" + std::to_string(result.conflicts.size()) + " conflicts, " +
                             std::to_string(result.warnings.size()) + " warnings)");

    return result;
}

std::vector<Conflict> APCapabilities::get_conflicts() const
{
    return validate().conflicts;
}

bool APCapabilities::has_conflicts() const
{
    return !validate().valid;
}


// =============================================================================
// ID Assignment
// =============================================================================

void APCapabilities::assign_ids()
{
    int64_t base_id = APF_GLOBAL_ID_BASE;
    int64_t current_id = base_id;

    // Assign location IDs first
    for (auto &loc : locations_)
    {
        loc.location_id = current_id++;
    }

    // Then assign item IDs
    for (auto &item : items_)
    {
        item.item_id = current_id++;
    }

    APLogger::get()->log(LogLevel::Info, "APCapabilities",
                         "Assigned IDs: " + std::to_string(locations_.size()) + " locations, " +
                             std::to_string(items_.size()) + " items, base=" + std::to_string(base_id));
}

int64_t APCapabilities::get_location_id(const std::string &mod_id, const std::string &location_name, int instance) const
{
    for (const auto &loc : locations_)
    {
        if (loc.mod_id == mod_id && loc.location_name == location_name && loc.instance == instance)
        {
            return loc.location_id;
        }
    }
    return 0;
}

int64_t APCapabilities::get_item_id(const std::string &mod_id, const std::string &item_name) const
{
    for (const auto &item : items_)
    {
        if (item.mod_id == mod_id && item.item_name == item_name)
        {
            return item.item_id;
        }
    }
    return 0;
}

std::optional<LocationOwnership> APCapabilities::get_location_by_id(int64_t location_id) const
{
    for (const auto &loc : locations_)
    {
        if (loc.location_id == location_id)
        {
            return loc;
        }
    }
    return std::nullopt;
}

std::optional<ItemOwnership> APCapabilities::get_item_by_id(int64_t item_id) const
{
    for (const auto &item : items_)
    {
        if (item.item_id == item_id)
        {
            return item;
        }
    }
    return std::nullopt;
}

// =============================================================================
// Checksum
// =============================================================================

std::string APCapabilities::compute_checksum() const
{
    std::string game_name = APConfig::get()->get_game_name();
    std::string slot_name = APConfig::get()->get_ap_server().slot_name;

    // Get manifests from registry
    auto manifests = APModRegistry::get()->get_enabled_manifests();

    // Sort mod IDs for deterministic checksum
    std::vector<std::string> sorted_mod_ids;
    for (const auto &manifest : manifests)
    {
        sorted_mod_ids.push_back(manifest.mod_id);
    }
    std::sort(sorted_mod_ids.begin(), sorted_mod_ids.end());

    // Build manifest map for version lookup
    std::map<std::string, Manifest> manifest_map;
    for (const auto &m : manifests)
    {
        manifest_map[m.mod_id] = m;
    }

    // Build checksum input
    SHA1 sha;
    sha.update(game_name);
    sha.update(slot_name);

    for (const auto &mod_id : sorted_mod_ids)
    {
        const auto &manifest = manifest_map.at(mod_id);
        sha.update(mod_id);
        sha.update(manifest.version);

        // Include region definitions (sorted by name for determinism)
        std::vector<RegionDef> sorted_regions = manifest.regions;
        std::sort(sorted_regions.begin(), sorted_regions.end(),
                  [](const RegionDef &a, const RegionDef &b) { return a.name < b.name; });
        for (const auto &reg : sorted_regions)
        {
            sha.update(reg.name);
            sha.update(reg.logic);
        }

        // Include location names and logic
        for (const auto &loc : manifest.locations)
        {
            sha.update(loc.name);
            sha.update(std::to_string(loc.amount));
            sha.update(loc.logic);
        }

        // Include item names
        for (const auto &item : manifest.items)
        {
            sha.update(item.name);
            sha.update(item_type_to_string(item.type));
            sha.update(std::to_string(item.amount));
        }

        // Include goals
        for (const auto &goal : manifest.goals)
        {
            sha.update(goal.name);
            sha.update(goal.logic);
        }

        // Include dependency constraints
        for (const auto &dep : manifest.depends)
        {
            sha.update("dep:");
            sha.update(dep.mod_id);
            sha.update(dep.constraint_string());
        }

        // Include incompatibility constraints
        for (const auto &inc : manifest.incompatible)
        {
            sha.update("inc:");
            sha.update(inc.mod_id);
            sha.update(inc.constraint_string());
        }
    }

    return sha.final_hex();
}

// =============================================================================
// Config Generation
// =============================================================================

CapabilitiesConfig APCapabilities::generate_capabilities_config() const
{
    std::string game_name = APConfig::get()->get_game_name();
    std::string slot_name = APConfig::get()->get_ap_server().slot_name;

    CapabilitiesConfig config;
    config.version = "1.0.0";
    config.game = game_name;
    config.slot_name = slot_name;
    config.checksum = compute_checksum();
    config.id_base = APF_GLOBAL_ID_BASE;

    // Get current timestamp
    auto now = std::chrono::system_clock::now();
    config.generated_at = std::format("{:%Y-%m-%dT%H:%M:%SZ}", std::chrono::floor<std::chrono::seconds>(now));

    // Add mod info from registry
    auto manifests = APModRegistry::get()->get_enabled_manifests();
    for (const auto &manifest : manifests)
    {
        ModInfo info;
        info.mod_id = manifest.mod_id;
        info.name = manifest.name;
        info.version = manifest.version;
        config.mods.push_back(info);

        // Collect mod-defined option defaults (first-writer wins across mods)
        for (const auto &opt : manifest.options)
        {
            if (config.option_defaults.find(opt.key) == config.option_defaults.end())
            {
                config.option_defaults[opt.key] = {opt.type, opt.default_value};
            }
        }
    }

    // Add regions
    for (const auto &reg : regions_)
    {
        CapabilitiesConfigRegion cfg_reg;
        cfg_reg.name = reg.name;
        cfg_reg.logic = reg.logic;
        config.capabilities.regions.push_back(cfg_reg);
    }

    // Add locations
    for (const auto &loc : locations_)
    {
        CapabilitiesConfigLocation cfg_loc;
        cfg_loc.id = loc.location_id;
        cfg_loc.name = loc.location_name;
        cfg_loc.mod_id = loc.mod_id;
        cfg_loc.instance = loc.instance;
        cfg_loc.logic = loc.logic;
        cfg_loc.priority = loc.priority;
        cfg_loc.exclude  = loc.exclude;
        config.capabilities.locations.push_back(cfg_loc);
    }

    // Add items
    for (const auto &item : items_)
    {
        CapabilitiesConfigItem cfg_item;
        cfg_item.id = item.item_id;
        cfg_item.name = item.item_name;
        cfg_item.type = item_type_to_string(item.type);
        cfg_item.mod_id = item.mod_id;
        cfg_item.count = item.max_count;
        cfg_item.count_expr = item.count_expr;
        cfg_item.logic = item.logic;
        cfg_item.early = item.early;
        cfg_item.start = item.start;
        cfg_item.local = item.local;
        config.capabilities.items.push_back(cfg_item);
    }

    // Add goals — use aggregated goals_ directly (already conflict-resolved by add_manifest).
    // source_mods[0] is the first (primary) declaring mod; combined_logics holds extras.
    for (const auto &goal : goals_)
    {
        CapabilitiesConfigGoal cfg_goal;
        cfg_goal.name           = goal.name;
        cfg_goal.display        = goal.display;
        cfg_goal.description    = goal.description;
        cfg_goal.logic          = goal.logic;
        cfg_goal.mod_id         = goal.source_mods.empty() ? "" : goal.source_mods.front();
        cfg_goal.combined_logics = goal.combined_logics;
        cfg_goal.source_mods    = goal.source_mods;
        config.capabilities.goals.push_back(std::move(cfg_goal));
    }

    // Add item overrides (source_mod already set by add_manifest via item_overrides_)
    for (const auto &ovr : item_overrides_)
    {
        CapabilitiesConfigItemOverride cfg_ovr;
        cfg_ovr.target_item = ovr.target_item;
        cfg_ovr.target_mod = ovr.target_mod;
        cfg_ovr.type = ovr.type;
        cfg_ovr.logic = ovr.logic;
        cfg_ovr.source_mod = ovr.source_mod;
        config.capabilities.item_overrides.push_back(cfg_ovr);
    }

    APLogger::get()->log(LogLevel::Info, "APCapabilities",
                         "Generated config: " + std::to_string(config.mods.size()) + " mods, " +
                             std::to_string(config.capabilities.locations.size()) + " locs, " +
                             std::to_string(config.capabilities.items.size()) + " items, " +
                             std::to_string(config.capabilities.regions.size()) + " regions, " +
                             std::to_string(config.capabilities.goals.size()) + " goals");

    return config;
}

bool APCapabilities::write_capabilities_config(const std::filesystem::path &output_path) const
{
    auto config = generate_capabilities_config();
    std::string json_content = config.to_json().dump(2);
    APLogger::get()->log(LogLevel::Info, "APCapabilities", "Writing capabilities config: " + output_path.string());
    return APPathUtil::get()->write_file(output_path, json_content);
}

std::filesystem::path APCapabilities::write_capabilities_config_default() const
{
    APLogger::get()->log(LogLevel::Trace, "APCapabilities", "> APCapabilities::write_capabilities_config_default()");

    auto output_folder = APPathUtil::get()->find_output_folder();
    if (!output_folder)
    {
        APLogger::get()->log(LogLevel::Error, "APCapabilities", "Could not find output folder for capabilities config");
        return {};
    }

    std::string slot_name = APConfig::get()->get_ap_server().slot_name;
    std::string filename = "AP_Capabilities_" + slot_name + ".json";
    auto output_path = *output_folder / filename;

    if (!write_capabilities_config(output_path))
    {
        return {};
    }

    APLogger::get()->log(LogLevel::Info, "APCapabilities", "Wrote capabilities config: " + output_path.string());

    // Load option templates and generate YAML
    auto framework_folder = APPathUtil::get()->find_framework_mod_folder();
    if (framework_folder)
    {
        auto templates_dir = *framework_folder / "Templates";
        std::string game_name = APConfig::get()->get_game_name();
        APGeneratedConfig::get()->load_templates(templates_dir, game_name);

        // Build mod options including auto-generated goal option
        auto options_with_goals = mod_options_;
        if (goals_.size() > 1)
        {
            ManifestOptionDef goal_opt;
            goal_opt.key = "goal";
            goal_opt.type = "text_choice";
            goal_opt.description = "Win condition for this game";
            for (const auto &g : goals_)
            {
                goal_opt.choices.push_back(g.name);
            }
            goal_opt.default_value = goals_.front().name;
            options_with_goals.push_back(goal_opt);
        }

        // Merge mod-declared options into generated config
        // Priority: default_options.json < game_options.json < manifest options
        APGeneratedConfig::get()->merge_mod_options(options_with_goals);
    }

    std::string yaml_filename = "AP_" + slot_name + ".yaml";
    auto yaml_path = *output_folder / yaml_filename;

    // Read the JSON we just wrote and generate YAML with base64-encoded capabilities
    std::string json_content = APPathUtil::get()->read_file(output_path);
    if (!json_content.empty())
    {
        if (APGeneratedConfig::get()->generate_yaml(json_content, yaml_path))
        {
            APLogger::get()->log(LogLevel::Info, "APCapabilities",
                                 "Generated YAML for Archipelago: " + yaml_path.string());
        }
        else
        {
            APLogger::get()->log(LogLevel::Warn, "APCapabilities",
                                 "Failed to generate YAML: " + yaml_path.string());
        }
    }

    return output_path;
}

// =============================================================================
// Queries
// =============================================================================

std::vector<LocationOwnership> APCapabilities::get_all_locations() const
{
    return locations_;
}

std::vector<ItemOwnership> APCapabilities::get_all_items() const
{
    return items_;
}

std::vector<LocationOwnership> APCapabilities::get_locations_for_mod(const std::string &mod_id) const
{
    std::vector<LocationOwnership> result;

    for (const auto &loc : locations_)
    {
        if (loc.mod_id == mod_id)
        {
            result.push_back(loc);
        }
    }

    return result;
}

std::vector<ItemOwnership> APCapabilities::get_items_for_mod(const std::string &mod_id) const
{
    std::vector<ItemOwnership> result;

    for (const auto &item : items_)
    {
        if (item.mod_id == mod_id)
        {
            result.push_back(item);
        }
    }

    return result;
}

size_t APCapabilities::get_location_count() const
{
    return locations_.size();
}

size_t APCapabilities::get_item_count() const
{
    return items_.size();
}

std::vector<RegionDef> APCapabilities::get_regions() const
{
    return regions_;
}

std::vector<ManifestOptionDef> APCapabilities::get_mod_options() const
{
    return mod_options_;
}

std::vector<GoalDef> APCapabilities::get_goals() const
{
    return goals_;
}

std::vector<ItemOverrideDef> APCapabilities::get_item_overrides() const
{
    return item_overrides_;
}

std::vector<LocationOverrideDef> APCapabilities::get_location_overrides() const
{
    return location_overrides_;
}

void APCapabilities::apply_location_overrides()
{
    for (const auto &ovr : location_overrides_)
    {
        // Find the target location by name + mod_id
        LocationOwnership *target = nullptr;
        for (auto &loc : locations_)
        {
            if (loc.location_name == ovr.location && loc.mod_id == ovr.target_mod)
            {
                target = &loc;
                break;
            }
        }

        if (!target)
        {
            APLogger::get()->log(LogLevel::Warn, "APCapabilities",
                "overrides.locations: location '" + ovr.location +
                "' not found in mod '" + ovr.target_mod + "' (override from " + ovr.source_mod + ")");
            continue;
        }

        // OR-merge logic
        if (target->logic.empty())
        {
            target->logic = ovr.logic;
        }
        else
        {
            target->logic = "(" + target->logic + ") OR (" + ovr.logic + ")";
        }

        APLogger::get()->log(LogLevel::Info, "APCapabilities",
            "Location '" + ovr.location + "' logic OR-merged from mod: " + ovr.source_mod);
    }
}

std::vector<APCapabilities::RegionContribution> APCapabilities::get_all_region_contributions() const
{
    return region_contributions_;
}

std::vector<APCapabilities::RegionContribution> APCapabilities::get_region_contributions(const std::string &region_name) const
{
    std::vector<RegionContribution> result;
    for (const auto &contrib : region_contributions_)
    {
        if (contrib.region_name == region_name)
        {
            result.push_back(contrib);
        }
    }
    return result;
}

} // namespace ap