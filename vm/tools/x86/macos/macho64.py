"""Minimal 64-bit Mach-O parser for x86-64 object layout probing and image qualification."""

import struct

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_X86_64 = 0x01000007
MH_OBJECT = 1
MH_EXECUTE = 2
MH_DYLIB = 6

MH_PIE = 0x00200000
MH_ALLOW_STACK_EXECUTION = 0x00020000

LC_SYMTAB = 0x2
LC_SEGMENT_64 = 0x19

VM_PROT_READ = 1
VM_PROT_WRITE = 2
VM_PROT_EXECUTE = 4

N_STAB = 0xE0
N_TYPE = 0x0E
N_SECT = 0x0E
N_EXT = 0x01
N_PEXT = 0x10


def _decode_cstr16(raw):
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="strict")


class MachO64:
    """Read-only 64-bit little-endian x86-64 Mach-O view."""

    def __init__(self, data, *, expected_cputype=CPU_TYPE_X86_64):
        if type(expected_cputype) is not int or expected_cputype <= 0:
            raise ValueError("Invalid expected Mach-O CPU type: " + repr(expected_cputype))
        self.data = bytes(data)
        if len(self.data) < 32:
            raise ValueError("Truncated Mach-O header")
        (
            self.magic,
            self.cputype,
            self.cpusubtype,
            self.filetype,
            self.ncmds,
            self.sizeofcmds,
            self.flags,
            self.reserved,
        ) = struct.unpack_from("<IIIIIIII", self.data, 0)
        if self.magic != MH_MAGIC_64:
            raise ValueError("Expected 64-bit little-endian Mach-O")
        if self.cputype != expected_cputype:
            raise ValueError(
                f"Expected Mach-O cputype {hex(expected_cputype)}, got {hex(self.cputype)}"
            )
        if 32 + self.sizeofcmds > len(self.data):
            raise ValueError("Truncated Mach-O load commands")
        self.segments = []
        self.sections = []
        self._symtab = None
        offset = 32
        sect_index = 1
        for _ in range(self.ncmds):
            if offset + 8 > 32 + self.sizeofcmds:
                raise ValueError("Truncated Mach-O load command header")
            cmd, cmdsize = struct.unpack_from("<II", self.data, offset)
            if cmdsize < 8 or offset + cmdsize > 32 + self.sizeofcmds:
                raise ValueError("Invalid Mach-O load command size")
            if cmd == LC_SEGMENT_64:
                if cmdsize < 72:
                    raise ValueError("Truncated LC_SEGMENT_64")
                (
                    segname_raw,
                    vmaddr,
                    vmsize,
                    fileoff,
                    filesize,
                    maxprot,
                    initprot,
                    nsects,
                    segflags,
                ) = struct.unpack_from("<16sQQQQIIII", self.data, offset + 8)
                seg = dict(
                    segname=_decode_cstr16(segname_raw),
                    vmaddr=vmaddr,
                    vmsize=vmsize,
                    fileoff=fileoff,
                    filesize=filesize,
                    maxprot=maxprot,
                    initprot=initprot,
                    nsects=nsects,
                    flags=segflags,
                )
                self.segments.append(seg)
                sect_off = offset + 72
                if sect_off + nsects * 80 > offset + cmdsize:
                    raise ValueError("Truncated LC_SEGMENT_64 sections")
                for _ in range(nsects):
                    (
                        sectname_raw,
                        s_segname_raw,
                        addr,
                        size,
                        s_offset,
                        align,
                        reloff,
                        nreloc,
                        s_flags,
                        res1,
                        res2,
                        res3,
                    ) = struct.unpack_from("<16s16sQQIIIIIIII", self.data, sect_off)
                    self.sections.append(
                        dict(
                            index=sect_index,
                            sectname=_decode_cstr16(sectname_raw),
                            segname=_decode_cstr16(s_segname_raw),
                            addr=addr,
                            size=size,
                            offset=s_offset,
                            align=align,
                            reloff=reloff,
                            nreloc=nreloc,
                            flags=s_flags,
                        )
                    )
                    sect_index += 1
                    sect_off += 80
            elif cmd == LC_SYMTAB:
                if cmdsize < 24:
                    raise ValueError("Truncated LC_SYMTAB")
                symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", self.data, offset + 8)
                self._symtab = (symoff, nsyms, stroff, strsize)
            offset += cmdsize

    @classmethod
    def read(cls, path, *, expected_cputype=CPU_TYPE_X86_64):
        return cls(open(path, "rb").read(), expected_cputype=expected_cputype)

    def section(self, segname, sectname):
        matches = [
            s for s in self.sections if s["segname"] == segname and s["sectname"] == sectname
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected unique Mach-O section {segname},{sectname}")
        return matches[0]

    def section_data(self, section):
        start = section["offset"]
        end = start + section["size"]
        if end > len(self.data):
            raise ValueError(
                f"Truncated Mach-O section data {section['segname']},{section['sectname']}"
            )
        return self.data[start:end]

    def symbols(self):
        if not self._symtab:
            return []
        symoff, nsyms, stroff, strsize = self._symtab
        if symoff + nsyms * 16 > len(self.data) or stroff + strsize > len(self.data):
            raise ValueError("Truncated Mach-O symbol or string table")
        strings = self.data[stroff : stroff + strsize]
        result = []
        for i in range(nsyms):
            n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from(
                "<IBBHQ", self.data, symoff + i * 16
            )
            if n_type & N_STAB:
                continue
            if n_strx >= strsize:
                raise ValueError("Mach-O symbol string offset out of bounds")
            end = strings.find(b"\x00", n_strx)
            name = (strings[n_strx:end] if end != -1 else strings[n_strx:]).decode(
                "utf-8", errors="replace"
            )
            result.append(
                dict(
                    name=name,
                    n_type=n_type,
                    n_sect=n_sect,
                    n_desc=n_desc,
                    value=n_value,
                    defined=(n_type & N_TYPE) == N_SECT and n_sect != 0,
                    external=bool(n_type & N_EXT),
                    private_extern=bool(n_type & N_PEXT),
                )
            )
        return result
