#include "ap_version.h"

#include <charconv>
#include <sstream>

namespace ap
{

// =============================================================================
// SemVer
// =============================================================================

std::optional<SemVer> SemVer::parse(const std::string &str)
{
    if (str.empty())
        return std::nullopt;

    SemVer ver;
    const char *begin = str.c_str();
    const char *end = begin + str.size();

    // Parse major
    auto [ptr1, ec1] = std::from_chars(begin, end, ver.major);
    if (ec1 != std::errc{})
        return std::nullopt;

    if (ptr1 == end)
        return ver; // "1"

    if (*ptr1 != '.')
        return std::nullopt;

    // Parse minor
    auto [ptr2, ec2] = std::from_chars(ptr1 + 1, end, ver.minor);
    if (ec2 != std::errc{})
        return std::nullopt;

    if (ptr2 == end)
        return ver; // "1.2"

    if (*ptr2 != '.')
        return std::nullopt;

    // Parse patch
    auto [ptr3, ec3] = std::from_chars(ptr2 + 1, end, ver.patch);
    if (ec3 != std::errc{})
        return std::nullopt;

    // Reject trailing garbage (e.g. "1.2.3abc")
    if (ptr3 != end)
        return std::nullopt;

    return ver;
}

std::string SemVer::to_string() const
{
    return std::to_string(major) + "." + std::to_string(minor) + "." + std::to_string(patch);
}

// =============================================================================
// VersionConstraint
// =============================================================================

bool VersionConstraint::satisfied_by(const SemVer &candidate) const
{
    switch (op)
    {
    case Op::Eq:
        return candidate == version;
    case Op::Ne:
        return candidate != version;
    case Op::Lt:
        return candidate < version;
    case Op::Le:
        return candidate <= version;
    case Op::Gt:
        return candidate > version;
    case Op::Ge:
        return candidate >= version;
    }
    return false;
}

std::optional<VersionConstraint> VersionConstraint::parse(const std::string &str)
{
    if (str.empty())
        return std::nullopt;

    // Skip leading whitespace
    size_t pos = 0;
    while (pos < str.size() && str[pos] == ' ')
        ++pos;

    if (pos >= str.size())
        return std::nullopt;

    VersionConstraint vc;

    // Parse operator
    if (str.compare(pos, 2, ">=") == 0)
    {
        vc.op = Op::Ge;
        pos += 2;
    }
    else if (str.compare(pos, 2, "<=") == 0)
    {
        vc.op = Op::Le;
        pos += 2;
    }
    else if (str.compare(pos, 2, "!=") == 0)
    {
        vc.op = Op::Ne;
        pos += 2;
    }
    else if (str.compare(pos, 2, "==") == 0)
    {
        vc.op = Op::Eq;
        pos += 2;
    }
    else if (str[pos] == '>')
    {
        vc.op = Op::Gt;
        pos += 1;
    }
    else if (str[pos] == '<')
    {
        vc.op = Op::Lt;
        pos += 1;
    }
    else
    {
        // No operator — treat as exact match
        vc.op = Op::Eq;
    }

    // Skip whitespace between operator and version
    while (pos < str.size() && str[pos] == ' ')
        ++pos;

    // Trim trailing whitespace
    size_t end = str.size();
    while (end > pos && str[end - 1] == ' ')
        --end;

    auto ver = SemVer::parse(str.substr(pos, end - pos));
    if (!ver)
        return std::nullopt;

    vc.version = *ver;
    return vc;
}

std::string VersionConstraint::to_string() const
{
    std::string op_str;
    switch (op)
    {
    case Op::Eq:
        op_str = "==";
        break;
    case Op::Ne:
        op_str = "!=";
        break;
    case Op::Lt:
        op_str = "<";
        break;
    case Op::Le:
        op_str = "<=";
        break;
    case Op::Gt:
        op_str = ">";
        break;
    case Op::Ge:
        op_str = ">=";
        break;
    }
    return op_str + version.to_string();
}

// =============================================================================
// Dependency
// =============================================================================

Dependency Dependency::parse(const std::string &dep_string)
{
    Dependency dep;

    // Find opening parenthesis for version constraints
    auto paren_pos = dep_string.find('(');
    if (paren_pos == std::string::npos)
    {
        // No constraints — just a mod_id
        dep.mod_id = dep_string;

        // Trim trailing whitespace from mod_id
        while (!dep.mod_id.empty() && dep.mod_id.back() == ' ')
            dep.mod_id.pop_back();

        return dep;
    }

    // Extract mod_id (everything before the parenthesis, trimmed)
    dep.mod_id = dep_string.substr(0, paren_pos);
    while (!dep.mod_id.empty() && dep.mod_id.back() == ' ')
        dep.mod_id.pop_back();

    // Find closing parenthesis
    auto close_paren = dep_string.find(')', paren_pos);
    if (close_paren == std::string::npos)
        return dep; // Malformed — return with mod_id only

    // Extract constraint string: everything between ( and )
    std::string constraints_str = dep_string.substr(paren_pos + 1, close_paren - paren_pos - 1);

    // Split by comma and parse each constraint
    std::istringstream ss(constraints_str);
    std::string token;
    while (std::getline(ss, token, ','))
    {
        auto vc = VersionConstraint::parse(token);
        if (vc)
        {
            dep.constraints.push_back(*vc);
        }
    }

    return dep;
}

bool Dependency::version_satisfied(const std::string &version_str) const
{
    if (constraints.empty())
        return true; // No constraints — any version accepted

    auto ver = SemVer::parse(version_str);
    if (!ver)
        return false; // Can't parse version — treat as not satisfied

    for (const auto &constraint : constraints)
    {
        if (!constraint.satisfied_by(*ver))
            return false; // All constraints must be satisfied
    }

    return true;
}

std::string Dependency::constraint_string() const
{
    if (constraints.empty())
        return "";

    std::string result;
    for (size_t i = 0; i < constraints.size(); ++i)
    {
        if (i > 0)
            result += ", ";
        result += constraints[i].to_string();
    }
    return result;
}

} // namespace ap
