#include "ap_vocabulary.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <algorithm>
#include <nlohmann/json.hpp>
#include <regex>
#include <set>

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
            // Vocabulary regions are just name strings
            std::string name;
            if (reg.is_string())
            {
                name = reg.get<std::string>();
            }
            else if (reg.is_object())
            {
                name = reg.value("name", "");
            }

            if (!name.empty())
            {
                VocabRegion vr;
                vr.name = name;
                regions_[name] = vr;
            }
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
            // Vocabulary items are just name strings
            std::string name;
            if (item.is_string())
            {
                name = item.get<std::string>();
            }
            else if (item.is_object())
            {
                name = item.value("name", "");
            }

            if (!name.empty())
            {
                VocabItem vi;
                vi.name = name;
                items_[name] = vi;
            }
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
            // Vocabulary locations are just name strings
            std::string name;
            if (loc.is_string())
            {
                name = loc.get<std::string>();
            }
            else if (loc.is_object())
            {
                name = loc.value("name", "");
            }

            if (!name.empty())
            {
                VocabLocation vl;
                vl.name = name;
                locations_[name] = vl;
            }
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

    // Validate item and region references inside logic strings
    // Extract (Item: NAME) and (Can Access: REGION) tokens from logic expressions
    std::set<std::string> logic_item_refs;
    std::set<std::string> logic_region_refs;

    auto extract_logic_refs = [&](const std::string &logic)
    {
        if (logic.empty())
            return;

        // Extract (Item: NAME) and (Item: NAME : COUNT)
        static const std::regex item_re(R"(\(Item:\s*([^:)]+?)(?:\s*:\s*\d+)?\s*\))");
        auto it_begin = std::sregex_iterator(logic.begin(), logic.end(), item_re);
        auto it_end = std::sregex_iterator();
        for (auto it = it_begin; it != it_end; ++it)
        {
            std::string name = (*it)[1].str();
            // Trim whitespace
            name.erase(0, name.find_first_not_of(" \t"));
            name.erase(name.find_last_not_of(" \t") + 1);
            if (!name.empty())
                logic_item_refs.insert(name);
        }

        // Extract (Can Access: REGION)
        static const std::regex region_re(R"(\(Can Access:\s*([^)]+?)\s*\))");
        auto rg_begin = std::sregex_iterator(logic.begin(), logic.end(), region_re);
        auto rg_end = std::sregex_iterator();
        for (auto rg = rg_begin; rg != rg_end; ++rg)
        {
            std::string name = (*rg)[1].str();
            name.erase(0, name.find_first_not_of(" \t"));
            name.erase(name.find_last_not_of(" \t") + 1);
            if (!name.empty())
                logic_region_refs.insert(name);
        }
    };

    // Collect logic strings from regions and locations
    for (const auto &reg : manifest.regions)
        extract_logic_refs(reg.logic);
    for (const auto &loc : manifest.locations)
        extract_logic_refs(loc.logic);

    // Validate item references from logic
    if (!items_.empty())
    {
        for (const auto &ref : logic_item_refs)
        {
            if (items_.find(ref) == items_.end())
            {
                std::string suggestion = find_closest_match(ref, item_names);
                std::string msg = "[Vocabulary] Mod '" + manifest.mod_id +
                                  "': logic references item '" + ref + "' not in vocabulary";
                if (!suggestion.empty())
                    msg += " (did you mean '" + suggestion + "'?)";
                warnings.push_back(msg);
            }
        }
    }

    // Validate region references from logic
    if (!regions_.empty())
    {
        for (const auto &ref : logic_region_refs)
        {
            if (regions_.find(ref) == regions_.end())
            {
                std::string suggestion = find_closest_match(ref, region_names);
                std::string msg = "[Vocabulary] Mod '" + manifest.mod_id +
                                  "': logic references region '" + ref + "' not in vocabulary";
                if (!suggestion.empty())
                    msg += " (did you mean '" + suggestion + "'?)";
                warnings.push_back(msg);
            }
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