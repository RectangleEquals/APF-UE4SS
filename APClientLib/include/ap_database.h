#pragma once

#include <string>
#include <vector>
#include <unordered_map>

// Forward declare to avoid including sqlite3.h in header
struct sqlite3;

namespace ap::client
{

/// Simple SQLite database wrapper for runtime queries from Lua.
/// Follows Meyers singleton pattern (no pass-key needed — internal to APClientLib).
class APDatabase
{
  public:
    static APDatabase *get();

    APDatabase(const APDatabase &) = delete;
    APDatabase &operator=(const APDatabase &) = delete;

    /// Open a SQLite database file. Closes any previously open database.
    /// @param path Absolute or relative path to .db file.
    /// @return true on success.
    bool open(const std::string &path);

    /// Execute a SQL query and return results as a vector of row maps.
    /// Each row is a map of column_name -> string_value.
    /// @param sql SQL query string.
    /// @return Vector of rows, empty on error or no results.
    std::vector<std::unordered_map<std::string, std::string>> query(const std::string &sql);

    /// Close the currently open database.
    void close();

    /// Check if a database is currently open.
    bool is_open() const;

  private:
    APDatabase() = default;
    ~APDatabase();

    sqlite3 *db_ = nullptr;
};

} // namespace ap::client
