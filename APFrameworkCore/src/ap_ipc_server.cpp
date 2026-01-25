#include "ap_ipc_server.h"
#include "ap_logger.h"

#include <thread>
#include <mutex>
#include <atomic>
#include <vector>
#include <unordered_map>
#include <nlohmann/json.hpp>

#ifdef _WIN32
#include <Windows.h>
#endif

namespace ap {

// =============================================================================
// Implementation Details
// =============================================================================

#ifdef _WIN32

/**
 * @brief Represents a single client connection.
 */
struct ClientConnection {
    HANDLE pipe = INVALID_HANDLE_VALUE;
    OVERLAPPED overlapped = {};
    std::string client_id;
    std::vector<char> read_buffer;
    std::vector<char> write_buffer;
    bool reading = false;
    bool writing = false;
    bool pending_disconnect = false;

    ClientConnection() : read_buffer(65536), write_buffer(65536) {
        overlapped.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    }

    ~ClientConnection() {
        if (overlapped.hEvent != nullptr) {
            CloseHandle(overlapped.hEvent);
        }
        if (pipe != INVALID_HANDLE_VALUE) {
            DisconnectNamedPipe(pipe);
            CloseHandle(pipe);
        }
    }
};

class APIPCServer::Impl {
public:
    Impl() = default;
    ~Impl() { stop(); }

    bool start(const std::string& game_name) {
        if (running_) {
            return false;
        }

        pipe_name_ = "\\\\.\\pipe\\APFramework_" + game_name;
        running_ = true;
        stop_token_.reset();

        // Start the I/O thread
        io_thread_ = std::thread(&Impl::io_thread_func, this);

        APLogger::instance().log(LogLevel::Info,
            "IPC Server started on: " + pipe_name_);
        return true;
    }

    void stop() {
        if (!running_) {
            return;
        }

        running_ = false;
        stop_token_.request_stop();

        // Signal all client events to wake up I/O thread
        {
            std::lock_guard<std::mutex> lock(clients_mutex_);
            for (auto& [id, conn] : clients_) {
                if (conn->overlapped.hEvent) {
                    SetEvent(conn->overlapped.hEvent);
                }
            }
        }

        // Wait for I/O thread
        if (io_thread_.joinable()) {
            io_thread_.join();
        }

        // Close all client connections
        {
            std::lock_guard<std::mutex> lock(clients_mutex_);
            clients_.clear();
        }

        APLogger::instance().log(LogLevel::Info, "IPC Server stopped");
    }

    bool is_running() const {
        return running_;
    }

    bool send_message(const std::string& client_id, const IPCMessage& message) {
        std::lock_guard<std::mutex> lock(clients_mutex_);

        auto it = clients_.find(client_id);
        if (it == clients_.end()) {
            return false;
        }

        return queue_write(it->second.get(), message);
    }

    void broadcast(const IPCMessage& message) {
        std::lock_guard<std::mutex> lock(clients_mutex_);

        for (auto& [id, conn] : clients_) {
            queue_write(conn.get(), message);
        }
    }

    void broadcast_except(const IPCMessage& message, const std::string& exclude_client_id) {
        std::lock_guard<std::mutex> lock(clients_mutex_);

        for (auto& [id, conn] : clients_) {
            if (id != exclude_client_id) {
                queue_write(conn.get(), message);
            }
        }
    }

    std::vector<IPCMessage> get_pending_messages() {
        return incoming_queue_.pop_all();
    }

    void poll() {
        auto messages = incoming_queue_.pop_all();
        for (const auto& msg : messages) {
            if (message_handler_) {
                message_handler_(msg.source, msg);
            }
        }
    }

    std::vector<std::string> get_connected_clients() const {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        std::vector<std::string> result;
        result.reserve(clients_.size());
        for (const auto& [id, conn] : clients_) {
            result.push_back(id);
        }
        return result;
    }

    bool is_client_connected(const std::string& client_id) const {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        return clients_.find(client_id) != clients_.end();
    }

    size_t get_client_count() const {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        return clients_.size();
    }

    void set_message_handler(MessageHandler handler) {
        message_handler_ = std::move(handler);
    }

    void set_connect_handler(ConnectHandler handler) {
        connect_handler_ = std::move(handler);
    }

    void set_disconnect_handler(DisconnectHandler handler) {
        disconnect_handler_ = std::move(handler);
    }

    void set_timeout(int timeout_ms) {
        timeout_ms_ = timeout_ms;
    }

    void set_retry_policy(int max_retries, int retry_delay_ms) {
        max_retries_ = max_retries;
        retry_delay_ms_ = retry_delay_ms;
    }

    std::string get_pipe_name() const {
        return pipe_name_;
    }

private:
    void io_thread_func() {
        APLogger::set_thread_name("IPC-Server");

        // Create the initial listening pipe
        HANDLE listen_pipe = create_pipe_instance();
        if (listen_pipe == INVALID_HANDLE_VALUE) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to create named pipe: " + std::to_string(GetLastError()));
            return;
        }

        OVERLAPPED connect_overlapped = {};
        connect_overlapped.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);

        // Start listening for connections
        ConnectNamedPipe(listen_pipe, &connect_overlapped);
        DWORD connect_error = GetLastError();
        if (connect_error != ERROR_IO_PENDING && connect_error != ERROR_PIPE_CONNECTED) {
            APLogger::instance().log(LogLevel::Error,
                "ConnectNamedPipe failed: " + std::to_string(connect_error));
            CloseHandle(listen_pipe);
            CloseHandle(connect_overlapped.hEvent);
            return;
        }

        while (running_ && !stop_token_.stop_requested()) {
            // Build wait handles array
            std::vector<HANDLE> wait_handles;
            wait_handles.push_back(connect_overlapped.hEvent);

            std::vector<ClientConnection*> wait_clients;
            {
                std::lock_guard<std::mutex> lock(clients_mutex_);
                for (auto& [id, conn] : clients_) {
                    if (conn->overlapped.hEvent) {
                        wait_handles.push_back(conn->overlapped.hEvent);
                        wait_clients.push_back(conn.get());
                    }
                }
            }

            // Wait for any event
            DWORD result = WaitForMultipleObjects(
                static_cast<DWORD>(wait_handles.size()),
                wait_handles.data(),
                FALSE,
                100  // 100ms timeout for periodic checks
            );

            if (!running_ || stop_token_.stop_requested()) {
                break;
            }

            if (result == WAIT_TIMEOUT) {
                continue;
            }

            if (result == WAIT_FAILED) {
                APLogger::instance().log(LogLevel::Error,
                    "WaitForMultipleObjects failed: " + std::to_string(GetLastError()));
                continue;
            }

            DWORD index = result - WAIT_OBJECT_0;

            if (index == 0) {
                // New client connection
                DWORD bytes_transferred;
                if (GetOverlappedResult(listen_pipe, &connect_overlapped, &bytes_transferred, FALSE)) {
                    handle_new_connection(listen_pipe);

                    // Create new pipe for next connection
                    listen_pipe = create_pipe_instance();
                    if (listen_pipe != INVALID_HANDLE_VALUE) {
                        ResetEvent(connect_overlapped.hEvent);
                        ConnectNamedPipe(listen_pipe, &connect_overlapped);
                    }
                }
            } else if (index > 0 && index <= wait_clients.size()) {
                // Client I/O completed
                ClientConnection* conn = wait_clients[index - 1];
                handle_client_io(conn);
            }
        }

        // Cleanup
        CancelIo(listen_pipe);
        CloseHandle(listen_pipe);
        CloseHandle(connect_overlapped.hEvent);
    }

    HANDLE create_pipe_instance() {
        return CreateNamedPipeA(
            pipe_name_.c_str(),
            PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            65536,  // Output buffer size
            65536,  // Input buffer size
            0,      // Default timeout
            nullptr // Default security
        );
    }

    void handle_new_connection(HANDLE pipe) {
        auto conn = std::make_unique<ClientConnection>();
        conn->pipe = pipe;

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

        APLogger::instance().log(LogLevel::Debug,
            "New client connected: " + temp_id);

        if (connect_handler_) {
            connect_handler_(temp_id);
        }
    }

    void handle_client_io(ClientConnection* conn) {
        DWORD bytes_transferred;
        BOOL success = GetOverlappedResult(
            conn->pipe, &conn->overlapped, &bytes_transferred, FALSE);

        if (!success) {
            DWORD error = GetLastError();
            if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) {
                handle_client_disconnect(conn->client_id);
            }
            return;
        }

        if (conn->reading) {
            conn->reading = false;
            if (bytes_transferred > 0) {
                process_received_data(conn, bytes_transferred);
            }
            // Start next read
            start_read(conn);
        } else if (conn->writing) {
            conn->writing = false;
            // Write completed, can send more if queued
        }
    }

    void start_read(ClientConnection* conn) {
        if (conn->reading || conn->pending_disconnect) {
            return;
        }

        ResetEvent(conn->overlapped.hEvent);
        conn->reading = true;

        BOOL success = ReadFile(
            conn->pipe,
            conn->read_buffer.data(),
            static_cast<DWORD>(conn->read_buffer.size()),
            nullptr,
            &conn->overlapped
        );

        if (!success) {
            DWORD error = GetLastError();
            if (error != ERROR_IO_PENDING) {
                conn->reading = false;
                if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) {
                    conn->pending_disconnect = true;
                }
            }
        }
    }

    void process_received_data(ClientConnection* conn, DWORD bytes_received) {
        if (bytes_received < 4) {
            return;  // Need at least length prefix
        }

        // Read 4-byte length prefix (little-endian)
        uint32_t msg_length;
        memcpy(&msg_length, conn->read_buffer.data(), 4);

        if (bytes_received < 4 + msg_length) {
            APLogger::instance().log(LogLevel::Warn,
                "Incomplete message from " + conn->client_id);
            return;
        }

        // Parse JSON message
        try {
            std::string json_str(
                conn->read_buffer.data() + 4,
                conn->read_buffer.data() + 4 + msg_length
            );

            nlohmann::json j = nlohmann::json::parse(json_str);
            IPCMessage msg = IPCMessage::from_json(j);

            // Handle registration to update client_id
            if (msg.type == IPCMessageType::REGISTER) {
                std::string new_id = msg.payload.value("mod_id", "");
                if (!new_id.empty() && new_id != conn->client_id) {
                    std::lock_guard<std::mutex> lock(clients_mutex_);
                    auto it = clients_.find(conn->client_id);
                    if (it != clients_.end()) {
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

        } catch (const nlohmann::json::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "JSON parse error from " + conn->client_id + ": " + e.what());
        }
    }

    bool queue_write(ClientConnection* conn, const IPCMessage& message) {
        if (conn->pending_disconnect) {
            return false;
        }

        try {
            std::string json_str = message.to_json().dump();

            // Build length-prefixed message
            uint32_t length = static_cast<uint32_t>(json_str.size());
            std::vector<char> buffer(4 + length);
            memcpy(buffer.data(), &length, 4);
            memcpy(buffer.data() + 4, json_str.data(), length);

            // For simplicity, do synchronous write (could be made async)
            DWORD bytes_written;
            BOOL success = WriteFile(
                conn->pipe,
                buffer.data(),
                static_cast<DWORD>(buffer.size()),
                &bytes_written,
                nullptr  // Synchronous for now
            );

            return success && bytes_written == buffer.size();

        } catch (const std::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to send message to " + conn->client_id + ": " + e.what());
            return false;
        }
    }

    void handle_client_disconnect(const std::string& client_id) {
        std::unique_ptr<ClientConnection> conn;
        {
            std::lock_guard<std::mutex> lock(clients_mutex_);
            auto it = clients_.find(client_id);
            if (it != clients_.end()) {
                conn = std::move(it->second);
                clients_.erase(it);
            }
        }

        if (conn) {
            APLogger::instance().log(LogLevel::Debug,
                "Client disconnected: " + client_id);

            if (disconnect_handler_) {
                disconnect_handler_(client_id);
            }
        }
    }

    std::string pipe_name_;
    std::atomic<bool> running_{false};
    StopToken stop_token_;
    std::thread io_thread_;

    mutable std::mutex clients_mutex_;
    std::unordered_map<std::string, std::unique_ptr<ClientConnection>> clients_;

    ThreadSafeQueue<IPCMessage> incoming_queue_;

    MessageHandler message_handler_;
    ConnectHandler connect_handler_;
    DisconnectHandler disconnect_handler_;

    int timeout_ms_ = 5000;
    int max_retries_ = 3;
    int retry_delay_ms_ = 100;
};

#else  // Non-Windows stub

class APIPCServer::Impl {
public:
    bool start(const std::string&) { return false; }
    void stop() {}
    bool is_running() const { return false; }
    bool send_message(const std::string&, const IPCMessage&) { return false; }
    void broadcast(const IPCMessage&) {}
    void broadcast_except(const IPCMessage&, const std::string&) {}
    std::vector<IPCMessage> get_pending_messages() { return {}; }
    void poll() {}
    std::vector<std::string> get_connected_clients() const { return {}; }
    bool is_client_connected(const std::string&) const { return false; }
    size_t get_client_count() const { return 0; }
    void set_message_handler(MessageHandler) {}
    void set_connect_handler(ConnectHandler) {}
    void set_disconnect_handler(DisconnectHandler) {}
    void set_timeout(int) {}
    void set_retry_policy(int, int) {}
    std::string get_pipe_name() const { return ""; }
};

#endif  // _WIN32

// =============================================================================
// Public API Implementation
// =============================================================================

APIPCServer::APIPCServer() : impl_(std::make_unique<Impl>()) {}
APIPCServer::~APIPCServer() = default;

bool APIPCServer::start(const std::string& game_name) {
    return impl_->start(game_name);
}

void APIPCServer::stop() {
    impl_->stop();
}

bool APIPCServer::is_running() const {
    return impl_->is_running();
}

bool APIPCServer::send_message(const std::string& client_id, const IPCMessage& message) {
    return impl_->send_message(client_id, message);
}

void APIPCServer::broadcast(const IPCMessage& message) {
    impl_->broadcast(message);
}

void APIPCServer::broadcast_except(const IPCMessage& message, const std::string& exclude_client_id) {
    impl_->broadcast_except(message, exclude_client_id);
}

std::vector<IPCMessage> APIPCServer::get_pending_messages() {
    return impl_->get_pending_messages();
}

void APIPCServer::poll() {
    impl_->poll();
}

std::vector<std::string> APIPCServer::get_connected_clients() const {
    return impl_->get_connected_clients();
}

bool APIPCServer::is_client_connected(const std::string& client_id) const {
    return impl_->is_client_connected(client_id);
}

size_t APIPCServer::get_client_count() const {
    return impl_->get_client_count();
}

void APIPCServer::set_message_handler(MessageHandler handler) {
    impl_->set_message_handler(std::move(handler));
}

void APIPCServer::set_connect_handler(ConnectHandler handler) {
    impl_->set_connect_handler(std::move(handler));
}

void APIPCServer::set_disconnect_handler(DisconnectHandler handler) {
    impl_->set_disconnect_handler(std::move(handler));
}

void APIPCServer::set_timeout(int timeout_ms) {
    impl_->set_timeout(timeout_ms);
}

void APIPCServer::set_retry_policy(int max_retries, int retry_delay_ms) {
    impl_->set_retry_policy(max_retries, retry_delay_ms);
}

std::string APIPCServer::get_pipe_name() const {
    return impl_->get_pipe_name();
}

} // namespace ap
