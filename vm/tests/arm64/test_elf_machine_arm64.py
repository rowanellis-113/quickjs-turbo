"""ARM64 ELF machine policy checks (zero foreign tokens)."""

from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import activate_tools

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


foreign, arm = fixture(62), fixture(183)
assert Elf64(arm, expected_machine=183).machine == 183
rejects(lambda: Elf64(arm))
rejects(lambda: Elf64(foreign, expected_machine=183))
for machine in (0, 3, 40, 62.0, True, None):
    rejects(lambda: Elf64(arm, expected_machine=machine))
rejects(lambda: Elf64(arm[:63], expected_machine=183))
wrong_endian = bytearray(arm)
wrong_endian[5] = 2
rejects(lambda: Elf64(wrong_endian, expected_machine=183))
print("ELF_MACHINE_ARM64_POLICY_OK explicit=183 rejects=wrong,unknown,endian,truncated")
