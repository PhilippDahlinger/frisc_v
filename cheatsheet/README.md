# cheatsheet: RV32IMB instruction cheat sheet

**[rv32imb_cheatsheet.pdf](rv32imb_cheatsheet.pdf)** is 7 landscape A4 pages:

1. **Encoding formats:** the R/I/S/B/U/J formats plus the variants the B extension uses (shift-immediate,
   unary, `funct12`, fence) as bit diagrams. Also how each format's immediate is assembled (Figure 1).
2. **Major opcode table:** name, binary/hex/decimal and which instructions use it. Also the register table
   (x0–x31 with ABI names).
3. **Every instruction** of RV32I, M and B (Zba, Zbb, Zbs), 79 in total: mnemonic, arguments, format, major
   opcode, funct3, funct7 or fixed bits, description, and an example with its machine code as hex and as
   **signed int32** (the value a Factorio signal carries).
4. **Pseudoinstructions:** every one the spec defines, what it is assembled as, and an example. Also the
   operand short forms the tools accept.

## Regenerate

```bash
pip install reportlab
python cheatsheet/build_cheatsheet.py
```

The script reads opcodes, funct fields and formats from `debug_gui/rv32_encoder.py`, and every example is
assembled with it. That encoder is checked against llvm-mc, so the sheet always agrees with the tools. The
build stops if an instruction is missing or an example doesn't assemble to its own mnemonic. Descriptions
follow the spec (`riscv-unprivileged.pdf`, Chapters 2, 12, 30 and 36).
