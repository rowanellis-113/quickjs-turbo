"""Own per-function CallLinkInfo and route exact private weak-reset calls. MIT."""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
from native_abi import current as current_abi, source_abi
from abi_layout import load as load_layout
from native_build import source_digest, find_objdump
from pathlib import Path
import bisect, hashlib, importlib.util, json, re, struct, subprocess

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name, file):
    sp = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def adapt(source, object_path):
    C = module("call_link_coff", "object-adapter.py")
    input_raw = object_path.read_bytes()
    raw = module("call_link_core_layout", "core_routes").pack(input_raw)
    c = C.Coff(raw)
    before = C.Coff(raw)
    assert "qjs_frame_core_reset_weak_ref" not in c.symbols
    c.expose("reset_weak_ref")
    target = c.external("JS_FrameCallLinkResetWeak")
    owners = {}
    starts = {}
    for s in c.all_symbols.values():
        if s["section"] > 0 and s["type"] & 32:
            starts.setdefault((s["section"], s["value"]), []).append(s["name"])
    for (section, value), names in starts.items():
        # Exposed core aliases retain the exact original typed definition.
        # Attribute a shared start to that definition, not its appended alias.
        name = min(names, key=lambda value: (value.startswith("qjs_"), value))
        owners.setdefault(section, []).append((value, name))
    for v in owners.values():
        v.sort()

    def owner(si, offset):
        v = owners[si]
        i = bisect.bisect_right([x[0] for x in v], offset) - 1
        assert i >= 0
        return v[i][1]

    routes = []
    existing = set()
    for si, rec in enumerate(c.section_records, 1):
        if not rec["flags"] & 0x20:
            continue
        for i in range(rec["count"]):
            pos = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", c.data, pos)
            if kind != 4 or c.all_symbols[sym]["name"] != "reset_weak_ref":
                continue
            assert c.data[rec["raw"] + off - 1] in (0xE8, 0xE9)
            struct.pack_into("<I", c.data, pos + 4, target)
            existing.add((si, off))
            routes.append(
                dict(
                    section=si,
                    offset=off,
                    owner=owner(si, off - 1),
                    kind="existing-rel32",
                    old_symbol=sym,
                    new_symbol=target,
                )
            )
    f = c.symbols["reset_weak_ref"]
    si = f["section"]
    rec = c.section_records[si - 1]
    if c.sections[si - 1]["name"] == ".text":
        objdump = find_objdump(object_path.parent)
        listing = subprocess.check_output(
            [str(objdump), "-d", "-w", "-Mintel", "-j", ".text", str(object_path)], text=True
        )
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not m:
                continue
            off = int(m[1], 16)
            code = bytes.fromhex(m[2])
            if (
                len(code) != 5
                or code[0] not in (0xE8, 0xE9)
                or off + 5 + struct.unpack_from("<i", code, 1)[0] != f["value"]
            ):
                continue
            at = off + 1
            if (si, at) in existing:
                continue
            assert bytes(c.data[rec["raw"] + off : rec["raw"] + off + 5]) == code
            c.data[rec["raw"] + at : rec["raw"] + at + 4] = bytes(4)
            c.extra_relocations.setdefault(si, []).append(struct.pack("<IIH", at, target, 4))
            routes.append(
                dict(
                    section=si,
                    offset=at,
                    owner=owner(si, off),
                    kind="decoded-rel32",
                    old_bytes=code[1:].hex(),
                    new_symbol=target,
                )
            )
    if routes and routes[0]["kind"] == "existing-rel32":
        expected = {"JS_FreeAtomStruct", "free_object"}
    elif load_layout(source)["reference_count_model"] == "inline-header":
        expected = {"JS_FreeAtomStruct", "free_gc_object"}
    else:
        expected = {
            "JS_FreeAtomStruct",
            "__JS_FreeAtom",
            "JS_FreeAtom.part.0.isra.0",
            "free_gc_object",
        }
    assert len(routes) == len(expected) and {r["owner"] for r in routes} == expected, routes
    result = c.finish()
    check = C.Coff(result)
    for si, (oldrec, newrec) in enumerate(zip(before.section_records, check.section_records), 1):
        previous = (
            raw[oldrec["raw"] : oldrec["raw"] + oldrec["size"]]
            if oldrec["raw"]
            else bytes(oldrec["size"])
        )
        payload = bytearray(
            result[newrec["raw"] : newrec["raw"] + newrec["size"]]
            if newrec["raw"]
            else bytes(newrec["size"])
        )
        for route in routes:
            if route["section"] == si and route["kind"] == "decoded-rel32":
                at = route["offset"]
                payload[at : at + 4] = bytes.fromhex(route["old_bytes"])
        assert bytes(payload) == previous, ("Changes outside decoded weak-reset operands", si)
        oldrels = [
            struct.unpack_from("<IIH", raw, oldrec["reloc"] + 10 * i)
            for i in range(oldrec["count"])
        ]
        newrels = [
            list(struct.unpack_from("<IIH", result, newrec["reloc"] + 10 * i))
            for i in range(newrec["count"])
        ]
        for route in routes:
            if route["section"] != si:
                continue
            if route["kind"] == "existing-rel32":
                hit = [r for r in newrels if r[0] == route["offset"]]
                assert len(hit) == 1 and hit[0][1] == target
                hit[0][1] = route["old_symbol"]
            else:
                newrels.remove([route["offset"], target, 4])
        assert sorted(map(tuple, newrels)) == sorted(oldrels), ("Unlisted relocation changes", si)
    for index, s in before.all_symbols.items():
        assert check.all_symbols[index] == s, index
    backup = object_path.with_name(object_path.name + ".before-call-link")
    assert not backup.exists()
    backup.write_bytes(input_raw)
    object_path.write_bytes(result)
    object_path.with_name(object_path.name + ".call-link.json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=sha(backup),
                after_sha256=sha(object_path),
                routes=routes,
                original_symbols_unchanged=True,
                all_other_section_payloads_and_relocations_unchanged=True,
                source_sha256=sha(_frame_source_file(source, "quickjs.c")),
                generator_sha256=sha(__file__),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("CALL LINK WEAK RESET ROUTED", len(routes), flush=True)


def compile_backend(source, build, destination, *, msvc=False):
    C = module("call_link_compile_coff", "object-adapter.py")
    M = module("call_link_compiler", "atod.py")
    merge = module("call_link_merge", "extension-merge.py")
    output = _frame_generated_file(build, "quickjs-interpreter-call-link.obj")

    def generate(source, path):
        path.write_text(
            native_prelude(source)
            + '#include "src/x86/win64/common/quickjs-interpreter-call-link.inc"\n',
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-call-link.c",
        late_name=".qjssrc$C",
    )
    obj = C.Coff(output.read_bytes())
    for index, s in obj.all_symbols.items():
        if s["section"] > 0 and s["storage"] == 2 and not s["name"].startswith("JS_FrameCallLink"):
            name = "call_link_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
            at = len(obj.strings)
            obj.strings += name.encode() + b"\0"
            struct.pack_into("<II", obj.data, obj.table + index * obj.stride, 0, at)
    for number, rec in enumerate(obj.section_records, 1):
        name = merge.section_name(obj, number)
        if name == ".qjssrc$C" or name.startswith(".pdata"):
            # Compiler unwind records join the already owned RX carrier, as
            # the existing dense-pop/native contributions do. Keep their bytes.
            struct.pack_into("<I", obj.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    output.write_bytes(obj.finish())
    # Construction requires ResetWeak first. GNU links its native RX carrier
    # after the hot VM; MS retains the qualified Grouped section order.
    # This is a compiler-policy ablation, not a padding/address search.
    native_output = ".qjssrc$C" if msvc else ".qjssrc$Z"
    merge.append(
        destination,
        output,
        "JS_FrameCallLinkResetWeak",
        "call-link-native",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=native_output,
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameDenseArrayPop",
        baseline_sections=(),
        metadata_inputs=(".voltbl",) if msvc else (),
    )
    compile_vm_backend(source, build, destination, msvc=msvc)
    module("numeric_vm_invoke", "numeric-invoke.py").compile_backend(
        source, build, destination, msvc=msvc
    )
    (_frame_generated_file(build, "quickjs-call-link-native.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                source_sha256=sha(_frame_source_file(source, "quickjs.c")),
                header_sha256=sha(_frame_source_file(source, "quickjs-interpreter-call-link.h")),
                object_sha256=sha(output),
                destination_sha256=sha(destination),
                native_output_subsection=native_output,
                vm_output_subsection=".qjssrc$C",
                native_link_order_after_vm=not msvc,
                native_link_policy="grouped-exact" if msvc else "native-after-vm",
                scope="Owned call-site metadata, weak reset and cached prepared-frame VM kernels. Actual pre-link activation requires quickjs-call-link-vm-route.json; no performance result is inferred from compilation.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# Appended to the private call-link generator; all VM code stays out of the core.
def _function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


def native_prelude(source):
    text = _frame_source_text(source, "quickjs-interpreter-loop.h")
    parts = []
    for name in ("JSFrameSegment", "JSFrame", "JSFrameCallSite"):
        start = text.index("typedef struct " + name + " {")
        end = text.index("} " + name + ";", start) + len("} " + name + ";")
        parts.append(text[start:end])
    helpers = "".join(
        _function(text, "static FRAME_INLINE void " + name + "(")
        for name in ("js_frame_charge_stack", "js_frame_begin_c", "js_frame_finish_c")
    )
    return (
        """#include "quickjs-dense-array-pop-private.h"
#ifdef _MSC_VER
#define FRAME_INLINE __forceinline
#else
#define FRAME_INLINE inline __attribute__((always_inline))
#endif
#define FRAME_CACHE_SLOTS 16
"""
        + "\n".join(parts)
        + '\n#include "src/common/call/quickjs-interpreter-register.h"\n'
        + helpers
        + "\n"
    )


def _alias(coff, name, alias):
    matches = [s for s in coff.all_symbols.values() if s["name"] == name and s["section"] > 0]
    assert len(matches) == 1, (name, matches)
    s = matches[0]
    at = len(coff.strings)
    coff.strings += alias.encode() + b"\0"
    record = bytearray(coff.stride)
    struct.pack_into("<III", record, 0, 0, at, s["value"])
    struct.pack_into("<h", record, 12, s["section"])
    struct.pack_into("<H", record, 14, s["type"])
    record[coff.class_offset] = 2
    coff.aliases.append(record)
    return dict(name=name, alias=alias, section=s["section"], value=s["value"])


def _activation_ready(body):
    # Every replacement consumes the actual original ready sequence. No
    # guessed continuation offsets or independently restated old frame body.
    fields = current_abi()["offsets"]
    flags = current_abi()["bits"]["JSFunctionBytecode.is_strict_mode"][0][0]
    code = fields["JSFunctionBytecode.byte_code_buf"]
    body = list(body)

    def replace(old, new):
        found = [i for i in range(len(body) - len(old) + 1) if body[i : i + len(old)] == old]
        assert len(found) == 1, (old, found)
        at = found[0]
        body[at : at + len(old)] = new

    at = body.index(f"movzx eax, BYTE PTR [r9+{code - 3}]")
    assert body[at + 1] == "cmp ecx, eax" and body[at + 2].startswith("jae ")
    branch = body[at + 2].replace("jae ", "je ", 1)
    body[at : at + 3] = ["cmp BYTE PTR [rsp+45], 0", branch]
    at = body.index("shl rax, 4")
    body[at:at] = ["movd eax, xmm2", "shr eax, 16"]
    replace(
        [f"movzx eax, WORD PTR [r9+{code - 6}]", "sub eax, 32"], ["movzx eax, WORD PTR [rsp+40]"]
    )
    replace(
        [
            "mov eax, DWORD PTR [rsp+48]",
            "lea eax, [rax+rcx+1]",
            "or eax, DWORD PTR [rsp+52]",
            "mov WORD PTR [rbp+126], ax",
        ],
        ["movzx eax, WORD PTR [rsp+42]", "mov WORD PTR [rbp+126], ax"],
    )
    replace(
        [
            f"movzx edx, BYTE PTR [r9+{code - 3}]",
            "cmp edx, ecx",
            "cmovb edx, ecx",
            "mov WORD PTR [rax+58], dx",
            f"movzx edx, BYTE PTR [r9+{flags}]",
            "and edx, 1",
            "mov BYTE PTR [rax+60], dl",
        ],
        ["movq QWORD PTR [rax+56], xmm2"],
    )
    at = body.index(f"movzx edx, BYTE PTR [r9+{code - 3}]")
    assert body[at + 1] == "cmp ecx, edx" and body[at + 2].startswith("jae ")
    branch = body[at + 2].replace("jae ", "jz ", 1)
    body[at : at + 3] = ["movzx edx, BYTE PTR [rsp+45]", "test edx, edx", branch]
    replace(["add rdx, r15"], ["add rdx, r8"])
    substitutions = {f"[r9+{code - 4}]": "[rsp+44]", f"[r9+{code - 1}]": "[rsp+46]"}
    for old, new in substitutions.items():
        assert any(old in line for line in body), old
        body = [line.replace(old, new) for line in body]
    assert not any(
        f"[r9+{offset}]" in line
        for offset in (flags, code - 6, code - 4, code - 3, code - 1)
        for line in body
    )
    # xmm2 holds precomputed argc/strict. Fetch immutable codebuf from live b.
    assert body.count(f"mov r12, QWORD PTR [r9+{code}]") == 1
    return body, dict(
        schema="framebytes16/pending16/locals8/pad8/kind8/history8; SF argc/strict64",
        original_scalar_loads_folded=True,
    )


@source_abi
def _vm_blocks(source, build, *, msvc=False):
    fields = current_abi()["offsets"]
    flags = current_abi()["bits"]["JSFunctionBytecode.is_strict_mode"][0][0]
    code = fields["JSFunctionBytecode.byte_code_buf"]
    proof = json.loads(
        (_frame_generated_file(build, "quickjs-interpreter-call-link.compile.json")).read_text()
    )
    diagnostic = any("QJS_INTERP_FRAME_DIAGNOSTICS" in x for x in proof["compiler_command"])
    C = module("call_link_vm_coff", "object-adapter.py")
    reg = C.Coff((_frame_generated_file(build, "quickjs-interpreter-register.obj")).read_bytes())
    families = [
        (
            "M",
            "",
            reg,
            _frame_build_file(
                build,
                "quickjs-interpreter-register-win64.asm"
                if msvc
                else "quickjs-interpreter-register-win64.S",
            ),
        )
    ]
    pub = _frame_generated_file(build, "quickjs-interpreter-publish.obj")
    pubasm = _frame_generated_file(build, "quickjs-interpreter-publish-win64.S")
    if (
        not msvc
        and pub.exists()
        and "publish_interp_meta_ready:" in pubasm.read_text(encoding="utf-8")
    ):
        families.append(("P", "publish_", C.Coff(pub.read_bytes()), pubasm))
    admission_contracts = []
    blocks = []
    secondary_blocks = []
    aliases = {}
    external = {
        "JS_FrameCallLinkControl",
        "JS_FrameCallLinkMiss",
        "JS_FrameInterpPropertyCold_unwind",
    }
    native_limit = 2312 if diagnostic else 72
    for tag, prefix, coff, path in families:
        lines = path.read_text(encoding="utf-8").splitlines()

        def label(name):
            return next(
                i for i, line in enumerate(lines) if line.rstrip(":") == name and line.endswith(":")
            )

        lo = label(prefix + "interp_meta_ready")
        hi = label(prefix + "interp_meta_unready")
        body = lines[lo:hi]
        body = [
            line[:-1] if line.endswith("::") else line
            for line in body
            if not line.startswith(("PUBLIC ", ".globl "))
        ]
        local = {
            line[:-1]: "calllink_" + tag + "_" + line[:-1] for line in body if line.endswith(":")
        }
        local[prefix + "interp_meta_ready"] = "JS_FrameCallLink" + tag + "Ready"
        rx = re.compile(r"\b(?:" + "|".join(map(re.escape, local)) + r")\b")
        body = [rx.sub(lambda m: local[m[0]], line) for line in body]
        body, changes = _activation_ready(body)
        # Branches outside the cloned ready region retain the exact original slow paths.
        definitions = {s["name"] for s in coff.all_symbols.values() if s["section"] > 0}
        all_names = {s["name"] for s in coff.all_symbols.values()}
        references = set(re.findall(r"\b[A-Za-z_]\w*\b", "\n".join(body))) & all_names
        mapping = {
            name: "JS_FrameCallLinkOld" + tag + "_" + name
            for name in references
            if name in definitions
        }
        mapping[prefix + "interp_meta_prepare_call"] = "JS_FrameCallLinkOld" + tag + "_Prepare"
        aliases[tag] = [dict(name=name, alias=alias) for name, alias in mapping.items()]
        for name in references:
            external.add(mapping.get(name, name))
        external.add(mapping[prefix + "interp_meta_prepare_call"])
        if mapping:
            rename = re.compile(r"\b(?:" + "|".join(map(re.escape, mapping)) + r")\b")
            body = [rename.sub(lambda m: mapping[m[0]], line) for line in body]
        ready = "JS_FrameCallLink" + tag + "Ready"
        assert body[0] == ready + ":"
        blocks.append((ready, body[1:]))
        fallback = mapping[prefix + "interp_meta_prepare_call"]
        for name in (
            "call0",
            "call1",
            "call2",
            "call3",
            "call",
            "tail_call",
            "call_method",
            "tail_call_method",
        ):
            op = "JS_FrameCallLink" + tag + "_" + name
            argc = (
                "mov ecx, " + name[-1]
                if re.fullmatch(r"call[0-3]", name)
                else "movzx ecx, WORD PTR [r12+1]"
            )
            stream = [
                argc,
                "mov DWORD PTR [rsp+48], " + str(int(name.endswith("_method"))),
                "mov DWORD PTR [rsp+52], " + str(32768 if name.startswith("tail_") else 0),
                "mov DWORD PTR [rsp+56], " + str(1 if re.fullmatch(r"call[0-3]", name) else 3),
                "jmp JS_FrameCallLink" + tag + "Probe",
            ]
            blocks.append((op, stream))
        # Copy the actual original admission prefix, retaining exact class,
        # leaf and dirty-mode continuations. Eligible targets reach the link
        # cache with argv/rdx/r9 already valid; all other calls skip it entirely.
        first = label(prefix + "interp_meta_prepare_call")
        last = label(prefix + "interp_meta_ready")
        admission = [
            line[:-1] if line.endswith("::") else line
            for line in lines[first + 1 : last]
            if not line.startswith(("PUBLIC ", ".globl "))
        ]
        references = set(re.findall(r"\b[A-Za-z_]\w*\b", "\n".join(admission))) & all_names
        for name in references:
            if name in definitions:
                mapping.setdefault(name, "JS_FrameCallLinkOld" + tag + "_" + name)
            external.add(mapping.get(name, name))
        mapping[prefix + "interp_meta_ready"] = "JS_FrameCallLinkOld" + tag + "_Ready"
        external.add(mapping[prefix + "interp_meta_ready"])
        aliases[tag] = [dict(name=name, alias=alias) for name, alias in mapping.items()]
        rename = re.compile(r"\b(?:" + "|".join(map(re.escape, mapping)) + r")\b")
        admission = [rename.sub(lambda m: mapping[m[0]], line) for line in admission]
        ready_fallback = mapping[prefix + "interp_meta_ready"]
        # The exact original prefix establishes argv and the live OBJECT tag.
        # Only a miss may dereference the target's class/bytecode/native kind.
        split = next(
            i
            for i, line in enumerate(admission)
            if line.startswith(f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], ")
        )
        minimal, classification = admission[:split], admission[split:]
        assert minimal[:5] == [
            "mov r8, rcx",
            "shl r8, 4",
            "neg r8",
            "add r8, r13",
            "cmp DWORD PTR [r8-8], -1",
        ]
        assert (
            len(minimal) == 7
            and minimal[5].startswith("jne ")
            and minimal[6] == "mov rdx, QWORD PTR [r8-16]"
        )
        assert len(classification) == 7 + int(diagnostic) and classification[0].startswith(
            f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], "
        )
        assert classification[7:] == (["inc QWORD PTR [rbx+2376]"] if diagnostic else [])
        assert classification[1].startswith("jne ") and classification[2:6] == [
            f"mov r9, QWORD PTR [rdx+{fields['JSObject.u.func.function_bytecode']}]",
            f"movzx eax, BYTE PTR [r9+{code - 1}]",
            "and eax, 21",
            "cmp eax, 17",
        ]
        assert classification[6].startswith("jne ")
        assert not any(
            line.startswith(("call ", "push ", "pop ")) or "[rsp" in line or line.endswith(":")
            for line in classification
        )
        # rsp40 carries NULL=no owner, 1=unlinked site, otherwise a live entry.
        # The only fallthrough to its consumption is the seven pure original
        # classification instructions. Leaf/C/unready branches retain their
        # old destinations and NEVER return to the private miss continuation.
        admit = "calllink_" + tag + "_admit"
        no_entry = "calllink_" + tag + "_no_entry"
        no_link = "calllink_" + tag + "_no_link"
        miss = "calllink_" + tag + "_miss"
        hit = "calllink_" + tag + "_hit"
        secondary = "JS_FrameCallLink" + tag + "Secondary"
        mode = "calllink_" + tag + "_mode"
        no_owner = "calllink_" + tag + "_no_owner"
        probe = minimal + [
            "cmp BYTE PTR [rip+JS_FrameCallLinkControl], 1",
            "jne " + no_entry,
            "mov r10, QWORD PTR [rbp+8]",
            f"mov r10, QWORD PTR [r10+{fields['JSObject.first_weak_ref']}]",
            "test r10, r10",
            "jz " + no_entry,
            f"cmp DWORD PTR [r10], {0x4C4B0101}",
            "jne " + no_entry,
            "mov rax, QWORD PTR [r10+24]",
            "movzx eax, BYTE PTR [r12+rax]",
            "cmp eax, 255",
            "je " + no_link,
            "shl eax, 6",
            "lea r11, [r10+rax+64]",
            "cmp QWORD PTR [r11+32], rdx",
            "jne " + miss,
        ]
        # Zero-byte label: either live identity shares the existing hit body.
        probe += [hit + ":"]
        if diagnostic:
            probe += ["inc QWORD PTR [r10+32]", "inc QWORD PTR [rbx+2376]"]
        probe += ["mov r9, QWORD PTR [r11+40]"]
        if msvc:
            # Actual same-file ablation prefers the existing guarded Ready on
            # MSVC. It consumes the already validated live target and cached b;
            # all original arity/realm/quota/ownership checks remain in place.
            # Match the diagnostic's complete twenty-byte hit window.
            # These fifteen bytes follow an unconditional jump and never run.
            probe += ["jmp " + ready_fallback, "DB 15 DUP(90h)"]
        else:
            probe += [
                "mov rax, QWORD PTR [r11+56]",
                "mov QWORD PTR [rsp+40], rax",
                "movq xmm2, QWORD PTR [r11+48]",
                "jmp " + ready,
            ]
        # Preserve the complete miss-stub width and all later Probe labels.
        # GAS uses explicit rel32 bytes, independent of jump relaxation.
        miss_stub = (
            ["jmp " + secondary, "DB 5 DUP(90h)"]
            if msvc
            else [".byte 0xe9", ".long " + secondary + " - . - 4", ".byte 0x90, 0x90"]
        )
        probe += [
            miss + ":",
            *miss_stub,
            no_link + ":",
            "mov QWORD PTR [rsp+40], 1",
            "jmp " + admit,
            no_entry + ":",
            "mov QWORD PTR [rsp+40], 0",
            admit + ":",
            *classification,
            "cmp BYTE PTR [rip+JS_FrameCallLinkControl], 1",
            "jne " + mode,
            "mov r11, QWORD PTR [rsp+40]",
            "cmp r11, 1",
            "je " + ready_fallback,
            "test r11, r11",
            "jz " + no_owner,
            "cmp BYTE PTR [r11+63], 4",
            "jae " + ready_fallback,
            "jmp JS_FrameCallLink" + tag + "Cold",
            no_owner + ":",
            "mov rax, QWORD PTR [rbp+80]",
            f"test BYTE PTR [rax+{flags + 1}], 128",
            "jnz " + ready_fallback,
            "jmp JS_FrameCallLink" + tag + "Cold",
            mode + ":",
            "cmp BYTE PTR [rip+JS_FrameCallLinkControl], 0",
            "je JS_FrameCallLink" + tag + "Cold",
            "jmp " + ready_fallback,
        ]
        admission_contracts.append(
            dict(
                family=tag,
                original_asm=str(path),
                original_asm_sha256=sha(path),
                minimal_prefix=minimal,
                miss_classification=classification[:7],
                diagnostic_admission_counter=classification[7:],
                warm_target_compared_before_class=True,
                warm_ready_strategy="shared-original" if msvc else "packed-activation",
                unexecuted_hit_padding_bytes=15 if msvc else 0,
                secondary_blocks_after_all_primary_families=True,
                secondary_probe=dict(
                    block=secondary,
                    hit=hit,
                    admit=admit,
                    primary_miss_stub_bytes=10 if msvc else 7,
                    alternate_offset=24,
                    callee_offset=32,
                    blocked_sentinel=1,
                    primary_saved_before_secondary="rsp40",
                    primary_hit_instructions_unchanged=True,
                ),
                miss_scratch="rsp40:0=none,1=unlinked,else primary entry; consumed only after pure suffix",
                no_gc_or_c_in_fallthrough_suffix=True,
                original_leaf_c_unready_exits=[classification[1], classification[6]],
                original_ready_and_cold_fallbacks_retained=True,
            )
        )
        blocks.append(("JS_FrameCallLink" + tag + "Probe", probe))
        cold = [
            # Match the existing native root's 8KB physical margin before a new C call.
            "mov rax, rsp",
            "sub rax, QWORD PTR [rbx+32]",
            "jc " + fallback,
            "sub rax, 8192",
            "jc " + fallback,
            f"cmp rax, QWORD PTR [rbx+{native_limit}]",
            "jb " + fallback,
            "mov DWORD PTR [rsp+60], ecx",
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov eax, DWORD PTR [rsp+56]",
            "add rax, r12",
            "mov QWORD PTR [rbp+48], rax",
            "mov QWORD PTR [rbp+64], r13",
            "mov QWORD PTR [rbp+104], r13",
            "mov rax, QWORD PTR [rbx+56]",
            f"mov QWORD PTR [rax+{fields['JSRuntime.current_stack_frame']}], rbp",
        ]
        if tag == "P":
            cold += [
                "lea r10, [rip+JS_FramePublishDirtyTable]",
                "cmp rdi, r10",
                "jne calllink_P_clean",
                "lea rdi, [rip+JS_FramePublishTable]",
                "calllink_P_clean:",
            ]
            external.update(("JS_FramePublishDirtyTable", "JS_FramePublishTable"))
        cold += [
            "mov rcx, rbx",
            "mov edx, DWORD PTR [rsp+60]",
            "call JS_FrameCallLinkMiss",
            "mov ecx, DWORD PTR [rsp+60]",
            "jmp " + fallback,
        ]
        blocks.append(("JS_FrameCallLink" + tag + "Cold", cold))
        # No GC/C call or new frame. The original completed VM frame owns
        # this separately typed continuation and both outgoing targets.
        # Keep PRIMARY for the original cold-budget continuation, even
        # when r11 becomes NULL, sentinel1 or a nonmatching secondary.
        secondary_blocks.append(
            (
                secondary,
                [
                    "mov QWORD PTR [rsp+40], r11",
                    "mov r11, QWORD PTR [r11+24]",
                    "cmp r11, 1",
                    "jbe " + admit,
                    "cmp QWORD PTR [r11+32], rdx",
                    "jne " + admit,
                    "jmp " + hit,
                ],
            )
        )
    # Growing secondary cold continuations cannot split M/P primary families.
    blocks.extend(secondary_blocks)
    (_frame_generated_file(build, "quickjs-call-link-warm-contract.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                source_tree_sha256=source_digest(source),
                generator_sha256=sha(__file__),
                contracts=admission_contracts,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return blocks, aliases, external, diagnostic


def compile_vm_backend(source, build, destination, *, msvc=False):
    C = module("call_link_vm_compile_coff", "object-adapter.py")
    merge = module("call_link_vm_merge", "extension-merge.py")
    blocks, aliases, external, diag = _vm_blocks(source, build, msvc=msvc)
    proof = json.loads(
        (_frame_generated_file(build, "quickjs-interpreter-call-link.compile.json")).read_text()
    )
    compiler = Path(proof["compiler_command"][0])
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-call-link-vm.asm" if msvc else "quickjs-interpreter-call-link-vm.S",
    )
    obj = _frame_generated_file(build, "quickjs-interpreter-call-link-vm.obj")
    opcode_sizes = [
        int(size)
        for name, size in re.findall(
            r"^\s*DEF\(\s*(\w+)\s*,\s*(\d+)",
            _frame_source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8"),
            re.M,
        )
    ]
    assert opcode_sizes and all(0 < size < 256 for size in opcode_sizes)
    if msvc:
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *[
                "EXTERN " + name + (":PROC" if name == "JS_FrameCallLinkMiss" else ":BYTE")
                for name in sorted(external)
            ],
            ".qjssrc$C SEGMENT ALIGN(16) 'CODE'",
        ]
        for name, stream in blocks:
            lines += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in stream:
                line = line.replace("rip+", "")
                if line.endswith(":"):
                    lines += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                else:
                    lines.append(re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", line))
            lines += [name + "_end LABEL BYTE", name + " ENDP"]
        lines += [
            "PUBLIC JS_FrameCallLinkOpcodeSizes",
            "JS_FrameCallLinkOpcodeSizes LABEL BYTE",
            *[
                "DB " + ",".join(map(str, opcode_sizes[i : i + 16]))
                for i in range(0, len(opcode_sizes), 16)
            ],
            ".qjssrc$C ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        for name, _ in blocks:
            lines += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        lines += [".pdata$zzzzzznullfast ENDS", "END"]
        cmd = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        lines = [".intel_syntax noprefix", '.section .qjssrc$C,"xr"']
        for name, stream in blocks:
            lines += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
            ]
            for line in stream:
                if line.endswith(":"):
                    lines += [".globl " + line[:-1]]
                lines.append(line)
            lines += [name + "_end:"]
        lines += [
            ".globl JS_FrameCallLinkOpcodeSizes",
            "JS_FrameCallLinkOpcodeSizes:",
            ".byte " + ",".join(map(str, opcode_sizes)),
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _ in blocks:
            lines += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
        cmd = [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    p = subprocess.run(cmd, capture_output=True)
    asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (cmd, (p.stdout + p.stderr).decode(errors="replace"))
    co = C.Coff(obj.read_bytes())
    corrections = []
    for rec in co.section_records:
        for i in range(rec["count"]):
            pos = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", co.data, pos)
            if 5 <= kind <= 9:
                assert msvc
                at = rec["raw"] + off
                value = struct.unpack_from("<i", co.data, at)[0]
                struct.pack_into("<i", co.data, at, value - (kind - 4))
                struct.pack_into("<H", co.data, pos + 8, 4)
                corrections.append(dict(offset=off, kind=kind))
        if merge.section_name(
            co, co.section_records.index(rec) + 1
        ) == ".qjssrc$C" or merge.section_name(co, co.section_records.index(rec) + 1).startswith(
            ".pdata"
        ):
            struct.pack_into("<I", co.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    obj.write_bytes(co.finish())
    merge.append(
        destination,
        obj,
        "JS_FrameCallLinkM_call0",
        "call-link-vm",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameCallLinkResetWeak",
        baseline_sections=(),
    )
    (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                diagnostics=diag,
                msvc=msvc,
                asm=str(asm),
                asm_sha256=sha(asm),
                object=str(obj),
                object_sha256=sha(obj),
                aliases=aliases,
                blocks=[name for name, _ in blocks],
                rel32_corrections=corrections,
                scope="Two-target PIC, secondary probe on primary mismatch only; original quota/ownership/arity/realm rules; weak target invalidation; four-miss cap per actual call site; bytecode PC index, variable owner size, byte17-bit7 optional-allocation backoff. Opcode sizes are readonly data after the final ended VM block. No old VM instruction body edits. Entry relocation and one-byte control carrier are finalized at pre-link.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _control(coff, raw, numeric_state=False):
    symbols = [
        s
        for s in coff.all_symbols.values()
        if s["name"] == "JS_FrameCallbackControl" and s["section"] > 0
    ]
    assert len(symbols) == 1
    sn = symbols[0]["section"]
    rec = coff.section_records[sn - 1]
    assert rec["flags"] & 0xE0000000 == 0xC0000000 and not rec["count"]
    before = raw[rec["raw"] : rec["raw"] + rec["size"]]
    payload = before + b"\0"
    offset = len(before)
    at = len(coff.strings)
    coff.strings += b"JS_FrameCallLinkControl\0"
    symbol = bytearray(coff.stride)
    struct.pack_into("<III", symbol, 0, 0, at, offset)
    struct.pack_into("<h", symbol, 12, sn)
    symbol[coff.class_offset] = 2
    coff.aliases.append(symbol)
    if numeric_state:
        # Preserve the original link-control offset. New MS-only numeric
        # state follows every inherited byte in this already owned section.
        for name, align, size in (
            ("JS_FrameNumericInvokeControl", 1, 1),
            ("JS_FrameNativeCScopeControl", 1, 1),
            ("JS_FrameNumericInvokeHits", 8, 8),
            *(
                (name, 8, 8)
                for name in module("native_scope_control", "native-c-scope.py").COUNTERS
            ),
        ):
            value = (len(payload) + align - 1) & ~(align - 1)
            payload += bytes(value - len(payload) + size)
            at = len(coff.strings)
            coff.strings += name.encode() + b"\0"
            added = bytearray(coff.stride)
            struct.pack_into("<III", added, 0, 0, at, value)
            struct.pack_into("<h", added, 12, sn)
            added[coff.class_offset] = 2
            coff.aliases.append(added)
    value = len(payload)
    payload += b"\0"
    at = len(coff.strings)
    coff.strings += b"JS_FrameCallLinkBacklinkControl\0"
    added = bytearray(coff.stride)
    struct.pack_into("<III", added, 0, 0, at, value)
    struct.pack_into("<h", added, 12, sn)
    added[coff.class_offset] = 2
    coff.aliases.append(added)
    if numeric_state:
        payload += bytes((-len(payload)) % 8)  # Preserve the following uint64 metadata alignment.
    for index, s in coff.all_symbols.items():
        at = coff.table + index * coff.stride
        if (
            s["section"] == sn
            and s["storage"] == 3
            and s["type"] == 0
            and raw[at + coff.class_offset + 1]
        ):
            struct.pack_into("<I", coff.data, at + coff.stride, len(payload))
    return sn, rec, payload


def route_vm(source, build):
    C = module("call_link_vm_route_coff", "object-adapter.py")
    generation = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text()
    )
    assert generation["status"] == "passed"
    paths = [_frame_generated_file(build, "quickjs-interpreter-register.obj")]
    if "P" in generation["aliases"]:
        paths += [_frame_generated_file(build, "quickjs-interpreter-publish.obj")]
    glob = _frame_generated_file(build, "quickjs-interpreter-global-binding.obj")
    if glob.exists():
        paths.append(glob)
    rx = re.compile(r"^(publish_)?interp_meta_(call[0-3]?|call_method|tail_call|tail_call_method)$")
    records = []
    for path in paths:
        raw = path.read_bytes()
        c = C.Coff(raw)
        before = C.Coff(raw)
        routes = []
        added = []
        if path.name == "quickjs-interpreter-register.obj":
            tag = "M"
        elif path.name == "quickjs-interpreter-publish.obj":
            tag = "P"
        else:
            tag = None
        if tag:
            for row in generation["aliases"][tag]:
                added.append(_alias(c, row["name"], row["alias"]))
        targets = {
            (s["section"], s["value"]): s["name"]
            for s in c.all_symbols.values()
            if s["section"] > 0 and rx.fullmatch(s["name"])
        }
        for si, rec in enumerate(c.section_records, 1):
            name = before.sections[si - 1]["name"]
            if name.startswith("/"):
                at = int(name[1:])
                name = c.strings[at : c.strings.index(0, at)].decode()
            if name.startswith((".pdata", ".xdata", ".debug")):
                continue
            for i in range(rec["count"]):
                pos = rec["reloc"] + 10 * i
                off, index, kind = struct.unpack_from("<IIH", c.data, pos)
                sym = c.all_symbols[index]
                matched = sym["name"] if rx.fullmatch(sym["name"]) else None
                if kind == 1 and off + 8 <= rec["size"]:
                    width = 8
                    addend = struct.unpack_from("<q", c.data, rec["raw"] + off)[0]
                elif kind in (2, 3, 4, 5, 6, 7, 8, 9) and off + 4 <= rec["size"]:
                    width = 4
                    addend = struct.unpack_from("<i", c.data, rec["raw"] + off)[0]
                else:
                    continue
                if sym["section"] > 0:
                    matched = targets.get((sym["section"], sym["value"] + addend), matched)
                if not matched:
                    continue
                m = rx.fullmatch(matched)
                newname = "JS_FrameCallLink" + ("P" if m[1] else "M") + "_" + m[2]
                target = c.external(newname)
                routes.append(
                    dict(
                        section=si,
                        section_name=name,
                        offset=off,
                        kind=kind,
                        width=width,
                        old_symbol=index,
                        old_addend=addend,
                        target=newname,
                    )
                )
                struct.pack_into("<I", c.data, pos + 4, target)
                c.data[rec["raw"] + off : rec["raw"] + off + width] = bytes(width)
        control = (
            _control(c, raw, numeric_state=generation["msvc"])
            if path.name == "quickjs-interpreter-register.obj"
            else None
        )
        result = bytearray(c.finish())
        if control:
            sn, rec, payload = control
            old_end = before.string_offset + struct.unpack_from("<I", raw, before.string_offset)[0]
            tail_shift = len(result) - len(raw)
            pa = c.table
            for rr in c.section_records:
                for field in (20, 24, 28):
                    at = rr["pos"] + field
                    v = struct.unpack_from("<I", raw, at)[0]
                    if not v:
                        continue
                    if v >= old_end:
                        v += tail_shift
                    if v >= pa:
                        v += len(payload)
                    struct.pack_into("<I", result, at, v)
            result[pa:pa] = payload
            struct.pack_into("<I", result, c.table_offset, c.table + len(payload))
            struct.pack_into("<II", result, rec["pos"] + 16, len(payload), pa)
        check = C.Coff(result)
        assert all(check.all_symbols[index] == s for index, s in before.all_symbols.items())
        for si, (a, b) in enumerate(zip(before.section_records, check.section_records), 1):
            old = raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])
            new = bytearray(
                result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"])
            )
            if control and si == control[0]:
                assert new == control[2]
                continue
            for route in routes:
                if route["section"] == si:
                    off = route["offset"]
                    new[off : off + route["width"]] = old[off : off + route["width"]]
            assert bytes(new) == old, (path, si, "outside routed data/relocation addends")
        for si, (a, b) in enumerate(zip(before.section_records, check.section_records), 1):
            oldrels = [
                struct.unpack_from("<IIH", raw, a["reloc"] + 10 * i) for i in range(a["count"])
            ]
            newrels = [
                list(struct.unpack_from("<IIH", result, b["reloc"] + 10 * i))
                for i in range(b["count"])
            ]
            for route in routes:
                if route["section"] != si:
                    continue
                hits = [r for r in newrels if r[0] == route["offset"]]
                assert (
                    len(hits) == 1
                    and check.all_symbols[hits[0][1]]["name"] == route["target"]
                    and hits[0][2] == route["kind"]
                )
                hits[0][1] = route["old_symbol"]
            assert list(map(tuple, newrels)) == oldrels, (path, si, "unlisted relocation changes")
        backup = path.with_name(path.name + ".before-call-link-vm")
        assert not backup.exists()
        backup.write_bytes(raw)
        stamp = path.stat()
        path.write_bytes(result)
        import os

        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        records.append(
            dict(
                path=str(path),
                before_sha256=sha(backup),
                after_sha256=sha(path),
                aliases=added,
                routes=routes,
                control_bytes=len(control[2]) - before.section_records[control[0] - 1]["size"]
                if control
                else 0,
            )
        )
    assert sum(len(r["routes"]) for r in records) == (40 if "P" in generation["aliases"] else 8)
    (_frame_generated_file(build, "quickjs-call-link-vm-route.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                records=records,
                generation_sha256=sha(
                    _frame_generated_file(build, "quickjs-call-link-vm-generation.json")
                ),
                source_tree_sha256=source_digest(source),
                policy="Only eight static call table references and, on GNU release, 32 runtime selector LEAs; one natural byte appended to existing RW carrier. Original symbol names/classes/values and other section payloads preserved; the owning section auxiliary length reflects its one-byte growth.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("CALL LINK VM ROUTED", sum(len(r["routes"]) for r in records), flush=True)


def restore_vm(source, build):
    import os, shutil, time

    receipt = _frame_generated_file(build, "quickjs-call-link-vm-route.json")
    if not receipt.exists():
        return
    state = json.loads(receipt.read_text())
    assert state["status"] == "passed"
    history = _frame_build_file(build, "call-link-vm-history") / (
        sha(receipt) + "-" + str(time.time_ns())
    )
    history.mkdir(parents=True, exist_ok=False)
    C = module("call_link_vm_restore_coff", "object-adapter.py")
    for row in state["records"]:
        path = Path(row["path"]).resolve()
        assert path.parent == _frame_generated_file(build, "").resolve()
        backup = path.with_name(path.name + ".before-call-link-vm")
        assert sha(backup) == row["before_sha256"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == row["after_sha256"]:
            stamp = path.stat()
            path.write_bytes(backup.read_bytes())
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        elif digest != row["before_sha256"]:
            c = C.Coff(raw)
            assert not any(
                s["name"].startswith("JS_FrameCallLinkOld")
                or s["name"] == "JS_FrameCallLinkControl"
                for s in c.all_symbols.values()
            ), ("Unknown adapted VM object", path)
        shutil.copyfile(backup, history / backup.name)
        backup.unlink()
    shutil.copyfile(receipt, history / receipt.name)
    receipt.unlink()
    print("CALL LINK VM EPOCH RESTORED", flush=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--route-vm", action="store_true")
    ap.add_argument("--restore-vm", action="store_true")
    a = ap.parse_args()
    assert a.route_vm != a.restore_vm
    (route_vm if a.route_vm else restore_vm)(a.source, a.build)
