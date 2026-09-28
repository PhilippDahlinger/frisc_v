# factorio_mod: One line assembler

A Factorio **2.1** mod that adds one item and entity: the **One line assembler**. It's a constant combinator
(tinted blue) whose GUI is replaced by a single-instruction RISC-V assembler:

* Type one RV32IMB instruction, e.g. `addi x1, x2, 23`.
* The combinator outputs the machine code on **signal D** as a **signed 32-bit
  integer** (`addi x1, x2, 23` → `D = 24182931`, `beq x1, x2, -4096` → `D = -2145353629`).
* The GUI shows, live while you type: the signed value, hex, binary split into fields, unsigned value,
  canonical form, format and extension, the immediate, a colored bit-field diagram, and a table of every field
  (bit range, binary, hex, decimal, meaning).
* An invalid instruction outputs **nothing** and the GUI shows the reason, e.g.
  `12-bit signed immediate 5000 out of range [-2048, 2047]`.
* The *Output on* checkbox is the combinator's normal on/off switch.

Supported instructions, syntax and encodings are the same as `debug_gui` (see its README). Hover the text field
in game for a summary.

## Install

Either copy (or symlink) the `one-line-assembler` folder into your Factorio `mods` folder, or build a zip:

```bash
python factorio_mod/build_mod.py     # -> factorio_mod/dist/one-line-assembler_0.1.0.zip
```

and put the zip into the `mods` folder.

## Getting the item

There is no recipe on purpose. Use the map editor (`/editor`) or:

```
/c game.player.insert{name = "one-line-assembler", count = 10}
```

## Behavior details

* The instruction text is stored as the combinator's **description**. It survives blueprints,
  copy/paste (Shift+right/left click), undo and save/load, and it shows in the entity tooltip. The output
  signal is always regenerated from that text: on opening, building, pasting and cloning.
* Only signal D is output. Anything else in the combinator's sections is removed.
* Ghosts can be configured before they're built.
* Several players can have the same assembler open; they see each other's edits live.

## Files

| File | Purpose |
|---|---|
| `one-line-assembler/info.json` | mod metadata (`factorio_version` 2.1) |
| `one-line-assembler/data.lua` | item and entity, copied from the constant combinator and tinted; no recipe |
| `one-line-assembler/control.lua` | GUI, events, writes signal D |
| `one-line-assembler/encoder.lua` | Lua port of `debug_gui/rv32_encoder.py` (pure Lua 5.2) |
| `tests/` | parity and runtime tests (below) |

## Tests

```bash
sudo apt install lua5.2          # Factorio uses Lua 5.2
python -m unittest discover -s factorio_mod/tests -v
```

* `test_lua_parity.py` runs the Lua encoder and the Python encoder (which is cross-checked against
  `llvm-mc`) on ~31,000 inputs. These are random valid instructions for every mnemonic plus mutated and invalid
  ones. Everything must match exactly: word, signed value, hex, binary, every field and meaning, and error messages.
* `test_mod_runtime.py` runs `data.lua` and `control.lua` against `tests/mock_factorio.lua`, a strict mock of
  the 2.1 runtime API. It rejects unknown GUI parameters, style properties, style/font/sprite names and invalid
  logistic filters. The scenario opens the GUI, types instructions, toggles output, runs two players, closes,
  destroys, builds from blueprint, pastes, and uses ghosts. It then types ~1,900 instructions and checks the
  exact signal D value for each.

**Not tested in the real game:** the sandbox this was built in can't download Factorio. The API names come
from the 2.1.20 runtime API definitions and the `wube/factorio-data` prototypes. Please try it in game.
Things that could only show up there are layout or visual issues, and API behavior the mock gets wrong.
