-- Register display: a display panel whose GUI shows the FRISC-V register file.
--
-- Wire it (red and/or green) to the register memory cell. Each register is one
-- item signal (see REGISTER_SIGNALS); x0 is hard-wired to zero and has none.
--
-- Zero overhead while nobody looks: the on_tick handler exists only while at
-- least one register-display GUI is open, and rows are only rewritten when
-- their value changes.

local encoder = require("encoder")

local ENTITY = "register-display"
local FRAME = "frd_frame"
local HIGHLIGHT_TICKS = 60   -- changed values stay highlighted for one second

-- x1..x31 = the first 31 signals of the "Logistics" signal group with Space Age
-- (Factorio 2.1): storage, belts, inserters, poles/pipes, rails.
local REGISTER_SIGNALS = {
  "wooden-chest", "iron-chest", "steel-chest", "storage-tank",                        -- x1  - x4
  "transport-belt", "fast-transport-belt", "express-transport-belt", "turbo-transport-belt", -- x5  - x8
  "underground-belt", "fast-underground-belt", "express-underground-belt",            -- x9  - x11
  "turbo-underground-belt",                                                           -- x12
  "splitter", "fast-splitter", "express-splitter", "turbo-splitter",                  -- x13 - x16
  "burner-inserter", "inserter", "long-handed-inserter", "fast-inserter",             -- x17 - x20
  "bulk-inserter", "stack-inserter",                                                  -- x21 - x22
  "small-electric-pole", "medium-electric-pole", "big-electric-pole", "substation",   -- x23 - x26
  "pipe", "pipe-to-ground", "pump", "rail", "rail-ramp",                              -- x27 - x31
}

local COLORS = {
  normal = {1, 1, 1},
  zero = {0.55, 0.55, 0.55},
  changed = {1.0, 0.85, 0.2},
  error = {1.0, 0.42, 0.35},
  ok = {0.5, 0.95, 0.5},
  dim = {0.7, 0.7, 0.7},
}

local RED = defines.wire_connector_id.circuit_red
local GREEN = defines.wire_connector_id.circuit_green

local M = {}
M.REGISTER_SIGNALS = REGISTER_SIGNALS

-- --------------------------------------------------------------------------
-- Formatting
-- --------------------------------------------------------------------------

local function format_value(v)
  local word = v % 4294967296
  local bin = encoder.bin_str(word, 32)
  local groups = {}
  for i = 1, 32, 4 do groups[#groups + 1] = bin:sub(i, i + 3) end
  return string.format("%d", v), "0x" .. encoder.hex_str(word, 8), table.concat(groups, " ")
end
M.format_value = format_value

-- --------------------------------------------------------------------------
-- State: storage.register_display.viewers[player_index] = {
--   entity, rows = {[reg] = {dec, hex, bin} gui elements}, values, changed_at,
--   status (label), frozen }
-- --------------------------------------------------------------------------

local function state()
  storage.register_display = storage.register_display or {viewers = {}}
  return storage.register_display
end

local on_tick   -- forward declaration

local function update_tick_handler()
  if next(state().viewers) then
    script.on_event(defines.events.on_tick, on_tick)
  else
    script.on_event(defines.events.on_tick, nil)
  end
end

local function close_gui(player)
  if not player then return end
  state().viewers[player.index] = nil
  local frame = player.gui.screen[FRAME]
  if frame and frame.valid then frame.destroy() end
  update_tick_handler()
end

-- --------------------------------------------------------------------------
-- Reading and refreshing
-- --------------------------------------------------------------------------

local function connection_text(entity)
  local red = entity.get_circuit_network(RED)
  local green = entity.get_circuit_network(GREEN)
  if red and green then return "Reading red + green wire", COLORS.ok end
  if red then return "Reading red wire", COLORS.ok end
  if green then return "Reading green wire", COLORS.ok end
  return "No wire connected: connect the register memory cell with a red or green wire", COLORS.error
end

local function refresh(viewer, tick, force)
  local entity = viewer.entity
  if not (entity and entity.valid) then return false end

  if force or tick % 30 == 0 then
    local text, color = connection_text(entity)
    viewer.status.caption = text
    viewer.status.style.font_color = color
  end
  if viewer.frozen and not force then return true end

  for reg = 1, 31 do
    local row = viewer.rows[reg]
    if row then
      local v = entity.get_signal(viewer.signal_ids[reg], RED, GREEN)
      if force or v ~= viewer.values[reg] then
        local first = viewer.values[reg] == nil
        viewer.values[reg] = v
        local dec, hex, bin = format_value(v)
        row.dec.caption, row.hex.caption, row.bin.caption = dec, hex, bin
        local color = v == 0 and COLORS.zero or COLORS.normal
        if not first and not force then
          color = COLORS.changed
          viewer.changed_at[reg] = tick
        end
        row.dec.style.font_color = color
        row.hex.style.font_color = color
        row.bin.style.font_color = color
      elseif viewer.changed_at[reg] and tick - viewer.changed_at[reg] >= HIGHLIGHT_TICKS then
        viewer.changed_at[reg] = nil
        local color = v == 0 and COLORS.zero or COLORS.normal
        row.dec.style.font_color = color
        row.hex.style.font_color = color
        row.bin.style.font_color = color
      end
    end
  end
  return true
end

on_tick = function(event)
  for index, viewer in pairs(state().viewers) do
    if not refresh(viewer, event.tick, false) then
      close_gui(game.get_player(index))
    end
  end
end

-- --------------------------------------------------------------------------
-- GUI
-- --------------------------------------------------------------------------

local function label(parent, caption, opts)
  opts = opts or {}
  local l = parent.add{type = "label", caption = caption, style = opts.style, tooltip = opts.tooltip}
  if opts.color then l.style.font_color = opts.color end
  if opts.font then l.style.font = opts.font end
  if opts.width then l.style.minimal_width = opts.width end
  return l
end

local function open_gui(player, entity)
  local screen = player.gui.screen
  if screen[FRAME] then screen[FRAME].destroy() end

  local frame = screen.add{type = "frame", name = FRAME, direction = "vertical"}
  local titlebar = frame.add{type = "flow", direction = "horizontal"}
  titlebar.drag_target = frame
  titlebar.style.horizontal_spacing = 8
  titlebar.add{type = "label", caption = {"entity-name." .. ENTITY}, style = "frame_title",
               ignored_by_interaction = true}
  local filler = titlebar.add{type = "empty-widget", style = "draggable_space_header",
                              ignored_by_interaction = true}
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  filler.style.right_margin = 4
  titlebar.add{type = "sprite-button", name = "frd_close", style = "frame_action_button",
               sprite = "utility/close", tooltip = "Close"}

  local inner = frame.add{type = "frame", name = "frd_inner", direction = "vertical",
                          style = "inside_shallow_frame_with_padding"}
  local header = inner.add{type = "flow", direction = "horizontal"}
  header.style.vertical_align = "center"
  header.style.horizontal_spacing = 12
  local status = label(header, "")
  local spacer = header.add{type = "empty-widget"}
  spacer.style.horizontally_stretchable = true
  header.add{type = "checkbox", name = "frd_freeze", caption = "Freeze", state = false,
             tooltip = "Stop updating the values (e.g. to read them while the CPU keeps running)."}

  local scroll = inner.add{type = "scroll-pane", horizontal_scroll_policy = "never",
                           vertical_scroll_policy = "auto-and-reserve-space"}
  scroll.style.maximal_height = 820
  scroll.style.top_margin = 6
  local tbl = scroll.add{type = "table", column_count = 6, style = "bordered_table"}
  tbl.style.horizontal_spacing = 14
  for _, h in ipairs({"Reg", "ABI", "Signal", "Decimal (signed)", "Hex", "Binary"}) do
    label(tbl, h, {style = "semibold_label"})
  end

  -- x0: hard-wired zero, no signal
  local dec0, hex0, bin0 = format_value(0)
  label(tbl, "x0", {style = "semibold_label"})
  label(tbl, encoder.ABI_NAMES[1], {color = COLORS.dim})
  label(tbl, "–", {color = COLORS.dim, tooltip = "x0 is hard-wired to 0 and has no signal"})
  label(tbl, dec0, {color = COLORS.zero, width = 110})
  label(tbl, hex0, {color = COLORS.zero, width = 90})
  label(tbl, bin0, {color = COLORS.zero})

  local rows, signal_ids = {}, {}
  for reg = 1, 31 do
    local name = REGISTER_SIGNALS[reg]
    label(tbl, "x" .. reg, {style = "semibold_label"})
    label(tbl, encoder.ABI_NAMES[reg + 1] .. (reg == 8 and " / fp" or ""), {color = COLORS.dim})
    if prototypes.item[name] then
      label(tbl, "[item=" .. name .. "]", {tooltip = name})
      signal_ids[reg] = {type = "item", name = name, quality = "normal"}
      rows[reg] = {
        dec = label(tbl, "", {width = 110}),
        hex = label(tbl, "", {width = 90}),
        bin = label(tbl, ""),
      }
    else
      label(tbl, "?", {color = COLORS.error, tooltip = "item '" .. name .. "' does not exist (Space Age off?)"})
      label(tbl, "n/a", {color = COLORS.error})
      label(tbl, "", {})
      label(tbl, "", {})
    end
  end

  frame.force_auto_center()
  player.opened = frame

  local viewer = {entity = entity, rows = rows, signal_ids = signal_ids, values = {}, changed_at = {},
                  status = status, frozen = false}
  state().viewers[player.index] = viewer
  script.register_on_object_destroyed(entity)
  refresh(viewer, game.tick, true)
  update_tick_handler()
end

-- --------------------------------------------------------------------------
-- Event handlers (registered by control.lua)
-- --------------------------------------------------------------------------

function M.on_init()
  state()
end

function M.on_configuration_changed()
  state()
  for _, player in pairs(game.players) do close_gui(player) end
  update_tick_handler()
end

-- on_load must not write storage; it only re-registers the tick handler if
-- GUIs were open when the game was saved.
function M.on_load()
  local s = storage.register_display
  if s and next(s.viewers) then
    script.on_event(defines.events.on_tick, on_tick)
  end
end

M.events = {
  on_gui_opened = function(event)
    local entity = event.entity
    if event.gui_type ~= defines.gui_type.entity or not (entity and entity.valid and entity.name == ENTITY) then
      return
    end
    local player = game.get_player(event.player_index)
    if player then open_gui(player, entity) end
  end,

  on_gui_closed = function(event)
    local element = event.element
    if element and element.valid and element.name == FRAME then
      close_gui(game.get_player(event.player_index))
    end
  end,

  on_gui_click = function(event)
    local element = event.element
    if element and element.valid and element.name == "frd_close" then
      close_gui(game.get_player(event.player_index))
    end
  end,

  on_gui_checked_state_changed = function(event)
    local element = event.element
    if not (element and element.valid and element.name == "frd_freeze") then return end
    local viewer = state().viewers[event.player_index]
    if viewer then
      viewer.frozen = element.state
      if not viewer.frozen then refresh(viewer, event.tick, true) end
    end
  end,

  on_object_destroyed = function()
    for index, viewer in pairs(state().viewers) do
      if not (viewer.entity and viewer.entity.valid) then close_gui(game.get_player(index)) end
    end
  end,
}

M.filters = {}

return M
