"""32-bit number conversions (binary <-> hex <-> signed decimal).

All values are treated as 32-bit two's complement words: internally a word is
an unsigned int in [0, 2**32), and "signed" means bit 31 is the sign bit.
"""

from __future__ import annotations

WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


class ConversionError(ValueError):
    pass


def to_signed(word: int) -> int:
    """Interpret a 32-bit word as a signed (two's complement) integer."""
    word &= WORD_MASK
    return word - (1 << WORD_BITS) if word & (1 << 31) else word


def to_word(value: int) -> int:
    """Wrap any Python int into a 32-bit word."""
    return value & WORD_MASK


def fmt_bin(word: int, group: int = 4) -> str:
    s = format(word & WORD_MASK, "032b")
    if not group:
        return s
    return " ".join(s[i:i + group] for i in range(0, WORD_BITS, group))


def fmt_hex(word: int) -> str:
    return "0x" + format(word & WORD_MASK, "08X")


def _clean(text: str) -> str:
    return text.strip().replace("_", "").replace(" ", "")


def parse_bin(text: str) -> int:
    """Parse up to 32 binary digits (optional 0b prefix, spaces/underscores ok).

    Fewer than 32 digits are zero-extended (leading zeros are implied).
    """
    s = _clean(text)
    if s[:2].lower() == "0b":
        s = s[2:]
    if not s:
        raise ConversionError("empty")
    if any(c not in "01" for c in s):
        raise ConversionError("binary may only contain 0 and 1")
    if len(s) > WORD_BITS:
        raise ConversionError(f"more than {WORD_BITS} bits ({len(s)})")
    return int(s, 2)


def parse_hex(text: str) -> int:
    """Parse up to 8 hex digits (optional 0x prefix, spaces/underscores ok).

    Fewer than 8 digits are zero-extended (leading zeros are implied).
    """
    s = _clean(text)
    if s[:2].lower() == "0x":
        s = s[2:]
    if not s:
        raise ConversionError("empty")
    if any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ConversionError("hex may only contain 0-9 and A-F")
    if len(s) > WORD_BITS // 4:
        raise ConversionError(f"more than {WORD_BITS // 4} hex digits ({len(s)})")
    return int(s, 16)


def parse_signed_dec(text: str) -> int:
    """Parse a signed decimal in [-2^31, 2^31 - 1] and return its 32-bit word."""
    s = _clean(text)
    if not s or s in "+-":
        raise ConversionError("empty")
    sign = 1
    if s[0] in "+-":
        sign = -1 if s[0] == "-" else 1
        s = s[1:]
    if not s.isdigit():
        raise ConversionError("decimal may only contain an optional sign and digits 0-9")
    value = sign * int(s, 10)
    if not INT32_MIN <= value <= INT32_MAX:
        raise ConversionError(f"out of signed 32-bit range [{INT32_MIN}, {INT32_MAX}]")
    return to_word(value)
