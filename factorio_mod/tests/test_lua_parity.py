"""Checks that the mod's Lua encoder behaves exactly like debug_gui/rv32_encoder.py.

The Python encoder is itself cross-checked against llvm-mc (debug_gui/tests), so
matching it field by field, including error messages, makes the Lua port trustworthy.

Needs a Lua 5.2 interpreter (Factorio uses Lua 5.2):
    python -m unittest discover -s factorio_mod/tests -v
"""

import os
import random
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MOD_DIR = os.path.join(REPO, "factorio_mod", "one-line-assembler")
sys.path.insert(0, os.path.join(REPO, "debug_gui"))
sys.path.insert(0, os.path.join(REPO, "debug_gui", "tests"))

import rv32_encoder as rv  # noqa: E402
from test_encoder import INVALID, PSEUDOS, _random_instances  # noqa: E402

LUA = next((shutil.which(n) for n in ("lua5.2", "lua52", "lua") if shutil.which(n)), None)


def python_dump(line):
    try:
        e = rv.encode(line)
    except rv.AsmError as err:
        return "ERR\t" + str(err).replace("\t", " ").replace("\n", " ")
    fields = " ;; ".join("|".join([f.name, str(f.msb), str(f.lsb), str(f.value), f.bits, f.meaning])
                         for f in e.fields)
    return "\t".join([
        "OK", str(e.word), str(e.signed), e.hex, e.bin_grouped, e.canonical, e.format_name, e.ext,
        "" if e.immediate is None else str(e.immediate), e.immediate_note, " || ".join(e.notes),
        e.pseudo or "", fields,
    ])


def lua_dump(lines):
    res = subprocess.run([LUA, os.path.join(HERE, "lua_dump.lua"), MOD_DIR],
                         input="\n".join(lines) + "\n", capture_output=True, text=True)
    if res.returncode != 0:
        raise AssertionError(f"lua failed:\n{res.stderr}")
    out = res.stdout.split("\n")[:-1]
    if len(out) != len(lines):
        raise AssertionError(f"expected {len(lines)} output lines, got {len(out)}\n{res.stderr}")
    return out


EDGE_CASES = [
    "", "   ", "# only a comment", "addi x1, x2, 23 # comment", "ADDI X1, X2, 23", "\taddi\tx1,x2,23",
    "addi x1,,x2", "addi x1, x2,", "addi x1, x2, 0x_", "addi x1, x2, 1_000", "addi x1, x2, +5",
    "addi x1, x2, --5", "addi x1, x2, 0x7FF", "addi x1, x2, -0x800", "addi x1, x2, 0b101",
    "addi x1, x2, 0o17", "addi x1, x2, 99999999999999999999", "addi x1, x2, 4503599627370495",
    "addi x1, x2, 4503599627370496", "addi x1, x2, abc", "addi x1, x2, 1.5", "addi fp, s11, 1",
    "addi x1, x2, x3", "lw x1, 4 ( x2 )", "lw x1, (x2)", "lw x1, x2", "lw x1, 4(x2)(x3)",
    "lw x1, -2048(sp)", "sw x1, 2048(sp)", "fence", "fence rw, rw", "fence wr, r", "fence 0, 0",
    "fence iorw,iorw", "fence x, r", "fence r", "fence.tso", "pause", "ecall", "ebreak",
    "ecall x1", "jal 2", "jal x1", "jalr x5", "jalr x1, x2, -2048", "jalr x1, 4(x2)", "ret x1",
    "j -1048576", "j 1048576", "lui x1, 0xFFFFF", "lui x1, 0x100000", "auipc a0, 0",
    "clz x1, x2", "rev8 a0, a1", "zext.h t0, t1", "rori x1, x2, 31", "bseti x1, x2, 32",
    "nop x1", "mv x1", "bgt x1, x2", "unknown x1", "add.uw x1, x2, x3", "csrrw x1, 0x300, x2",
    "sub x0, x0, x0", "mulh zero, ra, sp", "sltiu x1, x2, -1", "not a0, a1", "seqz a0, a1",
]


def mutate(line, r):
    parts = line.split(" ", 1)
    ops = parts[1].split(",") if len(parts) > 1 else []
    choice = r.randrange(6)
    if choice == 0 and ops:
        ops = ops[:-1]
    elif choice == 1:
        ops = ops + [" x1"]
    elif choice == 2 and ops:
        i = r.randrange(len(ops))
        ops[i] = " " + r.choice(["2048", "-2049", "4095", "4096", "-4098", "3", "1048576", "32",
                                 "-1", "0x100000", "x32", "s12", "q5", "0x_", "", "1(x2)", "(x2)"])
    elif choice == 3:
        return parts[0].upper() + (" " + ",".join(ops) if ops else "")
    elif choice == 4:
        return line + "   # trailing comment"
    else:
        return line.replace(",", " ,\t")
    return parts[0] + (" " + ",".join(ops) if ops else "")


@unittest.skipUnless(LUA, "no Lua interpreter found (install lua5.2)")
class LuaParity(unittest.TestCase):
    def compare(self, lines):
        lua = lua_dump(lines)
        diffs = []
        for line, got in zip(lines, lua):
            want = python_dump(line)
            if got != want:
                diffs.append(f"input: {line!r}\n  python: {want}\n  lua:    {got}")
        if diffs:
            self.fail(f"{len(diffs)} differences, first ones:\n" + "\n".join(diffs[:10]))

    def test_random_valid(self):
        r = random.Random(2024)
        lines = []
        for mn in list(rv.OPS) + PSEUDOS:
            lines += _random_instances(mn, r, 300)
        self.compare(lines)
        print(f"\n  {len(lines)} random valid instructions identical in Lua and Python", file=sys.stderr)

    def test_invalid_and_edge_cases(self):
        r = random.Random(99)
        lines = list(INVALID) + EDGE_CASES
        for mn in list(rv.OPS) + PSEUDOS:
            lines += [mutate(x, r) for x in _random_instances(mn, r, 40)]
        lines = [x for x in lines if "\n" not in x]
        self.compare(lines)
        n_err = sum(python_dump(x).startswith("ERR") for x in lines)
        print(f"\n  {len(lines)} edge/mutated inputs identical ({n_err} of them errors)", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
