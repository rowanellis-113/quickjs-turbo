"""Native JS->JS captured-readonly admission over the inherited frame builder. MIT."""

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
from pathlib import Path
from abi_layout import load as load_layout
import hashlib, importlib.util, json, re, struct, subprocess, time

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
CONTROL = "JS_FrameJSCapturedControl"


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "jscap_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def compile_extra(source, build, compiler, msvc, diagnostics):
    C = module(source, "object-adapter")
    families = ["M"]
    kind_offset = load_layout(source)["offsets"]["JSFunctionBytecode.byte_code_buf"] - 1
    pub = _frame_generated_file(build, "quickjs-interpreter-publish.obj")
    if (
        not msvc
        and pub.exists()
        and any(
            s["name"] == "publish_interp_meta_unready" and s["section"] > 0
            for s in C.Coff(pub.read_bytes()).all_symbols.values()
        )
    ):
        families += ["P"]
    blocks = []
    for tag in families:
        prefix = "JS_FrameJSCaptured" + tag
        fallback = prefix + "Fallback" if tag == "M" else "dirty_interp_slow"
        blocks.append(
            (
                prefix + "Try",
                [
                    f"movzx eax, BYTE PTR [r9+{kind_offset}]",
                    "and eax, 7",
                    "cmp eax, 7",
                    "jne " + fallback,
                    "cmp BYTE PTR [rip+" + CONTROL + "], 1",
                    "jne " + fallback,
                    f"test BYTE PTR [r9+{kind_offset}], 16",
                    "jz " + prefix + "Init",
                    "jmp " + prefix + "Ready",
                ],
            )
        )
    publisher = ["lea r11, [rip+" + CONTROL + "]", "xchg BYTE PTR [r11], cl", "ret"]
    external = [CONTROL, "JS_FrameInterpPropertyCold_unwind", "JS_FrameJSCapturedMFallback"] + [
        ("JS_FrameJSCaptured" + tag + suffix) for tag in families for suffix in ("Init", "Ready")
    ]
    if "P" in families:
        external += ["dirty_interp_slow"]
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n + ":BYTE" for n in external],
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
        ]
        for name, body in blocks + [("JS_FrameJSCapturedPublish", publisher)]:
            text += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            text += [
                re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", s.replace("rip+", "")) for s in body
            ]
            text += [name + "_end LABEL BYTE", name + " ENDP"]
        text += [
            "ALIGN 4",
            "JS_FrameJSCapturedPublish_unwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        for name, _ in blocks:
            text += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        text += [
            "DD IMAGEREL JS_FrameJSCapturedPublish, IMAGEREL JS_FrameJSCapturedPublish_end, IMAGEREL JS_FrameJSCapturedPublish_unwind",
            ".pdata$zzzzzznullfast ENDS",
            "END",
        ]
        asm = _frame_generated_file(build, "quickjs-interpreter-js-captured.asm")
        obj = asm.with_suffix(".obj")
        cmd = [compiler.with_name("ml64.exe"), "/nologo", "/c", "/Fo" + str(obj), asm]
    else:
        text = [".intel_syntax noprefix", '.section .qjzzva,"xr"']
        for name, body in blocks + [("JS_FrameJSCapturedPublish", publisher)]:
            text += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *body,
                name + "_end:",
            ]
        text += [
            ".p2align 2",
            "JS_FrameJSCapturedPublish_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _ in blocks:
            text += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
        text += [
            ".rva JS_FrameJSCapturedPublish, JS_FrameJSCapturedPublish_end, JS_FrameJSCapturedPublish_unwind",
            '.section .qjslcm$zzjscaptured,"dw"',
            ".globl " + CONTROL,
            CONTROL + ":",
            ".byte 255",
        ]
        asm = _frame_generated_file(build, "quickjs-interpreter-js-captured.S")
        obj = asm.with_suffix(".obj")
        cmd = [compiler, "-c", "-g0", asm, "-o", obj]
    asm.write_text("\n".join(text) + "\n", encoding="ascii")
    p = subprocess.run(list(map(str, cmd)), capture_output=True)
    asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (cmd, p.stdout, p.stderr)
    # The existing merger accepts REL32. This is the same exact typed
    # REL32_n -> REL32/addend conversion as call-link.py uses.
    co = C.Coff(obj.read_bytes())
    corrections = []
    for rec in co.section_records:
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                assert msvc
                value = struct.unpack_from("<i", co.data, rec["raw"] + off)[0]
                struct.pack_into("<i", co.data, rec["raw"] + off, value - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                corrections.append(
                    dict(
                        offset=off,
                        old_kind=kind,
                        new_kind=4,
                        old_addend=value,
                        new_addend=value - (kind - 4),
                    )
                )
    obj.write_bytes(co.finish())
    (_frame_generated_file(build, "quickjs-js-captured-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                generator_sha256=sha(__file__),
                families=families,
                bytecode_kind_offset=kind_offset,
                object=str(obj),
                object_sha256=sha(obj),
                asm_sha256=sha(asm),
                diagnostics=diagnostics,
                typed_relocation_corrections=corrections,
                contract="Only proved low-kind7. Same inherited arity/capacity/quota/poll/initialization/return guards. No call, RSP or nonvolatile write in admission; public C roots are unchanged.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, code_group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-js-captured.obj"),
        "JS_FrameJSCapturedMTry",
        "js-captured-admission",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$K",
        pdata_output=prefix + "1",
        writable_metadata_inputs=() if msvc else (".qjslcm$zzjscaptured",),
        base_owner=owner,
        baseline_sections=(),
    )


def append_control(source, build, path, raw):
    return module(source, "call-forward-native").append_control(
        source,
        build,
        path,
        raw,
        name=CONTROL,
        previous="JS_FrameCallForwardBorrowMissingControl",
        original_bytes=64,
    )


def adapt(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    meta = module(source, "call-metadata")
    raw, packing = meta.packed(raw, C)
    old = C.Coff(raw)
    co = C.Coff(raw)
    routes = []
    aliases = []

    def symbol(n, undefined=False):
        ss = [
            s
            for s in old.all_symbols.values()
            if s["name"] == n and (s["section"] > 0 or undefined)
        ]
        assert len(ss) == 1, (path, n, ss)
        return ss[0]

    def alias(n, s):
        r = bytearray(co.stride)
        at = len(co.strings)
        co.strings += n.encode() + b"\0"
        struct.pack_into("<III", r, 0, 0, at, s["value"])
        struct.pack_into("<i" if co.stride == 20 else "<h", r, 12, s["section"])
        r[co.class_offset] = 2
        co.aliases.append(r)
        aliases.append(dict(name=n, section=s["section"], value=s["value"]))

    for tag, prefix in (("M", ""), ("P", "publish_")):
        names = {s["name"] for s in old.all_symbols.values() if s["section"] > 0}
        if prefix + "interp_meta_unready" not in names:
            continue
        s = symbol(prefix + "interp_meta_unready")
        init = symbol(prefix + "JS_FrameInterpCallMeta_init")
        slow = symbol("interp_slow" if tag == "M" else "dirty_interp_slow", undefined=True)
        assert s["section"] == init["section"] and init["value"] == s["value"] + 22
        rec = co.section_records[s["section"] - 1]
        start = rec["raw"] + s["value"]
        code = raw[start : start + 22]
        assert code[:7] == bytes.fromhex("a9010000000f84") and code[11:18] == bytes.fromhex(
            "a9040000000f85"
        ), (path, tag, code.hex())
        operand = s["value"] + 18
        original_bytes = raw[rec["raw"] + operand : rec["raw"] + operand + 4]
        fields = [
            rec["reloc"] + 10 * i
            for i in range(rec["count"])
            if struct.unpack_from("<I", raw, rec["reloc"] + 10 * i)[0] == operand
        ]
        target = co.external("JS_FrameJSCaptured" + tag + "Try")
        if fields:
            assert len(fields) == 1
            at = fields[0]
            off, index, kind = struct.unpack_from("<IIH", raw, at)
            target_old = old.all_symbols[index]
            assert (
                kind == 4
                and target_old["section"] == slow["section"]
                and target_old["value"] + int.from_bytes(original_bytes, "little", signed=True)
                == slow["value"]
            )
            struct.pack_into("<I", co.data, at + 4, target)
            mode = "existing-rel32"
        else:
            assert (
                slow["section"] == s["section"]
                and operand + 4 + int.from_bytes(original_bytes, "little", signed=True)
                == slow["value"]
            )
            co.extra_relocations.setdefault(s["section"], []).append(
                struct.pack("<IIH", operand, target, 4)
            )
            mode = "decoded-rel32"
        co.data[rec["raw"] + operand : rec["raw"] + operand + 4] = bytes(4)
        destinations = [("Init", init), ("Ready", symbol(prefix + "interp_meta_ready"))]
        if tag == "M":
            destinations += [("Fallback", slow)]
        for suffix, target_symbol in destinations:
            alias("JS_FrameJSCaptured" + tag + suffix, target_symbol)
        routes.append(
            dict(
                tag=tag,
                section=s["section"],
                offset=operand,
                old_bytes=original_bytes.hex(),
                mode=mode,
                target="JS_FrameJSCaptured" + tag + "Try",
            )
        )
    if not routes:
        return raw, None
    result = co.finish()
    after = C.Coff(result)
    for i, (a, b) in enumerate(zip(old.section_records, after.section_records), 1):
        before = raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])
        code = bytearray(result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"]))
        for r in routes:
            if r["section"] == i:
                code[r["offset"] : r["offset"] + 4] = bytes.fromhex(r["old_bytes"])
        assert bytes(code) == before, ("Unlisted instruction/data change", path, i)
    for index, s in old.all_symbols.items():
        assert after.all_symbols[index] == s
    folder = _frame_generated_file(build, "js-captured-link") / str(time.time_ns())
    folder.mkdir(parents=True)
    (folder / "input.obj").write_bytes(raw)
    (folder / "output.obj").write_bytes(result)
    record = folder / "adapt.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                generator_sha256=sha(__file__),
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                packing=packing,
                routes=routes,
                aliases=aliases,
                original_symbols_unchanged=True,
                all_other_instruction_and_data_bytes_identical=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(record)
