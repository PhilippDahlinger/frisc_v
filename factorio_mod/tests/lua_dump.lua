-- Reads one instruction per line from stdin and prints the Lua encoder's
-- result as one tab-separated line per input (used by test_lua_parity.py).
--   usage: lua5.2 lua_dump.lua <mod dir> < cases.txt
package.path = arg[1] .. "/?.lua;" .. package.path
local encoder = require("encoder")

local function clean(s) return (tostring(s):gsub("[\t\n]", " ")) end

for line in io.lines() do
  local ok, res, err = pcall(encoder.encode, line)
  if not ok then
    print("BUG\t" .. clean(res))
  elseif not res then
    print("ERR\t" .. clean(err))
  else
    local fields = {}
    for _, f in ipairs(res.fields) do
      fields[#fields + 1] = table.concat({f.name, f.msb, f.lsb, string.format("%d", f.value),
                                          f.bits, f.meaning}, "|")
    end
    print(table.concat({
      "OK",
      string.format("%d", res.word),
      string.format("%d", res.signed),
      res.hex,
      res.bin_grouped,
      res.canonical,
      res.format_name,
      res.ext,
      res.immediate and string.format("%d", res.immediate) or "",
      res.immediate_note,
      table.concat(res.notes, " || "),
      res.pseudo or "",
      table.concat(fields, " ;; "),
    }, "\t"))
  end
end
