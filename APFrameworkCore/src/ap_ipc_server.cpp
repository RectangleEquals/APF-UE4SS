#include "ap_ipc_server.h"
#include "ap_ipc_server_types.h"
#include "ap_logger.h"

#include <atomic>
#include <chrono>
#include <mutex>
#include <nlohmann/json.hpp>
#include <thread>
#include <unordered_map>
#include <vector>

namespace ap
{

// =============================================================================
// Pass-Key + Meyers Singleton
// =============================================================================

APIPCServer *APIPCServer::get()
{
    static std::unique_ptr<APIPCServer> instance = std::make_unique<APIPCServer>(ConstructorKey{});
    return instance.get();
}

APIPCServer::APIPCServer(ConstructorKey)
{
    // Default initialization
}

APIPCServer::~APIPCServer()
{
    stop();
}

// =============================================================================
// Windows Implementation
// =============================================================================

#ifdef _WIN32

bool APIPCServer::start(const std::string &game_name)
{
    if (running_)
    {
        return false;
    }

    pipe_name_ = "\\\\.\\pipe\\APFramework_" + game_name;
    running_ = true;
    stop_token_.reset();

    // Start the I/O thread and write thread
    io_thread_ = std::thread(&APIPCServer::io_thread_func, this);
    write_thread_ = std::thread(&APIPCServer::write_thread_func, this);

    APLogger::get()->log(LogLevel::Info, "APIPCServer", "IPC Server started on: " + pipe_name_);
    return true;
}

void APIPCServer::stop()
{
    if (!running_)
    {
        return;
    }

    running_ = false;
    stop_token_.request_stop();

    // Signal all client events to wake up I/O thread
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        for (auto &[id, conn] : clients_)
        {
            if (conn->overlapped.hEvent)
            {
                SetEvent(conn->overlapped.hEvent);
            }
        }
    }

    // Wake and join write thread first (releases shared_ptr refs before clients_.clear())
    write_cv_.notify_all();
    if (write_thread_.joinable())
    {
        write_thread_.join();
    }

    // Wait for I/O thread
    if (io_thread_.joinable())
    {
        io_thread_.join();
    }

    // Close all client connections
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        clients_.clear();
    }

    APLogger::get()->log(LogLevel::Info, "APIPCServer", "IPC Server stopped");
}

bool APIPCServer::is_running() const
{
    return running_;
}

bool APIPCServer::send_message(const std::string &client_id, const IPCMessage &message)
{
    std::lock_guard<std::mutex> lock(clients_mutex_);

    auto it = clients_.find(client_id);
    if (it == clients_.end())
    {
        return false;
    }

    return queue_write(it->second.get(), message);
}

void APIPCServer::broadcast(const IPCMessage &message)
{
    std::lock_guard<std::mutex> lock(clients_mutex_);

    for (auto &[id, conn] : clients_)
    {
        queue_write(conn.get(), message);
    }
}

void APIPCServer::broadcast_except(const IPCMessage &message, const std::string &exclude_client_id)
{
    std::lock_guard<std::mutex> lock(clients_mutex_);

    for (auto &[id, conn] : clients_)
    {
        if (id != exclude_client_id)
        {
            queue_write(conn.get(), message);
        }
    }
}

std::vector<IPCMessage> APIPCServer::get_pending_messages()
{
    return incoming_queue_.pop_all();
}

void APIPCServer::poll()
{
    auto messages = incoming_queue_.pop_all();
    for (const auto &msg : messages)
    {
        if (message_handler_)
        {
            message_handler_(msg.source, msg);
        }
    }
}

std::vector<std::string> APIPCServer::get_connected_clients() const
{
    std::lock_guard<std::mutex> lock(clients_mutex_);
    std::vector<std::string> result;
    result.reserve(clients_.size());
    for (const auto &[id, conn] : clients_)
    {
        result.push_back(id);
    }
    return result;
}

bool APIPCServer::is_client_connected(const std::string &client_id) const
{
    std::lock_guard<std::mutex> lock(clients_mutex_);
    return clients_.find(client_id) != clients_.end();
}

size_t APIPCServer::get_client_count() const
{
    std::lock_guard<std::mutex> lock(clients_mutex_);
    return clients_.size();
}

void APIPCServer::set_message_handler(MessageHandler handler)
{
    message_handler_ = std::move(handler);
}

void APIPCServer::set_connect_handler(ConnectHandler handler)
{
    connect_handler_ = std::move(handler);
}

void APIPCServer::set_disconnect_handler(DisconnectHandler handler)
{
    disconnect_handler_ = std::move(handler);
}

void APIPCServer::set_timeout(int timeout_ms)
{
    timeout_ms_ = timeout_ms;
}

void APIPCServer::set_retry_policy(int max_retries, int retry_delay_ms)
{
    max_retries_ = max_retries;
    retry_delay_ms_ = retry_delay_ms;
}

std::string APIPCServer::get_pipe_name() const
{
    return pipe_name_;
}

// =============================================================================
// Private Methods (Windows)
// =============================================================================

void APIPCServer::io_thread_func()
{
    APLogger::set_thread_name("IPC-Server");

    // Create the initial listening pipe
    HANDLE listen_pipe = static_cast<HANDLE>(create_pipe_instance());
    if (listen_pipe == INVALID_HANDLE_VALUE)
    {
        APLogger::get()->log(LogLevel::Error, "APIPCServer",
                             "Failed to create named pipe: " + std::to_string(GetLastError()));
        return;
    }

    OVERLAPPED connect_overlapped = {};
    connect_overlapped.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);

    // Start listening for connections
    ConnectNamedPipe(listen_pipe, &connect_overlapped);
    DWORD connect_error = GetLastError();
    if (connect_error != ERROR_IO_PENDING && connect_error != ERROR_PIPE_CONNECTED)
    {
        APLogger::get()->log(LogLevel::Error, "APIPCServer",
                             "ConnectNamedPipe failed: " + std::to_string(connect_error));
        CloseHandle(listen_pipe);
        CloseHandle(connect_overlapped.hEvent);
        return;
    }

    while (running_ && !stop_token_.stop_requested())
    {
        // Build wait handles array
        std::vector<HANDLE> wait_handles;
        wait_handles.push_back(connect_overlapped.hEvent);

        std::vector<ClientConnection *> wait_clients;
        {
            std::lock_guard<std::mutex> lock(clients_mutex_);
            for (auto &[id, conn] : clients_)
            {
                if (conn->overlapped.hEvent)
                {
                    wait_handles.push_back(conn->overlapped.hEvent);
                    wait_clients.push_back(conn.get());
                }
            }
        }

        // Wait for any event
        DWORD result = WaitForMultipleObjects(static_cast<DWORD>(wait_handles.size()), wait_handles.data(), FALSE,
                                              100 // 100ms timeout for periodic checks
        );

        if (!running_ || stop_token_.stop_requested())
        {
            break;
        }

        if (result == WAIT_TIMEOUT)
        {
            continue;
        }

        if (result == WAIT_FAILED)
        {
            APLogger::get()->log(LogLevel::Error, "APIPCServer",
                                 "WaitForMultipleObjects failed: " + std::to_string(GetLastError()));
            continue;
        }

        DWORD index = result - WAIT_OBJECT_0;

        if (index == 0)
        {
            // New client connection
            DWORD bytes_transferred;
            if (GetOverlappedResult(listen_pipe, &connect_overlapped, &bytes_transferred, FALSE))
            {
                // Handle new connection inline
                auto conn = std::make_shared<ClientConnection>();
                conn->pipe = listen_pipe;

                // Generate temporary client ID until registration
                static std::atomic<int> next_id{1};
                std::string temp_id = "client_" + std::to_string(next_id++);
                conn->client_id = temp_id;

                // Start reading from this client
                start_read(conn.get());

                {
                    std::lock_guard<std::mutex> lock(clients_mutex_);
                    clients_[temp_id] = std::move(conn);
                }

                APLogger::get()->log(LogLevel::Debug, "APIPCServer", "New client connected: " + temp_id);

                if (connect_handler_)
                {
                    connect_handler_(temp_id);
                }

                // Create new pipe for next connection
                listen_pipe = static_cast<HANDLE>(create_pipe_instance());
                if (listen_pipe != INVALID_HANDLE_VALUE)
                {
                    ResetEvent(connect_overlapped.hEvent);
                    ConnectNamedPipe(listen_pipe, &connect_overlapped);
                }
            }
        }
        else if (index > 0 && index <= wait_clients.size())
        {
            // Client I/O completed
            ClientConnection *conn = wait_clients[index - 1];
            handle_read_complete(conn, 0); // Will get actual bytes from GetOverlappedResult
        }
    }

    // Cleanup
    CancelIo(listen_pipe);
    CloseHandle(listen_pipe);
    CloseHandle(connect_overlapped.hEvent);
}

void APIPCServer::write_thread_func()
{
    APLogger::set_thread_name("IPC-Write");

    while (running_)
    {
        {
            std::unique_lock<std::mutex> lk(write_cv_mutex_);
            write_cv_.wait_for(lk, std::chrono::milliseconds(10));
        }

        // Snapshot connections that have pending writes (brief lock — no I/O under lock)
        std::vector<std::shared_ptr<ClientConnection>> to_drain;
        {
            std::lock_guard<std::mutex> lock(clients_mutex_);
            for (auto &[id, conn] : clients_)
            {
                std::lock_guard<std::mutex> qlock(*conn->send_mutex);
                if (!conn->send_queue.empty())
                    to_drain.push_back(conn); // shared_ptr copy keeps conn alive
            }
        }

        // Drain each connection without holding clients_mutex_
        for (auto &conn : to_drain)
        {
            while (!conn->pending_disconnect)
            {
                std::vector<char> buffer;
                {
                    std::lock_guard<std::mutex> qlock(*conn->send_mutex);
                    if (conn->send_queue.empty())
                        break;
                    buffer = std::move(conn->send_queue.front());
                    conn->send_queue.pop();
                }

                DWORD written = 0;
                BOOL ok = WriteFile(conn->pipe, buffer.data(),
                                    static_cast<DWORD>(buffer.size()), &written, nullptr);
                if (!ok || written != static_cast<DWORD>(buffer.size()))
                {
                    conn->pending_disconnect = true;
                    break;
                }
            }
        }
    }
}

void *APIPCServer::create_pipe_instance()
{
    return CreateNamedPipeA(pipe_name_.c_str(), PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
                            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT, PIPE_UNLIMITED_INSTANCES,
                            65536,  // Output buffer size
                            65536,  // Input buffer size
                            0,      // Default timeout
                            nullptr // Default security
    );
}

bool APIPCServer::queue_write(ClientConnection *conn, const IPCMessage &message)
{
    if (conn->pending_disconnect)
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

        // Enqueue for the write thread — never blocks the calling thread
        {
            std::lock_guard<std::mutex> qlock(*conn->send_mutex);
            conn->send_queue.push(std::move(buffer));
        }
        write_cv_.notify_one();
        return true;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APIPCServer",
                             "Failed to queue message for " + conn->client_id + ": " + e.what());
        return false;
    }
}

void APIPCServer::handle_read_complete(ClientConnection *conn, unsigned long bytes_read)
{
    DWORD bytes_transferred;
    BOOL success = GetOverlappedResult(conn->pipe, &conn->overlapped, &bytes_transferred, FALSE);

    if (!success)
    {
        DWORD error = GetLastError();
        if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED)
        {
            disconnect_client(conn->client_id);
        }
        return;
    }

    if (conn->reading)
    {
        conn->reading = false;
        if (bytes_transferred > 0)
        {
            // Process received data
            if (bytes_transferred >= 4)
            {
                // Read 4-byte length prefix (little-endian)
                uint32_t msg_length;
                memcpy(&msg_length, conn->read_buffer.data(), 4);

                if (bytes_transferred >= 4 + msg_length)
                {
                    // Parse JSON message
                    try
                    {
                        std::string json_str(conn->read_buffer.data() + 4, conn->read_buffer.data() + 4 + msg_length);

                        nlohmann::json j = nlohmann::json::parse(json_str);
                        IPCMessage msg = IPCMessage::from_json(j);

                        // Handle registration to update client_id
                        if (msg.type == IPCMessageType::REGISTER)
                        {
                            std::string new_id = msg.payload.value("mod_id", "");
                            if (!new_id.empty() && new_id != conn->client_id)
                            {
                                std::lock_guard<std::mutex> lock(clients_mutex_);
                                auto it = clients_.find(conn->client_id);
                                if (it != clients_.end())
                                {
                                    auto moved_conn = std::move(it->second);
                                    clients_.erase(it);
                                    moved_conn->client_id = new_id;
                                    msg.source = new_id;
                                    clients_[new_id] = std::move(moved_conn);
                                }
                            }
                        }

                        msg.source = conn->client_id;
                        incoming_queue_.push(std::move(msg));
                    }
                    catch (const nlohmann::json::exception &e)
                    {
                        APLogger::get()->log(LogLevel::Error, "APIPCServer",
                                             "JSON parse error from " + conn->client_id + ": " + e.what());
                    }
                }
            }
        }
        // Start next read
        start_read(conn);
    }
    else if (conn->writing)
    {
        conn->writing = false;
        // Write completed, can send more if queued
    }
}

void APIPCServer::handle_write_complete(ClientConnection *conn)
{
    conn->writing = false;
}

void APIPCServer::start_read(ClientConnection *conn)
{
    if (conn->reading || conn->pending_disconnect)
    {
        return;
    }

    ResetEvent(conn->overlapped.hEvent);
    conn->reading = true;

    BOOL success = ReadFile(conn->pipe, conn->read_buffer.data(), static_cast<DWORD>(conn->read_buffer.size()), nullptr,
                            &conn->overlapped);

    if (!success)
    {
        DWORD error = GetLastError();
        if (error != ERROR_IO_PENDING)
        {
            conn->reading = false;
            if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED)
            {
                conn->pending_disconnect = true;
            }
        }
    }
}

void APIPCServer::disconnect_client(const std::string &client_id)
{
    std::shared_ptr<ClientConnection> conn;
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        auto it = clients_.find(client_id);
        if (it != clients_.end())
        {
            conn = std::move(it->second);
            clients_.erase(it);
        }
    }

    if (conn)
    {
        APLogger::get()->log(LogLevel::Debug, "APIPCServer", "Client disconnected: " + client_id);

        if (disconnect_handler_)
        {
            disconnect_handler_(client_id);
        }
    }
}

#else // Non-Windows stub

bool APIPCServer::start(const std::string &)
{
    return false;
}

void APIPCServer::stop()
{
}

bool APIPCServer::is_running() const
{
    return false;
}

bool APIPCServer::send_message(const std::string &, const IPCMessage &)
{
    return false;
}

void APIPCServer::broadcast(const IPCMessage &)
{
}

void APIPCServer::broadcast_except(const IPCMessage &, const std::string &)
{
}

std::vector<IPCMessage> APIPCServer::get_pending_messages()
{
    return {};
}

void APIPCServer::poll()
{
}

std::vector<std::string> APIPCServer::get_connected_clients() const
{
    return {};
}

bool APIPCServer::is_client_connected(const std::string &) const
{
    return false;
}

size_t APIPCServer::get_client_count() const
{
    return 0;
}

void APIPCServer::set_message_handler(MessageHandler)
{
}

void APIPCServer::set_connect_handler(ConnectHandler)
{
}

void APIPCServer::set_disconnect_handler(DisconnectHandler)
{
}

void APIPCServer::set_timeout(int)
{
}

void APIPCServer::set_retry_policy(int, int)
{
}

std::string APIPCServer::get_pipe_name() const
{
    return "";
}

#endif // _WIN32

} // namespace ap
