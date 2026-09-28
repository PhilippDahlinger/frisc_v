"""Tests for the RV32IMB encoder and the number converter.

Run from the debug_gui folder:   python -m unittest discover -s tests -v

If LLVM's `llvm-mc` is installed, every instruction is additionally
cross-checked against it with thousands of random operand combinations.
"""

import os
import random
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numconv  # noqa: E402
import rv32_encoder as rv  # noqa: E402

LLVM_MC = shutil.which("llvm-mc")
LLVM_ARGS = ["-triple=riscv32", "-mattr=+m,+zba,+zbb,+zbs,+zihintpause", "-show-encoding"]

# (assembly, expected word) -- values produced by llvm-mc 18
GOLDEN = [
    ("addi x1, x2, 23", 0x01710093),
    ("addi x1, x2, -1", 0xFFF10093),
    ("lw a0, -4(sp)", 0xFFC12503),
    ("sw x5, 2047(x6)", 0x7E532FA3),
    ("beq x1, x2, -4096", 0x80208063),
    ("bne x3, x4, 4094", 0x7E419FE3),
    ("jal ra, 2048", 0x001000EF),
    ("jal x0, -1048576", 0x8000006F),
    ("jalr x1, 12(x5)", 0x00C280E7),
    ("lui x1, 0xfffff", 0xFFFFF0B7),
    ("auipc x10, 1", 0x00001517),
    ("srai x1, x2, 31", 0x41F15093),
    ("sub x3, x4, x5", 0x405201B3),
    ("fence rw, w", 0x0310000F),
    ("fence.tso", 0x8330000F),
    ("pause", 0x0100000F),
    ("ecall", 0x00000073),
    ("ebreak", 0x00100073),
    ("mul x1, x2, x3", 0x023100B3),
    ("remu x31, x30, x29", 0x03DF7FB3),
    ("sh2add a0, a1, a2", 0x20C5C533),
    ("andn x1, x2, x3", 0x403170B3),
    ("clz x3, x4", 0x60021193),
    ("cpop x1, x2", 0x60211093),
    ("zext.h x1, x2", 0x080140B3),
    ("rev8 x1, x2", 0x69815093),
    ("orc.b x1, x2", 0x28715093),
    ("rori x1, x2, 7", 0x60715093),
    ("bseti x1, x2, 31", 0x29F11093),
    ("bext x1, x2, x3", 0x483150B3),
    ("nop", 0x00000013),
    ("ret", 0x00008067),
    ("ble x1, x2, 8", 0x00115463),
]


class GoldenTests(unittest.TestCase):
    def test_golden(self):
        for asm, word in GOLDEN:
            with self.subTest(asm=asm):
                self.assertEqual(rv.encode(asm).word, word, f"{asm}: {rv.encode(asm).hex}")

    def test_example_from_request(self):
        e = rv.encode("addi x1, x2, 23")
        self.assertEqual(e.bin, "00000001011100010000000010010011")
        self.assertEqual(e.hex, "0x01710093")
        self.assertEqual(e.signed, 24182931)
        self.assertEqual([(f.name, f.value) for f in e.fields],
                         [("imm[11:0]", 23), ("rs1", 2), ("funct3", 0), ("rd", 1), ("opcode", 0b0010011)])

    def test_negative_signed(self):
        e = rv.encode("lw a0, -4(sp)")
        self.assertEqual(e.signed, 0xFFC12503 - (1 << 32))
        self.assertLess(e.signed, 0)

    def test_fields_tile_word(self):
        for mn in rv.OPS:
            for asm in _random_instances(mn, random.Random(1), 3):
                e = rv.encode(asm)
                rebuilt = 0
                for f in e.fields:
                    rebuilt |= f.value << f.lsb
                self.assertEqual(rebuilt, e.word, asm)
                self.assertEqual(e.bin_grouped.replace(" ", ""), e.bin)

    def test_invalid(self):
        for bad in INVALID:
            with self.subTest(asm=bad):
                with self.assertRaises(rv.AsmError):
                    rv.encode(bad)


INVALID = [
    "addi x1, x2, 2048", "addi x1, x2, -2049", "slli x1, x2, 32", "slli x1, x2, -1",
    "beq x1, x2, 3", "beq x1, x2, 4096", "beq x1, x2, -4098", "jal x1, 1048576",
    "jal x1, 1", "lui x1, 0x100000", "lui x1, -1", "lw x1, 2048(x2)", "sw x1, x2",
    "add x1, x2", "add x1, x2, x32", "foo x1, x2, x3", "clz x1, x2, x3", "fence rw",
    "fence wr, r", "rori x1, x2, 32", "bseti x1, x2, 32", "ecall x1", "csrrw x1, 0x300, x2",
    "fld f0, 0(x1)", "addw x1, x2, x3", "addi x1, x2, 0x_", "addi x1, x2, 0b__",
]

# --------------------------------------------------------------------------
# Random instance generation for the llvm-mc cross-check
# --------------------------------------------------------------------------


def _reg(r):
    n = r.randrange(32)
    return rv.ABI_NAMES[n] if r.random() < 0.3 else f"x{n}"


def _imm(r, lo, hi, step=1):
    edges = [lo, hi, 0, step, -step, lo + step, hi - step]
    v = r.choice(edges) if r.random() < 0.3 else r.randrange(lo, hi + 1, step) if lo % step == 0 else lo
    v = max(lo, min(hi, v))
    if v >= 0 and r.random() < 0.3:
        return hex(v)
    return str(v)


def _fence_set(r):
    s = "".join(c for c in "iorw" if r.random() < 0.5)
    return s or "rw"


PSEUDOS = ["nop", "mv", "not", "seqz", "snez", "j", "jr", "ret", "bgt", "bgtu", "ble", "bleu"]


def _random_instances(mn, r, n):
    out = []
    op = rv.OPS.get(mn)
    fmt = op.fmt if op else None
    for _ in range(n):
        if fmt == "R":
            s = f"{mn} {_reg(r)}, {_reg(r)}, {_reg(r)}"
        elif fmt == "I":
            s = f"{mn} {_reg(r)}, {_reg(r)}, {_imm(r, -2048, 2047)}"
        elif fmt == "SHIFT":
            s = f"{mn} {_reg(r)}, {_reg(r)}, {_imm(r, 0, 31)}"
        elif fmt in ("LOAD", "S"):
            off = _imm(r, -2048, 2047)
            s = f"{mn} {_reg(r)}, {off}({_reg(r)})"
        elif fmt == "JALR":
            k = r.randrange(3)
            if k == 0:
                s = f"{mn} {_reg(r)}"
            elif k == 1:
                s = f"{mn} {_reg(r)}, {_imm(r, -2048, 2047)}({_reg(r)})"
            else:
                s = f"{mn} {_reg(r)}, {_reg(r)}, {_imm(r, -2048, 2047)}"
        elif fmt == "B":
            s = f"{mn} {_reg(r)}, {_reg(r)}, {_imm(r, -4096, 4094, 2)}"
        elif fmt == "U":
            s = f"{mn} {_reg(r)}, {_imm(r, 0, 0xFFFFF)}"
        elif fmt == "J":
            off = _imm(r, -(1 << 20), (1 << 20) - 2, 2)
            s = f"{mn} {off}" if r.random() < 0.2 else f"{mn} {_reg(r)}, {off}"
        elif fmt == "FENCE":
            s = mn if r.random() < 0.1 else f"{mn} {_fence_set(r)}, {_fence_set(r)}"
        elif fmt == "FIXED":
            s = mn
        elif fmt == "UNARY":
            s = f"{mn} {_reg(r)}, {_reg(r)}"
        elif mn in ("nop", "ret"):
            s = mn
        elif mn in ("mv", "not", "seqz", "snez"):
            s = f"{mn} {_reg(r)}, {_reg(r)}"
        elif mn == "j":
            s = f"{mn} {_imm(r, -(1 << 20), (1 << 20) - 2, 2)}"
        elif mn == "jr":
            s = f"{mn} {_reg(r)}"
        elif mn in ("bgt", "bgtu", "ble", "bleu"):
            s = f"{mn} {_reg(r)}, {_reg(r)}, {_imm(r, -4096, 4094, 2)}"
        else:
            raise AssertionError(mn)
        out.append(s)
    return out


def llvm_encode(lines):
    """Assemble many lines with llvm-mc, return list of 32-bit words."""
    res = subprocess.run([LLVM_MC] + LLVM_ARGS, input="\n".join(lines) + "\n",
                         capture_output=True, text=True)
    if res.returncode != 0 or "error" in res.stderr:
        raise AssertionError(f"llvm-mc failed:\n{res.stderr[:3000]}")
    words = []
    for m in re.finditer(r"encoding: \[([^\]]*)\]", res.stdout):
        b = [int(x, 16) for x in m.group(1).split(",")]
        if len(b) != 4:
            raise AssertionError(f"unexpected encoding length: {m.group(0)}")
        words.append(b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24)
    return words


def llvm_rejects(line):
    res = subprocess.run([LLVM_MC] + LLVM_ARGS, input=line + "\n",
                         capture_output=True, text=True)
    return res.returncode != 0 or "error" in res.stderr


@unittest.skipUnless(LLVM_MC, "llvm-mc not installed")
class LlvmCrossCheck(unittest.TestCase):
    N_PER_OP = 300

    def test_golden_against_llvm(self):
        words = llvm_encode([a for a, _ in GOLDEN])
        self.assertEqual(words, [w for _, w in GOLDEN])

    def test_all_instructions_random(self):
        r = random.Random(12345)
        lines = []
        for mn in list(rv.OPS) + PSEUDOS:
            lines += _random_instances(mn, r, self.N_PER_OP)
        expected = llvm_encode(lines)
        self.assertEqual(len(expected), len(lines))
        mismatches = []
        for line, want in zip(lines, expected):
            got = rv.encode(line).word
            if got != want:
                mismatches.append(f"{line}: ours 0x{got:08X}, llvm 0x{want:08X}")
        if mismatches:
            self.fail(f"{len(mismatches)} mismatches, first ones:\n" + "\n".join(mismatches[:20]))
        print(f"\n  cross-checked {len(lines)} instructions "
              f"({len(rv.OPS)} mnemonics + {len(PSEUDOS)} pseudos) against llvm-mc", file=sys.stderr)

    def test_invalid_also_rejected_by_llvm(self):
        # Only the ones that are wrong for an RV32IMB assembler in general.
        for bad in INVALID:
            if bad in ("csrrw x1, 0x300, x2", "fence wr, r"):
                continue   # llvm-mc accepts these (Zicsr / any set order); we don't
            with self.subTest(asm=bad):
                self.assertTrue(llvm_rejects(bad), f"llvm-mc accepted '{bad}'")


class NumConvTests(unittest.TestCase):
    def test_roundtrips(self):
        r = random.Random(7)
        vals = [0, 1, -1, numconv.INT32_MIN, numconv.INT32_MAX, 24182931]
        vals += [r.randint(numconv.INT32_MIN, numconv.INT32_MAX) for _ in range(2000)]
        for v in vals:
            w = numconv.parse_signed_dec(str(v))
            self.assertEqual(numconv.to_signed(w), v)
            self.assertEqual(numconv.parse_hex(numconv.fmt_hex(w)), w)
            self.assertEqual(numconv.parse_bin(numconv.fmt_bin(w)), w)

    def test_specific(self):
        self.assertEqual(numconv.to_signed(numconv.parse_hex("FFFFFFFF")), -1)
        self.assertEqual(numconv.to_signed(numconv.parse_hex("0x80000000")), -2147483648)
        self.assertEqual(numconv.to_signed(numconv.parse_bin("1" + "0" * 31)), -2147483648)
        self.assertEqual(numconv.parse_bin("101"), 5)      # zero-extended
        self.assertEqual(numconv.parse_hex("ff"), 255)     # zero-extended
        self.assertEqual(numconv.fmt_hex(numconv.parse_signed_dec("-2")), "0xFFFFFFFE")

    def test_invalid(self):
        for f, s in [(numconv.parse_signed_dec, "2147483648"), (numconv.parse_signed_dec, "-2147483649"),
                     (numconv.parse_signed_dec, "12a"), (numconv.parse_hex, "123456789"),
                     (numconv.parse_hex, "0xG"), (numconv.parse_bin, "2"), (numconv.parse_bin, "1" * 33)]:
            with self.subTest(s=s):
                with self.assertRaises(numconv.ConversionError):
                    f(s)


if __name__ == "__main__":
    unittest.main()
