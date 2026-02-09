local RegistryHelper = {
    registry = {},
    callback_map = {}
}

function RegistryHelper.add_object(className)
    if not RegistryHelper.registry[className] then
        RegistryHelper.registry[className] = {
            definitions = {},
            active_hooks = {}
        }

        NotifyOnNewObject(className, function(instance)
            local data = RegistryHelper.registry[className]
            RegistryHelper.unregister_class_hooks(className)

            for _, def in ipairs(data.definitions) do
                local preId, postId = RegisterHook(def.path, function(obj, ...)
                    def.callback(className, obj, ...)
                end)

                table.insert(data.active_hooks, {
                    path = def.path,
                    pre = preId,
                    post = postId,
                    callback = def.callback
                })
            end
        end)
    end
    return className
end

function RegistryHelper.add_function(className, functionPath, callback)
    local data = RegistryHelper.registry[className]
    if not data then return end

    table.insert(data.definitions, { path = functionPath, callback = callback })
    RegistryHelper.callback_map[callback] = className
end

function RegistryHelper.unregister_class_hooks(className)
    local data = RegistryHelper.registry[className]
    if data and #data.active_hooks > 0 then
        for _, hook in ipairs(data.active_hooks) do
            UnregisterHook(hook.path, hook.pre, hook.post)
        end
        data.active_hooks = {}
    end
end

function RegistryHelper.remove(target)
    if type(target) == "function" then
        local className = RegistryHelper.callback_map[target]
        if className then
            local defs = RegistryHelper.registry[className].definitions
            for i = #defs, 1, -1 do
                if defs[i].callback == target then table.remove(defs, i) end
            end
            RegistryHelper.unregister_class_hooks(className)
            RegistryHelper.callback_map[target] = nil
        end
    elseif type(target) == "string" and RegistryHelper.registry[target] then
        RegistryHelper.unregister_class_hooks(target)
        RegistryHelper.registry[target] = nil
    end
end

function RegistryHelper.clear()
    for className, _ in pairs(RegistryHelper.registry) do
        RegistryHelper.remove(className)
    end
end

return RegistryHelper