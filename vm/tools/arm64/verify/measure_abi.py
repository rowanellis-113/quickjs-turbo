"""Compile actual overlaid core types into constants; no target probe execution."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import activate_arm64_tools, source_file, upstream_root

activate_arm64_tools()
from elf64 import Elf64
from layout_input import load_input, requests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "output"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    source, build, output = (p.resolve() for p in (a.source, a.build, a.output))
    output.mkdir(parents=True, exist_ok=True)
    profile_path = source / "src/arm64/linux/abi/profile.json"
    profile = json.loads(profile_path.read_text())
    if profile["schema"] != 1 or profile["machine"] != 183 or profile["native_vm"]:
        raise ValueError("Unreviewed AArch64 foundation profile")
    for name, digest in profile["files"].items():
        path = source_file(source, name).resolve()
        if (
            not (path.is_relative_to(source) or path.is_relative_to(upstream_root(source)))
            or sha(path) != digest
        ):
            raise ValueError("AArch64 reviewed input changed: " + name)
    actual_input = load_input(source, build)
    catalogue_path, catalogue, backports = (
        actual_input.catalogue_path,
        actual_input.catalogue,
        actual_input.receipt,
    )
    core, compiler, flags = actual_input.core, actual_input.compiler, actual_input.flags
    command, prelude = actual_input.command, actual_input.prelude
    if sha(source_file(source, "quickjs.h")) != profile["public_header_sha256"]:
        raise ValueError("Public value/callback types require review")
    triple = subprocess.check_output([compiler, "-dumpmachine"], text=True).strip()
    if not triple.startswith("aarch64"):
        raise ValueError("Expected an actual AArch64 compiler")
    if any(f.startswith(("-flto", "-fsanitize")) for f in flags):
        raise ValueError("Foundation probe requires plain non-LTO, nonsanitized objects")
    signatures = re.findall(r"static\s+(JSValue\s+JS_CallInternal\s*\([^;{}]+\));", prelude)
    if len(signatures) != 1:
        raise ValueError("Missing unique actual JS_CallInternal declaration")
    signature = signatures[0]
    types = "/* Generated from the actual overlaid core; no compiler clone ABI. */\n"
    types += "#ifndef QJS_AARCH64_CALL_TYPES_H\n#define QJS_AARCH64_CALL_TYPES_H\n"
    types += (
        "typedef " + signature.replace("JS_CallInternal", "QJSAArch64CoreCall", 1) + ";\n#endif\n"
    )
    put(output / "qjs-aarch64-call-types.h", types)
    keys, expressions = requests(catalogue, backports["property_ic"], alignment=True)
    checks = """
#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Linux AArch64 LE LP64 required
#endif
#include <stddef.h>
#include <stdint.h>
#include "qjs-aarch64-call-types.h"
_Static_assert(__builtin_types_compatible_p(__typeof__(JS_CallInternal), QJSAArch64CoreCall), "Actual core call type changed");
#ifndef __ARM_FEATURE_BTI_DEFAULT
#define __ARM_FEATURE_BTI_DEFAULT 0
#endif
#ifndef __ARM_FEATURE_PAC_DEFAULT
#define __ARM_FEATURE_PAC_DEFAULT 0
#endif
__attribute__((used,section(".qjs.arm.features"),aligned(8)))
const uint64_t qjs_arm_features[] = {__ARM_ARCH,__ARM_FEATURE_BTI_DEFAULT,__ARM_FEATURE_PAC_DEFAULT,sizeof(void*)};
"""
    lines = [
        prelude,
        checks,
        '__attribute__((used,section(".qjs.arm.layout"),aligned(8))) const uint64_t qjs_arm_layout[] = {',
        "0x514a5341524d3634ULL," + str(len(keys)) + ",",
        *[e + "," for e in expressions],
        "};",
    ]
    for index, name in enumerate(catalogue["bits"]):
        owner, field = name.split(".", 1)
        lines.append(
            '__attribute__((used,section(".qjs.arm.bit'
            + str(index)
            + '"))) const '
            + owner
            + " qjs_arm_bit"
            + str(index)
            + " = {."
            + field
            + "=1};"
        )
    probe, obj = output / "layout-probe.c", output / "layout-probe.o"
    put(probe, "\n".join(lines) + "\n")
    actual = [
        compiler,
        "-I" + str(core.parent),
        "-I" + str(output),
        *flags,
        "-Wno-unused-function",
        "-Wno-unused-const-variable",
        "-c",
        str(probe),
        "-o",
        str(obj),
    ]
    with (output / "compile.stdout").open("wb") as so, (output / "compile.stderr").open("wb") as se:
        subprocess.run(actual, cwd=command["directory"], stdout=so, stderr=se, check=True)
    elf = Elf64.read(obj, expected_machine=183)
    if elf.kind != 1:
        raise ValueError("Expected a relocatable target probe")
    raw = elf.section_data(elf.section(".qjs.arm.layout"))
    if len(raw) != (len(keys) + 2) * 8:
        raise ValueError("Unexpected constant-table extent")
    values = struct.unpack("<" + "Q" * (len(keys) + 2), raw)
    if values[:2] != (0x514A5341524D3634, len(keys)):
        raise ValueError("Invalid probe signature")
    layout = dict(
        schema=1,
        platform="linux-aarch64-aapcs64",
        reference_count_model="allocator-prefix",
        sizes={},
        offsets={},
        constants={},
        alignment={},
        bits={},
    )
    for (group, name), value in zip(keys, values[2:]):
        if group == "constants" and value >= 1 << 63:
            value -= 1 << 64
        layout[group][name] = value
    for index, name in enumerate(catalogue["bits"]):
        raw = elf.section_data(elf.section(".qjs.arm.bit" + str(index)))
        bits = [[i, b] for i, b in enumerate(raw) if b]
        if len(bits) != 1:
            raise ValueError("Review missing/split target bitfield: " + name)
        layout["bits"][name] = bits
    feature_values = struct.unpack("<4Q", elf.section_data(elf.section(".qjs.arm.features")))
    layout["compiler_features"] = dict(
        zip(("arm_arch", "bti", "pac", "pointer_size"), feature_values)
    )
    if feature_values != (8, 0, 0, 8):
        raise ValueError(
            "Current AArch64 foundation requires ARMv8 LP64 without BTI/PAC; measured "
            + str(feature_values)
        )
    if (
        layout["sizes"]["JSValue"],
        layout["offsets"]["JSValue.tag"],
        layout["alignment"]["JSValue"],
    ) != (16, 8, 8):
        raise ValueError("Unsupported actual value representation")
    header = [
        "/* Generated target constants; do not substitute another architecture. */",
        "#ifndef QJS_AARCH64_ABI_VALUES_H",
        "#define QJS_AARCH64_ABI_VALUES_H",
    ]
    for group, prefix in (
        ("sizes", "SIZE_"),
        ("offsets", "OFF_"),
        ("constants", "CONST_"),
        ("alignment", "ALIGN_"),
    ):
        for name, value in layout[group].items():
            header.append(
                "#define QJS_AARCH64_" + prefix + name.replace(".", "_") + " (" + str(value) + ")"
            )
    for name, bits in layout["bits"].items():
        header += [
            "#define QJS_AARCH64_BIT_" + name.replace(".", "_") + "_BYTE (" + str(bits[0][0]) + ")",
            "#define QJS_AARCH64_BIT_" + name.replace(".", "_") + "_MASK (" + str(bits[0][1]) + ")",
        ]
    header += ["#endif", ""]
    put(output / "qjs-aarch64-abi-values.h", "\n".join(header))
    layout.update(
        compiler_input_sha256=sha(core),
        public_header_sha256=sha(source_file(source, "quickjs.h")),
        field_catalogue_sha256=sha(catalogue_path),
        profile_sha256=sha(profile_path),
        reviewed_inputs=profile["files"],
        probe_sha256=sha(probe),
        object_sha256=sha(obj),
        compiler=compiler,
        target=triple,
        flags=flags,
        compile_command=actual,
        core_call_declaration=signature,
        probe_executed=False,
        native_vm=False,
    )
    put(output / "LAYOUT.json", json.dumps(layout, indent=2) + "\n")
    print(
        "AARCH64_CORE_ABI_MEASURED",
        len(keys),
        "values",
        len(catalogue["bits"]),
        "bitfields; core call type checked",
    )


if __name__ == "__main__":
    main()
