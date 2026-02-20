#pragma once

/**
 * @file ap_vocabulary.h
 * @brief Game vocabulary loading and validation for the AP Framework.
 *
 * Loads optional vocabulary files from Templates/<game_name>/:
 * - Regions.json: canonical region names
 * - Items.json: canonical item names
 * - Locations.json: canonical location names
 *
 * Vocabulary is naming conventions only — no logic, no requirements.
 * Validation is opt-in per manifest (vocab_validation: true).
 * When enabled, the framework validates manifest names against vocabulary
 * with fuzzy suggestions for typos.
 *
 * Vocabulary is advisory, not enforced — validation produces warnings, not errors.
 */

#include "ap_types.h"

#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace ap
{

// =============================================================================
// Vocabulary Entry Types (name-only, no logic)
// =============================================================================

struct VocabRegion
{
    std::string name;
};

struct VocabItem
{
    std::string name;
};

struct VocabLocation
{
    std::string name;
};

// =============================================================================
// APVocabulary
// =============================================================================

class APVocabulary
{
  public:
    /**
     * @brief Load vocabulary files from a game-specific templates directory.
     * @param templates_dir Path to Templates/<game_name>/ directory.
     * @return true if at least one vocabulary file was loaded.
     *
     * Loads Regions.json, Items.json, Locations.json if they exist.
     * Missing files are silently skipped (vocabulary is optional).
     */
    bool load(const std::filesystem::path &templates_dir);

    /**
     * @brief Check if any vocabulary was loaded.
     */
    bool is_loaded() const;

    /**
     * @brief Validate manifest names against vocabulary.
     * @param manifest Manifest to validate.
     * @return Vector of warning messages. Empty if all names are valid or no vocabulary loaded.
     *
     * Only runs if manifest has vocab_validation=true.
     * Extracts item/region names from logic strings for validation.
     */
    std::vector<std::string> validate_manifest(const Manifest &manifest) const;

    // Getters for vocabulary entries
    std::vector<VocabRegion> get_regions() const;
    std::vector<VocabItem> get_items() const;
    std::vector<VocabLocation> get_locations() const;

  private:
    bool load_regions(const std::filesystem::path &path);
    bool load_items(const std::filesystem::path &path);
    bool load_locations(const std::filesystem::path &path);

    /**
     * @brief Find the closest match for a name in a set of vocabulary names.
     * @param name Name to find a match for.
     * @param vocab_names Set of valid vocabulary names.
     * @return Closest match, or empty string if no close match found.
     */
    static std::string find_closest_match(const std::string &name,
                                          const std::vector<std::string> &vocab_names);

    /**
     * @brief Compute Levenshtein edit distance between two strings.
     */
    static size_t levenshtein_distance(const std::string &a, const std::string &b);

    std::map<std::string, VocabRegion> regions_;
    std::map<std::string, VocabItem> items_;
    std::map<std::string, VocabLocation> locations_;
    bool loaded_ = false;
};

} // namespace ap