"""Bounds/type rejection for ELF tools, using an actual GCC probe object."""

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from x86.common.paths_x86 import activate_tools

activate_tools()
from elf64 import Elf64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--object", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    raw = a.object.read_bytes()
    elf = Elf64(raw)
    if elf.kind != 1 or not elf.symbols():
        raise ValueError("Expected a real relocatable GCC object with symbols")
    cases = {"truncated": raw[:32]}
    for name, offset, value in [
        ("wrong-class", 4, 1),
        ("wrong-endian", 5, 2),
        ("wrong-machine", 18, 183),
    ]:
        data = bytearray(raw)
        data[offset] = value
        cases[name] = bytes(data)
    data = bytearray(raw)
    struct.pack_into("<Q", data, 40, len(raw) + 4096)
    cases["out-of-file-section-table"] = bytes(data)
    data = bytearray(raw)
    struct.pack_into("<H", data, 60, 0)
    cases["unsupported-extended-section-count"] = bytes(data)
    shoff = struct.unpack_from("<Q", raw, 40)[0]
    data = bytearray(raw)
    struct.pack_into("<I", data, shoff + 64, 0xFFFFFFFF)
    cases["out-of-file-section-name"] = bytes(data)
    refused = []
    for name, data in cases.items():
        try:
            Elf64(data)
        except (ValueError, UnicodeDecodeError):
            refused.append(name)
        else:
            raise ValueError("Invalid ELF input admitted: " + name)
    a.output.write_text(
        json.dumps(
            dict(
                status="passed-actual-GCC-ELF-and-invalid-input-rejection",
                valid_object=str(a.object),
                refused=refused,
            ),
            indent=2,
        )
        + "\n"
    )
    print("ELF OBJECT AND", len(refused), "REJECTION CHECKS PASSED")


if __name__ == "__main__":
    main()
