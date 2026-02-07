#pragma once

#include "ap_client_types.h"
#include "ap_exports.h"

#include <atomic>
#include <functional>
#include <mutex>
#include <optional>
#include <queue>
#include <string>
#include <vector>

#ifdef _WIN32
#include <Windows.h>
#endif

namespace ap
{

/**
 * @brief Named pipes client for IPC with the framework.
 *
 * Connects to APFrameworkCore's IPC server to send/receive messages.
 * Uses length-prefixed JSON messages (4-byte LE length + JSON body).
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation in .cpp file
 */
class AP_API APIPCClient
{
  public:
    using MessageHandler = std::function<void(const IPCMessage &)>;
    using ConnectHandler = std::function<void()>;
    using DisconnectHandler = std::function<void()>;

    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey
    {
      private:
        friend class APIPCClient;
        explicit ConstructorKey() = default;
    };

    explicit APIPCClient(ConstructorKey);
    ~APIPCClient();

    // Delete copy/move operations
    APIPCClient(const APIPCClient &) = delete;
    APIPCClient &operator=(const APIPCClient &) = delete;
    APIPCClient(APIPCClient &&) = delete;
    APIPCClient &operator=(APIPCClient &&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APIPCClient singleton.
     */
    static APIPCClient *get();

    // =========================================================================
    // Connection
    // =========================================================================

    /**
     * @brief Connect to the framework's IPC server.
     * @param game_name Game name used in pipe path: \\.\pipe\APFramework_<game_name>
     * @return true if connected successfully.
     */
    bool connect(const std::string &game_name);

    /**
     * @brief Disconnect from the server.
     */
    void disconnect();

    /**
     * @brief Check if connected to the server.
     * @return true if connected.
     */
    bool is_connected() const;

    // =========================================================================
    // Messaging
    // =========================================================================

    /**
     * @brief Send a message to the framework.
     * @param message Message to send.
     * @return true if message was sent successfully.
     */
    bool send_message(const IPCMessage &message);

    /**
     * @brief Poll for incoming messages (non-blocking).
     *
     * Should be called periodically to receive messages from the framework.
     * Triggers the message handler for each received message.
     */
    void poll();

    /**
     * @brief Get all pending messages without triggering handlers.
     * @return Vector of received messages.
     */
    std::vector<IPCMessage> get_pending_messages();

    /**
     * @brief Try to receive a single message (non-blocking).
     * @return The message if available, std::nullopt otherwise.
     */
    std::optional<IPCMessage> try_receive();

    // ==========================================================================
    // Callbacks
    // ==========================================================================

    /**
     * @brief Set handler for incoming messages.
     * @param handler Function called when a message is received.
     */
    void set_message_handler(MessageHandler handler);

    /**
     * @brief Set handler for successful connection.
     * @param handler Function called when connected.
     */
    void set_connect_handler(ConnectHandler handler);

    /**
     * @brief Set handler for disconnection.
     * @param handler Function called when disconnected.
     */
    void set_disconnect_handler(DisconnectHandler handler);

    // ==========================================================================
    // Configuration
    // ==========================================================================

    /**
     * @brief Enable or disable auto-reconnection.
     * @param enabled Whether to automatically reconnect on disconnect.
     */
    void set_auto_reconnect(bool enabled);

    /**
     * @brief Set connection timeout.
     * @param timeout_ms Timeout in milliseconds.
     */
    void set_timeout(int timeout_ms);

    /**
     * @brief Get the pipe name being used.
     * @return Full pipe path, or empty string if not connected.
     */
    std::string get_pipe_name() const;

  private:
    // =========================================================================
    // Private Methods
    // =========================================================================

#ifdef _WIN32
    void start_read();
    void check_read_completion();
    void process_received_data(DWORD bytes_received);
    void handle_disconnect();
#endif

    // =========================================================================
    // Private Member Variables
    // =========================================================================

#ifdef _WIN32
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
    OVERLAPPED read_overlapped_ = {};
    std::vector<char> read_buffer_;
    std::atomic<bool> reading_{false};
#endif

    std::string pipe_name_;
    std::atomic<bool> connected_{false};
    bool auto_reconnect_ = false;
    int timeout_ms_ = 5000;

    std::mutex queue_mutex_;
    std::queue<IPCMessage> message_queue_;

    MessageHandler message_handler_;
    ConnectHandler connect_handler_;
    DisconnectHandler disconnect_handler_;
};

} // namespace ap