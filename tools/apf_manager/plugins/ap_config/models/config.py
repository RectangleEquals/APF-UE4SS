DEFAULT_CONFIG = {
    "ap_server": {
        "host": "archipelago.gg",
        "port": 38281,
        "slot_name": "",
        "password": "",
        "auto_reconnect": True,
    },
    "logging": {
        "level": "info",
        "file": "ap_framework.log",
        "console": True,
        "append": False,
    },
    "timeouts": {
        "connection_ms": 30000,
        "priority_registration_ms": 30000,
        "registration_ms": 60000,
        "ipc_message_ms": 5000,
        "action_execution_ms": 5000,
        "retry": {
            "max_connection": 3,
            "max_ipc_message": 3,
            "initial_delay_ms": 1000,
            "backoff_multiplier": 2.0,
            "max_delay_ms": 10000,
        },
    },
    "threading": {
        "polling_interval_ms": 16,
        "queue_max_size": 1000,
        "shutdown_timeout_ms": 5000,
    },
}
