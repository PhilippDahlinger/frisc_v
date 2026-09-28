-- FRISC-V debug tools: two entities copied from vanilla ones with a custom GUI
-- (see control.lua):
--   one-line-assembler  constant combinator, tinted blue
--   register-display    display panel, tinted orange
-- No recipes on purpose: get them from the map editor or with
--   /c game.player.insert{name = "one-line-assembler"}
--   /c game.player.insert{name = "register-display"}

require("util")

local function tinted_icons(proto, tint)
  if proto.icons then
    local icons = table.deepcopy(proto.icons)
    for _, icon in pairs(icons) do icon.tint = tint end
    return icons
  end
  return {{icon = proto.icon, icon_size = proto.icon_size, tint = tint}}
end

-- Copy an entity + its item under a new name, tinting icon and body (not the shadow).
local function tinted_copy(entity_type, base_name, name, tint, order)
  local base_entity = data.raw[entity_type][base_name]
  local base_item = data.raw["item"][base_name]

  local entity = table.deepcopy(base_entity)
  entity.name = name
  entity.icons = tinted_icons(base_entity, tint)
  entity.icon = nil
  entity.icon_size = nil
  entity.minable = {mining_time = base_entity.minable and base_entity.minable.mining_time or 0.1, result = name}
  for _, direction in pairs(entity.sprites or {}) do
    if type(direction) == "table" and direction.layers then
      for _, layer in pairs(direction.layers) do
        if not layer.draw_as_shadow then layer.tint = tint end
      end
    end
  end

  local item = table.deepcopy(base_item)
  item.name = name
  item.icons = tinted_icons(base_item, tint)
  item.icon = nil
  item.icon_size = nil
  item.place_result = name
  item.order = order

  data:extend({entity, item})
end

tinted_copy("constant-combinator", "constant-combinator", "one-line-assembler",
            {r = 0.45, g = 0.8, b = 1.0, a = 1.0}, "c[combinators]-e[one-line-assembler]")
tinted_copy("display-panel", "display-panel", "register-display",
            {r = 1.0, g = 0.7, b = 0.35, a = 1.0}, "s[display-panel]-b[register-display]")
