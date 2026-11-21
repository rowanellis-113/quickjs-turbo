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
    VM_PROT_WRITE,
    MachO64,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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

    for name, expected in {**adapt["c_files"], **adapt["asm_files"]}.items():
        if sha(generated / name) != expected:
            raise ValueError("Generated macOS native input changed: " + name)

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

    varg_section = macho.section("__TEXT", "__qjs_varg")
    if varg_section["size"] == 0:
        raise ValueError("Empty virtual arguments code section")

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
    ]
    missing = [name for name in sorted(set(required)) if ("_" + name) not in defined_symbols]
    if missing:
        raise ValueError("Missing required native Mach-O symbols: " + ", ".join(missing[:20]))

    # Verify DWARF EH frame coverage for assembly VM entries and compact unwind / EH frame
    # coverage for compiled C entries.
    eh = subprocess.check_output(["dwarfdump", "--eh-frame", str(binary)], text=True)
    spans = [
        (int(m.group(1), 16), int(m.group(2), 16))
        for m in re.finditer(r"FDE .*?pc=([0-9a-fA-F]+)\.\.\.([0-9a-fA-F]+)", eh)
    ]
    if not spans:
        raise ValueError("Missing DWARF EH frame FDE entries in Mach-O binary")

    text_seg = next(s for s in macho.segments if s["segname"] == "__TEXT")
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

    def has_compact_unwind(addr):
        lo_idx, hi_idx = 0, len(compact_entries) - 1
        found = -1
        while lo_idx <= hi_idx:
            mid = (lo_idx + hi_idx) // 2
            if compact_entries[mid][0] <= addr:
                found = mid
                lo_idx = mid + 1
            else:
                hi_idx = mid - 1
        return found >= 0 and compact_entries[found][1] != 0

    for check_sym in (vm["private_entry"], "JS_Call"):
        addr = defined_symbols["_" + check_sym]["value"]
        if not any(lo <= addr < hi for lo, hi in spans):
            raise ValueError("Missing EH frame FDE for native ASM symbol: " + check_sym)
    for check_sym in ("JS_LinuxVirtualArgumentsStep", "JS_LinuxVirtualArgumentsPush"):
        addr = defined_symbols["_" + check_sym]["value"]
        if not any(lo <= addr < hi for lo, hi in spans) and not has_compact_unwind(addr):
            raise ValueError("Missing unwind coverage for native C symbol: " + check_sym)

    otool_out = subprocess.check_output(["otool", "-l", str(binary)], text=True)
    (build / "native-macho.txt").write_text(otool_out, encoding="utf-8")

    record = dict(
        status="built-normal-CMake-macos-x86_64-native-backend",
        register_vm=True,
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
