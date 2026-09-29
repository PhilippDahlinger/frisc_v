-- Minimal, strict mock of the Factorio 2.0 runtime API used by control.lua.
-- It exists to run control.lua outside the game: unknown GUI parameters, style
-- properties, style names or malformed logistic filters raise errors, so typos
-- and API misuse show up in tests. Allowed names come from the 2.0.77 runtime
-- API (factorio-types) and core/prototypes/style.lua.

local M = {}

local function set_of(list)
  local s = {}
  for _, v in ipairs(list) do s[v] = true end
  return s
end

local BASE_ADD_KEYS = set_of{"anchor", "caption", "elem_tooltip", "enabled", "game_controller_interaction",
  "ignored_by_interaction", "index", "locked", "name", "raise_hover_events", "style", "tags", "tooltip",
  "type", "visible"}
local TYPE_ADD_KEYS = {
  ["frame"] = set_of{"direction"},
  ["flow"] = set_of{"direction"},
  ["label"] = set_of{},
  ["empty-widget"] = set_of{},
  ["textfield"] = set_of{"allow_decimal", "allow_negative", "icon_selector", "is_password",
                         "lose_focus_on_confirm", "numeric", "text"},
  ["table"] = set_of{"column_count", "draw_horizontal_line_after_headers", "draw_horizontal_lines",
                     "draw_vertical_lines", "vertical_centering"},
  ["checkbox"] = set_of{"state"},
  ["scroll-pane"] = set_of{"horizontal_scroll_policy", "vertical_scroll_policy"},
  ["sprite-button"] = set_of{"auto_toggle", "clicked_sprite", "hovered_sprite", "mouse_button_filter",
                             "number", "quality", "show_percent_for_small_numbers",
                             "sprite", "toggled"},
}
local STYLE_PROPS = set_of{"bottom_margin", "bottom_padding", "cell_padding", "font", "font_color",
  "height", "horizontal_align", "horizontal_spacing", "horizontally_squashable", "horizontally_stretchable",
  "left_margin", "left_padding", "margin", "maximal_height", "maximal_width", "minimal_height",
  "minimal_width", "natural_height", "natural_width", "padding", "right_margin", "right_padding",
  "single_line", "size", "top_margin", "top_padding", "vertical_align", "vertical_spacing",
  "vertically_squashable", "vertically_stretchable", "width"}
local STYLE_NAMES = set_of{"frame_title", "draggable_space_header", "frame_action_button",
  "inside_shallow_frame_with_padding", "semibold_label", "bold_label", "bordered_table"}
local FONTS = set_of{"default", "default-semibold", "default-bold", "default-large", "default-large-semibold",
  "default-large-bold", "default-small", "default-small-semibold", "default-small-bold"}
local SPRITES = set_of{"utility/close"}

-- --------------------------------------------------------------------------
-- GUI elements
-- --------------------------------------------------------------------------

local Element = {}

local function new_style(element)
  local values = {}
  return setmetatable({}, {
    __index = function(_, k)
      if not STYLE_PROPS[k] then error("mock: unknown style property '" .. tostring(k) .. "'", 2) end
      return values[k]
    end,
    __newindex = function(_, k, v)
      if not STYLE_PROPS[k] then error("mock: unknown style property '" .. tostring(k) .. "'", 2) end
      if k == "font" and not FONTS[v] then error("mock: unknown font '" .. tostring(v) .. "'", 2) end
      if not element.valid then error("mock: style access on invalid element", 2) end
      values[k] = v
    end,
  })
end

local function make_element(parent, params)
  local e = {
    __kind = "element", valid = true, type = params.type, name = params.name or "",
    caption = params.caption or "", text = params.text or "", state = params.state,
    tooltip = params.tooltip, tags = params.tags or {}, children = {}, parent = parent,
    style_name = params.style, sprite = params.sprite, column_count = params.column_count,
  }
  e.style = new_style(e)
  return setmetatable(e, Element)
end

Element.__index = function(self, k)
  local method = Element[k]
  if method then return function(...) return method(self, ...) end end
  if not rawget(self, "valid") then error("mock: access '" .. tostring(k) .. "' on invalid element", 2) end
  for _, c in ipairs(rawget(self, "children")) do
    if c.name == k and c.name ~= "" then return c end
  end
  return nil
end

local WRITABLE = set_of{"caption", "text", "state", "tooltip", "drag_target", "visible", "enabled",
  "tags", "name", "style"}
Element.__newindex = function(self, k, v)
  if not WRITABLE[k] then error("mock: cannot write element property '" .. tostring(k) .. "'", 2) end
  if not rawget(self, "valid") then error("mock: write to invalid element", 2) end
  rawset(self, k, v)
end

function Element.add(self, params)
  if not self.valid then error("mock: add() on invalid element", 2) end
  local allowed = TYPE_ADD_KEYS[params.type]
  if not allowed then error("mock: unsupported element type '" .. tostring(params.type) .. "'", 2) end
  for k in pairs(params) do
    if not BASE_ADD_KEYS[k] and not allowed[k] then
      error("mock: '" .. k .. "' is not a valid add() parameter for " .. params.type, 2)
    end
  end
  if params.style and not STYLE_NAMES[params.style] then
    error("mock: unknown style '" .. params.style .. "'", 2)
  end
  if params.sprite and not SPRITES[params.sprite] then
    error("mock: unknown sprite '" .. params.sprite .. "'", 2)
  end
  if params.type == "table" and not params.column_count then error("mock: table needs column_count", 2) end
  if params.name and params.name ~= "" and self[params.name] then
    error("mock: duplicate child name '" .. params.name .. "'", 2)
  end
  local child = make_element(self, params)
  table.insert(self.children, child)
  return child
end

local function invalidate(e)
  e.valid = false
  for _, c in ipairs(e.children) do invalidate(c) end
end

function Element.destroy(self)
  if not self.valid then error("mock: destroy() on invalid element", 2) end
  local siblings = self.parent.children
  for i, c in ipairs(siblings) do
    if c == self then table.remove(siblings, i) break end
  end
  invalidate(self)
  if M.on_destroy then M.on_destroy(self) end
end

function Element.clear(self)
  for _, c in ipairs(self.children) do invalidate(c) end
  self.children = {}
end

function Element.focus(self) M.focused = self end
function Element.select_all(self) end
function Element.force_auto_center(self) end
function Element.bring_to_front(self) end

-- find all descendants matching a predicate (test helper)
function M.find_all(root, pred, out)
  out = out or {}
  for _, c in ipairs(root.children) do
    if pred(c) then out[#out + 1] = c end
    M.find_all(c, pred, out)
  end
  return out
end

function M.all_captions(root)
  local t = {}
  for _, e in ipairs(M.find_all(root, function(e) return e.type == "label" end)) do
    t[#t + 1] = type(e.caption) == "table" and table.concat(e.caption, ",") or e.caption
  end
  return table.concat(t, "\n")
end

-- --------------------------------------------------------------------------
-- Entities, control behaviour, logistic sections
-- --------------------------------------------------------------------------

local VALID_SIGNAL_TYPES = set_of{"item", "fluid", "virtual", "entity", "recipe", "space-location",
  "asteroid-chunk", "quality"}

local function new_section(index)
  local s = {valid = true, index = index, is_manual = true, group = "", active = true, multiplier = 1}
  local filters = {}
  local function check_filter(f)
    local v = f.value
    if type(v) ~= "table" then error("mock: filter.value must be a SignalFilter table", 3) end
    if not VALID_SIGNAL_TYPES[v.type] then error("mock: bad signal type " .. tostring(v.type), 3) end
    if type(v.name) ~= "string" then error("mock: signal name missing", 3) end
    local min = f.min or 0
    if min ~= 0 and v.quality == nil then error("mock: quality is mandatory when min ~= 0", 3) end
    if math.floor(min) ~= min or min < -2147483648 or min > 2147483647 then
      error("mock: min " .. tostring(min) .. " is not an int32", 3)
    end
  end
  s.set_slot = function(i, f)
    check_filter(f)
    filters[i] = f
  end
  s.clear_slot = function(i) filters[i] = nil end
  s.get_slot = function(i) return filters[i] or {} end
  return setmetatable(s, {
    __index = function(_, k)
      if k == "filters" then
        local list = {}
        for i, f in pairs(filters) do list[#list + 1] = f end
        return list
      elseif k == "filters_count" then
        local n = 0
        for i in pairs(filters) do if i > n then n = i end end
        return n
      end
    end,
    __newindex = function(_, k, v)
      if k == "filters" then
        filters = {}
        for i, f in ipairs(v) do check_filter(f); filters[i] = f end
      else
        error("mock: cannot set section." .. tostring(k), 2)
      end
    end,
  })
end

local function new_control_behavior()
  local cb = {valid = true, enabled = true, sections = {}}
  cb.add_section = function()
    local s = new_section(#cb.sections + 1)
    table.insert(cb.sections, s)
    return s
  end
  cb.get_section = function(i) return cb.sections[i] end
  cb.remove_section = function(i)
    if not cb.sections[i] then return false end
    table.remove(cb.sections, i)
    return true
  end
  return setmetatable(cb, {__index = function(_, k)
    if k == "sections_count" then return #cb.sections end
  end})
end

local next_unit = 1
function M.new_entity(name, opts)
  opts = opts or {}
  local e = {valid = true, name = name, type = opts.type or "constant-combinator",
             ghost_name = opts.ghost_name, unit_number = next_unit, combinator_description = ""}
  next_unit = next_unit + 1
  local cb = new_control_behavior()
  cb.add_section()   -- a fresh constant combinator has one empty manual section
  e.get_or_create_control_behavior = function() return cb end
  e.get_control_behavior = function() return cb end
  e.__cb = cb

  -- circuit input (display panels etc.): values per wire, keyed by item name
  e.__wires = {[0] = nil, [1] = nil}   -- set M.connect(e, wire, {name = value})
  e.__get_signal_calls = 0
  e.get_circuit_network = function(id)
    if id ~= 0 and id ~= 1 then error("mock: bad wire_connector_id " .. tostring(id), 2) end
    return e.__wires[id] and {valid = true, signals = e.__wires[id]} or nil
  end
  e.get_signal = function(signal, id1, id2)
    if type(signal) ~= "table" or signal.type ~= "item" or signal.quality ~= "normal" then
      error("mock: get_signal expects an item SignalID with quality", 2)
    end
    if not _G.prototypes.item[signal.name] then error("mock: unknown item signal " .. signal.name, 2) end
    if id1 ~= 0 or id2 ~= 1 then error("mock: expected red + green wire connector ids", 2) end
    e.__get_signal_calls = e.__get_signal_calls + 1
    local total = 0
    for _, id in ipairs({id1, id2}) do
      local w = e.__wires[id]
      if w and w[signal.name] then total = total + w[signal.name] end
    end
    return total
  end
  return e
end

function M.connect(entity, wire, values)
  entity.__wires[wire] = values
end

-- the (type, name, min) the entity currently outputs, as a list
function M.outputs(entity)
  local out = {}
  local cb = entity.__cb
  for _, s in ipairs(cb.sections) do
    for _, f in ipairs(s.filters) do
      out[#out + 1] = {type = f.value.type, name = f.value.name, quality = f.value.quality, min = f.min}
    end
  end
  return out
end

-- --------------------------------------------------------------------------
-- Globals: script, defines, game, storage
-- --------------------------------------------------------------------------

function M.install()
  local handlers = {}
  local event_names = {"on_gui_opened", "on_gui_closed", "on_gui_click", "on_gui_text_changed",
    "on_gui_checked_state_changed", "on_object_destroyed", "on_built_entity", "on_robot_built_entity",
    "on_space_platform_built_entity", "script_raised_built", "script_raised_revive", "on_entity_cloned",
    "on_entity_settings_pasted", "on_tick"}
  local events = {}
  for i, n in ipairs(event_names) do events[n] = i end
  _G.defines = {events = events, gui_type = {entity = 5, custom = 4},
                wire_connector_id = {circuit_red = 0, circuit_green = 1}}
  _G.prototypes = {item = {}}
  for _, n in ipairs(M.ITEMS) do _G.prototypes.item[n] = {name = n} end

  M.handlers = handlers
  M.registered = {}
  _G.script = {
    on_init = function(f) handlers.init = f end,
    on_configuration_changed = function(f) handlers.config = f end,
    on_load = function(f) handlers.load = f end,
    on_event = function(id, f, filters)
      if type(id) ~= "number" then error("mock: unknown event id " .. tostring(id), 2) end
      handlers[id] = f
    end,
    register_on_object_destroyed = function(obj)
      M.registered[obj] = true
      return 1, 0, 1
    end,
  }
  _G.storage = {}

  local players = {}
  M.players = players
  _G.game = {
    players = players,
    tick = 0,
    get_player = function(i) return players[i] end,
  }
end

function M.add_player(index)
  local root = make_element(nil, {type = "flow", name = "screen"})
  rawset(root, "parent", {children = {}})
  local p = {index = index, valid = true, gui = {screen = root}, opened = nil}
  M.players[index] = p
  return p
end

-- items that exist in the mocked game (Space Age item set for the register signals)
M.ITEMS = {"wooden-chest", "iron-chest", "steel-chest", "storage-tank", "transport-belt", "fast-transport-belt",
  "express-transport-belt", "turbo-transport-belt", "underground-belt", "fast-underground-belt",
  "express-underground-belt", "turbo-underground-belt", "splitter", "fast-splitter", "express-splitter",
  "turbo-splitter", "burner-inserter", "inserter", "long-handed-inserter", "fast-inserter", "bulk-inserter",
  "stack-inserter", "small-electric-pole", "medium-electric-pole", "big-electric-pole", "substation", "pipe",
  "pipe-to-ground", "pump", "rail", "rail-ramp", "rail-support", "train-stop"}

-- advance the game by n ticks, firing on_tick if (and only if) a handler is registered
function M.run_ticks(n)
  for _ = 1, n do
    game.tick = game.tick + 1
    local h = M.handlers[defines.events.on_tick]
    if h then h({name = defines.events.on_tick, tick = game.tick}) end
  end
end

function M.fire(name, event)
  event.name = defines.events[name]
  event.tick = event.tick or game.tick
  local h = M.handlers[defines.events[name]]
  if h then h(event) end
end

return M
