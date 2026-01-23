#pragma once

#include <nlohmann/json.hpp>
#include <sol/sol.hpp>
#include <apclient.hpp>

namespace ap {
	class APManager {
	private:
		APManager() = default;

		friend struct std::default_delete<APManager>;
		friend class std::unique_ptr<APManager>;
		friend std::unique_ptr<APManager> std::make_unique<APManager>();
	
	public:
		~APManager() = default;

		static APManager* get();
		int init(lua_State* L);
		int update(lua_State* L);
		
		static inline std::unique_ptr<sol::state_view> cached_lua = nullptr;
		static inline std::unique_ptr<APClient> ap_client = nullptr;
	};
}