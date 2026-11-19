"""Diagnostic-only real slow-interpreter entry census; production text is exact."""

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
import hashlib, json

RW = ".qjvsom$C"
CODE = r"""
#include <stdatomic.h>
typedef struct {
    _Atomic(uint64_t) total,exceptions,invalid,controls,bad_calls,max_depth;
    _Atomic(uint64_t) masks[33],ops[256],op_masks[256][32];
    _Atomic(uint64_t) call_kinds[6][8],call_classes[256],cprotos[33][8],js_arity[3];
} FrameSlowObservePhase;
typedef struct {
    unsigned version;_Atomic(unsigned) enabled,phase;
    JSCFunction *control;
    FrameSlowObservePhase data[3];
} FrameSlowObserveData;
#ifdef _MSC_VER
#pragma section(".qjvsom$C",read,write)
__declspec(allocate(".qjvsom$C"))
#else
__attribute__((section(".qjvsom$C"),used,aligned(8)))
#endif
static FrameSlowObserveData frame_slow_observe={1};
_Static_assert(sizeof(JSFrame)==128 && sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame &&
    offsetof(JSStackFrame,var_ref_count)==QJS_ABI_OFF_JSStackFrame_var_ref_count && sizeof(((JSStackFrame *)0)->var_ref_count)==2 &&
    offsetof(JSFunctionBytecode,pc2line_len)==QJS_ABI_OFF_JSFunctionBytecode_pc2line_len &&
    offsetof(JSFunctionBytecode,pc2line_buf)==QJS_ABI_OFF_JSFunctionBytecode_pc2line_buf,
    "diagnostic slow observation uses existing frame/bytecode contracts");
FRAME_CODE void JS_FrameVarargsObserveBegin(JSCFunction *control){
    /* One registration before engine execution; no JS pointer/root retained. */
    frame_slow_observe.control=control;
    atomic_store_explicit(&frame_slow_observe.phase,0,memory_order_relaxed);
    atomic_store_explicit(&frame_slow_observe.enabled,1,memory_order_release);
}
FRAME_CODE void JS_FrameVarargsObservePhase(unsigned phase){
    if(phase<3)atomic_store_explicit(&frame_slow_observe.phase,phase,memory_order_relaxed);
}
static FRAME_INLINE unsigned frame_slow_observe_argbucket(unsigned n){
    return n<4?n:n<8?4:n<16?5:n<64?6:7;
}
static FRAME_CODE void JS_FrameVarargsObserveEnter(JSFrameRegisterState *state){
    if(!atomic_load_explicit(&frame_slow_observe.enabled,memory_order_acquire))return;
    unsigned phase=atomic_load_explicit(&frame_slow_observe.phase,memory_order_relaxed);
    FrameSlowObservePhase *d=&frame_slow_observe.data[phase<3?phase:2];
#define SO_INC(v) atomic_fetch_add_explicit(&(v),1,memory_order_relaxed)
    if(state->exception_pending){SO_INC(d->total);SO_INC(d->exceptions);SO_INC(d->masks[1]);return;}
    JSFrame *frame=state->frame;JSFunctionBytecode *b=frame->bytecode;
    uintptr_t pc=(uintptr_t)state->pc,base=(uintptr_t)b->byte_code_buf;
    if(b->byte_code_len<=0||pc<base||pc-base>=(unsigned)b->byte_code_len){
        SO_INC(d->total);SO_INC(d->invalid);SO_INC(d->masks[32]);return;
    }
    unsigned op=*(const uint8_t *)pc;
    if(op>=OP_COUNT){SO_INC(d->total);SO_INC(d->invalid);SO_INC(d->masks[32]);return;}
    unsigned argc=0;int call=0,method=0,bad_call=0;JSValue callee=JS_UNDEFINED;
    if(op>=OP_call0&&op<=OP_call3){argc=op-OP_call0;call=1;}
    else if(op==OP_call||op==OP_tail_call||op==OP_call_method||op==OP_tail_call_method){
        call=1;method=op==OP_call_method||op==OP_tail_call_method;
        if((unsigned)b->byte_code_len-(unsigned)(pc-base)<3)bad_call=1;
        else argc=get_u16((const uint8_t *)pc+1);
    }
    if(call&&!bad_call){
        uintptr_t sp=(uintptr_t)state->sp,lo=(uintptr_t)(frame->sf.var_buf+b->var_count);
        size_t need=((size_t)argc+1+(unsigned)method)*sizeof(JSValue);
        if(sp<lo||sp-lo<need)bad_call=1;
        else callee=state->sp[-(ptrdiff_t)argc-1];
    }
    if(call&&!bad_call&&JS_IsObject(callee)){
        JSObject *object=JS_VALUE_GET_OBJ(callee);
        if(object->class_id==JS_CLASS_C_FUNCTION&&object->u.cfunc.cproto==JS_CFUNC_generic&&
            object->u.cfunc.c_function.generic==frame_slow_observe.control){SO_INC(d->controls);return;}
    }
    unsigned mask=0,depth=0;
    if(state->iterator_checkpoint_depth)mask|=2;
    if(op==OP_append||op==OP_apply)mask|=4;
    for(JSFrame *f=frame;f;f=js_frame_parent(f)){
        depth++;
        if(FRAME_ROOT(f)!=1&&js_frame_forward_sf(f->sf.prev_frame))mask|=8;
        if(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET]&10)mask|=16;
    }
    uint64_t previous=atomic_load_explicit(&d->max_depth,memory_order_relaxed);
    while(previous<depth&&!atomic_compare_exchange_weak_explicit(&d->max_depth,&previous,depth,memory_order_relaxed,memory_order_relaxed)){}
    SO_INC(d->total);SO_INC(d->masks[mask]);SO_INC(d->ops[op]);SO_INC(d->op_masks[op][mask]);
    if(call){
        if(bad_call){SO_INC(d->bad_calls);return;}
        unsigned kind=5,bucket=frame_slow_observe_argbucket(argc);
        if(JS_IsObject(callee)){
            JSObject *o=JS_VALUE_GET_OBJ(callee);kind=4;
            SO_INC(d->call_classes[o->class_id<255?o->class_id:255]);
            if(o->class_id==JS_CLASS_BYTECODE_FUNCTION){
                kind=0;unsigned declared=o->u.func.function_bytecode->arg_count;
                SO_INC(d->js_arity[argc<declared?0:argc==declared?1:2]);
            }else if(o->class_id==JS_CLASS_C_FUNCTION){
                kind=1;unsigned proto=o->u.cfunc.cproto;SO_INC(d->cprotos[proto<32?proto:32][bucket]);
            }else if(o->class_id==JS_CLASS_BOUND_FUNCTION)kind=2;
            else if(o->class_id==JS_CLASS_PROXY)kind=3;
        }
        SO_INC(d->call_kinds[kind][bucket]);
    }
#undef SO_INC
}
static FRAME_CODE void JS_FrameVarargsObserveVector(_Atomic(uint64_t) *p,unsigned n){
    fputc('[',stderr);
    for(unsigned i=0;i<n;i++)fprintf(stderr,"%s%"PRIu64,i?",":"",(uint64_t)atomic_load_explicit(&p[i],memory_order_relaxed));
    fputc(']',stderr);
}
FRAME_CODE void JS_FrameVarargsObserveReport(void){
    for(unsigned phase=0;phase<3;phase++){
        FrameSlowObservePhase *d=&frame_slow_observe.data[phase];
#define SO_LOAD(v) ((uint64_t)atomic_load_explicit(&(v),memory_order_relaxed))
        fprintf(stderr,"SLOW_REASON_JSON {\"version\":1,\"phase\":%u,\"total\":%"PRIu64",\"exceptions\":%"PRIu64",\"invalid\":%"PRIu64",\"controls\":%"PRIu64",\"bad_calls\":%"PRIu64",\"max_depth\":%"PRIu64",\"masks\":",
            phase,SO_LOAD(d->total),SO_LOAD(d->exceptions),SO_LOAD(d->invalid),SO_LOAD(d->controls),SO_LOAD(d->bad_calls),SO_LOAD(d->max_depth));
        JS_FrameVarargsObserveVector(d->masks,33);fputs(",\"opcodes\":[",stderr);
        int comma=0;
        for(unsigned op=0;op<256;op++)if(SO_LOAD(d->ops[op])){
            fprintf(stderr,"%s[%u,%"PRIu64",",comma?",":"",op,SO_LOAD(d->ops[op]));comma=1;
            JS_FrameVarargsObserveVector(d->op_masks[op],32);fputc(']',stderr);
        }
        fputs("],\"call_kinds\":[",stderr);
        for(unsigned kind=0;kind<6;kind++){
            if(kind)fputc(',',stderr);JS_FrameVarargsObserveVector(d->call_kinds[kind],8);
        }
        fputs("],\"call_classes\":",stderr);JS_FrameVarargsObserveVector(d->call_classes,256);
        fputs(",\"cprotos\":[",stderr);
        for(unsigned proto=0;proto<33;proto++){
            if(proto)fputc(',',stderr);JS_FrameVarargsObserveVector(d->cprotos[proto],8);
        }
        fputs("],\"js_arity\":",stderr);JS_FrameVarargsObserveVector(d->js_arity,3);fputs("}\n",stderr);
#undef SO_LOAD
    }
}
"""


def instrument(text, diagnostics):
    if not diagnostics:
        return text
    signature = "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)"
    assert text.count(signature) == 1
    assert "JS_FrameVarargsObserveEnter" not in text
    text = text.replace(signature, CODE + "\n" + signature, 1)
    needle = "#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY\n    js_frame_begin_c(state);\n#endif\n    if (state->exception_pending) {"
    assert text.count(needle) == 1
    return text.replace(
        needle,
        needle.replace(
            "    if (state->exception_pending)",
            "    JS_FrameVarargsObserveEnter(state);\n    if (state->exception_pending)",
        ),
        1,
    )


def adapt_source(source, build, text):
    rows = json.loads(
        (_frame_build_file(build, "compile_commands.json")).read_text(encoding="utf-8-sig")
    )
    command = next(x["command"] for x in rows if Path(x["file"]).name == "quickjs-interpreter.c")
    diagnostics = "QJS_INTERP_FRAME_DIAGNOSTICS" in command
    result = instrument(text, diagnostics)
    record = _frame_generated_file(build, "quickjs-interpreter-slow-observe-source.json")
    assert not record.exists()
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                diagnostics=diagnostics,
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                before_sha256=hashlib.sha256(text.encode()).hexdigest(),
                after_sha256=hashlib.sha256(result.encode()).hexdigest(),
                production_text_identical=(result == text),
                entry="Inside exact actual VarargsSlow after inherited begin_c; covers all direct/internal entry edges.",
                no_counter_allocation_or_js_or_os_calls=True,
                no_engine_pointer_or_frame_mutation=True,
                phase="Explicit host API before execution and diagnostic JS native phase callback; no getenv/atexit/constructor in engine.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def normalize_object(source, build, path):
    import importlib.util, struct

    rows = json.loads(
        (_frame_build_file(build, "compile_commands.json")).read_text(encoding="utf-8-sig")
    )
    command = next(x["command"] for x in rows if Path(x["file"]).name == "quickjs-interpreter.c")
    if "QJS_INTERP_FRAME_DIAGNOSTICS" not in command:
        return
    spec = importlib.util.spec_from_file_location(
        "slow_observe_rel32", _frame_tool_path("object-adapter")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    raw = path.read_bytes()
    co = m.Coff(raw)
    changes = []
    for number, sec in enumerate(co.section_records, 1):
        for j in range(sec["count"]):
            at = sec["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if not 5 <= kind <= 9:
                continue
            assert sec["flags"] & 0x20000000 and off + 4 <= sec["size"]
            value = struct.unpack_from("<i", co.data, sec["raw"] + off)[0]
            newvalue = value - (kind - 4)
            struct.pack_into("<i", co.data, sec["raw"] + off, newvalue)
            struct.pack_into("<H", co.data, at + 8, 4)
            changes.append(
                dict(
                    section=number,
                    offset=off,
                    old_kind=kind,
                    new_kind=4,
                    old_addend=value,
                    new_addend=newvalue,
                    target=co.all_symbols[index]["name"],
                )
            )
    result = co.finish()
    check = m.Coff(result)
    assert check.all_symbols == m.Coff(raw).all_symbols
    restored = bytearray(result)
    for row in changes:
        sec = check.section_records[row["section"] - 1]
        struct.pack_into("<i", restored, sec["raw"] + row["offset"], row["old_addend"])
        matches = [
            j
            for j in range(sec["count"])
            if struct.unpack_from("<I", restored, sec["reloc"] + 10 * j)[0] == row["offset"]
        ]
        assert len(matches) == 1
        struct.pack_into("<H", restored, sec["reloc"] + 10 * matches[0] + 8, row["old_kind"])
        assert row["old_addend"] - (row["old_kind"] - 4) == row["new_addend"]
    assert m.Coff(restored).sections == m.Coff(raw).sections
    backup = path.with_name(path.name + ".before-slow-observe-rel32")
    assert not backup.exists()
    backup.write_bytes(raw)
    path.write_bytes(result)
    path.with_name(path.name + ".slow-observe-rel32.json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                changes=changes,
                symbol_indexes_held=True,
                all_other_section_bytes_and_relocations_held=True,
                policy="REL32_n -> REL32 with addend minus n: exact AMD64 target expression, no code/address/padding search.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
