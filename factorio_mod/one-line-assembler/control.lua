-- FRISC-V debug tools. Factorio allows only one handler per event per mod, so
-- each feature module exposes its handlers and this file dispatches to them.
--   assembler.lua         One line assembler (constant combinator -> signal D)
--   register_display.lua  Register display (display panel -> register table GUI)
-- register_display.lua also (un)registers on_tick itself, only while its GUI is open.

local modules = {
  require("assembler"),
  require("register_display"),
}

local by_event = {}   -- event name -> {handlers = {...}, filter = filter or nil}
for _, m in ipairs(modules) do
  for name, handler in pairs(m.events) do
    local entry = by_event[name]
    if not entry then
      entry = {handlers = {}, filters = {}}
      by_event[name] = entry
    end
    table.insert(entry.handlers, handler)
    table.insert(entry.filters, m.filters[name] or false)
  end
end

for name, entry in pairs(by_event) do
  local id = defines.events[name]
  if #entry.handlers == 1 then
    -- a single listener may use its event filter
    script.on_event(id, entry.handlers[1], entry.filters[1] or nil)
  else
    local handlers = entry.handlers
    script.on_event(id, function(event)
      for i = 1, #handlers do handlers[i](event) end
    end)
  end
end

script.on_init(function()
  for _, m in ipairs(modules) do if m.on_init then m.on_init() end end
end)

script.on_configuration_changed(function(data)
  for _, m in ipairs(modules) do if m.on_configuration_changed then m.on_configuration_changed(data) end end
end)

script.on_load(function()
  for _, m in ipairs(modules) do if m.on_load then m.on_load() end end
end)
