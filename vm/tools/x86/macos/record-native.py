"""Bind a normally linked CMake macOS x86-64 Mach-O image to its generated inputs."""

import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, upstream_root

_act_x86()

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from x86.macos.macho64 import (
    MH_ALLOW_STACK_EXECUTION,
    MH_EXECUTE,
    MH_PIE,
    VM_PROT_EXECUTE,
    VM_PROT_READ,
    VM_PROT_WRITE,
    MachO64,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


REQUIRED_CVM_BODY_RULES = (
    "CFA=RSP+72:",
    "RBX=[CFA-16]",
    "RBP=[CFA-24]",
    "RSI=[CFA-32]",
    "RDI=[CFA-40]",
    "R12=[CFA-48]",
    "R13=[CFA-56]",
    "R14=[CFA-64]",
    "R15=[CFA-72]",
    "RIP=[CFA-8]",
)

# Exact x86-64 SysV machine code emitted by cvm_fast_native.py:
#   Prologue (12B): push rbx, rbp, rsi, rdi, r12, r13, r14, r15
#   Epilogue (13B): pop r15, r14, r13, r12, rdi, rsi, rbp, rbx; ret
CVM_ENDBR64 = bytes.fromhex("f3 0f 1e fa")
CVM_PROLOGUE_BYTES = bytes.fromhex("535556574154415541564157")
CVM_EPILOGUE_BYTES = bytes.fromhex("415f415e415d415c5f5e5d5bc3")
CVM_PROLOGUE_STEPS = (
    (0, "CFA=RSP+8:"),
    (1, "CFA=RSP+16:"),
    (2, "CFA=RSP+24:"),
    (3, "CFA=RSP+32:"),
    (4, "CFA=RSP+40:"),
    (6, "CFA=RSP+48:"),
    (8, "CFA=RSP+56:"),
    (10, "CFA=RSP+64:"),
)
CVM_EPILOGUE_STEPS = (
    (-11, "CFA=RSP+64:"),
    (-9, "CFA=RSP+56:"),
    (-7, "CFA=RSP+48:"),
    (-5, "CFA=RSP+40:"),
    (-4, "CFA=RSP+32:"),
    (-3, "CFA=RSP+24:"),
    (-2, "CFA=RSP+16:"),
    (-1, "CFA=RSP+8:"),
)

FDE_BLOCK_RE = re.compile(
    r"^([0-9a-fA-F]+) [0-9a-fA-F]+ [0-9a-fA-F]+ FDE .*?pc=([0-9a-fA-F]+)\.\.\.([0-9a-fA-F]+)"
    r"[\s\S]*?(?=\n[0-9a-fA-F]+ [0-9a-fA-F]+ [0-9a-fA-F]+ (?:CIE|FDE)|\Z)",
    re.M,
)
FDE_ROW_RE = re.compile(r"^\s*0x([0-9a-fA-F]+):\s*(.+)$", re.M)


def verify_adapt_receipt(adapt, generated_dir):
    """Verify MACOS-ADAPT.json completeness and SHA-256 hashes of all adapted inputs."""
    generated_dir = Path(generated_dir)
    for field, expected_type in (
        ("c_files", dict),
        ("asm_files", dict),
        ("adapted_includes", list),
        ("adapted_include_files", dict),
    ):
        if field not in adapt or not isinstance(adapt[field], expected_type):
            raise ValueError(f"Missing or invalid {field} in MACOS-ADAPT.json")

    expected_inc_keys = {"macos-inc/" + rel for rel in adapt["adapted_includes"]}
    actual_inc_keys = set(adapt["adapted_include_files"].keys())
    if actual_inc_keys != expected_inc_keys:
        missing = sorted(expected_inc_keys - actual_inc_keys)
        extra = sorted(actual_inc_keys - expected_inc_keys)
        raise ValueError(
            f"adapted_include_files mismatch in MACOS-ADAPT.json: missing={missing[:5]}, extra={extra[:5]}"
        )

    all_inputs = {
        **adapt["c_files"],
        **adapt["asm_files"],
        **adapt["adapted_include_files"],
    }
    for name, expected_hash in all_inputs.items():
        target = generated_dir / name
        if not target.is_file() or sha(target) != expected_hash:
            raise ValueError("Generated macOS native input changed or missing: " + name)


def parse_eh_frame_fdes(eh_text):
    """Parse dwarfdump --eh-frame FDE blocks into (fde_offset, lo, hi, block_text)."""
    return [
        (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16), m.group(0))
        for m in FDE_BLOCK_RE.finditer(eh_text)
    ]


def verify_cvm_unwind(
    cvm_addr,
    cvm_section,
    cvm_section_bytes,
    cvm_section_symbols,
    compact_entry,
    fde_blocks,
):
    """Verify JS_CVMRunFastSegment DWARF FDE covers the exclusive __TEXT,__qjs_cvm section."""
    sec_addr = cvm_section["addr"]
    sec_size = cvm_section["size"]
    sec_end = sec_addr + sec_size
    if sec_size < 128 or len(cvm_section_bytes) != sec_size:
        raise ValueError(f"Invalid __TEXT,__qjs_cvm section size: {sec_size}")
    if cvm_addr != sec_addr:
        raise ValueError(
            f"Expected JS_CVMRunFastSegment at __TEXT,__qjs_cvm start {hex(sec_addr)}, got {hex(cvm_addr)}"
        )
    if sorted(cvm_section_symbols) != ["_JS_CVMRunFastSegment"]:
        raise ValueError(
            f"Expected __TEXT,__qjs_cvm to exclusively contain _JS_CVMRunFastSegment, got {cvm_section_symbols}"
        )
    if (
        compact_entry is None
        or compact_entry[0] != cvm_addr
        or (compact_entry[1] & 0x0F000000) != 0x04000000
    ):
        raise ValueError(
            f"Expected DWARF compact unwind mode for JS_CVMRunFastSegment: {compact_entry}"
        )

    expected_fde_offset = compact_entry[1] & 0x00FFFFFF
    cvm_fde = next(
        ((off, lo, hi, txt) for off, lo, hi, txt in fde_blocks if lo == cvm_addr),
        None,
    )
    if cvm_fde is None:
        raise ValueError("Missing DWARF FDE starting at JS_CVMRunFastSegment")
    fde_offset, fde_lo, fde_hi, fde_txt = cvm_fde
    if fde_offset != expected_fde_offset:
        raise ValueError(
            f"Compact unwind FDE offset mismatch for JS_CVMRunFastSegment: "
            f"compact={hex(expected_fde_offset)}, fde={hex(fde_offset)}"
        )
    if fde_hi <= fde_lo or fde_hi > sec_end:
        raise ValueError(
            f"Invalid FDE bounds [{hex(fde_lo)}..{hex(fde_hi)}) for __TEXT,__qjs_cvm end {hex(sec_end)}"
        )
    trailing = sec_end - fde_hi
    if trailing >= 16:
        raise ValueError(
            f"Truncated FDE for JS_CVMRunFastSegment: covers {fde_hi - fde_lo} of {sec_size} bytes"
        )
    if trailing > 0:
        pad = cvm_section_bytes[fde_hi - sec_addr :]
        if any(b not in (0x90, 0x00) for b in pad):
            raise ValueError(f"Non-padding bytes after JS_CVMRunFastSegment FDE end: {pad.hex()}")

    fde_bytes = cvm_section_bytes[: fde_hi - sec_addr]
    # IBT adds an ENDBR64 before the first push. It leaves the entry CFA unchanged.
    prefix_size = len(CVM_ENDBR64) if fde_bytes.startswith(CVM_ENDBR64) else 0
    if not fde_bytes.startswith(CVM_PROLOGUE_BYTES, prefix_size):
        raise ValueError(
            f"Unexpected JS_CVMRunFastSegment push sequence: "
            f"{fde_bytes[prefix_size : prefix_size + len(CVM_PROLOGUE_BYTES)].hex()} "
            f"(expected {CVM_PROLOGUE_BYTES.hex()})"
        )
    if not fde_bytes.endswith(CVM_EPILOGUE_BYTES):
        raise ValueError(
            f"Unexpected JS_CVMRunFastSegment epilogue bytes: {fde_bytes[-13:].hex()} "
            f"(expected {CVM_EPILOGUE_BYTES.hex()})"
        )

    first_push = fde_lo + prefix_size
    expected_body_start = first_push + len(CVM_PROLOGUE_BYTES)

    rows = [(int(m.group(1), 16), m.group(2).strip()) for m in FDE_ROW_RE.finditer(fde_txt)]
    expected_row_count = len(CVM_PROLOGUE_STEPS) + 1 + len(CVM_EPILOGUE_STEPS)
    if len(rows) != expected_row_count:
        raise ValueError(
            f"Expected {expected_row_count} decoded DWARF unwind rows for JS_CVMRunFastSegment, "
            f"got {len(rows)}"
        )

    for idx, (rel_off, expected_cfa) in enumerate(CVM_PROLOGUE_STEPS):
        row_pc, row_rule = rows[idx]
        expected_pc = first_push + rel_off if rel_off else fde_lo
        if row_pc != expected_pc or expected_cfa not in row_rule:
            raise ValueError(
                f"Prologue unwind mismatch at row {idx}: got ({hex(row_pc)}, {row_rule!r}), "
                f"expected ({hex(expected_pc)}, {expected_cfa!r})"
            )

    body_idx = len(CVM_PROLOGUE_STEPS)
    body_pc, body_rule = rows[body_idx]
    if body_pc != expected_body_start or not all(
        tok in body_rule for tok in REQUIRED_CVM_BODY_RULES
    ):
        raise ValueError(
            f"JS_CVMRunFastSegment body unwind row must start at {hex(expected_body_start)} "
            f"with full CFA=RSP+72 rules; got ({hex(body_pc)}, {body_rule!r})"
        )

    for offset_idx, (rel_end, expected_cfa) in enumerate(CVM_EPILOGUE_STEPS):
        row_pc, row_rule = rows[body_idx + 1 + offset_idx]
        expected_pc = fde_hi + rel_end
        if row_pc != expected_pc or expected_cfa not in row_rule:
            raise ValueError(
                f"Epilogue unwind mismatch at step {offset_idx}: got ({hex(row_pc)}, {row_rule!r}), "
                f"expected ({hex(expected_pc)}, {expected_cfa!r})"
            )
    return fde_offset, fde_lo, fde_hi


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    a = ap.parse_args()
    source, build, binary, archive = [p.resolve() for p in (a.source, a.build, a.binary, a.archive)]
    generated = build / "generated/macos-native"
    adapt = json.loads((generated / "MACOS-ADAPT.json").read_text(encoding="utf-8"))
    vm = json.loads((generated / "VM.json").read_text(encoding="utf-8"))

    verify_adapt_receipt(adapt, generated)

    macho = MachO64.read(binary)
    if macho.filetype != MH_EXECUTE:
        raise ValueError("Expected Mach-O MH_EXECUTE binary")
    if not (macho.flags & MH_PIE):
        raise ValueError("Expected PIE Mach-O binary (MH_PIE)")
    if macho.flags & MH_ALLOW_STACK_EXECUTION:
        raise ValueError("Mach-O binary must have non-executable stack")
    for seg in macho.segments:
        if (seg["initprot"] & VM_PROT_WRITE) and (seg["initprot"] & VM_PROT_EXECUTE):
            raise ValueError("W^X violation in Mach-O segment: " + seg["segname"])
    text_seg = next(s for s in macho.segments if s["segname"] == "__TEXT")
    if (text_seg["initprot"] & (VM_PROT_READ | VM_PROT_EXECUTE)) != (
        VM_PROT_READ | VM_PROT_EXECUTE
    ) or (text_seg["initprot"] & VM_PROT_WRITE):
        raise ValueError(f"Expected __TEXT RX permissions, got {hex(text_seg['initprot'])}")

    varg_section = macho.section("__TEXT", "__qjs_varg")
    if varg_section["size"] == 0:
        raise ValueError("Empty virtual arguments code section")
    cvm_section = macho.section("__TEXT", "__qjs_cvm")
    if cvm_section["size"] == 0:
        raise ValueError("Empty CVM fast-segment code section")
    const_section = macho.section("__TEXT", "__const")

    defined_symbols = {s["name"]: s for s in macho.symbols() if s["defined"]}
    required = [
        vm["private_entry"],
        *vm["helper_mapping"].values(),
        *vm.get("extra_native_functions", []),
        *vm.get("extra_vm_functions", []),
        *vm.get("returning_forward_functions", []),
        "JS_Call",
        "JS_FrameCallEntryDispatch",
        "JS_LinuxVirtualArgumentsStep",
        "JS_LinuxVirtualArgumentsPush",
        "JS_CompilerFunctionPlan",
        "JS_FrameAtod",
        "JS_LinuxIntExpressionInit",
        "JS_CVMRunFastSegment",
        "JS_CVMFastEligible",
    ]
    missing = [name for name in sorted(set(required)) if ("_" + name) not in defined_symbols]
    if missing:
        raise ValueError("Missing required native Mach-O symbols: " + ", ".join(missing[:20]))

    def require_in_section(sym_name, sec, sec_label):
        sym_addr = defined_symbols["_" + sym_name]["value"]
        if not (sec["addr"] <= sym_addr < sec["addr"] + sec["size"]):
            raise ValueError(f"Symbol {sym_name} ({hex(sym_addr)}) outside {sec_label}")

    require_in_section("JS_CVMRunFastSegment", cvm_section, "__TEXT,__qjs_cvm")
    require_in_section("JS_CVMFastEligible", const_section, "__TEXT,__const")
    require_in_section("JS_LinuxVirtualArgumentsStep", varg_section, "__TEXT,__qjs_varg")

    # Verify DWARF EH frame coverage for assembly VM entries and compact unwind / EH frame
    # coverage for compiled C entries.
    eh = subprocess.check_output(["dwarfdump", "--eh-frame", str(binary)], text=True)
    fde_blocks = parse_eh_frame_fdes(eh)
    spans = [(lo, hi) for _, lo, hi, _ in fde_blocks]
    if not spans:
        raise ValueError("Missing DWARF EH frame FDE entries in Mach-O binary")

    text_base = text_seg["vmaddr"]
    unwind_out = subprocess.check_output(["objdump", "--unwind-info", str(binary)], text=True)
    compact_entries = [
        (text_base + int(m.group(1), 16), int(m.group(2), 16))
        for m in re.finditer(
            r"\[\d+\]:\s+function offset=0x([0-9a-fA-F]+),\s+encoding(?:\[\d+\])?=0x([0-9a-fA-F]+)",
            unwind_out,
        )
    ]
    compact_entries.sort(key=lambda item: item[0])

    def lookup_compact_unwind(addr):
        lo_idx, hi_idx = 0, len(compact_entries) - 1
        found = -1
        while lo_idx <= hi_idx:
            mid = (lo_idx + hi_idx) // 2
            if compact_entries[mid][0] <= addr:
                found = mid
                lo_idx = mid + 1
            else:
                hi_idx = mid - 1
        return compact_entries[found] if found >= 0 else None

    def has_compact_unwind(addr):
        entry = lookup_compact_unwind(addr)
        return entry is not None and entry[1] != 0

    for check_sym in (vm["private_entry"], "JS_Call", "JS_CVMRunFastSegment"):
        addr = defined_symbols["_" + check_sym]["value"]
        if not any(lo <= addr < hi for lo, hi in spans):
            raise ValueError("Missing EH frame FDE for native ASM symbol: " + check_sym)

    cvm_addr = defined_symbols["_JS_CVMRunFastSegment"]["value"]
    cvm_section_symbols = [
        sym["name"]
        for sym in defined_symbols.values()
        if cvm_section["addr"] <= sym["value"] < cvm_section["addr"] + cvm_section["size"]
    ]
    verify_cvm_unwind(
        cvm_addr,
        cvm_section,
        macho.section_data(cvm_section),
        cvm_section_symbols,
        lookup_compact_unwind(cvm_addr),
        fde_blocks,
    )

    for check_sym in ("JS_LinuxVirtualArgumentsStep", "JS_LinuxVirtualArgumentsPush"):
        addr = defined_symbols["_" + check_sym]["value"]
        if not any(lo <= addr < hi for lo, hi in spans) and not has_compact_unwind(addr):
            raise ValueError("Missing unwind coverage for native C symbol: " + check_sym)

    otool_out = subprocess.check_output(["otool", "-l", str(binary)], text=True)
    (build / "native-macho.txt").write_text(otool_out, encoding="utf-8")

    cvm_c_enabled = (
        "_JS_CVMResumeEntry" in defined_symbols and "_JS_CVMResumeInternal" in defined_symbols
    )
    record = dict(
        status="built-normal-CMake-macos-x86_64-native-backend",
        register_vm=True,
        cvm_asm_linked=True,
        cvm_fast_segments=cvm_c_enabled,
        internal_quota=True,
        internal_entry_routed=True,
        source=str(source),
        binary_sha256=sha(binary),
        archive_sha256=sha(archive),
        backend="MACOS_X86_64",
        PIE=True,
        nonexec_stack=True,
        wx_clean=True,
        fde_count=len(spans),
        required_symbols_verified=len(set(required)),
        adapt_sha256=sha(generated / "MACOS-ADAPT.json"),
        vm_sha256=sha(generated / "VM.json"),
        layout=str(build / "generated/macos-abi/layout.json"),
        layout_sha256=sha(build / "generated/macos-abi/layout.json"),
    )
    git_root = upstream_root(source)
    git = subprocess.run(
        ["git", "-C", git_root, "rev-parse", "--show-toplevel"], text=True, capture_output=True
    )
    if git.returncode == 0 and Path(git.stdout.strip()).resolve() in {
        source.resolve(),
        git_root.resolve(),
    }:
        record["source_commit"] = subprocess.check_output(
            ["git", "-C", git_root, "rev-parse", "HEAD"], text=True
        ).strip()
        record["source_dirty"] = subprocess.check_output(
            ["git", "-C", git_root, "status", "--porcelain"], text=True
        )
    (build / "BUILD.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("MACOS NATIVE CMAKE IMAGE BOUND", binary)


if __name__ == "__main__":
    main()
