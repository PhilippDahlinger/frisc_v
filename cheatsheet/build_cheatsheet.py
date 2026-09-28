"""Build rv32imb_cheatsheet.pdf: every RV32I / M / B instruction, the encoding
formats, the pseudoinstructions and the register names on a few A4 pages.

Opcodes, funct fields and formats are read from debug_gui/rv32_encoder.py (itself
verified against llvm-mc), and every example is assembled with it, so the sheet
cannot drift from the tools. Descriptions follow the wording of the spec
(riscv-unprivileged.pdf: Chapter 2 RV32I, 12 M, 30 B, 36 listings).

    pip install reportlab
    python cheatsheet/build_cheatsheet.py
"""

import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Flowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "debug_gui"))
import rv32_encoder as rv  # noqa: E402

OUT = os.path.join(HERE, "rv32imb_cheatsheet.pdf")

# --------------------------------------------------------------------------
# Fonts (DejaVu has the ← × ≥ ≠ glyphs; Helvetica does not)
# --------------------------------------------------------------------------

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/Library/Fonts",
             os.path.expanduser("~/Library/Fonts"), "C:/Windows/Fonts"]
try:
    import matplotlib
    FONT_DIRS.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"))
except ImportError:
    pass


def register_fonts():
    names = {"Sans": "DejaVuSans.ttf", "Sans-Bold": "DejaVuSans-Bold.ttf",
             "Mono": "DejaVuSansMono.ttf", "Mono-Bold": "DejaVuSansMono-Bold.ttf"}
    for d in FONT_DIRS:
        if all(os.path.exists(os.path.join(d, f)) for f in names.values()):
            for n, f in names.items():
                pdfmetrics.registerFont(TTFont(n, os.path.join(d, f)))
            for family in ("Sans", "Mono"):   # so <b> in paragraphs picks the bold face
                addMapping(family, 0, 0, family)
                addMapping(family, 1, 0, family + "-Bold")
                addMapping(family, 0, 1, family)
                addMapping(family, 1, 1, family + "-Bold")
            return
    sys.exit("DejaVu fonts not found (install fonts-dejavu or matplotlib)")


register_fonts()

# --------------------------------------------------------------------------
# Styles and colours (same field colours as the debug GUI)
# --------------------------------------------------------------------------

KIND = {
    "opcode": colors.HexColor("#F4C7C3"),
    "funct": colors.HexColor("#FCE8B2"),
    "reg": colors.HexColor("#B7E1CD"),
    "imm": colors.HexColor("#C9DAF8"),
}
HEAD_BG = colors.HexColor("#37474F")
GROUP_BG = colors.HexColor("#E3E7EC")
ZEBRA = colors.HexColor("#F7F8FA")
GRID = colors.HexColor("#B0B7BF")

BASE = ParagraphStyle("base", fontName="Sans", fontSize=7.2, leading=8.6)
MONO = ParagraphStyle("mono", parent=BASE, fontName="Mono", fontSize=7.0, leading=8.6)
MONO_B = ParagraphStyle("monob", parent=MONO, fontName="Mono-Bold")
HEAD = ParagraphStyle("head", parent=BASE, fontName="Sans-Bold", textColor=colors.white)
H1 = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=21, spaceAfter=2)
H2 = ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12.5, leading=15, spaceBefore=8, spaceAfter=4,
                    textColor=HEAD_BG)
DESC = ParagraphStyle("desc", parent=BASE, leading=10.2)   # room for superscripts
NOTE = ParagraphStyle("note", parent=BASE, fontSize=7.6, leading=9.6)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=6.6, leading=8, textColor=colors.HexColor("#444"))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(text, style=BASE):
    return Paragraph(text, style)


def code(text, bold=False):
    return Paragraph(esc(text), MONO_B if bold else MONO)


# --------------------------------------------------------------------------
# Instruction descriptions: (arguments, description, example)
# --------------------------------------------------------------------------

GROUPS = [
    ("RV32I: integer register-immediate", [
        ("addi", "rd, rs1, imm", "rd = rs1 + sext(imm). Overflow is ignored.", "addi x1, x2, 23"),
        ("slti", "rd, rs1, imm", "rd = (rs1 &lt; sext(imm)) ? 1 : 0, signed compare", "slti x5, x6, -1"),
        ("sltiu", "rd, rs1, imm", "rd = (rs1 &lt; sext(imm)) ? 1 : 0, unsigned compare (imm is sign-extended "
                                  "first, then treated as unsigned)", "sltiu x5, x6, 1"),
        ("xori", "rd, rs1, imm", "rd = rs1 ^ sext(imm)", "xori x5, x6, -1"),
        ("ori", "rd, rs1, imm", "rd = rs1 | sext(imm)", "ori x5, x6, 0x0F0"),
        ("andi", "rd, rs1, imm", "rd = rs1 &amp; sext(imm)", "andi x5, x6, 255"),
        ("slli", "rd, rs1, shamt", "rd = rs1 &lt;&lt; shamt (logical left shift, shamt 0..31)", "slli x5, x6, 4"),
        ("srli", "rd, rs1, shamt", "rd = rs1 &gt;&gt; shamt, logical (zeros shifted in)", "srli x5, x6, 4"),
        ("srai", "rd, rs1, shamt", "rd = rs1 &gt;&gt; shamt, arithmetic (sign bit copied in)", "srai x5, x6, 4"),
    ]),
    ("RV32I: integer register-register", [
        ("add", "rd, rs1, rs2", "rd = rs1 + rs2. Overflow is ignored.", "add x3, x4, x5"),
        ("sub", "rd, rs1, rs2", "rd = rs1 − rs2", "sub x3, x4, x5"),
        ("sll", "rd, rs1, rs2", "rd = rs1 &lt;&lt; rs2[4:0] (logical left shift)", "sll x3, x4, x5"),
        ("slt", "rd, rs1, rs2", "rd = (rs1 &lt; rs2) ? 1 : 0, signed", "slt x3, x4, x5"),
        ("sltu", "rd, rs1, rs2", "rd = (rs1 &lt; rs2) ? 1 : 0, unsigned", "sltu x3, x4, x5"),
        ("xor", "rd, rs1, rs2", "rd = rs1 ^ rs2", "xor x3, x4, x5"),
        ("srl", "rd, rs1, rs2", "rd = rs1 &gt;&gt; rs2[4:0], logical", "srl x3, x4, x5"),
        ("sra", "rd, rs1, rs2", "rd = rs1 &gt;&gt; rs2[4:0], arithmetic", "sra x3, x4, x5"),
        ("or", "rd, rs1, rs2", "rd = rs1 | rs2", "or x3, x4, x5"),
        ("and", "rd, rs1, rs2", "rd = rs1 &amp; rs2", "and x3, x4, x5"),
    ]),
    ("RV32I: upper immediates", [
        ("lui", "rd, imm20", "rd = imm20 &lt;&lt; 12 (lower 12 bits zero). Builds 32-bit constants "
                             "(imm20: 0..0xFFFFF).", "lui x5, 0x12345"),
        ("auipc", "rd, imm20", "rd = pc + (imm20 &lt;&lt; 12). Builds pc-relative addresses.", "auipc x5, 0x10"),
    ]),
    ("RV32I: control transfer (offsets in bytes, relative to this instruction)", [
        ("jal", "rd, offset", "rd = pc + 4; pc = pc + offset. Offset is even, ±1 MiB.", "jal ra, 2048"),
        ("jalr", "rd, offset(rs1)", "t = pc + 4; pc = (rs1 + sext(offset)) &amp; ~1; rd = t", "jalr x1, 12(x5)"),
        ("beq", "rs1, rs2, offset", "if rs1 == rs2: pc = pc + offset. Offset is even, ±4 KiB.", "beq x1, x2, -8"),
        ("bne", "rs1, rs2, offset", "if rs1 ≠ rs2: pc = pc + offset", "bne x1, x2, 16"),
        ("blt", "rs1, rs2, offset", "if rs1 &lt; rs2 (signed): pc = pc + offset", "blt x1, x2, -8"),
        ("bge", "rs1, rs2, offset", "if rs1 ≥ rs2 (signed): pc = pc + offset", "bge x1, x2, 8"),
        ("bltu", "rs1, rs2, offset", "if rs1 &lt; rs2 (unsigned): pc = pc + offset", "bltu x1, x2, -4096"),
        ("bgeu", "rs1, rs2, offset", "if rs1 ≥ rs2 (unsigned): pc = pc + offset", "bgeu x1, x2, 4094"),
    ]),
    ("RV32I: loads and stores (address = rs1 + sext(offset))", [
        ("lb", "rd, offset(rs1)", "rd = sext(mem8[addr]), 8-bit value sign-extended", "lb x5, 0(x6)"),
        ("lh", "rd, offset(rs1)", "rd = sext(mem16[addr]), 16-bit value sign-extended", "lh x5, 2(x6)"),
        ("lw", "rd, offset(rs1)", "rd = mem32[addr]", "lw a0, -4(sp)"),
        ("lbu", "rd, offset(rs1)", "rd = zext(mem8[addr]), 8-bit value zero-extended", "lbu x5, 1(x6)"),
        ("lhu", "rd, offset(rs1)", "rd = zext(mem16[addr]), 16-bit value zero-extended", "lhu x5, 6(x6)"),
        ("sb", "rs2, offset(rs1)", "mem8[addr] = rs2[7:0]", "sb x5, 3(x6)"),
        ("sh", "rs2, offset(rs1)", "mem16[addr] = rs2[15:0]", "sh x5, 2(x6)"),
        ("sw", "rs2, offset(rs1)", "mem32[addr] = rs2", "sw x5, 2047(x6)"),
    ]),
    ("RV32I: memory ordering and environment", [
        ("fence", "pred, succ", "Order device I/O and memory accesses: no other hart or device sees an operation "
                                "in the successor set before any in the predecessor set. Sets are letters "
                                "from i, o, r, w.", "fence rw, w"),
        ("fence.tso", "", "FENCE with fm=1000, pred=succ=rw: loads ordered before all later accesses, "
                          "stores before later stores (total store ordering).", "fence.tso"),
        ("pause", "", "Zihintpause hint: temporarily reduce the instruction retirement rate (e.g. in spin-wait "
                      "loops). Encoded as FENCE with pred=w, succ=0.", "pause"),
        ("ecall", "", "Environment call: service request to the execution environment (trap).", "ecall"),
        ("ebreak", "", "Breakpoint: return control to a debugging environment (trap).", "ebreak"),
    ]),
    ("M: multiplication and division", [
        ("mul", "rd, rs1, rs2", "rd = (rs1 × rs2)[31:0], lower 32 bits of the product", "mul x1, x2, x3"),
        ("mulh", "rd, rs1, rs2", "rd = (rs1 × rs2)[63:32], signed × signed", "mulh x1, x2, x3"),
        ("mulhsu", "rd, rs1, rs2", "rd = (rs1 × rs2)[63:32], signed rs1 × unsigned rs2", "mulhsu x1, x2, x3"),
        ("mulhu", "rd, rs1, rs2", "rd = (rs1 × rs2)[63:32], unsigned × unsigned", "mulhu x1, x2, x3"),
        ("div", "rd, rs1, rs2", "rd = rs1 / rs2, signed, rounds towards zero. x/0 = −1; "
                                "−2<super>31</super> / −1 = −2<super>31</super>.", "div x1, x2, x3"),
        ("divu", "rd, rs1, rs2", "rd = rs1 / rs2, unsigned. x/0 = 2<super>32</super> − 1 (all ones).", "divu x1, x2, x3"),
        ("rem", "rd, rs1, rs2", "rd = rs1 % rs2, signed; a nonzero result has the sign of the dividend. "
                                "x % 0 = x; −2<super>31</super> % −1 = 0.", "rem x1, x2, x3"),
        ("remu", "rd, rs1, rs2", "rd = rs1 % rs2, unsigned. x % 0 = x.", "remu x31, x30, x29"),
    ]),
    ("B / Zba: address generation", [
        ("sh1add", "rd, rs1, rs2", "rd = rs2 + (rs1 &lt;&lt; 1)", "sh1add a0, a1, a2"),
        ("sh2add", "rd, rs1, rs2", "rd = rs2 + (rs1 &lt;&lt; 2)", "sh2add a0, a1, a2"),
        ("sh3add", "rd, rs1, rs2", "rd = rs2 + (rs1 &lt;&lt; 3)", "sh3add a0, a1, a2"),
    ]),
    ("B / Zbb: basic bit manipulation", [
        ("andn", "rd, rs1, rs2", "rd = rs1 &amp; ~rs2", "andn x1, x2, x3"),
        ("orn", "rd, rs1, rs2", "rd = rs1 | ~rs2", "orn x1, x2, x3"),
        ("xnor", "rd, rs1, rs2", "rd = ~(rs1 ^ rs2)", "xnor x1, x2, x3"),
        ("clz", "rd, rs1", "rd = number of leading zero bits, counted from bit 31 (32 if rs1 = 0)", "clz x3, x4"),
        ("ctz", "rd, rs1", "rd = number of trailing zero bits, counted from bit 0 (32 if rs1 = 0)", "ctz x3, x4"),
        ("cpop", "rd, rs1", "rd = number of 1 bits in rs1 (population count)", "cpop x1, x2"),
        ("max", "rd, rs1, rs2", "rd = larger of rs1, rs2 (signed)", "max x1, x2, x3"),
        ("maxu", "rd, rs1, rs2", "rd = larger of rs1, rs2 (unsigned)", "maxu x1, x2, x3"),
        ("min", "rd, rs1, rs2", "rd = smaller of rs1, rs2 (signed)", "min x1, x2, x3"),
        ("minu", "rd, rs1, rs2", "rd = smaller of rs1, rs2 (unsigned)", "minu x1, x2, x3"),
        ("sext.b", "rd, rs1", "rd = sext(rs1[7:0]): bit 7 copied into bits 31..8", "sext.b x1, x2"),
        ("sext.h", "rd, rs1", "rd = sext(rs1[15:0]): bit 15 copied into bits 31..16", "sext.h x1, x2"),
        ("zext.h", "rd, rs1", "rd = zext(rs1[15:0]): bits 31..16 cleared", "zext.h x1, x2"),
        ("rol", "rd, rs1, rs2", "rd = rs1 rotated left by rs2[4:0]", "rol x1, x2, x3"),
        ("ror", "rd, rs1, rs2", "rd = rs1 rotated right by rs2[4:0]", "ror x1, x2, x3"),
        ("rori", "rd, rs1, shamt", "rd = rs1 rotated right by shamt (0..31)", "rori x1, x2, 7"),
        ("orc.b", "rd, rs1", "OR-combine per byte: each byte of rd is 0x00 if that byte of rs1 is 0, "
                             "else 0xFF", "orc.b x1, x2"),
        ("rev8", "rd, rs1", "rd = rs1 with the byte order reversed", "rev8 x1, x2"),
    ]),
    ("B / Zbs: single-bit instructions (bit index = rs2[4:0] or shamt 0..31)", [
        ("bclr", "rd, rs1, rs2", "rd = rs1 &amp; ~(1 &lt;&lt; rs2[4:0])  (clear bit)", "bclr x1, x2, x3"),
        ("bclri", "rd, rs1, shamt", "rd = rs1 &amp; ~(1 &lt;&lt; shamt)", "bclri x1, x2, 5"),
        ("bext", "rd, rs1, rs2", "rd = (rs1 &gt;&gt; rs2[4:0]) &amp; 1  (extract bit)", "bext x1, x2, x3"),
        ("bexti", "rd, rs1, shamt", "rd = (rs1 &gt;&gt; shamt) &amp; 1", "bexti x1, x2, 5"),
        ("binv", "rd, rs1, rs2", "rd = rs1 ^ (1 &lt;&lt; rs2[4:0])  (invert bit)", "binv x1, x2, x3"),
        ("binvi", "rd, rs1, shamt", "rd = rs1 ^ (1 &lt;&lt; shamt)", "binvi x1, x2, 5"),
        ("bset", "rd, rs1, rs2", "rd = rs1 | (1 &lt;&lt; rs2[4:0])  (set bit)", "bset x1, x2, x3"),
        ("bseti", "rd, rs1, shamt", "rd = rs1 | (1 &lt;&lt; shamt)", "bseti x1, x2, 31"),
    ]),
]

PSEUDOS = [
    # (pseudo syntax, expansion syntax, meaning, example)
    ("nop", "addi x0, x0, 0", "no operation", "nop"),
    ("mv rd, rs", "addi rd, rs, 0", "copy register", "mv a0, a1"),
    ("not rd, rs", "xori rd, rs, -1", "bitwise NOT", "not a0, a1"),
    ("seqz rd, rs", "sltiu rd, rs, 1", "rd = (rs == 0) ? 1 : 0", "seqz a0, a1"),
    ("snez rd, rs", "sltu rd, x0, rs", "rd = (rs ≠ 0) ? 1 : 0", "snez a0, a1"),
    ("j offset", "jal x0, offset", "jump, no link", "j -16"),
    ("jr rs", "jalr x0, 0(rs)", "jump to register, no link", "jr t0"),
    ("ret", "jalr x0, 0(x1)", "return from subroutine (to address in ra)", "ret"),
    ("bgt rs, rt, offset", "blt rt, rs, offset", "branch if rs &gt; rt (signed): operands swapped", "bgt a0, a1, 8"),
    ("bgtu rs, rt, offset", "bltu rt, rs, offset", "branch if rs &gt; rt (unsigned)", "bgtu a0, a1, 8"),
    ("ble rs, rt, offset", "bge rt, rs, offset", "branch if rs ≤ rt (signed)", "ble a0, a1, 8"),
    ("bleu rs, rt, offset", "bgeu rt, rs, offset", "branch if rs ≤ rt (unsigned)", "bleu a0, a1, 8"),
]

SHORT_FORMS = [
    ("jal offset", "jal x1, offset", "call: link register ra", "jal 256"),
    ("jalr rs", "jalr x1, 0(rs)", "call through register", "jalr t0"),
    ("jalr rd, rs1, offset", "jalr rd, offset(rs1)", "alternative operand order", "jalr x1, x5, 12"),
    ("lw rd, (rs1)", "lw rd, 0(rs1)", "offset may be omitted (all loads/stores)", "lw a0, (sp)"),
    ("fence", "fence iorw, iorw", "full fence", "fence"),
]

# --------------------------------------------------------------------------
# Helpers built on the encoder
# --------------------------------------------------------------------------


def funct_column(op):
    if op.fmt in ("R", "SHIFT"):
        return format(op.funct7, "07b")
    if op.fmt == "UNARY":
        return " ".join(format(v, f"0{msb - lsb + 1}b") for _, msb, lsb, v in op.fixed)
    if op.fmt == "FIXED":
        w = op.word
        if op.opcode == rv.SYSTEM:
            return format(w >> 20, "012b")
        return f"fm {w >> 28:04b} pred {(w >> 24) & 15:04b} succ {(w >> 20) & 15:04b}"
    return "–"


def short_format(op):
    return {
        "R": "R", "I": "I", "SHIFT": "I (shamt)", "LOAD": "I", "JALR": "I", "S": "S", "B": "B",
        "U": "U", "J": "J", "FENCE": "I (fence)",
        "UNARY": "R (unary)" if op.opcode == rv.OP else "I (unary)",
        "FIXED": "I (fence)" if op.opcode == rv.MISC_MEM else "I (system)",
    }[op.fmt]


def check_coverage():
    listed = [mn for _, rows in GROUPS for mn, *_ in rows]
    missing = set(rv.OPS) - set(listed)
    extra = set(listed) - set(rv.OPS)
    dup = {m for m in listed if listed.count(m) > 1}
    if missing or extra or dup:
        sys.exit(f"coverage error: missing {missing}, unknown {extra}, duplicated {dup}")
    for _, rows in GROUPS:
        for mn, _, _, ex in rows:
            if rv.encode(ex).mnemonic != mn:
                sys.exit(f"example '{ex}' does not assemble to {mn}")
    for syntax, expansion, _, ex in PSEUDOS + SHORT_FORMS:
        e = rv.encode(ex)
        mn = expansion.split()[0]
        if e.mnemonic != mn:
            sys.exit(f"'{ex}' expands to {e.mnemonic}, sheet says {mn}")


# --------------------------------------------------------------------------
# Instruction-format diagrams
# --------------------------------------------------------------------------

def kind_of(name):
    if name == "opcode":
        return "opcode"
    if name in ("rd", "rs1", "rs2"):
        return "reg"
    if name.startswith("funct") or name in ("fm",) or "fixed" in name:
        return "funct"
    return "imm"


class FormatDiagram(Flowable):
    """One instruction format drawn like the spec: bit numbers above, fields in boxes."""

    def __init__(self, label, fields, note="", width=None, label_w=92, note_w=0):
        super().__init__()
        self.label, self.fields, self.note = label, fields, note
        self.label_w, self.note_w = label_w, note_w
        self.w = width or 700
        self.h = 30

    def wrap(self, avail_w, avail_h):
        self.w = min(self.w, avail_w)
        return self.w, self.h

    def draw(self):
        c = self.canv
        bar_w = self.w - self.label_w - self.note_w
        cell = bar_w / 32.0
        x0, box_y, box_h = self.label_w, 3, 15
        c.setFont("Sans-Bold", 8)
        c.setFillColor(colors.black)
        c.drawString(0, box_y + 4, self.label)
        for name, msb, lsb, *rest in self.fields:
            fill = KIND[rest[0] if rest else kind_of(name)]
            xa = x0 + (31 - msb) * cell
            xb = x0 + (32 - lsb) * cell
            c.setFillColor(fill)
            c.setStrokeColor(colors.HexColor("#555"))
            c.setLineWidth(0.5)
            c.rect(xa, box_y, xb - xa, box_h, fill=1, stroke=1)
            c.setFillColor(colors.black)
            size = 6.8
            while c.stringWidth(name, "Mono", size) > (xb - xa) - 2 and size > 4.5:
                size -= 0.3
            c.setFont("Mono", size)
            c.drawCentredString((xa + xb) / 2, box_y + 4.5, name)
            c.setFont("Sans", 5.6)
            c.setFillColor(colors.HexColor("#333"))
            c.drawString(xa + 1, box_y + box_h + 2, str(msb))
            if msb != lsb:
                c.drawRightString(xb - 1, box_y + box_h + 2, str(lsb))
        if self.note:
            c.setFont("Sans", 6.8)
            c.setFillColor(colors.HexColor("#333"))
            c.drawString(x0 + bar_w + 8, box_y + 4, self.note)


def I(name, msb, lsb, kind=None):
    return (name, msb, lsb, kind) if kind else (name, msb, lsb)


FORMATS = [
    ("R-type", [I("funct7", 31, 25), I("rs2", 24, 20), I("rs1", 19, 15), I("funct3", 14, 12),
                I("rd", 11, 7), I("opcode", 6, 0)],
     "register-register (OP), incl. M, Zba, most of Zbb/Zbs"),
    ("I-type", [I("imm[11:0]", 31, 20), I("rs1", 19, 15), I("funct3", 14, 12), I("rd", 11, 7),
                I("opcode", 6, 0)],
     "OP-IMM, loads, JALR"),
    ("S-type", [I("imm[11:5]", 31, 25), I("rs2", 24, 20), I("rs1", 19, 15), I("funct3", 14, 12),
                I("imm[4:0]", 11, 7), I("opcode", 6, 0)],
     "stores"),
    ("B-type", [I("[12]", 31, 31), I("imm[10:5]", 30, 25), I("rs2", 24, 20), I("rs1", 19, 15),
                I("funct3", 14, 12), I("imm[4:1]", 11, 8), I("[11]", 7, 7), I("opcode", 6, 0)],
     "branches, offset bit 0 is always 0"),
    ("U-type", [I("imm[31:12]", 31, 12), I("rd", 11, 7), I("opcode", 6, 0)],
     "LUI, AUIPC"),
    ("J-type", [I("[20]", 31, 31), I("imm[10:1]", 30, 21), I("[11]", 20, 20), I("imm[19:12]", 19, 12),
                I("rd", 11, 7), I("opcode", 6, 0)],
     "JAL, offset bit 0 is always 0"),
]

VARIANTS = [
    ("I (shamt)", [I("funct7", 31, 25), I("shamt", 24, 20, "imm"), I("rs1", 19, 15), I("funct3", 14, 12),
                   I("rd", 11, 7), I("opcode", 6, 0)],
     "slli srli srai, rori, bclri bexti binvi bseti"),
    ("I (unary)", [I("funct7", 31, 25), I("funct5", 24, 20), I("rs1", 19, 15), I("funct3", 14, 12),
                   I("rd", 11, 7), I("opcode", 6, 0)],
     "clz ctz cpop sext.b sext.h (OP-IMM)"),
    ("I (unary 12)", [I("funct12", 31, 20), I("rs1", 19, 15), I("funct3", 14, 12), I("rd", 11, 7),
                      I("opcode", 6, 0)],
     "orc.b, rev8 (OP-IMM); ecall, ebreak (SYSTEM)"),
    ("R (unary)", [I("funct7", 31, 25), I("rs2=0", 24, 20, "funct"), I("rs1", 19, 15), I("funct3", 14, 12),
                   I("rd", 11, 7), I("opcode", 6, 0)],
     "zext.h (OP)"),
    ("I (fence)", [I("fm", 31, 28), I("pred", 27, 24, "imm"), I("succ", 23, 20, "imm"), I("rs1", 19, 15),
                   I("funct3", 14, 12), I("rd", 11, 7), I("opcode", 6, 0)],
     "fence, fence.tso, pause; pred/succ bits = I O R W"),
]

IMMEDIATES = [
    ("I-immediate", [I("inst[31] (sign)", 31, 11, "imm"), I("inst[30:25]", 10, 5, "imm"),
                     I("inst[24:21]", 4, 1, "imm"), I("[20]", 0, 0, "imm")]),
    ("S-immediate", [I("inst[31] (sign)", 31, 11, "imm"), I("inst[30:25]", 10, 5, "imm"),
                     I("inst[11:8]", 4, 1, "imm"), I("[7]", 0, 0, "imm")]),
    ("B-immediate", [I("inst[31] (sign)", 31, 12, "imm"), I("[7]", 11, 11, "imm"), I("inst[30:25]", 10, 5, "imm"),
                     I("inst[11:8]", 4, 1, "imm"), I("0", 0, 0, "funct")]),
    ("U-immediate", [I("inst[31:12]", 31, 12, "imm"), I("0", 11, 0, "funct")]),
    ("J-immediate", [I("inst[31] (sign)", 31, 20, "imm"), I("inst[19:12]", 19, 12, "imm"), I("[20]", 11, 11, "imm"),
                     I("inst[30:25]", 10, 5, "imm"), I("inst[24:21]", 4, 1, "imm"), I("0", 0, 0, "funct")]),
]

# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

INSTR_COLS = [("Mnemonic", 20), ("Arguments", 30), ("Format", 17), ("Opcode", 26), ("funct3", 14),
              ("funct7 / fixed", 30), ("Description", 97), ("Example", 35), ("Hex · signed int32", 36)]


def base_table_style(n_rows, group_rows=()):
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, n_rows):
        if r % 2 == 0 and r not in group_rows:
            st.append(("BACKGROUND", (0, r), (-1, r), ZEBRA))
    for r in group_rows:
        st += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), GROUP_BG)]
    return TableStyle(st)


def instruction_table(title, items):
    """One group: header row + group title row (both repeated on page breaks) + instructions."""
    header = [P(esc(h), HEAD) for h, _ in INSTR_COLS]
    rows = [header, [P(f"<b>{esc(title)}</b>")] + [""] * (len(INSTR_COLS) - 1)]
    for mn, args, desc, example in items:
        op = rv.OPS[mn]
        enc = rv.encode(example)
        opcode = f"{rv.OPCODE_NAMES[op.opcode]}<br/><font name='Mono' size='6.4'>{op.opcode:07b}</font>"
        funct3 = "–" if op.fmt in ("U", "J") else format((enc.word >> 12) & 7, "03b")
        rows.append([
            code(mn, bold=True),
            code(args or "–"),
            P(esc(short_format(op))),
            P(opcode),
            code(funct3),
            P(f"<font name='Mono' size='6.4'>{esc(funct_column(op))}</font>"),
            P(desc, DESC),
            code(example),
            P(f"<font name='Mono' size='6.6'>{enc.hex}</font><br/>"
              f"<font name='Mono-Bold' size='6.6'>{enc.signed}</font>"),
        ])
    width = landscape(A4)[0] - 20 * mm
    total = sum(w for _, w in INSTR_COLS)
    t = Table(rows, colWidths=[width * w / total for _, w in INSTR_COLS], repeatRows=2)
    style = base_table_style(len(rows), group_rows=(1,))
    style.add("BACKGROUND", (3, 2), (3, -1), KIND["opcode"])
    t.setStyle(style)
    return t


def simple_table(header, rows, widths, mono_cols=(), bold_cols=()):
    body = [[P(esc(h), HEAD) for h in header]]
    for row in rows:
        cells = []
        for i, v in enumerate(row):
            if isinstance(v, Flowable):
                cells.append(v)
            elif i in mono_cols:
                cells.append(code(v, bold=i in bold_cols))
            else:
                cells.append(P(v))
        body.append(cells)
    width = landscape(A4)[0] - 20 * mm
    total = sum(widths)
    t = Table(body, colWidths=[width * w / total for w in widths], repeatRows=1)
    t.setStyle(base_table_style(len(body)))
    return t


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------

def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Sans", 6.5)
    canvas.setFillColor(colors.HexColor("#666"))
    w, h = landscape(A4)
    canvas.drawString(10 * mm, 6 * mm, "FRISC-V · RV32IMB cheat sheet · source: RISC-V Unprivileged ISA "
                                        "(riscv-unprivileged.pdf), Ch. 2, 12, 30, 36 · generated by "
                                        "cheatsheet/build_cheatsheet.py from debug_gui/rv32_encoder.py")
    canvas.drawRightString(w - 10 * mm, 6 * mm, f"page {doc.page}")
    canvas.restoreState()


def build():
    check_coverage()
    doc = SimpleDocTemplate(OUT, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=11 * mm,
                            title="RV32IMB instruction cheat sheet", author="FRISC-V",
                            subject="RISC-V RV32I + M + B (Zba, Zbb, Zbs) instructions and encodings")
    width = landscape(A4)[0] - 20 * mm
    story = []

    # ---- page 1: formats ------------------------------------------------
    story.append(P("RV32IMB instruction cheat sheet", H1))
    story.append(P("RV32I base + M (multiply/divide) + B (= Zba + Zbb + Zbs bit manipulation). All instructions "
                   "are 32 bits. <b>sext</b> = sign-extend, <b>zext</b> = zero-extend, all registers are 32 bits. "
                   "Immediates in examples are decimal unless written 0x…; branch and jump offsets are byte "
                   "offsets relative to the instruction itself. The <b>signed int32</b> column is the "
                   "machine word read as a two's-complement number (what a Factorio signal carries).", NOTE))
    story.append(Spacer(1, 4))
    legend = Table([[P("<b>Field colours:</b>"), P("opcode"), P("funct3 / funct7 / fixed"), P("register"),
                     P("immediate")]],
                   colWidths=[70, 50, 100, 55, 60], hAlign="LEFT")
    legend.setStyle(TableStyle([("BACKGROUND", (1, 0), (1, 0), KIND["opcode"]),
                                ("BACKGROUND", (2, 0), (2, 0), KIND["funct"]),
                                ("BACKGROUND", (3, 0), (3, 0), KIND["reg"]),
                                ("BACKGROUND", (4, 0), (4, 0), KIND["imm"]),
                                ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(legend)

    story.append(P("Base instruction formats (Sec. 2.2 / 2.3)", H2))
    for label, fields, note in FORMATS:
        story.append(FormatDiagram(label, fields, note, width=width, note_w=215))
    story.append(P("Format variants used by specific instructions", H2))
    for label, fields, note in VARIANTS:
        story.append(FormatDiagram(label, fields, note, width=width, note_w=215))

    story.append(PageBreak())
    story.append(P("Immediate values produced by each format (Figure 1): bit positions of the 32-bit "
                   "immediate, labelled with the instruction bits that fill them", H2))
    for label, fields in IMMEDIATES:
        story.append(FormatDiagram(label, fields, width=width, note_w=215))
    story.append(Spacer(1, 2))
    story.append(P("The sign bit of every immediate is always inst[31]. Ranges: I/S −2048…2047 · "
                   "B −4096…4094 (even) · J −1048576…1048574 (even) · U: imm20 0…0xFFFFF (value = imm20 × 4096) · "
                   "shamt 0…31.", NOTE))

    story.append(P("Major opcodes used (Table 72, inst[1:0] = 11)", H2))
    by_opcode = {}
    for op in rv.OPS.values():
        by_opcode.setdefault(op.opcode, []).append(op.mnemonic)
    op_rows = []
    for opc in sorted(by_opcode):
        fmts = sorted({short_format(rv.OPS[m]) for m in by_opcode[opc]})
        op_rows.append([rv.OPCODE_NAMES[opc], format(opc, "07b"), f"0x{opc:02X}", str(opc), ", ".join(fmts),
                        " ".join(by_opcode[opc])])
    story.append(simple_table(["Opcode", "inst[6:0]", "Hex", "Dec", "Formats", "Instructions"], op_rows,
                              [22, 18, 10, 9, 38, 180], mono_cols=(1, 2, 3, 5), bold_cols=(1,)))

    story.append(P("Registers (x0 is hard-wired to 0; ABI names accepted by the tools)", H2))
    names = rv.ABI_NAMES
    reg_rows = []
    for r in range(8):
        row = []
        for block in range(4):
            n = block * 8 + r
            row += [f"x{n}", names[n] + (" / fp" if n == 8 else "")]
        reg_rows.append(row)
    story.append(simple_table(["Reg", "ABI", "Reg", "ABI", "Reg", "ABI", "Reg", "ABI"], reg_rows,
                              [10, 18] * 4, mono_cols=range(8), bold_cols=(0, 2, 4, 6)))

    # ---- instruction tables ------------------------------------------------
    story.append(PageBreak())
    story.append(P("Instructions", H2))
    for title, items in GROUPS:
        story.append(CondPageBreak(45 * mm))   # never strand a group title at the page bottom
        story.append(instruction_table(title, items))
        story.append(Spacer(1, 5))

    # ---- pseudoinstructions -----------------------------------------------
    story.append(CondPageBreak(90 * mm))
    story.append(P("Pseudoinstructions (only those defined in the spec)", H2))
    rows = []
    for syntax, expansion, meaning, example in PSEUDOS:
        e = rv.encode(example)
        rows.append([syntax, expansion, meaning, example, e.canonical, f"{e.hex}  ·  {e.signed}"])
    story.append(simple_table(["Pseudo", "Assembled as", "Meaning", "Example", "Example assembled as",
                               "Hex · signed int32"], rows, [30, 34, 60, 26, 36, 40],
                              mono_cols=(0, 1, 3, 4, 5), bold_cols=(0,)))
    story.append(Spacer(1, 4))
    story.append(KeepTogether([
        P("Operand short forms accepted by the tools", H2),
        simple_table(["Short form", "Same as", "Meaning", "Example", "Example assembled as", "Hex · signed int32"],
                     [[s, x, m, ex, rv.encode(ex).canonical,
                       f"{rv.encode(ex).hex}  ·  {rv.encode(ex).signed}"] for s, x, m, ex in SHORT_FORMS],
                     [30, 34, 60, 26, 36, 40], mono_cols=(0, 1, 3, 4, 5), bold_cols=(0,)),
    ]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return OUT


if __name__ == "__main__":
    print(build())
