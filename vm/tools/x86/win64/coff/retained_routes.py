"""Bind retained Win64 paths to live symbols, decoded operands and opcode slots.

The inline-header engine has different C and assembly layouts from the retained
prefix-allocator revision. No historical object offsets enter these routes.
All allocated bytes outside selected operands, and all other relocations, stay
unchanged. Missing labels, destinations, counts or instruction forms fail closed.
"""

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from native_build import find_objdump
from core_routes import C, pack, relocations, section_name
from x86.common.paths_x86 import generated_file, source_file


def diagnostic_profile(build):
    cache = (Path(build) / "CMakeCache.txt").read_text(encoding="utf-8")
    mode = re.findall(r"^QJS_INTERP_FRAME_DIAGNOSTICS:BOOL=([^\r\n]+)$", cache, re.M)
    commands = json.loads((Path(build) / "compile_commands.json").read_text(encoding="utf-8"))
    selected = [
        row["command"] for row in commands if Path(row["file"]).name == "quickjs-interpreter.c"
    ]
    if len(mode) != 1 or len(selected) != 1:
        raise RuntimeError("Need one configured and compiled retained diagnostic profile")
    value = mode[0].strip().upper()
    if value not in {"ON", "TRUE", "YES", "1", "OFF", "FALSE", "NO", "0"}:
        raise RuntimeError("Unknown retained diagnostic Boolean")
    enabled = value in {"ON", "TRUE", "YES", "1"}
    if (
        bool(re.search(r"(?:^|\s)[-/]DQJS_INTERP_FRAME_DIAGNOSTICS(?:\s|$)", selected[0]))
        != enabled
    ):
        raise RuntimeError("Retained diagnostic configuration and compiler flags disagree")
    return enabled


class Router:
    def __init__(self, path, build):
        self.path, self.build = Path(path), Path(build)
        self.raw = pack(self.path.read_bytes())
        self.old, self.co = C.Coff(self.raw), C.Coff(self.raw)
        self.routes, self.aliases, self.renames = [], [], []
        self.profile_contracts = []
        self.external_symbols, self.decoded, self.occupied = {}, {}, set()

    def symbol(self, name):
        matches = [
            s for s in self.old.all_symbols.values() if s["name"] == name and s["section"] > 0
        ]
        positions = {(s["section"], s["value"]) for s in matches}
        if len(positions) != 1:
            raise RuntimeError("Need one retained source symbol: " + name + " in " + str(self.path))
        return matches[0]

    def external(self, name):
        if name not in self.external_symbols:
            matches = [
                i
                for i, s in self.co.all_symbols.items()
                if s["name"] == name and s["section"] == 0 and s["storage"] == 2 and not s["value"]
            ]
            self.external_symbols[name] = matches[0] if matches else self.co.external(name)
        return self.external_symbols[name]

    def alias(self, name, original):
        source = self.symbol(original)
        if not self.old.section_records[source["section"] - 1]["flags"] & 0x20000000:
            raise RuntimeError("Retained function alias is not executable: " + original)
        present = [
            s
            for s in self.old.all_symbols.values()
            if s["name"] == name and s["section"] > 0 and s["storage"] == 2
        ]
        if present:
            if any(
                (s["section"], s["value"]) != (source["section"], source["value"]) for s in present
            ):
                raise RuntimeError("Retained alias already has another owner: " + name)
            return
        index = self.co.external(name)
        entry = self.co.aliases[-1]
        struct.pack_into("<I", entry, 8, source["value"])
        struct.pack_into("<i" if self.co.stride == 20 else "<h", entry, 12, source["section"])
        struct.pack_into("<H", entry, 16 if self.co.stride == 20 else 14, 32)
        self.aliases.append(
            dict(
                name=name,
                original=original,
                section=source["section"],
                value=source["value"],
                index=index,
            )
        )

    def data_alias(self, name, original, size):
        source = self.symbol(original)
        section = self.old.section_records[source["section"] - 1]
        if source["type"] or not section["flags"] & 0x80000000 or section["flags"] & 0x20000000:
            raise RuntimeError("Need original writable data: " + original)
        if source["value"] + size > section["size"] or source["value"] % size:
            raise RuntimeError("Original data alias is outside its aligned storage: " + original)
        if any(s["name"] == name for s in self.old.all_symbols.values()):
            raise RuntimeError("Original data alias name is occupied: " + name)
        index = self.co.external(name)
        entry = self.co.aliases[-1]
        struct.pack_into("<I", entry, 8, source["value"])
        struct.pack_into("<i" if self.co.stride == 20 else "<h", entry, 12, source["section"])
        struct.pack_into("<H", entry, 16 if self.co.stride == 20 else 14, 0)
        self.aliases.append(
            dict(
                name=name,
                original=original,
                section=source["section"],
                value=source["value"],
                index=index,
                bytes=size,
                kind="data",
            )
        )

    def rename(self, name, after):
        source = self.symbol(name)
        found = []
        for index, s in self.co.all_symbols.items():
            if s["name"] != name or (s["section"], s["value"]) != (
                source["section"],
                source["value"],
            ):
                continue
            offset = len(self.co.strings)
            self.co.strings += after.encode() + b"\0"
            struct.pack_into("<II", self.co.data, self.co.table + index * self.co.stride, 0, offset)
            s["name"] = after
            found.append(index)
        if not found:
            raise RuntimeError("Missing retained rename: " + name)
        self.renames.append(dict(before=name, after=after, indices=found))

    def span(self, label, end=None, whole=False):
        s = self.symbol(label)
        starts = [
            v["value"]
            for v in self.old.all_symbols.values()
            if v["section"] == s["section"]
            and v["value"] > s["value"]
            and (v["type"] & 32 if whole else not v["name"].startswith((".", "$")))
        ]
        stop = (
            self.symbol(end)["value"]
            if end
            else min(starts + [self.old.section_records[s["section"] - 1]["size"]])
        )
        if end and self.symbol(end)["section"] != s["section"]:
            raise RuntimeError("Retained label range crosses sections")
        return s["section"], s["value"], stop

    def instructions(self, section):
        if section not in self.decoded:
            r = self.old.section_records[section - 1]
            folder = generated_file(self.build, "retained-route-decode")
            folder.mkdir(parents=True, exist_ok=True)
            data = self.raw[r["raw"] : r["raw"] + r["size"]]
            binary = folder / (hashlib.sha256(data).hexdigest() + ".bin")
            binary.write_bytes(data)
            command = [
                str(find_objdump(self.build)),
                "-D",
                "-b",
                "binary",
                "-m",
                "i386:x86-64",
                "-w",
                "-Mintel",
                str(binary),
            ]
            process = subprocess.run(
                command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if process.returncode:
                raise RuntimeError(process.stderr.decode("utf-8", errors="replace"))
            binary.with_suffix(".log").write_bytes(process.stdout)
            rows = []
            for line in process.stdout.decode("ascii", errors="replace").splitlines():
                m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)(.*?)\s*$", line)
                if not m:
                    continue
                at, code = int(m[1], 16), bytes.fromhex(m[2])
                if code != data[at : at + len(code)]:
                    raise RuntimeError("Retained disassembly is not bound to its input")
                operand = None
                if len(code) == 5 and code[0] in (0xE8, 0xE9):
                    operand = at + 1
                elif len(code) == 6 and code[0] == 0x0F and 0x80 <= code[1] <= 0x8F:
                    operand = at + 2
                elif (
                    len(code) == 7
                    and 0x48 <= code[0] <= 0x4F
                    and code[1] in (0x8D, 0x89, 0x8B)
                    and code[2] & 0xC7 == 5
                ):
                    operand = at + 3
                rows.append(
                    dict(
                        address=at, code=code, text=m[3].partition("#")[0].strip(), operand=operand
                    )
                )
            self.decoded[section] = rows
        return self.decoded[section]

    def reference(self, section, offset, kind):
        r = self.old.section_records[section - 1]
        width = 8 if kind == 1 else 4
        addend = int.from_bytes(
            self.raw[r["raw"] + offset : r["raw"] + offset + width], "little", signed=kind == 4
        )
        matches = []
        for pos in range(r["reloc"], r["reloc"] + 10 * r["count"], 10):
            off, index, typ = struct.unpack_from("<IIH", self.raw, pos)
            if off == offset:
                if typ != kind:
                    raise RuntimeError(
                        "Unexpected retained relocation kind: " + str((section, offset, typ, kind))
                    )
                matches.append((pos, self.old.all_symbols[index], addend))
        if len(matches) > 1:
            raise RuntimeError("Repeated retained operand relocation")
        return matches[0] if matches else None

    def matches(self, section, offset, expected, kind=4, delta=0):
        ref = self.reference(section, offset, kind)
        if ref:
            _, symbol, addend = ref
            if symbol["name"] == expected and addend == delta:
                return True
            if symbol["section"] <= 0:
                return False
            targets = [
                s
                for s in self.old.all_symbols.values()
                if s["name"] == expected and s["section"] > 0
            ]
            return any(
                (symbol["section"], symbol["value"] + addend) == (s["section"], s["value"] + delta)
                for s in targets
            )
        if kind != 4:
            return False
        row = next((i for i in self.instructions(section) if i["operand"] == offset), None)
        if row is None:
            return False
        # A resolved same-section operand cannot name an undefined external.
        # Other local constants/labels may precede the required relocation.
        if not any(
            s["name"] == expected and s["section"] > 0 for s in self.old.all_symbols.values()
        ):
            return False
        s = self.symbol(expected)
        displacement = struct.unpack_from("<i", row["code"], offset - row["address"])[0]
        return (section, row["address"] + len(row["code"]) + displacement) == (
            s["section"],
            s["value"] + delta,
        )

    def change(self, section, offset, before, after, kind=4, role="direct"):
        if (section, offset) in self.occupied or not self.matches(section, offset, before, kind):
            raise RuntimeError(
                "Retained source operand changed: "
                + str((self.path.name, section, offset, before, role))
            )
        if kind == 4 and not any(i["operand"] == offset for i in self.instructions(section)):
            raise RuntimeError("Retained REL32 is not a decoded instruction operand")
        ref = self.reference(section, offset, kind)
        target = self.external(after)
        width = 8 if kind == 1 else 4
        r = self.old.section_records[section - 1]
        original = bytes(self.co.data[r["raw"] + offset : r["raw"] + offset + width])
        self.co.data[r["raw"] + offset : r["raw"] + offset + width] = bytes(width)
        if ref:
            struct.pack_into("<I", self.co.data, ref[0] + 4, target)
        else:
            self.co.extra_relocations.setdefault(section, []).append(
                struct.pack("<IIH", offset, target, kind)
            )
        self.routes.append(
            dict(
                section=section,
                offset=offset,
                before=before,
                after=after,
                kind=kind,
                role=role,
                original=original.hex(),
                had_relocation=ref is not None,
            )
        )
        self.occupied.add((section, offset))

    def branches(
        self, label, before, after, first=False, end=None, count=1, mnemonic=None, comparison=None
    ):
        section, start, stop = self.span(label, end)
        instructions = self.instructions(section)
        previous = {
            r["address"] + len(r["code"]): " ".join(r["text"].split()) for r in instructions
        }
        rows = [
            r
            for r in instructions
            if start <= r["address"] < stop
            and r["operand"] is not None
            and r["text"].split()[0]
            in (
                "call",
                "jmp",
                "je",
                "jne",
                "ja",
                "jae",
                "jb",
                "jbe",
                "jg",
                "jge",
                "jl",
                "jle",
                "js",
                "jns",
            )
            and (mnemonic is None or r["text"].split()[0] == mnemonic)
            and (comparison is None or previous.get(r["address"]) == comparison)
            and self.matches(section, r["operand"], before)
        ]
        if first:
            rows = rows[:1]
        if len(rows) != count:
            raise RuntimeError(
                "Retained branch inventory changed: "
                + str((label, before, after, len(rows), count))
            )
        for row in rows:
            self.change(section, row["operand"], before, after, role=label)

    def refs(self, before, after, count=None, owners=None, kind=4, minimum=1):
        spans = [self.span(owner, whole=True) for owner in owners] if owners else None
        found = []
        for section, r in enumerate(self.old.section_records, 1):
            if kind == 4 and not r["flags"] & 0x20000000:
                continue
            for at in range(r["reloc"], r["reloc"] + 10 * r["count"], 10):
                off, _, typ = struct.unpack_from("<IIH", self.raw, at)
                if (
                    typ != kind
                    or spans
                    and not any(n == section and start <= off < stop for n, start, stop in spans)
                ):
                    continue
                if self.matches(section, off, before, kind):
                    found.append((section, off))
        if len(found) < minimum or count is not None and len(found) != count:
            raise RuntimeError(
                "Retained reference inventory changed: "
                + str((before, after, len(found), count, minimum))
            )
        for section, off in found:
            self.change(section, off, before, after, kind, "named relocation")

    def address(self, label, before, after):
        section, start, stop = self.span(label)
        rows = [
            r
            for r in self.instructions(section)
            if start <= r["address"] < stop
            and r["operand"] is not None
            and r["text"].startswith("lea ")
            and self.matches(section, r["operand"], before)
        ]
        if len(rows) != 1:
            raise RuntimeError(
                "Retained address selection changed: " + str((label, before, len(rows)))
            )
        self.change(section, rows[0]["operand"], before, after, role=label)

    def pointer_load(self, label, target, addend, register):
        """Verify an existing selected-table load without undoing prior routes."""
        section, start, stop = self.span(label)
        found = [
            row
            for row in self.instructions(section)
            if start <= row["address"] < stop
            and row["operand"] is not None
            and len(row["code"]) == 7
            and row["code"][1] == 0x8B
            and row["text"].split(None, 1)[-1].startswith(register + ",")
            and self.matches(section, row["operand"], target, delta=addend)
        ]
        if len(found) != 1:
            raise RuntimeError(
                "Retained selected table load changed: "
                + str((label, target, addend, register, len(found)))
            )
        self.profile_contracts.append(
            dict(
                label=label,
                address=found[0]["address"],
                target=target,
                addend=addend,
                register=register,
            )
        )

    def slot(self, source, opcode, before, after):
        names = re.findall(
            r"^\s*DEF\(\s*(\w+)",
            source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8"),
            re.M,
        )
        table = self.symbol("interp_table")
        self.change(
            table["section"],
            table["value"] + names.index(opcode) * 8,
            before,
            after,
            1,
            "opcode:" + opcode,
        )

    def install(self, source, selector, opcode, before, after):
        names = re.findall(
            r"^\s*DEF\(\s*(\w+)",
            source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8"),
            re.M,
        )
        section, start, stop = self.span(selector, selector + "_end")
        instructions = self.instructions(section)
        found = []
        for i, row in enumerate(instructions[:-1]):
            if (
                not start <= row["address"] < stop
                or row["operand"] is None
                or not re.match(r"lea\s+r10,", row["text"])
            ):
                continue
            store = instructions[i + 1]
            if (
                store["address"] != row["address"] + len(row["code"])
                or store["operand"] is None
                or not re.match(r"mov\s+QWORD PTR \[rip\+.*\],r10$", store["text"])
            ):
                continue
            if self.matches(
                section,
                store["operand"],
                "JS_FramePublishDirtyTable",
                delta=names.index(opcode) * 8,
            ) and self.matches(section, row["operand"], before):
                found.append(row)
        if len(found) != 1:
            raise RuntimeError(
                "Retained selector opcode inventory changed: "
                + str((selector, opcode, before, len(found)))
            )
        self.change(section, found[0]["operand"], before, after, role=selector + ":" + opcode)

    def finish(self):
        result = self.co.finish()
        after = C.Coff(result)
        if len(after.section_records) != len(self.old.section_records):
            raise RuntimeError("Retained section membership changed")
        for section, (old, new) in enumerate(
            zip(self.old.section_records, after.section_records), 1
        ):
            if (old["size"], old["flags"], section_name(self.old, section)) != (
                new["size"],
                new["flags"],
                section_name(after, section),
            ):
                raise RuntimeError("Retained section envelope changed")
            data = (
                bytearray(result[new["raw"] : new["raw"] + new["size"]])
                if new["raw"]
                else bytearray()
            )
            expected, actual = relocations(self.old, section), relocations(after, section)
            renamed_names = {row["before"]: row["after"] for row in self.renames}
            expected = {
                off: (kind, renamed_names.get(name, name) if number > 0 else name, number, value)
                for off, (kind, name, number, value) in expected.items()
            }
            for row in self.routes:
                if row["section"] != section:
                    continue
                off, kind = row["offset"], row["kind"]
                if actual.pop(off, None) != (kind, row["after"], 0, 0):
                    raise RuntimeError("Retained destination was not published")
                if row["had_relocation"]:
                    del expected[off]
                data[off : off + (8 if kind == 1 else 4)] = bytes.fromhex(row["original"])
            original = self.raw[old["raw"] : old["raw"] + old["size"]] if old["raw"] else b""
            if data != original or actual != expected:
                raise RuntimeError(
                    "Retained bytes or relocations changed outside selected operands"
                )
        renamed = {i: row["after"] for row in self.renames for i in row["indices"]}
        for index, s in self.old.all_symbols.items():
            expected = dict(s)
            if index in renamed:
                expected["name"] = renamed[index]
            if after.all_symbols[index] != expected:
                raise RuntimeError("Retained original symbol changed outside selected renames")
        self.path.write_bytes(result)
        return dict(
            path=str(self.path),
            source_bound=True,
            routes=self.routes,
            aliases=self.aliases,
            profile_contracts=self.profile_contracts,
            renames=self.renames,
            before_sha256=hashlib.sha256(self.raw).hexdigest(),
            sha256=hashlib.sha256(result).hexdigest(),
            allocated_bytes_held_outside_operands=True,
        )


def core(router, source, recipe, required):
    if "qjs_frame_core_js_create_from_ctor" in required:
        router.alias("qjs_frame_core_js_create_from_ctor", "js_create_from_ctor")
    # Keep public legacy roots for the retained wire implementation. The live
    # optimized roots are separate source-compiled definitions in this archive.
    names = ("JS_WriteObject", "JS_WriteObject2", "JS_ReadObject", "JS_ReadObject2")
    for name in names:
        router.rename(name, "JS_WireLegacy_" + name)
    for entry in recipe["aliases"]:
        name = entry["name"]
        if not name.startswith("qjs_frame_core_"):
            continue
        original = name[len("qjs_frame_core_") :]
        if any(s["name"] == original and s["section"] > 0 for s in router.old.all_symbols.values()):
            router.alias(name, original)
        elif name in required:
            raise RuntimeError("Required retained source helper has no exact ABI symbol: " + name)
    from core_routes import rewrite

    rules = [
        dict(before="js_new_string_char", after="JS_FrameSmallCharNew", minimum=7),
        dict(before="js_strict_eq_slow", after="JS_FrameStrictIdentitySlow", minimum=2),
        dict(before="js_get_fast_array_element", after="JS_FrameFastArrayOwnGet", minimum=1),
        dict(
            before="JS_RunGC",
            after="JS_FrameSmallCharCleanupGC",
            owners=["JS_FreeRuntime"],
            count=1,
        ),
        dict(before="JS_WriteObject2", after="JS_WriteObject2", minimum=1),
        dict(before="JS_ReadObject2", after="JS_ReadObject2", minimum=0),
    ]
    # Decode against original names, then compose the independently verified
    # direct-call changes with our current symbol names/aliases.
    routed, routes = rewrite(router.raw, router.path, find_objdump(router.build), rules)
    routed_co = C.Coff(routed)
    for row in routes:
        ref = router.reference(row["section"], row["offset"], 4)
        old = router.old.section_records[row["section"] - 1]
        new = routed_co.section_records[row["section"] - 1]
        off = row["offset"]
        router.co.data[old["raw"] + off : old["raw"] + off + 4] = routed_co.data[
            new["raw"] + off : new["raw"] + off + 4
        ]
        index = router.external(row["after"])
        if ref:
            struct.pack_into("<I", router.co.data, ref[0] + 4, index)
        else:
            router.co.extra_relocations.setdefault(row["section"], []).append(
                struct.pack("<IIH", off, index, 4)
            )
        router.routes.append(
            dict(
                section=row["section"],
                offset=off,
                before=row["before"],
                after=row["after"],
                kind=4,
                role=row["owner"],
                original=router.raw[old["raw"] + off : old["raw"] + off + 4].hex(),
                had_relocation=ref is not None,
            )
        )


def aliases(router, dirty=False, msvc=False):
    prefix = "dirty_" if dirty else ""
    suffix = "Dirty" if dirty else "Clean"
    for operator in ("Eq", "Neq"):
        router.alias(
            "JS_FrameStrictEqOld" + suffix + operator,
            prefix + "interp_op_slow_strict_" + ("eq" if operator == "Eq" else "neq"),
        )
        router.alias(
            "JS_FrameLooseEqOld" + operator + ("Dirty" if dirty else ""),
            prefix + "interp_op_slow_" + ("eq" if operator == "Eq" else "neq"),
        )
    if msvc:
        router.alias("JS_FrameTruthMSVCOldSlow", "interp_slow")


def operators(router, dirty=False, msvc=False):
    prefix = "dirty_" if dirty else ""
    suffix = "Dirty" if dirty else "Clean"
    cache = (router.build / "CMakeCache.txt").read_text(encoding="utf-8")
    numeric_mode = re.findall(r"^QJS_FRAME_EXPERIMENTAL_COMPARE:BOOL=([^\r\n]+)$", cache, re.M)
    numeric_compare = len(numeric_mode) == 1 and numeric_mode[0].strip().upper() in (
        "ON",
        "YES",
        "TRUE",
        "1",
    )
    has_numeric = any(
        s["name"] == prefix + "interp_number_compare_eq" and s["section"] > 0
        for s in router.old.all_symbols.values()
    )
    if numeric_compare != has_numeric:
        raise RuntimeError("Numeric comparison configuration and emitted handler symbols disagree")
    for label, target in (
        ("lnot", "Lnot"),
        ("if_true", "IfTrue"),
        ("if_false", "IfFalse"),
        ("if_true8", "IfTrue8"),
        ("if_false8", "IfFalse8"),
    ):
        router.branches(
            prefix + "interp_" + label,
            prefix + "interp_slow",
            "JS_FrameTruth" + target + suffix,
            mnemonic="ja",
        )
    for operator in ("eq", "neq"):
        target = "JS_FrameLooseEq" + operator.capitalize() + ("Dirty" if dirty else "")
        if numeric_compare:
            # Both tag failures preserve the original operands. Only these
            # two decoded branches bind to the established coercion helper.
            for label in (
                prefix + "interp_number_compare_" + operator,
                prefix + "interp_number_compare_" + operator + "_lhs_ready",
            ):
                router.branches(
                    label, prefix + "interp_op_slow_" + operator, target, mnemonic="jne"
                )
        else:
            router.branches(
                prefix + "interp_" + operator, prefix + "interp_op_slow_" + operator, target
            )
        strict_fallback = (
            "interp_primitive_eq_original_fallback"
            if numeric_compare
            else "interp_primitive_eq_fallback"
        )
        router.branches(
            prefix + strict_fallback,
            prefix + "interp_op_slow_strict_" + operator,
            "JS_FrameStrictEq" + suffix,
        )
    for label in ("get_array_el", "get_array_el2"):
        after = (
            "JS_FrameLatinIndex" + ("Consume" if label == "get_array_el" else "Keep")
            if msvc
            else "JS_FrameStringIndex" + suffix
        )
        # The native string entry consumes an integer index. Keep the earlier
        # index-tag failure on the general slow path; select only the receiver
        # object-tag failure after that check. A float's low word is no index.
        router.branches(
            prefix + "interp_" + label,
            prefix + "interp_slow",
            after,
            mnemonic="jne",
            comparison="cmp DWORD PTR [r13-0x18],0xffffffff",
        )
    if not msvc:
        for label, target in (
            ("get_array_el_typed", "Get"),
            ("get_array_el2_typed", "Get2"),
            ("put_array_el_typed", "Put"),
        ):
            router.branches(
                prefix + "interp_" + label,
                prefix + "interp_slow",
                "JS_FrameArguments" + target + suffix,
                first=True,
            )


DIRTY_SLOTS = {
    "object": ("dirty_interp_slow", "JS_FrameOrdinaryLiteralOpDirty"),
    "special_object": ("dirty_JS_FrameNullProtoCold", "JS_FrameArgumentsOpDirty"),
    "insert2": ("dirty_interp_slow", "JS_FrameStackInsert2Dirty"),
    "regexp": ("dirty_interp_slow", "JS_FrameRegexpEntry"),
    "define_field": ("dirty_interp_slow", "JS_FrameOrdinaryLiteralOpDirty"),
    "typeof": ("dirty_interp_slow", "JS_FrameTypeofValueDirty"),
    "typeof_is_undefined": ("dirty_interp_slow", "JS_FrameTypeofUndefinedDirty"),
    "typeof_is_function": ("dirty_interp_slow", "JS_FrameTypeofFunctionDirty"),
    **{
        name: ("dirty_interp_slow", "JS_FrameIteratorEntry_" + name)
        for name in (
            "catch",
            "gosub",
            "ret",
            "nip_catch",
            "check_object",
            "for_of_start",
            "for_of_next",
            "iterator_close",
        )
    },
}


def selector(router, source, name, new_table_label):
    for opcode, (before, after) in DIRTY_SLOTS.items():
        router.install(source, name, opcode, before, after)
    router.address(new_table_label, "JS_FramePublishTable", "JS_FramePublishDirtyTable")


def register(router, source, msvc, diagnostics=False):
    aliases(router, msvc=msvc)
    if diagnostics and not msvc:
        # The diagnostic VM always publishes before C and has no dirty copy.
        # Retained objects still contain both entry families. Their six cold
        # fallback references therefore name the same live diagnostic labels.
        for name, original in (
            ("JS_FrameStrictEqOldDirtyEq", "interp_op_slow_strict_eq"),
            ("JS_FrameStrictEqOldDirtyNeq", "interp_op_slow_strict_neq"),
            ("JS_FrameLooseEqOldEqDirty", "interp_op_slow_eq"),
            ("JS_FrameLooseEqOldNeqDirty", "interp_op_slow_neq"),
            ("dirty_interp_slow", "interp_slow"),
            ("dirty_JS_FrameNullProtoCold", "JS_FrameNullProtoCold"),
        ):
            router.alias(name, original)
        router.profile_contracts.append(
            "diagnostic cold fallback aliases bind to the directly published VM"
        )
    operators(router, msvc=msvc)
    if msvc:
        router.refs("JS_FrameLeafGuard", "JS_FrameReadonlyCallGuard1", count=1)
        router.refs("JS_FrameVarargsValidateSelect", "JS_FrameRegExpValidateSelect", count=1)
        router.refs("JS_FrameInterpGenericFast", "JS_FrameStringNumericSelect", count=1)
        if not diagnostics and "QJS_PROPERTY_IC:BOOL=ON" in (
            Path(router.build) / "CMakeCache.txt"
        ).read_text(encoding="utf-8"):
            for opcode, kind in (("get_var", "GetVar"), ("get_var_undef", "GetVarUndef")):
                ready = "interp_" + opcode + "_ready"
                worker = "JS_FrameSymbolGlobal" + kind + "Condition"
                router.alias("JS_FrameSymbolGlobal" + kind + "OriginalReady", ready)
                router.branches(
                    "interp_" + opcode + "_binding_cell_hit", ready, worker, mnemonic="jne"
                )
                router.branches(
                    "interp_" + opcode + "_binding_cell_hit", ready, worker, mnemonic="jmp"
                )
    slots = {
        "regexp": ("interp_slow", "JS_FrameRegExpOpcode" if msvc else "JS_FrameRegexpEntry"),
        "typeof": ("interp_slow", "JS_FrameTypeofValueClean"),
        "typeof_is_undefined": ("interp_slow", "JS_FrameTypeofUndefinedClean"),
        "typeof_is_function": ("interp_slow", "JS_FrameTypeofFunctionClean"),
    }
    if not msvc:
        slots.update(
            object=("interp_slow", "JS_FrameOrdinaryLiteralOpClean"),
            special_object=("JS_FrameNullProtoCold", "JS_FrameArgumentsOpClean"),
            insert2=("interp_slow", "JS_FrameStackInsert2Clean"),
            define_field=("interp_slow", "JS_FrameOrdinaryLiteralOpClean"),
        )
    for opcode, (before, after) in slots.items():
        router.slot(source, opcode, before, after)


def publish(router, source, diagnostics=False):
    if diagnostics:
        # The diagnostic producer intentionally emits no dirty VM clone.
        # All live dispatch goes through the already routed clean table.
        if any(r["size"] and r["flags"] & 0xE0000000 for r in router.old.section_records) or any(
            s["section"] > 0 and s["type"] & 32 for s in router.old.all_symbols.values()
        ):
            raise RuntimeError("Diagnostic publication object is not the empty producer contract")
        router.profile_contracts.append(
            "diagnostic publication producer has no allocated payload or functions"
        )
        return
    aliases(router, dirty=True)
    operators(router, dirty=True)
    router.refs("JS_FrameLeafGuard", "JS_FrameArgumentsGuard", count=1)
    entries = [
        ("publish_interp_return_value_ready", "FrameInterpClose"),
        ("publish_interp_release_finalizer", "FrameInterpFree"),
        ("dirty_interp_host_call", "FrameNativeCallLinkDispatch"),
        ("dirty_interp_host_exception", "FrameInterpSlow"),
        ("dirty_interp_op_slow_add", "FrameInterpAddDirect"),
        ("dirty_interp_op_slow_mul", "FrameInterpBig_mul"),
        ("dirty_interp_slow", "FrameInterpSlow"),
        ("dirty_null_proto_begin_done", "FrameNewNullObject"),
        ("dirty_add_local_call_c", "FrameAddLocalBig"),
        ("dirty_slot_free_begin_done", "FreeValue"),
        ("dirty_slot_free_legacy", "FrameInterpFree"),
        ("dirty_JS_FrameNumberPropertyFallback", "FrameInterpProperty_get_field2"),
        ("dirty_proto_persist_slow", "FrameProtoPersistentFill"),
        ("dirty_JS_FrameAddLocalStringCold", "FrameAddLocalString"),
    ]
    entries += [
        ("dirty_interp_op_slow_" + op, "FrameInterpOp_" + op)
        for op in (
            "sub",
            "div",
            "mod",
            "lt",
            "lte",
            "gt",
            "gte",
            "eq",
            "neq",
            "strict_eq",
            "strict_neq",
        )
    ]
    entries += [
        ("dirty_interp_property_slow_" + op, "FrameInterpProperty_" + op)
        for op in ("get_field", "put_field", "drop", "call_constructor")
    ]
    for label, suffix in entries:
        router.branches(
            label, "JS_FramePublishBefore_" + suffix, "JS_FrameAlwaysPublishBefore_" + suffix
        )
    selector(router, source, "JS_FramePublishSelect", "publish_new_table")


def route(source, build, path, recipe, toolchain, required):
    router = Router(path, build)
    name = Path(recipe["object_path"]).name
    msvc = toolchain == "msvc"
    diagnostics = diagnostic_profile(build)
    if recipe["object_path"] == "CMakeFiles/qjs-core.dir/quickjs.c.obj":
        core(router, source, recipe, required)
    elif name == "quickjs-interpreter-internal.obj":
        s = router.symbol("internal_legacy_target")
        router.change(
            s["section"],
            s["value"],
            "qjs_frame_core_JS_CallInternal",
            "JS_FrameCEntry" if msvc else "JS_FrameArgumentsEntry",
            1,
            "internal legacy target",
        )
    elif name == "quickjs-interpreter-register.obj":
        register(router, source, msvc, diagnostics)
    elif name == "quickjs-interpreter-null-proto.obj" and msvc:
        router.refs("JS_FrameCallLinkOldM_JS_FrameLeafGuard", "JS_FrameReadonlyCallGuard0", count=1)
        router.refs("JS_FrameCallEnvMetaMiss", "JS_FrameCallEnvMetaMiss", count=1)
        router.refs("JS_FrameCallEnvLinkMiss", "JS_FrameCallEnvLinkMiss", count=1)
        router.refs("JS_FrameVarargsValidateSelect", "JS_FrameRegExpValidateSelect", minimum=5)
    elif name == "quickjs-interpreter-publish.obj" and not msvc:
        publish(router, source, diagnostics)
    elif (
        name
        in (
            "quickjs-interpreter-c-invoke.obj",
            "quickjs-interpreter-iterator-asm.obj",
            "quickjs-interpreter-native-c-scope.obj",
        )
        and not msvc
    ):
        router.refs(
            "JS_FramePublishTable",
            "JS_FramePublishDirtyTable",
            count=0
            if diagnostics
            else {
                "quickjs-interpreter-c-invoke.obj": 6,
                "quickjs-interpreter-iterator-asm.obj": 8,
                "quickjs-interpreter-native-c-scope.obj": 4,
            }[name],
            minimum=0 if diagnostics else 1,
        )
        if diagnostics:
            router.refs(
                "JS_FramePublishDirtyTable", "JS_FramePublishDirtyTable", count=0, minimum=0
            )
    elif name == "quickjs-interpreter-iterator-literal-asm.obj" and not msvc:
        router.refs("JS_FrameIteratorLiteralEnter", "JS_FrameOrdinaryLiteralEnter", count=1)
        router.refs("JS_FrameInterp", "JS_FrameOrdinaryLiteralLazyEnter", count=1)
    elif name == "quickjs-interpreter-global-binding.obj" and not msvc:
        if not diagnostics and "QJS_PROPERTY_IC:BOOL=ON" in (
            Path(build) / "CMakeCache.txt"
        ).read_text(encoding="utf-8"):
            router.alias("JS_FrameSymbolGlobalOriginalReady", "global_binding_ready")
            router.branches(
                "activation_binding_cell_hit",
                "global_binding_ready",
                "JS_FrameSymbolGlobalCondition",
                mnemonic="jne",
            )
            router.branches(
                "activation_binding_cell_hit",
                "global_binding_ready",
                "JS_FrameSymbolGlobalCondition",
                mnemonic="jmp",
            )
        if diagnostics:
            # The prior owned-bytecode stage redirects both diagnostic
            # selectors through its selected pointer (C asserts offset8).
            # Preserve that route; its base inherits the retained clean slots.
            for label in ("JS_FrameGlobalBindingSelect", "JS_FrameLeafSelect"):
                router.pointer_load(label, "JS_FrameOwnBytecodeDispatch", 8, "rsi")
            for label in (
                "global_binding_original_table",
                "leaf_select_global_binding_original_table",
            ):
                router.pointer_load(label, "JS_FrameOwnBytecodeDispatch", 8, "rdi")
        else:
            selector(
                router, source, "JS_FrameGlobalBindingSelect", "global_select_publish_new_table"
            )
            selector(
                router, source, "JS_FrameLeafSelect", "leaf_select_global_select_publish_new_table"
            )
        for alias, label in (
            ("Store", "leaf_classify_store"),
            ("Literal", "leaf_value_boolean_literal"),
            ("Boolean", "leaf_value_boolean"),
        ):
            router.alias("JS_FramePredicate" + alias, label)
        router.branches("leaf_classify_reject", "JS_FrameLeafUnready", "JS_FramePredicateClassify")
        router.branches("JS_FrameLeafHit", "leaf_value_boolean_literal", "JS_FramePredicateValue")
    elif name == "quickjs-interpreter-json-callback.obj" and not msvc:
        router.refs(
            "JS_FramePublishTable",
            "JS_FramePublishDirtyTable",
            count=0 if diagnostics else 3,
            minimum=0 if diagnostics else 1,
        )
        router.refs(
            "JS_FrameCallEnvMetaMiss",
            "JS_FrameCallLinkPolicyMetaMiss",
            count=1 if diagnostics else 2,
        )
        router.refs("JS_FrameLeafGuard", "JS_FrameArgumentsGuard", count=1)
    elif name == "quickjs-interpreter.c.obj" and not msvc:
        if "JS_FrameConstructPolicyForArguments" in required:
            router.data_alias("JS_FrameConstructPolicyForArguments", "js_frame_construct_policy", 4)
        router.refs("JS_FrameCallEnvLinkMiss", "JS_FrameCallLinkPolicyLinkMiss", count=1)
        router.refs("JS_FrameVarargsOldValidate", "JS_FrameRegexpValidateSelect", count=1)
        router.refs("JS_FrameCallForwardNativeProbe", "JS_FrameArgumentsForwardProbe", count=1)
        router.branches("length_M_miss", "interp_slow", "JS_FrameArgumentsLengthClean")
        if diagnostics:
            if any(
                s["name"] == "length_P_miss" and s["section"] > 0
                for s in router.old.all_symbols.values()
            ):
                raise RuntimeError(
                    "Diagnostic length producer unexpectedly defines a dirty handler"
                )
            router.refs(
                "JS_FramePublishBefore_FrameProtoPersistentFill",
                "JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill",
                count=0,
                minimum=0,
            )
        else:
            router.branches("length_P_miss", "dirty_interp_slow", "JS_FrameArgumentsLengthDirty")
            router.refs(
                "JS_FramePublishBefore_FrameProtoPersistentFill",
                "JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill",
                count=1,
            )
    elif recipe.get("strict_identity_only") and recipe.get("strict_identity_calls"):
        # These C opcode executors retain every other route and instruction.
        # Their declared imports use the same consuming (ctx,sp,bool) ABI.
        pass
    else:
        raise RuntimeError(
            "Current-source retained route is not implemented: " + recipe["object_path"]
        )
    if recipe.get("strict_identity_calls"):
        router.refs("qjs_frame_core_js_strict_eq_slow", "JS_FrameStrictIdentitySlow", minimum=1)
    if recipe.get("array_own_calls"):
        router.refs(
            "qjs_frame_core_js_get_fast_array_element", "JS_FrameFastArrayOwnGet", minimum=1
        )
    return router.finish()
