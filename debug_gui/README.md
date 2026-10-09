# debug_gui – RISC-V instruction encoder & number converter

A small Qt (PySide6) tool for debugging the Factorio RISC-V CPU.

**Tab 1: Instruction encoder.** Type one instruction (e.g. `addi x1, x2, 23`) and it shows, live:

* the machine code as **binary** (split at field boundaries), **hex**, **signed decimal**
  (int32: a word with bit 31 set is shown as a negative number) and unsigned decimal,
  each with a *Copy* button
* a bit-field diagram in the style of the spec, plus a table of every field
  (opcode, funct3/funct7, rd/rs1/rs2, immediate pieces …) with bit range, binary, hex, decimal and meaning
* the full immediate value as the CPU sees it, plus the real instruction when you enter a pseudoinstruction

**Tab 2: Number converter.** Binary, hex and signed decimal fields, all treated as 32-bit two's
complement. Edit any of them and the other two update live.

## Run

```bash
cd debug_gui
pip install -r requirements.txt
python gui.py
```

## Supported instructions (RV32 I + M + B + Zicsr + privileged)

| Extension | Instructions |
|---|---|
| RV32I | `lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw lbu lhu sb sh sw addi slti sltiu xori ori andi slli srli srai add sub sll slt sltu xor srl sra or and fence fence.tso pause ecall ebreak` |
| M | `mul mulh mulhsu mulhu div divu rem remu` |
| B = Zba | `sh1add sh2add sh3add` |
| B = Zbb | `andn orn xnor clz ctz cpop max maxu min minu sext.b sext.h zext.h rol ror rori orc.b rev8` |
| B = Zbs | `bclr bclri bext bexti binv binvi bset bseti` |
| Zicsr | `csrrw csrrs csrrc csrrwi csrrsi csrrci` |
| Privileged | `mret wfi` (machine mode), `sret sfence.vma` (supervisor mode) |
| Pseudo | `nop mv not seqz snez j jr ret bgt bgtu ble bleu csrr csrw csrs csrc csrwi csrsi csrci rdcycle[h] rdtime[h] rdinstret[h]` (only those defined in the spec) |

Syntax notes:

* Registers: `x0`–`x31`, or the ABI names (`zero ra sp gp tp t0-t6 s0-s11 fp a0-a7`).
* Loads, stores and `jalr`: `lw x1, -4(x2)`, `sw x5, 8(sp)`, `jalr x1, 0(x5)`. `jalr x1, x5, 0` and `jalr x5` also work.
* Branches and `jal` take a **byte offset** relative to the instruction (no labels), e.g. `beq x1, x2, -8`.
  It must be even. Range: ±4 KiB for branches, ±1 MiB for `jal`.
* `lui` / `auipc` take the 20-bit upper immediate (`0` … `0xFFFFF`), as in `lui x1, 0x12345`.
* Immediates can be written in decimal, `0x` hex, `0b` binary or `0o` octal.
* CSR operands are a 12-bit number (`0x300`) or a name: `cycle time instret` (+`h`), `mvendorid marchid mimpid
  mhartid mconfigptr`, `mstatus misa medeleg mideleg mie mtvec mcounteren mstatush mcountinhibit`,
  `mscratch mepc mcause mtval mip`, `mcycle minstret` (+`h`). Example: `csrrw t0, mstatus, t1`, `csrr a0, mepc`.
* `sfence.vma` takes 0, 1 or 2 registers (`sfence.vma`, `sfence.vma rs1`, `sfence.vma rs1, rs2`).

## Where the encodings come from

All encodings follow `../riscv-unprivileged.pdf` only: formats from §2.2–2.3, opcodes, funct3 and funct7
from the Chapter 36 listings (RV32I, RV32M), and the B extension from §30.1–30.9 using the **RV32**
encodings (`rev8`, `zext.h` and the shift-immediates differ on RV64). The source for each part is
cited at the top of `rv32_encoder.py`. The ABI register names are the one exception: they come from the
psABI, not the ISA spec.

The CSR instructions come from Volume I as well (§6.1 and the Chapter 36 Zicsr table). The privileged parts
follow `../riscv-privileged.pdf`: `mret`, `sret`, `wfi` and `sfence.vma` from Chapter 19 (Figure 125), and the
CSR names and addresses from §2.2 (Table 4 for the counters, Table 7 for the machine-level CSRs). The field
view shows `mret`/`sret`/`wfi` split as funct7 + rs2 exactly like Figure 125.

Every encoding is also checked two ways. The encoder packs the fields, checks that they cover exactly
32 bits, then decodes the immediate back out of the word (Figure 1 of the spec) and compares it to the input.

## Tests

```bash
cd debug_gui
python -m unittest discover -s tests -v
```

* Golden vectors plus invalid-input checks, such as out-of-range immediates, odd branch offsets, CSR numbers
  outside 0…0xFFF, unknown CSR names and instructions outside the supported set.
* If LLVM's `llvm-mc` is installed, a randomized cross-check assembles ~34,000 random instances of every
  supported instruction and pseudoinstruction (CSR operands as random numbers and names) with
  `llvm-mc -triple=riscv32 -mattr=+m,+zba,+zbb,+zbs,+zihintpause,+zicsr,+zicntr` and compares every word.
* Round-trip tests for the number converter.
