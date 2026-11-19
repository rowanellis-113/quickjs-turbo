"""Exact private function shape with reviewed symbolic local fixups.

This does not infer an ABI. Callers supply their pinned source/type contracts,
whole-code fingerprints and exact reviewed instruction offsets/target functions.
Only the displacement of an admitted CALL/JMP or RIP-relative function LEA is
normalized; changing the opcode/register/target/other bytes rejects the shape.
"""

import hashlib
import struct


def fingerprint(co, name, transfers=(), addresses=(), allowed_relocations=tuple(range(1, 10))):
    symbol = co.symbols.get(name)
    if not symbol or symbol["section"] <= 0:
        return None
    sn, begin = symbol["section"], symbol["value"]
    section = co.section_records[sn - 1]
    ends = [
        s["value"]
        for s in co.all_symbols.values()
        if s["section"] == sn and s["type"] & 32 and s["value"] > begin
    ]
    end = min(ends, default=section["size"])
    data = bytearray(co.data[section["raw"] + begin : section["raw"] + end])
    relocations = []
    occupied = set()
    for at in co.relocation_positions(sn):
        offset, index, kind = struct.unpack_from("<IIH", co.data, at)
        if begin <= offset < end:
            if kind not in allowed_relocations:
                return None
            width = 8 if kind == 1 else 4
            offset -= begin
            if offset + width > len(data):
                return None
            data[offset : offset + width] = bytes(width)
            occupied.update(range(offset, offset + width))
            relocations.append([offset, kind, co.all_symbols[index]["name"]])
    for site in transfers:
        offset = site["offset"]
        target = co.symbols.get(site["target"])
        span = set(range(offset + 1, offset + 5))
        if (
            not target
            or offset < 0
            or offset + 5 > len(data)
            or site["opcode"] not in (0xE8, 0xE9)
            or data[offset] != site["opcode"]
            or target["section"] != sn
            or span & occupied
        ):
            return None
        if begin + offset + 5 + struct.unpack_from("<i", data, offset + 1)[0] != target["value"]:
            return None
        data[offset + 1 : offset + 5] = bytes(4)
        occupied.update(span)
    for site in addresses:
        offset = site["offset"]
        target = co.symbols.get(site["target"])
        span = set(range(offset + 3, offset + 7))
        if (
            not target
            or offset < 0
            or offset + 7 > len(data)
            or target["section"] != sn
            or span & occupied
        ):
            return None
        prefix = bytes(data[offset : offset + 3])
        if (
            prefix.hex() != site["prefix"]
            or prefix[0] not in (0x48, 0x4C)
            or prefix[1] != 0x8D
            or prefix[2] & 0xC7 != 5
        ):
            return None
        if begin + offset + 7 + struct.unpack_from("<i", data, offset + 3)[0] != target["value"]:
            return None
        data[offset + 3 : offset + 7] = bytes(4)
        occupied.update(span)
    return dict(
        size=end - begin,
        normalized_code_sha256=hashlib.sha256(data).hexdigest(),
        relocations=relocations,
        local_transfers=list(transfers),
        local_addresses=list(addresses),
    )
