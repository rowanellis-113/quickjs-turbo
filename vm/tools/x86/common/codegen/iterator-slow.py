"""Reuse the dense-array guard at the inherited C slow-dispatch call site.

The caller owns SF/PC/SP publication and its C quota boundary. This helper
commits only idx/value/done on a hit; completion and every miss use the exact
original helper selected by the extracted private header, with its typed ABI.
"""

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
import argparse, hashlib, json, struct

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    import importlib.util

    sp = importlib.util.spec_from_file_location(
        "iterator_slow_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def expose_legacy(source, build):
    adapter = module(source, "object-adapter")
    parent = module(source, "iterator")
    path = _frame_generated_file(build, "quickjs-interpreter-iterator.obj")
    raw = path.read_bytes()
    coff = adapter.Coff(raw)
    alias = "qjs_frame_iterator_legacy_next"
    if alias in {x["name"] for x in coff.all_symbols.values()}:
        return alias
    if "js_for_of_next" not in coff.symbols:
        # The extractor imports an exact original helper when the core
        # compiler emits it. Do not require a second private copy, or select
        # an arbitrary constprop clone whose argument contract may differ.
        target = "qjs_frame_core_js_for_of_next"
        imported = next(symbol for symbol in coff.all_symbols.values() if symbol["name"] == target)
        assert imported["section"] == 0 and imported["type"] & 32
        header = _frame_generated_file(build, "quickjs-iterator-private.h").read_text(
            encoding="utf-8"
        )
        assert "#define js_for_of_next " + target in header
        assert (
            "extern __exception int js_for_of_next(JSContext *ctx, JSValue *sp, int offset);"
            in header
        )
        core_path = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
        core = adapter.Coff(core_path.read_bytes())
        provider = next(symbol for symbol in core.all_symbols.values() if symbol["name"] == target)
        assert provider["section"] > 0 and provider["type"] & 32 and provider["storage"] == 2
        raw_core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
        start = raw_core.index("static __exception int js_for_of_next(")
        end = raw_core.index("\n}\n", start) + 3
        (
            _frame_generated_file(build, "quickjs-interpreter-iterator-legacy-provider.json")
        ).write_text(
            json.dumps(
                dict(
                    status="verified-original-core-provider",
                    target=target,
                    prototype="int (JSContext *, JSValue *, int)",
                    core_object=str(core_path),
                    core_object_sha256=sha(core_path),
                    definition=provider,
                    pinned_helper_source_sha256=hashlib.sha256(
                        raw_core[start:end].encode()
                    ).hexdigest(),
                ),
                indent=2,
            )
            + "\n"
        )
        return target
    # Append a public alias, preserving the local symbol/COMDAT identity.
    symbol = coff.symbols["js_for_of_next"]
    at = len(coff.strings)
    coff.strings += alias.encode() + b"\0"
    entry = bytearray(coff.stride)
    struct.pack_into("<III", entry, 0, 0, at, symbol["value"])
    big = coff.stride == 20
    struct.pack_into("<i" if big else "<h", entry, 12, symbol["section"])
    struct.pack_into("<H", entry, 16 if big else 14, 32)
    entry[coff.class_offset] = 2
    coff.aliases.append(entry)
    parent.finish_preserving_tail(coff, raw, path)
    return alias


def generate(source, build, out):
    inherited = _frame_generated_file(build, "quickjs-interpreter-iterator-fast.c")
    text = inherited.read_text(encoding="utf-8")
    prefix = text[: text.index("#define ITERATOR_KIND(b)")].replace(
        'section(".qjsitfa")', 'section(".qjsitsl")'
    )
    start = text.index("    JSObject *method,*iterator,*array;")
    end = text.index("    frame->saved_sp=sp;", start)
    guard = text[start:end]
    declaration = guard[: guard.index("    if (!(ITERATOR_KIND(b)&2)")]
    checks = guard[len(declaration) :]
    body = r"""
#define ITERATOR_KIND(b) (((unsigned char *)(b))[offsetof(JSFunctionBytecode,byte_code_buf)-2])
_Static_assert(sizeof(JSGCObjectHeader)==QJS_ABI_SIZE_JSGCObjectHeader &&
               offsetof(JSFunctionBytecode,byte_code_buf)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,
               "slow iterator controls occupy measured bytecode padding");
extern int qjs_frame_iterator_legacy_next(JSContext *ctx,JSValue *sp,int offset);
FRAME_CODE int JS_FrameIteratorSlowNext(JSContext *ctx,JSValue *sp,int offset)
{
    JSStackFrame *sf=ctx->rt->current_stack_frame;
    JSFunctionBytecode *b;
    JSObject *function;
DECLARATION
    /* No upcast of an arbitrary public stack frame to the private frame ABI.
       The active function is a strong root and supplies its live bytecode. */
    if (!sf || !JS_IsObject(sf->cur_func))goto slow;
    function=JS_VALUE_GET_OBJ(sf->cur_func);
    if (function->class_id!=JS_CLASS_BYTECODE_FUNCTION)goto slow;
    b=function->u.func.function_bytecode;
    if ((ITERATOR_KIND(b)&3)!=3)goto slow;
    /* Scope the ablation to bytecodes that actually reach this call site.
       Ordinary roots and inherited validation entries remain untouched. */
    if (!(ITERATOR_KIND(b)&16)) {
        ITERATOR_KIND(b)|=16;
        if (!getenv("QJS_DISABLE_FRAME_ARRAY_ITERATOR_SLOW"))ITERATOR_KIND(b)|=8;
    }
    if (!(ITERATOR_KIND(b)&8))goto slow;
CHECKS
    it->idx=idx+1;
    sp[0]=js_dup(array->u.array.u.values[idx]);
    sp[1]=js_bool(false);
    return 0;
slow:
    return qjs_frame_iterator_legacy_next(ctx,sp,offset);
}
""".replace("DECLARATION", declaration.rstrip()).replace("CHECKS", checks.rstrip())
    legacy_target = expose_legacy(source, build)
    body = body.replace("qjs_frame_iterator_legacy_next", legacy_target)
    out.write_text(prefix + body, encoding="utf-8")
    (_frame_generated_file(build, "quickjs-interpreter-iterator-slow-source.json")).write_text(
        json.dumps(
            dict(
                generated_sha256=sha(out),
                inherited_fast_source_sha256=sha(inherited),
                guard_source_sha256=hashlib.sha256(guard.encode()).hexdigest(),
                guard_policy="Byte-for-byte inherited live array guards, plus independent C-slow ablation.",
                configuration_bits=dict(
                    inherited_extended=1,
                    inherited_array_enabled=2,
                    inherited_initialized=4,
                    slow_enabled=8,
                    slow_initialized=16,
                ),
                ownership="Commit idx and two existing stack slots only; original caller owns publication, quota, completion and exceptions.",
                legacy_alias=legacy_target,
                legacy_provider="Verified exact original core helper or the inherited private js_for_of_next copy; unchanged typed ABI.",
            ),
            indent=2,
        )
        + "\n"
    )


def compile_extra(source, build, out):
    compiler = module(source, "atod")
    old = compiler.win_argv
    compiler.win_argv = lambda command: [x for x in old(command) if not x.startswith("-g")] + [
        "-g0"
    ]
    compiler.compile_extra(
        source,
        build,
        out,
        generator=lambda src, target: generate(src, build, target),
        filename="quickjs-interpreter-iterator-slow.c",
        late_name=".qjsitsl",
    )
    adapter = module(source, "object-adapter")
    coff = adapter.Coff(out.read_bytes())
    for rec in coff.section_records:
        for i in range(rec["count"]):
            off, sym, kind = struct.unpack_from("<IIH", coff.data, rec["reloc"] + 10 * i)
            assert kind != 1, (
                "New slow iterator bridge must not add ADDR64 relocations",
                off,
                coff.all_symbols[sym]["name"],
            )
    for sn, (sec, rec) in enumerate(zip(coff.sections, coff.section_records), 1):
        name = sec["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = coff.strings[at : coff.strings.index(0, at)].decode()
        if not name.startswith(".pdata"):
            continue
        at = len(coff.strings)
        coff.strings += b".pdata$zzzzzzzzzzzzzzzzfast2\0"
        coff.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
        for index, symbol in coff.all_symbols.items():
            if (
                symbol["section"] == sn
                and symbol["name"] == name
                and symbol["storage"] == 3
                and symbol["type"] == 0
            ):
                struct.pack_into("<II", coff.data, coff.table + index * coff.stride, 0, at)
    out.write_bytes(coff.finish())
    record = out.with_suffix(".compile.json")
    j = json.loads(record.read_text())
    j.update(
        object_sha256=sha(out),
        no_absolute64_relocations=True,
        pdata_policy="After inherited .qjsitfa ranges.",
    )
    record.write_text(json.dumps(j, indent=2) + "\n")


def route(source, paths, objdump):
    parent = module(source, "iterator")
    for path in paths:
        adapter = module(source, "object-adapter")
        coff = adapter.Coff(path.read_bytes())
        target = "js_for_of_next"
        if target not in coff.symbols:
            target = "qjs_frame_core_js_for_of_next"
            imported = next(
                symbol for symbol in coff.all_symbols.values() if symbol["name"] == target
            )
            assert imported["section"] == 0 and imported["type"] & 32
            provider = json.loads(
                path.parent.joinpath(
                    "quickjs-interpreter-iterator-legacy-provider.json"
                ).read_text()
            )
            assert (
                provider["status"] == "verified-original-core-provider"
                and provider["target"] == target
            )
        parent.route(
            path,
            source,
            objdump,
            targets={target: "JS_FrameIteratorSlowNext"},
            caller="JS_FrameIteratorSlow",
            label="iterator-slow",
        )
        receipt = json.loads(path.with_name(path.name + ".iterator-slow.json").read_text())
        assert len(receipt["routes"]) == 1 and receipt["caller"] == "JS_FrameIteratorSlow", receipt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--objdump", type=Path)
    ap.add_argument("--route", nargs="*", type=Path)
    a = ap.parse_args()
    if a.compile:
        compile_extra(a.source, a.build, a.out)
    else:
        assert a.route and a.objdump
        route(a.source, a.route, a.objdump)
