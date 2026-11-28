"""x86-64 Mach-O parser and machine policy checks."""

from pathlib import Path
import importlib.util
import struct
import sys
import tempfile

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(TOOLS_DIR))
from x86.macos.adapt_macho import adapt_asm_files
from x86.macos.macho64 import CPU_TYPE_X86_64, MH_MAGIC_64, MH_OBJECT, MachO64

_rn_spec = importlib.util.spec_from_file_location(
    "record_native", TOOLS_DIR / "x86/macos/record-native.py"
)
_rn_mod = importlib.util.module_from_spec(_rn_spec)
_rn_spec.loader.exec_module(_rn_mod)
CVM_EPILOGUE_BYTES = _rn_mod.CVM_EPILOGUE_BYTES
CVM_PROLOGUE_BYTES = _rn_mod.CVM_PROLOGUE_BYTES
parse_eh_frame_fdes = _rn_mod.parse_eh_frame_fdes
sha = _rn_mod.sha
verify_adapt_receipt = _rn_mod.verify_adapt_receipt
verify_cvm_unwind = _rn_mod.verify_cvm_unwind

_ep_spec = importlib.util.spec_from_file_location(
    "export_pregen", TOOLS_DIR / "common/export-pregen.py"
)
_ep_mod = importlib.util.module_from_spec(_ep_spec)
_ep_spec.loader.exec_module(_ep_mod)
export_pregen_bundle = _ep_mod.export_bundle


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

# Verify CVM DWARF FDE coverage, compact-unwind offset matching, and body-row integrity.
CVM_BASE = 0x10012B1D0
CVM_SIZE = 11554
CVM_END = CVM_BASE + CVM_SIZE
CVM_FDE_OFF = 0x3648
CVM_BODY_RULE = (
    "CFA=RSP+72: RBX=[CFA-16], RSI=[CFA-32], RDI=[CFA-40], RBP=[CFA-24], "
    "R12=[CFA-48], R13=[CFA-56], R14=[CFA-64], R15=[CFA-72], RIP=[CFA-8]"
)


def make_fde_text(
    *,
    fde_off=CVM_FDE_OFF,
    lo=CVM_BASE,
    hi=CVM_END,
    prefix_size=0,
    body_pc=None,
    body_rule=CVM_BODY_RULE,
    epilogue_pc=None,
    extra_rows="",
):
    first_push = lo + prefix_size
    if body_pc is None:
        body_pc = first_push + len(CVM_PROLOGUE_BYTES)
    if epilogue_pc is None:
        epilogue_pc = hi - 11
    return (
        f"{fde_off:08x} 00000064 00000984 FDE cie=00002cc8 pc={lo:x}...{hi:x}\n"
        "  Format:       DWARF32\n"
        f"  0x{lo:x}: CFA=RSP+8: RIP=[CFA-8]\n"
        f"  0x{first_push + 1:x}: CFA=RSP+16: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{first_push + 2:x}: CFA=RSP+24: RBX=[CFA-16], RBP=[CFA-24], RIP=[CFA-8]\n"
        f"  0x{first_push + 3:x}: CFA=RSP+32: RBX=[CFA-16], RSI=[CFA-32], RBP=[CFA-24], RIP=[CFA-8]\n"
        f"  0x{first_push + 4:x}: CFA=RSP+40: RBX=[CFA-16], RSI=[CFA-32], RDI=[CFA-40], RBP=[CFA-24], RIP=[CFA-8]\n"
        f"  0x{first_push + 6:x}: CFA=RSP+48: RBX=[CFA-16], RSI=[CFA-32], RDI=[CFA-40], RBP=[CFA-24], R12=[CFA-48], RIP=[CFA-8]\n"
        f"  0x{first_push + 8:x}: CFA=RSP+56: RBX=[CFA-16], RSI=[CFA-32], RDI=[CFA-40], RBP=[CFA-24], R12=[CFA-48], R13=[CFA-56], RIP=[CFA-8]\n"
        f"  0x{first_push + 10:x}: CFA=RSP+64: RBX=[CFA-16], RSI=[CFA-32], RDI=[CFA-40], RBP=[CFA-24], R12=[CFA-48], R13=[CFA-56], R14=[CFA-64], RIP=[CFA-8]\n"
        f"  0x{body_pc:x}: {body_rule}\n"
        f"{extra_rows}"
        f"  0x{epilogue_pc:x}: CFA=RSP+64: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 9:x}: CFA=RSP+56: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 7:x}: CFA=RSP+48: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 5:x}: CFA=RSP+40: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 4:x}: CFA=RSP+32: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 3:x}: CFA=RSP+24: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 2:x}: CFA=RSP+16: RBX=[CFA-16], RIP=[CFA-8]\n"
        f"  0x{hi - 1:x}: CFA=RSP+8: RIP=[CFA-8]\n"
    )


cvm_sec = dict(addr=CVM_BASE, size=CVM_SIZE)
cvm_bytes = (
    CVM_PROLOGUE_BYTES
    + b"\x90" * (CVM_SIZE - len(CVM_PROLOGUE_BYTES) - len(CVM_EPILOGUE_BYTES))
    + CVM_EPILOGUE_BYTES
)
valid_fdes = parse_eh_frame_fdes(make_fde_text())
assert verify_cvm_unwind(
    CVM_BASE,
    cvm_sec,
    cvm_bytes,
    ["_JS_CVMRunFastSegment"],
    (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
    valid_fdes,
) == (CVM_FDE_OFF, CVM_BASE, CVM_END)

# ENDBR64 delays the pushes by four bytes while the entry row stays at the function start.
endbr64 = bytes.fromhex("f3 0f 1e fa")
cet_bytes = endbr64 + cvm_bytes
cet_end = CVM_BASE + len(cet_bytes)
cet_args = (
    CVM_BASE,
    dict(addr=CVM_BASE, size=len(cet_bytes)),
    cet_bytes,
    ["_JS_CVMRunFastSegment"],
    (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
)
assert verify_cvm_unwind(
    *cet_args, parse_eh_frame_fdes(make_fde_text(hi=cet_end, prefix_size=len(endbr64)))
) == (CVM_FDE_OFF, CVM_BASE, cet_end)
rejects(lambda: verify_cvm_unwind(*cet_args, parse_eh_frame_fdes(make_fde_text(hi=cet_end))))

# Edge-shift regressions: delaying body rule from +12 to +18 or pulling restore
# transition forward from -11 to -20 must be rejected against exact push/pop bounds.
delayed_body_fdes = parse_eh_frame_fdes(make_fde_text(body_pc=CVM_BASE + 18))
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        delayed_body_fdes,
    )
)
early_restore_fdes = parse_eh_frame_fdes(make_fde_text(epilogue_pc=CVM_END - 20))
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        early_restore_fdes,
    )
)
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        b"\x90" * CVM_SIZE,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        valid_fdes,
    )
)

# Trailing NOP alignment (<16B) inside __TEXT,__qjs_cvm is accepted; non-NOP code is rejected.
padded_sec = dict(addr=CVM_BASE, size=CVM_SIZE + 4)
assert verify_cvm_unwind(
    CVM_BASE,
    padded_sec,
    cvm_bytes + b"\x90\x90\x90\x90",
    ["_JS_CVMRunFastSegment"],
    (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
    valid_fdes,
) == (CVM_FDE_OFF, CVM_BASE, CVM_END)
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        padded_sec,
        cvm_bytes + b"\xc3\x90\x90\x90",
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        valid_fdes,
    )
)

# Truncated FDE (e.g. 128 bytes of an 11,554-byte section) must be rejected.
trunc_fdes = parse_eh_frame_fdes(make_fde_text(hi=CVM_BASE + 128, epilogue_pc=CVM_BASE + 117))
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        trunc_fdes,
    )
)

# Compact-unwind 24-bit FDE offset mismatch and non-DWARF encoding (0x02011860) must be rejected.
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04009999),
        valid_fdes,
    )
)
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x02011860),
        valid_fdes,
    )
)

# Rules scattered across different rows or dropped mid-function must be rejected.
split_fdes = parse_eh_frame_fdes(
    make_fde_text(
        body_rule="CFA=RSP+72: RBX=[CFA-16], RBP=[CFA-24], RIP=[CFA-8]",
        extra_rows=(
            f"  0x{CVM_BASE + 20:x}: CFA=RSP+64: RSI=[CFA-32], RDI=[CFA-40], "
            "R12=[CFA-48], R13=[CFA-56], R14=[CFA-64], R15=[CFA-72], RIP=[CFA-8]\n"
        ),
    )
)
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        split_fdes,
    )
)
mid_drop_fdes = parse_eh_frame_fdes(
    make_fde_text(
        extra_rows=f"  0x{CVM_BASE + 256:x}: CFA=RSP+8: RIP=[CFA-8]\n",
    )
)
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        mid_drop_fdes,
    )
)

# Non-exclusive __TEXT,__qjs_cvm section must be rejected.
rejects(
    lambda: verify_cvm_unwind(
        CVM_BASE,
        cvm_sec,
        cvm_bytes,
        ["_JS_CVMRunFastSegment", "_unexpected_sym"],
        (CVM_BASE, 0x04000000 | CVM_FDE_OFF),
        valid_fdes,
    )
)

# Verify MACOS-ADAPT.json adapted_include_files receipt completeness and tamper detection.
with tempfile.TemporaryDirectory() as tmp:
    gen = Path(tmp)
    (gen / "a.c").write_text("int a(void) { return 1; }\n", encoding="utf-8")
    (gen / "a.S").write_text(".text\n", encoding="utf-8")
    inc = gen / "macos-inc/src/foo.inc"
    inc.parent.mkdir(parents=True, exist_ok=True)
    inc.write_text("/* adapted */\n", encoding="utf-8")
    good_adapt = {
        "c_files": {"a.c": sha(gen / "a.c")},
        "asm_files": {"a.S": sha(gen / "a.S")},
        "adapted_includes": ["src/foo.inc"],
        "adapted_include_files": {"macos-inc/src/foo.inc": sha(inc)},
    }
    verify_adapt_receipt(good_adapt, gen)

    missing_field = {k: v for k, v in good_adapt.items() if k != "adapted_include_files"}
    rejects(lambda: verify_adapt_receipt(missing_field, gen))

    missing_inc = {**good_adapt, "adapted_include_files": {}}
    rejects(lambda: verify_adapt_receipt(missing_inc, gen))

    extra_inc = {
        **good_adapt,
        "adapted_include_files": {
            "macos-inc/src/foo.inc": sha(inc),
            "macos-inc/src/bar.inc": sha(inc),
        },
    }
    rejects(lambda: verify_adapt_receipt(extra_inc, gen))

    inc.write_text("/* tampered */\n", encoding="utf-8")
    rejects(lambda: verify_adapt_receipt(good_adapt, gen))

# Verify export-pregen.py ignores stale incremental files outside MACOS-ADAPT.json.
with tempfile.TemporaryDirectory() as tmp:
    import json

    root = Path(tmp)
    src_vm = Path(__file__).resolve().parents[3]
    bld = root / "build"
    out = root / "pregen"
    (bld / "interpreter-backend.json").parent.mkdir(parents=True, exist_ok=True)
    (bld / "interpreter-backend.json").write_text(
        json.dumps({"effective": "MACOS_X86_64"}), encoding="utf-8"
    )
    nat = bld / "generated/macos-native"
    nat.mkdir(parents=True, exist_ok=True)
    (nat / "a.c").write_text("int a(void) { return 1; }\n", encoding="utf-8")
    (nat / "a.S").write_text(".text\n", encoding="utf-8")
    (nat / "stale.c").write_text("/* leftover */\n", encoding="utf-8")
    kept_inc = nat / "macos-inc/src/kept.inc"
    kept_inc.parent.mkdir(parents=True, exist_ok=True)
    kept_inc.write_text("/* kept */\n", encoding="utf-8")
    stale_inc = nat / "macos-inc/src/stale-tls.inc"
    stale_inc.write_text("/* stale */\n", encoding="utf-8")
    adapt_json = {
        "schema": 1,
        "target": "macos-x86_64-macho",
        "c_files": {"a.c": sha(nat / "a.c")},
        "asm_files": {"a.S": sha(nat / "a.S")},
        "adapted_includes": ["src/kept.inc"],
        "adapted_include_files": {"macos-inc/src/kept.inc": sha(kept_inc)},
    }
    (nat / "MACOS-ADAPT.json").write_text(json.dumps(adapt_json), encoding="utf-8")
    bundle = export_pregen_bundle(src_vm, bld, out)
    manifest = json.loads((bundle / "PREGEN-MANIFEST.json").read_text(encoding="utf-8"))
    exported = set(manifest["files"].keys())
    assert "generated/macos-native/macos-inc/src/kept.inc" in exported
    assert "generated/macos-native/macos-inc/src/stale-tls.inc" not in exported
    assert "generated/macos-native/stale.c" not in exported
    assert manifest["file_count"] == 4

print(
    "MACHO_X86_POLICY_OK cputype=0x01000007 "
    "rejects=wrong,32bit,truncated,invalid,cvm_fde_gaps,cvm_edge_shifts,adapt_receipt_gaps,stale_pregen"
)
