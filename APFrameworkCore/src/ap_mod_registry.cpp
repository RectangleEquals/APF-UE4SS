#include "ap_mod_registry.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <regex>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APModRegistry *APModRegistry::get()
{
    static std::unique_ptr<APModRegistry> instance = std::make_unique<APModRegistry>(ConstructorKey{});
    return instance.get();
}

APModRegistry::APModRegistry(ConstructorKey)
{
    // Default initialization
}

APModRegistry::~APModRegistry() = default;

// =============================================================================
// Discovery
// =============================================================================

size_t APModRegistry::discover_manifests()
{
    auto mods_folder = APPathUtil::get()->find_mods_folder();
    if (!mods_folder)
    {
        APLogger::get()->log(LogLevel::Warn, "APModRegistry", "Mods folder not found");
        return 0;
    }

    size_t count = 0;
    std::error_code ec;

    for (const auto &entry : std::filesystem::directory_iterator(*mods_folder, ec))
    {
        if (!entry.is_directory(ec))
        {
            continue;
        }

        // Look for manifest.json in each mod folder
        auto manifest_path = entry.path() / "manifest.json";
        if (!APPathUtil::get()->file_exists(manifest_path))
        {
            continue;
        }

        auto manifest = parse_manifest_file(manifest_path);
        if (!manifest)
        {
            APLogger::get()->log(LogLevel::Warn, "APModRegistry",
                                 "Failed to parse manifest: " + manifest_path.string());
            continue;
        }

        // Skip if mod_id already exists
        if (manifests_.find(manifest->mod_id) != manifests_.end())
        {
            APLogger::get()->log(LogLevel::Warn, "APModRegistry", "Duplicate mod_id: " + manifest->mod_id);
            continue;
        }

        APLogger::get()->log(LogLevel::Debug, "APModRegistry",
                             "Discovered mod: " + manifest->mod_id + " v" + manifest->version +
                                 (manifest->enabled ? "" : " (disabled)"));

        add_manifest(*manifest);
        count++;
    }

    APLogger::get()->log(LogLevel::Info, "APModRegistry", "Discovered " + std::to_string(count) + " mods");

    return count;
}

bool APModRegistry::add_manifest(const Manifest &manifest)
{
    if (manifests_.find(manifest.mod_id) != manifests_.end())
    {
        return false;
    }

    manifests_[manifest.mod_id] = manifest;
    return true;
}

void APModRegistry::clear()
{
    manifests_.clear();
    registered_.clear();
}

// =============================================================================
// Registration
// =============================================================================

bool APModRegistry::mark_registered(const std::string &mod_id)
{
    if (manifests_.find(mod_id) == manifests_.end())
    {
        return false;
    }

    registered_.insert(mod_id);

    APLogger::get()->log(LogLevel::Debug, "APModRegistry", "Mod registered: " + mod_id);

    return true;
}

bool APModRegistry::is_registered(const std::string &mod_id) const
{
    return registered_.find(mod_id) != registered_.end();
}

bool APModRegistry::all_registered() const
{
    for (const auto &[mod_id, manifest] : manifests_)
    {
        if (manifest.enabled && registered_.find(mod_id) == registered_.end())
        {
            return false;
        }
    }
    return true;
}

std::vector<std::string> APModRegistry::get_pending_registrations() const
{
    std::vector<std::string> pending;

    for (const auto &[mod_id, manifest] : manifests_)
    {
        if (manifest.enabled && registered_.find(mod_id) == registered_.end())
        {
            pending.push_back(mod_id);
        }
    }

    return pending;
}

void APModRegistry::reset_registrations()
{
    registered_.clear();
}

// =============================================================================
// Queries
// =============================================================================

std::vector<Manifest> APModRegistry::get_discovered_manifests() const
{
    std::vector<Manifest> result;
    result.reserve(manifests_.size());

    for (const auto &[mod_id, manifest] : manifests_)
    {
        result.push_back(manifest);
    }

    return result;
}

std::vector<Manifest> APModRegistry::get_enabled_manifests() const
{
    std::vector<Manifest> result;

    for (const auto &[mod_id, manifest] : manifests_)
    {
        if (manifest.enabled)
        {
            result.push_back(manifest);
        }
    }

    return result;
}

std::optional<Manifest> APModRegistry::get_manifest(const std::string &mod_id) const
{
    auto it = manifests_.find(mod_id);
    if (it != manifests_.end())
    {
        return it->second;
    }
    return std::nullopt;
}

ModType APModRegistry::get_mod_type(const std::string &mod_id) const
{
    // Priority clients match pattern: archipelago.<game>.*
    static const std::regex priority_pattern(R"(^archipelago\.[^.]+\..*)");
    if (std::regex_match(mod_id, priority_pattern))
    {
        return ModType::Priority;
    }
    return ModType::Regular;
}

bool APModRegistry::is_priority_client(const std::string &mod_id) const
{
    return get_mod_type(mod_id) == ModType::Priority;
}

std::vector<std::string> APModRegistry::get_priority_clients() const
{
    std::vector<std::string> result;

    for (const auto &[mod_id, manifest] : manifests_)
    {
        if (manifest.enabled && is_priority_client(mod_id))
        {
            result.push_back(mod_id);
        }
    }

    return result;
}

std::vector<std::string> APModRegistry::get_regular_mods() const
{
    std::vector<std::string> result;

    for (const auto &[mod_id, manifest] : manifests_)
    {
        if (manifest.enabled && !is_priority_client(mod_id))
        {
            result.push_back(mod_id);
        }
    }

    return result;
}

std::vector<ModInfo> APModRegistry::get_mod_infos() const
{
    std::vector<ModInfo> result;
    result.reserve(manifests_.size());

    for (const auto &[mod_id, manifest] : manifests_)
    {
        ModInfo info;
        info.mod_id = mod_id;
        info.name = manifest.name;
        info.version = manifest.version;
        info.type = get_mod_type(mod_id);
        info.is_registered = (registered_.find(mod_id) != registered_.end());
        info.has_conflict = false; // Set later by APCapabilities
        result.push_back(info);
    }

    return result;
}

size_t APModRegistry::count() const
{
    return manifests_.size();
}

// =============================================================================
// Manifest Parsing
// =============================================================================

std::optional<Manifest> APModRegistry::parse_manifest(const std::string &json_content) const
{
    try
    {
        nlohmann::json j = nlohmann::json::parse(json_content);

        Manifest manifest;

        // Required fields
        if (!j.contains("mod_id") || !j["mod_id"].is_string())
        {
            return std::nullopt;
        }
        manifest.mod_id = j["mod_id"].get<std::string>();

        manifest.name = j.value("name", manifest.mod_id);
        manifest.version = j.value("version", "1.0.0");
        manifest.enabled = j.value("enabled", true);
        manifest.description = j.value("description", "");

        // Parse incompatibility rules
        if (j.contains("incompatible") && j["incompatible"].is_array())
        {
            for (const auto &rule : j["incompatible"])
            {
                IncompatibilityRule inc;
                inc.id = rule.value("id", "");
                if (rule.contains("versions") && rule["versions"].is_array())
                {
                    for (const auto &ver : rule["versions"])
                    {
                        inc.versions.push_back(ver.get<std::string>());
                    }
                }
                manifest.incompatible.push_back(inc);
            }
        }

        // Parse manifest-level options
        if (j.contains("options") && j["options"].is_object())
        {
            for (const auto &[key, opt] : j["options"].items())
            {
                ManifestOptionDef mopt;
                mopt.key = key;
                mopt.type = opt.value("type", "toggle");

                // Parse default based on type
                if (opt.contains("default"))
                {
                    if (opt["default"].is_boolean())
                        mopt.default_value = opt["default"].get<bool>() ? "true" : "false";
                    else if (opt["default"].is_number_integer())
                        mopt.default_value = std::to_string(opt["default"].get<int>());
                    else
                        mopt.default_value = opt["default"].get<std::string>();
                }

                mopt.range_start = opt.value("range_start", 0);
                mopt.range_end = opt.value("range_end", 100);
                mopt.description = opt.value("description", "");

                // Parse choices for text_choice type
                if (opt.contains("choices") && opt["choices"].is_array())
                {
                    for (const auto &c : opt["choices"])
                    {
                        mopt.choices.push_back(c.get<std::string>());
                    }
                }

                manifest.options.push_back(mopt);
            }
        }

        // Parse capabilities section
        if (j.contains("capabilities") && j["capabilities"].is_object())
        {
            const auto &caps = j["capabilities"];

            // Parse regions
            if (caps.contains("regions") && caps["regions"].is_array())
            {
                for (const auto &reg : caps["regions"])
                {
                    RegionDef def;
                    def.name = reg.value("name", "");
                    parse_requirements(reg, def.requires_all, def.requires_any, def.requires_count);
                    def.requires_option = reg.value("requires_option", "");

                    // Handle ^ prefix
                    if (!def.name.empty() && def.name[0] == '^')
                    {
                        def.name = def.name.substr(1);
                        def.suppress_vocab_warning = true;
                    }

                    if (!def.name.empty())
                    {
                        manifest.regions.push_back(def);
                    }
                }
            }

            // Parse locations
            if (caps.contains("locations") && caps["locations"].is_array())
            {
                for (const auto &loc : caps["locations"])
                {
                    LocationDef def;
                    def.name = loc.value("name", "");
                    def.amount = loc.value("amount", 1);
                    def.unique = loc.value("unique", false);
                    def.region = loc.value("region", "");
                    parse_requirements(loc, def.requires_all, def.requires_any, def.requires_count);
                    def.requires_option = loc.value("requires_option", "");

                    // Handle ^ prefix
                    if (!def.name.empty() && def.name[0] == '^')
                    {
                        def.name = def.name.substr(1);
                        def.suppress_vocab_warning = true;
                    }

                    if (!def.name.empty())
                    {
                        manifest.locations.push_back(def);
                    }
                }
            }

            // Parse items
            if (caps.contains("items") && caps["items"].is_array())
            {
                for (const auto &item : caps["items"])
                {
                    ItemDef def;
                    def.name = item.value("name", "");
                    def.type = item_type_from_string(item.value("type", "filler"));
                    def.amount = item.value("amount", 1);
                    def.action = item.value("action", "");
                    def.requires_option = item.value("requires_option", "");

                    // Handle ^ prefix
                    if (!def.name.empty() && def.name[0] == '^')
                    {
                        def.name = def.name.substr(1);
                        def.suppress_vocab_warning = true;
                    }

                    // Parse action args
                    if (item.contains("args") && item["args"].is_array())
                    {
                        for (const auto &arg : item["args"])
                        {
                            ActionArg aa;
                            aa.name = arg.value("name", "");
                            aa.type = arg_type_from_string(arg.value("type", "string"));
                            if (arg.contains("value"))
                            {
                                aa.value = arg["value"];
                            }
                            def.args.push_back(aa);
                        }
                    }

                    if (!def.name.empty())
                    {
                        manifest.items.push_back(def);
                    }
                }
            }
        }

        return manifest;
    }
    catch (const nlohmann::json::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APModRegistry", "JSON parse error: " + std::string(e.what()));
        return std::nullopt;
    }
}

std::optional<Manifest> APModRegistry::parse_manifest_file(const std::filesystem::path &file_path) const
{
    std::string content = APPathUtil::get()->read_file(file_path);
    if (content.empty())
    {
        return std::nullopt;
    }
    return parse_manifest(content);
}

// =============================================================================
// Requirement Parsing Helper
// =============================================================================

void APModRegistry::parse_requirements(const nlohmann::json &j,
                                       std::vector<std::string> &out_requires,
                                       std::vector<std::string> &out_requires_any,
                                       std::vector<CountRequirement> &out_requires_count)
{
    // Parse "requires": ["A", "B"] — need ALL (AND)
    if (j.contains("requires") && j["requires"].is_array())
    {
        for (const auto &req : j["requires"])
        {
            std::string name = req.get<std::string>();
            // Strip ^ prefix from item references too
            if (!name.empty() && name[0] == '^')
                name = name.substr(1);
            out_requires.push_back(name);
        }
    }

    // Parse "requires_any": ["A", "B"] — need ANY (OR)
    if (j.contains("requires_any") && j["requires_any"].is_array())
    {
        for (const auto &req : j["requires_any"])
        {
            std::string name = req.get<std::string>();
            if (!name.empty() && name[0] == '^')
                name = name.substr(1);
            out_requires_any.push_back(name);
        }
    }

    // Parse "requires_count": [{"item": "XP", "count": 5}] — need N of item
    if (j.contains("requires_count") && j["requires_count"].is_array())
    {
        for (const auto &rc : j["requires_count"])
        {
            CountRequirement cr;
            cr.item = rc.value("item", "");
            cr.count = rc.value("count", 1);
            // Strip ^ prefix from item references
            if (!cr.item.empty() && cr.item[0] == '^')
                cr.item = cr.item.substr(1);
            if (!cr.item.empty())
                out_requires_count.push_back(cr);
        }
    }
}

} // namespace ap