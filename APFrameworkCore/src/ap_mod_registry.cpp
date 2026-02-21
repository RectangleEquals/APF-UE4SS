#include "ap_mod_registry.h"
#include "ap_config.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <regex>
#include <set>

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
            APLogger::get()->log(LogLevel::Trace, "APModRegistry",
                                 "Skipped (no manifest): " + entry.path().filename().string());
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
        manifest.vocab_validation = j.value("vocab_validation", false);

        // Parse depends array — unified Dependency with optional semver constraints
        // e.g. "some.mod", "some.mod (>=1.0.0)", "some.mod (>=1.0.0, <2.0.0)"
        if (j.contains("depends") && j["depends"].is_array())
        {
            for (const auto &dep : j["depends"])
            {
                manifest.depends.push_back(Dependency::parse(dep.get<std::string>()));
            }
        }

        // Parse incompatible array — same unified Dependency format
        // e.g. "other.mod" (all versions), "other.mod (>=2.0.0)" (specific range)
        if (j.contains("incompatible") && j["incompatible"].is_array())
        {
            for (const auto &inc : j["incompatible"])
            {
                manifest.incompatible.push_back(Dependency::parse(inc.get<std::string>()));
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

        // Parse goals (top-level, aggregated across all mods)
        if (j.contains("goals") && j["goals"].is_array())
        {
            for (const auto &goal : j["goals"])
            {
                GoalDef def;
                def.name = goal.value("name", "");
                def.display = goal.value("display", "");
                def.description = goal.value("description", "");
                def.logic = goal.value("logic", "");

                if (!def.name.empty())
                {
                    manifest.goals.push_back(def);
                }
            }
        }

        // Parse capabilities section
        if (j.contains("capabilities") && j["capabilities"].is_object())
        {
            const auto &caps = j["capabilities"];

            // Parse item_overrides (cross-mod item type overrides)
            if (caps.contains("item_overrides") && caps["item_overrides"].is_array())
            {
                for (const auto &ovr : caps["item_overrides"])
                {
                    ItemOverrideDef def;
                    def.target_item = ovr.value("target_item", "");
                    def.target_mod = ovr.value("target_mod", "");
                    def.type = ovr.value("type", "");
                    def.requires_option = ovr.value("requires_option", "");

                    if (!def.target_item.empty() && !def.type.empty())
                    {
                        manifest.item_overrides.push_back(def);
                    }
                }
            }

            // Parse regions
            if (caps.contains("regions") && caps["regions"].is_array())
            {
                for (const auto &reg : caps["regions"])
                {
                    RegionDef def;
                    def.name = reg.value("name", "");
                    def.logic = reg.value("logic", "");
                    def.requires_option = reg.value("requires_option", "");

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
                    def.region = loc.value("region", "");
                    def.logic = loc.value("logic", "");
                    def.requires_option = loc.value("requires_option", "");

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

        APLogger::get()->log(LogLevel::Debug, "APModRegistry",
                             "Parsed " + manifest.mod_id + ": " +
                                 std::to_string(manifest.items.size()) + " items, " +
                                 std::to_string(manifest.locations.size()) + " locs, " +
                                 std::to_string(manifest.regions.size()) + " regions, " +
                                 std::to_string(manifest.goals.size()) + " goals, " +
                                 std::to_string(manifest.item_overrides.size()) + " overrides");

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

    // Process includes before parsing: resolve external logic files and merge
    // into the capabilities JSON so parse_manifest() sees final merged data.
    try
    {
        nlohmann::json j = nlohmann::json::parse(content);

        if (j.contains("capabilities") && j["capabilities"].is_object())
        {
            auto &caps = j["capabilities"];

            if (caps.contains("include") && caps["include"].is_array())
            {
                auto manifest_dir = file_path.parent_path();
                std::set<std::string> visited;
                resolve_includes(caps, manifest_dir, visited);
            }
        }

        // Serialize back and parse
        return parse_manifest(j.dump());
    }
    catch (const nlohmann::json::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APModRegistry",
                             "JSON error processing includes for " + file_path.string() + ": " + e.what());
        return std::nullopt;
    }
}

// =============================================================================
// Include Resolution
// =============================================================================

void APModRegistry::resolve_includes(nlohmann::json &caps,
                                     const std::filesystem::path &manifest_dir,
                                     std::set<std::string> &visited) const
{
    if (!caps.contains("include") || !caps["include"].is_array())
        return;

    auto includes = caps["include"];
    caps.erase("include"); // Remove include key — final JSON has no references

    // Build Templates/<game>/logic/ path for shared logic fallback
    std::filesystem::path shared_logic_dir;
    auto framework_folder = APPathUtil::get()->find_framework_mod_folder();
    if (framework_folder)
    {
        std::string game_name = APConfig::get()->get_game_name();
        shared_logic_dir = *framework_folder / "Templates" / game_name / "logic";
    }

    for (const auto &inc : includes)
    {
        if (!inc.is_string())
            continue;

        std::string include_path_str = inc.get<std::string>();

        // Resolve path: local first, then shared logic
        std::filesystem::path resolved;
        auto local_path = manifest_dir / include_path_str;
        if (APPathUtil::get()->file_exists(local_path))
        {
            resolved = local_path;
        }
        else if (!shared_logic_dir.empty())
        {
            auto shared_path = shared_logic_dir / include_path_str;
            if (APPathUtil::get()->file_exists(shared_path))
            {
                resolved = shared_path;
            }
        }

        if (resolved.empty())
        {
            APLogger::get()->log(LogLevel::Warn, "APModRegistry",
                                 "Include file not found: " + include_path_str);
            continue;
        }

        // Circular include detection
        std::string canonical = resolved.string();
        if (visited.count(canonical) > 0)
        {
            APLogger::get()->log(LogLevel::Error, "APModRegistry",
                                 "Circular include detected: " + canonical);
            continue;
        }
        visited.insert(canonical);

        // Load the included file
        std::string file_content = APPathUtil::get()->read_file(resolved);
        if (file_content.empty())
        {
            APLogger::get()->log(LogLevel::Warn, "APModRegistry",
                                 "Include file empty or unreadable: " + canonical);
            continue;
        }

        try
        {
            nlohmann::json included = nlohmann::json::parse(file_content);

            // Recurse: included files can also have includes
            if (included.contains("include") && included["include"].is_array())
            {
                resolve_includes(included, resolved.parent_path(), visited);
            }

            // Merge arrays: included content first, then manifest's own
            if (included.contains("regions") && included["regions"].is_array())
            {
                nlohmann::json merged = included["regions"];
                if (caps.contains("regions") && caps["regions"].is_array())
                {
                    for (const auto &r : caps["regions"])
                        merged.push_back(r);
                }
                caps["regions"] = merged;
            }

            if (included.contains("locations") && included["locations"].is_array())
            {
                nlohmann::json merged = included["locations"];
                if (caps.contains("locations") && caps["locations"].is_array())
                {
                    for (const auto &l : caps["locations"])
                        merged.push_back(l);
                }
                caps["locations"] = merged;
            }

            if (included.contains("items") && included["items"].is_array())
            {
                nlohmann::json merged = included["items"];
                if (caps.contains("items") && caps["items"].is_array())
                {
                    for (const auto &i : caps["items"])
                        merged.push_back(i);
                }
                caps["items"] = merged;
            }

            APLogger::get()->log(LogLevel::Debug, "APModRegistry",
                                 "Resolved include: " + include_path_str + " -> " + canonical);
        }
        catch (const nlohmann::json::exception &e)
        {
            APLogger::get()->log(LogLevel::Error, "APModRegistry",
                                 "Failed to parse include " + canonical + ": " + e.what());
        }
    }
}

} // namespace ap