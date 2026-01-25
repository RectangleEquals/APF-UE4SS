#pragma once

#include "ap_clientlib_exports.h"
#include "ap_client_types.h"

#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <optional>

namespace ap {

/**
 * @brief Named pipes client for IPC with the framework.
 *
 * Connects to APFrameworkCore's IPC server to send/receive messages.
 * Uses length-prefixed JSON messages (4-byte LE length + JSON body).
 */
class APCLIENT_API APIPCClient {
public:
    using MessageHandler = std::function<void(const ClientIPCMessage&)>;
    using ConnectHandler = std::function<void()>;
    using DisconnectHandler = std::function<void()>;

    APIPCClient();
    ~APIPCClient();

    // Delete copy/move operations
    APIPCClient(const APIPCClient&) = delete;
    APIPCClient& operator=(const APIPCClient&) = delete;
    APIPCClient(APIPCClient&&) = delete;
    APIPCClient& operator=(APIPCClient&&) = delete;

    /**
     * @brief Connect to the framework's IPC server.
     * @param game_name Game name used in pipe path: \\.\pipe\APFramework_<game_name>
     * @return true if connected successfully.
     */
    bool connect(const std::string& game_name);

    /**
     * @brief Disconnect from the server.
     */
    void disconnect();

    /**
     * @brief Check if connected to the server.
     * @return true if connected.
     */
    bool is_connected() const;

    /**
     * @brief Send a message to the framework.
     * @param message Message to send.
     * @return true if message was sent successfully.
     */
    bool send_message(const ClientIPCMessage& message);

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
    std::vector<ClientIPCMessage> get_pending_messages();

    /**
     * @brief Try to receive a single message (non-blocking).
     * @return The message if available, std::nullopt otherwise.
     */
    std::optional<ClientIPCMessage> try_receive();

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
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace ap
