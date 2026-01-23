#include "ap_manager.h"
#include "ap_exports.h"
#include <string>

namespace ap {
	APManager* APManager::get() {
		if (!g_ap_manager) {
			g_ap_manager = std::make_unique<APManager>();
		}
		return g_ap_manager.get();
	}

	int APManager::init(lua_State* L) {
		sol::state_view lua(L);

		// Create a table that will be returned to Lua when 'require' is called
		sol::table module = lua.create_table();

		// Register your functions into that table
		module["Update"] = [](lua_State* L) {
			return ap::APManager::get()->update(L);
		};

		// Cache the state immediately upon loading
		ap::APManager::get()->update(L);

		// Push the table to the stack so Lua receives it
		return sol::stack::push(L, module);
	}

    int APManager::update(lua_State* L) {
		static int tickCount = 0;

        // Refresh or initialize the cache
        if (!cached_lua || cached_lua->lua_state() != L) {
			if(cached_lua) {
				cached_lua.reset();
			}
            cached_lua = std::make_unique<sol::state_view>(L);
			if(cached_lua) {
				sol::state_view& lua = *cached_lua;
				lua["print"]("Initializing APManager\n");
			}
        }

		sol::state_view& lua = *cached_lua;

		// Refresh or initialize the cache
		if (!ap_client) {
			lua["print"]("Initializing APClient\n");
			ap_client = std::make_unique<APClient>("", "", "");

			// Set up callbacks
			ap_client->set_socket_error_handler([this](std::string error) {
				sol::state_view& lua = *cached_lua;
				std::string message = "Socket error: " + error + "\n";
				lua["print"](message);
			});

			ap_client->set_socket_disconnected_handler([this]() {
				sol::state_view& lua = *cached_lua;
				std::string message = "Socket disconnected\n";
				lua["print"](message);
			});

			ap_client->set_room_info_handler([this]() {
				sol::state_view& lua = *cached_lua;
				std::string message = "Room info updated\n";
				lua["print"](message);
			});

			ap_client->set_slot_connected_handler([this](const nlohmann::json& slot_data) {
				sol::state_view& lua = *cached_lua;
				std::string message = "Slot connected: " + slot_data.dump() + "\n";
				lua["print"](message);
			});

			ap_client->set_slot_refused_handler([this](const std::list<std::string>& reasons) {
				sol::state_view& lua = *cached_lua;
				std::string message = "Slot refused: " + reasons.front() + "\n";
				lua["print"](message);
			});
		}

		sol::function f_on_event = lua["ap_on_event"];
		if(f_on_event.valid()) {
			sol::protected_function_result result = f_on_event("TickCount", tickCount);
			if(result.valid()) {
				tickCount = result.get<int>();
			}
			std::string message = "Updated from C++: " + std::to_string(tickCount) + "\n";
			lua["print"](message);
		} else {
			lua["print"]("Updated from C++\n");
		}

        return 0; 
    }
}