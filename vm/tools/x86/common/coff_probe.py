"""Shared x86 COFF reader and pure-C regex re-exports."""

import sys as _coff_sys
from pathlib import Path as _CoffPath

_coff_tools_root = str(_CoffPath(__file__).resolve().parents[2])
if _coff_tools_root not in _coff_sys.path:
    _coff_sys.path.insert(0, _coff_tools_root)

import hashlib
import struct

from common.c_extract.object_adapter_c import (  # noqa: F401
    BIGINT_ISLAND_HELPERS,
    FUNCTION,
    HOT_LOCAL_HELPERS,
    MACRO,
    identifiers,
)


def relocation_layout(data, pointer, count, flags):
    """Return logical records and complete storage for COFF's overflow form.

    The first extended record stores the physical count, including itself;
    it is metadata, not a relocation at that section offset. Keep the section
    header representation intact and still reject unsupported code rewrites.
    """
    first, records, storage = pointer, count, count * 10
    if flags & 0x01000000:
        if count != 0xFFFF or not pointer or pointer + 10 > len(data):
            raise RuntimeError("Invalid extended COFF relocation header")
        physical, symbol, kind = struct.unpack_from("<IIH", data, pointer)
        if physical < 0x10000 or symbol or kind:
            raise RuntimeError("Invalid extended COFF relocation count")
        first, records, storage = pointer + 10, physical - 1, physical * 10
    if storage and (not pointer or pointer + storage > len(data)):
        raise RuntimeError("Truncated COFF relocation table")
    return first, records, storage


class Coff:
    """Minimal read-only x64 COFF / bigobj container parser."""

    def __init__(self, data):
        self.data = bytearray(data)
        big = data[:4] == b"\0\0\xff\xff"
        if big:
            if struct.unpack_from("<H", data, 6)[0] != 0x8664:
                raise RuntimeError("Expected an x64 bigobj COFF object")
            self.header, self.stride, self.class_offset = 56, 20, 18
            self.count = struct.unpack_from("<I", data, 44)[0]
            self.table, self.symbol_count = struct.unpack_from("<II", data, 48)
            self.table_offset = 48
        else:
            machine, self.count = struct.unpack_from("<HH", data)
            if machine != 0x8664:
                raise RuntimeError("Expected an x64 COFF object")
            self.header, self.stride, self.class_offset = 20, 18, 16
            self.table, self.symbol_count = struct.unpack_from("<II", data, 8)
            self.table_offset = 8
            self.header += struct.unpack_from("<H", data, 16)[0]
        self.string_offset = self.table + self.stride * self.symbol_count
        length = struct.unpack_from("<I", data, self.string_offset)[0]
        self.strings = bytearray(data[self.string_offset : self.string_offset + length])
        self.symbols = {}
        self.all_symbols = {}
        self.aliases = []
        self.sections = []
        self.section_records = []
        self.extra_relocations = {}
        for i in range(self.count):
            pos = self.header + i * 40
            size, raw, reloc, line, nr, nl = struct.unpack_from("<IIIIHH", data, pos + 16)
            name = data[pos : pos + 8].split(b"\0")[0].decode("ascii", errors="replace")
            flags = struct.unpack_from("<I", data, pos + 36)[0]
            _, _, relocation_bytes = relocation_layout(data, reloc, nr, flags)
            self.sections.append(
                dict(
                    name=name,
                    size=size,
                    flags=flags,
                    sha256=hashlib.sha256(
                        data[raw : raw + size] if raw else b"\0" * size
                    ).hexdigest(),
                    relocations_sha256=hashlib.sha256(
                        data[reloc : reloc + relocation_bytes]
                    ).hexdigest(),
                    lines_sha256=hashlib.sha256(data[line : line + nl * 6]).hexdigest(),
                )
            )
            self.section_records.append(
                dict(
                    pos=pos,
                    size=size,
                    raw=raw,
                    reloc=reloc,
                    count=nr,
                    flags=flags,
                    relocation_bytes=relocation_bytes,
                )
            )
        index = 0
        while index < self.symbol_count:
            pos = self.table + index * self.stride
            if data[pos : pos + 4] == b"\0" * 4:
                off = struct.unpack_from("<I", data, pos + 4)[0]
                end = self.strings.find(0, off)
                name = self.strings[off:end].decode("utf-8", errors="replace")
            else:
                name = data[pos : pos + 8].split(b"\0")[0].decode("ascii", errors="replace")
            section = struct.unpack_from("<i" if big else "<h", data, pos + 12)[0]
            typ = struct.unpack_from("<H", data, pos + (16 if big else 14))[0]
            storage, aux = data[pos + self.class_offset : pos + self.class_offset + 2]
            self.all_symbols[index] = dict(
                name=name,
                section=section,
                type=typ,
                storage=storage,
                value=struct.unpack_from("<I", data, pos + 8)[0],
            )
            if section > 0 and typ & 0x20 and storage in (2, 3):
                self.symbols[name] = dict(
                    pos=pos,
                    section=section,
                    storage=storage,
                    value=struct.unpack_from("<I", data, pos + 8)[0],
                )
            index += 1 + aux

    def relocation_positions(self, index):
        section = self.section_records[index - 1]
        first, count, _ = relocation_layout(
            self.data, section["reloc"], section["count"], section["flags"]
        )
        return range(first, first + count * 10, 10)

    def external(self, name):
        index = self.symbol_count + len(self.aliases)
        offset = len(self.strings)
        self.strings += name.encode("ascii") + b"\0"
        symbol = bytearray(self.stride)
        struct.pack_into("<II", symbol, 0, 0, offset)
        struct.pack_into("<H", symbol, 16 if self.stride == 20 else 14, 0x20)
        symbol[self.class_offset] = 2
        self.aliases.append(symbol)
        return index
