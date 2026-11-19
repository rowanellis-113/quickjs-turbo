"""Verify the GNU Win64 append islands with the actual Windows unwinder.

Decode the linked image, reject unknown instructions and query every genuine
instruction boundary. No JavaScript or instruction in the image is executed.
"""

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


def image_symbols(data):
    pe = struct.unpack_from("<I", data, 60)[0]
    assert data[pe : pe + 4] == b"PE\0\0"
    hdr = pe + 4
    count = struct.unpack_from("<H", data, hdr + 2)[0]
    table, symbols = struct.unpack_from("<II", data, hdr + 8)
    optional = struct.unpack_from("<H", data, hdr + 16)[0]
    assert struct.unpack_from("<H", data, hdr + 20)[0] == 0x20B
    base = struct.unpack_from("<Q", data, hdr + 44)[0]
    strings = table + symbols * 18

    def name(raw):
        if raw[:4] == bytes(4):
            off = strings + struct.unpack_from("<I", raw, 4)[0]
            return data[off : data.index(0, off)].decode()
        return raw.rstrip(b"\0").decode()

    sections = []
    for i in range(count):
        off = hdr + 20 + optional + 40 * i
        sections.append(
            (
                struct.unpack_from("<I", data, off + 12)[0],
                struct.unpack_from("<I", data, off + 36)[0],
            )
        )
    found = {}
    i = 0
    while i < symbols:
        off = table + 18 * i
        value, section, _, _, aux = struct.unpack_from("<IhHBB", data, off + 8)
        key = name(data[off : off + 8])
        if section > 0 and key.startswith("JS_FrameNativeRopeAppend"):
            rva, flags = sections[section - 1]
            assert flags & 0x20000000 and key not in found
            found[key] = rva + value
        i += 1 + aux
    return base, found


class RuntimeFunction(C.Structure):
    _fields_ = [("begin", C.c_uint32), ("end", C.c_uint32), ("unwind", C.c_uint32)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    data = a.image.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    image_base, symbols = image_symbols(data)
    result = dict(status="running", image=str(a.image.resolve()), sha256=digest, checks=[])

    def save():
        if a.report:
            a.report.parent.mkdir(parents=True, exist_ok=True)
            a.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    k = C.WinDLL("kernel32", use_last_error=True)
    n = C.WinDLL("ntdll")
    k.SetErrorMode(0x8003)
    k.LoadLibraryExW.argtypes = [C.c_wchar_p, C.c_void_p, C.c_uint32]
    k.LoadLibraryExW.restype = C.c_void_p
    k.FreeLibrary.argtypes = [C.c_void_p]
    n.RtlLookupFunctionEntry.argtypes = [C.c_uint64, C.POINTER(C.c_uint64), C.c_void_p]
    n.RtlLookupFunctionEntry.restype = C.POINTER(RuntimeFunction)
    n.RtlVirtualUnwind.argtypes = [
        C.c_uint32,
        C.c_uint64,
        C.c_uint64,
        C.POINTER(RuntimeFunction),
        C.c_void_p,
        C.POINTER(C.c_void_p),
        C.POINTER(C.c_uint64),
        C.c_void_p,
    ]
    n.RtlVirtualUnwind.restype = C.c_void_p
    registers = [
        "rax",
        "rcx",
        "rdx",
        "rbx",
        "rsp",
        "rbp",
        "rsi",
        "rdi",
        "r8",
        "r9",
        "r10",
        "r11",
        "r12",
        "r13",
        "r14",
        "r15",
        "rip",
    ]
    offsets = {name: 120 + 8 * i for i, name in enumerate(registers)}
    saved = ["r15", "r14", "r13", "r12", "rdi", "rsi", "rbp", "rbx"]
    allowed = {
        "cmp",
        "jne",
        "je",
        "jbe",
        "ja",
        "jae",
        "jb",
        "jle",
        "mov",
        "movzx",
        "movsxd",
        "lea",
        "test",
        "and",
        "add",
        "sub",
        "inc",
        "dec",
        "shl",
        "jmp",
    }
    module = k.LoadLibraryExW(str(a.image.resolve()), None, 1)
    assert module, C.get_last_error()
    try:
        for family in ["Clean", "Dirty"]:
            name = "JS_FrameNativeRopeAppend" + family
            start, end = symbols[name], symbols[name + "_end"]
            assert end > start
            cmd = [
                a.objdump,
                "-d",
                "-w",
                "-Mintel",
                "--start-address=" + hex(image_base + start),
                "--stop-address=" + hex(image_base + end),
                str(a.image),
            ]
            decoded = subprocess.run(cmd, capture_output=True, check=True).stdout.decode()
            instructions = []
            for line in decoded.splitlines():
                m = re.match(r"\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)\s*(.+)", line)
                if m:
                    instructions.append(
                        dict(rva=int(m[1], 16) - image_base, bytes=len(m[2].split()), text=m[3])
                    )
            assert instructions and instructions[0]["rva"] == start
            assert instructions[-1]["rva"] + instructions[-1]["bytes"] == end
            assert all(
                x["rva"] + x["bytes"] == y["rva"] for x, y in zip(instructions, instructions[1:])
            )
            for ins in instructions:
                assert ins["text"].split()[0] in allowed, ins
                assert not re.search(r"\b(?:rsp|esp)\b", ins["text"]), ins
            base = C.c_uint64()
            row = n.RtlLookupFunctionEntry(module + start, C.byref(base), None)
            assert row and base.value == module
            assert (row.contents.begin, row.contents.end) == (start, end)
            info = module + row.contents.unwind
            assert C.string_at(info, 4) == b"\x21\0\0\0"
            parent = RuntimeFunction.from_address(info + 4)
            assert C.string_at(module + parent.begin, 16) == bytes.fromhex(
                "5355565741544155415641574883ec48"
            )
            actual = n.RtlLookupFunctionEntry(module + parent.begin, C.byref(base), None)
            assert actual and C.string_at(actual, 12) == C.string_at(C.addressof(parent), 12)
            stack = C.create_string_buffer(8 * 40 + 15)
            sp = (C.addressof(stack) + 15) & ~15
            expected = {reg: 0x11000000 + 0x101 * i for i, reg in enumerate(saved)}
            for i, reg in enumerate(saved):
                C.c_uint64.from_address(sp + (9 + i) * 8).value = expected[reg]
            ret = 0x123456789
            C.c_uint64.from_address(sp + 136).value = ret
            for ins in instructions:
                observed = n.RtlLookupFunctionEntry(module + ins["rva"], C.byref(base), None)
                assert observed and C.addressof(observed.contents) == C.addressof(row.contents)
                raw = C.create_string_buffer(1232 + 15)
                ctx = (C.addressof(raw) + 15) & ~15
                C.memset(ctx, 0, 1232)
                C.c_uint32.from_address(ctx + 48).value = 0x100003
                for reg in saved:
                    C.c_uint64.from_address(ctx + offsets[reg]).value = 0x55000000 + offsets[reg]
                C.c_uint64.from_address(ctx + offsets["rsp"]).value = sp
                C.c_uint64.from_address(ctx + offsets["rip"]).value = module + ins["rva"]
                handler, frame = C.c_void_p(), C.c_uint64()
                assert not n.RtlVirtualUnwind(
                    0,
                    module,
                    module + ins["rva"],
                    observed,
                    ctx,
                    C.byref(handler),
                    C.byref(frame),
                    None,
                )
                assert frame.value == sp, ins
                assert C.c_uint64.from_address(ctx + offsets["rsp"]).value == sp + 144, ins
                assert C.c_uint64.from_address(ctx + offsets["rip"]).value == ret, ins
                assert all(
                    C.c_uint64.from_address(ctx + offsets[reg]).value == value
                    for reg, value in expected.items()
                ), ins
            result["checks"].append(dict(name=name, instructions=instructions))
            save()
    finally:
        k.FreeLibrary(module)
    assert hashlib.sha256(a.image.read_bytes()).hexdigest() == digest
    result["status"] = "passed"
    save()
    print(
        "Native rope unwind passed:",
        [(x["name"], len(x["instructions"])) for x in result["checks"]],
    )


if __name__ == "__main__":
    main()
