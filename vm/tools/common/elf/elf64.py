"""Strict ELF64 little-endian inspection with an explicit expected machine (62 or 183)."""

import struct
from pathlib import Path


class Elf64:
    def __init__(self, data, expected_machine=62):
        if type(expected_machine) is not int or expected_machine not in (62, 183):
            raise ValueError("Unreviewed ELF machine policy")
        self.data = bytes(data)
        if len(data) < 64:
            raise ValueError("Truncated ELF header")
        (
            ident,
            kind,
            machine,
            version,
            entry,
            phoff,
            shoff,
            flags,
            ehsize,
            phsize,
            phnum,
            shsize,
            shnum,
            names,
        ) = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
        if (
            ident[:7] != b"\x7fELF\x02\x01\x01"
            or machine != expected_machine
            or version != 1
            or kind not in (1, 2, 3)
        ):
            raise ValueError(f"Expected ELF64 little-endian machine {expected_machine}")
        if ehsize != 64 or shsize != 64 or not shnum or names >= shnum:
            raise ValueError("Unsupported ELF section header representation")
        self._span(shoff, shsize * shnum)
        self.kind = kind
        self.machine = machine
        self.sections = []
        for index in range(shnum):
            values = struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * shsize)
            name, typ, attr, addr, off, size, link, info, align, entsize = values
            if typ != 8:
                self._span(off, size)
            self.sections.append(
                dict(
                    index=index,
                    name_offset=name,
                    type=typ,
                    flags=attr,
                    address=addr,
                    offset=off,
                    size=size,
                    link=link,
                    info=info,
                    align=align,
                    entsize=entsize,
                )
            )
        table = self.section_data(self.sections[names])
        for section in self.sections:
            section["name"] = self.string(table, section["name_offset"])

    @classmethod
    def read(cls, path, expected_machine=62):
        return cls(Path(path).read_bytes(), expected_machine=expected_machine)

    def _span(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.data) or size > len(self.data) - offset:
            raise ValueError("ELF span exceeds input")

    @staticmethod
    def string(table, offset):
        if offset >= len(table):
            raise ValueError("ELF string offset exceeds table")
        end = table.find(b"\0", offset)
        if end < 0:
            raise ValueError("Unterminated ELF string")
        return table[offset:end].decode("utf-8")

    def section(self, name):
        found = [s for s in self.sections if s["name"] == name]
        if len(found) != 1:
            raise ValueError("Expected exactly one ELF section: " + name)
        return found[0]

    def section_data(self, section):
        if section["type"] == 8:
            raise ValueError("NOBITS section has no file data")
        return self.data[section["offset"] : section["offset"] + section["size"]]

    def symbols(self):
        result = []
        for section in self.sections:
            if section["type"] != 2:
                continue
            if (
                section["entsize"] != 24
                or section["size"] % 24
                or section["link"] >= len(self.sections)
            ):
                raise ValueError("Malformed ELF symbol table")
            strings = self.section_data(self.sections[section["link"]])
            raw = self.section_data(section)
            for pos in range(0, len(raw), 24):
                name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", raw, pos)
                if 0 < index < 0xFF00 and index >= len(self.sections):
                    raise ValueError("ELF symbol section exceeds table")
                result.append(
                    dict(
                        name=self.string(strings, name),
                        binding=info >> 4,
                        type=info & 15,
                        visibility=other & 3,
                        section=index,
                        value=value,
                        size=size,
                        table=section["index"],
                        index=pos // 24,
                    )
                )
        return result
