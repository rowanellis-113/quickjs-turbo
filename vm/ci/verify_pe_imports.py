#!/usr/bin/env python3
"""Verify imported DLLs on x64 PE32+ binaries (used to enforce MSVC /MT purity)."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys

PE_MAGIC = b"PE\x00\x00"
COFF_MACHINE_AMD64 = 0x8664
OPT_MAGIC_PE32_PLUS = 0x20B
IMAGE_DIRECTORY_ENTRY_IMPORT = 1


def _rva_to_offset(sections: list[tuple[int, int, int, int]], data_len: int, rva: int) -> int:
    for virtual_size, virtual_addr, raw_size, raw_ptr in sections:
        span = max(virtual_size, raw_size)
        if virtual_addr <= rva < virtual_addr + span:
            delta = rva - virtual_addr
            offset = raw_ptr + delta
            if raw_ptr == 0 or delta >= raw_size or offset >= data_len:
                raise ValueError(f"RVA 0x{rva:x} maps outside initialized section raw data")
            return offset
    raise ValueError(f"RVA 0x{rva:x} does not belong to any PE section")


def read_pe_imports(data: bytes) -> list[str]:
    """Return all imported DLL names from an x64 PE32+ image."""
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("Not an MZ executable")
    (e_lfanew,) = struct.unpack_from("<I", data, 0x3C)
    if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != PE_MAGIC:
        raise ValueError("Invalid PE header offset or signature")

    coff = e_lfanew + 4
    machine, num_sections, _, _, _, size_of_opt, _ = struct.unpack_from("<HHIIIHH", data, coff)
    if machine != COFF_MACHINE_AMD64:
        raise ValueError(f"Expected AMD64 PE (0x8664), got 0x{machine:04x}")

    opt = coff + 20
    if opt + size_of_opt > len(data) or size_of_opt < 128:
        raise ValueError("Truncated or undersized PE Optional Header")
    (opt_magic,) = struct.unpack_from("<H", data, opt)
    if opt_magic != OPT_MAGIC_PE32_PLUS:
        raise ValueError(f"Expected PE32+ Optional Header (0x20B), got 0x{opt_magic:04x}")
    (num_dirs,) = struct.unpack_from("<I", data, opt + 108)
    if num_dirs <= IMAGE_DIRECTORY_ENTRY_IMPORT:
        return []
    import_rva, import_size = struct.unpack_from("<II", data, opt + 120)
    if import_rva == 0 or import_size == 0:
        return []

    sec_off = opt + size_of_opt
    if sec_off + num_sections * 40 > len(data):
        raise ValueError("Truncated PE section table")
    sections = [
        struct.unpack_from("<IIII", data, sec_off + i * 40 + 8) for i in range(num_sections)
    ]

    pos = _rva_to_offset(sections, len(data), import_rva)
    dlls: list[str] = []
    while pos + 20 <= len(data):
        oft, ts, fwd, name_rva, ft = struct.unpack_from("<IIIII", data, pos)
        if (oft, ts, fwd, name_rva, ft) == (0, 0, 0, 0, 0):
            break
        name_off = _rva_to_offset(sections, len(data), name_rva)
        end = data.find(b"\x00", name_off)
        if end < 0:
            raise ValueError(f"Unterminated import DLL name at RVA 0x{name_rva:x}")
        dlls.append(data[name_off:end].decode("ascii"))
        pos += 20
    return dlls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow",
        action="append",
        help="Allowed imported DLL name (repeatable, case-insensitive). Defaults to KERNEL32.dll.",
    )
    parser.add_argument("pe_files", nargs="+", type=Path, help="PE32+ files to inspect")
    args = parser.parse_args(argv)

    allowed = args.allow if args.allow is not None else ["KERNEL32.dll"]
    allowed_lower = {name.lower() for name in allowed}

    errors: list[str] = []
    for pe_path in args.pe_files:
        try:
            dlls = read_pe_imports(pe_path.read_bytes())
        except (OSError, ValueError, struct.error, UnicodeDecodeError) as exc:
            errors.append(f"{pe_path}: {exc}")
            continue
        print(f"PE_IMPORTS {pe_path.name}: {dlls}")
        if not dlls:
            errors.append(f"{pe_path}: empty import table")
            continue
        disallowed = [dll for dll in dlls if dll.lower() not in allowed_lower]
        if disallowed:
            errors.append(f"{pe_path}: disallowed DLL imports {disallowed} (allowed: {allowed})")

    if errors:
        for err in errors:
            print(f"PE_IMPORT_ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
