"""Guarded live array steps and a leaf route for ordinary root slow paths.

Keep the inherited iteration island compiled unchanged. New helpers reside in
one later island; only decoded inherited call destinations are redirected.
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
from abi_layout import load as load_layout
import argparse, hashlib, json, re, struct, subprocess
from pathlib import Path

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    import importlib.util

    sp = importlib.util.spec_from_file_location(
        "iterator_fast_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    result = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(result)
    return result


def function(text, signature):
    start = text.index(signature)
    begin = text.index("{", start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


def generate(source, build, out):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    inherited = _frame_source_text(source, "quickjs-interpreter-loop.h")
    types = inherited[
        inherited.index("typedef struct JSFrameSegment {") : inherited.index(
            "\n/* Ordinary native frames"
        )
    ]
    start = inherited.index("typedef struct JSFrameCallSite {")
    end = inherited.index("} JSFrameCallSite;", start) + len("} JSFrameCallSite;")
    types += "\n" + inherited[start:end] + "\n"
    start = core.index("typedef struct JSArrayIteratorData {")
    end = core.index("} JSArrayIteratorData;", start) + len("} JSArrayIteratorData;")
    array = core[start:end] + "\n"
    charge = function(inherited, "static FRAME_INLINE void js_frame_charge_stack(")
    boundaries = function(inherited, "static FRAME_INLINE void js_frame_begin_c(") + function(
        inherited, "static FRAME_INLINE void js_frame_finish_c("
    )
    start = core.index(
        "static JSValue js_array_iterator_next(", core.index("typedef struct JSArrayIteratorData {")
    )
    declaration = (
        core[start : core.index("{", start)]
        .strip()
        .replace("static JSValue", "extern JSValue", 1)
        .replace("js_array_iterator_next(", "qjs_frame_core_js_array_iterator_next(", 1)
        + ";\n"
    )
    prefix = '#include "quickjs-iterator-private.h"\n#define FRAME_INLINE inline __attribute__((always_inline))\n#define FRAME_CODE __attribute__((section(".qjsitfa"),noipa))\n'
    body = r"""
#define ITERATOR_KIND(b) (((unsigned char *)(b))[offsetof(JSFunctionBytecode,byte_code_buf)-2])
_Static_assert(sizeof(JSGCObjectHeader)==QJS_ABI_SIZE_JSGCObjectHeader &&
               offsetof(JSFunctionBytecode,byte_code_buf)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,
               "iterator flags occupy measured bytecode padding");
_Static_assert(offsetof(JSStackFrame,is_strict_mode)+2==62,
               "leaf selector reads inherited root padding marker");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
_Static_assert(offsetof(JSFrameRegisterState,exception_pending)==2296,
               "leaf selector reads diagnostic exception flag");
#else
_Static_assert(offsetof(JSFrameRegisterState,exception_pending)==160,
               "leaf selector reads release exception flag");
#endif
extern bool JS_FrameIteratorValidateSelect(JSFunctionBytecode *b);
extern int JS_FrameIteratorOp_for_of_next(JSFrameRegisterState *state);
/* Bit0 is inherited extended qualification. Bit2 publishes initialization;
   bit1 enables this guard. Configuration belongs to the live bytecode. */
FRAME_CODE bool JS_FrameIteratorFastValidateSelect(JSFunctionBytecode *b)
{
    bool supported=JS_FrameIteratorValidateSelect(b);
    if (supported && ITERATOR_KIND(b) && !(ITERATOR_KIND(b)&4))
        ITERATOR_KIND(b)|=4|(getenv("QJS_DISABLE_FRAME_ARRAY_ITERATOR")==NULL ? 2 : 0);
    return supported;
}
/* No guard commits state, invokes JS, allocates or releases a reference.
   Misses tail-return through the inherited next helper, including completion.
   On a hit the existing opcode entry already publishes SF/PC/SP. */
FRAME_CODE int JS_FrameIteratorArrayNext(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSFunctionBytecode *b=frame->bytecode;
    JSValue *sp=state->sp;
    uint8_t *pc=state->pc+2;
    int offset=-3-state->pc[1];
    JSObject *method,*iterator,*array;
    JSArrayIteratorData *it;
    JSShapeProperty *first;
    JSValue length;
    uint32_t idx;
    __typeof__(&qjs_frame_core_js_array_iterator_next) expected_next;
    if (!(ITERATOR_KIND(b)&2) || !JS_IsObject(sp[offset]) || !JS_IsObject(sp[offset+1]))goto slow;
    /* Materialize this inherited function address with a RIP-relative LEA.
       A MinGW refptr would add an absolute relocation beyond the PE script's
       .reloc position. This new island needs no loader fixups. */
    __asm__("lea qjs_frame_core_js_array_iterator_next(%%rip), %0" : "=r"(expected_next));
    method=JS_VALUE_GET_OBJ(sp[offset+1]);
    if (method->class_id!=JS_CLASS_C_FUNCTION || method->u.cfunc.cproto!=JS_CFUNC_iterator_next ||
        method->u.cfunc.c_function.iterator_next!=expected_next)goto slow;
    iterator=JS_VALUE_GET_OBJ(sp[offset]);
    if (iterator->class_id!=JS_CLASS_ARRAY_ITERATOR)goto slow;
    it=iterator->u.array_iterator_data;
    if (!it || it->kind!=JS_ITERATOR_KIND_VALUE || !JS_IsObject(it->obj))goto slow;
    array=JS_VALUE_GET_OBJ(it->obj);
    if (array->class_id!=JS_CLASS_ARRAY || !array->fast_array || array->shape->prop_count<1)goto slow;
    first=get_shape_prop(array->shape);
    if (first->atom!=JS_ATOM_length || (first->flags&JS_PROP_TMASK) || !(first->flags&JS_PROP_LENGTH))goto slow;
    length=array->prop[0].u.value;
    if (JS_VALUE_GET_TAG(length)!=JS_TAG_INT || JS_VALUE_GET_INT(length)<0)goto slow;
    idx=it->idx;
    if (idx>=(uint32_t)JS_VALUE_GET_INT(length) || idx>=array->u.array.count)goto slow;
    frame->saved_sp=sp;
    frame->sf.cur_pc=pc;
    js_frame_begin_c(state);
    it->idx=idx+1;
    sp[0]=js_dup(array->u.array.u.values[idx]);
    sp[1]=js_bool(false);
    state->pc=pc;
    state->sp=sp+2;
    frame->saved_sp=sp+2;
    js_frame_finish_c(state);
    return 0;
slow:
    return JS_FrameIteratorOp_for_of_next(state);
}
"""
    out.write_text(
        prefix
        + types
        + '\n#include "src/common/call/quickjs-interpreter-register.h"\n'
        + array
        + declaration
        + charge
        + boundaries
        + body,
        encoding="utf-8",
    )
    parent = module(source, "iterator")
    adapter = module(source, "object-adapter")
    path = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    raw = path.read_bytes()
    coff = adapter.Coff(raw)
    names = {x["name"] for x in coff.all_symbols.values()}
    alias = "qjs_frame_core_js_array_iterator_next"
    assert "js_array_iterator_next" in names
    if alias not in names:
        coff.expose("js_array_iterator_next")
        parent.finish_preserving_tail(coff, raw, path)
    (_frame_generated_file(build, "quickjs-interpreter-iterator-fast-source.json")).write_text(
        json.dumps(
            dict(
                core_sha256=sha(_frame_source_file(source, "quickjs.c")),
                inherited_private_header_sha256=sha(
                    _frame_generated_file(build, "quickjs-iterator-private.h")
                ),
                generated_sha256=sha(out),
                core_object_before_sha256=hashlib.sha256(raw).hexdigest(),
                core_object_after_sha256=sha(path),
                kind_offset=load_layout(source)["offsets"]["JSFunctionBytecode.byte_code_buf"] - 2,
                configuration_bits=dict(extended=1, enabled=2, initialized=4),
                no_weak_object_cache=True,
                completion_and_misses="Inherited opcode helper unchanged.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
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
        filename="quickjs-interpreter-iterator-fast.c",
        late_name=".qjsitfa",
    )
    # The new C island follows the inherited iterator ASM ranges and the new
    # leaf ASM route. Its runtime-function entries must follow both as well.
    adapter = module(source, "object-adapter")
    coff = adapter.Coff(out.read_bytes())
    for rec in coff.section_records:
        for i in range(rec["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", coff.data, rec["reloc"] + i * 10)
            assert kind != 1, (
                "New iterator island must have no absolute64 relocation",
                offset,
                coff.all_symbols[symbol]["name"],
            )
    for section, rec in zip(coff.sections, coff.section_records):
        name = section["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = coff.strings[at : coff.strings.index(0, at)].decode()
        if not name.startswith(".pdata"):
            continue
        newname = ".pdata$zzzzzzzzzzzzzzzzfast1"
        at = len(coff.strings)
        coff.strings += newname.encode() + b"\0"
        coff.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
        sn = coff.section_records.index(rec) + 1
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
    j["object_sha256"] = sha(out)
    j["pdata_policy"] = "After inherited iterator island and appended leaf selector."
    j["no_absolute64_relocations"] = True
    record.write_text(json.dumps(j, indent=2) + "\n", encoding="utf-8")


def append(out, diagnostics=False):
    path = out / "quickjs-interpreter-iterator-win64.S"
    source = Path(__file__).resolve().parents[4]
    ops = [
        m[1]
        for m in re.finditer(
            r"^DEF\(\s*(\w+)\s*,", _frame_source_file(source, "quickjs-opcode.h").read_text(), re.M
        )
    ]
    error = 2296 if diagnostics else 160
    code = [
        '.section .qjsitfa,"xr"',
        ".p2align 4",
        ".globl JS_FrameIteratorSelectEntry, JS_FrameIteratorSelectEntry_end",
        ".def JS_FrameIteratorSelectEntry; .scl 2; .type 32; .endef",
        "JS_FrameIteratorSelectEntry:",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rax+80]",
        "cmp BYTE PTR [rdx+22], 0",
        "jne JS_FrameIteratorSlow",
        "cmp BYTE PTR [rax+62], 0",
        "jne JS_FrameInterpSlow",
        "cmp BYTE PTR [rcx+" + str(error) + "], 0",
        "jne JS_FrameIteratorSlowSelect",
        "mov rdx, QWORD PTR [rcx+16]",
        "movzx edx, BYTE PTR [rdx]",
        # LiteralSelect only handles object/define_field and otherwise tail
        # calls the ordinary selector. Partition those two opcodes here,
        # retaining the original two-test leaf size and all guards above.
        # Returns and other opcodes still use the inherited ordinary path,
        # including its array readonly gateway behind InterpSlow.
        "cmp edx, " + str(ops.index("object")),
        "je JS_FrameIteratorSlowSelect",
        "cmp edx, " + str(ops.index("define_field")),
        "je JS_FrameIteratorSlowSelect",
        "jmp JS_FrameInterpSlow",
        "JS_FrameIteratorSelectEntry_end:",
        ".p2align 2",
        "JS_FrameIteratorSelectEntry_unwind:",
        ".byte 1, 0, 0, 0",
        '.section .pdata$zzzzzzzzzzzzzzzzfast0,"dr"',
        ".p2align 2",
        ".rva JS_FrameIteratorSelectEntry, JS_FrameIteratorSelectEntry_end, JS_FrameIteratorSelectEntry_unwind",
    ]
    with path.open("a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(code) + "\n")


def route(source, paths, objdump):
    parent = module(source, "iterator")
    targets = {
        "JS_FrameIteratorValidateSelect": "JS_FrameIteratorFastValidateSelect",
        "JS_FrameIteratorSlowSelect": "JS_FrameIteratorSelectEntry",
        "JS_FrameIteratorOp_for_of_next": "JS_FrameIteratorArrayNext",
    }
    for path in paths:
        parent.route(
            path,
            source,
            objdump,
            targets=targets,
            label="iterator-fast",
            excluded_sections=(".qjsitfa",),
        )


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
