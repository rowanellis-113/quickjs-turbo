"""Read-only validation of the ordinary PE exception directory and ASLR flags."""

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
from pathlib import Path
import struct


def validate(path):
    raw = path.read_bytes()
    pe = struct.unpack_from("<I", raw, 60)[0]
    if raw[:2] != b"MZ" or raw[pe : pe + 4] != b"PE\0\0":
        raise ValueError("Not a PE image")
    machine, count = struct.unpack_from("<HH", raw, pe + 4)
    optional = pe + 24
    if machine != 0x8664 or struct.unpack_from("<H", raw, optional)[0] != 0x20B:
        raise ValueError("Expected a Windows x86-64 PE32+ image")
    flags = struct.unpack_from("<H", raw, optional + 70)[0]
    if flags & 0x140 != 0x140:
        raise ValueError("Expected normal DYNAMICBASE and NXCOMPAT flags")
    at = optional + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(count):
        pos = at + 40 * i
        name = raw[pos : pos + 8].split(b"\0")[0].decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, pos + 8)
        attributes = struct.unpack_from("<I", raw, pos + 36)[0]
        sections.append(
            dict(
                name=name,
                rva=rva,
                size=size,
                physical_size=physical_size,
                physical=physical,
                flags=attributes,
            )
        )
    headers = struct.unpack_from("<I", raw, optional + 60)[0]
    first_rva = min(s["rva"] for s in sections)
    if not at + 40 * count <= headers <= first_rva or headers > len(raw):
        raise ValueError(
            f"PE headers overlap the first mapped section:headers={headers:#x},firstRVA={first_rva:#x},sections={count};reuse existing output groups"
        )

    def locate(rva, size):
        found = [
            s for s in sections if s["rva"] <= rva and rva + size <= s["rva"] + s["physical_size"]
        ]
        if len(found) != 1:
            raise ValueError(f"RVA outside one mapped section: {rva:#x}, {size}")
        s = found[0]
        return s["physical"] + rva - s["rva"], s

    directory, size = struct.unpack_from("<II", raw, optional + 112 + 3 * 8)
    if not size or size % 12:
        raise ValueError("Missing or malformed exception directory")
    offset, carrier = locate(directory, size)
    if carrier["name"] != ".pdata" or carrier["flags"] & 0x80000000:
        raise ValueError("Native production image must use ordinary readonly .pdata")
    previous_end = 0
    for at in range(offset, offset + size, 12):
        begin, end, unwind = struct.unpack_from("<III", raw, at)
        if not previous_end <= begin < end:
            raise ValueError(
                f"Unsorted or overlapping native range: {begin:#x}..{end:#x}, previous {previous_end:#x}"
            )
        _, code = locate(begin, end - begin)
        if not code["flags"] & 0x20000000:
            raise ValueError("Runtime-function range is not executable")
        info, _ = locate(unwind, 4)
        if (raw[info] & 7) not in (1, 2):
            raise ValueError("Unsupported or invalid unwind-info version")
        previous_end = end
    reloc_rva, reloc_size = struct.unpack_from("<II", raw, optional + 112 + 5 * 8)
    if not reloc_rva or not reloc_size:
        raise ValueError("Expected normal PE base relocations")
    return dict(
        status="passed",
        image=str(path),
        image_sha256=hashlib.sha256(raw).hexdigest(),
        runtime_functions=size // 12,
        exception_section=carrier["name"],
        dynamicbase=True,
        nxcompat=True,
        base_relocations_bytes=reloc_size,
        scope="Read-only structural check; instruction-level unwind is tested by native ABI hosts.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("images", type=Path, nargs="+")
    args = parser.parse_args()
    for image in args.images:
        print(json.dumps(validate(image), sort_keys=True))
