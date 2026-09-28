"""Runs data.lua and control.lua against a strict mock of the Factorio runtime.

This cannot replace testing in the game, but catches Lua errors, misspelled API
parameters/styles, and checks the exact signal the combinator outputs for
thousands of instructions (expected values from the llvm-verified Python encoder).
"""

import os
import random
import subprocess
import sys
import tempfile
import unittest

from test_lua_parity import HERE, LUA, MOD_DIR, rv, _random_instances, PSEUDOS, EDGE_CASES


@unittest.skipUnless(LUA, "no Lua interpreter found (install lua5.2)")
class ModRuntime(unittest.TestCase):
    def test_scenario(self):
        r = random.Random(5)
        lines = list(EDGE_CASES)
        for mn in list(rv.OPS) + PSEUDOS:
            lines += _random_instances(mn, r, 20)
        rows = []
        for line in lines:
            if "\t" in line or "\n" in line:
                continue
            try:
                rows.append(f"{line}\t{rv.encode(line).signed}")
            except rv.AsmError:
                rows.append(f"{line}\tERR")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("\n".join(rows) + "\n")
            cases = f.name
        # register display formatting: expected strings computed independently here
        values = [0, 1, -1, 23, -2147483648, 2147483647] + [r.randint(-2**31, 2**31 - 1) for _ in range(3000)]
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            for v in values:
                word = v & 0xFFFFFFFF
                bits = format(word, "032b")
                f.write(f"{v}\t{v}\t0x{word:08X}\t{' '.join(bits[i:i + 4] for i in range(0, 32, 4))}\n")
            values_file = f.name
        try:
            res = subprocess.run([LUA, os.path.join(HERE, "control_scenario.lua"), MOD_DIR, HERE, cases,
                                  values_file], capture_output=True, text=True)
        finally:
            os.unlink(cases)
            os.unlink(values_file)
        if res.returncode != 0 or not res.stdout.startswith("PASS"):
            self.fail(f"scenario failed:\n{res.stdout}\n{res.stderr}")
        print("\n  " + res.stdout.strip(), file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
