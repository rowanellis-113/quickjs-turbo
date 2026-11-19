"""Interp-style capacity-bounded dense append, outside inherited VM bodies.

Only the existing append-miss conditional operand changes. Growth, holes,
prototype effects and observable operations use the exact inherited slow path.
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
from native_abi import current as current_abi, source_abi
from abi_layout import constants as abi_constants
import hashlib, importlib.util, json, re, struct, subprocess
from pathlib import Path

DATA = "JS_FrameVarargsArrayAppendData"
RW_MS = ".qjszzcm$zzzzzzzzzzzzarrayappend"
RW_GNU = ".qjslcm$zzzzarrayappend"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DECLARATION = r"""
#include <stdatomic.h>
typedef struct JSFrameArrayAppendData {
    _Atomic(unsigned char) mode;
    unsigned char reserved[7];
    uint64_t hits;
} JSFrameArrayAppendData;
_Static_assert(sizeof(JSFrameArrayAppendData)==16 &&
    offsetof(JSFrameArrayAppendData,hits)==8,"array append observation ABI");
_Static_assert(JS_CLASS_ARRAY==2 && sizeof(JSValue)==16 && JS_TAG_INT==0 &&
    offsetof(JSObject,shape)==QJS_ABI_OFF_JSObject_shape && offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop &&
    offsetof(JSObject,u.array.u.values)==QJS_ABI_OFF_JSObject_u_array_u_values &&
    offsetof(JSObject,u.array.count)==QJS_ABI_OFF_JSObject_u_array_count &&
    offsetof(JSObject,u.array.u1.size)==QJS_ABI_OFF_JSObject_u_array_u1 &&
    offsetof(JSShape,proto)==QJS_ABI_OFF_JSShape_proto &&
    offsetof(JSContext,class_proto)==QJS_ABI_OFF_JSContext_class_proto &&
    offsetof(JSShape,prop_hash_mask)==QJS_ABI_OFF_JSShape_prop_hash_mask && JS_PROP_WRITABLE==2,
    "dense append selected private ABI");
#ifdef _MSC_VER
#pragma section(".qjszzcm$zzzzzzzzzzzzarrayappend",read,write)
__declspec(allocate(".qjszzcm$zzzzzzzzzzzzarrayappend"))
#else
__attribute__((section(".qjslcm$zzzzarrayappend"),used))
#endif
JSFrameArrayAppendData JS_FrameVarargsArrayAppendData={255};
static FRAME_CODE int JS_FrameVarargsArrayAppendConfigure(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameVarargsArrayReadonlyStep(JSFrameRegisterState *state);
/* The original core has an in-capacity append shortcut which omits this
 * writable-length check. Keep the giant copied semantic body unchanged, but
 * route the violating case to the original complete property setter first.
 * Reads only: no reference, PC, quota, frame or object mutation here.
 */
static FRAME_INLINE bool JS_FrameVarargsArrayReadonlyAppend(JSFrameRegisterState *state)
{
    JSValue *sp=state->sp;
    JSContext *ctx=state->frame->bytecode->realm;
    JSObject *p;
    uint32_t index,length;
    JSShapeProperty *props;
    if(!JS_IsObject(sp[-3]) || JS_VALUE_GET_TAG(sp[-2])!=JS_TAG_INT)return false;
    p=JS_VALUE_GET_OBJ(sp[-3]);
    if(p->class_id!=JS_CLASS_ARRAY || !p->fast_array || !p->extensible ||
       !ctx->std_array_prototype ||
       p->shape->proto!=JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_ARRAY]) ||
       JS_VALUE_GET_TAG(p->prop[0].u.value)!=JS_TAG_INT)return false;
    index=(uint32_t)JS_VALUE_GET_INT(sp[-2]);
    length=(uint32_t)JS_VALUE_GET_INT(p->prop[0].u.value);
    if(index!=p->u.array.count || index<length ||
       index>=p->u.array.u1.size)return false;
#if QJS_ABI_HAS_PREFIX_RC
    props=(JSShapeProperty *)(p->shape->hash_table+p->shape->prop_hash_mask+1);
#else
    props=p->shape->prop;
#endif
    return !(props[0].flags & JS_PROP_WRITABLE);
}

extern int JS_FrameVarargsSlowSelect(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameVarargsArrayStep(JSFrameRegisterState *state);
"""
CONFIGURE = '\n/* First append miss arrives through the inherited real C boundary. Publish\n * roots before environment access, then re-enter the unchanged selector.\n * Subsequent disabled misses execute the inherited semantic path directly.\n * Environment policy has the same process lifetime as the existing controls.\n */\nstatic FRAME_CODE int JS_FrameVarargsArrayAppendConfigure(JSFrameRegisterState *state)\n{\n    JSFrame *frame=state->frame;\n    unsigned char mode;\n    js_frame_begin_c(state);\n    frame->saved_sp=state->sp;\n    frame->sf.cur_sp=state->sp;\n    frame->sf.cur_pc=state->pc;\n    mode=getenv("QJS_DISABLE_FRAME_ARRAY_APPEND")?2:1;\n    if(getenv("QJS_OBSERVE_FRAME_ARRAY_APPEND"))mode|=4;\n    atomic_store_explicit(&JS_FrameVarargsArrayAppendData.mode,mode,memory_order_relaxed);\n    js_frame_finish_c(state);\n    return JS_FrameVarargsArrayStep(state);\n}\n\n/* Only the inherited in-capacity readonly-extension defect with a proven\n * normal prototype chain reaches this operation. No prototype observer can\n * run before the setter consumes the rejected value. Other prototype cases\n * retain the inherited full semantic path and its live-value root protocol.\n * The complete setter preserves strict/sloppy behavior.\n * A rejected value may run a finalizer: clear its consumed slot before the\n * call, then publish the popped cursor before releasing the base object.\n * Exceptions use the retained complete checkpoint/forward unwinder.\n */\nstatic FRAME_CODE int JS_FrameVarargsArrayReadonlyStep(JSFrameRegisterState *state)\n{\n    JSFrame *frame=state->frame;\n    JSStackFrame *sf=&frame->sf;\n    JSContext *ctx=frame->bytecode->realm;\n    JSValue *sp=state->sp;\n    JSValue value=sp[-1],base;\n    int result;\n    js_frame_begin_c(state);\n    state->pc++;\n    sf->cur_pc=state->pc;\n    frame->saved_sp=sp;\n    sf->cur_sp=sp;\n    sp[-1]=JS_UNDEFINED;\n    result=JS_SetPropertyValue(ctx,sp[-3],sp[-2],value,JS_PROP_THROW_STRICT);\n    base=sp[-3];\n    sp[-3]=JS_UNDEFINED;\n    sp-=3;\n    state->sp=sp;\n    frame->saved_sp=sp;\n    sf->cur_sp=sp;\n    JS_FreeValue(ctx,base);\n    if(unlikely(result<0))state->exception_pending=true;\n    js_frame_finish_c(state);\n    return result<0?JS_FrameVarargsSlowSelect(state):0;\n}\n'
GATEWAY = "\n/* This opcode-only gateway must remain a tail dispatcher. In particular,\n * do not inline array shape checks into a shared selector/prologue. */\nFRAME_CODE int JS_FrameVarargsArraySlowSelect(JSFrameRegisterState *state)\n{\n    if (!state->exception_pending && *state->pc == OP_put_array_el)\n        return JS_FrameVarargsArrayStep(state);\n    return JS_FrameVarargsSlowSelect(state);\n}\n\nstatic FRAME_CODE int JS_FrameVarargsArrayStep(JSFrameRegisterState *state)\n{\n    if (atomic_load_explicit(&JS_FrameVarargsArrayAppendData.mode,memory_order_relaxed) == 255)\n        return JS_FrameVarargsArrayAppendConfigure(state);\n    if (JS_FrameVarargsArrayReadonlyAppend(state))\n        return JS_FrameVarargsArrayReadonlyStep(state);\n    return JS_FrameVarargsSlowSelect(state);\n}\n"


def generate_c(source, build, target):
    parent = (_frame_generated_file(build, "quickjs-interpreter-varargs.c")).read_text(
        encoding="utf-8"
    )
    include = next(line for line in parent.splitlines() if line.startswith("#include "))
    start = parent.index("#ifndef QJS_FRAME_CONTEXT_TYPES\n#define QJS_FRAME_CONTEXT_TYPES\n")
    end = parent.index(
        "/* A supported opcode is declared once, for validation and dispatch. */", start
    )
    # This prefix contains ABI definitions and inline quota helpers only;
    # neither a copied core public body nor a validator/semantic body enters.
    prefix = parent[start:end]
    assert not re.search(r"(?m)^(?:static )?FRAME_CODE ", prefix)
    target.write_text(
        include + "\n" + prefix + "\n" + DECLARATION + GATEWAY + CONFIGURE, encoding="utf-8"
    )


def compile_c(source, build, msvc):
    M = module(source, "atod")
    C = module(source, "object-adapter")
    output = _frame_generated_file(build, "quickjs-interpreter-array-append-c.obj")
    M.compile_extra(
        source,
        build,
        output,
        generator=lambda src, p: generate_c(src, build, p),
        filename="quickjs-interpreter-array-append.c",
        late_name=".qjzzva",
    )
    original = output.read_bytes()
    co = C.Coff(original)
    renamed = []
    commons = []
    for index, symbol in co.all_symbols.items():
        if symbol["section"] == 0 and symbol["storage"] == 2 and symbol["value"]:
            providers = []
            for path in (
                _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj"),
                _frame_build_file(
                    build, "CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                ),
            ):
                provider = C.Coff(path.read_bytes())
                if any(
                    v["name"] == symbol["name"]
                    and v["storage"] == 2
                    and (v["section"] > 0 or (v["section"] == 0 and v["value"] >= symbol["value"]))
                    for v in provider.all_symbols.values()
                ):
                    providers.append(str(path))
            assert providers, ("Common storage requires an original provider", symbol)
            struct.pack_into("<I", co.data, co.table + index * co.stride + 8, 0)
            commons.append(dict(name=symbol["name"], bytes=symbol["value"], providers=providers))
        if (
            symbol["section"] > 0
            and symbol["storage"] == 2
            and not symbol["name"].startswith("JS_FrameVarargsArray")
        ):
            name = "arrayappend_emitted_" + hashlib.sha256(symbol["name"].encode()).hexdigest()[:32]
            at = len(co.strings)
            co.strings += name.encode() + b"\0"
            struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
            renamed.append(dict(index=index, old=symbol["name"], new=name))
    for number, rec in enumerate(co.section_records, 1):
        if not rec["flags"] & 0x20000000:
            continue
        for j in range(rec["count"]):
            off, index, kind = struct.unpack_from("<IIH", co.data, rec["reloc"] + 10 * j)
            assert kind != 1, (
                "No new absolute 64-bit code/data references",
                number,
                off,
                co.all_symbols[index],
            )
    backup = output.with_name(output.name + ".unrenamed")
    assert not backup.exists()
    backup.write_bytes(original)
    output.write_bytes(co.finish())
    assert C.Coff(original).sections == C.Coff(output.read_bytes()).sections
    output.with_name(output.name + ".private-symbols.json").write_text(
        json.dumps(
            dict(
                status="passed",
                original=str(backup),
                original_sha256=sha(backup),
                output_sha256=sha(output),
                renamed=renamed,
                common_dependencies=commons,
                all_section_payloads_and_relocations_identical=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def route(out, masm, gas, diagnostics):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]

    def change(lines, entry, fallback, target):
        start = lines.index(entry + ":") if entry + ":" in lines else lines.index(entry + "::")
        at = lines.index(f"cmp ecx, DWORD PTR [r8+{abi_fields['JSObject.u.array.count']}]", start)
        assert lines[at + 1] == "jae " + fallback, (entry, lines[at + 1])
        assert lines[at + 2] == "shl rcx, 4"
        lines[at + 1] = "jae " + target

    change(masm, "interp_put_array_el", "interp_slow", "NEAR PTR JS_FrameArrayAppendClean")
    change(gas, "interp_put_array_el", "interp_slow", "JS_FrameArrayAppendClean")
    masm[:0] = ["EXTERN JS_FrameArrayAppendClean:PROC"]
    dirty = out / "quickjs-interpreter-publish-win64.S"
    if dirty.exists() and not diagnostics:
        lines = dirty.read_text(encoding="utf-8").splitlines()
        change(lines, "dirty_interp_put_array_el", "dirty_interp_slow", "JS_FrameArrayAppendDirty")
        assert "dirty_interp_slow:" in lines
        lines[:0] = [".globl dirty_interp_slow"]
        dirty.write_text("\n".join(lines) + "\n", encoding="utf-8")


def body(name, fallback, *, layout=None):
    # Incoming R8/ECX are the original array/index after class, fast-array and
    # refcount>1 guards. No observer, C call, allocator or failure after commit.
    abi = current_abi() if layout is None else layout
    fields = abi["offsets"]
    ((ext_byte, ext_mask),) = abi["bits"]["JSObject.extensible"]
    ((std_byte, std_mask),) = abi["bits"]["JSContext.std_array_prototype"]
    assert abi["bits"]["JSShapeProperty.flags"] == [[3, 4]]
    properties = (
        [f"lea r11, [rax+{fields['JSShape.prop']}]"]
        if abi["reference_count_model"] == "inline-header"
        else [
            f"mov r11d, DWORD PTR [rax+{fields['JSShape.prop_hash_mask']}]",
            f"lea r11, [rax+r11*4+{fields['JSShape.hash_table'] + 4}]",
        ]
    )
    return [
        f"movzx eax, BYTE PTR [rip+{DATA}]",
        "and eax, 3",
        "cmp eax, 1",
        "jne " + fallback,
        f"cmp ecx, DWORD PTR [r8+{fields['JSObject.u.array.count']}]",
        "jne " + fallback,
        f"test BYTE PTR [r8+{ext_byte}], {ext_mask}",
        "jz " + fallback,
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov rax, QWORD PTR [rsi+{fields['JSContext.class_proto']}]",
        f"mov r11, QWORD PTR [r10+{fields['JSShape.proto']}]",
        "cmp r11, QWORD PTR [rax+32]",
        "jne " + fallback,
        f"test BYTE PTR [rsi+{std_byte}], {std_mask}",
        "jz " + fallback,
        f"mov r10, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "cmp DWORD PTR [r10+8], 0",
        "jne " + fallback,
        "lea edx, [rcx+1]",
        f"cmp edx, DWORD PTR [r8+{fields['JSObject.u.array.u1']}]",
        "ja " + fallback,
        "cmp edx, DWORD PTR [r10]",
        "jbe " + name + "_length_allowed",
        f"mov rax, QWORD PTR [r8+{fields['JSObject.shape']}]",
        *properties,
        "test DWORD PTR [r11], 134217728",
        "jz " + fallback,
        name + "_length_allowed:",
        f"movzx eax, BYTE PTR [rip+{DATA}]",
        "test al, 4",
        "jz " + name + "_commit",
        f"inc QWORD PTR [rip+{DATA}+8]",
        name + "_commit:",
        f"mov r11, QWORD PTR [r8+{fields['JSObject.u.array.u.values']}]",
        "shl rcx, 4",
        "movdqu xmm0, XMMWORD PTR [r13-16]",
        "movdqu XMMWORD PTR [r11+rcx], xmm0",
        f"mov DWORD PTR [r8+{fields['JSObject.u.array.count']}], edx",
        "cmp edx, DWORD PTR [r10]",
        "jbe " + name + "_stored",
        "mov eax, edx",
        "mov QWORD PTR [r10], rax",
        "mov QWORD PTR [r10+8], 0",
        name + "_stored:",
        f"dec DWORD PTR [r8{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "sub r13, 48",
        "inc r12",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]


@source_abi
def compile_extra(source, build, compiler, msvc, diagnostics):
    compile_c(source, build, msvc)
    blocks = [("JS_FrameArrayAppendClean", "interp_slow")]
    if not msvc and not diagnostics:
        blocks.append(("JS_FrameArrayAppendDirty", "dirty_interp_slow"))
    externals = ["interp_slow", "JS_FrameInterpPropertyCold_unwind", DATA]
    if len(blocks) == 2:
        externals.append("dirty_interp_slow")
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n + ":BYTE" for n in externals],
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
        ]
        for name, fallback in blocks:
            text += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in body(name, fallback):
                line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
                if re.fullmatch(r"j\w+ \w+", line):
                    op, target = line.split()
                    line = op + " NEAR PTR " + target
                text.append(line)
            text += [name + "_end LABEL BYTE", name + " ENDP"]
        text += [".qjzzva ENDS", ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'"]
        for name, _ in blocks:
            text += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        text += [".pdata$zzzzzznullfast ENDS", "END"]
        asm = _frame_generated_file(build, "quickjs-interpreter-array-append.asm")
        obj = asm.with_suffix(".obj")
        command = [compiler.with_name("ml64.exe"), "/nologo", "/c", "/Fo" + str(obj), asm]
    else:
        text = [".intel_syntax noprefix", '.section .qjzzva,"xr"']
        for name, fallback in blocks:
            text += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *body(name, fallback),
                name + "_end:",
            ]
        text += ['.section .pdata$zzzzzznullfast,"dr"', ".p2align 2"]
        for name, _ in blocks:
            text += [".rva " + name + "," + name + "_end,JS_FrameInterpPropertyCold_unwind"]
        asm = _frame_generated_file(build, "quickjs-interpreter-array-append.S")
        obj = asm.with_suffix(".obj")
        command = [compiler, "-c", "-g0", asm, "-o", obj]
    asm.write_text("\n".join(text) + "\n", encoding="ascii")
    command = list(map(str, command))
    p = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, p.stdout, p.stderr)
    (_frame_generated_file(build, "quickjs-array-append-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                generator_sha256=sha(__file__),
                source_sha256=sha(asm),
                object_sha256=sha(obj),
                functions=[n for n, _ in blocks],
                diagnostics=diagnostics,
                protocol="Jump-entered VM continuation, same live registers and chained parent Windows unwind. No RSP/C call/allocation. All semantic guards before count/length/value/refcount/SP/PC mutation; original clean/dirty fallback; unchanged current dispatch table.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-array-append-c.obj"),
        "JS_FrameVarargsArrayReadonlyStep",
        "array-append-c",
        keep_all=True,
        code_input=".qjzzva",
        code_output=group if msvc else group + "$N",
        pdata_output=prefix + "1",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=(RW_MS,) if msvc else (RW_GNU,),
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-array-append.obj"),
        "JS_FrameArrayAppendClean",
        "array-append-native",
        keep_all=True,
        code_input=".qjzzva",
        code_output=group if msvc else group + "$O",
        pdata_output=prefix + "1",
        base_owner=owner,
        baseline_sections=(),
    )
