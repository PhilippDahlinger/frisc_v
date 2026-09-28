-- Drives data.lua and control.lua through the mock runtime.
--   usage: lua5.2 control_scenario.lua <mod dir> <tests dir> <cases file>
-- cases file: one "<instruction>\t<expected signed int or ERR>" per line.
local mod_dir, tests_dir, cases_file = arg[1], arg[2], arg[3]
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
  }}
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
  check(#extended == 2, "data.lua adds exactly two prototypes")
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
