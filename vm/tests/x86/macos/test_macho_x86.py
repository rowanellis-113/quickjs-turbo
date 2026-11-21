"""x86-64 Mach-O parser and machine policy checks."""

from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from x86.macos.adapt_macho import adapt_asm_files
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

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    (out / "quickjs-linux-vm.S").write_text(
        ".intel_syntax noprefix\n"
        '.section .text.qjs_linux_vm,"ax",@progbits\n'
        ".globl vm_entry\n"
        ".hidden vm_entry\n"
        "vm_entry:\n"
        ".cfi_startproc\n"
        "sub rsp, 72\n"
        ".cfi_adjust_cfa_offset 72\n"
        "jmp done_label\n"
        "done_label:\n"
        "add rsp, 72\n"
        ".cfi_adjust_cfa_offset -72\n"
        "ret\n"
        ".cfi_endproc\n"
        '.section .data.rel.ro.local.qjs_linux_dispatch,"aw",@progbits\n'
        "dispatch_tbl:\n"
        ".quad done_label\n",
        encoding="utf-8",
    )
    (out / "quickjs-linux-bridges.S").write_text(".intel_syntax noprefix\n", encoding="utf-8")
    (out / "quickjs-linux-entry.S").write_text(".intel_syntax noprefix\n", encoding="utf-8")
    adapt_asm_files(out)
    rendered = (out / "quickjs-linux-vm.S").read_text(encoding="utf-8")
    assert "_vm_entry:\n" in rendered, rendered
    assert "L_done_label:\n" in rendered, rendered
    assert "jmp L_done_label\n" in rendered, rendered
    assert ".quad L_done_label\n" in rendered, rendered
    assert "dispatch_tbl:\n" in rendered, rendered

print("MACHO_X86_POLICY_OK cputype=0x01000007 rejects=wrong,32bit,truncated,invalid")
