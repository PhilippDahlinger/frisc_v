-- One line assembler: a constant combinator with a custom GUI (see control.lua).
-- No recipe on purpose: get it from the map editor or with
--   /c game.player.insert{name = "one-line-assembler"}

require("util")

local NAME = "one-line-assembler"
local TINT = {r = 0.45, g = 0.8, b = 1.0, a = 1.0}

local base_item = data.raw["item"]["constant-combinator"]
local base_entity = data.raw["constant-combinator"]["constant-combinator"]

local function tinted_icons(proto)
  if proto.icons then
    local icons = table.deepcopy(proto.icons)
    for _, icon in pairs(icons) do icon.tint = TINT end
    return icons
  end
  return {{icon = proto.icon, icon_size = proto.icon_size, tint = TINT}}
end

local entity = table.deepcopy(base_entity)
entity.name = NAME
entity.icons = tinted_icons(base_entity)
entity.icon = nil
entity.icon_size = nil
entity.minable = {mining_time = 0.1, result = NAME}

-- Tint the combinator body (not the shadow) so it can be told apart in the world.
for _, direction in pairs(entity.sprites or {}) do
  if type(direction) == "table" and direction.layers then
    for _, layer in pairs(direction.layers) do
      if not layer.draw_as_shadow then layer.tint = TINT end
    end
  end
end

local item = table.deepcopy(base_item)
item.name = NAME
item.icons = tinted_icons(base_item)
item.icon = nil
item.icon_size = nil
item.place_result = NAME
item.order = "c[combinators]-e[one-line-assembler]"

data:extend({entity, item})
