-- Drives data.lua and control.lua through the mock runtime.
--   usage: lua5.2 control_scenario.lua <mod dir> <tests dir> <cases file> <values file>
-- cases file: one "<instruction>\t<expected signed int or ERR>" per line.
-- values file: one "<int32>\t<dec>\t<unsigned>\t<hex>\t<bin>" per line (expected register formatting).
local mod_dir, tests_dir, cases_file, values_file = arg[1], arg[2], arg[3], arg[4]
package.path = mod_dir .. "/?.lua;" .. tests_dir .. "/?.lua;" .. package.path

local checks = 0
local function check(cond, msg)
  checks = checks + 1
  if not cond then error("CHECK FAILED: " .. msg, 2) end
end

-- ---------------------------------------------------------------- data stage
do
  -- stand-ins for core's util and the base prototypes the mod copies
  package.preload["util"] = function()
    function table.deepcopy(o)
      if type(o) ~= "table" then return o end
      local c = {}
      for k, v in pairs(o) do c[table.deepcopy(k)] = table.deepcopy(v) end
      return setmetatable(c, getmetatable(o))
    end
    return {}
  end
  local function dir_sprite()
    return {layers = {{filename = "body.png"}, {filename = "shadow.png", draw_as_shadow = true}}}
  end
  _G.data = {raw = {
    ["item"] = {["constant-combinator"] = {type = "item", name = "constant-combinator",
      icon = "__base__/graphics/icons/constant-combinator.png", subgroup = "circuit-network",
      place_result = "constant-combinator", order = "c[combinators]-d[constant-combinator]", stack_size = 50}},
    ["constant-combinator"] = {["constant-combinator"] = {type = "constant-combinator",
      name = "constant-combinator", icon = "__base__/graphics/icons/constant-combinator.png",
      minable = {mining_time = 0.1, result = "constant-combinator"},
      sprites = {north = dir_sprite(), east = dir_sprite(), south = dir_sprite(), west = dir_sprite()}}},
    ["display-panel"] = {["display-panel"] = {type = "display-panel", name = "display-panel",
      icon = "__base__/graphics/icons/display-panel.png", icon_size = 64,
      minable = {mining_time = 0.2, result = "display-panel"},
      sprites = {north = dir_sprite(), east = dir_sprite(), south = dir_sprite(), west = dir_sprite()}}},
  }}
  data.raw["item"]["display-panel"] = {type = "item", name = "display-panel",
    icon = "__base__/graphics/icons/display-panel.png", icon_size = 64, subgroup = "circuit-network",
    order = "s[display-panel]", place_result = "display-panel", stack_size = 10}
  local extended = {}
  function data.extend(self, list)
    for _, p in ipairs(list) do
      data.raw[p.type] = data.raw[p.type] or {}
      check(not data.raw[p.type][p.name], "duplicate prototype " .. p.name)
      data.raw[p.type][p.name] = p
      extended[#extended + 1] = p
    end
  end
  dofile(mod_dir .. "/data.lua")
  check(#extended == 4, "data.lua adds exactly four prototypes")
  local d = data.raw["display-panel"]["register-display"]
  local di = data.raw["item"]["register-display"]
  check(d and d.minable.result == "register-display" and d.minable.mining_time == 0.2, "display mines into item")
  check(di and di.place_result == "register-display" and di.icons[1].tint, "display item places entity")
  check(d.sprites.west.layers[1].tint and not d.sprites.west.layers[2].tint, "display body tinted")
  check(data.raw["display-panel"]["display-panel"].sprites.north.layers[1].tint == nil, "base panel untouched")
  local e = data.raw["constant-combinator"]["one-line-assembler"]
  local i = data.raw["item"]["one-line-assembler"]
  check(e and e.minable.result == "one-line-assembler", "entity mines into its own item")
  check(i and i.place_result == "one-line-assembler", "item places the entity")
  check(e.icon == nil and e.icons[1].tint and i.icons[1].tint, "icons are tinted")
  check(e.sprites.north.layers[1].tint and not e.sprites.north.layers[2].tint, "body tinted, shadow not")
  check(data.raw["constant-combinator"]["constant-combinator"].sprites.north.layers[1].tint == nil,
        "base combinator untouched")
  check(data.raw["recipe"] == nil, "no recipe (editor/cheat only)")
  _G.data = nil
end

-- ------------------------------------------------------------- control stage
local mock = require("mock_factorio")
mock.install()
dofile(mod_dir .. "/control.lua")
local encoder = require("encoder")
mock.handlers.init()

local p1 = mock.add_player(1)
local p2 = mock.add_player(2)
local ENTITY_GUI = defines.gui_type.entity

local function frame_of(p) return p.gui.screen.ola_frame end
local function textfield(p) return frame_of(p).ola_inner.ola_input_row.ola_input end
local function checkbox(p) return frame_of(p).ola_inner.ola_input_row.ola_enabled end
local function type_text(p, text)
  local tf = textfield(p)
  tf.text = text
  mock.fire("on_gui_text_changed", {player_index = p.index, element = tf, text = text})
end
local function output_of(entity)
  local outs = mock.outputs(entity)
  if #outs == 0 then return nil end
  check(#outs == 1, "exactly one output signal")
  local o = outs[1]
  check(o.type == "virtual" and o.name == "signal-D" and o.quality == "normal", "output is signal D")
  return o.min
end

-- build + open
local ent = mock.new_entity("one-line-assembler")
mock.fire("on_built_entity", {entity = ent, player_index = 1})
check(output_of(ent) == nil, "fresh assembler outputs nothing")
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = ent})
check(frame_of(p1) and p1.opened == frame_of(p1), "GUI opened and set as player.opened")
check(textfield(p1).text == "", "empty text field on a fresh assembler")
check(mock.focused == textfield(p1), "text field focused")
check(mock.all_captions(frame_of(p1)):find("Type an instruction", 1, true), "hint shown when empty")

-- the example from the original request
type_text(p1, "addi x1, x2, 23")
check(output_of(ent) == 24182931, "addi x1, x2, 23 -> 24182931")
check(ent.combinator_description == "addi x1, x2, 23", "text stored in combinator_description")
local captions = mock.all_captions(frame_of(p1))
for _, s in ipairs({"0x01710093", "000000010111 00010 000 00001 0010011", "24182931", "addi x1, x2, 23",
                    "I-type", "imm[11:0]", "OP-IMM", "x2 (sp)", "0010011"}) do
  check(captions:find(s, 1, true), "GUI shows '" .. s .. "'")
end

-- negative signed values
type_text(p1, "beq x1, x2, -4096")
check(output_of(ent) == -2145353629, "beq x1, x2, -4096 -> -2145353629")
check(mock.all_captions(frame_of(p1)):find("-2145353629", 1, true), "GUI shows negative value")

-- invalid input clears the output and shows the error
type_text(p1, "addi x1, x2, 5000")
check(output_of(ent) == nil, "invalid instruction outputs nothing")
check(mock.all_captions(frame_of(p1)):find("out of range [-2048, 2047]", 1, true), "error shown")

-- on/off switch
type_text(p1, "lw a0, -4(sp)")
checkbox(p1).state = false
mock.fire("on_gui_checked_state_changed", {player_index = 1, element = checkbox(p1)})
check(ent.__cb.enabled == false, "checkbox switches the combinator off")
check(output_of(ent) == -4119293, "signal kept while switched off")
check(mock.all_captions(frame_of(p1)):find("switched off", 1, true), "switched-off status shown")
checkbox(p1).state = true
mock.fire("on_gui_checked_state_changed", {player_index = 1, element = checkbox(p1)})
check(ent.__cb.enabled == true, "checkbox switches the combinator on")

-- second player sees live updates
mock.fire("on_gui_opened", {player_index = 2, gui_type = ENTITY_GUI, entity = ent})
check(textfield(p2).text == "lw a0, -4(sp)", "second player sees stored text")
type_text(p1, "mul x1, x2, x3")
check(textfield(p2).text == "mul x1, x2, x3", "second player's text field follows")
check(mock.all_captions(frame_of(p2)):find("0x023100B3", 1, true), "second player's result follows")

-- close via button (p2) and via escape / on_gui_closed (p1)
mock.fire("on_gui_click", {player_index = 2, element = frame_of(p2).children[1].ola_close})
check(frame_of(p2) == nil and storage.open[2] == nil, "close button closes the GUI")
mock.fire("on_gui_closed", {player_index = 1, element = frame_of(p1), gui_type = defines.gui_type.custom})
check(frame_of(p1) == nil and storage.open[1] == nil, "on_gui_closed closes the GUI")

-- reopening shows the stored instruction; stale signal is regenerated
ent.__cb.sections[1].filters = {}
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = ent})
check(textfield(p1).text == "mul x1, x2, x3" and output_of(ent) == 36765875, "reopen re-applies text")

-- entity removed while GUI open
ent.valid = false
mock.fire("on_object_destroyed", {registration_number = 1, useful_id = 0, type = 1})
check(frame_of(p1) == nil and storage.open[1] == nil, "GUI closed when entity is destroyed")

-- built from blueprint / pasted settings: output regenerated from description
local bp = mock.new_entity("one-line-assembler")
bp.combinator_description = "jal ra, -2"
mock.fire("on_robot_built_entity", {entity = bp})
check(output_of(bp) == -3857, "blueprint-built assembler outputs its instruction")
bp.combinator_description = "sub x3, x4, x5"
mock.fire("on_entity_settings_pasted", {destination = bp, source = bp, player_index = 1})
check(output_of(bp) == 0x405201B3, "pasted settings re-applied")
-- extra sections from elsewhere are removed
bp.__cb.add_section().set_slot(1, {value = {type = "virtual", name = "signal-A", quality = "normal"}, min = 5})
mock.fire("script_raised_built", {entity = bp})
check(#mock.outputs(bp) == 1 and output_of(bp) == 0x405201B3, "only signal D remains")

-- other entities are ignored
local plain = mock.new_entity("constant-combinator")
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = plain})
check(frame_of(p1) == nil, "vanilla constant combinator keeps its own GUI")
mock.fire("on_entity_settings_pasted", {destination = plain, source = bp, player_index = 1})
check(#mock.outputs(plain) == 0, "vanilla combinator not touched")

-- ghosts of the assembler get the GUI too
local ghost = mock.new_entity("entity-ghost", {type = "entity-ghost", ghost_name = "one-line-assembler"})
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = ghost})
type_text(p1, "ecall")
check(output_of(ghost) == 115 and ghost.combinator_description == "ecall", "ghost configurable")
mock.fire("on_gui_closed", {player_index = 1, element = frame_of(p1), gui_type = defines.gui_type.custom})

-- configuration change closes stale GUIs
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = bp})
mock.handlers.config({})
check(frame_of(p1) == nil, "configuration change closes GUIs")

-- ------------------------------------------------------ register display
local rd = require("register_display")
local ON_TICK = defines.events.on_tick
local function display_frame(p) return p.gui.screen.frd_frame end
local function reg_row(p, reg)
  -- table children: 7 header cells, then 7 cells per register x0..x31:
  -- ABI | reg | signal | signed | unsigned | hex | binary
  local tbl = display_frame(p).frd_inner.children[2].children[1]
  check(tbl.column_count == 7, "register table has 7 columns")
  local base = 7 + reg * 7
  local c = tbl.children
  return {abi = c[base + 1], reg = c[base + 2], sig = c[base + 3], dec = c[base + 4], udec = c[base + 5],
          hex = c[base + 6], bin = c[base + 7]}
end
local function color_of(el) return el.style.font_color end

check(#rd.REGISTER_SIGNALS == 31, "31 register signals")
check(rd.REGISTER_SIGNALS[1] == "wooden-chest" and rd.REGISTER_SIGNALS[31] == "rail-ramp", "x1..x31 mapping")
check(mock.handlers[ON_TICK] == nil, "no on_tick handler before any display GUI is open")

local disp = mock.new_entity("register-display", {type = "display-panel"})
local regs = {["wooden-chest"] = 23, ["iron-chest"] = -1, ["rail-ramp"] = -2147483648, ["stack-inserter"] = 2147483647}
mock.connect(disp, 0, regs)
mock.run_ticks(5)
check(disp.__get_signal_calls == 0, "nothing is read while no GUI is open")

mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = disp})
check(display_frame(p1) and p1.opened == display_frame(p1), "display GUI opened")
check(mock.handlers[ON_TICK] ~= nil, "on_tick registered while GUI open")
local r0, r1, r2, r8 = reg_row(p1, 0), reg_row(p1, 1), reg_row(p1, 2), reg_row(p1, 8)
check(r0.reg.caption == "x0" and r0.abi.caption == "zero" and r0.dec.caption == "0", "x0 row")
check(r1.reg.caption == "x1" and r1.abi.caption == "ra" and r1.sig.caption == "[item=wooden-chest]", "x1 = ra = wooden chest")
check(r1.dec.caption == "23" and r1.udec.caption == "23" and r1.hex.caption == "0x00000017"
      and r1.bin.caption == "0000 0000 0000 0000 0000 0000 0001 0111", "x1 value")
check(r2.abi.caption == "sp" and r2.dec.caption == "-1" and r2.udec.caption == "4294967295"
      and r2.hex.caption == "0xFFFFFFFF", "x2 = sp = -1 / 4294967295")
local header = display_frame(p1).frd_inner.children[2].children[1].children
check(header[1].caption == "ABI" and header[2].caption == "Reg" and header[5].caption == "Unsigned", "header order")
for reg = 0, 31 do
  local row = reg_row(p1, reg)
  check(row.abi.style_name == "bold_label" and row.reg.caption == "x" .. reg, "ABI bold first, then x" .. reg)
end
check(r8.abi.caption == "s0 / fp", "x8 = s0 / fp")
check(reg_row(p1, 31).dec.caption == "-2147483648" and reg_row(p1, 31).udec.caption == "2147483648"
      and reg_row(p1, 31).hex.caption == "0x80000000", "x31 = INT32_MIN")
check(reg_row(p1, 22).dec.caption == "2147483647" and reg_row(p1, 22).sig.caption == "[item=stack-inserter]", "x22 = stack inserter")
check(reg_row(p1, 5).dec.caption == "0" and color_of(reg_row(p1, 5).dec)[1] < 0.6, "unset register shows grey 0")
check(mock.all_captions(display_frame(p1)):find("Reading red wire", 1, true), "wire status shown")

-- live update with highlight, then highlight fades
regs["wooden-chest"] = 42
mock.run_ticks(1)
check(r1.dec.caption == "42", "value updates on tick")
check(color_of(r1.dec)[3] < 0.5 and color_of(r1.udec)[3] < 0.5 and color_of(r1.bin)[3] < 0.5,
      "changed value highlighted in all value columns")
mock.run_ticks(59)
check(color_of(r1.dec)[3] < 0.5, "still highlighted before one second")
mock.run_ticks(1)
check(color_of(r1.dec)[3] == 1 and color_of(r1.udec)[3] == 1, "highlight gone after one second")

-- green wire adds to red (circuit networks sum)
mock.connect(disp, 1, {["wooden-chest"] = 8})
mock.run_ticks(30)
check(r1.dec.caption == "50", "red + green are summed")
check(mock.all_captions(display_frame(p1)):find("Reading red + green wire", 1, true), "both wires detected")

-- freeze
local freeze = display_frame(p1).frd_inner.children[1].frd_freeze
freeze.state = true
mock.fire("on_gui_checked_state_changed", {player_index = 1, element = freeze})
regs["wooden-chest"] = 1000
mock.run_ticks(3)
check(r1.dec.caption == "50", "frozen display does not update")
freeze.state = false
mock.fire("on_gui_checked_state_changed", {player_index = 1, element = freeze})
check(r1.dec.caption == "1008", "unfreeze refreshes immediately")

-- second viewer; handler stays until the last one closes
mock.fire("on_gui_opened", {player_index = 2, gui_type = ENTITY_GUI, entity = disp})
check(reg_row(p2, 1).dec.caption == "1008", "second player sees values")
mock.fire("on_gui_click", {player_index = 2, element = display_frame(p2).children[1].frd_close})
check(display_frame(p2) == nil and mock.handlers[ON_TICK] ~= nil, "p2 closed, tick handler kept for p1")
mock.fire("on_gui_closed", {player_index = 1, element = display_frame(p1), gui_type = defines.gui_type.custom})
check(display_frame(p1) == nil and mock.handlers[ON_TICK] == nil, "last GUI closed -> on_tick unregistered")
local calls = disp.__get_signal_calls
mock.run_ticks(100)
check(disp.__get_signal_calls == calls, "zero reads after closing")

-- on_load re-registers the tick handler for GUIs open at save time
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = disp})
mock.handlers[ON_TICK] = nil           -- simulate a fresh load: handlers are not saved
mock.handlers.load()
check(mock.handlers[ON_TICK] ~= nil, "on_load restores on_tick when a display GUI is open")

-- wire removed, then entity destroyed
mock.connect(disp, 0, nil); mock.connect(disp, 1, nil)
mock.run_ticks(30)
check(mock.all_captions(display_frame(p1)):find("No wire connected", 1, true), "missing wire reported")
check(reg_row(p1, 1).dec.caption == "0" and reg_row(p1, 2).dec.caption == "0", "values drop to 0 without wire")
disp.valid = false
mock.fire("on_object_destroyed", {registration_number = 2, useful_id = 0, type = 1})
check(display_frame(p1) == nil and mock.handlers[ON_TICK] == nil, "destroyed entity closes GUI + unregisters")

-- the assembler and the display do not interfere
local disp2 = mock.new_entity("register-display", {type = "display-panel"})
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = disp2})
check(frame_of(p1) == nil and display_frame(p1) ~= nil, "display entity opens only the display GUI")
mock.fire("on_gui_closed", {player_index = 1, element = display_frame(p1), gui_type = defines.gui_type.custom})
local vanilla_panel = mock.new_entity("display-panel", {type = "display-panel"})
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = vanilla_panel})
check(display_frame(p1) == nil, "vanilla display panel keeps its own GUI")

-- missing item (e.g. Space Age disabled): row shows n/a, never read
prototypes.item["rail-ramp"] = nil
local disp3 = mock.new_entity("register-display", {type = "display-panel"})
mock.connect(disp3, 0, {["wooden-chest"] = 7})
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = disp3})
mock.run_ticks(2)
check(reg_row(p1, 31).dec.caption == "n/a" and reg_row(p1, 1).dec.caption == "7", "missing item handled")
mock.fire("on_gui_closed", {player_index = 1, element = display_frame(p1), gui_type = defines.gui_type.custom})
prototypes.item["rail-ramp"] = {name = "rail-ramp"}

-- value formatting vs Python, for many values
local nvals = 0
for line in io.lines(values_file) do
  local v, dec, udec, hex, bin = line:match("^(.-)\t(.-)\t(.-)\t(.-)\t(.*)$")
  local d2, u2, h2, b2 = rd.format_value(tonumber(v))
  check(d2 == dec and u2 == udec and h2 == hex and b2 == bin,
        "format " .. v .. ": " .. d2 .. " " .. u2 .. " " .. h2 .. " " .. b2)
  nvals = nvals + 1
end
check(nvals > 1000, "formatting cases present")

-- bulk: every case through the full GUI path
local target = mock.new_entity("one-line-assembler")
mock.fire("on_gui_opened", {player_index = 1, gui_type = ENTITY_GUI, entity = target})
local n = 0
for line in io.lines(cases_file) do
  local text, expected = line:match("^(.-)\t(.*)$")
  type_text(p1, text)
  local out = output_of(target)
  if expected == "ERR" then
    check(out == nil, "no output for invalid '" .. text .. "'")
  else
    check(out == tonumber(expected), "'" .. text .. "' -> " .. expected .. ", got " .. tostring(out))
    check(mock.all_captions(frame_of(p1)):find(expected, 1, true), "value visible for '" .. text .. "'")
  end
  n = n + 1
end

print(string.format("PASS %d checks, %d bulk instructions", checks, n))
