"""ELF control-flow properties shared by the Linux assembly emitters."""

import struct


def property_note(cet):
    if cet not in (0, 1, 2, 3):
        raise ValueError("Unreviewed compiler CET feature bits: " + str(cet))
    if not cet:
        return []
    return [
        '.section .note.gnu.property,"a",@note',
        ".p2align 3",
        ".long 4, 16, 5",
        '.asciz "GNU"',
        ".long 0xc0000002, 4",
        ".long " + str(cet),
        ".long 0",
    ]


def read_property(elf):
    notes = [s for s in elf.sections if s["name"] == ".note.gnu.property"]
    result = 0
    for section in notes:
        raw, pos = elf.section_data(section), 0
        while pos < len(raw):
            if pos + 12 > len(raw):
                raise ValueError("Truncated GNU property note")
            namesz, descsz, kind = struct.unpack_from("<III", raw, pos)
            pos += 12
            name = raw[pos : pos + namesz]
            pos += (namesz + 3) & ~3
            end = pos + descsz
            if end > len(raw):
                raise ValueError("Truncated GNU property descriptor")
            if name == b"GNU\0" and kind == 5:
                prop = pos
                while prop < end:
                    if prop + 8 > end:
                        raise ValueError("Truncated x86 property header")
                    typ, size = struct.unpack_from("<II", raw, prop)
                    prop += 8
                    if prop + size > end:
                        raise ValueError("Truncated x86 property data")
                    if typ == 0xC0000002:
                        if size != 4:
                            raise ValueError("Unexpected x86 feature property size")
                        result |= struct.unpack_from("<I", raw, prop)[0]
                    prop += (size + 7) & ~7
            pos = (end + 3) & ~3
    return result
