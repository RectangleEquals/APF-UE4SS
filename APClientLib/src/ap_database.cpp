#include "ap_database.h"
#include "ap_logger.h"

#include <sqlite3.h>

namespace ap::client
{

APDatabase *APDatabase::get()
{
    static APDatabase instance;
    return &instance;
}

APDatabase::~APDatabase()
{
    close();
}

bool APDatabase::open(const std::string &path)
{
    // Close any existing connection
    close();

    int rc = sqlite3_open_v2(path.c_str(), &db_,
                             SQLITE_OPEN_READONLY, nullptr);
    if (rc != SQLITE_OK)
    {
        std::string err = db_ ? sqlite3_errmsg(db_) : "unknown error";
        APLogger::get()->log(LogLevel::Error, "APDatabase",
                             "Failed to open database: " + path + " (" + err + ")");
        if (db_)
        {
            sqlite3_close(db_);
            db_ = nullptr;
        }
        return false;
    }

    APLogger::get()->log(LogLevel::Info, "APDatabase",
                         "Opened database: " + path);
    return true;
}

std::vector<std::unordered_map<std::string, std::string>>
APDatabase::query(const std::string &sql)
{
    std::vector<std::unordered_map<std::string, std::string>> results;

    if (!db_)
    {
        APLogger::get()->log(LogLevel::Error, "APDatabase",
                             "No database open");
        return results;
    }

    sqlite3_stmt *stmt = nullptr;
    int rc = sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK)
    {
        APLogger::get()->log(LogLevel::Error, "APDatabase",
                             "SQL prepare failed: " + std::string(sqlite3_errmsg(db_)));
        return results;
    }

    int col_count = sqlite3_column_count(stmt);

    while (sqlite3_step(stmt) == SQLITE_ROW)
    {
        std::unordered_map<std::string, std::string> row;
        for (int i = 0; i < col_count; ++i)
        {
            const char *col_name = sqlite3_column_name(stmt, i);
            const char *col_text =
                reinterpret_cast<const char *>(sqlite3_column_text(stmt, i));

            row[col_name ? col_name : ""]
                = col_text ? col_text : "";
        }
        results.push_back(std::move(row));
    }

    sqlite3_finalize(stmt);

    APLogger::get()->log(LogLevel::Debug, "APDatabase",
                         "Query returned " + std::to_string(results.size()) + " rows");
    APLogger::get()->log(LogLevel::Trace, "APDatabase", "SQL: " + sql);

    return results;
}

void APDatabase::close()
{
    if (db_)
    {
        sqlite3_close(db_);
        db_ = nullptr;
        APLogger::get()->log(LogLevel::Info, "APDatabase",
                             "Database closed");
    }
}

bool APDatabase::is_open() const
{
    return db_ != nullptr;
}

} // namespace ap::client
