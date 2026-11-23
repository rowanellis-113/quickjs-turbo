import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, source_file

_act_x86()

"""Measure Linux private ABI from this build's actual overlaid core prelude.

No Windows numeric layout or compiler clone signature is used. The catalogue
declares required field names; GCC emits their actual constants and bitfields.
The probe is compiled separately and never linked into the engine.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from elf64 import Elf64
from layout_input import load_input, requests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--command-source",
        type=Path,
        help="Select actual generated core compile flags for a normal native CMake target",
    )
    args = ap.parse_args()
    source, build, output = [p.resolve() for p in (args.source, args.build, args.output)]
    output.mkdir(parents=True, exist_ok=True)
    actual_input = load_input(source, build, args.command_source)
    catalogue_path, catalogue, receipt = (
        actual_input.catalogue_path,
        actual_input.catalogue,
        actual_input.receipt,
    )
    core, compiler, flags = actual_input.core, actual_input.compiler, actual_input.flags
    command, prelude = actual_input.command, actual_input.prelude
    keys, expressions = requests(catalogue, receipt["property_ic"])
    if "drc_ok" in prelude:
        keys.append(("offsets", "JSRuntime.drc_ok"))
        expressions.append("offsetof(JSRuntime, drc_ok)")
    lines = [
        prelude,
        "#include <stdint.h>\n#include <stddef.h>",
        '__attribute__((used,section(".rodata.qjs_linux_layout"),aligned(8)))',
        "const uint64_t qjs_linux_layout[] = {",
        "0x514a534c41594f55ULL, 1, " + str(len(keys)) + ",",
    ]
    lines += [expr + "," for expr in expressions]
    lines += [
        "};",
        "#ifndef __CET__",
        "#define __CET__ 0",
        "#endif",
        '__attribute__((used,section(".rodata.qjs_linux_cet")))',
        "const uint32_t qjs_linux_cet = __CET__;",
    ]
    for index, name in enumerate(catalogue["bits"]):
        typename, field = name.split(".", 1)
        lines += [
            '__attribute__((used,section(".rodata.qjs_linux_bit_' + str(index) + '")))',
            "const " + typename + " qjs_linux_bit_" + str(index) + " = { ." + field + " = 1 };",
        ]
    probe, obj = output / "layout-probe.c", output / "layout-probe.o"
    probe.write_text("\n".join(lines) + "\n")
    actual = [
        compiler,
        "-I" + str(core.parent),
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
    elf = Elf64.read(obj)
    if elf.kind != 1:
        raise ValueError("Layout probe must be relocatable ELF")
    raw = elf.section_data(elf.section(".rodata.qjs_linux_layout"))
    if len(raw) != (len(keys) + 3) * 8:
        raise ValueError("Unexpected layout probe extent")
    values = struct.unpack("<" + "Q" * (len(keys) + 3), raw)
    if values[:3] != (0x514A534C41594F55, 1, len(keys)):
        raise ValueError("Invalid layout probe header")
    (cet,) = struct.unpack("<I", elf.section_data(elf.section(".rodata.qjs_linux_cet")))
    if cet not in (0, 1, 2, 3):
        raise ValueError("Unreviewed compiler CET feature bits: " + str(cet))
    layout = dict(
        schema=1,
        platform="linux-x86_64-sysv",
        sizes={},
        offsets={},
        constants={},
        bits={},
        compiler_features=dict(cet=cet),
    )
    for (group, name), value in zip(keys, values[3:]):
        if group == "constants" and value >= 1 << 63:
            value -= 1 << 64
        layout[group][name] = value
    for index, name in enumerate(catalogue["bits"]):
        raw = elf.section_data(elf.section(".rodata.qjs_linux_bit_" + str(index)))
        nonzero = [[i, value] for i, value in enumerate(raw) if value]
        if not nonzero:
            raise ValueError("Missing bitfield initializer: " + name)
        layout["bits"][name] = nonzero
    prefix_rc = "JSMallocBlockHeader.ref_count" in layout["offsets"]
    ref_model = "allocator-prefix" if prefix_rc else "inline-header"
    rc_off = (
        layout["offsets"]["JSMallocBlockHeader.ref_count"]
        - layout["offsets"]["JSMallocBlockHeader.user_data"]
        if prefix_rc
        else layout["offsets"]["JSGCObjectHeader.ref_count"]
    )
    coro_owner = int("JSStackFrame.cur_gc_obj" in layout["offsets"])
    layout.update(
        source_sha256=sha(source_file(source, "quickjs.c")),
        compiler_input_sha256=sha(core),
        compiler_input=str(core),
        reference_count_model=ref_model,
        public_header_sha256=sha(source_file(source, "quickjs.h")),
        catalogue_sha256=sha(catalogue_path),
        compiler=subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        target=subprocess.check_output([compiler, "-dumpmachine"], text=True).strip(),
        flags=flags,
        property_ic=receipt["property_ic"],
        value64_header=receipt["value64_header"],
        probe_sha256=sha(probe),
        object_sha256=sha(obj),
        compile_command=actual,
        scope="Actual Linux compiler layout and control-flow feature measurement",
    )
    (output / "layout.json").write_text(json.dumps(layout, indent=2) + "\n")
    contract = [
        "/* Generated from actual Linux compiler input; do not edit. */",
        "#ifndef QJS_LINUX_PRIVATE_ABI_H",
        "#define QJS_LINUX_PRIVATE_ABI_H",
    ]
    for group, prefix in [("sizes", "SIZE_"), ("offsets", "OFF_"), ("constants", "CONST_")]:
        for name, value in layout[group].items():
            contract.append(
                "#define QJS_ABI_" + prefix + name.replace(".", "_") + " (" + str(value) + ")"
            )
    for name, bits in layout["bits"].items():
        if len(bits) != 1:
            raise ValueError("Review split bitfield before native access: " + name)
        contract += [
            "#define QJS_ABI_BIT_" + name.replace(".", "_") + "_BYTE (" + str(bits[0][0]) + ")",
            "#define QJS_ABI_BIT_" + name.replace(".", "_") + "_MASK (" + str(bits[0][1]) + ")",
        ]
    contract += [
        f"#define QJS_ABI_HAS_CORO_OWNER ({coro_owner})",
        f"#define QJS_ABI_HAS_PREFIX_RC ({int(prefix_rc)})",
        f"#define QJS_ABI_REF_COUNT_OFFSET ({rc_off})",
    ]
    values = [
        line.replace("QJS_LINUX_PRIVATE_ABI_H", "QJS_LINUX_PRIVATE_ABI_VALUES_H")
        for line in contract
    ]
    (output / "interpreter-private-abi-values.h").write_text("\n".join(values + ["#endif", ""]))
    for name in layout["sizes"]:
        contract.append(
            "_Static_assert(sizeof("
            + name
            + ") == QJS_ABI_SIZE_"
            + name
            + ', "Linux size: '
            + name
            + '");'
        )
    for name, value in layout["offsets"].items():
        typename, field = name.split(".", 1)
        contract.append(
            "_Static_assert(offsetof("
            + typename
            + ", "
            + field
            + ") == "
            + str(value)
            + ', "Linux offset: '
            + name
            + '");'
        )
    contract += [
        "#ifdef __CET__",
        "_Static_assert(__CET__ == " + str(cet) + ', "Linux compiler CET profile changed");',
        "#else",
        "_Static_assert(0 == " + str(cet) + ', "Linux compiler CET profile changed");',
        "#endif",
        "#endif",
        "",
    ]
    (output / "interpreter-private-abi.h").write_text("\n".join(contract))
    print(
        "LINUX PRIVATE ABI MEASURED", len(keys), "constants,", len(catalogue["bits"]), "bitfields"
    )


if __name__ == "__main__":
    main()
