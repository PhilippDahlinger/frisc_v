-- One line assembler: replaces the constant combinator GUI with an RV32IMB
-- single-instruction assembler. The machine code is output on signal D as a
-- signed 32-bit integer.
--
-- The instruction text lives in the entity's combinator_description, so it
-- survives blueprints, copy/paste and save/load, and shows in the tooltip.
-- The output signal is always regenerated from that text.

local encoder = require("encoder")

local ENTITY = "one-line-assembler"
local OUTPUT_SIGNAL = {type = "virtual", name = "signal-D", quality = "normal"}
local FRAME = "ola_frame"

local COLORS = {
  opcode = {1.0, 0.62, 0.58},
  funct = {1.0, 0.86, 0.45},
  reg = {0.55, 0.95, 0.65},
  imm = {0.6, 0.78, 1.0},
  error = {1.0, 0.42, 0.35},
  ok = {0.5, 0.95, 0.5},
  dim = {0.7, 0.7, 0.7},
}

local function field_kind(name)
  if name == "opcode" then return "opcode" end
  if name == "rd" or name == "rs1" or name == "rs2" then return "reg" end
  if name:sub(1, 5) == "funct" or name == "fm" or name:find("fixed", 1, true) then return "funct" end
  return "imm"
end

local function fmt_int(v) return string.format("%d", v) end

-- --------------------------------------------------------------------------
-- Entity access
-- --------------------------------------------------------------------------

local function is_assembler(entity)
  if not (entity and entity.valid) then return false end
  if entity.name == ENTITY then return true end
  return entity.type == "entity-ghost" and entity.ghost_name == ENTITY
end

local function get_text(entity)
  local ok, text = pcall(function() return entity.combinator_description end)
  return ok and text or ""
end

local function set_text(entity, text)
  pcall(function() entity.combinator_description = text end)
end

local function get_behavior(entity)
  local ok, cb = pcall(entity.get_or_create_control_behavior)
  if ok then return cb end
  return nil
end

local function output_enabled(entity)
  local cb = get_behavior(entity)
  return cb == nil or cb.enabled
end

-- Make the combinator output exactly `value` on signal D (nothing if nil).
local function write_output(entity, value)
  local cb = get_behavior(entity)
  if not cb then return end
  for i = cb.sections_count, 2, -1 do cb.remove_section(i) end
  local section = cb.get_section(1) or cb.add_section()
  if not section then return end
  if section.group ~= "" then section.group = "" end
  section.filters = {}
  if value then
    section.set_slot(1, {value = OUTPUT_SIGNAL, min = value})
  end
end

-- Encode `text`, store it on the entity and update the output signal.
-- Returns result, error_message (exactly one of them is non-nil).
-- If the signal could not be written, the error is kept in result.write_error.
local function apply(entity, text)
  set_text(entity, text)
  local ok, result, err = pcall(encoder.encode, text)
  if not ok then
    result, err = nil, "internal error: " .. tostring(result)
  end
  local written, write_err = pcall(write_output, entity, result and result.signed or nil)
  if result and not written then
    result.write_error = "could not set the output signal: " .. tostring(write_err)
  end
  return result, err
end

-- --------------------------------------------------------------------------
-- GUI
-- --------------------------------------------------------------------------

local function label(parent, caption, opts)
  opts = opts or {}
  local l = parent.add{type = "label", caption = caption, style = opts.style, tooltip = opts.tooltip}
  if opts.color then l.style.font_color = opts.color end
  if opts.font then l.style.font = opts.font end
  if opts.single_line == false then l.style.single_line = false end
  if opts.width then l.style.maximal_width = opts.width end
  return l
end

local function show_result(frame, entity, result, err)
  local body = frame.ola_inner.ola_result
  body.clear()

  local status = body.add{type = "label", name = "ola_status"}
  status.style.single_line = false
  status.style.maximal_width = 680
  if result then
    if result.write_error then
      status.caption = result.write_error
      status.style.font_color = COLORS.error
    elseif output_enabled(entity) then
      status.caption = "OK: outputting [virtual-signal=signal-D] = " .. fmt_int(result.signed)
      status.style.font_color = COLORS.ok
    else
      status.caption = "OK, but the output is switched off"
      status.style.font_color = COLORS.funct
    end
  elseif err == "empty input" then
    status.caption = "Type an instruction, e.g.  addi x1, x2, 23   (hover the text field for help)"
    status.style.font_color = COLORS.dim
    return
  else
    status.caption = err
    status.style.font_color = COLORS.error
    return
  end

  -- machine code and instruction info
  local out = body.add{type = "table", column_count = 2}
  out.style.horizontal_spacing = 16
  out.style.vertical_spacing = 2
  out.style.top_margin = 6
  local function row(name, value, opts)
    label(out, name, {style = "semibold_label"})
    return label(out, value, opts)
  end
  row("Signal D (signed)", "[virtual-signal=signal-D] " .. fmt_int(result.signed), {font = "default-large-bold"})
  row("Hex", result.hex, {font = "default-large"})
  row("Binary", result.bin_grouped, {font = "default-large"})
  row("Unsigned", fmt_int(result.word))
  row("Encoded as", result.canonical)
  row("Format", result.format_name .. "   ·   extension: " .. result.ext)
  if result.immediate then
    local imm_hex = "0x" .. encoder.hex_str(result.immediate % 4294967296, 8)
    row("Immediate", fmt_int(result.immediate) .. "  (" .. imm_hex .. ")   ·   " .. result.immediate_note,
        {single_line = false, width = 520})
  end
  if #result.notes > 0 then
    row("Notes", table.concat(result.notes, "\n"), {single_line = false, width = 520})
  end

  -- bit-field diagram: bit range / bits / field name per column
  local diagram = body.add{type = "table", column_count = #result.fields, style = "bordered_table"}
  diagram.style.top_margin = 8
  for _, f in ipairs(result.fields) do
    local range = f.msb == f.lsb and fmt_int(f.msb) or (fmt_int(f.msb) .. " - " .. fmt_int(f.lsb))
    label(diagram, range, {color = COLORS.dim, font = "default-small"})
  end
  for _, f in ipairs(result.fields) do
    label(diagram, f.bits, {color = COLORS[field_kind(f.name)], font = "default-large-bold"})
  end
  for _, f in ipairs(result.fields) do
    label(diagram, f.name, {font = "default-small-semibold"})
  end

  -- field table
  local fields = body.add{type = "table", column_count = 6, style = "bordered_table"}
  fields.style.top_margin = 8
  for _, h in ipairs({"Field", "Bits", "Binary", "Hex", "Decimal", "Meaning"}) do
    label(fields, h, {style = "semibold_label"})
  end
  for _, f in ipairs(result.fields) do
    local range = f.msb == f.lsb and ("[" .. f.msb .. "]") or ("[" .. f.msb .. ":" .. f.lsb .. "]")
    label(fields, f.name, {color = COLORS[field_kind(f.name)]})
    label(fields, range)
    label(fields, f.bits)
    label(fields, "0x" .. encoder.hex_str(f.value, math.floor((f.width + 3) / 4)))
    label(fields, fmt_int(f.value))
    label(fields, f.meaning)
  end
end

local function build_gui(player, entity)
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
  titlebar.add{type = "sprite-button", name = "ola_close", style = "frame_action_button",
               sprite = "utility/close", tooltip = "Close"}

  local inner = frame.add{type = "frame", name = "ola_inner", direction = "vertical",
                          style = "inside_shallow_frame_with_padding"}
  inner.style.minimal_width = 700

  local input_row = inner.add{type = "flow", name = "ola_input_row", direction = "horizontal"}
  input_row.style.vertical_align = "center"
  input_row.style.horizontal_spacing = 8
  label(input_row, "Instruction:", {style = "semibold_label"})
  local textfield = input_row.add{type = "textfield", name = "ola_input", text = get_text(entity),
                                  tooltip = encoder.SUPPORTED_HELP, lose_focus_on_confirm = true}
  textfield.style.width = 420
  textfield.style.font = "default-large"
  input_row.add{type = "checkbox", name = "ola_enabled", caption = "Output on",
                state = output_enabled(entity),
                tooltip = "Switches the combinator output on or off (same as the on/off switch of a constant combinator)."}

  inner.add{type = "flow", name = "ola_result", direction = "vertical"}

  frame.force_auto_center()
  player.opened = frame
  textfield.focus()
  return frame
end

local function close_gui(player)
  if not player then return end
  storage.open[player.index] = nil
  local frame = player.gui.screen[FRAME]
  if frame and frame.valid then frame.destroy() end
end

-- Re-render the GUI of every player looking at `entity`.
-- `skip_text_for` keeps the text field of the player who is typing untouched.
local function refresh_viewers(entity, result, err, skip_text_for)
  for index, open in pairs(storage.open) do
    local player = game.get_player(index)
    local frame = player and player.gui.screen[FRAME]
    if frame and frame.valid and open == entity then
      if index ~= skip_text_for then
        frame.ola_inner.ola_input_row.ola_input.text = get_text(entity)
      end
      frame.ola_inner.ola_input_row.ola_enabled.state = output_enabled(entity)
      show_result(frame, entity, result, err)
    end
  end
end

local function open_gui(player, entity)
  local frame = build_gui(player, entity)
  storage.open[player.index] = entity
  script.register_on_object_destroyed(entity)
  -- re-apply so the output always matches the stored text
  local result, err = apply(entity, get_text(entity))
  show_result(frame, entity, result, err)
end

-- --------------------------------------------------------------------------
-- Events
-- --------------------------------------------------------------------------

script.on_init(function()
  storage.open = {}
end)

script.on_configuration_changed(function()
  storage.open = storage.open or {}
  for _, player in pairs(game.players) do close_gui(player) end
end)

script.on_event(defines.events.on_gui_opened, function(event)
  if event.gui_type ~= defines.gui_type.entity or not is_assembler(event.entity) then return end
  local player = game.get_player(event.player_index)
  if player then open_gui(player, event.entity) end
end)

script.on_event(defines.events.on_gui_closed, function(event)
  local element = event.element
  if element and element.valid and element.name == FRAME then
    close_gui(game.get_player(event.player_index))
  end
end)

script.on_event(defines.events.on_gui_click, function(event)
  local element = event.element
  if element and element.valid and element.name == "ola_close" then
    close_gui(game.get_player(event.player_index))
  end
end)

script.on_event(defines.events.on_gui_text_changed, function(event)
  local element = event.element
  if not (element and element.valid and element.name == "ola_input") then return end
  local player = game.get_player(event.player_index)
  local entity = storage.open[event.player_index]
  if not is_assembler(entity) then
    close_gui(player)
    return
  end
  local result, err = apply(entity, event.text)
  refresh_viewers(entity, result, err, event.player_index)
end)

script.on_event(defines.events.on_gui_checked_state_changed, function(event)
  local element = event.element
  if not (element and element.valid and element.name == "ola_enabled") then return end
  local entity = storage.open[event.player_index]
  if not is_assembler(entity) then
    close_gui(game.get_player(event.player_index))
    return
  end
  local cb = get_behavior(entity)
  if cb then cb.enabled = element.state end
  local result, err = apply(entity, get_text(entity))
  refresh_viewers(entity, result, err, nil)
end)

script.on_event(defines.events.on_object_destroyed, function()
  for index, entity in pairs(storage.open) do
    if not (entity and entity.valid) then close_gui(game.get_player(index)) end
  end
end)

-- The description is the source of truth: whenever an assembler is built
-- (blueprint, robot, undo, clone) or gets pasted settings, regenerate its output.
local function reapply(entity)
  if is_assembler(entity) then
    local result, err = apply(entity, get_text(entity))
    refresh_viewers(entity, result, err, nil)
  end
end

local FILTER = {{filter = "name", name = ENTITY}, {filter = "ghost_name", name = ENTITY}}
for _, ev in pairs({"on_built_entity", "on_robot_built_entity", "on_space_platform_built_entity",
                    "script_raised_built", "script_raised_revive"}) do
  script.on_event(defines.events[ev], function(event) reapply(event.entity) end, FILTER)
end
script.on_event(defines.events.on_entity_cloned, function(event) reapply(event.destination) end, FILTER)
script.on_event(defines.events.on_entity_settings_pasted, function(event) reapply(event.destination) end)
