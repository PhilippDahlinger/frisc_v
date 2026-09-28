"""Single-instruction RV32IMB assembler that also reports every encoded field.

Ground truth: "The RISC-V Instruction Set Manual, Volume I: Unprivileged
Architecture" (riscv-unprivileged.pdf in the repo root):

* Instruction formats R/I/S/B/U/J ........ Sec. 2.2 / 2.3 (Figure 1)
* Opcodes, funct3, funct7 ................ Chapter 36, "RV32I Base Instruction
                                            Set", "RV32M Standard Extension"
* Major opcode names ..................... Table 72
* Shifts (shamt[4:0], bit 30 = SRA/SRAI) . Sec. 2.4.1
* FENCE fm/pred/succ ..................... Sec. 2.7 (+ Table 4)
* ECALL/EBREAK funct12 ................... Sec. 2.8
* B = Zba + Zbb + Zbs (RV32 encodings) ... Sec. 30.1 - 30.5, 30.9
* Pseudoinstructions ..................... only those the spec itself defines
                                            (NOP, MV, NOT, SEQZ, SNEZ, J, JR,
                                            RET, BGT/BGTU/BLE/BLEU)

Branch and jump operands are byte offsets relative to the instruction's own
address (there are no labels, since only one instruction is assembled).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from numconv import WORD_MASK, fmt_bin, fmt_hex, to_signed


class AsmError(ValueError):
    pass


# --------------------------------------------------------------------------
# Registers
# --------------------------------------------------------------------------

# Standard calling-convention (psABI) names.  These are not part of the ISA
# spec (it only defines x0..x31); they are accepted purely for convenience.
ABI_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
]
REGISTERS: Dict[str, int] = {f"x{i}": i for i in range(32)}
REGISTERS.update({name: i for i, name in enumerate(ABI_NAMES)})
REGISTERS["fp"] = 8


def reg_label(n: int) -> str:
    return f"x{n} ({ABI_NAMES[n]})"


# --------------------------------------------------------------------------
# Major opcodes, Table 72 (inst[1:0] = 11)
# --------------------------------------------------------------------------

OPCODE_NAMES = {
    0b0000011: "LOAD",
    0b0001111: "MISC-MEM",
    0b0010011: "OP-IMM",
    0b0010111: "AUIPC",
    0b0100011: "STORE",
    0b0110011: "OP",
    0b0110111: "LUI",
    0b1100011: "BRANCH",
    0b1100111: "JALR",
    0b1101111: "JAL",
    0b1110011: "SYSTEM",
}

# --------------------------------------------------------------------------
# Instruction table (Chapter 36)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Op:
    mnemonic: str
    fmt: str            # R, I, SHIFT, LOAD, S, B, U, J, JALR, FENCE, FIXED, UNARY
    opcode: int
    funct3: int = 0
    funct7: int = 0     # R-type funct7, or imm[11:5] for shift-immediates
    word: int = 0       # full encoding for FIXED instructions
    ext: str = "RV32I"
    # UNARY (rd, rs1 only): fixed fields above rs1, as (name, msb, lsb, value)
    fixed: Tuple[Tuple[str, int, int, int], ...] = ()


OPS: Dict[str, Op] = {}


def _add(*ops: Op) -> None:
    for op in ops:
        OPS[op.mnemonic] = op


LUI, AUIPC, JAL, JALR, BRANCH, LOAD, STORE = (
    0b0110111, 0b0010111, 0b1101111, 0b1100111, 0b1100011, 0b0000011, 0b0100011)
OP_IMM, OP, MISC_MEM, SYSTEM = 0b0010011, 0b0110011, 0b0001111, 0b1110011

_add(
    Op("lui", "U", LUI),
    Op("auipc", "U", AUIPC),
    Op("jal", "J", JAL),
    Op("jalr", "JALR", JALR, 0b000),
    Op("beq", "B", BRANCH, 0b000),
    Op("bne", "B", BRANCH, 0b001),
    Op("blt", "B", BRANCH, 0b100),
    Op("bge", "B", BRANCH, 0b101),
    Op("bltu", "B", BRANCH, 0b110),
    Op("bgeu", "B", BRANCH, 0b111),
    Op("lb", "LOAD", LOAD, 0b000),
    Op("lh", "LOAD", LOAD, 0b001),
    Op("lw", "LOAD", LOAD, 0b010),
    Op("lbu", "LOAD", LOAD, 0b100),
    Op("lhu", "LOAD", LOAD, 0b101),
    Op("sb", "S", STORE, 0b000),
    Op("sh", "S", STORE, 0b001),
    Op("sw", "S", STORE, 0b010),
    Op("addi", "I", OP_IMM, 0b000),
    Op("slti", "I", OP_IMM, 0b010),
    Op("sltiu", "I", OP_IMM, 0b011),
    Op("xori", "I", OP_IMM, 0b100),
    Op("ori", "I", OP_IMM, 0b110),
    Op("andi", "I", OP_IMM, 0b111),
    Op("slli", "SHIFT", OP_IMM, 0b001, 0b0000000),
    Op("srli", "SHIFT", OP_IMM, 0b101, 0b0000000),
    Op("srai", "SHIFT", OP_IMM, 0b101, 0b0100000),
    Op("add", "R", OP, 0b000, 0b0000000),
    Op("sub", "R", OP, 0b000, 0b0100000),
    Op("sll", "R", OP, 0b001, 0b0000000),
    Op("slt", "R", OP, 0b010, 0b0000000),
    Op("sltu", "R", OP, 0b011, 0b0000000),
    Op("xor", "R", OP, 0b100, 0b0000000),
    Op("srl", "R", OP, 0b101, 0b0000000),
    Op("sra", "R", OP, 0b101, 0b0100000),
    Op("or", "R", OP, 0b110, 0b0000000),
    Op("and", "R", OP, 0b111, 0b0000000),
    Op("fence", "FENCE", MISC_MEM, 0b000),
    # fm=1000 pred=0011 succ=0011 rs1=0 funct3=000 rd=0 MISC-MEM
    Op("fence.tso", "FIXED", MISC_MEM, word=0b1000_0011_0011_00000_000_00000_0001111),
    # fm=0000 pred=0001 succ=0000 rs1=0 funct3=000 rd=0 MISC-MEM
    Op("pause", "FIXED", MISC_MEM, word=0b0000_0001_0000_00000_000_00000_0001111,
       ext="Zihintpause"),
    Op("ecall", "FIXED", SYSTEM, word=0b000000000000_00000_000_00000_1110011),
    Op("ebreak", "FIXED", SYSTEM, word=0b000000000001_00000_000_00000_1110011),
    Op("mul", "R", OP, 0b000, 0b0000001, ext="RV32M"),
    Op("mulh", "R", OP, 0b001, 0b0000001, ext="RV32M"),
    Op("mulhsu", "R", OP, 0b010, 0b0000001, ext="RV32M"),
    Op("mulhu", "R", OP, 0b011, 0b0000001, ext="RV32M"),
    Op("div", "R", OP, 0b100, 0b0000001, ext="RV32M"),
    Op("divu", "R", OP, 0b101, 0b0000001, ext="RV32M"),
    Op("rem", "R", OP, 0b110, 0b0000001, ext="RV32M"),
    Op("remu", "R", OP, 0b111, 0b0000001, ext="RV32M"),
    # ---- B = Zba + Zbb + Zbs (Sec. 30.9, RV32 encodings) ----
    # Zba
    Op("sh1add", "R", OP, 0b010, 0b0010000, ext="Zba"),
    Op("sh2add", "R", OP, 0b100, 0b0010000, ext="Zba"),
    Op("sh3add", "R", OP, 0b110, 0b0010000, ext="Zba"),
    # Zbb: logical with negate
    Op("andn", "R", OP, 0b111, 0b0100000, ext="Zbb"),
    Op("orn", "R", OP, 0b110, 0b0100000, ext="Zbb"),
    Op("xnor", "R", OP, 0b100, 0b0100000, ext="Zbb"),
    # Zbb: count leading/trailing zeros, population count
    Op("clz", "UNARY", OP_IMM, 0b001, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0110000), ("funct5", 24, 20, 0b00000))),
    Op("ctz", "UNARY", OP_IMM, 0b001, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0110000), ("funct5", 24, 20, 0b00001))),
    Op("cpop", "UNARY", OP_IMM, 0b001, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0110000), ("funct5", 24, 20, 0b00010))),
    # Zbb: integer min/max
    Op("max", "R", OP, 0b110, 0b0000101, ext="Zbb"),
    Op("maxu", "R", OP, 0b111, 0b0000101, ext="Zbb"),
    Op("min", "R", OP, 0b100, 0b0000101, ext="Zbb"),
    Op("minu", "R", OP, 0b101, 0b0000101, ext="Zbb"),
    # Zbb: sign/zero extension
    Op("sext.b", "UNARY", OP_IMM, 0b001, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0110000), ("funct5", 24, 20, 0b00100))),
    Op("sext.h", "UNARY", OP_IMM, 0b001, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0110000), ("funct5", 24, 20, 0b00101))),
    Op("zext.h", "UNARY", OP, 0b100, ext="Zbb",
       fixed=(("funct7", 31, 25, 0b0000100), ("rs2 (fixed)", 24, 20, 0b00000))),
    # Zbb: rotation
    Op("rol", "R", OP, 0b001, 0b0110000, ext="Zbb"),
    Op("ror", "R", OP, 0b101, 0b0110000, ext="Zbb"),
    Op("rori", "SHIFT", OP_IMM, 0b101, 0b0110000, ext="Zbb"),
    # Zbb: OR-combine, byte-reverse
    Op("orc.b", "UNARY", OP_IMM, 0b101, ext="Zbb",
       fixed=(("funct12", 31, 20, 0b001010000111),)),
    Op("rev8", "UNARY", OP_IMM, 0b101, ext="Zbb",
       fixed=(("funct12", 31, 20, 0b011010011000),)),
    # Zbs: single-bit instructions
    Op("bclr", "R", OP, 0b001, 0b0100100, ext="Zbs"),
    Op("bclri", "SHIFT", OP_IMM, 0b001, 0b0100100, ext="Zbs"),
    Op("bext", "R", OP, 0b101, 0b0100100, ext="Zbs"),
    Op("bexti", "SHIFT", OP_IMM, 0b101, 0b0100100, ext="Zbs"),
    Op("binv", "R", OP, 0b001, 0b0110100, ext="Zbs"),
    Op("binvi", "SHIFT", OP_IMM, 0b001, 0b0110100, ext="Zbs"),
    Op("bset", "R", OP, 0b001, 0b0010100, ext="Zbs"),
    Op("bseti", "SHIFT", OP_IMM, 0b001, 0b0010100, ext="Zbs"),
)

FORMAT_NAMES = {
    "R": "R-type",
    "I": "I-type",
    "SHIFT": "I-type (shift by constant)",
    "LOAD": "I-type (load)",
    "JALR": "I-type (JALR)",
    "S": "S-type",
    "B": "B-type",
    "U": "U-type",
    "J": "J-type",
    "FENCE": "I-type (FENCE)",
}


def format_name(op: Op) -> str:
    if op.fmt == "UNARY":
        return ("R-type (unary, rs2 field fixed)" if op.opcode == OP
                else "I-type (unary, imm field fixed)")
    if op.fmt == "FIXED":
        return "I-type (FENCE)" if op.opcode == MISC_MEM else "I-type (SYSTEM)"
    return FORMAT_NAMES[op.fmt]

# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass
class Field:
    name: str
    msb: int
    lsb: int
    value: int          # raw bits as stored in the instruction
    meaning: str = ""

    @property
    def width(self) -> int:
        return self.msb - self.lsb + 1

    @property
    def bits(self) -> str:
        return format(self.value, f"0{self.width}b")

    @property
    def bit_range(self) -> str:
        return f"[{self.msb}]" if self.msb == self.lsb else f"[{self.msb}:{self.lsb}]"


@dataclass
class Encoded:
    source: str
    canonical: str          # the real (non-pseudo) instruction that was encoded
    mnemonic: str
    fmt: str
    ext: str
    word: int
    fields: List[Field]
    immediate: Optional[int] = None   # immediate value as the CPU sees it
    immediate_note: str = ""
    pseudo: Optional[str] = None      # name of the pseudoinstruction, if any
    notes: List[str] = field(default_factory=list)
    format_name: str = ""

    @property
    def hex(self) -> str:
        return fmt_hex(self.word)

    @property
    def bin(self) -> str:
        return fmt_bin(self.word, 0)

    @property
    def bin_grouped(self) -> str:
        """Binary string split at the instruction's field boundaries."""
        b = self.bin
        return " ".join(b[31 - f.msb:32 - f.lsb] for f in self.fields)

    @property
    def signed(self) -> int:
        return to_signed(self.word)

    @property
    def unsigned(self) -> int:
        return self.word


# --------------------------------------------------------------------------
# Operand parsing
# --------------------------------------------------------------------------

_INT_RE = re.compile(r"^[+-]?(0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|[0-9][0-9_]*)$")


def parse_int(text: str, what: str = "immediate") -> int:
    s = text.strip()
    if not _INT_RE.match(s):
        raise AsmError(f"invalid {what}: '{text.strip()}' (use decimal, 0x.., 0b.. or 0o..)")
    neg = s.startswith("-")
    s = s.lstrip("+-")
    base = 10
    if s[:2].lower() in ("0x", "0b", "0o"):
        base = {"0x": 16, "0b": 2, "0o": 8}[s[:2].lower()]
        s = s[2:]
    digits = s.replace("_", "")
    if not digits:
        raise AsmError(f"invalid {what}: '{text.strip()}' (no digits)")
    v = int(digits, base)
    if v >= 1 << 52:   # far outside any field; also keeps the Lua port (doubles) exact
        raise AsmError(f"invalid {what}: '{text.strip()}' (too large)")
    return -v if neg else v


def parse_reg(text: str) -> int:
    s = text.strip().lower()
    if s not in REGISTERS:
        raise AsmError(f"unknown register '{text.strip()}' (use x0..x31 or ABI names)")
    return REGISTERS[s]


_MEM_RE = re.compile(r"^(.*?)\(\s*([A-Za-z0-9]+)\s*\)$")


def parse_mem(text: str) -> Tuple[int, int]:
    """Parse 'offset(reg)' or '(reg)'; returns (offset, reg)."""
    m = _MEM_RE.match(text.strip())
    if not m:
        raise AsmError(f"expected memory operand 'offset(rs1)', got '{text.strip()}'")
    off = m.group(1).strip()
    return (parse_int(off, "offset") if off else 0), parse_reg(m.group(2))


def check_range(v: int, lo: int, hi: int, what: str) -> None:
    if not lo <= v <= hi:
        raise AsmError(f"{what} {v} out of range [{lo}, {hi}]")


def check_even(v: int, what: str) -> None:
    if v % 2:
        raise AsmError(f"{what} {v} must be a multiple of 2 (bit 0 is not encoded)")


_FENCE_BITS = {"i": 8, "o": 4, "r": 2, "w": 1}   # PI/PO/PR/PW, SI/SO/SR/SW (Sec. 2.7)


def parse_fence_set(text: str) -> int:
    s = text.strip().lower()
    if s == "0":
        return 0
    bits = 0
    last = -1
    for c in s:
        order = "iorw".find(c)
        if order < 0 or order <= last:
            raise AsmError(f"invalid FENCE set '{text.strip()}' (letters from i, o, r, w in that order)")
        last = order
        bits |= _FENCE_BITS[c]
    if not s:
        raise AsmError("empty FENCE set")
    return bits


def fence_set_str(bits: int) -> str:
    return "".join(c for c in "iorw" if bits & _FENCE_BITS[c]) or "0"


def split_operands(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(",")]
    if any(not p for p in parts):
        raise AsmError("empty operand (check the commas)")
    return parts


# --------------------------------------------------------------------------
# Field builders per format (layouts from Sec. 2.2/2.3 and Chapter 36)
# --------------------------------------------------------------------------

def bits(value: int, msb: int, lsb: int) -> int:
    return (value >> lsb) & ((1 << (msb - lsb + 1)) - 1)


def _opcode_field(opcode: int) -> Field:
    return Field("opcode", 6, 0, opcode, OPCODE_NAMES.get(opcode, "?"))


def _reg_field(name: str, msb: int, n: int) -> Field:
    return Field(name, msb, msb - 4, n, reg_label(n))


def _funct3_field(op: Op) -> Field:
    return Field("funct3", 14, 12, op.funct3, op.mnemonic.upper())


def fields_r(op: Op, rd: int, rs1: int, rs2: int) -> List[Field]:
    return [
        Field("funct7", 31, 25, op.funct7, op.mnemonic.upper()),
        _reg_field("rs2", 24, rs2),
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_i(op: Op, rd: int, rs1: int, imm: int) -> List[Field]:
    u = imm & 0xFFF
    return [
        Field("imm[11:0]", 31, 20, u, f"{imm} (sign-extended from bit 11)"),
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_shift(op: Op, rd: int, rs1: int, shamt: int) -> List[Field]:
    # Base shifts (Sec. 2.4.1) and the B shift-immediate forms (rori, b*i)
    # share this layout: a fixed funct7 in imm[11:5] and shamt[4:0] below it.
    if op.mnemonic in ("slli", "srli", "srai"):
        meaning = f"{op.mnemonic.upper()} (bit 30 selects arithmetic right shift)"
        amount = f"shift amount {shamt}"
    else:
        meaning = op.mnemonic.upper()
        amount = f"rotate amount {shamt}" if op.mnemonic == "rori" else f"bit index {shamt}"
    return [
        Field("funct7", 31, 25, op.funct7, meaning),
        Field("shamt[4:0]", 24, 20, shamt, amount),
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_s(op: Op, rs1: int, rs2: int, imm: int) -> List[Field]:
    u = imm & 0xFFF
    return [
        Field("imm[11:5]", 31, 25, bits(u, 11, 5), f"offset bits 11..5 (offset = {imm})"),
        _reg_field("rs2", 24, rs2),
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        Field("imm[4:0]", 11, 7, bits(u, 4, 0), f"offset bits 4..0 (offset = {imm})"),
        _opcode_field(op.opcode),
    ]


def fields_b(op: Op, rs1: int, rs2: int, imm: int) -> List[Field]:
    u = imm & 0x1FFF
    return [
        Field("imm[12]", 31, 31, bits(u, 12, 12), f"offset bit 12 = sign (offset = {imm})"),
        Field("imm[10:5]", 30, 25, bits(u, 10, 5), "offset bits 10..5"),
        _reg_field("rs2", 24, rs2),
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        Field("imm[4:1]", 11, 8, bits(u, 4, 1), "offset bits 4..1 (bit 0 is always 0)"),
        Field("imm[11]", 7, 7, bits(u, 11, 11), "offset bit 11"),
        _opcode_field(op.opcode),
    ]


def fields_u(op: Op, rd: int, imm20: int) -> List[Field]:
    return [
        Field("imm[31:12]", 31, 12, imm20, f"upper 20 bits (0x{imm20:05X})"),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_j(op: Op, rd: int, imm: int) -> List[Field]:
    u = imm & 0x1FFFFF
    return [
        Field("imm[20]", 31, 31, bits(u, 20, 20), f"offset bit 20 = sign (offset = {imm})"),
        Field("imm[10:1]", 30, 21, bits(u, 10, 1), "offset bits 10..1 (bit 0 is always 0)"),
        Field("imm[11]", 20, 20, bits(u, 11, 11), "offset bit 11"),
        Field("imm[19:12]", 19, 12, bits(u, 19, 12), "offset bits 19..12"),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_fence(op: Op, fm: int, pred: int, succ: int) -> List[Field]:
    return [
        Field("fm", 31, 28, fm, "normal fence" if fm == 0 else ("TSO" if fm == 0b1000 else "reserved")),
        Field("pred", 27, 24, pred, f"PI PO PR PW = {fence_set_str(pred)}"),
        Field("succ", 23, 20, succ, f"SI SO SR SW = {fence_set_str(succ)}"),
        _reg_field("rs1", 19, 0),
        _funct3_field(op),
        _reg_field("rd", 11, 0),
        _opcode_field(op.opcode),
    ]


def fields_unary(op: Op, rd: int, rs1: int) -> List[Field]:
    return [Field(name, msb, lsb, value, op.mnemonic.upper()) for name, msb, lsb, value in op.fixed] + [
        _reg_field("rs1", 19, rs1),
        _funct3_field(op),
        _reg_field("rd", 11, rd),
        _opcode_field(op.opcode),
    ]


def fields_fixed(op: Op) -> List[Field]:
    w = op.word
    if op.mnemonic in ("fence.tso", "pause"):
        return fields_fence(op, bits(w, 31, 28), bits(w, 27, 24), bits(w, 23, 20))
    if op.mnemonic in ("ecall", "ebreak"):  # Sec. 2.8
        return [
            Field("funct12", 31, 20, bits(w, 31, 20), op.mnemonic.upper()),
            _reg_field("rs1", 19, 0),
            Field("funct3", 14, 12, bits(w, 14, 12), "PRIV"),
            _reg_field("rd", 11, 0),
            _opcode_field(op.opcode),
        ]
    raise AssertionError(op.mnemonic)


def assemble_fields(fields: List[Field]) -> int:
    """Pack the fields into a word, checking they tile bits 31..0 exactly."""
    word = 0
    covered = 0
    for f in fields:
        if f.value >> f.width:
            raise AssertionError(f"field {f.name} value {f.value} wider than {f.width} bits")
        mask = ((1 << f.width) - 1) << f.lsb
        if covered & mask:
            raise AssertionError(f"field {f.name} overlaps another field")
        covered |= mask
        word |= f.value << f.lsb
    if covered != WORD_MASK:
        raise AssertionError("fields do not cover all 32 bits")
    return word


# --------------------------------------------------------------------------
# Immediate decoding straight from the instruction word (Figure 1).  Used to
# double-check every encoding: decode(encode(imm)) must give back imm.
# --------------------------------------------------------------------------

def _sext(v: int, width: int) -> int:
    return v - (1 << width) if v >> (width - 1) & 1 else v


def decode_immediate(fmt: str, w: int) -> int:
    if fmt in ("I", "LOAD", "JALR"):
        return _sext(bits(w, 31, 20), 12)
    if fmt == "S":
        return _sext(bits(w, 31, 25) << 5 | bits(w, 11, 7), 12)
    if fmt == "B":
        return _sext(bits(w, 31, 31) << 12 | bits(w, 7, 7) << 11
                     | bits(w, 30, 25) << 5 | bits(w, 11, 8) << 1, 13)
    if fmt == "U":
        return to_signed(w & 0xFFFFF000)
    if fmt == "J":
        return _sext(bits(w, 31, 31) << 20 | bits(w, 19, 12) << 12
                     | bits(w, 20, 20) << 11 | bits(w, 30, 21) << 1, 21)
    if fmt == "SHIFT":
        return bits(w, 24, 20)
    raise ValueError(fmt)


# --------------------------------------------------------------------------
# Pseudoinstructions defined in the spec
# --------------------------------------------------------------------------

def _expand_pseudo(mn: str, ops: List[str]) -> Optional[Tuple[str, List[str]]]:
    def need(n: int) -> None:
        if len(ops) != n:
            raise AsmError(f"'{mn}' expects {n} operand(s), got {len(ops)}")

    if mn == "nop":                       # Sec. 2.4.3
        need(0); return "addi", ["x0", "x0", "0"]
    if mn == "mv":                        # Sec. 2.4.1
        need(2); return "addi", [ops[0], ops[1], "0"]
    if mn == "not":
        need(2); return "xori", [ops[0], ops[1], "-1"]
    if mn == "seqz":
        need(2); return "sltiu", [ops[0], ops[1], "1"]
    if mn == "snez":                      # Sec. 2.4.2
        need(2); return "sltu", [ops[0], "x0", ops[1]]
    if mn == "j":                         # Sec. 2.5.1
        need(1); return "jal", ["x0", ops[0]]
    if mn == "jr":
        need(1); return "jalr", ["x0", ops[0], "0"]
    if mn == "ret":
        need(0); return "jalr", ["x0", "x1", "0"]
    if mn in ("bgt", "bgtu", "ble", "bleu"):   # Sec. 2.5.2: swap operands
        need(3)
        real = {"bgt": "blt", "bgtu": "bltu", "ble": "bge", "bleu": "bgeu"}[mn]
        return real, [ops[1], ops[0], ops[2]]
    return None


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def encode(text: str) -> Encoded:
    """Assemble one RV32 instruction and describe its encoding."""
    source = text.split("#", 1)[0].strip()
    if not source:
        raise AsmError("empty input")
    parts = source.split(None, 1)
    mn = parts[0].lower()
    ops = split_operands(parts[1] if len(parts) > 1 else "")

    pseudo = None
    expanded = _expand_pseudo(mn, ops)
    if expanded:
        pseudo = mn
        mn, ops = expanded
    if mn not in OPS:
        raise AsmError(f"unknown instruction '{parts[0]}'")
    op = OPS[mn]
    enc = _encode_op(op, ops)
    enc.source = source
    enc.pseudo = pseudo
    if pseudo:
        enc.notes.insert(0, f"'{pseudo}' is a pseudoinstruction for: {enc.canonical}")
    return enc


def _encode_op(op: Op, ops: List[str]) -> Encoded:
    mn, fmt = op.mnemonic, op.fmt

    def need(*counts: int) -> None:
        if len(ops) not in counts:
            want = " or ".join(str(c) for c in counts)
            raise AsmError(f"'{mn}' expects {want} operand(s), got {len(ops)}")

    imm: Optional[int] = None
    imm_note = ""
    notes: List[str] = []

    if fmt == "R":
        need(3)
        rd, rs1, rs2 = (parse_reg(o) for o in ops)
        fields = fields_r(op, rd, rs1, rs2)
        canonical = f"{mn} x{rd}, x{rs1}, x{rs2}"

    elif fmt == "I":
        need(3)
        rd, rs1 = parse_reg(ops[0]), parse_reg(ops[1])
        imm = parse_int(ops[2])
        check_range(imm, -2048, 2047, "12-bit signed immediate")
        fields = fields_i(op, rd, rs1, imm)
        canonical = f"{mn} x{rd}, x{rs1}, {imm}"
        imm_note = "I-immediate, sign-extended to 32 bits"
        if mn == "sltiu":
            notes.append("SLTIU compares against the sign-extended immediate treated as unsigned")

    elif fmt == "SHIFT":
        need(3)
        rd, rs1 = parse_reg(ops[0]), parse_reg(ops[1])
        imm = parse_int(ops[2], "shift amount")
        check_range(imm, 0, 31, "shamt (5-bit unsigned)")
        fields = fields_shift(op, rd, rs1, imm)
        canonical = f"{mn} x{rd}, x{rs1}, {imm}"
        imm_note = "shamt[4:0], unsigned"

    elif fmt == "LOAD":
        need(2)
        rd = parse_reg(ops[0])
        imm, rs1 = parse_mem(ops[1])
        check_range(imm, -2048, 2047, "12-bit signed offset")
        fields = fields_i(op, rd, rs1, imm)
        canonical = f"{mn} x{rd}, {imm}(x{rs1})"
        imm_note = "byte offset added to rs1, sign-extended"

    elif fmt == "JALR":
        need(1, 2, 3)
        if len(ops) == 1:                      # jalr rs1  ->  jalr x1, 0(rs1)
            rd, rs1, imm = 1, parse_reg(ops[0]), 0
        elif len(ops) == 2:                    # jalr rd, imm(rs1)
            rd = parse_reg(ops[0])
            imm, rs1 = parse_mem(ops[1])
        else:                                  # jalr rd, rs1, imm
            rd, rs1, imm = parse_reg(ops[0]), parse_reg(ops[1]), parse_int(ops[2], "offset")
        check_range(imm, -2048, 2047, "12-bit signed offset")
        fields = fields_i(op, rd, rs1, imm)
        canonical = f"{mn} x{rd}, {imm}(x{rs1})"
        imm_note = "target = (rs1 + imm) with bit 0 cleared"

    elif fmt == "S":
        need(2)
        rs2 = parse_reg(ops[0])
        imm, rs1 = parse_mem(ops[1])
        check_range(imm, -2048, 2047, "12-bit signed offset")
        fields = fields_s(op, rs1, rs2, imm)
        canonical = f"{mn} x{rs2}, {imm}(x{rs1})"
        imm_note = "byte offset added to rs1, sign-extended"

    elif fmt == "B":
        need(3)
        rs1, rs2 = parse_reg(ops[0]), parse_reg(ops[1])
        imm = parse_int(ops[2], "branch offset")
        check_range(imm, -4096, 4094, "13-bit signed branch offset")
        check_even(imm, "branch offset")
        fields = fields_b(op, rs1, rs2, imm)
        canonical = f"{mn} x{rs1}, x{rs2}, {imm}"
        imm_note = "byte offset relative to this instruction's address"

    elif fmt == "U":
        need(2)
        rd = parse_reg(ops[0])
        imm20 = parse_int(ops[1])
        check_range(imm20, 0, 0xFFFFF, "20-bit upper immediate")
        fields = fields_u(op, rd, imm20)
        canonical = f"{mn} x{rd}, 0x{imm20:X}"
        imm = to_signed(imm20 << 12)
        imm_note = f"U-immediate = imm[31:12] << 12 = 0x{imm20 << 12:08X}"

    elif fmt == "J":
        need(1, 2)
        if len(ops) == 1:                      # jal offset  ->  jal x1, offset
            rd, imm = 1, parse_int(ops[0], "jump offset")
        else:
            rd, imm = parse_reg(ops[0]), parse_int(ops[1], "jump offset")
        check_range(imm, -(1 << 20), (1 << 20) - 2, "21-bit signed jump offset")
        check_even(imm, "jump offset")
        fields = fields_j(op, rd, imm)
        canonical = f"{mn} x{rd}, {imm}"
        imm_note = "byte offset relative to this instruction's address"

    elif fmt == "FENCE":
        need(0, 2)
        if ops:
            pred, succ = parse_fence_set(ops[0]), parse_fence_set(ops[1])
        else:
            pred = succ = 0b1111
            notes.append("'fence' without operands is taken as 'fence iorw, iorw'")
        fields = fields_fence(op, 0, pred, succ)
        canonical = f"fence {fence_set_str(pred)}, {fence_set_str(succ)}"

    elif fmt == "FIXED":
        need(0)
        fields = fields_fixed(op)
        canonical = mn

    elif fmt == "UNARY":
        need(2)
        rd, rs1 = parse_reg(ops[0]), parse_reg(ops[1])
        fields = fields_unary(op, rd, rs1)
        canonical = f"{mn} x{rd}, x{rs1}"

    else:  # pragma: no cover
        raise AssertionError(fmt)

    word = assemble_fields(fields)
    if fmt == "FIXED" and word != op.word:
        raise AssertionError(f"{mn}: field view disagrees with table encoding")
    if imm is not None and decode_immediate(fmt, word) != imm:
        raise AssertionError(f"{mn}: immediate {imm} does not round-trip "
                             f"(decoded {decode_immediate(fmt, word)})")

    return Encoded(
        source="", canonical=canonical, mnemonic=mn, fmt=fmt, ext=op.ext, word=word,
        fields=fields, immediate=imm, immediate_note=imm_note, notes=notes,
        format_name=format_name(op),
    )


SUPPORTED_HELP = """\
RV32I:    lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw lbu lhu sb sh sw
          addi slti sltiu xori ori andi slli srli srai
          add sub sll slt sltu xor srl sra or and
          fence fence.tso pause ecall ebreak
RV32M:    mul mulh mulhsu mulhu div divu rem remu
Zba:      sh1add sh2add sh3add
Zbb:      andn orn xnor clz ctz cpop max maxu min minu sext.b sext.h zext.h
          rol ror rori orc.b rev8
Zbs:      bclr bclri bext bexti binv binvi bset bseti
Pseudo:   nop mv not seqz snez j jr ret bgt bgtu ble bleu

Registers: x0..x31 or ABI names (zero ra sp gp tp t0-t6 s0-s11 fp a0-a7)
Loads/stores/jalr: lw x1, -4(x2)     Branches/jal: offset in bytes, e.g. beq x1, x2, -8
Immediates: decimal, 0x hex, 0b binary"""
