"""Route named direct core calls, preserving all other instructions/relocations."""

import bisect
import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import activate_tools, tool_path

activate_tools()
spec = importlib.util.spec_from_file_location("typed_core_route_coff", tool_path("object-adapter"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
packing_spec = importlib.util.spec_from_file_location(
    "typed_core_route_packing", tool_path("call-metadata")
)
packing = importlib.util.module_from_spec(packing_spec)
packing_spec.loader.exec_module(packing)


def pack(raw):
    # Previous decoded routes can place new relocation tables after COFF's
    # string table. Preserve that tail before appending any further symbols.
    return packing.packed(raw, C)[0]


def section_name(coff, index):
    name = coff.sections[index - 1]["name"]
    return coff.strings[int(name[1:]) :].split(b"\0")[0].decode() if name.startswith("/") else name


def relocations(coff, index):
    section = coff.section_records[index - 1]
    result = {}
    for at in coff.relocation_positions(index):
        offset, symbol, kind = struct.unpack_from("<IIH", coff.data, at)
        target = coff.all_symbols[symbol]
        if offset in result:
            raise RuntimeError("Repeated core relocation at one operand")
        result[offset] = (kind, target["name"], target["section"], target["value"])
    return result


def rewrite(raw, object_path, objdump, rules):
    """Rules select exact unspecialized symbols and optional owning functions.

    GCC same-section calls must be decoded. Their four displacement bytes are
    changed to an explicit REL32 operand; byte scanning is never used.
    """
    original_raw = raw
    raw = pack(raw)
    before, coff = C.Coff(raw), C.Coff(raw)
    starts = {}
    for symbol in before.all_symbols.values():
        if symbol["section"] > 0 and symbol["type"] & 32:
            starts.setdefault((symbol["section"], symbol["value"]), []).append(symbol["name"])
    owners = {}
    for (index, address), names in starts.items():
        name = min(names, key=lambda value: (value.startswith("qjs_"), value))
        owners.setdefault(index, []).append((address, name))
    for entries in owners.values():
        entries.sort()

    def owner(index, address):
        entries = owners.get(index, [])
        at = bisect.bisect_right([entry[0] for entry in entries], address) - 1
        if at < 0:
            raise RuntimeError("Direct call has no typed function owner")
        return entries[at][1]

    prepared = []
    for rule in rules:
        original = before.symbols[rule["before"]]
        if original["section"] <= 0:
            raise RuntimeError("Core target is not defined: " + rule["before"])
        prepared.append((rule, original, coff.external(rule["after"])))
    routes, occupied, listings = [], set(), {}
    for index, section in enumerate(coff.section_records, 1):
        if not section["flags"] & 0x20:
            continue
        if section["count"] == 65535:
            raise RuntimeError("Review core relocation overflow")
        for at in range(section["reloc"], section["reloc"] + 10 * section["count"], 10):
            offset, symbol, kind = struct.unpack_from("<IIH", coff.data, at)
            occupied.add((index, offset))
            for rule, original, target in prepared:
                if coff.all_symbols[symbol]["name"] != rule["before"]:
                    continue
                if (
                    kind != 4
                    or not offset
                    or coff.data[section["raw"] + offset - 1] not in (0xE8, 0xE9)
                ):
                    continue
                caller = owner(index, offset - 1)
                if rule.get("owners") is not None and caller not in rule["owners"]:
                    continue
                struct.pack_into("<I", coff.data, at + 4, target)
                routes.append(
                    dict(
                        section=index,
                        offset=offset,
                        owner=caller,
                        before=rule["before"],
                        after=rule["after"],
                        kind="existing-rel32",
                    )
                )
        # The existing compiler produces GCC's resolved local calls in one
        # .text section. Other section representations require explicit review.
        if section_name(before, index) != ".text" or not objdump:
            continue
        selected = [entry for entry in prepared if entry[1]["section"] == index]
        if not selected:
            continue
        name = section_name(before, index)
        if name not in listings:
            listings[name] = subprocess.check_output(
                [str(objdump), "-d", "-w", "-Mintel", "-j", name, str(object_path)], text=True
            )
        for line in listings[name].splitlines():
            match = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not match:
                continue
            address, code = int(match[1], 16), bytes.fromhex(match[2])
            if len(code) != 5 or code[0] not in (0xE8, 0xE9) or (index, address + 1) in occupied:
                continue
            destination = address + 5 + struct.unpack_from("<i", code, 1)[0]
            for rule, original, target in selected:
                if destination != original["value"]:
                    continue
                caller = owner(index, address)
                if rule.get("owners") is not None and caller not in rule["owners"]:
                    continue
                if (
                    bytes(coff.data[section["raw"] + address : section["raw"] + address + 5])
                    != code
                ):
                    raise RuntimeError("Decoded core call does not match its original bytes")
                offset = address + 1
                coff.data[section["raw"] + offset : section["raw"] + offset + 4] = bytes(4)
                coff.extra_relocations.setdefault(index, []).append(
                    struct.pack("<IIH", offset, target, 4)
                )
                routes.append(
                    dict(
                        section=index,
                        offset=offset,
                        owner=caller,
                        before=rule["before"],
                        after=rule["after"],
                        kind="decoded-rel32",
                        original_operand=code[1:].hex(),
                    )
                )
                occupied.add((index, offset))
    for rule in rules:
        count = sum(
            route["before"] == rule["before"] and route["after"] == rule["after"]
            for route in routes
        )
        if count < rule.get("minimum", 1) or ("count" in rule and count != rule["count"]):
            raise RuntimeError("Unexpected typed core route count: " + str((rule, count)))
    result = coff.finish()
    verify(original_raw, result, routes)
    return result, routes


def verify(raw, result, routes):
    before, after = C.Coff(raw), C.Coff(result)
    if len(before.section_records) != len(after.section_records):
        raise RuntimeError("Core section membership changed")
    indexed = {(row["section"], row["offset"]): row for row in routes}
    if len(indexed) != len(routes):
        raise RuntimeError("A core call was routed twice")
    for index, (old, new) in enumerate(zip(before.section_records, after.section_records), 1):
        if (
            old["size"] != new["size"]
            or old["flags"] != new["flags"]
            or section_name(before, index) != section_name(after, index)
        ):
            raise RuntimeError("Core section envelope changed")
        data = (
            bytearray(after.data[new["raw"] : new["raw"] + new["size"]])
            if new["raw"]
            else bytearray()
        )
        actual = relocations(after, index)
        expected = relocations(before, index)
        for (number, offset), route in indexed.items():
            if number != index:
                continue
            if actual.get(offset) != (4, route["after"], 0, 0):
                raise RuntimeError("Typed core destination was not published")
            if route["kind"] == "decoded-rel32":
                if offset in expected:
                    raise RuntimeError("Decoded operand already had a relocation")
                del actual[offset]
                data[offset : offset + 4] = bytes.fromhex(route["original_operand"])
            else:
                if expected[offset][1] != route["before"]:
                    raise RuntimeError("Original typed destination changed")
                actual[offset] = expected[offset]
        original = bytes(before.data[old["raw"] : old["raw"] + old["size"]]) if old["raw"] else b""
        if bytes(data) != original or actual != expected:
            raise RuntimeError("Changes outside approved core call operands")
