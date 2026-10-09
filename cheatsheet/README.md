# cheatsheet: RV32IMB + Zicsr + privileged instruction cheat sheet

**[rv32imb_cheatsheet.pdf](rv32imb_cheatsheet.pdf)** is 9 landscape A4 pages:

1. **Base formats:** the R/I/S/B/U/J formats as bit diagrams, plus how each format's immediate is assembled
   (Figure 1).
2. **Format variants:** shift-immediate, unary, `funct12`, fence, CSR (register and immediate source),
   `mret`/`sret`/`wfi`, `sfence.vma`. Also the major opcode table: name, binary/hex/decimal and which
   instructions use it.
3. **Registers** (x0–x31 with ABI names) and the **CSR names** the tools accept, with their addresses.
4. **Every instruction** of RV32I, M, B (Zba, Zbb, Zbs), Zicsr and the privileged `mret`, `wfi`, `sret`,
   `sfence.vma`, 89 in total. Each has mnemonic, arguments, format, major opcode, funct3, funct7 or fixed
   bits, description, and an example with its machine code as hex and as **signed int32** (the value a
   Factorio signal carries).
5. **Pseudoinstructions:** every one the specs define, including the CSR ones (`csrr`, `csrw`, …,
   `rdcycle[h]`), what it is assembled as, and an example. Also the operand short forms the tools accept.

## Regenerate

```bash
pip install reportlab
python cheatsheet/build_cheatsheet.py
```

The script reads opcodes, funct fields and formats from `debug_gui/rv32_encoder.py`, and every example is
assembled with it. That encoder is checked against llvm-mc, so the sheet always agrees with the tools. The
build stops if an instruction is missing or an example doesn't assemble to its own mnemonic.

Descriptions follow the specs:
* `riscv-unprivileged.pdf`, Chapters 2, 6, 7, 12, 30 and 36.
* `riscv-privileged.pdf`: encodings from Chapter 19 (Figure 125), MRET/SRET/WFI semantics from §3.1.6.1 and
  §3.3, CSR addresses from §2.2 (Tables 4 and 7).
