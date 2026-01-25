#pragma once

#include "ap_exports.h"
#include "ap_types.h"
#include "thread_safe_queue.h"
#include "stop_token.h"

#include <string>
#include <memory>
#include <functional>
#include <unordered_map>

namespace ap {

/**
 * @brief Named pipes server for IPC with client mods.
 *
 * Manages multiple client connections via Windows Named Pipes.
 * Uses length-prefixed JSON messages (4-byte LE length + JSON body).
 *
 * Thread model:
 * - Main thread calls start(), stop(), send_message(), broadcast()
 * - Background thread handles pipe I/O via overlapped operations
 * - Messages are queued for thread-safe access
 */
class AP_API APIPCServer {
public:
    using MessageHandler = std::function<void(const std::string& client_id, const IPCMessage&)>;
    using ConnectHandler = std::function<void(const std::string& client_id)>;
    using DisconnectHandler = std::function<void(const std::string& client_id)>;

    APIPCServer();
    ~APIPCServer();

    // Delete copy/move operations
    APIPCServer(const APIPCServer&) = delete;
    APIPCServer& operator=(const APIPCServer&) = delete;
    APIPCServer(APIPCServer&&) = delete;
    APIPCServer& operator=(APIPCServer&&) = delete;

    /**
     * @brief Start the IPC server.
     * @param game_name Game name used in pipe path: \\.\pipe\APFramework_<game_name>
     * @return true if server started successfully.
     */
    bool start(const std::string& game_name);

    /**
     * @brief Stop the IPC server and disconnect all clients.
     */
    void stop();

    /**
     * @brief Check if the server is running.
     * @return true if server is running.
     */
    bool is_running() const;

    /**
     * @brief Send a message to a specific client.
     * @param client_id Target client identifier (mod_id).
     * @param message Message to send.
     * @return true if message was queued for sending.
     */
    bool send_message(const std::string& client_id, const IPCMessage& message);

    /**
     * @brief Broadcast a message to all connected clients.
     * @param message Message to broadcast.
     */
    void broadcast(const IPCMessage& message);

    /**
     * @brief Broadcast a message to all clients except the specified one.
     * @param message Message to broadcast.
     * @param exclude_client_id Client to exclude from broadcast.
     */
    void broadcast_except(const IPCMessage& message, const std::string& exclude_client_id);

    /**
     * @brief Get all pending messages received from clients.
     * @return Vector of messages with their source client IDs.
     */
    std::vector<IPCMessage> get_pending_messages();

    /**
     * @brief Poll for new messages (non-blocking).
     *
     * This should be called periodically from the main thread to process
     * incoming messages. It triggers message handlers if set.
     */
    void poll();

    /**
     * @brief Get list of connected client IDs.
     * @return Vector of client identifiers.
     */
    std::vector<std::string> get_connected_clients() const;

    /**
     * @brief Check if a specific client is connected.
     * @param client_id Client identifier.
     * @return true if client is connected.
     */
    bool is_client_connected(const std::string& client_id) const;

    /**
     * @brief Get number of connected clients.
     * @return Client count.
     */
    size_t get_client_count() const;

    // ==========================================================================
    // Callbacks
    // ==========================================================================

    /**
     * @brief Set handler for incoming messages.
     * @param handler Function called when a message is received.
     */
    void set_message_handler(MessageHandler handler);

    /**
     * @brief Set handler for client connections.
     * @param handler Function called when a client connects.
     */
    void set_connect_handler(ConnectHandler handler);

    /**
     * @brief Set handler for client disconnections.
     * @param handler Function called when a client disconnects.
     */
    void set_disconnect_handler(DisconnectHandler handler);

    // ==========================================================================
    // Configuration
    // ==========================================================================

    /**
     * @brief Set the message timeout.
     * @param timeout_ms Timeout in milliseconds.
     */
    void set_timeout(int timeout_ms);

    /**
     * @brief Set retry policy for failed sends.
     * @param max_retries Maximum number of retries.
     * @param retry_delay_ms Delay between retries in milliseconds.
     */
    void set_retry_policy(int max_retries, int retry_delay_ms);

    /**
     * @brief Get the pipe name being used.
     * @return Full pipe path.
     */
    std::string get_pipe_name() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
