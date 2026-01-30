#include "ap_config.h"
#include "ap_path_util.h"

#include <fstream>
#include <nlohmann/json.hpp>

namespace ap
{

APConfig &APConfig::instance()
{
    static APConfig instance;
    return instance;
}

bool APConfig::load(const std::filesystem::path &config_path)
{
    // Start with defaults
    reset_to_defaults();

    // Try to read the file
    std::string content = APPathUtil::read_file(config_path);
    if (content.empty())
    {
        // File doesn't exist or is empty - use defaults
        loaded_ = true;
        loaded_path_ = config_path;
        return true;
    }

    try
    {
        nlohmann::json j = nlohmann::json::parse(content);

        // Top-level fields
        if (j.contains("game_name"))
            config_.game_name = j["game_name"].get<std::string>();
        if (j.contains("id_base"))
            config_.id_base = j["id_base"].get<int64_t>();
        if (j.contains("log_level"))
        {
            std::string level = j["log_level"].get<std::string>();
            if (level == "trace")
                config_.log_level = LogLevel::Trace;
            else if (level == "debug")
                config_.log_level = LogLevel::Debug;
            else if (level == "info")
                config_.log_level = LogLevel::Info;
            else if (level == "warn")
                config_.log_level = LogLevel::Warn;
            else if (level == "error")
                config_.log_level = LogLevel::Error;
            else if (level == "fatal")
                config_.log_level = LogLevel::Fatal;
        }
        if (j.contains("log_file"))
            config_.log_file = j["log_file"].get<std::string>();
        if (j.contains("log_to_console"))
            config_.log_to_console = j["log_to_console"].get<bool>();

        // Timeouts section
        if (j.contains("timeouts") && j["timeouts"].is_object())
        {
            const auto &t = j["timeouts"];
            if (t.contains("priority_registration_ms"))
                config_.timeouts.priority_registration_ms = t["priority_registration_ms"].get<int>();
            if (t.contains("registration_ms"))
                config_.timeouts.registration_ms = t["registration_ms"].get<int>();
            if (t.contains("connection_ms"))
                config_.timeouts.connection_ms = t["connection_ms"].get<int>();
            if (t.contains("ipc_message_ms"))
                config_.timeouts.ipc_message_ms = t["ipc_message_ms"].get<int>();
            if (t.contains("action_execution_ms"))
                config_.timeouts.action_execution_ms = t["action_execution_ms"].get<int>();
        }

        // Retry section
        if (j.contains("retry") && j["retry"].is_object())
        {
            const auto &r = j["retry"];
            if (r.contains("max_retries"))
                config_.retry.max_retries = r["max_retries"].get<int>();
            if (r.contains("initial_delay_ms"))
                config_.retry.initial_delay_ms = r["initial_delay_ms"].get<int>();
            if (r.contains("backoff_multiplier"))
                config_.retry.backoff_multiplier = r["backoff_multiplier"].get<double>();
            if (r.contains("max_delay_ms"))
                config_.retry.max_delay_ms = r["max_delay_ms"].get<int>();
        }

        // Threading section
        if (j.contains("threading") && j["threading"].is_object())
        {
            const auto &th = j["threading"];
            if (th.contains("polling_interval_ms"))
                config_.threading.polling_interval_ms = th["polling_interval_ms"].get<int>();
            if (th.contains("ipc_poll_interval_ms"))
                config_.threading.ipc_poll_interval_ms = th["ipc_poll_interval_ms"].get<int>();
            if (th.contains("queue_max_size"))
                config_.threading.queue_max_size = th["queue_max_size"].get<int>();
            if (th.contains("shutdown_timeout_ms"))
                config_.threading.shutdown_timeout_ms = th["shutdown_timeout_ms"].get<int>();
        }

        // AP Server section
        if (j.contains("ap_server") && j["ap_server"].is_object())
        {
            const auto &ap = j["ap_server"];
            if (ap.contains("server"))
                config_.ap_server.server = ap["server"].get<std::string>();
            if (ap.contains("port"))
                config_.ap_server.port = ap["port"].get<int>();
            if (ap.contains("slot_name"))
                config_.ap_server.slot_name = ap["slot_name"].get<std::string>();
            if (ap.contains("password"))
                config_.ap_server.password = ap["password"].get<std::string>();
            if (ap.contains("auto_reconnect"))
                config_.ap_server.auto_reconnect = ap["auto_reconnect"].get<bool>();
        }

        loaded_ = true;
        loaded_path_ = config_path;
        return true;
    }
    catch (const nlohmann::json::exception &)
    {
        // JSON parsing failed - use defaults
        reset_to_defaults();
        loaded_ = true;
        loaded_path_ = config_path;
        return false;
    }
}

bool APConfig::load_default()
{
    return load(APPathUtil::get_config_path());
}

bool APConfig::save(const std::filesystem::path &config_path) const
{
    nlohmann::json j;

    // Top-level fields
    j["id_base"] = config_.id_base;
    j["game_name"] = config_.game_name;

    // Convert log level to string
    switch (config_.log_level)
    {
    case LogLevel::Trace:
        j["log_level"] = "trace";
        break;
    case LogLevel::Debug:
        j["log_level"] = "debug";
        break;
    case LogLevel::Info:
        j["log_level"] = "info";
        break;
    case LogLevel::Warn:
        j["log_level"] = "warn";
        break;
    case LogLevel::Error:
        j["log_level"] = "error";
        break;
    case LogLevel::Fatal:
        j["log_level"] = "fatal";
        break;
    }

    j["log_file"] = config_.log_file;
    j["log_to_console"] = config_.log_to_console;

    // Timeouts section
    j["timeouts"] = {{"priority_registration_ms", config_.timeouts.priority_registration_ms},
                     {"registration_ms", config_.timeouts.registration_ms},
                     {"connection_ms", config_.timeouts.connection_ms},
                     {"ipc_message_ms", config_.timeouts.ipc_message_ms},
                     {"action_execution_ms", config_.timeouts.action_execution_ms}};

    // Retry section
    j["retry"] = {{"max_retries", config_.retry.max_retries},
                  {"initial_delay_ms", config_.retry.initial_delay_ms},
                  {"backoff_multiplier", config_.retry.backoff_multiplier},
                  {"max_delay_ms", config_.retry.max_delay_ms}};

    // Threading section
    j["threading"] = {{"polling_interval_ms", config_.threading.polling_interval_ms},
                      {"ipc_poll_interval_ms", config_.threading.ipc_poll_interval_ms},
                      {"queue_max_size", config_.threading.queue_max_size},
                      {"shutdown_timeout_ms", config_.threading.shutdown_timeout_ms}};

    // AP Server section
    j["ap_server"] = {{"server", config_.ap_server.server},
                      {"port", config_.ap_server.port},
                      {"slot_name", config_.ap_server.slot_name},
                      {"password", config_.ap_server.password},
                      {"auto_reconnect", config_.ap_server.auto_reconnect}};

    // Write with pretty printing
    std::string content = j.dump(2);
    return APPathUtil::write_file(config_path, content);
}

bool APConfig::save_default() const
{
    return save(APPathUtil::get_config_path());
}

void APConfig::reset_to_defaults()
{
    config_ = FrameworkConfig{};
}

} // namespace ap
