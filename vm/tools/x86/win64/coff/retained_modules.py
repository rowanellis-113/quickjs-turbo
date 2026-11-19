"""Compile-time integration of the accepted retained native source bundle.

The bundle contains C/assembly and guarded relocation/operand descriptions.
No historical object, archive, executable or experiment directory is read.
"""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

import call_env_adapter as E
import standard_unwind as U
from abi_layout import load as load_layout


def capture(build, archive):
    """Shield the new source modules from the older whole-archive adapters."""
    build = build.resolve()
    folder = _frame_generated_file(build, "quickjs-retained-pristine")
    folder.mkdir()
    manifest = json.loads(
        (_frame_project_root() / "src/x86/win64/backend.json").read_text(encoding="utf-8")
    )
    members = {
        (_frame_build_file(build, spec["object"])).resolve()
        for backend in manifest["toolchains"].values()
        for spec in backend["modules"]
    }
    rows = []
    for path in U.inputs(build, archive):
        if path.resolve() in members:
            data, stamp = path.read_bytes(), path.stat()
            name = str(len(rows)) + ".bin"
            (folder / name).write_bytes(data)
            rows.append(
                dict(
                    path=path.relative_to(build).as_posix(),
                    backup=name,
                    sha256=hashlib.sha256(data).hexdigest(),
                    atime_ns=stamp.st_atime_ns,
                    mtime_ns=stamp.st_mtime_ns,
                )
            )
    (folder / "inputs.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print("RETAINED_COMPILER_INPUTS_CAPTURED", len(rows))


def restore(build, paths):
    folder = _frame_generated_file(build, "quickjs-retained-pristine")
    allowed = {path.resolve() for path in paths}
    for row in json.loads((folder / "inputs.json").read_text(encoding="utf-8")):
        path = (_frame_build_file(build, row["path"])).resolve()
        if path not in allowed:
            raise RuntimeError("Retained compiler input is no longer in this archive: " + str(path))
        data = (folder / row["backup"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RuntimeError("Retained compiler input backup changed: " + str(path))
        path.write_bytes(data)
        os.utime(path, ns=(row["atime_ns"], row["mtime_ns"]))


def section_name(co, number):
    value = co.sections[number - 1]["name"]
    return co.strings[int(value[1:]) :].split(b"\0")[0].decode() if value.startswith("/") else value


def rename(co, index, value):
    at = len(co.strings)
    co.strings += value.encode() + b"\0"
    struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
    co.all_symbols[index]["name"] = value


def defined_alias(co, name, section, value, typ=0):
    index = co.external(name)
    symbol = co.aliases[-1]
    struct.pack_into("<I", symbol, 8, value)
    struct.pack_into("<i" if co.stride == 20 else "<h", symbol, 12, section)
    struct.pack_into("<H", symbol, 16 if co.stride == 20 else 14, typ)
    return index


def runtime_common(symbol):
    # UCRT inline accessors emit these program-wide options as eight-byte
    # COMMON definitions in C. Keep the linker coalescing contract; they are
    # not private QJS storage or an unresolved retained ABI dependency.
    return (
        symbol["storage"] == 2
        and symbol["section"] == 0
        and symbol["value"] == 8
        and symbol["type"] == 0
        and symbol["name"]
        in {
            "?_OptionsStorage@?1??__local_stdio_printf_options@@9@9",
            "?_OptionsStorage@?1??__local_stdio_scanf_options@@9@9",
        }
    )


def normalize_module(path, spec, providers):
    packed, _ = E.module("call-metadata").packed(path.read_bytes(), U.C)
    co = U.C.Coff(packed)
    exports = set(spec["exports"])
    changes = []
    compiler_common = []
    for index, symbol in co.all_symbols.items():
        if symbol["storage"] != 2:
            continue
        if symbol["name"].startswith(".refptr."):
            continue
        if symbol["section"] > 0 and symbol["name"] not in exports:
            old = symbol["name"]
            value = "retained_" + spec["id"] + "_" + hashlib.sha256(old.encode()).hexdigest()[:24]
            rename(co, index, value)
            changes.append(dict(kind="private", old=old, new=value))
        elif symbol["section"] == 0 and symbol["value"]:
            if runtime_common(symbol):
                compiler_common.append(dict(name=symbol["name"], size=symbol["value"]))
                continue
            if symbol["name"] not in providers:
                raise RuntimeError("Unbound retained tentative definition: " + symbol["name"])
            struct.pack_into("<I", co.data, co.table + index * co.stride + 8, 0)
    source_aliases = []
    for alias in spec.get("symbol_aliases", []):
        found = [
            s for s in co.all_symbols.values() if s["name"] == alias["source"] and s["section"] > 0
        ]
        if len(found) != 1 or not (found[0]["type"] & 32):
            raise RuntimeError("Need one original typed helper: " + alias["source"])
        symbol = found[0]
        if not co.section_records[symbol["section"] - 1]["flags"] & 0x20000000:
            raise RuntimeError("Original helper is not code: " + alias["source"])
        if any(s["name"] == alias["name"] for s in co.all_symbols.values()):
            raise RuntimeError("Helper alias name is already occupied: " + alias["name"])
        defined_alias(co, alias["name"], symbol["section"], symbol["value"], 32)
        source_aliases.append(
            dict(
                name=alias["name"],
                original=alias["source"],
                section=symbol["section"],
                value=symbol["value"],
            )
        )
    standard_readonly = set(spec.get("standard_readonly_sections", []))
    if standard_readonly and (
        spec["id"] != "cvm_segments" or standard_readonly != {".rdata$cvm_segments"}
    ):
        raise RuntimeError("Unknown standard readonly source-module section")
    standard_records = []
    # All appended code/data have semantic protection groups. Compiler .pdata
    # remains ordinary and follows its owning code's COMDAT association.
    for number, record in enumerate(co.section_records, 1):
        old = section_name(co, number)
        if old in standard_readonly:
            if (
                record["flags"] & 0xE00000E0 != 0x40000040
                or record["size"] != 2048
                or record["count"] != 256
            ):
                raise RuntimeError("Native dispatch must be one ordinary readonly pointer table")
            positions = []
            for at in range(record["reloc"], record["reloc"] + 10 * record["count"], 10):
                offset, index, kind = struct.unpack_from("<IIH", co.data, at)
                symbol = co.all_symbols[index]
                if kind != 1 or symbol["section"] <= 0:
                    raise RuntimeError("Native dispatch needs an exact own-code ADDR64 target")
                target = co.section_records[symbol["section"] - 1]
                addend = struct.unpack_from("<Q", co.data, record["raw"] + offset)[0]
                if (
                    not target["flags"] & 0x20000000
                    or not 0 <= symbol["value"] + addend < target["size"]
                ):
                    raise RuntimeError("Native dispatch target lies outside its code")
                positions.append(offset)
            if positions != list(range(0, 2048, 8)):
                raise RuntimeError("Native dispatch pointer coverage differs")
            standard_records.append(
                dict(
                    section=old,
                    entries=256,
                    entry_bytes=8,
                    relocation="ADDR64",
                    policy="Ordinary .rdata placement with complete PE loader fixups; no extension merge",
                )
            )
            continue
        if (
            not record["flags"] & 0xE0000000
            or record["flags"] & 0x200
            or old.startswith((".pdata", ".debug", ".drectve", ".llvm"))
            or ".refptr." in old
        ):
            continue
        new = (
            ".qjsex$C"
            if record["flags"] & 0x20000000
            else ".qjsem$C"
            if record["flags"] & 0x80000000
            else ".qjser$C"
        )
        at = len(co.strings)
        co.strings += new.encode() + b"\0"
        co.data[record["pos"] : record["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
        for index, symbol in co.all_symbols.items():
            if (
                symbol["section"] == number
                and symbol["storage"] == 3
                and symbol["type"] == 0
                and symbol["name"] == old
            ):
                struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
    for mode in spec["modes"]:
        symbol = next(
            (s for s in co.all_symbols.values() if s["section"] > 0 and s["name"] == mode["name"]),
            None,
        )
        if not symbol:
            continue
        section = co.section_records[symbol["section"] - 1]
        value = bytes.fromhex(mode["bytes"])
        if not section["raw"]:
            if any(value):
                raise RuntimeError("Retained mode needs initialized storage: " + mode["name"])
            continue
        co.data[
            section["raw"] + symbol["value"] : section["raw"] + symbol["value"] + len(value)
        ] = value
    required = set(spec.get("required_imports", []))
    referenced = set()
    for section in co.section_records:
        if not section["flags"] & 0x20000000:
            continue
        for at in range(section["reloc"], section["reloc"] + 10 * section["count"], 10):
            index = struct.unpack_from("<I", co.data, at + 4)[0]
            referenced.add(co.all_symbols[index]["name"])
    if required - referenced:
        raise RuntimeError(
            "Missing accepted module call route: " + ", ".join(sorted(required - referenced))
        )
    if len(standard_records) != len(standard_readonly):
        raise RuntimeError("Declared ordinary readonly section was not found")
    path.write_bytes(co.finish())
    return dict(
        path=str(path),
        module=spec["id"],
        private_definitions=changes,
        standard_readonly_sections=standard_records,
        compiler_common=compiler_common,
        source_aliases=source_aliases,
        required_imports_verified=sorted(required),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def route_object(path, recipe):
    packed, _ = E.module("call-metadata").packed(path.read_bytes(), U.C)
    co = U.C.Coff(packed)
    aliases = {}
    operations = []
    # Existing source definitions keep their bodies and are given the retained
    # names (notably the four legacy serialization roots).
    for change in recipe["renames"]:
        old, new = change["before"], change["after"]
        matches = [
            (i, s)
            for i, s in co.all_symbols.items()
            if s["name"] == old["name"]
            and s["section"] == old["section"]
            and s["value"] == old["value"]
        ]
        if not matches:
            if any(
                s["name"] == new["name"]
                and s["section"] == new["section"]
                and s["value"] == new["value"]
                for s in co.all_symbols.values()
            ):
                continue
            raise RuntimeError("Missing retained definition: " + old["name"] + " in " + str(path))
        for index, symbol in matches:
            rename(co, index, new["name"])
            co.data[co.table + index * co.stride + co.class_offset] = new["storage"]
        operations.append(dict(kind="rename", old=old["name"], new=new["name"]))
    for symbol in recipe["aliases"]:
        if symbol["name"] in aliases:
            continue
        present = next(
            (
                i
                for i, s in co.all_symbols.items()
                if s["storage"] == 2
                and s["name"] == symbol["name"]
                and s["section"] == symbol["section"]
                and s["value"] == symbol["value"]
            ),
            None,
        )
        aliases[symbol["name"]] = (
            present
            if present is not None
            else defined_alias(
                co, symbol["name"], symbol["section"], symbol["value"], symbol["type"]
            )
        )

    def target(symbol):
        name = symbol["name"]
        if symbol["section"] > recipe["original_sections"]:
            if name.startswith("."):
                raise RuntimeError(
                    "New retained section reference needs a named source export: " + name
                )
            return co.external(name)
        if symbol["section"] > 0:
            if name in aliases:
                return aliases[name]
            found = next(
                (
                    i
                    for i, s in co.all_symbols.items()
                    if s["name"] == name
                    and s["section"] == symbol["section"]
                    and s["value"] == symbol["value"]
                ),
                None,
            )
            if found is None:
                found = defined_alias(co, name, symbol["section"], symbol["value"], symbol["type"])
            return found
        return co.external(name)

    for change in recipe["changes"]:
        number = change["section"]
        section = co.section_records[number - 1]
        if (section_name(co, number), section["size"], section["flags"]) != (
            change["name"],
            change["size"],
            change["flags"],
        ):
            raise RuntimeError(f"Retained ABI/code shape changed: {path.name} section {number}")
        for patch in change["patches"]:
            old, new = bytes.fromhex(patch["before"]), bytes.fromhex(patch["after"])
            at = section["raw"] + patch["offset"]
            actual = bytes(co.data[at : at + len(old)])
            if actual not in (old, new):
                raise RuntimeError(
                    f"Retained operand changed: {path.name} section {number} +{patch['offset']}"
                )
            co.data[at : at + len(new)] = new
        existing = {
            struct.unpack_from("<I", co.data, section["reloc"] + 10 * j)[0]: section["reloc"]
            + 10 * j
            for j in range(section["count"])
        }
        for relocation in change["relocations"]:
            offset = relocation["offset"]
            after = relocation["after"]
            index = target(after["symbol"])
            if offset in existing:
                at = existing[offset]
                struct.pack_into("<IH", co.data, at + 4, index, after["kind"])
            else:
                co.extra_relocations.setdefault(number, []).append(
                    struct.pack("<IIH", offset, index, after["kind"])
                )
        operations.append(
            dict(
                kind="section_routes",
                section=number,
                operands=len(change["patches"]),
                relocations=len(change["relocations"]),
            )
        )
    path.write_bytes(co.finish())
    return dict(
        path=str(path), operations=operations, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )


def integrate(source, build, archive, toolchain):
    source, build = source.resolve(), build.resolve()
    manifest = json.loads((source / "src/x86/win64/backend.json").read_text(encoding="utf-8"))
    if manifest.get("schema") not in (1, 2) or (
        manifest["schema"] == 2 and manifest.get("route_model") != "live-symbols-v1"
    ):
        raise RuntimeError("Unknown retained route contract")
    if manifest.get("schema") == 2 and manifest.get("route_model") != "live-symbols-v1":
        raise RuntimeError("Unknown retained live-route contract")
    for name, digest in manifest["source_pin"].items():
        if hashlib.sha256(_frame_source_text(source, name).encode()).hexdigest() != digest:
            raise RuntimeError(
                "Retained private ABI needs review for changed upstream source: " + name
            )
    selected = manifest["toolchains"][toolchain]
    paths = U.inputs(build, archive)
    restore(build, paths)
    members = {path.relative_to(build).as_posix(): path for path in paths}
    providers = {
        s["name"]
        for path in paths
        for s in U.C.Coff(path.read_bytes()).all_symbols.values()
        if s["storage"] == 2 and s["section"] > 0
    }
    rows = []
    stamps = {path: path.stat() for path in paths}
    for spec in selected["modules"]:
        member = spec["object"]
        if member not in members:
            raise RuntimeError("Missing source-compiled retained member: " + member)
        rows.append(normalize_module(members[member], spec, providers))
    current_layout = load_layout(source)
    if manifest.get("schema") == 2 and current_layout["reference_count_model"] != "inline-header":
        raise RuntimeError("Live-route bundle requires review for the changed reference-count ABI")
    required = {
        s["name"]
        for path in paths
        for s in U.C.Coff(path.read_bytes()).all_symbols.values()
        if s["storage"] == 2 and s["section"] == 0 and not s["value"]
    }
    for recipe in selected["routes"]:
        path = members[recipe["object_path"]]
        if current_layout["reference_count_model"] == "inline-header":
            import retained_routes

            rows.append(retained_routes.route(source, build, path, recipe, toolchain, required))
        else:
            rows.append(route_object(path, recipe))
    # Compiler timestamps belong to Ninja; the enclosing stage seals hashes.
    for path, stamp in stamps.items():
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (_frame_generated_file(build, "quickjs-retained-integration.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                toolchain=toolchain,
                source_modules=len(selected["modules"]),
                root_objects=len(selected["routes"]),
                records=rows,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "RETAINED_SOURCE_INTEGRATED",
        toolchain,
        len(selected["modules"]),
        "modules;",
        len(selected["routes"]),
        "root objects",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--toolchain", choices=("msvc", "mingw"))
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if args.capture:
        capture(args.build, args.archive)
    elif args.source and args.toolchain:
        integrate(args.source, args.build, args.archive, args.toolchain)
    else:
        parser.error("Supply --capture or --source and --toolchain")
