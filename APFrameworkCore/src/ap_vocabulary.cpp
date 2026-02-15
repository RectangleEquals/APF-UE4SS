#include "ap_vocabulary.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <algorithm>
#include <nlohmann/json.hpp>

namespace ap
{

// =============================================================================
// Loading
// =============================================================================

bool APVocabulary::load(const std::filesystem::path &templates_dir)
{
    regions_.clear();
    items_.clear();
    locations_.clear();
    loaded_ = false;

    bool any = false;

    auto regions_path = templates_dir / "Regions.json";
    if (load_regions(regions_path))
    {
        any = true;
        APLogger::get()->log(LogLevel::Debug, "Vocabulary",
                             "Loaded " + std::to_string(regions_.size()) + " regions from " + regions_path.string());
    }

    auto items_path = templates_dir / "Items.json";
    if (load_items(items_path))
    {
        any = true;
        APLogger::get()->log(LogLevel::Debug, "Vocabulary",
                             "Loaded " + std::to_string(items_.size()) + " items from " + items_path.string());
    }

    auto locations_path = templates_dir / "Locations.json";
    if (load_locations(locations_path))
    {
        any = true;
        APLogger::get()->log(LogLevel::Debug, "Vocabulary",
                             "Loaded " + std::to_string(locations_.size()) + " locations from " + locations_path.string());
    }

    loaded_ = any;
    return any;
}

bool APVocabulary::is_loaded() const
{
    return loaded_;
}

bool APVocabulary::load_regions(const std::filesystem::path &path)
{
    if (!APPathUtil::get()->file_exists(path))
        return false;

    std::string content = APPathUtil::get()->read_file(path);
    if (content.empty())
        return false;

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);
        if (!j.contains("regions") || !j["regions"].is_array())
            return false;

        for (const auto &reg : j["regions"])
        {
            VocabRegion vr;
            vr.name = reg.value("name", "");
            if (vr.name.empty())
                continue;

            if (reg.contains("requires") && reg["requires"].is_array())
            {
                for (const auto &r : reg["requires"])
                    vr.requires_all.push_back(r.get<std::string>());
            }
            if (reg.contains("requires_any") && reg["requires_any"].is_array())
            {
                for (const auto &r : reg["requires_any"])
                    vr.requires_any.push_back(r.get<std::string>());
            }
            if (reg.contains("requires_count") && reg["requires_count"].is_array())
            {
                for (const auto &rc : reg["requires_count"])
                {
                    CountRequirement cr;
                    cr.item = rc.value("item", "");
                    cr.count = rc.value("count", 1);
                    if (!cr.item.empty())
                        vr.requires_count.push_back(cr);
                }
            }

            regions_[vr.name] = vr;
        }

        return !regions_.empty();
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Warn, "Vocabulary",
                             "Failed to parse " + path.string() + ": " + e.what());
        return false;
    }
}

bool APVocabulary::load_items(const std::filesystem::path &path)
{
    if (!APPathUtil::get()->file_exists(path))
        return false;

    std::string content = APPathUtil::get()->read_file(path);
    if (content.empty())
        return false;

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);
        if (!j.contains("items") || !j["items"].is_array())
            return false;

        for (const auto &item : j["items"])
        {
            VocabItem vi;
            vi.name = item.value("name", "");
            vi.type = item.value("type", "filler");
            if (vi.name.empty())
                continue;

            items_[vi.name] = vi;
        }

        return !items_.empty();
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Warn, "Vocabulary",
                             "Failed to parse " + path.string() + ": " + e.what());
        return false;
    }
}

bool APVocabulary::load_locations(const std::filesystem::path &path)
{
    if (!APPathUtil::get()->file_exists(path))
        return false;

    std::string content = APPathUtil::get()->read_file(path);
    if (content.empty())
        return false;

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);
        if (!j.contains("locations") || !j["locations"].is_array())
            return false;

        for (const auto &loc : j["locations"])
        {
            VocabLocation vl;
            vl.name = loc.value("name", "");
            vl.region = loc.value("region", "");
            if (vl.name.empty())
                continue;

            locations_[vl.name] = vl;
        }

        return !locations_.empty();
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Warn, "Vocabulary",
                             "Failed to parse " + path.string() + ": " + e.what());
        return false;
    }
}

// =============================================================================
// Validation
// =============================================================================

std::vector<std::string> APVocabulary::validate_manifest(const Manifest &manifest) const
{
    std::vector<std::string> warnings;

    if (!loaded_)
        return warnings;

    // Build vocabulary name lists for fuzzy matching
    std::vector<std::string> region_names;
    for (const auto &[name, _] : regions_)
        region_names.push_back(name);

    std::vector<std::string> item_names;
    for (const auto &[name, _] : items_)
        item_names.push_back(name);

    std::vector<std::string> location_names;
    for (const auto &[name, _] : locations_)
        location_names.push_back(name);

    // Validate region names
    if (!regions_.empty())
    {
        for (const auto &reg : manifest.regions)
        {
            if (reg.suppress_vocab_warning)
                continue;
            if (regions_.find(reg.name) == regions_.end())
            {
                std::string suggestion = find_closest_match(reg.name, region_names);
                std::string msg = "[Vocabulary] Mod '" + manifest.mod_id + "': region '" + reg.name +
                                  "' not in vocabulary";
                if (!suggestion.empty())
                    msg += " (did you mean '" + suggestion + "'?)";
                warnings.push_back(msg);
            }
        }
    }

    // Validate location names
    if (!locations_.empty())
    {
        for (const auto &loc : manifest.locations)
        {
            if (loc.suppress_vocab_warning)
                continue;
            if (locations_.find(loc.name) == locations_.end())
            {
                std::string suggestion = find_closest_match(loc.name, location_names);
                std::string msg = "[Vocabulary] Mod '" + manifest.mod_id + "': location '" + loc.name +
                                  "' not in vocabulary";
                if (!suggestion.empty())
                    msg += " (did you mean '" + suggestion + "'?)";
                warnings.push_back(msg);
            }
        }
    }

    // Validate item names
    if (!items_.empty())
    {
        for (const auto &item : manifest.items)
        {
            if (item.suppress_vocab_warning)
                continue;
            if (items_.find(item.name) == items_.end())
            {
                std::string suggestion = find_closest_match(item.name, item_names);
                std::string msg = "[Vocabulary] Mod '" + manifest.mod_id + "': item '" + item.name +
                                  "' not in vocabulary";
                if (!suggestion.empty())
                    msg += " (did you mean '" + suggestion + "'?)";
                warnings.push_back(msg);
            }
        }
    }

    // Also validate item references in requirements
    if (!items_.empty())
    {
        auto validate_item_refs = [&](const std::vector<std::string> &refs, const std::string &context)
        {
            for (const auto &ref : refs)
            {
                if (items_.find(ref) == items_.end())
                {
                    std::string suggestion = find_closest_match(ref, item_names);
                    std::string msg = "[Vocabulary] Mod '" + manifest.mod_id + "': " + context +
                                      " references item '" + ref + "' not in vocabulary";
                    if (!suggestion.empty())
                        msg += " (did you mean '" + suggestion + "'?)";
                    warnings.push_back(msg);
                }
            }
        };

        for (const auto &loc : manifest.locations)
        {
            validate_item_refs(loc.requires_all, "location '" + loc.name + "'");
            validate_item_refs(loc.requires_any, "location '" + loc.name + "'");
            for (const auto &rc : loc.requires_count)
            {
                if (items_.find(rc.item) == items_.end())
                {
                    std::string suggestion = find_closest_match(rc.item, item_names);
                    std::string msg = "[Vocabulary] Mod '" + manifest.mod_id + "': location '" +
                                      loc.name + "' requires_count references item '" + rc.item +
                                      "' not in vocabulary";
                    if (!suggestion.empty())
                        msg += " (did you mean '" + suggestion + "'?)";
                    warnings.push_back(msg);
                }
            }
        }
    }

    return warnings;
}

std::vector<std::string> APVocabulary::apply_region_defaults(std::vector<RegionDef> &regions,
                                                             const std::vector<LocationOwnership> &locations,
                                                             const std::string &manifest_mod_id) const
{
    std::vector<std::string> warnings;

    if (!loaded_ || regions_.empty())
        return warnings;

    // Find region names used by locations that aren't already declared
    std::set<std::string> declared_regions;
    for (const auto &reg : regions)
        declared_regions.insert(reg.name);

    std::set<std::string> used_regions;
    for (const auto &loc : locations)
    {
        if (!loc.region.empty())
            used_regions.insert(loc.region);
    }

    // For each used region not declared by any manifest
    for (const auto &region_name : used_regions)
    {
        if (declared_regions.count(region_name) > 0)
            continue;

        auto vocab_it = regions_.find(region_name);
        if (vocab_it == regions_.end())
            continue;

        // Apply vocabulary defaults
        RegionDef inherited;
        inherited.name = vocab_it->second.name;
        inherited.requires_all = vocab_it->second.requires_all;
        inherited.requires_any = vocab_it->second.requires_any;
        inherited.requires_count = vocab_it->second.requires_count;
        regions.push_back(inherited);

        // Build description of inherited requirements for warning
        std::string req_desc;
        if (!inherited.requires_all.empty())
        {
            req_desc += "requires: [";
            for (size_t i = 0; i < inherited.requires_all.size(); ++i)
            {
                if (i > 0)
                    req_desc += ", ";
                req_desc += "\"" + inherited.requires_all[i] + "\"";
            }
            req_desc += "]";
        }

        if (!req_desc.empty())
        {
            warnings.push_back(
                "[Vocabulary] Mod '" + manifest_mod_id + "' uses region '" + region_name +
                "' without declaring requirements - inheriting defaults from Regions.json (" +
                req_desc + "). Consider declaring requirements explicitly.");
        }
    }

    return warnings;
}

// =============================================================================
// Getters
// =============================================================================

std::vector<VocabRegion> APVocabulary::get_regions() const
{
    std::vector<VocabRegion> result;
    result.reserve(regions_.size());
    for (const auto &[_, vr] : regions_)
        result.push_back(vr);
    return result;
}

std::vector<VocabItem> APVocabulary::get_items() const
{
    std::vector<VocabItem> result;
    result.reserve(items_.size());
    for (const auto &[_, vi] : items_)
        result.push_back(vi);
    return result;
}

std::vector<VocabLocation> APVocabulary::get_locations() const
{
    std::vector<VocabLocation> result;
    result.reserve(locations_.size());
    for (const auto &[_, vl] : locations_)
        result.push_back(vl);
    return result;
}

// =============================================================================
// Fuzzy Matching
// =============================================================================

std::string APVocabulary::find_closest_match(const std::string &name,
                                              const std::vector<std::string> &vocab_names)
{
    if (vocab_names.empty())
        return "";

    std::string best_match;
    size_t best_distance = std::string::npos;

    // Maximum distance threshold: 40% of the name length or 3, whichever is larger
    size_t max_distance = std::max(static_cast<size_t>(3), name.size() * 2 / 5);

    for (const auto &candidate : vocab_names)
    {
        size_t dist = levenshtein_distance(name, candidate);
        if (dist < best_distance && dist <= max_distance)
        {
            best_distance = dist;
            best_match = candidate;
        }
    }

    return best_match;
}

size_t APVocabulary::levenshtein_distance(const std::string &a, const std::string &b)
{
    size_t m = a.size();
    size_t n = b.size();

    // Use two rows for space efficiency
    std::vector<size_t> prev(n + 1);
    std::vector<size_t> curr(n + 1);

    for (size_t j = 0; j <= n; ++j)
        prev[j] = j;

    for (size_t i = 1; i <= m; ++i)
    {
        curr[0] = i;
        for (size_t j = 1; j <= n; ++j)
        {
            size_t cost = (std::tolower(static_cast<unsigned char>(a[i - 1])) ==
                           std::tolower(static_cast<unsigned char>(b[j - 1])))
                              ? 0
                              : 1;
            curr[j] = std::min({prev[j] + 1,          // deletion
                                curr[j - 1] + 1,      // insertion
                                prev[j - 1] + cost});  // substitution
        }
        std::swap(prev, curr);
    }

    return prev[n];
}

} // namespace ap
