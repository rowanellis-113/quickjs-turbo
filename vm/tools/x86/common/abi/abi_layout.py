"""Measured, source-bound private ABI constants for C and Win64 assemblers."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.paths import source_file


def validate_measured_override(source, layout):
    """An explicit Linux measurement is separate from the Win64 catalogue."""
    source = Path(source).resolve()
    target = layout.get("target", "")
    platform = layout.get("platform", "")
    linux_suffixes = ("-linux-gnu", "-linux-musl", "-linux")
    linux_target = target.startswith("x86_64-") and target.endswith(linux_suffixes)
    valid_target = (
        platform == "linux-x86_64-sysv"
        and (linux_target or target.startswith("x86_64-apple-darwin"))
    ) or (platform == "win64-x86_64" and target == "x86_64-pc-windows-msvc")
    if not valid_target:
        raise ValueError("Unsupported measured native platform override")
    if (
        hashlib.sha256(
            source_file(source, "quickjs.c").read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        != layout["source_sha256"]
    ):
        raise ValueError("Measured Linux ABI source changed")
    compiler_input = Path(layout["compiler_input"])
    if hashlib.sha256(compiler_input.read_bytes()).hexdigest() != layout["compiler_input_sha256"]:
        raise ValueError("Measured Linux compiler input changed")
    if (
        layout.get("reference_count_model") != "inline-header"
        or layout["offsets"]["JSGCObjectHeader.ref_count"] != 0
    ):
        raise ValueError("Review Linux reference-count model before native generation")
    return layout


def write_if_changed(path, text):
    path = Path(path)
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def load(source):
    source = Path(source).resolve()
    text = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    directory = source / "src/x86/win64/abi"
    matches = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("quickjs-*.json"))
    ]
    matches = [value for value in matches if value["source_sha256"] == digest]
    if len(matches) != 1:
        raise ValueError(
            "No unique measured private ABI for this quickjs.c; compile both layout probes and review the port"
        )
    return matches[0]


def constants(layout):
    values = {}
    for name, value in layout["constants"].items():
        values["QJS_ABI_CONST_" + name] = value
    for name, value in layout["sizes"].items():
        values["QJS_ABI_SIZE_" + name] = value
    for name, value in layout["offsets"].items():
        values["QJS_ABI_OFF_" + name.replace(".", "_")] = value
    for name, value in layout["bits"].items():
        if len(value) != 1:
            raise ValueError("Bitfield spans bytes; review native access: " + name)
        values["QJS_ABI_BIT_" + name.replace(".", "_") + "_BYTE"] = value[0][0]
        values["QJS_ABI_BIT_" + name.replace(".", "_") + "_MASK"] = value[0][1]
    values["QJS_ABI_REF_COUNT_OFFSET"] = (
        layout["offsets"]["JSMallocBlockHeader.ref_count"]
        - layout["offsets"]["JSMallocBlockHeader.user_data"]
        if layout["reference_count_model"] == "allocator-prefix"
        else layout["offsets"]["JSGCObjectHeader.ref_count"]
    )
    values["QJS_ABI_HAS_CORO_OWNER"] = int("JSStackFrame.cur_gc_obj" in layout["offsets"])
    values["QJS_ABI_HAS_PREFIX_RC"] = int(layout["reference_count_model"] == "allocator-prefix")
    return values


def c_contract(layout):
    lines = [
        "/* Measured private ABI; source SHA256: " + layout["source_sha256"] + " */",
        "#ifndef QJS_FRAME_PRIVATE_ABI_H",
        "#define QJS_FRAME_PRIVATE_ABI_H",
    ]
    for name, value in constants(layout).items():
        if name in (
            "QJS_ABI_SIZE_JSRuntime",
            "QJS_ABI_SIZE_JSFunctionBytecode",
            "QJS_ABI_SIZE_JSContext",
        ):
            extra = 32 if name.endswith("JSRuntime") else 56 if name.endswith("JSContext") else 8
            lines.extend(
                [
                    "#ifdef QJS_PROPERTY_IC",
                    "#define " + name + " (" + str(value + extra) + ")",
                    "#else",
                    "#define " + name + " (" + str(value) + ")",
                    "#endif",
                ]
            )
        else:
            lines.append("#define " + name + " (" + str(value) + ")")
    for name, value in layout["sizes"].items():
        lines.append(
            "_Static_assert(sizeof("
            + name
            + ") == QJS_ABI_SIZE_"
            + name
            + ', "private ABI size: '
            + name
            + '");'
        )
    lines.extend(
        [
            "#ifdef QJS_PROPERTY_IC",
            "_Static_assert(offsetof(JSContext, closure_template_shapes) == "
            + str(layout["sizes"]["JSContext"])
            + ', "Closure templates append after the complete pinned context");',
            "_Static_assert(offsetof(JSContext, closure_template_mode) == "
            + str(layout["sizes"]["JSContext"] + 32)
            + ', "Four owned closure shapes precede mode");',
            "_Static_assert(offsetof(JSContext, internal_function_shape) == "
            + str(layout["sizes"]["JSContext"] + 40)
            + ', "Internal function shape follows closure storage");',
            "_Static_assert(offsetof(JSContext, internal_function_mode) == "
            + str(layout["sizes"]["JSContext"] + 48)
            + ', "Internal function policy follows its owned shape");',
            "_Static_assert(offsetof(JSFunctionBytecode, property_ic) == "
            + str(layout["sizes"]["JSFunctionBytecode"])
            + ', "IC is appended after pinned bytecode fields");',
            "_Static_assert(offsetof(JSRuntime, property_ic_epoch) == "
            + str(layout["sizes"]["JSRuntime"])
            + ', "IC epoch is appended after pinned runtime fields");',
            "_Static_assert(offsetof(JSRuntime, property_ic_list) == "
            + str(layout["sizes"]["JSRuntime"] + 16)
            + ', "IC owner list follows epoch and mode");',
            "#endif",
        ]
    )
    for name, value in layout["offsets"].items():
        typename, field = name.split(".", 1)
        lines.append(
            "_Static_assert(offsetof("
            + typename
            + ", "
            + field
            + ") == "
            + str(value)
            + ', "private ABI offset: '
            + name
            + '");'
        )
    lines += ["#endif", ""]
    return "\n".join(lines)


def assembly_contract(layout, dialect):
    if dialect not in {"gas", "masm"}:
        raise ValueError("Unknown assembler dialect: " + dialect)
    return (
        "\n".join(
            (".equ " + name + ", " + str(value))
            if dialect == "gas"
            else (name + " EQU " + str(value))
            for name, value in constants(layout).items()
        )
        + "\n"
    )


def c_values(layout):
    """Measured constants for opaque-public-API ABI fixtures, without types."""
    lines = [
        "/* Measured private values; source SHA256: " + layout["source_sha256"] + " */",
        "#ifndef QJS_FRAME_PRIVATE_ABI_VALUES_H",
        "#define QJS_FRAME_PRIVATE_ABI_VALUES_H",
    ]
    lines += [
        "#define " + name + " (" + str(value) + ")" for name, value in constants(layout).items()
    ]
    return "\n".join(lines + ["#endif", ""])


def write_contracts(source, directory):
    layout = load(source)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("interpreter-private-abi.h", c_contract(layout)),
        ("interpreter-private-abi-values.h", c_values(layout)),
        ("interpreter-private-abi-gas.inc", assembly_contract(layout, "gas")),
        ("interpreter-private-abi-masm.inc", assembly_contract(layout, "masm")),
    ):
        write_if_changed(directory / name, text)
    return layout


def verify(source, actual):
    expected = load(source)
    differences = []
    for section in (
        "source_sha256",
        "reference_count_model",
        "sizes",
        "offsets",
        "bits",
        "constants",
    ):
        if actual.get(section) == expected[section]:
            continue
        left, right = expected[section], actual.get(section)
        if isinstance(left, dict) and isinstance(right, dict):
            for name in sorted(set(left) | set(right)):
                if left.get(name) != right.get(name):
                    differences.append(
                        {
                            "field": section + "." + name,
                            "expected": left.get(name),
                            "actual": right.get(name),
                        }
                    )
        else:
            differences.append({"field": section, "expected": left, "actual": right})
    return {
        "schema": 1,
        "status": "failed" if differences else "passed",
        "upstream": expected["upstream"],
        "source_sha256": expected["source_sha256"],
        "differences": differences,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.source, json.loads(args.actual.read_text(encoding="utf-8")))
    args.output.mkdir(parents=True, exist_ok=True)
    write_if_changed(
        args.output / "interpreter-private-abi-proof.json", json.dumps(result, indent=2) + "\n"
    )
    if not result["differences"]:
        write_contracts(args.source, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["differences"]))
