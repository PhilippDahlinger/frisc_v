"""Package the mod as dist/<name>_<version>.zip, ready for Factorio's mods folder."""

import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "one-line-assembler")


def main() -> str:
    with open(os.path.join(MOD, "info.json")) as f:
        info = json.load(f)
    root = f"{info['name']}_{info['version']}"
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", root + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, files in os.walk(MOD):
            dirnames.sort()
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, MOD).replace(os.sep, "/")
                z.write(full, f"{root}/{rel}")
    return out


if __name__ == "__main__":
    print(main())
