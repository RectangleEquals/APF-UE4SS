#include "ap_action_executor.h"
#include "ap_clientlib_exports.h"

#include <sol/sol.hpp>

#include <sstream>
#include <vector>

namespace ap::client {

// =============================================================================
// Implementation
// =============================================================================

class APActionExecutor::Impl {
public:
    ActionResult execute(
        const std::string& action,
        const std::vector<ActionArg>& args,
        int64_t item_id,
        const std::string& item_name
    ) {
        ActionResult result;
        result.item_id = item_id;
        result.item_name = item_name;

        // Get cached Lua state
        sol::state_view* lua = get_cached_lua();
        if (!lua) {
            result.success = false;
            result.error = "Lua state not available";
            return result;
        }

        try {
            // Resolve the function from the action path
            sol::object func = resolve_function_path(*lua, action);
            if (!func.is<sol::function>()) {
                result.success = false;
                result.error = "Function not found: " + action;
                return result;
            }

            // Build arguments
            std::vector<sol::object> lua_args;
            for (const auto& arg : args) {
                sol::object resolved = resolve_argument(*lua, arg);
                lua_args.push_back(resolved);
            }

            // Call the function
            sol::protected_function fn = func.as<sol::function>();
            sol::protected_function_result call_result;

            switch (lua_args.size()) {
                case 0:
                    call_result = fn();
                    break;
                case 1:
                    call_result = fn(lua_args[0]);
                    break;
                case 2:
                    call_result = fn(lua_args[0], lua_args[1]);
                    break;
                case 3:
                    call_result = fn(lua_args[0], lua_args[1], lua_args[2]);
                    break;
                case 4:
                    call_result = fn(lua_args[0], lua_args[1], lua_args[2], lua_args[3]);
                    break;
                case 5:
                    call_result = fn(lua_args[0], lua_args[1], lua_args[2], lua_args[3], lua_args[4]);
                    break;
                default:
                    // For more than 5 arguments, use lua_call directly
                    call_result = fn(sol::as_args(lua_args));
                    break;
            }

            if (!call_result.valid()) {
                sol::error err = call_result;
                result.success = false;
                result.error = "Execution error: " + std::string(err.what());
                return result;
            }

            result.success = true;
            return result;

        } catch (const sol::error& e) {
            result.success = false;
            result.error = "Sol2 error: " + std::string(e.what());
            return result;
        } catch (const std::exception& e) {
            result.success = false;
            result.error = "Exception: " + std::string(e.what());
            return result;
        } catch (...) {
            result.success = false;
            result.error = "Unknown error during execution";
            return result;
        }
    }

    ActionResult execute_from_payload(const nlohmann::json& payload) {
        ActionResult result;

        try {
            // Extract required fields
            int64_t item_id = payload.value("item_id", 0LL);
            std::string item_name = payload.value("item_name", "");
            std::string action = payload.value("action", "");

            result.item_id = item_id;
            result.item_name = item_name;

            if (action.empty()) {
                result.success = false;
                result.error = "No action specified in payload";
                return result;
            }

            // Parse arguments
            std::vector<ActionArg> args;
            if (payload.contains("args") && payload["args"].is_array()) {
                for (const auto& arg_json : payload["args"]) {
                    ActionArg arg;
                    arg.name = arg_json.value("name", "");
                    arg.type = APActionExecutor::parse_arg_type(arg_json.value("type", "string"));
                    arg.value = arg_json.value("value", nlohmann::json());
                    args.push_back(arg);
                }
            }

            return execute(action, args, item_id, item_name);

        } catch (const nlohmann::json::exception& e) {
            result.success = false;
            result.error = "JSON parse error: " + std::string(e.what());
            return result;
        }
    }

private:
    /**
     * Resolve a function path like "MyUserObj.UnlockTechnology" to the actual Lua function.
     */
    sol::object resolve_function_path(sol::state_view& lua, const std::string& path) {
        // Split path by '.'
        std::vector<std::string> parts;
        std::stringstream ss(path);
        std::string part;
        while (std::getline(ss, part, '.')) {
            if (!part.empty()) {
                parts.push_back(part);
            }
        }

        if (parts.empty()) {
            return sol::nil;
        }

        // Start from global table
        sol::object current = lua[parts[0]];

        // Navigate through nested tables
        for (size_t i = 1; i < parts.size(); ++i) {
            if (!current.is<sol::table>()) {
                return sol::nil;  // Path broken - not a table
            }
            current = current.as<sol::table>()[parts[i]];
        }

        return current;
    }

    /**
     * Resolve an argument to a Lua value.
     * For property types, evaluates the path in the current Lua state.
     */
    sol::object resolve_argument(sol::state_view& lua, const ActionArg& arg) {
        switch (arg.type) {
            case ArgType::String:
                if (arg.value.is_string()) {
                    return sol::make_object(lua, arg.value.get<std::string>());
                }
                return sol::make_object(lua, arg.value.dump());

            case ArgType::Number:
                if (arg.value.is_number_integer()) {
                    return sol::make_object(lua, arg.value.get<int64_t>());
                } else if (arg.value.is_number_float()) {
                    return sol::make_object(lua, arg.value.get<double>());
                }
                return sol::make_object(lua, 0);

            case ArgType::Boolean:
                if (arg.value.is_boolean()) {
                    return sol::make_object(lua, arg.value.get<bool>());
                }
                return sol::make_object(lua, false);

            case ArgType::Property: {
                // Property path - evaluate at runtime
                if (!arg.value.is_string()) {
                    return sol::nil;
                }

                std::string property_path = arg.value.get<std::string>();
                return resolve_function_path(lua, property_path);  // Same logic works for properties
            }

            default:
                return sol::nil;
        }
    }
};

// =============================================================================
// Public API
// =============================================================================

APActionExecutor::APActionExecutor() : impl_(std::make_unique<Impl>()) {}
APActionExecutor::~APActionExecutor() = default;

ActionResult APActionExecutor::execute(
    const std::string& action,
    const std::vector<ActionArg>& args,
    int64_t item_id,
    const std::string& item_name
) {
    return impl_->execute(action, args, item_id, item_name);
}

ActionResult APActionExecutor::execute_from_payload(const nlohmann::json& payload) {
    return impl_->execute_from_payload(payload);
}

ArgType APActionExecutor::parse_arg_type(const std::string& type_str) {
    if (type_str == "string") {
        return ArgType::String;
    } else if (type_str == "number") {
        return ArgType::Number;
    } else if (type_str == "boolean" || type_str == "bool") {
        return ArgType::Boolean;
    } else if (type_str == "property") {
        return ArgType::Property;
    }
    return ArgType::String;  // Default
}

std::string APActionExecutor::arg_type_to_string(ArgType type) {
    switch (type) {
        case ArgType::String: return "string";
        case ArgType::Number: return "number";
        case ArgType::Boolean: return "boolean";
        case ArgType::Property: return "property";
        default: return "unknown";
    }
}

} // namespace ap::client
