"""x86-64 ELF machine policy checks."""

from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from x86.common.paths_x86 import activate_tools

activate_tools()
from elf64 import Elf64


def fixture(machine):
    names = b"\0.shstrtab\0"
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01" + b"\0" * 9,
        1,
        machine,
        1,
        0,
        0,
        64,
        0,
        64,
        0,
        0,
        64,
        2,
        1,
    )
    return (
        header
        + b"\0" * 64
        + struct.pack("<IIQQQQIIQQ", 1, 3, 0, 0, 192, len(names), 0, 0, 1, 0)
        + names
    )


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Unreviewed/wrong ELF machine accepted")


x86, foreign = fixture(62), fixture(183)
assert Elf64(x86).machine == 62
rejects(lambda: Elf64(foreign))
for machine in (0, 3, 40, 62.0, True, None):
    rejects(lambda: Elf64(x86, expected_machine=machine))
rejects(lambda: Elf64(x86[:63]))
wrong_endian = bytearray(x86)
wrong_endian[5] = 2
rejects(lambda: Elf64(wrong_endian))
print("ELF_MACHINE_X86_POLICY_OK default=62 rejects=wrong,unknown,endian,truncated")
