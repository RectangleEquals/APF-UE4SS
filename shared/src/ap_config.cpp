#include "ap_config.h"
#include "ap_path_util.h"

#include <fstream>
#include <nlohmann/json.hpp>

namespace ap
{

// =============================================================================
// Singleton Implementation
// =============================================================================

APConfig::APConfig(ConstructorKey)
{
    reset_to_defaults();
}

APConfig *APConfig::get()
{
    static std::unique_ptr<APConfig> instance = std::make_unique<APConfig>(ConstructorKey{});
    return instance.get();
}

// =============================================================================
// Loading
// =============================================================================

bool APConfig::load(const std::filesystem::path &config_path)
{
    // Start with defaults
    reset_to_defaults();

    // Try to read the file
    std::string content = APPathUtil::get()->read_file(config_path);
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
        {
            config_.game_name = j["game_name"].get<std::string>();
        }
        // id_base is intentionally not read from config — it is a hardcoded framework
        // constant (6942067) that players should never need to adjust. Per-player ID
        // uniqueness is handled by the Python apworld via per-slot offsets in slot_data.

        // Logging section (nested)
        if (j.contains("logging") && j["logging"].is_object())
        {
            const auto &log = j["logging"];
            if (log.contains("level"))
            {
                std::string level = log["level"].get<std::string>();
                config_.logging.level = log_level_from_string(level);
            }
            if (log.contains("file"))
            {
                config_.logging.file = log["file"].get<std::string>();
            }
            if (log.contains("console"))
            {
                config_.logging.console = log["console"].get<bool>();
            }
            if (log.contains("append"))
            {
                config_.logging.append = log["append"].get<bool>();
            }
        }

        // AP Server section
        if (j.contains("ap_server") && j["ap_server"].is_object())
        {
            const auto &ap = j["ap_server"];
            if (ap.contains("host"))
            {
                config_.ap_server.host = ap["host"].get<std::string>();
            }
            if (ap.contains("port"))
            {
                config_.ap_server.port = ap["port"].get<int>();
            }
            if (ap.contains("slot_name"))
            {
                config_.ap_server.slot_name = ap["slot_name"].get<std::string>();
            }
            if (ap.contains("password"))
            {
                config_.ap_server.password = ap["password"].get<std::string>();
            }
            if (ap.contains("auto_reconnect"))
            {
                config_.ap_server.auto_reconnect = ap["auto_reconnect"].get<bool>();
            }
        }

        // Timeouts section
        if (j.contains("timeouts") && j["timeouts"].is_object())
        {
            const auto &t = j["timeouts"];
            if (t.contains("priority_registration_ms"))
            {
                config_.timeouts.priority_registration_ms = t["priority_registration_ms"].get<int>();
            }
            if (t.contains("registration_ms"))
            {
                config_.timeouts.registration_ms = t["registration_ms"].get<int>();
            }
            if (t.contains("connection_ms"))
            {
                config_.timeouts.connection_ms = t["connection_ms"].get<int>();
            }
            if (t.contains("ipc_message_ms"))
            {
                config_.timeouts.ipc_message_ms = t["ipc_message_ms"].get<int>();
            }
            if (t.contains("action_execution_ms"))
            {
                config_.timeouts.action_execution_ms = t["action_execution_ms"].get<int>();
            }

            // Retry sub-section
            if (t.contains("retry") && t["retry"].is_object())
            {
                const auto &r = t["retry"];
                if (r.contains("max_connection"))
                {
                    config_.timeouts.retry.max_connection = r["max_connection"].get<int>();
                }
                if (r.contains("max_ipc_message"))
                {
                    config_.timeouts.retry.max_ipc_message = r["max_ipc_message"].get<int>();
                }
                if (r.contains("initial_delay_ms"))
                {
                    config_.timeouts.retry.initial_delay_ms = r["initial_delay_ms"].get<int>();
                }
                if (r.contains("backoff_multiplier"))
                {
                    config_.timeouts.retry.backoff_multiplier = r["backoff_multiplier"].get<double>();
                }
                if (r.contains("max_delay_ms"))
                {
                    config_.timeouts.retry.max_delay_ms = r["max_delay_ms"].get<int>();
                }
            }
        }

        // Threading section
        if (j.contains("threading") && j["threading"].is_object())
        {
            const auto &th = j["threading"];
            if (th.contains("polling_interval_ms"))
            {
                config_.threading.polling_interval_ms = th["polling_interval_ms"].get<int>();
            }
            if (th.contains("ipc_poll_interval_ms"))
            {
                config_.threading.ipc_poll_interval_ms = th["ipc_poll_interval_ms"].get<int>();
            }
            if (th.contains("queue_max_size"))
            {
                config_.threading.queue_max_size = th["queue_max_size"].get<int>();
            }
            if (th.contains("shutdown_timeout_ms"))
            {
                config_.threading.shutdown_timeout_ms = th["shutdown_timeout_ms"].get<int>();
            }
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
    return load(APPathUtil::get()->get_config_path());
}

bool APConfig::save(const std::filesystem::path &config_path) const
{
    nlohmann::json j;

    // Top-level fields
    j["game_name"] = config_.game_name;
    // id_base intentionally omitted — hardcoded constant, not user-configurable

    // Logging section (nested)
    j["logging"] = {{"level", log_level_to_string(config_.logging.level)},
                    {"file", config_.logging.file},
                    {"console", config_.logging.console},
                    {"append", config_.logging.append}};

    // AP Server section
    j["ap_server"] = {{"host", config_.ap_server.host},
                      {"port", config_.ap_server.port},
                      {"slot_name", config_.ap_server.slot_name},
                      {"password", config_.ap_server.password},
                      {"auto_reconnect", config_.ap_server.auto_reconnect}};

    // Timeouts section with nested retry
    j["timeouts"] = {{"priority_registration_ms", config_.timeouts.priority_registration_ms},
                     {"registration_ms", config_.timeouts.registration_ms},
                     {"connection_ms", config_.timeouts.connection_ms},
                     {"ipc_message_ms", config_.timeouts.ipc_message_ms},
                     {"action_execution_ms", config_.timeouts.action_execution_ms},
                     {"retry",
                      {{"max_connection", config_.timeouts.retry.max_connection},
                       {"max_ipc_message", config_.timeouts.retry.max_ipc_message},
                       {"initial_delay_ms", config_.timeouts.retry.initial_delay_ms},
                       {"backoff_multiplier", config_.timeouts.retry.backoff_multiplier},
                       {"max_delay_ms", config_.timeouts.retry.max_delay_ms}}}};

    // Threading section
    j["threading"] = {{"polling_interval_ms", config_.threading.polling_interval_ms},
                      {"ipc_poll_interval_ms", config_.threading.ipc_poll_interval_ms},
                      {"queue_max_size", config_.threading.queue_max_size},
                      {"shutdown_timeout_ms", config_.threading.shutdown_timeout_ms}};

    // Write with pretty printing
    std::string content = j.dump(2);
    return APPathUtil::get()->write_file(config_path, content);
}

bool APConfig::save_default() const
{
    return save(APPathUtil::get()->get_config_path());
}

void APConfig::reset_to_defaults()
{
    config_ = FrameworkConfig{};
}

} // namespace ap