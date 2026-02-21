#pragma once

/**
 * @file ap_version.h
 * @brief Semantic versioning and dependency constraint utilities.
 *
 * Used by both `depends` and `incompatible` manifest fields:
 * - depends:       "mod_id (>=1.0.0, <2.0.0)" — constraints specify required versions
 * - incompatible:  "mod_id" (all versions) or "mod_id (>=2.0.0)" — constraints specify conflicting versions
 */

#include <optional>
#include <string>
#include <vector>

namespace ap
{

// =============================================================================
// Semantic Version
// =============================================================================

struct SemVer
{
    int major = 0;
    int minor = 0;
    int patch = 0;

    /// Parse a version string like "1.2.3" or "1.2" or "1".
    /// Returns nullopt on failure.
    static std::optional<SemVer> parse(const std::string &str);

    /// C++20 spaceship operator for all comparisons.
    auto operator<=>(const SemVer &) const = default;

    /// Format as "major.minor.patch".
    std::string to_string() const;
};

// =============================================================================
// Version Constraint (single comparison)
// =============================================================================

struct VersionConstraint
{
    enum class Op
    {
        Eq,  // ==
        Ne,  // !=
        Lt,  // <
        Le,  // <=
        Gt,  // >
        Ge   // >=
    };

    Op op = Op::Ge;
    SemVer version;

    /// Check if a candidate version satisfies this constraint.
    bool satisfied_by(const SemVer &candidate) const;

    /// Parse a single constraint like ">=1.0.0" or "<2.0.0" or "==1.5.0".
    /// Returns nullopt on failure.
    static std::optional<VersionConstraint> parse(const std::string &str);

    /// Format as ">=1.0.0" etc.
    std::string to_string() const;
};

// =============================================================================
// Dependency (mod_id + optional version constraints)
// =============================================================================

/// Parsed from strings like:
///   "some.mod"                     — any version
///   "some.mod (>=1.0.0)"           — minimum version
///   "some.mod (>=1.0.0, <2.0.0)"  — version range
struct Dependency
{
    std::string mod_id;
    std::vector<VersionConstraint> constraints; ///< Empty = any version

    /// Parse a dependency string. Extracts mod_id and optional parenthesized constraints.
    static Dependency parse(const std::string &dep_string);

    /// Check if a version string satisfies all constraints.
    /// Returns true if constraints are empty (any version accepted).
    bool version_satisfied(const std::string &version_str) const;

    /// Format the constraints portion, e.g. ">=1.0.0, <2.0.0".
    /// Returns empty string if no constraints.
    std::string constraint_string() const;
};

} // namespace ap
