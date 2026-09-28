-- Single-instruction RV32IMB assembler that also reports every encoded field.
--
-- This is a line-by-line port of debug_gui/rv32_encoder.py (see there for the
-- spec references). Keep the two in sync: factorio_mod/tests/ checks that both
-- give identical results (words, fields, texts and error messages).
--
-- Pure Lua 5.2 with no Factorio API use, so it also runs in a plain interpreter.
-- Numbers are doubles; every value handled here stays far below 2^53, so all
-- arithmetic is exact.

local M = {}

-- --------------------------------------------------------------------------
-- Registers
-- --------------------------------------------------------------------------

-- Standard calling-convention (psABI) names; the ISA itself only has x0..x31.
local ABI_NAMES = {
  "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
  "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
  "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
  "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
}
local REGISTERS = {}
for i = 0, 31 do
  REGISTERS["x" .. i] = i
  REGISTERS[ABI_NAMES[i + 1]] = i
end
REGISTERS["fp"] = 8
M.ABI_NAMES = ABI_NAMES

local function reg_label(n)
  return "x" .. n .. " (" .. ABI_NAMES[n + 1] .. ")"
end

-- --------------------------------------------------------------------------
-- Major opcodes, Table 72 (inst[1:0] = 11)
-- --------------------------------------------------------------------------

local OPCODE_NAMES = {
  [0x03] = "LOAD",     -- 0000011
  [0x0F] = "MISC-MEM", -- 0001111
  [0x13] = "OP-IMM",   -- 0010011
  [0x17] = "AUIPC",    -- 0010111
  [0x23] = "STORE",    -- 0100011
  [0x33] = "OP",       -- 0110011
  [0x37] = "LUI",      -- 0110111
  [0x63] = "BRANCH",   -- 1100011
  [0x67] = "JALR",     -- 1100111
  [0x6F] = "JAL",      -- 1101111
  [0x73] = "SYSTEM",   -- 1110011
}

-- --------------------------------------------------------------------------
-- Instruction table (Chapter 36 and Sec. 30.9)
-- --------------------------------------------------------------------------

local function b(s) return tonumber((s:gsub("_", "")), 2) end

local LUI, AUIPC, JAL, JALR = b"0110111", b"0010111", b"1101111", b"1100111"
local BRANCH, LOAD, STORE = b"1100011", b"0000011", b"0100011"
local OP_IMM, OP, MISC_MEM, SYSTEM = b"0010011", b"0110011", b"0001111", b"1110011"

local OPS = {}
local function op(mnemonic, fmt, opcode, t)
  t = t or {}
  OPS[mnemonic] = {
    mnemonic = mnemonic, fmt = fmt, opcode = opcode,
    funct3 = t.funct3 or 0, funct7 = t.funct7 or 0, word = t.word or 0,
    ext = t.ext or "RV32I", fixed = t.fixed or {},
  }
end

op("lui", "U", LUI)
op("auipc", "U", AUIPC)
op("jal", "J", JAL)
op("jalr", "JALR", JALR, {funct3 = b"000"})
op("beq", "B", BRANCH, {funct3 = b"000"})
op("bne", "B", BRANCH, {funct3 = b"001"})
op("blt", "B", BRANCH, {funct3 = b"100"})
op("bge", "B", BRANCH, {funct3 = b"101"})
op("bltu", "B", BRANCH, {funct3 = b"110"})
op("bgeu", "B", BRANCH, {funct3 = b"111"})
op("lb", "LOAD", LOAD, {funct3 = b"000"})
op("lh", "LOAD", LOAD, {funct3 = b"001"})
op("lw", "LOAD", LOAD, {funct3 = b"010"})
op("lbu", "LOAD", LOAD, {funct3 = b"100"})
op("lhu", "LOAD", LOAD, {funct3 = b"101"})
op("sb", "S", STORE, {funct3 = b"000"})
op("sh", "S", STORE, {funct3 = b"001"})
op("sw", "S", STORE, {funct3 = b"010"})
op("addi", "I", OP_IMM, {funct3 = b"000"})
op("slti", "I", OP_IMM, {funct3 = b"010"})
op("sltiu", "I", OP_IMM, {funct3 = b"011"})
op("xori", "I", OP_IMM, {funct3 = b"100"})
op("ori", "I", OP_IMM, {funct3 = b"110"})
op("andi", "I", OP_IMM, {funct3 = b"111"})
op("slli", "SHIFT", OP_IMM, {funct3 = b"001", funct7 = b"0000000"})
op("srli", "SHIFT", OP_IMM, {funct3 = b"101", funct7 = b"0000000"})
op("srai", "SHIFT", OP_IMM, {funct3 = b"101", funct7 = b"0100000"})
op("add", "R", OP, {funct3 = b"000", funct7 = b"0000000"})
op("sub", "R", OP, {funct3 = b"000", funct7 = b"0100000"})
op("sll", "R", OP, {funct3 = b"001", funct7 = b"0000000"})
op("slt", "R", OP, {funct3 = b"010", funct7 = b"0000000"})
op("sltu", "R", OP, {funct3 = b"011", funct7 = b"0000000"})
op("xor", "R", OP, {funct3 = b"100", funct7 = b"0000000"})
op("srl", "R", OP, {funct3 = b"101", funct7 = b"0000000"})
op("sra", "R", OP, {funct3 = b"101", funct7 = b"0100000"})
op("or", "R", OP, {funct3 = b"110", funct7 = b"0000000"})
op("and", "R", OP, {funct3 = b"111", funct7 = b"0000000"})
op("fence", "FENCE", MISC_MEM, {funct3 = b"000"})
-- fm=1000 pred=0011 succ=0011 rs1=0 funct3=000 rd=0 MISC-MEM
op("fence.tso", "FIXED", MISC_MEM, {word = b"1000_0011_0011_00000_000_00000_0001111"})
-- fm=0000 pred=0001 succ=0000 rs1=0 funct3=000 rd=0 MISC-MEM
op("pause", "FIXED", MISC_MEM, {word = b"0000_0001_0000_00000_000_00000_0001111", ext = "Zihintpause"})
op("ecall", "FIXED", SYSTEM, {word = b"000000000000_00000_000_00000_1110011"})
op("ebreak", "FIXED", SYSTEM, {word = b"000000000001_00000_000_00000_1110011"})
-- RV32M
op("mul", "R", OP, {funct3 = b"000", funct7 = b"0000001", ext = "RV32M"})
op("mulh", "R", OP, {funct3 = b"001", funct7 = b"0000001", ext = "RV32M"})
op("mulhsu", "R", OP, {funct3 = b"010", funct7 = b"0000001", ext = "RV32M"})
op("mulhu", "R", OP, {funct3 = b"011", funct7 = b"0000001", ext = "RV32M"})
op("div", "R", OP, {funct3 = b"100", funct7 = b"0000001", ext = "RV32M"})
op("divu", "R", OP, {funct3 = b"101", funct7 = b"0000001", ext = "RV32M"})
op("rem", "R", OP, {funct3 = b"110", funct7 = b"0000001", ext = "RV32M"})
op("remu", "R", OP, {funct3 = b"111", funct7 = b"0000001", ext = "RV32M"})
-- ---- B = Zba + Zbb + Zbs (Sec. 30.9, RV32 encodings) ----
-- Zba
op("sh1add", "R", OP, {funct3 = b"010", funct7 = b"0010000", ext = "Zba"})
op("sh2add", "R", OP, {funct3 = b"100", funct7 = b"0010000", ext = "Zba"})
op("sh3add", "R", OP, {funct3 = b"110", funct7 = b"0010000", ext = "Zba"})
-- Zbb: logical with negate
op("andn", "R", OP, {funct3 = b"111", funct7 = b"0100000", ext = "Zbb"})
op("orn", "R", OP, {funct3 = b"110", funct7 = b"0100000", ext = "Zbb"})
op("xnor", "R", OP, {funct3 = b"100", funct7 = b"0100000", ext = "Zbb"})
-- Zbb: count leading/trailing zeros, population count
op("clz", "UNARY", OP_IMM, {funct3 = b"001", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0110000"}, {"funct5", 24, 20, b"00000"}}})
op("ctz", "UNARY", OP_IMM, {funct3 = b"001", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0110000"}, {"funct5", 24, 20, b"00001"}}})
op("cpop", "UNARY", OP_IMM, {funct3 = b"001", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0110000"}, {"funct5", 24, 20, b"00010"}}})
-- Zbb: integer min/max
op("max", "R", OP, {funct3 = b"110", funct7 = b"0000101", ext = "Zbb"})
op("maxu", "R", OP, {funct3 = b"111", funct7 = b"0000101", ext = "Zbb"})
op("min", "R", OP, {funct3 = b"100", funct7 = b"0000101", ext = "Zbb"})
op("minu", "R", OP, {funct3 = b"101", funct7 = b"0000101", ext = "Zbb"})
-- Zbb: sign/zero extension
op("sext.b", "UNARY", OP_IMM, {funct3 = b"001", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0110000"}, {"funct5", 24, 20, b"00100"}}})
op("sext.h", "UNARY", OP_IMM, {funct3 = b"001", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0110000"}, {"funct5", 24, 20, b"00101"}}})
op("zext.h", "UNARY", OP, {funct3 = b"100", ext = "Zbb",
  fixed = {{"funct7", 31, 25, b"0000100"}, {"rs2 (fixed)", 24, 20, b"00000"}}})
-- Zbb: rotation
op("rol", "R", OP, {funct3 = b"001", funct7 = b"0110000", ext = "Zbb"})
op("ror", "R", OP, {funct3 = b"101", funct7 = b"0110000", ext = "Zbb"})
op("rori", "SHIFT", OP_IMM, {funct3 = b"101", funct7 = b"0110000", ext = "Zbb"})
-- Zbb: OR-combine, byte-reverse
op("orc.b", "UNARY", OP_IMM, {funct3 = b"101", ext = "Zbb",
  fixed = {{"funct12", 31, 20, b"001010000111"}}})
op("rev8", "UNARY", OP_IMM, {funct3 = b"101", ext = "Zbb",
  fixed = {{"funct12", 31, 20, b"011010011000"}}})
-- Zbs: single-bit instructions
op("bclr", "R", OP, {funct3 = b"001", funct7 = b"0100100", ext = "Zbs"})
op("bclri", "SHIFT", OP_IMM, {funct3 = b"001", funct7 = b"0100100", ext = "Zbs"})
op("bext", "R", OP, {funct3 = b"101", funct7 = b"0100100", ext = "Zbs"})
op("bexti", "SHIFT", OP_IMM, {funct3 = b"101", funct7 = b"0100100", ext = "Zbs"})
op("binv", "R", OP, {funct3 = b"001", funct7 = b"0110100", ext = "Zbs"})
op("binvi", "SHIFT", OP_IMM, {funct3 = b"001", funct7 = b"0110100", ext = "Zbs"})
op("bset", "R", OP, {funct3 = b"001", funct7 = b"0010100", ext = "Zbs"})
op("bseti", "SHIFT", OP_IMM, {funct3 = b"001", funct7 = b"0010100", ext = "Zbs"})
M.OPS = OPS

local FORMAT_NAMES = {
  R = "R-type",
  I = "I-type",
  SHIFT = "I-type (shift by constant)",
  LOAD = "I-type (load)",
  JALR = "I-type (JALR)",
  S = "S-type",
  B = "B-type",
  U = "U-type",
  J = "J-type",
  FENCE = "I-type (FENCE)",
}

local function format_name(o)
  if o.fmt == "UNARY" then
    return o.opcode == OP and "R-type (unary, rs2 field fixed)" or "I-type (unary, imm field fixed)"
  end
  if o.fmt == "FIXED" then
    return o.opcode == MISC_MEM and "I-type (FENCE)" or "I-type (SYSTEM)"
  end
  return FORMAT_NAMES[o.fmt]
end

-- --------------------------------------------------------------------------
-- Helpers: errors, strings, numbers
-- --------------------------------------------------------------------------

-- Assembly errors are raised as tables so they can be told apart from bugs.
local function asm_error(msg) error({asm_error = msg}, 0) end

local function trim(s) return (s:match("^%s*(.-)%s*$")) end

local function d(v) return string.format("%d", v) end

local function pow2(n) return 2 ^ n end

-- bits msb..lsb of a non-negative value
local function bits(value, msb, lsb)
  return math.floor(value / pow2(lsb)) % pow2(msb - lsb + 1)
end

local WORD = pow2(32)

local function to_signed(word)
  word = word % WORD
  if word >= pow2(31) then return word - WORD end
  return word
end
M.to_signed = to_signed

local function bin_str(value, width)
  local t = {}
  for i = width - 1, 0, -1 do
    t[#t + 1] = (math.floor(value / pow2(i)) % 2 == 1) and "1" or "0"
  end
  return table.concat(t)
end
M.bin_str = bin_str

local function hex_str(value, digits)
  return string.format("%0" .. digits .. "X", value)
end
M.hex_str = hex_str

-- --------------------------------------------------------------------------
-- Operand parsing
-- --------------------------------------------------------------------------

local function parse_int(text, what)
  what = what or "immediate"
  local s = trim(text)
  local body = s:match("^[+-]?(.*)$")
  local ok = body:match("^0[xX][%x_]+$") or body:match("^0[bB][01_]+$")
    or body:match("^0[oO][0-7_]+$") or body:match("^%d[%d_]*$")
  if not ok then
    asm_error("invalid " .. what .. ": '" .. s .. "' (use decimal, 0x.., 0b.. or 0o..)")
  end
  local neg = s:sub(1, 1) == "-"
  local base = 10
  local prefix = body:sub(1, 2):lower()
  if prefix == "0x" or prefix == "0b" or prefix == "0o" then
    base = ({["0x"] = 16, ["0b"] = 2, ["0o"] = 8})[prefix]
    body = body:sub(3)
  end
  local digits = body:gsub("_", "")
  if digits == "" then
    asm_error("invalid " .. what .. ": '" .. s .. "' (no digits)")
  end
  local v = tonumber(digits, base)
  if v >= pow2(52) then
    asm_error("invalid " .. what .. ": '" .. s .. "' (too large)")
  end
  if neg then return -v end
  return v
end

local function parse_reg(text)
  local s = trim(text):lower()
  local r = REGISTERS[s]
  if not r then
    asm_error("unknown register '" .. trim(text) .. "' (use x0..x31 or ABI names)")
  end
  return r
end

-- 'offset(reg)' or '(reg)'  ->  offset, reg
local function parse_mem(text)
  local off, reg = trim(text):match("^(.-)%(%s*(%w+)%s*%)$")
  if not off then
    asm_error("expected memory operand 'offset(rs1)', got '" .. trim(text) .. "'")
  end
  off = trim(off)
  local v = 0
  if off ~= "" then v = parse_int(off, "offset") end
  return v, parse_reg(reg)
end

local function check_range(v, lo, hi, what)
  if v < lo or v > hi then
    asm_error(what .. " " .. d(v) .. " out of range [" .. d(lo) .. ", " .. d(hi) .. "]")
  end
end

local function check_even(v, what)
  if v % 2 ~= 0 then
    asm_error(what .. " " .. d(v) .. " must be a multiple of 2 (bit 0 is not encoded)")
  end
end

local FENCE_BITS = {i = 8, o = 4, r = 2, w = 1}   -- PI/PO/PR/PW, SI/SO/SR/SW (Sec. 2.7)

local function parse_fence_set(text)
  local s = trim(text):lower()
  if s == "0" then return 0 end
  local value, last = 0, -1
  for c in s:gmatch(".") do
    local order = ("iorw"):find(c, 1, true)
    order = order and (order - 1) or -1
    if order < 0 or order <= last then
      asm_error("invalid FENCE set '" .. trim(text) .. "' (letters from i, o, r, w in that order)")
    end
    last = order
    value = value + FENCE_BITS[c]
  end
  if s == "" then asm_error("empty FENCE set") end
  return value
end

local function fence_set_str(value)
  local out = ""
  for c in ("iorw"):gmatch(".") do
    if bits(value, 3, 0) % (FENCE_BITS[c] * 2) >= FENCE_BITS[c] then out = out .. c end
  end
  if out == "" then return "0" end
  return out
end

local function split_operands(text)
  text = trim(text)
  if text == "" then return {} end
  local parts = {}
  local start = 1
  while true do
    local i = text:find(",", start, true)
    parts[#parts + 1] = trim(text:sub(start, (i or 0) - 1))
    if not i then break end
    start = i + 1
  end
  for _, p in ipairs(parts) do
    if p == "" then asm_error("empty operand (check the commas)") end
  end
  return parts
end

-- --------------------------------------------------------------------------
-- Field builders per format (layouts from Sec. 2.2/2.3 and Chapter 36)
-- --------------------------------------------------------------------------

local function field(name, msb, lsb, value, meaning)
  return {name = name, msb = msb, lsb = lsb, value = value, meaning = meaning or "",
          width = msb - lsb + 1}
end

local function opcode_field(opcode)
  return field("opcode", 6, 0, opcode, OPCODE_NAMES[opcode] or "?")
end

local function reg_field(name, msb, n)
  return field(name, msb, msb - 4, n, reg_label(n))
end

local function funct3_field(o)
  return field("funct3", 14, 12, o.funct3, o.mnemonic:upper())
end

local function fields_r(o, rd, rs1, rs2)
  return {
    field("funct7", 31, 25, o.funct7, o.mnemonic:upper()),
    reg_field("rs2", 24, rs2),
    reg_field("rs1", 19, rs1),
    funct3_field(o),
    reg_field("rd", 11, rd),
    opcode_field(o.opcode),
  }
end

local function fields_i(o, rd, rs1, imm)
  return {
    field("imm[11:0]", 31, 20, imm % 4096, d(imm) .. " (sign-extended from bit 11)"),
    reg_field("rs1", 19, rs1),
    funct3_field(o),
    reg_field("rd", 11, rd),
    opcode_field(o.opcode),
  }
end

local function fields_shift(o, rd, rs1, shamt)
  -- Base shifts (Sec. 2.4.1) and the B shift-immediate forms (rori, b*i)
  -- share this layout: a fixed funct7 in imm[11:5] and shamt[4:0] below it.
  local meaning, amount
  local mn = o.mnemonic
  if mn == "slli" or mn == "srli" or mn == "srai" then
    meaning = mn:upper() .. " (bit 30 selects arithmetic right shift)"
    amount = "shift amount " .. d(shamt)
  else
    meaning = mn:upper()
    amount = (mn == "rori" and "rotate amount " or "bit index ") .. d(shamt)
  end
  return {
    field("funct7", 31, 25, o.funct7, meaning),
    field("shamt[4:0]", 24, 20, shamt, amount),
    reg_field("rs1", 19, rs1),
    funct3_field(o),
    reg_field("rd", 11, rd),
    opcode_field(o.opcode),
  }
end

local function fields_s(o, rs1, rs2, imm)
  local u = imm % 4096
  return {
    field("imm[11:5]", 31, 25, bits(u, 11, 5), "offset bits 11..5 (offset = " .. d(imm) .. ")"),
    reg_field("rs2", 24, rs2),
    reg_field("rs1", 19, rs1),
    funct3_field(o),
    field("imm[4:0]", 11, 7, bits(u, 4, 0), "offset bits 4..0 (offset = " .. d(imm) .. ")"),
    opcode_field(o.opcode),
  }
end

local function fields_b(o, rs1, rs2, imm)
  local u = imm % 8192
  return {
    field("imm[12]", 31, 31, bits(u, 12, 12), "offset bit 12 = sign (offset = " .. d(imm) .. ")"),
    field("imm[10:5]", 30, 25, bits(u, 10, 5), "offset bits 10..5"),
    reg_field("rs2", 24, rs2),
    reg_field("rs1", 19, rs1),
    funct3_field(o),
    field("imm[4:1]", 11, 8, bits(u, 4, 1), "offset bits 4..1 (bit 0 is always 0)"),
    field("imm[11]", 7, 7, bits(u, 11, 11), "offset bit 11"),
    opcode_field(o.opcode),
  }
end

local function fields_u(o, rd, imm20)
  return {
    field("imm[31:12]", 31, 12, imm20, "upper 20 bits (0x" .. hex_str(imm20, 5) .. ")"),
    reg_field("rd", 11, rd),
    opcode_field(o.opcode),
  }
end

local function fields_j(o, rd, imm)
  local u = imm % pow2(21)
  return {
    field("imm[20]", 31, 31, bits(u, 20, 20), "offset bit 20 = sign (offset = " .. d(imm) .. ")"),
    field("imm[10:1]", 30, 21, bits(u, 10, 1), "offset bits 10..1 (bit 0 is always 0)"),
    field("imm[11]", 20, 20, bits(u, 11, 11), "offset bit 11"),
    field("imm[19:12]", 19, 12, bits(u, 19, 12), "offset bits 19..12"),
    reg_field("rd", 11, rd),
    opcode_field(o.opcode),
  }
end

local function fields_fence(o, fm, pred, succ)
  local fm_meaning = "reserved"
  if fm == 0 then fm_meaning = "normal fence" elseif fm == 8 then fm_meaning = "TSO" end
  return {
    field("fm", 31, 28, fm, fm_meaning),
    field("pred", 27, 24, pred, "PI PO PR PW = " .. fence_set_str(pred)),
    field("succ", 23, 20, succ, "SI SO SR SW = " .. fence_set_str(succ)),
    reg_field("rs1", 19, 0),
    funct3_field(o),
    reg_field("rd", 11, 0),
    opcode_field(o.opcode),
  }
end

local function fields_unary(o, rd, rs1)
  local out = {}
  for _, f in ipairs(o.fixed) do
    out[#out + 1] = field(f[1], f[2], f[3], f[4], o.mnemonic:upper())
  end
  out[#out + 1] = reg_field("rs1", 19, rs1)
  out[#out + 1] = funct3_field(o)
  out[#out + 1] = reg_field("rd", 11, rd)
  out[#out + 1] = opcode_field(o.opcode)
  return out
end

local function fields_fixed(o)
  local w = o.word
  if o.mnemonic == "fence.tso" or o.mnemonic == "pause" then
    return fields_fence(o, bits(w, 31, 28), bits(w, 27, 24), bits(w, 23, 20))
  end
  if o.mnemonic == "ecall" or o.mnemonic == "ebreak" then  -- Sec. 2.8
    return {
      field("funct12", 31, 20, bits(w, 31, 20), o.mnemonic:upper()),
      reg_field("rs1", 19, 0),
      field("funct3", 14, 12, bits(w, 14, 12), "PRIV"),
      reg_field("rd", 11, 0),
      opcode_field(o.opcode),
    }
  end
  error("no fixed layout for " .. o.mnemonic)
end

-- Pack the fields into a word, checking they tile bits 31..0 exactly.
local function assemble_fields(fields)
  local word, covered = 0, {}
  for _, f in ipairs(fields) do
    if f.value < 0 or f.value >= pow2(f.width) then
      error("field " .. f.name .. " value " .. d(f.value) .. " wider than " .. f.width .. " bits")
    end
    for bit = f.lsb, f.msb do
      if covered[bit] then error("field " .. f.name .. " overlaps another field") end
      covered[bit] = true
    end
    word = word + f.value * pow2(f.lsb)
  end
  for bit = 0, 31 do
    if not covered[bit] then error("fields do not cover all 32 bits") end
  end
  return word
end

-- Immediate decoding straight from the instruction word (Figure 1), used to
-- double-check every encoding: decode(encode(imm)) must give back imm.
local function sext(v, width)
  if bits(v, width - 1, width - 1) == 1 then return v - pow2(width) end
  return v
end

local function decode_immediate(fmt, w)
  if fmt == "I" or fmt == "LOAD" or fmt == "JALR" then
    return sext(bits(w, 31, 20), 12)
  elseif fmt == "S" then
    return sext(bits(w, 31, 25) * 32 + bits(w, 11, 7), 12)
  elseif fmt == "B" then
    return sext(bits(w, 31, 31) * pow2(12) + bits(w, 7, 7) * pow2(11)
      + bits(w, 30, 25) * 32 + bits(w, 11, 8) * 2, 13)
  elseif fmt == "U" then
    return to_signed(bits(w, 31, 12) * pow2(12))
  elseif fmt == "J" then
    return sext(bits(w, 31, 31) * pow2(20) + bits(w, 19, 12) * pow2(12)
      + bits(w, 20, 20) * pow2(11) + bits(w, 30, 21) * 2, 21)
  elseif fmt == "SHIFT" then
    return bits(w, 24, 20)
  end
  error("no immediate for format " .. fmt)
end

-- --------------------------------------------------------------------------
-- Pseudoinstructions defined in the spec
-- --------------------------------------------------------------------------

local BRANCH_SWAP = {bgt = "blt", bgtu = "bltu", ble = "bge", bleu = "bgeu"}

local function expand_pseudo(mn, ops)
  local function need(n)
    if #ops ~= n then
      asm_error("'" .. mn .. "' expects " .. n .. " operand(s), got " .. #ops)
    end
  end
  if mn == "nop" then                      -- Sec. 2.4.3
    need(0); return "addi", {"x0", "x0", "0"}
  elseif mn == "mv" then                   -- Sec. 2.4.1
    need(2); return "addi", {ops[1], ops[2], "0"}
  elseif mn == "not" then
    need(2); return "xori", {ops[1], ops[2], "-1"}
  elseif mn == "seqz" then
    need(2); return "sltiu", {ops[1], ops[2], "1"}
  elseif mn == "snez" then                 -- Sec. 2.4.2
    need(2); return "sltu", {ops[1], "x0", ops[2]}
  elseif mn == "j" then                    -- Sec. 2.5.1
    need(1); return "jal", {"x0", ops[1]}
  elseif mn == "jr" then
    need(1); return "jalr", {"x0", ops[1], "0"}
  elseif mn == "ret" then
    need(0); return "jalr", {"x0", "x1", "0"}
  elseif BRANCH_SWAP[mn] then              -- Sec. 2.5.2: swap operands
    need(3); return BRANCH_SWAP[mn], {ops[2], ops[1], ops[3]}
  end
  return nil
end

-- --------------------------------------------------------------------------
-- Encoding
-- --------------------------------------------------------------------------

local function encode_op(o, ops)
  local mn, fmt = o.mnemonic, o.fmt

  local function need(...)
    local counts = {...}
    for _, c in ipairs(counts) do
      if #ops == c then return end
    end
    local want = {}
    for _, c in ipairs(counts) do want[#want + 1] = tostring(c) end
    asm_error("'" .. mn .. "' expects " .. table.concat(want, " or ")
      .. " operand(s), got " .. #ops)
  end

  local imm, imm_note, notes = nil, "", {}
  local fields, canonical

  if fmt == "R" then
    need(3)
    local rd, rs1, rs2 = parse_reg(ops[1]), parse_reg(ops[2]), parse_reg(ops[3])
    fields = fields_r(o, rd, rs1, rs2)
    canonical = mn .. " x" .. rd .. ", x" .. rs1 .. ", x" .. rs2

  elseif fmt == "I" then
    need(3)
    local rd, rs1 = parse_reg(ops[1]), parse_reg(ops[2])
    imm = parse_int(ops[3])
    check_range(imm, -2048, 2047, "12-bit signed immediate")
    fields = fields_i(o, rd, rs1, imm)
    canonical = mn .. " x" .. rd .. ", x" .. rs1 .. ", " .. d(imm)
    imm_note = "I-immediate, sign-extended to 32 bits"
    if mn == "sltiu" then
      notes[#notes + 1] = "SLTIU compares against the sign-extended immediate treated as unsigned"
    end

  elseif fmt == "SHIFT" then
    need(3)
    local rd, rs1 = parse_reg(ops[1]), parse_reg(ops[2])
    imm = parse_int(ops[3], "shift amount")
    check_range(imm, 0, 31, "shamt (5-bit unsigned)")
    fields = fields_shift(o, rd, rs1, imm)
    canonical = mn .. " x" .. rd .. ", x" .. rs1 .. ", " .. d(imm)
    imm_note = "shamt[4:0], unsigned"

  elseif fmt == "LOAD" then
    need(2)
    local rd = parse_reg(ops[1])
    local rs1
    imm, rs1 = parse_mem(ops[2])
    check_range(imm, -2048, 2047, "12-bit signed offset")
    fields = fields_i(o, rd, rs1, imm)
    canonical = mn .. " x" .. rd .. ", " .. d(imm) .. "(x" .. rs1 .. ")"
    imm_note = "byte offset added to rs1, sign-extended"

  elseif fmt == "JALR" then
    need(1, 2, 3)
    local rd, rs1
    if #ops == 1 then                    -- jalr rs1  ->  jalr x1, 0(rs1)
      rd, rs1, imm = 1, parse_reg(ops[1]), 0
    elseif #ops == 2 then                -- jalr rd, imm(rs1)
      rd = parse_reg(ops[1])
      imm, rs1 = parse_mem(ops[2])
    else                                 -- jalr rd, rs1, imm
      rd, rs1 = parse_reg(ops[1]), parse_reg(ops[2])
      imm = parse_int(ops[3], "offset")
    end
    check_range(imm, -2048, 2047, "12-bit signed offset")
    fields = fields_i(o, rd, rs1, imm)
    canonical = mn .. " x" .. rd .. ", " .. d(imm) .. "(x" .. rs1 .. ")"
    imm_note = "target = (rs1 + imm) with bit 0 cleared"

  elseif fmt == "S" then
    need(2)
    local rs2 = parse_reg(ops[1])
    local rs1
    imm, rs1 = parse_mem(ops[2])
    check_range(imm, -2048, 2047, "12-bit signed offset")
    fields = fields_s(o, rs1, rs2, imm)
    canonical = mn .. " x" .. rs2 .. ", " .. d(imm) .. "(x" .. rs1 .. ")"
    imm_note = "byte offset added to rs1, sign-extended"

  elseif fmt == "B" then
    need(3)
    local rs1, rs2 = parse_reg(ops[1]), parse_reg(ops[2])
    imm = parse_int(ops[3], "branch offset")
    check_range(imm, -4096, 4094, "13-bit signed branch offset")
    check_even(imm, "branch offset")
    fields = fields_b(o, rs1, rs2, imm)
    canonical = mn .. " x" .. rs1 .. ", x" .. rs2 .. ", " .. d(imm)
    imm_note = "byte offset relative to this instruction's address"

  elseif fmt == "U" then
    need(2)
    local rd = parse_reg(ops[1])
    local imm20 = parse_int(ops[2])
    check_range(imm20, 0, 0xFFFFF, "20-bit upper immediate")
    fields = fields_u(o, rd, imm20)
    canonical = mn .. " x" .. rd .. ", 0x" .. string.format("%X", imm20)
    imm = to_signed(imm20 * 4096)
    imm_note = "U-immediate = imm[31:12] << 12 = 0x" .. hex_str(imm20 * 4096, 8)

  elseif fmt == "J" then
    need(1, 2)
    local rd
    if #ops == 1 then                    -- jal offset  ->  jal x1, offset
      rd, imm = 1, parse_int(ops[1], "jump offset")
    else
      rd = parse_reg(ops[1])
      imm = parse_int(ops[2], "jump offset")
    end
    check_range(imm, -pow2(20), pow2(20) - 2, "21-bit signed jump offset")
    check_even(imm, "jump offset")
    fields = fields_j(o, rd, imm)
    canonical = mn .. " x" .. rd .. ", " .. d(imm)
    imm_note = "byte offset relative to this instruction's address"

  elseif fmt == "FENCE" then
    need(0, 2)
    local pred, succ
    if #ops > 0 then
      pred, succ = parse_fence_set(ops[1]), parse_fence_set(ops[2])
    else
      pred, succ = 15, 15
      notes[#notes + 1] = "'fence' without operands is taken as 'fence iorw, iorw'"
    end
    fields = fields_fence(o, 0, pred, succ)
    canonical = "fence " .. fence_set_str(pred) .. ", " .. fence_set_str(succ)

  elseif fmt == "FIXED" then
    need(0)
    fields = fields_fixed(o)
    canonical = mn

  elseif fmt == "UNARY" then
    need(2)
    local rd, rs1 = parse_reg(ops[1]), parse_reg(ops[2])
    fields = fields_unary(o, rd, rs1)
    canonical = mn .. " x" .. rd .. ", x" .. rs1

  else
    error("unknown format " .. fmt)
  end

  local word = assemble_fields(fields)
  if fmt == "FIXED" and word ~= o.word then
    error(mn .. ": field view disagrees with table encoding")
  end
  if imm ~= nil and decode_immediate(fmt, word) ~= imm then
    error(mn .. ": immediate " .. d(imm) .. " does not round-trip (decoded "
      .. d(decode_immediate(fmt, word)) .. ")")
  end

  local bin = bin_str(word, 32)
  local groups = {}
  for _, f in ipairs(fields) do
    f.bits = bin_str(f.value, f.width)
    groups[#groups + 1] = bin:sub(32 - f.msb, 32 - f.lsb)
  end

  return {
    canonical = canonical, mnemonic = mn, fmt = fmt, ext = o.ext,
    format_name = format_name(o),
    word = word,                       -- unsigned, 0 .. 2^32-1
    signed = to_signed(word),          -- int32, what the circuit network carries
    hex = "0x" .. hex_str(word, 8),
    bin = bin,
    bin_grouped = table.concat(groups, " "),
    fields = fields, immediate = imm, immediate_note = imm_note, notes = notes,
  }
end

--- Assemble one instruction.
-- Returns the result table, or nil and an error message for invalid input.
-- Internal bugs are re-raised as normal Lua errors.
function M.encode(text)
  local ok, res = pcall(function()
    local source = trim((text:gsub("#.*$", "")))
    if source == "" then asm_error("empty input") end
    local first, rest = source:match("^(%S+)%s*(.*)$")
    local mn = first:lower()
    local ops = split_operands(rest)

    local pseudo = nil
    local real, real_ops = expand_pseudo(mn, ops)
    if real then
      pseudo = mn
      mn, ops = real, real_ops
    end
    local o = OPS[mn]
    if not o then asm_error("unknown instruction '" .. first .. "'") end
    local enc = encode_op(o, ops)
    enc.source = source
    enc.pseudo = pseudo
    if pseudo then
      table.insert(enc.notes, 1, "'" .. pseudo .. "' is a pseudoinstruction for: " .. enc.canonical)
    end
    return enc
  end)
  if ok then return res end
  if type(res) == "table" and res.asm_error then return nil, res.asm_error end
  error(res, 0)
end

M.SUPPORTED_HELP = table.concat({
  "RV32I:  lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw lbu lhu sb sh sw",
  "        addi slti sltiu xori ori andi slli srli srai",
  "        add sub sll slt sltu xor srl sra or and",
  "        fence fence.tso pause ecall ebreak",
  "RV32M:  mul mulh mulhsu mulhu div divu rem remu",
  "Zba:    sh1add sh2add sh3add",
  "Zbb:    andn orn xnor clz ctz cpop max maxu min minu sext.b sext.h zext.h",
  "        rol ror rori orc.b rev8",
  "Zbs:    bclr bclri bext bexti binv binvi bset bseti",
  "Pseudo: nop mv not seqz snez j jr ret bgt bgtu ble bleu",
  "",
  "Registers: x0..x31 or ABI names (zero ra sp gp tp t0-t6 s0-s11 fp a0-a7)",
  "Loads/stores/jalr: lw x1, -4(x2)",
  "Branches/jal: byte offset relative to the instruction, e.g. beq x1, x2, -8",
  "Immediates: decimal, 0x hex, 0b binary, 0o octal",
}, "\n")

return M
