"""Publish native runtime-function records through ordinary COFF .pdata.

Research generators keep exact compiler/assembler records in private carriers
to hold an old executable's layout. Production static archives must be usable
by an ordinary linker without editing each consumer's PE exception directory.
Copy only proven ADDR32NB runtime-function triples; retain all old section
payloads, relocations and symbols. Normal linkers then sort/register .pdata.
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
import importlib.util
import json
import os
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "standard_unwind_coff", _frame_tool_path("object-adapter")
)
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
sha = lambda data: hashlib.sha256(data).hexdigest()


def ninja_words(line):
    words, word, pos = [], "", 0
    while pos < len(line):
        ch = line[pos]
        if ch == "$":
            pos += 1
            if pos == len(line) or line[pos] not in "$: ":
                raise RuntimeError("Unsupported variable in native archive input list")
            word += line[pos]
        elif ch.isspace():
            if word:
                words.append(word)
                word = ""
        else:
            word += ch
        pos += 1
    if word:
        words.append(word)
    return words


def inputs(build, archive):
    build, archive = Path(build).resolve(), Path(archive).resolve()
    text = (_frame_build_file(build, "build.ninja")).read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if not line.startswith("build ") or ": " not in line:
            continue
        left, right = line[6:].split(": ", 1)
        try:
            targets = ninja_words(left)
        except RuntimeError:
            # CMake also writes unrelated ${cmake_ninja_workdir} aliases.
            # The actual archive producer has a concrete standalone path.
            continue
        # Ninja tokens are concrete paths, including absolute CMake aliases.
        # They are not logical generator artifact names.
        if any((build / t).resolve() == archive.resolve() for t in targets if t != "|"):
            lines.append(right)
    if len(lines) != 1:
        raise RuntimeError("Cannot locate the native archive rule in the standalone Ninja build")
    tokens = ninja_words(lines[0])[1:]
    paths = []
    for token in tokens:
        if token in ("|", "||"):
            break
        path = (build / token).resolve()
        if path.suffix != ".obj" or not path.is_relative_to(build):
            raise RuntimeError(f"Unexpected native archive input: {path}")
        paths.append(path)
    if not paths or len(paths) != len(set(paths)):
        raise RuntimeError("Empty or duplicate native archive inputs")
    return paths


def section_name(co, index):
    name = co.sections[index - 1]["name"]
    if name.startswith("/"):
        at = int(name[1:])
        name = co.strings[at : co.strings.find(0, at)].decode("ascii")
    return name


def load(paths):
    objects = {p: C.Coff(p.read_bytes()) for p in paths}
    definitions = {}
    for path, co in objects.items():
        for symbol in co.all_symbols.values():
            if symbol["section"] > 0 and symbol["storage"] == 2:
                definitions.setdefault(symbol["name"], []).append((path, symbol))
    return objects, definitions


def resolve(path, co, index, addend, definitions):
    symbol = co.all_symbols[index]
    if symbol["section"] > 0:
        return path, symbol["section"], symbol["value"] + addend
    candidates = definitions.get(symbol["name"], [])
    if len(candidates) == 1:
        target, definition = candidates[0]
        return target, definition["section"], definition["value"] + addend
    return None


def runtime_rows(path, co, objects, definitions, standard):
    for number, record in enumerate(co.section_records, 1):
        is_standard = section_name(co, number).startswith(".pdata")
        if is_standard != standard or record["count"] == 65535:
            continue
        relocations = {}
        for i in range(record["count"]):
            at, symbol, kind = struct.unpack_from("<IIH", co.data, record["reloc"] + i * 10)
            if kind == 3:
                if at in relocations:
                    raise RuntimeError("Duplicate native relocation offset")
                relocations[at] = symbol
        occupied = set()
        for at in sorted(relocations):
            if at in occupied or any(at + d not in relocations for d in (4, 8)):
                continue
            if at + 12 > record["size"]:
                raise RuntimeError("Unwind fields outside their input section")
            data = bytes(co.data[record["raw"] + at : record["raw"] + at + 12])
            addends = struct.unpack("<iii", data)
            fields = [
                resolve(path, co, relocations[at + 4 * i], addends[i], definitions)
                for i in range(3)
            ]
            if any(x is None for x in fields):
                continue
            begin, end, unwind = fields
            if begin[:2] != end[:2] or not 0 <= begin[2] < end[2]:
                continue
            code = objects[begin[0]].section_records[begin[1] - 1]
            if not code["flags"] & 0x20000000 or end[2] > code["size"]:
                continue
            target = objects[unwind[0]]
            info = target.section_records[unwind[1] - 1]
            offset = unwind[2]
            if not info["raw"] or not 0 <= offset <= info["size"] - 4:
                continue
            header, prolog, count, frame = target.data[
                info["raw"] + offset : info["raw"] + offset + 4
            ]
            if header & 7 != 1 or header >> 3 not in (0, 1, 2, 3, 4):
                continue
            info_bytes = 4 + ((count + 1) // 2) * 4 + (12 if header >> 3 == 4 else 0)
            if offset + info_bytes > info["size"]:
                continue
            occupied.update((at, at + 4, at + 8))
            yield dict(
                key=tuple(fields),
                data=data,
                origin=path,
                code_comdat=bool(code["flags"] & 0x1000),
                symbols=tuple(relocations[at + 4 * i] for i in range(3)),
                section=number,
                offset=at,
                chained_record=(unwind[0], unwind[1], offset + 4 + ((count + 1) // 2) * 4)
                if header >> 3 == 4
                else None,
            )


def collect_runtime_rows(objects, definitions):
    candidates = {
        (path, standard): list(runtime_rows(path, co, objects, definitions, standard))
        for path, co in objects.items()
        for standard in (True, False)
    }
    chained = {
        row["chained_record"]
        for rows in candidates.values()
        for row in rows
        if row["chained_record"] is not None
    }
    for path, co in objects.items():
        # A compiler can retain an unreferenced chained UNWIND_INFO in a
        # merged object. Its parent triple must still never become a table row.
        starts = {(i, 0) for i, r in enumerate(co.section_records, 1) if r["size"] >= 16}
        functions = {
            (s["section"], s["value"])
            for s in co.all_symbols.values()
            if s["section"] > 0 and s["type"] & 32
        }
        starts.difference_update(functions)
        starts.update(
            (s["section"], s["value"])
            for s in co.all_symbols.values()
            if s["section"] > 0
            and not s["type"] & 32
            and ("unwind" in s["name"].lower() or s["name"].startswith(".xdata"))
        )
        for number, offset in starts:
            record = co.section_records[number - 1]
            if not record["raw"] or not 0 <= offset <= record["size"] - 16:
                continue
            header, prolog, count, frame = co.data[
                record["raw"] + offset : record["raw"] + offset + 4
            ]
            tail = offset + 4 + ((count + 1) // 2) * 4
            relocations = [
                struct.unpack_from("<I", co.data, record["reloc"] + i * 10)[0]
                for i in range(record["count"])
            ]
            if (
                header == 0x21
                and tail + 12 <= record["size"]
                and not any(offset <= at < tail for at in relocations)
            ):
                chained.add((path, number, tail))
    # An embedded CHAININFO parent triple is not an independently published
    # function range. In particular its EndAddress may be only a prologue end,
    # which overlaps the real parent entry and is rejected by MS link.exe.
    return {
        key: [row for row in rows if (key[0], row["section"], row["offset"]) not in chained]
        for key, rows in candidates.items()
    }


def append_pdata(raw, rows):
    before = C.Coff(raw)
    if not rows:
        return raw
    groups = {}
    for row in rows:
        code = row["key"][0]
        groups.setdefault(code[:2], []).append(row)
    groups = list(groups.items())
    if before.stride == 18 and before.count + len(groups) >= 32767:
        raise RuntimeError("Ordinary COFF section limit exceeded")
    # One contribution per code section, preserving COMDAT association. MS
    # link.exe rejects one unassociated table spanning static COMDAT bases.
    delta = 40 * len(groups)
    at = before.header + before.count * 40
    result = bytearray(raw[:at]) + bytearray(delta) + bytearray(raw[at:])
    if before.header == 56:
        struct.pack_into("<I", result, 44, before.count + len(groups))
    else:
        struct.pack_into("<H", result, 2, before.count + len(groups))
    for record in before.section_records:
        for field in (20, 24, 28):
            value = struct.unpack_from("<I", raw, record["pos"] + field)[0]
            if value:
                struct.pack_into("<I", result, record["pos"] + field, value + delta)
    symbols = bytearray(raw[before.table : before.string_offset])
    for group_index, ((owner, code_section), group) in enumerate(groups):
        if len(group) * 3 >= 65535:
            raise RuntimeError("Native relocation section exceeds ordinary COFF limits")
        group.sort(key=lambda row: row["key"][0][2])
        if any(row["code_comdat"] and owner != row["origin"] for row in group):
            raise RuntimeError(
                "Cross-object COMDAT metadata requires publication in its owning object"
            )
        associated = group[0]["code_comdat"]
        number = before.count + group_index + 1
        result += bytes((-len(result)) % 4)
        data_at = len(result)
        result += b"".join(row["data"] for row in group)
        reloc_at = len(result)
        for i, row in enumerate(group):
            for field, symbol in enumerate(row["symbols"]):
                result += struct.pack("<IIH", i * 12 + field * 4, symbol, 3)
        struct.pack_into(
            "<8sIIIIIIHHI",
            result,
            at + 40 * group_index,
            b".pdata\0\0",
            0,
            0,
            len(group) * 12,
            data_at,
            reloc_at,
            0,
            len(group) * 3,
            0,
            0x40300040 | (0x1000 if associated else 0),
        )
        definition = bytearray(before.stride)
        definition[:8] = b".pdata\0\0"
        struct.pack_into("<i" if before.stride == 20 else "<h", definition, 12, number)
        definition[before.class_offset : before.class_offset + 2] = bytes((3, 1))
        auxiliary = bytearray(before.stride)
        parent_number = code_section if associated else 0
        struct.pack_into(
            "<IHHIHBBH",
            auxiliary,
            0,
            len(group) * 12,
            len(group) * 3,
            0,
            0,
            parent_number & 0xFFFF,
            5 if associated else 0,
            0,
            parent_number >> 16,
        )
        symbols += definition + auxiliary
    result += bytes((-len(result)) % 4)
    symbol_at = len(result)
    result += symbols + before.strings
    struct.pack_into(
        "<II", result, before.table_offset, symbol_at, before.symbol_count + len(groups) * 2
    )
    after = C.Coff(result)
    original_symbols = {i: s for i, s in after.all_symbols.items() if i < before.symbol_count}
    if after.sections[: before.count] != before.sections or original_symbols != before.all_symbols:
        raise RuntimeError("Standard unwind publication changed an original section or symbol")
    return bytes(result)


def restore(paths):
    for path in paths:
        record = path.with_name(path.name + ".standard-unwind.json")
        backup = path.with_name(path.name + ".before-standard-unwind")
        if not record.exists():
            if backup.exists():
                raise RuntimeError("Unwind backup without provenance")
            continue
        receipt = json.loads(record.read_text(encoding="utf-8"))
        if (
            sha(backup.read_bytes()) != receipt["before_sha256"]
            or sha(path.read_bytes()) != receipt["after_sha256"]
        ):
            raise RuntimeError(f"Unknown native publication endpoint: {path}")
        stamp = path.stat()
        path.write_bytes(backup.read_bytes())
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        backup.unlink()
        record.unlink()


def publish(paths, report, dry_run=False):
    if not dry_run and any(p.with_name(p.name + ".standard-unwind.json").exists() for p in paths):
        raise RuntimeError("Restore the previous standard-unwind publication before replay")
    objects, definitions = load(paths)
    candidates = collect_runtime_rows(objects, definitions)
    seen = set()
    for path, co in objects.items():
        seen.update(row["key"] for row in candidates[path, True])
    rows_by_path = {}
    for path, co in objects.items():
        for row in candidates[path, False]:
            if row["key"] not in seen:
                rows_by_path.setdefault(path, []).append(row)
                seen.add(row["key"])
    records = []
    for path, rows in rows_by_path.items():
        raw = bytes(objects[path].data)
        output = append_pdata(raw, rows)
        if dry_run:
            print(path.name, "PROVEN_EXTRA_RUNTIME_FUNCTIONS", len(rows))
            continue
        backup = path.with_name(path.name + ".before-standard-unwind")
        record = path.with_name(path.name + ".standard-unwind.json")
        if backup.exists() or record.exists():
            raise RuntimeError("Native unwind publication must begin from a restored object")
        proof = dict(
            schema=1,
            path=str(path),
            before_sha256=sha(raw),
            after_sha256=sha(output),
            added_rows=len(rows),
            sources=[dict(section=r["section"], offset=r["offset"]) for r in rows],
            original_payloads_relocations_symbols_unchanged=True,
        )
        stamp = path.stat()
        backup.write_bytes(raw)
        path.write_bytes(output)
        # This is a pre-archive view of a compiler output, not a new producer.
        # A newer timestamp would dirty upstream generator dependencies on the
        # next no-op build and replay them against an already adapted object.
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        record.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        records.append(proof)
    if dry_run:
        return
    report.write_text(
        json.dumps(
            dict(
                status="passed",
                schema=1,
                objects=records,
                total_added_rows=sum(r["added_rows"] for r in records),
                scope="Typed native records copied into ordinary .pdata; no PE post-link mutation is required.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("FRAME_STANDARD_UNWIND_PUBLISHED", sum(len(r) for r in rows_by_path.values()), "rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    build = args.build.resolve()
    paths = inputs(build, args.archive)
    if args.restore:
        restore(paths)
    else:
        publish(paths, _frame_build_file(build, "interpreter-standard-unwind.json"), args.dry_run)
