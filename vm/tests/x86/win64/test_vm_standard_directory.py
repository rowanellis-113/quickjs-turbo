"""Standard publication must cover native rows without legacy PE table reserves."""

import argparse, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/x86/win64/coff"))
import standard_unwind as U

ap = argparse.ArgumentParser()
ap.add_argument("--build", type=Path, required=True)
ap.add_argument("--image", type=Path, required=True)
ap.add_argument("--archive", type=Path, required=True)
args = ap.parse_args()
raw = args.image.read_bytes()
at = struct.unpack_from("<I", raw, 0x3C)[0]
machine, count, _, symoff, nsyms, opt, _ = struct.unpack_from("<HHIIIHH", raw, at + 4)
assert machine == 0x8664
op = at + 24
assert struct.unpack_from("<H", raw, op)[0] == 0x20B
sections = []
for i in range(count):
    off = op + opt + 40 * i
    name = raw[off : off + 8].split(b"\0")[0].decode("ascii")
    vsize, rva, rsize, ptr = struct.unpack_from("<IIII", raw, off + 8)
    flags = struct.unpack_from("<I", raw, off + 36)[0]
    sections.append(
        dict(
            name=name, rva=rva, size=vsize, rawsize=rsize, flags=flags, data=raw[ptr : ptr + rsize]
        )
    )


def data_at(rva, size):
    sec = next(s for s in sections if s["rva"] <= rva and rva + size <= s["rva"] + s["rawsize"])
    return sec["data"][rva - sec["rva"] : rva - sec["rva"] + size]


drva, dsize = struct.unpack_from("<II", raw, op + 112 + 3 * 8)
assert dsize and dsize % 12 == 0
assert (
    next(
        s["name"] for s in sections if s["rva"] <= drva and drva + dsize <= s["rva"] + s["rawsize"]
    )
    == ".pdata"
)
previous = 0
for i in range(0, dsize, 12):
    lo, hi, uw = struct.unpack("<III", data_at(drva + i, 12))
    assert previous <= lo < hi and uw > 0
    previous = hi
    assert any(
        s["flags"] & 0x20000000 and s["rva"] <= lo < hi <= s["rva"] + s["size"] for s in sections
    )
    assert data_at(uw, 1)[0] & 7 == 1
strings = symoff + nsyms * 18
symbols = {}
i = 0
while i < nsyms:
    off = symoff + i * 18
    name = raw[off : off + 8]
    if name[:4] == bytes(4):
        pos = strings + struct.unpack_from("<I", name, 4)[0]
        name = raw[pos : raw.index(b"\0", pos)]
    else:
        name = name.split(b"\0")[0]
    value, section, typ, storage, aux = struct.unpack_from("<IhHBB", raw, off + 8)
    if 0 < section <= count:
        symbols[name.decode("utf-8")] = sections[section - 1]["rva"] + value
    elif section == -1:
        symbols[name.decode("utf-8")] = value
    i += 1 + aux
assert symbols["__qjs_native_standard_unwind"] == 1 and symbols["__qjs_keep_legacy_unwind"] == 0
for stem in ("__qjsgl_directory", "__qjsregexp_directory", "__qjsjson_directory"):
    assert symbols[stem + "_begin"] == symbols[stem + "_end"], stem
for name in (".qjscwfn", ".qjssrf", ".qjsmfn"):
    sec = next(s for s in sections if s["name"] == name)
    footer = b"QJSCW_END_v1!!!!"
    data = sec["data"]
    assert data.count(footer) == 1, name
    capacity, version = struct.unpack_from("<II", data, data.index(footer) + 16)
    assert (capacity, version) == (0, 1), (name, capacity, version)
paths = U.inputs(args.build, args.archive)
objects, definitions = U.load(paths)
rows = U.collect_runtime_rows(objects, definitions)
standard = {r["key"] for p in paths for r in rows[p, True]}
private = [r for p in paths for r in rows[p, False]]
assert private and all(r["key"] in standard for r in private)
print(
    "STANDARD_DIRECTORY_OK objects="
    + str(len(paths))
    + " private="
    + str(len(private))
    + " PE_rows="
    + str(dsize // 12)
    + " capacities=0"
)
