"""x86-64 Mach-O parser and machine policy checks."""

from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from x86.macos.macho64 import CPU_TYPE_X86_64, MH_MAGIC_64, MH_OBJECT, MachO64


def fixture(cputype=CPU_TYPE_X86_64, magic=MH_MAGIC_64):
    return struct.pack("<IIIIIIII", magic, cputype, 3, MH_OBJECT, 0, 0, 0, 0)


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Unreviewed/wrong Mach-O machine accepted")


x86 = fixture(CPU_TYPE_X86_64)
foreign = fixture(0x0100000C)
assert MachO64(x86).cputype == CPU_TYPE_X86_64
rejects(lambda: MachO64(foreign))
rejects(lambda: MachO64(fixture(magic=0xFEEDFACE)))
rejects(lambda: MachO64(x86[:31]))
for bad in (0, -1, 1.5, True, None):
    rejects(lambda: MachO64(x86, expected_cputype=bad))
print("MACHO_X86_POLICY_OK cputype=0x01000007 rejects=wrong,32bit,truncated,invalid")
