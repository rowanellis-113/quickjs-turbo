"""Bind real AArch64 bridge ELF, full CFI and source/ABI receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import activate_arm64_tools, source_file

activate_arm64_tools()
from elf64 import Elf64


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "image", "object", "readelf", "archive", "ar"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    source, build, image, obj = (p.resolve() for p in (a.source, a.build, a.image, a.object))
    output = build / "generated/aarch64-abi"
    layout = json.loads((output / "LAYOUT.json").read_text())
    if layout["native_vm"] or layout["probe_executed"]:
        raise ValueError("Wrong foundation scope")
    for name, digest in layout["reviewed_inputs"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Reviewed AArch64 input changed after generation: " + name)
    if sha(output / "layout-probe.o") != layout["object_sha256"]:
        raise ValueError("Target layout probe changed")
    elf, object_elf = Elf64.read(image, expected_machine=183), Elf64.read(obj, expected_machine=183)
    if elf.kind != 3 or object_elf.kind != 1:
        raise ValueError("Require PIE executable and relocatable bridge object")
    for path in (image, obj):
        try:
            Elf64.read(path)
        except ValueError:
            pass
        else:
            raise ValueError("Default foreign ELF policy accepted ARM input")

    def has_bridge(elf):
        return any(
            s["name"].startswith(("qjs_aarch64_call_", "qjs_aarch64_test_")) for s in elf.symbols()
        )

    if has_bridge(Elf64.read(build / "qjs", expected_machine=183)):
        raise ValueError("Foundation must not change the engine route")
    members = subprocess.check_output([str(a.ar), "t", str(a.archive)], text=True).splitlines()
    for member in members:
        data = subprocess.check_output([str(a.ar), "p", str(a.archive), member])
        if has_bridge(Elf64(data, expected_machine=183)):
            raise ValueError("Standalone foundation was linked into qjs archive")
    symbols = {s["name"]: s for s in elf.symbols() if s["type"] == 2 and s["size"]}
    frames = subprocess.check_output(
        [str(a.readelf), "-W", "--debug-dump=frames", image], text=True
    )
    spans = [
        (int(m[1], 16), int(m[2], 16))
        for m in re.finditer(r"FDE .*pc=([a-f0-9]+)\.\.([a-f0-9]+)", frames)
    ]
    entries = [
        "qjs_aarch64_call_" + n for n in ("generic", "magic", "data", "double", "internal")
    ] + ["qjs_aarch64_test_saved"]
    coverage = {}
    for name in entries:
        symbol = symbols[name]
        section = elf.sections[symbol["section"]]
        if section["flags"] & 6 != 6 or section["flags"] & 1:
            raise ValueError("Bridge code must be allocated, executable and nonwritable: " + name)
        if not any(
            lo <= symbol["value"] and symbol["value"] + symbol["size"] <= hi for lo, hi in spans
        ):
            raise ValueError("Missing complete target FDE: " + name)
        coverage[name] = dict(address=symbol["value"], size=symbol["size"])
    segments = subprocess.check_output([str(a.readelf), "-lW", image], text=True)
    stack = [line for line in segments.splitlines() if "GNU_STACK" in line]
    if len(stack) != 1 or "RWE" in stack[0] or "RW " not in stack[0]:
        raise ValueError("Missing nonexecutable GNU stack")
    compiler = layout["compiler"]
    rejected = subprocess.run(
        [
            compiler,
            "-mbranch-protection=standard",
            "-I" + str(source),
            "-I" + str(output),
            "-c",
            str(source / "asm/arm64/linux/call-abi.S"),
            "-o",
            str(output / "unsupported-hardening.o"),
        ],
        capture_output=True,
        text=True,
    )
    if rejected.returncode != 1 or "requires a baseline without BTI/PAC" not in rejected.stderr:
        raise ValueError("Unqualified hardening configuration was not rejected")
    (output / "hardening-rejection.txt").write_text(rejected.stderr)
    result = dict(
        status="passed-aarch64-standard-call-foundation",
        native_vm=False,
        linked_into_qjs=False,
        image_sha256=sha(image),
        bridge_object_sha256=sha(obj),
        archive_sha256=sha(a.archive),
        engine_sha256=sha(build / "qjs"),
        layout_sha256=sha(output / "LAYOUT.json"),
        full_fde_coverage=coverage,
        pie=True,
        nonexecutable_stack=True,
        unsupported_hardening_rejected=True,
    )
    (output / "CHECK.json").write_text(json.dumps(result, indent=2) + "\n")
    print("AARCH64_ABI_ELF_OK functions=6 full-FDE PIE NX; not a native VM")


if __name__ == "__main__":
    main()
