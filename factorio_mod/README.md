# factorio_mod: FRISC-V Debug Tools

A Factorio **2.1** mod (internal name `one-line-assembler`) with two debug tools for the FRISC-V CPU. Neither
has a recipe, so get them from the map editor (`/editor`) or with:

```
/c game.player.insert{name = "one-line-assembler", count = 10}
/c game.player.insert{name = "register-display", count = 10}
```

## One line assembler

A constant combinator (tinted blue) whose GUI is replaced by a single-instruction RISC-V assembler:

* Type one RV32IMB instruction, e.g. `addi x1, x2, 23`.
* The combinator outputs the machine code on **signal D** as a **signed 32-bit integer**
  (`addi x1, x2, 23` → `D = 24182931`, `beq x1, x2, -4096` → `D = -2145353629`).
* The GUI shows, live while you type: the signed value, hex, binary split into fields, unsigned value,
  canonical form, format and extension, the immediate, a colored bit-field diagram, and a table of every field
  (bit range, binary, hex, decimal, meaning).
* An invalid instruction outputs **nothing** and the GUI shows the reason, e.g.
  `12-bit signed immediate 5000 out of range [-2048, 2047]`.
* The *Output on* checkbox is the combinator's normal on/off switch.
* The instruction text is stored as the combinator's **description**. It survives blueprints, copy/paste,
  undo and save/load, and it shows in the entity tooltip. The signal is regenerated from that text on opening,
  building, pasting and cloning. Ghosts can be configured before they're built.

Supported instructions, syntax and encodings are the same as `debug_gui` (see its README).

## Register display

A display panel (tinted orange). Wire it with red and/or green wire to the **register memory cell**, then open it:

* A table of all 32 registers: `x0`–`x31`, ABI name (`zero`, `ra`, `sp`, …, `s0 / fp`, …), the signal, the value
  as **signed decimal**, **hex** (two's complement) and **binary** (grouped in 4s).
* `x0` is hard-wired to 0 and has no signal. `x1`–`x31` are the first 31 signals of the Logistics group
  (Space Age):

  | | | | |
  |---|---|---|---|
  | x1 wooden-chest | x9 underground-belt | x17 burner-inserter | x25 big-electric-pole |
  | x2 iron-chest | x10 fast-underground-belt | x18 inserter | x26 substation |
  | x3 steel-chest | x11 express-underground-belt | x19 long-handed-inserter | x27 pipe |
  | x4 storage-tank | x12 turbo-underground-belt | x20 fast-inserter | x28 pipe-to-ground |
  | x5 transport-belt | x13 splitter | x21 bulk-inserter | x29 pump |
  | x6 fast-transport-belt | x14 fast-splitter | x22 stack-inserter | x30 rail |
  | x7 express-transport-belt | x15 express-splitter | x23 small-electric-pole | x31 rail-ramp |
  | x8 turbo-transport-belt | x16 turbo-splitter | x24 medium-electric-pole | |

  The mapping is the `REGISTER_SIGNALS` list at the top of `register_display.lua`.
* Values update every tick. A value that just changed is highlighted yellow for one second, zeros are grey.
  *Freeze* holds the current values. The header says which wires are connected (red and green are summed,
  like any circuit input).
* **No overhead when closed:** the mod's `on_tick` handler only exists while at least one register display
  window is open. It is removed when the last one closes, and restored after loading a save. While open, it
  reads 31 signals per tick and only rewrites rows whose value changed.

## Install

Either copy (or symlink) the `one-line-assembler` folder into your Factorio `mods` folder, or build a zip:

```bash
python factorio_mod/build_mod.py     # -> factorio_mod/dist/one-line-assembler_<version>.zip
```

## Files

| File | Purpose |
|---|---|
| `one-line-assembler/info.json` | mod metadata (`factorio_version` 2.1) |
| `one-line-assembler/data.lua` | both entities and items, tinted copies of constant combinator and display panel; no recipes |
| `one-line-assembler/control.lua` | dispatches events to the two feature modules |
| `one-line-assembler/assembler.lua` | One line assembler GUI and signal output |
| `one-line-assembler/register_display.lua` | Register display GUI, register-to-signal mapping, on-demand `on_tick` |
| `one-line-assembler/encoder.lua` | Lua port of `debug_gui/rv32_encoder.py` (pure Lua 5.2) |
| `tests/` | parity and runtime tests (below) |

## Tests

```bash
sudo apt install lua5.2          # Factorio uses Lua 5.2
python -m unittest discover -s factorio_mod/tests -v
```

* `test_lua_parity.py` runs the Lua encoder and the Python encoder (which is cross-checked against
  `llvm-mc`) on ~31,000 inputs. Everything must match exactly: word, signed value, fields, meanings and error messages.
* `test_mod_runtime.py` runs `data.lua` and `control.lua` against `tests/mock_factorio.lua`, a strict mock of
  the 2.1 runtime API. It rejects unknown GUI parameters, style properties, style/font/sprite names, invalid
  logistic filters and malformed signal reads.
  * Assembler: opening, typing, on/off, two players, closing, destroying, blueprints, pasting and ghosts,
    plus ~1,900 instructions with the exact signal D value checked for each.
  * Register display:
    * the mapping and ABI names, and live updates with highlight and fade
    * red + green wires summed, freeze, two viewers
    * `on_tick` removed after the last window closes, with zero signal reads while closed
    * `on_load` restores the handler; missing wires, a destroyed entity and missing items are handled
    * decimal/hex/binary formatting checked against Python for 3,000 random values

**Not tested in the real game:** the sandbox this was built in can't download Factorio. API names come
from the 2.1.20 runtime API definitions and the `wube/factorio-data` prototypes. Please try it in game.
Things that could only show up there are layout or visual issues, and API behavior the mock gets wrong.
