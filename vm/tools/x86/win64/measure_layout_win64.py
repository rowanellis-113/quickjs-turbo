"""Measure Windows x86-64 private ABI from this build's overlaid core prelude.

Uses MSVC cl.exe or clang-cl to compile a small probe object and parses COFF
sections directly in Python (zero GNU binutils dependency). Works in both
standalone and add_subdirectory() builds across Ninja and Visual Studio.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

_TOOLS_ROOT = Path(__file__).resolve().parents[2]
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))

from common.paths import source_file
from common.elf.layout_input import requests as layout_requests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_coff_class(source):
    adapter_path = source / "tools/x86/win64/coff/object-adapter.py"
    spec = importlib.util.spec_from_file_location("qjs_win64_coff_adapter", adapter_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Coff


def section_bytes(coff, name):
    for info, rec in zip(coff.sections, coff.section_records):
        if info["name"] == name:
            raw, size = rec["raw"], rec["size"]
            return bytes(coff.data[raw : raw + size]) if raw else b"\0" * size
    raise ValueError(f"Missing COFF section {name!r} in layout probe")


def measure(source, upstream, build, output, compiler, defines=(), is_clang_cl=False):
    source = Path(source).resolve()
    upstream = Path(upstream).resolve()
    build = Path(build).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    catalogue_path = source / "src/common/internal/abi/core-fields.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    receipt = json.loads((build / "generated/backports/BACKPORTS.json").read_text(encoding="utf-8"))
    core = Path(receipt["compiler_input"])
    core_src = source_file(source, "quickjs.c")
    if sha(core) != receipt["compiler_input_sha256"]:
        raise ValueError("Backported core input changed; regenerate before measuring Win64 layout")
    actual_src_sha = hashlib.sha256(core_src.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if actual_src_sha != catalogue["source_sha256"]:
        raise ValueError("Upstream quickjs.c hash mismatch against core-fields.json")

    text = core.read_text(encoding="utf-8")
    anchor = "static inline bool double_is_int32"
    if text.count(anchor) != 1:
        raise ValueError("Core prelude anchor changed")
    prelude = text[: text.index(anchor)]

    keys, expressions = layout_requests(catalogue, receipt["property_ic"])
    if "drc_ok" in prelude:
        keys.append(("offsets", "JSRuntime.drc_ok"))
        expressions.append("offsetof(JSRuntime, drc_ok)")

    lines = [
        prelude,
        "#include <stdint.h>",
        "#include <stddef.h>",
        '#pragma section(".qjlay", read)',
        '__declspec(allocate(".qjlay")) const uint64_t qjs_win64_layout[] = {',
        f"0x514a534c41594f55ULL, 1, {len(keys)},",
    ]
    lines += [expr + "," for expr in expressions]
    lines += ["};"]
    for index, name in enumerate(catalogue["bits"]):
        typename, field = name.split(".", 1)
        sec = f".qjb{index:03d}"
        lines += [
            f'#pragma section("{sec}", read)',
            f'__declspec(allocate("{sec}")) const {typename} qjs_win64_bit_{index} = {{ .{field} = 1 }};',
        ]

    probe = output / "layout-probe.c"
    obj = output / "layout-probe.obj"
    probe.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    cmd = [
        str(compiler),
        "/nologo",
        "/c",
        "/O2",
        "/std:c11",
        "/GL-",
        f"/I{core.parent}",
        f"/I{source}",
        f"/I{upstream}",
        f"/I{build}",
    ]
    if not is_clang_cl:
        cmd.append("/experimental:c11atomics")
    else:
        cmd.append("-fno-lto")
    for d in defines:
        if d:
            cmd.append(f"/D{d}")
    cmd.extend([f"/Fo{obj}", str(probe)])

    res = subprocess.run(cmd, cwd=str(output), capture_output=True, text=True)
    (output / "compile.stdout").write_text(res.stdout, encoding="utf-8")
    (output / "compile.stderr").write_text(res.stderr, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(
            f"Win64 layout probe compilation failed (rc={res.returncode}):\n{res.stdout}\n{res.stderr}"
        )

    Coff = load_coff_class(source)
    coff = Coff(obj.read_bytes())
    raw = section_bytes(coff, ".qjlay")
    expected_len = (len(keys) + 3) * 8
    if len(raw) < expected_len:
        raise ValueError(f"Unexpected Win64 layout probe extent: {len(raw)} < {expected_len}")
    values = struct.unpack("<" + "Q" * (len(keys) + 3), raw[:expected_len])
    if values[:3] != (0x514A534C41594F55, 1, len(keys)):
        raise ValueError(f"Invalid Win64 layout probe header: {values[:3]}")

    layout = dict(
        schema=1,
        platform="win64-x86_64",
        target="x86_64-pc-windows-msvc",
        sizes={},
        offsets={},
        constants={},
        bits={},
        reference_count_model="inline-header",
        property_ic=receipt["property_ic"],
        value64_header=receipt["value64_header"],
        source_sha256=actual_src_sha,
        compiler_input_sha256=sha(core),
        compiler_input=str(core),
        catalogue_sha256=sha(catalogue_path),
        probe_sha256=sha(probe),
        object_sha256=sha(obj),
        compiler=str(compiler),
    )
    for (group, name), value in zip(keys, values[3:]):
        if group == "constants" and value >= 1 << 63:
            value -= 1 << 64
        layout[group][name] = value

    for index, name in enumerate(catalogue["bits"]):
        sec = f".qjb{index:03d}"
        braw = section_bytes(coff, sec)
        nonzero = [[i, v] for i, v in enumerate(braw) if v]
        if not nonzero:
            raise ValueError(f"Missing Win64 bitfield initializer: {name}")
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
    layout["reference_count_model"] = ref_model

    (output / "layout.json").write_text(
        json.dumps(layout, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    contract = [
        "/* Generated from actual Windows x86-64 compiler input; do not edit. */",
        "#ifndef QJS_WIN64_PRIVATE_ABI_H",
        "#define QJS_WIN64_PRIVATE_ABI_H",
    ]
    for group, prefix in [("sizes", "SIZE_"), ("offsets", "OFF_"), ("constants", "CONST_")]:
        for name, value in layout[group].items():
            contract.append(f"#define QJS_ABI_{prefix}{name.replace('.', '_')} ({value})")
    for name, bits in layout["bits"].items():
        if len(bits) != 1:
            raise ValueError(f"Split bitfield in Win64 ABI: {name}")
        contract += [
            f"#define QJS_ABI_BIT_{name.replace('.', '_')}_BYTE ({bits[0][0]})",
            f"#define QJS_ABI_BIT_{name.replace('.', '_')}_MASK ({bits[0][1]})",
        ]
    contract += [
        f"#define QJS_ABI_HAS_CORO_OWNER ({coro_owner})",
        f"#define QJS_ABI_HAS_PREFIX_RC ({int(prefix_rc)})",
        f"#define QJS_ABI_REF_COUNT_OFFSET ({rc_off})",
    ]
    values_hdr = [
        line.replace("QJS_WIN64_PRIVATE_ABI_H", "QJS_WIN64_PRIVATE_ABI_VALUES_H")
        for line in contract
    ]
    (output / "interpreter-private-abi-values.h").write_text(
        "\n".join(values_hdr + ["#endif", ""]), encoding="utf-8", newline="\n"
    )
    for name in layout["sizes"]:
        contract.append(
            f'_Static_assert(sizeof({name}) == QJS_ABI_SIZE_{name}, "Win64 size: {name}");'
        )
    for name, value in layout["offsets"].items():
        typename, field = name.split(".", 1)
        contract.append(
            f'_Static_assert(offsetof({typename}, {field}) == {value}, "Win64 offset: {name}");'
        )
    contract += ["#endif", ""]
    (output / "interpreter-private-abi.h").write_text(
        "\n".join(contract), encoding="utf-8", newline="\n"
    )
    print(f"WIN64 PRIVATE ABI MEASURED {len(keys)} constants, {len(catalogue['bits'])} bitfields")
    return layout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--clang-cl", action="store_true")
    ap.add_argument("--define", action="append", default=[])
    args = ap.parse_args()
    measure(
        args.source,
        args.upstream,
        args.build,
        args.output,
        args.compiler,
        defines=args.define,
        is_clang_cl=args.clang_cl,
    )


if __name__ == "__main__":
    main()
