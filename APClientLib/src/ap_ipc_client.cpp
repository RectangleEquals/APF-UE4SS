#include "ap_ipc_client.h"
#include "ap_logger.h"

#include <chrono>
#include <memory>
#include <thread>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APIPCClient *APIPCClient::get()
{
    static std::unique_ptr<APIPCClient> instance = std::make_unique<APIPCClient>(ConstructorKey{});
    return instance.get();
}

APIPCClient::APIPCClient(ConstructorKey)
#ifdef _WIN32
    : read_buffer_(65536)
#endif
{
    // Default initialization
}

APIPCClient::~APIPCClient()
{
    disconnect();
}

// =============================================================================
// Connection
// =============================================================================

#ifdef _WIN32

bool APIPCClient::connect(const std::string &game_name)
{
    if (connected_)
    {
        return true;
    }

    pipe_name_ = "\\\\.\\pipe\\APFramework_" + game_name;
    APLogger::get()->log(LogLevel::Trace, "APIPCClient", "Connecting to pipe: " + pipe_name_);

    // Try to connect to the named pipe
    for (int attempt = 0; attempt < 3; ++attempt)
    {
        pipe_ = CreateFileA(pipe_name_.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                            FILE_FLAG_OVERLAPPED, nullptr);

        if (pipe_ != INVALID_HANDLE_VALUE)
        {
            break;
        }

        DWORD error = GetLastError();
        if (error == ERROR_PIPE_BUSY)
        {
            // Wait for the pipe to become available
            if (!WaitNamedPipeA(pipe_name_.c_str(), timeout_ms_))
            {
                continue;
            }
        }
        else
        {
            // Other error, wait briefly and retry
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    if (pipe_ == INVALID_HANDLE_VALUE)
    {
        APLogger::get()->log(LogLevel::Error, "APIPCClient", "Failed to connect to pipe: " + pipe_name_);
        return false;
    }

    // Set pipe to message mode
    DWORD mode = PIPE_READMODE_MESSAGE;
    if (!SetNamedPipeHandleState(pipe_, &mode, nullptr, nullptr))
    {
        CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
        return false;
    }

    // Create overlapped event for async reads
    read_overlapped_.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    if (read_overlapped_.hEvent == nullptr)
    {
        CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
        return false;
    }

    connected_ = true;
    APLogger::get()->log(LogLevel::Debug, "APIPCClient", "Connected to pipe: " + pipe_name_);

    // Start async read
    start_read();

    if (connect_handler_)
    {
        connect_handler_();
    }

    return true;
}

void APIPCClient::disconnect()
{
    if (!connected_)
    {
        return;
    }

    APLogger::get()->log(LogLevel::Debug, "APIPCClient", "Disconnecting from pipe: " + pipe_name_);
    connected_ = false;

    if (read_overlapped_.hEvent != nullptr)
    {
        CancelIo(pipe_);
        CloseHandle(read_overlapped_.hEvent);
        read_overlapped_.hEvent = nullptr;
    }

    if (pipe_ != INVALID_HANDLE_VALUE)
    {
        CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }

    if (disconnect_handler_)
    {
        disconnect_handler_();
    }
}

bool APIPCClient::is_connected() const
{
    return connected_;
}

bool APIPCClient::send_message(const IPCMessage &message)
{
    if (!connected_)
    {
        return false;
    }

    try
    {
        std::string json_str = message.to_json().dump();

        // Build length-prefixed message
        uint32_t length = static_cast<uint32_t>(json_str.size());
        std::vector<char> buffer(4 + length);
        memcpy(buffer.data(), &length, 4);
        memcpy(buffer.data() + 4, json_str.data(), length);

        DWORD bytes_written;
        BOOL success = WriteFile(pipe_, buffer.data(), static_cast<DWORD>(buffer.size()), &bytes_written,
                                 nullptr // Synchronous write
        );

        if (!success || bytes_written != buffer.size())
        {
            handle_disconnect();
            return false;
        }

        return true;
    }
    catch (const std::exception &)
    {
        return false;
    }
}

void APIPCClient::poll()
{
    if (!connected_)
    {
        if (auto_reconnect_ && !pipe_name_.empty())
        {
            // Try to reconnect
            std::string game_name = pipe_name_.substr(pipe_name_.rfind('_') + 1);
            connect(game_name);
        }
        return;
    }

    // Check if async read completed
    check_read_completion();

    // Dispatch received messages
    std::vector<IPCMessage> messages;
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        while (!message_queue_.empty())
        {
            messages.push_back(std::move(message_queue_.front()));
            message_queue_.pop();
        }
    }

    for (const auto &msg : messages)
    {
        if (message_handler_)
        {
            message_handler_(msg);
        }
    }
}

std::vector<IPCMessage> APIPCClient::get_pending_messages()
{
    check_read_completion();

    std::vector<IPCMessage> messages;
    std::lock_guard<std::mutex> lock(queue_mutex_);
    while (!message_queue_.empty())
    {
        messages.push_back(std::move(message_queue_.front()));
        message_queue_.pop();
    }
    return messages;
}

std::optional<IPCMessage> APIPCClient::try_receive()
{
    check_read_completion();

    std::lock_guard<std::mutex> lock(queue_mutex_);
    if (message_queue_.empty())
    {
        return std::nullopt;
    }

    auto msg = std::move(message_queue_.front());
    message_queue_.pop();
    return msg;
}

void APIPCClient::start_read()
{
    if (!connected_ || reading_)
    {
        return;
    }

    ResetEvent(read_overlapped_.hEvent);
    reading_ = true;

    BOOL success =
        ReadFile(pipe_, read_buffer_.data(), static_cast<DWORD>(read_buffer_.size()), nullptr, &read_overlapped_);

    if (!success)
    {
        DWORD error = GetLastError();
        if (error != ERROR_IO_PENDING)
        {
            reading_ = false;
            if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED)
            {
                handle_disconnect();
            }
        }
    }
}

void APIPCClient::check_read_completion()
{
    if (!reading_ || !connected_)
    {
        return;
    }

    // Non-blocking check
    DWORD wait_result = WaitForSingleObject(read_overlapped_.hEvent, 0);
    if (wait_result != WAIT_OBJECT_0)
    {
        return; // Read not complete yet
    }

    DWORD bytes_read;
    if (!GetOverlappedResult(pipe_, &read_overlapped_, &bytes_read, FALSE))
    {
        DWORD error = GetLastError();
        reading_ = false;
        if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED)
        {
            handle_disconnect();
        }
        return;
    }

    reading_ = false;

    if (bytes_read > 0)
    {
        process_received_data(bytes_read);
    }

    // Start next read
    start_read();
}

void APIPCClient::process_received_data(DWORD bytes_received)
{
    if (bytes_received < 4)
    {
        return; // Need at least length prefix
    }

    // Read 4-byte length prefix (little-endian)
    uint32_t msg_length;
    memcpy(&msg_length, read_buffer_.data(), 4);

    if (bytes_received < 4 + msg_length)
    {
        return; // Incomplete message
    }

    // Parse JSON message
    try
    {
        std::string json_str(read_buffer_.data() + 4, read_buffer_.data() + 4 + msg_length);

        nlohmann::json j = nlohmann::json::parse(json_str);
        IPCMessage msg = IPCMessage::from_json(j);

        std::lock_guard<std::mutex> lock(queue_mutex_);
        message_queue_.push(std::move(msg));
    }
    catch (const nlohmann::json::exception &)
    {
        // Ignore malformed messages
    }
}

void APIPCClient::handle_disconnect()
{
    if (!connected_)
    {
        return;
    }

    APLogger::get()->log(LogLevel::Debug, "APIPCClient", "Pipe disconnected (broken pipe): " + pipe_name_);
    connected_ = false;
    reading_ = false;

    if (read_overlapped_.hEvent != nullptr)
    {
        CancelIo(pipe_);
    }

    if (disconnect_handler_)
    {
        disconnect_handler_();
    }
}

#else // Non-Windows stub

bool APIPCClient::connect(const std::string &)
{
    return false;
}

void APIPCClient::disconnect()
{
}

bool APIPCClient::is_connected() const
{
    return false;
}

bool APIPCClient::send_message(const IPCMessage &)
{
    return false;
}

void APIPCClient::poll()
{
}

std::vector<IPCMessage> APIPCClient::get_pending_messages()
{
    return {};
}

std::optional<IPCMessage> APIPCClient::try_receive()
{
    return std::nullopt;
}

#endif // _WIN32

// =============================================================================
// Callbacks
// =============================================================================

void APIPCClient::set_message_handler(MessageHandler handler)
{
    message_handler_ = std::move(handler);
}

void APIPCClient::set_connect_handler(ConnectHandler handler)
{
    connect_handler_ = std::move(handler);
}

void APIPCClient::set_disconnect_handler(DisconnectHandler handler)
{
    disconnect_handler_ = std::move(handler);
}

// =============================================================================
// Configuration
// =============================================================================

void APIPCClient::set_auto_reconnect(bool enabled)
{
    auto_reconnect_ = enabled;
}

void APIPCClient::set_timeout(int timeout_ms)
{
    timeout_ms_ = timeout_ms;
}

std::string APIPCClient::get_pipe_name() const
{
    return pipe_name_;
}

} // namespace ap