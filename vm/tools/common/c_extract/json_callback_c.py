"""Pure-C JSON parser/writer/reviver/dense-pop/toJSON slot extractors."""

import hashlib
import json
import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

from c_source_match import replace_one

sha_text = lambda t: hashlib.sha256(t.encode()).hexdigest()


def prepare(source, virtual):
    from pathlib import Path
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "json_callback_source_parser", _frame_tool_path("object-adapter-c")
    )
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in M.FUNCTION.finditer(original)}
    virtual = re.sub(
        r"^(static bool js_string_eq\([^\n]*\)) \{", lambda m: m[1] + "\n{", virtual, flags=re.M
    )
    proof = []
    names = {
        "internalize_json_property": "frame_json_reviver_property",
        "js_json_parse": "frame_json_reviver_parse",
        "js_json_check": "frame_json_replacer_check",
        "js_json_to_str": "frame_json_replacer_to_str",
        "JS_JSONStringify": "frame_json_replacer_stringify",
    }
    context = re.search(
        r"typedef struct JSONStringifyContext \{.*?\} JSONStringifyContext;", original, re.S
    )[0]
    private_context = context.replace("JSONStringifyContext", "FrameJSONLegacyContext")
    private_context = private_context.replace(
        "    StringBuffer *b;", "    StringBuffer *b;\n    void *json_callback_scope;"
    )
    record_object = re.search(
        r"typedef struct \{\n    int count;\n    uint32_t hash_size;.*?\} JSONParseRecordObject;",
        original,
        re.S,
    )
    assert record_object is not None
    begin = record_object.start()
    end = original.index("static void json_parse_record_init_obj(", begin)
    record_types = original[begin:end]
    number_hint = re.search(
        r"typedef enum JSToNumberHintEnum \{[^{}]*\} JSToNumberHintEnum;", original, re.S
    )
    assert number_hint is not None
    types = record_types + private_context + "\n" + number_hint[0] + "\n"
    marker = "static inline bool double_is_int32"
    assert virtual.count(marker) == 1
    virtual = virtual.replace(marker, types + "\n" + marker, 1)
    virtual = re.sub(
        r"^(static JSValue JS_ToQuotedStringFree\([^\n]*\)) \{",
        lambda m: m[1] + "\n{",
        virtual,
        flags=re.M,
    )
    for old, new in names.items():
        body = functions[old][0]
        transformed = re.sub(r"\b(" + "|".join(names) + r")\b", lambda m: names[m[0]], body)
        transformed = transformed.replace("JSONStringifyContext", "FrameJSONLegacyContext")
        if old in ("internalize_json_property", "js_json_parse", "JS_JSONStringify"):
            signature = next(m for m in M.FUNCTION.finditer(transformed) if m[2] == new)
            transformed = (
                transformed[: signature.end(3)]
                + ",void *json_scope"
                + transformed[signature.end(3) :]
            )
            if old == "JS_JSONStringify":
                transformed = transformed.replace(
                    "JSValue frame_json_replacer_stringify(",
                    "static JSValue frame_json_replacer_stringify(",
                    1,
                )
                needle = "    jsc->replacer_func = JS_UNDEFINED;"
                assert transformed.count(needle) == 1
                transformed = transformed.replace(
                    needle, "    jsc->json_callback_scope = json_scope;\n" + needle, 1
                )
        if old == "internalize_json_property":
            needle = "frame_json_reviver_property(ctx, val, prop, reviver, text_str, pr)"
            assert transformed.count(needle) == 1
            transformed = transformed.replace(needle, needle[:-1] + ",json_scope)", 1)
            needle = "JS_Call(ctx, reviver, holder, 3, args)"
            assert transformed.count(needle) == 1
            transformed = transformed.replace(
                needle, "frame_json_callback_call(ctx,reviver,holder,3,args,json_scope,0)", 1
            )
        if old == "js_json_parse":
            needle = "reviver, str, pr);"
            assert transformed.count(needle) == 1
            transformed = transformed.replace(needle, "reviver, str, pr,json_scope);", 1)
        if old == "js_json_check":
            for before, after in (
                (
                    "JS_CallFree(ctx, f, val, 1, &key)",
                    "frame_json_callback_free(ctx,f,val,1,&key,jsc->json_callback_scope,0)",
                ),
                (
                    "JS_Call(ctx, jsc->replacer_func, holder, 2, args)",
                    "frame_json_callback_call(ctx,jsc->replacer_func,holder,2,args,jsc->json_callback_scope,1)",
                ),
            ):
                assert transformed.count(before) == 1
                transformed = transformed.replace(before, after, 1)
        stack_checks = transformed.count("js_check_stack_overflow(ctx->rt, 0)")
        transformed = transformed.replace(
            "js_check_stack_overflow(ctx->rt, 0)", "frame_json_callback_stack_overflow(ctx->rt)"
        )
        virtual += "\n" + transformed + "\n"
        proof.append(
            dict(
                original=old,
                local=new,
                original_sha256=sha_text(body),
                generated_sha256=sha_text(transformed),
                live_stack_checks=stack_checks,
                policy="Exact parser-extracted body; private names/context type, explicit capsule propagation and JS_Call/JS_CallFree target substituted. Scope field initialized in copied root. GNU stack guard uses the separately qualified live-SP mechanism. All traversal/source/mutation/error/ownership statements retained.",
            )
        )
    runtime = _frame_source_text(source, "linux-json-callback.inc")
    capsule = _frame_source_text(source, "linux-prepared-callback.inc")
    begin = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    end = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", begin)
    declarations = capsule[begin:end]
    leaf = next(
        m[0] for m in M.FUNCTION.finditer(capsule) if m[2] == "frame_callback_may_have_leaf"
    )
    assert runtime.count("/* GENERATED_CALLBACK_CAPSULE */") == 1
    runtime = runtime.replace("/* GENERATED_CALLBACK_CAPSULE */", declarations + "\n" + leaf, 1)
    proto = """#include "quickjs.h"
#ifdef _MSC_VER
static __forceinline JSValue frame_json_callback_call(JSContext *,JSValueConst,JSValueConst,int,JSValueConst *,void *,unsigned);
static __forceinline JSValue frame_json_callback_free(JSContext *,JSValue,JSValueConst,int,JSValueConst *,void *,unsigned);
static __forceinline int frame_json_callback_stack_overflow(JSRuntime *);
#else
static inline __attribute__((always_inline)) JSValue frame_json_callback_call(JSContext *,JSValueConst,JSValueConst,int,JSValueConst *,void *,unsigned);
static inline __attribute__((always_inline)) JSValue frame_json_callback_free(JSContext *,JSValue,JSValueConst,int,JSValueConst *,void *,unsigned);
static inline __attribute__((always_inline)) int frame_json_callback_stack_overflow(JSRuntime *);
#endif
"""
    return (
        virtual,
        runtime,
        proto,
        dict(
            functions=proof,
            capsule_declarations_sha256=sha_text(declarations),
            leaf_classifier_sha256=sha_text(leaf),
            stringify_context_source_sha256=sha_text(context),
            stringify_context_private_sha256=sha_text(private_context),
            parse_record_types_sha256=sha_text(record_types),
        ),
    )


def prepare_writable_backend(backend, C, *, target_flag=False):
    def replace(before, after):
        nonlocal backend
        if before.startswith(".qjs"):
            if backend.count(before) != 1:
                raise ValueError("JSON section anchor missing or ambiguous: " + before)
            backend = backend.replace(before, after, 1)
        else:
            backend = replace_one(backend, before, after)

    replace(".qjsjson$C", ".qjsjcwr$C")
    if target_flag:
        replace(".qjs$zzjsonC", ".qjssrc$C")
    replace(
        "    size_t bytes;\n    if(JS_VALUE_GET_TAG(callee)",
        "    size_t bytes;\n    unsigned admission;\n    if(JS_VALUE_GET_TAG(callee)",
    )
    replace(
        "    if((FRAME_KIND(b)&7)!=3 || b->var_ref_count ||\n        b->arg_count>argc || frame_callback_may_have_leaf(b)) return 0;",
        '    admission=FRAME_KIND(b)&7;\n    if((admission!=1 && admission!=3) || b->var_ref_count ||\n        (admission==3 && b->arg_count>argc) || frame_callback_may_have_leaf(b)) return 0;\n    if(admission==1 && b->arg_count>argc && getenv("QJS_DISABLE_CALLBACK_ARITY")) return 0;',
    )
    replace(
        "    bytes=128+sizeof(JSValue)*(b->var_count+b->stack_size);",
        "    bytes=128+sizeof(JSValue)*((admission==1 ? b->arg_count : 0)+b->var_count+b->stack_size);",
    )
    replace(
        "call->callback_argc=argc;call->reserved=0;",
        "call->callback_argc=argc;call->reserved=(admission==1);",
    )
    replace(
        "frame->sf.cur_func=call->callee;frame->sf.var_buf=(JSValue *)(call->data+128);\n    frame->sf.arg_count=argc;",
        "frame->sf.cur_func=call->callee;\n    frame->sf.arg_buf=(JSValue *)(call->data+128);\n    frame->sf.var_buf=frame->sf.arg_buf+(admission==1 ? b->arg_count : 0);\n    frame->sf.arg_count=(admission==1 && b->arg_count) ? b->arg_count : argc;",
    )
    replace(
        "    return JS_FramePreparedCallbackSelect(ctx,func,this_val,JS_UNDEFINED,argc,argv,2,call);",
        "    if(call->reserved)\n        return JS_FramePreparedCallbackWriteSelect(ctx,func,this_val,JS_UNDEFINED,argc,argv,2,call);\n    return JS_FramePreparedCallbackSelect(ctx,func,this_val,JS_UNDEFINED,argc,argv,2,call);",
    )
    # Reviver has no demonstrated net benefit: do not emit its new traversal
    # or wrapper and do not alter either inherited parser call target.
    for name in ("frame_json_reviver_run", "JS_FrameJSONReviver"):
        functions = {m[2]: m for m in C.FUNCTION.finditer(backend)}
        body = functions[name][0]
        assert backend.count(body) == 1
        backend = backend.replace(body, "", 1)
    assert "frame_json_reviver_parse(" not in backend
    functions = {m[2]: m for m in C.FUNCTION.finditer(backend)}
    old = functions["JS_FrameJSONCallbackStringify"][0]
    new = """JSONCB_CODE JSValue JS_FrameJSONWriteCallbackStringify(JSContext *ctx,JSValueConst obj,
    JSValueConst replacer,JSValueConst space)
{
    JSObject *o;JSFunctionBytecode *b;
    /* No environment/bytecode/host work for roots too small to amortize a pair. */
    if(!JS_IsObject(obj)) return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
    o=JS_VALUE_GET_OBJ(obj);
    if(!((o->class_id==JS_CLASS_ARRAY && o->fast_array && o->u.array.count>=16) ||
         (o->class_id==JS_CLASS_OBJECT && !o->is_exotic && o->shape->prop_count>=16)))
        return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
    if(JS_IsUndefined(replacer)) {
        if(getenv("QJS_DISABLE_CALLBACK_WRITE") || getenv("QJS_DISABLE_JSON_CALLBACK_WRITE") ||
           !frame_json_callback_available(ctx))return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
        return frame_json_replacer_run(ctx,obj,replacer,space);
    }
    if(JS_VALUE_GET_TAG(replacer)!=JS_TAG_OBJECT) return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
    o=JS_VALUE_GET_OBJ(replacer);
    if(o->class_id!=JS_CLASS_BYTECODE_FUNCTION) return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
    b=o->u.func.function_bytecode;
    if(((FRAME_KIND(b)&7)!=1 && (FRAME_KIND(b)&7)!=3) || b->var_ref_count ||
       getenv("QJS_DISABLE_CALLBACK_WRITE") || getenv("QJS_DISABLE_JSON_CALLBACK_WRITE") ||
       !frame_json_callback_available(ctx)) return JS_FrameJSONCallbackStringify(ctx,obj,replacer,space);
    return frame_json_replacer_run(ctx,obj,replacer,space);
}"""
    if target_flag:
        # Both callers first execute the retained writer's mode initializer.
        # Read that existing atomic byte; never change its encoding or prefix.
        guard = """    unsigned char json_state=JS_FrameJSONLoad8((const unsigned char *)&JS_FrameJSONControl);
    if(!json_state || ((json_state-1)&8)) return JS_LegacyJSONStringify(ctx,obj,replacer,space);
"""
        new = new.replace(
            "    JSObject *o;JSFunctionBytecode *b;",
            "    JSObject *o;JSFunctionBytecode *b;\n" + guard,
        )
        new = new.replace("JS_FrameJSONCallbackStringify(", "JS_LegacyJSONStringify(")
        new = (
            "extern _Atomic unsigned char JS_FrameJSONControl;\n"
            + new
            + """
extern JSValue qjs_frame_core_js_json_stringify(JSContext *,JSValueConst,int,JSValueConst *);
JSONCB_CODE JSValue JS_FrameJSONWriteNativeStringify(JSContext *ctx,JSValueConst this_val,
    int argc,JSValueConst *argv)
{
    /* Non-bytecode replacers retain the original native entry and its C ABI.
       Keeping this real fallback also preserves the original core COMDAT. */
    if(!JS_IsUndefined(argv[1]) && (!JS_IsObject(argv[1]) || JS_VALUE_GET_OBJ(argv[1])->class_id!=JS_CLASS_BYTECODE_FUNCTION))
        return qjs_frame_core_js_json_stringify(ctx,this_val,argc,argv);
    return JS_FrameJSONWriteCallbackStringify(ctx,argv[0],argv[1],argv[2]);
}
"""
        )
    assert backend.count(old) == 1
    backend = backend.replace(old, new, 1)
    return backend


def compile_reviver_value(
    source, build=None, callback_out=None, parser_out=None, *, destination=None, source_owned=True
):
    """GNU late unit: extra argument is unobservable only under validated guards."""
    import importlib.util, json, os, struct
    from pathlib import Path

    here = Path(__file__).resolve().parent

    def module(name, file):
        sp = importlib.util.spec_from_file_location(
            name, _frame_tool_path(file if file != "object-adapter.py" else "object-adapter-c")
        )
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("reviver_value_coff", "object-adapter.py")
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in C.FUNCTION.finditer(original)}
    old = functions["internalize_json_property"][0]
    walker = old
    # Ordinary traversal/mutation/error/refcount statements stay source-owned.
    before = "static JSValue internalize_json_property(JSContext *ctx, JSValueConst holder,\n                                         JSAtom name, JSValueConst reviver,\n                                         const char *text_str, JSONParseRecord *pr)"
    assert walker.count(before) == 1
    walker = walker.replace(
        before,
        "static JSValue frame_json_value_property(JSContext *ctx, JSValueConst holder,\n                                         JSAtom name, JSValueConst reviver,void *scope)",
        1,
    )
    begin = walker.index("    if (pr) {")
    end = walker.index("    if (JS_IsObject(val)) {", begin)
    removed_prepare = walker[begin:end]
    walker = walker[:begin] + "    context = JS_UNDEFINED;\n\n" + walker[end:]
    begin = walker.index("    } else {\n        if (pr) {")
    end = walker.index("    js_free_prop_enum(ctx, atoms, len);", begin)
    removed_source = walker[begin:end]
    walker = walker[:begin] + "    }\n" + walker[end:]
    before = "internalize_json_property(ctx, val, prop, reviver, text_str, pr)"
    assert walker.count(before) == 1
    walker = walker.replace(before, "frame_json_value_property(ctx, val, prop, reviver,scope)", 1)
    walker = walker.replace(
        "js_check_stack_overflow(ctx->rt, 0)", "frame_json_callback_stack_overflow(ctx->rt)"
    )
    split = dict(
        callback_generation=dict(owned_core_helpers=[]),
        parts=dict(callback=dict(copied_helpers=[])),
    )
    for helper in split["callback_generation"]["owned_core_helpers"]:
        walker = re.sub(r"\b" + re.escape(helper["original"]) + r"\b", helper["private"], walker)
    assert "res = JS_Call(ctx, reviver, holder, 3, args);" in walker
    assert "args[2] = context;" in walker and "context = JS_UNDEFINED;" in walker
    walker = walker.replace(
        "res = JS_Call(ctx, reviver, holder, 3, args);",
        "res = frame_value_prepared_call(ctx, reviver, holder, 3, args,scope);",
    )
    assert "JSONParseRecord" not in walker and "text_str" not in walker
    if not source_owned:
        raise ValueError("json_callback_c only serves source-owned reviver_value")
    capsule = _frame_source_text(source, "linux-prepared-callback.inc")
    cs = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    ce = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", cs)
    declarations = capsule[cs:ce]
    callback = _frame_source_text(source, "linux-json-callback.inc")
    cf = {m[2]: m[0] for m in C.FUNCTION.finditer(callback)}
    available = (
        cf["frame_json_callback_available"]
        .replace("frame_json_callback_available", "frame_value_prepared_available")
        .replace("sizeof(FrameJSONCallbackPair)", "sizeof(JSFrameCallbackScope)")
    )
    bind = cf["frame_json_callback_bind"].replace(
        "frame_json_callback_bind", "frame_value_prepared_bind"
    )
    leaf = next(
        m[0] for m in C.FUNCTION.finditer(capsule) if m[2] == "frame_callback_may_have_leaf"
    )
    prepared = (
        (declarations + "\n" + leaf + "\n" + available + "\n" + bind)
        .replace("CALLBACK_INLINE", "REVIVER_INLINE")
        .replace("JSONCB_INLINE", "REVIVER_INLINE")
    )
    prepared += """
extern JSValue JS_FramePreparedCallbackSelect(JSContext *,JSValueConst,JSValueConst,JSValueConst,int,JSValueConst *,int,void *);
REVIVER_INLINE JSValue frame_value_prepared_call(JSContext *ctx,JSValueConst func,JSValueConst holder,int argc,JSValueConst *args,void *scope)
{
    if(!scope)return JS_Call(ctx,func,holder,argc,args);
    return JS_FramePreparedCallbackSelect(ctx,func,holder,JS_UNDEFINED,argc,args,2,scope);
}
REVIVER_INLINE int frame_value_prepared_enabled(void)
{
#ifdef _MSC_VER
    return (JS_FrameJSONLoad8(&reviver_value_control)&4)==0;
#else
    return (atomic_load_explicit(&reviver_value_control,memory_order_relaxed)&4)==0;
#endif
}
"""
    run = """
REVIVER_CODE static JSValue frame_value_run_prepared(JSContext *ctx,JSValueConst root,JSValueConst reviver)
{
    _Alignas(16) JSFrameCallbackScope call;
    JSFrameCallbackSegment *next,*following;JSValue result;
    call.callee=JS_UNDEFINED;call.segment.next=NULL;
    if(!frame_value_prepared_bind(ctx,reviver,3,&call))
        return frame_json_value_property(ctx,root,JS_ATOM_empty_string,reviver,NULL);
    result=frame_json_value_property(ctx,root,JS_ATOM_empty_string,reviver,&call);
    for(next=call.segment.next;next;next=following){following=next->next;js_free(ctx,next);}
    JS_FreeValue(ctx,call.callee);return result;
}
"""
    body = (
        r"""
#define REVIVER_INLINE static inline __attribute__((always_inline))
#define REVIVER_CODE __attribute__((section(".qjsjcrv$C"),noipa))
#include <stdatomic.h>
/* Startup-only controls, like the existing JSON mode cache. This new byte
   occupies its own final RW contribution; no old control/TLS bytes move. */
static _Atomic unsigned char reviver_value_control __attribute__((section(".qjsrvmd"),used));
REVIVER_CODE static unsigned char reviver_value_initialize_control(void)
{
    const char *mode=getenv("QJS_JSON_MODE");
    unsigned char expected=0;
    unsigned char value=(!mode || !strcmp(mode,"00") || !strcmp(mode,"0")) &&
        !getenv("QJS_DISABLE_JSON_REVIVER_VALUE") ? 1 : 2;
    if(value==1&&(getenv("QJS_DISABLE_JSON_VALUE_PREPARED")||getenv("QJS_DISABLE_PREPARED_CALLBACK")))value=5;
    if (!atomic_compare_exchange_strong_explicit(&reviver_value_control,&expected,value,
            memory_order_relaxed,memory_order_relaxed)) return expected;
    return value;
}
static inline __attribute__((always_inline)) int reviver_value_enabled(void)
{
    unsigned char state=atomic_load_explicit(&reviver_value_control,memory_order_relaxed);
    return ((state ? state : reviver_value_initialize_control())&1)!=0;
}
extern JSValue JS_FrameJSONParse(JSContext *,JSValueConst,int,JSValueConst *);
static inline __attribute__((always_inline)) int frame_json_callback_stack_overflow(JSRuntime *rt)
{
    uintptr_t sp;QJS_STACK_POINTER(sp);
    return unlikely(sp<rt->stack_limit);
}
"""
        + prepared
        + walker
        + run
        + r"""
REVIVER_CODE JSValue JS_FrameJSONReviverValue(JSContext *ctx,JSValueConst this_val,
                                            int argc,JSValueConst *argv)
{
    JSObject *o;JSFunctionBytecode *b;
    JSValue root,obj;
    /* This uses bytecode facts, never the mutable function.length property.
       Validated opcodes exclude arguments/rest/direct-eval. Captured locals
       are excluded; argument operands are validated against formal count.
       QuickJS Function.prototype caller/arguments are throwing accessors.
       Keep actual argc=3; only the proven-unobservable value is undefined. */
    if(argc<2 || JS_VALUE_GET_TAG(argv[0])!=JS_TAG_STRING ||
       JS_VALUE_GET_TAG(argv[1])!=JS_TAG_OBJECT) goto original;
    o=JS_VALUE_GET_OBJ(argv[1]);
    if(o->class_id!=JS_CLASS_BYTECODE_FUNCTION) goto original;
    b=o->u.func.function_bytecode;
    if(!b->has_simple_parameter_list || b->arg_count>2 || b->var_ref_count ||
       ((FRAME_KIND(b)&7)!=1 && (FRAME_KIND(b)&7)!=3)) goto original;
    if(!reviver_value_enabled()) goto original;
    root=JS_NewObject(ctx);
    if(JS_IsException(root)) return root;
    obj=JS_FrameJSONParse(ctx,this_val,1,argv);
    if(JS_IsException(obj)) {JS_FreeValue(ctx,root);return obj;}
    if(JS_DefinePropertyValue(ctx,root,JS_ATOM_empty_string,obj,JS_PROP_C_W_E)<0) {
        JS_FreeValue(ctx,root);return JS_EXCEPTION;
    }
    /* Native parse is complete, before the first user callback. Only a known
       root batch uses the reusable scope; small or cold batches stay public. */
    o=JS_IsObject(obj)?JS_VALUE_GET_OBJ(obj):NULL;
    if(o && ((o->class_id==JS_CLASS_ARRAY && o->fast_array && o->u.array.count>=16) ||
             (o->class_id==JS_CLASS_OBJECT && !o->is_exotic && o->shape->prop_count>=16)) &&
       (FRAME_KIND(b)&7)==3 && frame_value_prepared_enabled() &&
       frame_value_prepared_available(ctx))
        obj=frame_value_run_prepared(ctx,root,argv[1]);
    else
        obj=frame_json_value_property(ctx,root,JS_ATOM_empty_string,argv[1],NULL);
    JS_FreeValue(ctx,root);return obj;
original:
    return js_json_parse(ctx,this_val,argc,argv);
}
"""
    )
    return body, dict(
        original_walk_sha256=sha_text(old),
        value_walk_sha256=sha_text(walker),
        removed_prepare_sha256=sha_text(removed_prepare),
        removed_source_sha256=sha_text(removed_source),
    )


SOURCE_RECORD_RUNTIME = '/* Per-parse source records. New native TU only; no interpreter/layout change. */\ntypedef struct FrameSourceNode {\n    JSValue value;\n    JSAtom atom;\n    uint32_t next;\n    union { struct {uint32_t first,count;} object;\n            struct {uint32_t pos,len;} source; } u;\n} FrameSourceNode;\ntypedef struct FrameSourceArena {\n    FrameSourceNode *nodes;\n    uint32_t count,capacity;\n    FrameSourceNode local[16];\n    uint32_t *hash,count_hash,capacity_hash;\n    uint32_t local_hash[64];\n    void *prepared_call;\n} FrameSourceArena;\n_Static_assert(offsetof(FrameSourceArena,nodes)==0 && offsetof(FrameSourceArena,local)==16 && offsetof(FrameSourceArena,hash)==528 && offsetof(FrameSourceArena,local_hash)==544,"retain accepted source-arena prefix");\n_Static_assert(sizeof(FrameSourceNode)==32,"32-byte source node on 64-bit targets");\n\n/* RECORD_HELPERS */\nstatic uint32_t frame_source_add(FrameJSONParser *p,JSAtom atom)\n{\n    FrameSourceArena *a=p->records;FrameSourceNode *nodes,*n;uint32_t capacity,index;\n    if(a->count==a->capacity) {\n        if(a->capacity>UINT32_MAX/2/sizeof(*nodes)){p->error=1;return UINT32_MAX;}\n        capacity=a->capacity<256?256:a->capacity*2;\n        if(a->nodes==a->local) {\n            nodes=js_malloc(p->ctx,(size_t)capacity*sizeof(*nodes));\n            if(nodes)memcpy(nodes,a->nodes,(size_t)a->count*sizeof(*nodes));\n        } else nodes=js_realloc(p->ctx,a->nodes,(size_t)capacity*sizeof(*nodes));\n        if(!nodes){p->error=2;return UINT32_MAX;}\n        a->nodes=nodes;a->capacity=capacity;\n    }\n    index=a->count++;n=&a->nodes[index];n->value=JS_UNDEFINED;\n    n->atom=atom==JS_ATOM_NULL?JS_ATOM_NULL:frame_json_dup_atom(p->ctx,atom);\n    n->next=UINT32_MAX;n->u.object.first=UINT32_MAX;n->u.object.count=0;\n    return index;\n}\nstatic int frame_source_index(FrameJSONParser *p,uint32_t record)\n{\n    FrameSourceArena *a=p->records;FrameSourceNode *node=&a->nodes[record];\n    uint32_t size=16,base=a->count_hash,n,slot,need,capacity,*table;\n    if(node->u.object.count<=8)return 0;\n    while(size<node->u.object.count*2u) {\n        if(size>=0x40000000u){p->error=1;return -1;}size*=2;\n    }\n    if(base>0x7fffffffu-size-1){p->error=1;return -1;}\n    need=base+size+1;\n    if(need>a->capacity_hash){\n        capacity=a->capacity_hash;\n        while(capacity<need){if(capacity>UINT32_MAX/2){p->error=1;return -1;}capacity*=2;}\n        if(a->hash==a->local_hash){table=js_malloc(p->ctx,(size_t)capacity*sizeof(*table));if(table)memcpy(table,a->hash,(size_t)base*sizeof(*table));}\n        else table=js_realloc(p->ctx,a->hash,(size_t)capacity*sizeof(*table));\n        if(!table){p->error=2;return -1;}a->hash=table;a->capacity_hash=capacity;\n    }\n    a->hash[base]=size-1;memset(a->hash+base+1,0,(size_t)size*sizeof(*table));\n    for(n=node->u.object.first;n!=UINT32_MAX;n=a->nodes[n].next){\n        slot=((uint32_t)a->nodes[n].atom*2654435761u)&(size-1);\n        while(a->hash[base+1+slot])slot=(slot+1)&(size-1);\n        a->hash[base+1+slot]=n+1;\n    }\n    a->count_hash=need;node->u.object.first=base|0x80000000u;return 0;\n}\nstatic uint32_t frame_source_find(FrameSourceArena *a,uint32_t first,JSAtom atom)\n{\n    if(first!=UINT32_MAX&&(first&0x80000000u)){\n        uint32_t base=first&0x7fffffffu,mask=a->hash[base],slot=((uint32_t)atom*2654435761u)&mask,n;\n        while((n=a->hash[base+1+slot])){if(a->nodes[n-1].atom==atom)return n-1;slot=(slot+1)&mask;}\n        return UINT32_MAX;\n    }\n    while(first!=UINT32_MAX) {\n        if(a->nodes[first].atom==atom)return first;\n        first=a->nodes[first].next;\n    }\n    return UINT32_MAX;\n}\nstatic void frame_source_free(JSContext *ctx,FrameSourceArena *a)\n{\n    uint32_t i=a->count;\n    while(i){FrameSourceNode *n=&a->nodes[--i];JS_FreeAtom(ctx,n->atom);JS_FreeValue(ctx,n->value);}\n    if(a->nodes!=a->local)js_free(ctx,a->nodes);\n    if(a->hash!=a->local_hash)js_free(ctx,a->hash);\n    a->nodes=a->local;a->count=0;a->capacity=16;\n}\n\n/* ENTRY_BODY */\n#ifdef _MSC_VER\nextern unsigned char JS_FrameJSONReviverSourceControl;\nextern unsigned char JS_FrameJSONLoad8(const unsigned char *);\nextern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);\n#define SOURCE_CONTROL JS_FrameJSONReviverSourceControl\n#pragma section(".qjs$zzzzzzzzzzzzsrcu0",read)\n#pragma section(".qjs$zzzzzzzzzzzzsrcu2",read)\n__declspec(allocate(".qjs$zzzzzzzzzzzzsrcu0")) __declspec(align(4)) const unsigned char frame_source_ms_header[32]={/* UNWIND_HEADER */};\n__declspec(allocate(".qjs$zzzzzzzzzzzzsrcu2")) __declspec(align(4)) const unsigned char frame_source_ms_footer[24+SOURCE_UNWIND_CAPACITY]={/* SOURCE_MSVC_FOOTER */};\n#else\nstatic _Atomic unsigned char frame_source_control __attribute__((section(".qjssrm"),used));\n#define SOURCE_CONTROL frame_source_control\nconst unsigned char frame_source_unwind_header[32] __attribute__((section(".qjssrf$0"),used,aligned(4)))={/* UNWIND_HEADER */};\nconst unsigned char frame_source_unwind_footer[16] __attribute__((section(".qjssrf$Z"),used,aligned(4)))={/* UNWIND_FOOTER */};\n#endif\nJSON_CODE static unsigned char frame_source_initialize_control(void)\n{\n    const char *mode=getenv("QJS_JSON_MODE");unsigned char expected=0;\n    unsigned char value=(!mode||!strcmp(mode,"00")||!strcmp(mode,"0"))&&!getenv("QJS_DISABLE_JSON_REVIVER_SOURCE")?1:2;\n    if(value==1&&(getenv("QJS_DISABLE_JSON_SOURCE_PREPARED")||getenv("QJS_DISABLE_PREPARED_CALLBACK")))value=5;\n#ifdef _MSC_VER\n    if(!JS_FrameJSONCAS8(&SOURCE_CONTROL,&expected,value))return expected;\n#else\n    if(!atomic_compare_exchange_strong_explicit(&SOURCE_CONTROL,&expected,value,memory_order_relaxed,memory_order_relaxed))return expected;\n#endif\n    return value;\n}\nJSON_INLINE int frame_source_enabled(void)\n{\n    unsigned char state;\n#ifdef _MSC_VER\n    state=JS_FrameJSONLoad8(&SOURCE_CONTROL);\n#else\n    state=atomic_load_explicit(&SOURCE_CONTROL,memory_order_relaxed);\n#endif\n    state=state?state:frame_source_initialize_control();return (state&1)!=0;\n}\nJSON_CODE JSValue JS_FrameJSONReviverSource(JSContext *ctx,JSValueConst this_val,int argc,JSValueConst *argv)\n{\n    JSObject *o;JSFunctionBytecode *b;JSString *input;FrameJSONText text;\n    FrameSourceArena records;JSValue root,obj,input_value;size_t i;int error;\n    if(argc<2||!JS_IsString(argv[0])||JS_VALUE_GET_TAG(argv[1])!=JS_TAG_OBJECT)goto original;\n    o=JS_VALUE_GET_OBJ(argv[1]);if(o->class_id!=JS_CLASS_BYTECODE_FUNCTION)goto original;\n    b=o->u.func.function_bytecode;\n    if(!b->has_simple_parameter_list||b->arg_count<3||b->var_ref_count||\n       ((FRAME_KIND(b)&7)!=1&&(FRAME_KIND(b)&7)!=3))goto original;\n    if(!frame_source_enabled())goto original;\n    input_value=JS_ToString(ctx,argv[0]);if(JS_IsException(input_value))return input_value;\n    input=JS_VALUE_GET_STRING(input_value);\n    /* Stage one: raw source offsets are exact ASCII byte offsets. Other text\n       stays on the inherited source-record path, including UTF-16/surrogates. */\n    if(input->is_wide_char)goto unsupported;\n    text.p8=str8(input);text.p16=NULL;text.wide=0;text.length=input->len;text.pos=0;\n    for(i=0;i<text.length;i++)if(text.p8[i]>=128)goto unsupported;\n    root=JS_NewObject(ctx);if(JS_IsException(root)){JS_FreeValue(ctx,input_value);return root;}\n    records.prepared_call=NULL;\n    records.nodes=records.local;records.count=0;records.capacity=16;\n    records.hash=records.local_hash;records.count_hash=0;records.capacity_hash=64;\n    obj=frame_json_parse_text(ctx,text,0,&error,&records);\n    if(error) {\n        frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);\n        if(error==2)return JS_EXCEPTION;\n        goto original; /* No reviver callback has run; diagnostics stay core-owned. */\n    }\n    if(JS_DefinePropertyValue(ctx,root,JS_ATOM_empty_string,obj,JS_PROP_C_W_E)<0) {\n        frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);return JS_EXCEPTION;\n    }\n    if(records.count>=16&&(FRAME_KIND(b)&7)==3&&b->arg_count<=3&&\n       frame_source_prepared_enabled()&&frame_source_prepared_available(ctx))\n        obj=frame_source_run_prepared(ctx,root,argv[1],(const char *)text.p8,&records);\n    else\n        obj=frame_source_property(ctx,root,JS_ATOM_empty_string,argv[1],(const char *)text.p8,&records,0);\n    frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);return obj;\nunsupported:\n    JS_FreeValue(ctx,input_value);\noriginal:\n    return js_json_parse(ctx,this_val,argc,argv);\n}\n'


def source_codeunit_runtime(runtime):
    """Generate only the Unicode entry; accepted ASCII runtime stays verbatim."""
    old = "    /* Stage one: raw source offsets are exact ASCII byte offsets. Other text\n       stays on the inherited source-record path, including UTF-16/surrogates. */\n    if(input->is_wide_char)goto unsupported;\n    text.p8=str8(input);text.p16=NULL;text.wide=0;text.length=input->len;text.pos=0;\n    for(i=0;i<text.length;i++)if(text.p8[i]>=128)goto unsupported;"
    new = "    /* Only the old ASCII worker's unsupported text reaches this entry. */\n    text.wide=input->is_wide_char;text.length=input->len;text.pos=0;\n    text.p8=text.wide?NULL:str8(input);text.p16=text.wide?str16(input):NULL;\n    if(!text.wide) {\n        for(i=0;i<text.length;i++)if(text.p8[i]>=128)break;\n        if(i==text.length)goto unsupported;\n    }\n    if(!frame_source_codeunits_enabled())goto unsupported;"
    assert runtime.count(old) == 1
    runtime = runtime.replace(old, new)
    runtime = runtime.replace(
        "frame_source_run_prepared(ctx,root,argv[1],(const char *)text.p8,&records)",
        "frame_source_run_prepared(ctx,root,argv[1],&text,&records)",
    )
    runtime = runtime.replace(
        "frame_source_property(ctx,root,JS_ATOM_empty_string,argv[1],(const char *)text.p8,&records,0)",
        "frame_source_property(ctx,root,JS_ATOM_empty_string,argv[1],&text,&records,0)",
    )
    return runtime


def _prepare_source_variant(
    source, virtual, adapter_state=None, already_shared=(), codeunits=False, *, source_owned=True
):
    """Trace the selected fast parser in an independent TU; retain core fallback."""
    import importlib.util, json

    here = __import__("pathlib").Path(__file__).resolve().parent

    def module(name, file):
        spec = importlib.util.spec_from_file_location(
            name, _frame_tool_path(file if file != "object-adapter.py" else "object-adapter-c")
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    C = module("source_record_generator", "object-adapter.py")
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in C.FUNCTION.finditer(original)}
    parser = _frame_source_text(source, "linux-json.inc")
    parser = parser[: parser.index("/* Keep callable reviver parsing/source records")]
    parser = parser.replace(
        '_Atomic unsigned char JS_FrameJSONControl __attribute__((section(".qjscbmt$zzjson")));',
        "extern _Atomic unsigned char JS_FrameJSONControl;",
    )
    parser = parser.replace(".qjs$zzjson", ".qjssrc$C").replace(".qjsjson", ".qjssrc$C")
    runtime = source_codeunit_runtime(SOURCE_RECORD_RUNTIME) if codeunits else SOURCE_RECORD_RUNTIME
    runtime = runtime.replace(
        "/* UNWIND_HEADER */",
        ",".join(str(x) for x in b"QJSCW_UNWIND_v1!" + bytes(4) + bytes([1, 0, 0, 0]) + bytes(8)),
    )
    runtime = runtime.replace("/* UNWIND_FOOTER */", ",".join(str(x) for x in b"QJSCW_END_v1!!!!"))
    types, rest = runtime.split("/* RECORD_HELPERS */")
    helpers, entry = rest.split("/* ENTRY_BODY */")

    def replace(a, b):
        nonlocal parser
        parser = replace_one(parser, a, b)

    replace("typedef struct FrameJSONParser {", types + "\ntypedef struct FrameJSONParser {")
    replace(
        "    JSContext *ctx;\n    FrameJSONText text;",
        "    JSContext *ctx;\n    FrameSourceArena *records;\n    FrameJSONText text;",
    )
    replace("} FrameJSONParser;", "} FrameJSONParser;\n" + helpers)
    replace(
        "int cache=!(p->mode&JSON_NO_CACHE) && old->is_hashed;",
        "int cache=!(p->mode&JSON_NO_CACHE) && old->is_hashed && old->prop_count<8;",
    )
    replace(
        "static JSValue frame_json_value(FrameJSONParser *p)",
        "static JSValue frame_json_value(FrameJSONParser *p,uint32_t record)",
    )
    replace("    uint32_t idx=0;", "    uint32_t idx=0,child_record,last_record=UINT32_MAX;")
    replace(
        "    size_t n,i;\n    frame_json_space(t);c=frame_json_char(t,t->pos);",
        "    size_t n,i,start;\n    frame_json_space(t);start=t->pos;c=frame_json_char(t,t->pos);",
    )
    replace(
        "            child=frame_json_value(p);",
        """            child_record=frame_source_add(p,atom);
            if(child_record==UINT32_MAX){JS_FreeAtom(p->ctx,atom);goto invalid;}
            if(last_record==UINT32_MAX)p->records->nodes[record].u.object.first=child_record;
            else p->records->nodes[last_record].next=child_record;
            last_record=child_record;p->records->nodes[record].u.object.count++;
            child=frame_json_value(p,child_record);""",
    )
    replace(
        "        JS_FreeValue(p->ctx,prop->u.value);prop->u.value=child;return 1;",
        "        /* Preserve inherited duplicate-key source policy via fallback. */\n        p->error=1;JS_FreeValue(p->ctx,child);return -1;",
    )
    replace(
        "            if ((int)i<0) {p->error=2;goto invalid;}",
        "            if ((int)i<0) {if(!p->error)p->error=2;goto invalid;}",
    )
    replace(
        "done:\n    p->depth--;return value;",
        """done:
    if(!p->error&&c=='{'&&frame_source_index(p,record)<0){JS_FreeValue(p->ctx,value);value=JS_UNDEFINED;}
    if(!p->error) {
        FrameSourceNode *node=&p->records->nodes[record];node->value=js_dup(value);
        if(!JS_IsObject(value)){node->u.source.pos=(uint32_t)start;node->u.source.len=(uint32_t)(t->pos-start);}
    }
    p->depth--;return value;""",
    )
    replace(
        "frame_json_parse_text(JSContext *ctx,FrameJSONText text,unsigned mode,int *error)",
        "frame_json_parse_text(JSContext *ctx,FrameJSONText text,unsigned mode,int *error,FrameSourceArena *records)",
    )
    replace(
        "    unsigned i;\n    p.ctx=ctx;p.text=text;",
        "    unsigned i;uint32_t record;\n    p.records=records;\n    p.ctx=ctx;p.text=text;",
    )
    replace(
        "    value=frame_json_value(&p);frame_json_space(&p.text);",
        "    record=frame_source_add(&p,JS_ATOM_NULL);\n    value=record==UINT32_MAX?JS_EXCEPTION:frame_json_value(&p,record);frame_json_space(&p.text);",
    )
    walk = functions["internalize_json_property"][0]
    original_walk = walk
    walk = walk.replace("internalize_json_property", "frame_source_property")
    needle = "const char *text_str, JSONParseRecord *pr)"
    assert walk.count(needle) == 1
    walk = walk.replace(needle, "const char *text_str, FrameSourceArena *ar,uint32_t record)")
    needle = "    JSPropertyEnum *atoms = NULL;"
    assert walk.count(needle) == 1
    walk = walk.replace(
        needle, needle + "\n    FrameSourceNode *pr;\n    uint32_t cursor=UINT32_MAX,child_record;"
    )
    begin = walk.index("    if (pr) {")
    end = walk.index("    context = JS_NewObject(ctx);", begin)
    old_lookup = walk[begin:end]
    walk = (
        walk[:begin]
        + """    pr=record==UINT32_MAX?NULL:&ar->nodes[record];
    if(pr&&!js_same_value(ctx,pr->value,val))pr=NULL;
    if(pr&&JS_IsObject(val))cursor=pr->u.object.first;

"""
        + walk[end:]
    )
    needle = "            new_el = frame_source_property(ctx, val, prop, reviver, text_str, pr);"
    assert walk.count(needle) == 1
    walk = walk.replace(
        needle,
        """            child_record=UINT32_MAX;
            if(pr) {
                if(is_array) {child_record=cursor;if(cursor!=UINT32_MAX)cursor=ar->nodes[cursor].next;}
                else child_record=frame_source_find(ar,pr->u.object.first,prop);
            }
            new_el = frame_source_property(ctx, val, prop, reviver, text_str, ar,child_record);""",
    )
    walk = walk.replace("pr->u.primitive.source_pos", "pr->u.source.pos").replace(
        "pr->u.primitive.source_len", "pr->u.source.len"
    )
    if codeunits:
        walk = walk.replace(
            "const char *text_str, FrameSourceArena *ar,uint32_t record)",
            "const FrameJSONText *text_str, FrameSourceArena *ar,uint32_t record)",
        )
        old_slice = "new_el = JS_NewStringLen(ctx, text_str + pr->u.source.pos,\n                                     pr->u.source.len);"
        assert walk.count(old_slice) == 1
        walk = walk.replace(
            old_slice,
            "new_el = text_str->wide ? js_new_string16_len(ctx,text_str->p16+pr->u.source.pos,pr->u.source.len) :\n                js_new_string8_len(ctx,(const char *)text_str->p8+pr->u.source.pos,pr->u.source.len);",
        )

    assert "JSONParseRecord" not in walk and "res = JS_Call(ctx, reviver, holder, 3, args);" in walk
    walk = walk.replace(
        "res = JS_Call(ctx, reviver, holder, 3, args);",
        "res = frame_source_prepared_call(ctx, reviver, holder, 3, args,ar->prepared_call);",
    )

    capsule = _frame_source_text(source, "linux-prepared-callback.inc")
    cs = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    ce = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", cs)
    declarations = capsule[cs:ce]
    callback = _frame_source_text(source, "linux-json-callback.inc")
    cf = {m[2]: m[0] for m in C.FUNCTION.finditer(callback)}
    prelude = (
        "#define CALLBACK_INLINE JSON_INLINE\n"
        + declarations
        + "\n"
        + """static inline int frame_source_prepared_enabled(void)
{
#ifdef _MSC_VER
    return (JS_FrameJSONLoad8(&SOURCE_CONTROL)&4)==0;
#else
    return (atomic_load_explicit(&SOURCE_CONTROL,memory_order_relaxed)&4)==0;
#endif
}
"""
    )
    # No prepared-only control storage group; the existing source control
    # has states 1=source+prepared, 2=source disabled, 5=source only. Source admission tests bit0 identically in the on/off cases; bit2 disables preparation.
    if codeunits:
        prelude += 'JSON_INLINE int frame_source_codeunits_enabled(void)\n{\n    unsigned char state,expected,value;\n    for(;;) {\n#ifdef _MSC_VER\n        state=JS_FrameJSONLoad8(&SOURCE_CONTROL);\n#else\n        state=atomic_load_explicit(&SOURCE_CONTROL,memory_order_relaxed);\n#endif\n        if(!(state&1))return 0;\n        if(state&16)return (state&8)==0;\n        value=state|16;\n        if(getenv("QJS_DISABLE_JSON_SOURCE_CODEUNITS"))value|=8;\n        expected=state;\n#ifdef _MSC_VER\n        if(JS_FrameJSONCAS8(&SOURCE_CONTROL,&expected,value))return (value&8)==0;\n#else\n        if(atomic_compare_exchange_strong_explicit(&SOURCE_CONTROL,&expected,value,memory_order_relaxed,memory_order_relaxed))return (value&8)==0;\n#endif\n    }\n}\n'
    prelude = prelude.replace(
        "SOURCE_CONTROL",
        "frame_source_control",
    )
    # This prelude follows the source runtime control declaration below.
    available = (
        cf["frame_json_callback_available"]
        .replace("frame_json_callback_available", "frame_source_prepared_available")
        .replace("sizeof(FrameJSONCallbackPair)", "sizeof(JSFrameCallbackScope)")
    )
    bind = cf["frame_json_callback_bind"].replace(
        "frame_json_callback_bind", "frame_source_prepared_bind"
    )
    leaf = next(
        m[0] for m in C.FUNCTION.finditer(capsule) if m[2] == "frame_callback_may_have_leaf"
    )
    prelude = prelude.replace("JSONCB_INLINE", "JSON_INLINE")
    available = available.replace("JSONCB_INLINE", "JSON_INLINE")
    bind = bind.replace("JSONCB_INLINE", "JSON_INLINE")
    leaf = leaf.replace("CALLBACK_INLINE", "JSON_INLINE")
    prepared_call = """extern JSValue JS_FramePreparedCallbackSelect(JSContext *,JSValueConst,JSValueConst,JSValueConst,int,JSValueConst *,int,void *);
JSON_INLINE JSValue frame_source_prepared_call(JSContext *ctx,JSValueConst func,JSValueConst holder,int argc,JSValueConst *argv,void *scope)
{
    if(!scope)return frame_source_public_call(ctx,func,holder,argc,argv);
    return JS_FramePreparedCallbackSelect(ctx,func,holder,JS_UNDEFINED,argc,argv,2,scope);
}
"""
    run = """JSON_CODE static JSValue frame_source_run_prepared(JSContext *ctx,JSValueConst root,JSValueConst reviver,const char *text,FrameSourceArena *records)
{
    _Alignas(16) JSFrameCallbackScope call;
    JSFrameCallbackSegment *next,*following;
    JSValue result;
    call.callee=JS_UNDEFINED;call.segment.next=NULL;
    if(!frame_source_prepared_bind(ctx,reviver,3,&call))
        return frame_source_property(ctx,root,JS_ATOM_empty_string,reviver,text,records,0);
    records->prepared_call=&call;
    result=frame_source_property(ctx,root,JS_ATOM_empty_string,reviver,text,records,0);
    records->prepared_call=NULL;
    for(next=call.segment.next;next;next=following){following=next->next;js_free(ctx,next);}
    JS_FreeValue(ctx,call.callee);return result;
}
"""
    # The atomic source-control declaration must precede its load helper.
    pos = entry.index("JSON_CODE static unsigned char frame_source_initialize_control")
    controls = entry[:pos]
    entry = entry[pos:]
    if codeunits:
        run = run.replace(
            "const char *text,FrameSourceArena *records)",
            "const FrameJSONText *text,FrameSourceArena *records)",
        )
        controls = "extern _Atomic unsigned char frame_source_control;\nJSON_INLINE _Atomic unsigned char *frame_source_unit_control_slot(void)\n{\n    _Atomic unsigned char *p;\n    QJS_CONTROL_SLOT_ADDR(p, frame_source_control);\n    return p;\n}\n#define frame_source_control (*frame_source_unit_control_slot())\n#define SOURCE_CONTROL frame_source_control\n"

    backend = (
        parser
        + "\n"
        + controls
        + "\n"
        + prelude
        + "\n"
        + leaf
        + "\n"
        + available
        + "\n"
        + bind
        + "\n"
        + prepared_call
        + "\n"
        + walk
        + "\n"
        + run
        + "\n"
        + entry
    )
    # Private tiny public atom duplication and live-SP helpers are already in virtual.
    backend = backend.replace(
        "js_check_stack_overflow(ctx->rt, 0)", "frame_json_parser_stack_overflow_record(ctx->rt)"
    )
    backend += (
        """\n/* Helper prototype/body comes before the walker via the generated prelude. */\n"""
    )
    private_stack = """static inline int frame_json_parser_stack_overflow_record(JSRuntime *rt)
{
    QJS_JSON_STACK_CHECK(rt->stack_limit, rt);
}"""
    virtual += "\n" + private_stack + "\n"
    C.HOT_LOCAL_HELPERS |= {
        "string_buffer_putc8",
        "string_buffer_putc16",
        "string_buffer_write8",
        "string_buffer_write16",
        "string_buffer_puts8",
        "string_buffer_free",
        "string_buffer_init2",
        "js_new_string8_len",
        "js_new_string16_len",
        "add_fast_array_element",
        "JS_AtomGetKind",
        "js_dup_shape",
        "js_free_shape",
        "JS_AtomIsArrayIndex",
        "is_num_string",
    }
    if source_owned:
        if codeunits:
            backend = re.sub(
                r"\bJS_FrameJSONReviverSource\b", "JS_FrameJSONReviverCodeUnits", backend
            )
        return private_stack + "\n" + backend, dict(
            original_walk_sha256=sha_text(original_walk),
            generated_walk_sha256=sha_text(walk),
            removed_lookup_sha256=sha_text(old_lookup),
            selected_parser_sha256=sha_text(_frame_source_text(source, "linux-json.inc")),
            generated_parser_sha256=sha_text(parser),
            codeunits=codeunits,
        )
    raise ValueError("json_callback_c only supports source_owned=True")


TOJSON_SLOT_BACKEND = r"""
#include <stdatomic.h>
#ifdef _MSC_VER
#define SLOT_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
extern uintptr_t JS_FrameJSONToJSONShape;
extern uint32_t JS_FrameJSONToJSONSlot;
extern unsigned char JS_FrameJSONToJSONSlotControl;
#else
#define SLOT_CODE __attribute__((section(".qjssrc$C"),noipa))
static _Atomic uintptr_t JS_FrameJSONToJSONShape __attribute__((section(".qjssrm"),used));
static _Atomic uint32_t JS_FrameJSONToJSONSlot __attribute__((section(".qjssrm"),used));
static _Atomic unsigned char JS_FrameJSONToJSONSlotControl __attribute__((section(".qjssrm"),used));
#endif
#ifdef _MSC_VER
extern uintptr_t JS_FrameJSONSlotLoad64(const uintptr_t *);
extern uint32_t JS_FrameJSONSlotLoad32(const uint32_t *);
extern void JS_FrameJSONSlotStore64(uintptr_t *,uintptr_t);
extern void JS_FrameJSONSlotStore32(uint32_t *,uint32_t);
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);
#define SLOT_LOAD_SHAPE() JS_FrameJSONSlotLoad64(&JS_FrameJSONToJSONShape)
#define SLOT_LOAD_INDEX() JS_FrameJSONSlotLoad32(&JS_FrameJSONToJSONSlot)
#define SLOT_LOAD_CONTROL() JS_FrameJSONLoad8(&JS_FrameJSONToJSONSlotControl)
#define SLOT_STORE_INDEX(i) JS_FrameJSONSlotStore32(&JS_FrameJSONToJSONSlot,i)
#define SLOT_STORE_SHAPE(s) JS_FrameJSONSlotStore64(&JS_FrameJSONToJSONShape,s)
#define SLOT_CONTROL_CAS(p,v) JS_FrameJSONCAS8(&JS_FrameJSONToJSONSlotControl,p,v)
#else
#define SLOT_LOAD_SHAPE() atomic_load_explicit(&JS_FrameJSONToJSONShape,memory_order_relaxed)
#define SLOT_LOAD_INDEX() atomic_load_explicit(&JS_FrameJSONToJSONSlot,memory_order_relaxed)
#define SLOT_LOAD_CONTROL() atomic_load_explicit(&JS_FrameJSONToJSONSlotControl,memory_order_relaxed)
#define SLOT_STORE_INDEX(i) atomic_store_explicit(&JS_FrameJSONToJSONSlot,i,memory_order_relaxed)
#define SLOT_STORE_SHAPE(s) atomic_store_explicit(&JS_FrameJSONToJSONShape,s,memory_order_relaxed)
#define SLOT_CONTROL_CAS(p,v) atomic_compare_exchange_strong_explicit(&JS_FrameJSONToJSONSlotControl,p,v,memory_order_relaxed,memory_order_relaxed)
#endif
SLOT_CODE static unsigned char slot_json_initialize(void)
{
    const char *mode=getenv("QJS_JSON_MODE");unsigned char expected=0;
    unsigned char value=(!mode||!strcmp(mode,"00")||!strcmp(mode,"0"))&&!getenv("QJS_DISABLE_JSON_TOJSON_SLOT")?1:2;
    if(!SLOT_CONTROL_CAS(&expected,value))return expected;
    return value;
}
/* Readonly native qualification entry; no counters or mutation on the hot path. */
SLOT_CODE unsigned JS_FrameJSONToJSONSlotState(uintptr_t *shape,uint32_t *slot)
{
    *shape=SLOT_LOAD_SHAPE();
    *slot=SLOT_LOAD_INDEX();
    return SLOT_LOAD_CONTROL();
}
SLOT_CODE JSValue JS_FrameJSONSlotDuplicate(JSValueConst value)
{
    return js_dup(value);
}
SLOT_CODE JSValue JS_FrameJSONToJSONPropertySlow(JSContext *ctx,JSValueConst obj,
    JSAtom atom,JSValueConst receiver,bool throw_ref_error)
{
    JSObject *o;JSShape *sh;JSShapeProperty *pr;JSProperty *value;uint32_t slot;
    unsigned char control=SLOT_LOAD_CONTROL();
    if((control?control:slot_json_initialize())!=1)goto original;
    if(atom!=JS_ATOM_toJSON||throw_ref_error||JS_VALUE_GET_TAG(obj)!=JS_TAG_OBJECT||
       JS_VALUE_GET_TAG(receiver)!=JS_TAG_OBJECT||JS_VALUE_GET_PTR(obj)!=JS_VALUE_GET_PTR(receiver))goto original;
    o=JS_VALUE_GET_OBJ(obj);sh=o->shape;
    if(o->class_id!=JS_CLASS_OBJECT||o->is_exotic||!sh->is_hashed)goto original;
    /* The cached integer is never dereferenced or treated as a GC root.
       Pointer reuse and independently read atomic fields are safe because
       every hit validates the live shape's bounds, atom and property kind. */
    if(SLOT_LOAD_SHAPE()==(uintptr_t)sh){
        slot=SLOT_LOAD_INDEX();
        if(slot<(uint32_t)sh->prop_count){
            pr=&get_shape_prop(sh)[slot];
            if(pr->atom==JS_ATOM_toJSON&&!(pr->flags&JS_PROP_TMASK))return js_dup(o->prop[slot].u.value);
        }
    }
    pr=find_own_property(&value,o,JS_ATOM_toJSON);
    if(!pr||(pr->flags&JS_PROP_TMASK))goto original;
    slot=(uint32_t)(pr-get_shape_prop(sh));
    SLOT_STORE_INDEX(slot);
    SLOT_STORE_SHAPE((uintptr_t)sh);
    return js_dup(value->u.value);
original:
    return JS_GetPropertyInternal(ctx,obj,atom,receiver,throw_ref_error);
}
"""


def direct_quote_private(
    source, header, *, skip_widen=False, reference_count_model="inline-header"
):
    """Append string quotes to the live buffer; keep callback traversal owned."""
    import importlib.util

    sp = importlib.util.spec_from_file_location(
        "direct_quote_extract", _frame_tool_path("object-adapter-c")
    )
    C = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(C)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    selected = _frame_source_text(source, "linux-json.inc")
    funcs = {m[2]: m[0] for m in C.FUNCTION.finditer(original)}
    # New quote-only cursor owns no heap plan and never invokes a JS callback.
    # Input JSValue remains strongly owned until writing finishes.
    begin = selected.index("JSON_INLINE unsigned frame_json_first_lane(")
    end = selected.index("JSON_INLINE unsigned frame_json_hash(", begin)
    scanners = selected[begin:end]
    begin = selected.index("JSON_INLINE size_t frame_json_scan_latin8(")
    end = selected.index("JSON_INLINE int frame_json_key(", begin)
    quote = selected[begin:end]
    quote = quote.replace("FrameJSONWriter", "DirectJSONQuote")
    quote = quote.replace("&w->buffer", "w->buffer").replace("w->buffer.", "w->buffer->")
    text = (
        scanners
        + "\n"
        + funcs["string_buffer_putc16_slow"]
        + "\n"
        + funcs["string_buffer_putc16"]
        + "\n"
        + quote
    )
    names = (
        "frame_json_first_lane",
        "frame_json_scan8",
        "frame_json_scan16",
        "frame_json_scan_latin8",
        "frame_json_copy_wide",
        "frame_json_quote_chars",
        "frame_json_quote_latin8",
        "frame_json_quote_utf16",
        "frame_json_quote_scalar",
        "frame_json_quote",
        "string_buffer_putc16_slow",
        "string_buffer_putc16",
    )
    if not skip_widen:
        # These two current-source helpers were absent from GNU's old callback
        # closure. Own their exact bodies inside this new late TU; no new core
        # exports or formerly unreferenced early COMDAT retention.
        text = funcs["string_buffer_widen"] + "\n" + funcs["string_buffer_write16"] + "\n" + text
        names += ("string_buffer_widen", "string_buffer_write16")

        if (reference_count_model) == "inline-header":
            # The selected callback closure does not own this dependency in
            # 0.15.1. The direct escaper calls it after extraction, so copy its
            # exact current body privately rather than adding a core export.
            text = funcs["string_buffer_write8"] + "\n" + text
            names += ("string_buffer_write8",)
    for n in sorted(names, key=len, reverse=True):
        text = re.sub(r"\b" + n + r"\b", "direct_" + n, text)
    text = text.replace("JSON_INLINE", "DIRECT_INLINE").replace("JSON_CODE", "DIRECT_CODE")
    text = text.replace(
        "static no_inline int direct_string_buffer_putc16_slow",
        "DIRECT_CODE static int direct_string_buffer_putc16_slow",
    )
    text = text.replace(
        "static no_inline int direct_string_buffer_widen",
        "DIRECT_CODE static int direct_string_buffer_widen",
    )
    text = text.replace(
        "static int direct_string_buffer_write8", "DIRECT_INLINE int direct_string_buffer_write8"
    )
    prelude = """#include "qjs-json-simd.h"
#ifdef _MSC_VER
#define DIRECT_INLINE static __forceinline
#define DIRECT_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
#else
#define DIRECT_INLINE static inline __attribute__((always_inline))
#define DIRECT_CODE __attribute__((section(".qjsjcwr$C"),noipa))
#endif
enum { JSON_NO_SIMD=32 };
typedef struct DirectJSONQuote { StringBuffer *buffer; unsigned mode; } DirectJSONQuote;
"""
    helper = r"""DIRECT_CODE static int direct_quote_append(JSContext *ctx,StringBuffer *buffer,JSValueConst value,unsigned mode)
{
    DirectJSONQuote q;int result;
    if(JS_VALUE_GET_TAG(value)!=JS_TAG_STRING || (mode&64)) {
        JSValue quoted=JS_ToQuotedString(ctx,value);
        if(JS_IsException(quoted))return -1;
        result=string_buffer_concat_value(buffer,quoted);
        JS_FreeValue(ctx,quoted);return result;
    }
    q.buffer=buffer;q.mode=mode&32;
    return direct_frame_json_quote(&q,JS_VALUE_GET_STRING(value));
}
"""
    # Insert after all private declarations/definitions needed by the escaper,
    # before the exact copied traversal starts. Keep its forward declaration.
    assert header.count("    void *json_callback_scope;") == 1
    header = header.replace(
        "    void *json_callback_scope;",
        "    void *json_callback_scope;\n    unsigned direct_quote_mode;",
        1,
    )
    init = "    jsc->json_callback_scope = json_scope;"
    assert header.count(init) == 1
    header = header.replace(
        init,
        init
        + '\n    jsc->direct_quote_mode=getenv("QJS_DISABLE_JSON_DIRECT_QUOTE")?64:0;\n    if(getenv("QJS_JSON_MODE"))jsc->direct_quote_mode|=(unsigned)atoi(getenv("QJS_JSON_MODE"))&32;',
        1,
    )
    bodies = {m[2]: m[0] for m in C.FUNCTION.finditer(header)}
    target = bodies["frame_json_replacer_check"]
    assert header.count(target) == 1
    header = header.replace(target, prelude + text + "\n" + helper + "\n" + target, 1)
    qmatch = re.search(r"val = (\w*JS_ToQuotedStringFree)\(ctx, val\);", header)
    assert qmatch is not None
    quote_free = qmatch[1]  # GNU extraction retains the public helper spelling.
    a = """        val = frame_json_cb_local_JS_ToQuotedStringFree(ctx, val);
        if (JS_IsException(val))
            goto exception;
        goto concat_value;"""
    b = """        {
            int quote_result=direct_quote_append(ctx,jsc->b,val,jsc->direct_quote_mode);
            JS_FreeValue(ctx,val);
            return quote_result;
        }"""
    a = a.replace("frame_json_cb_local_JS_ToQuotedStringFree", quote_free)
    assert header.count(a) == 1
    header = header.replace(a, b, 1)
    a = """                    prop = frame_json_cb_local_JS_ToQuotedStringFree(ctx, prop);
                    if (JS_IsException(prop)) {
                        JS_FreeValue(ctx, v);
                        goto exception;
                    }
                    string_buffer_concat_value(jsc->b, sep);
                    string_buffer_concat_value(jsc->b, prop);"""
    b = """                    string_buffer_concat_value(jsc->b, sep);
                    if(direct_quote_append(ctx,jsc->b,prop,jsc->direct_quote_mode)) {
                        JS_FreeValue(ctx,v);
                        goto exception;
                    }"""
    a = a.replace("frame_json_cb_local_JS_ToQuotedStringFree", quote_free)
    assert header.count(a) == 1
    header = header.replace(a, b, 1)
    return header


DENSE_ARRAY_POP_BACKEND = r"""
/* The host pop selects contiguous storage; retain the checked C frame
   here and reduce only the no-callback dense-array semantic body. The moved
   tail cell is no longer owned/rooted by the array after count decreases.
   No cached object, shape, value, realm or native target. MIT. */
_Static_assert(sizeof(JSCFunctionListEntry)==32 &&
    offsetof(JSCFunctionListEntry,magic)==10 &&
    offsetof(JSCFunctionListEntry,u.func.cfunc)==24,
    "typed pop descriptor: name0/flags8/def9/magic10/formal16/proto17/target24");
#ifdef _MSC_VER
#define DENSE_POP_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
extern unsigned char JS_FrameDenseArrayPopControl;
extern unsigned char JS_FrameDensePopLeafControl;
extern uint64_t JS_FrameDensePopLeafHits;
extern uintptr_t JS_FrameJSONSlotLoad64(const uintptr_t *);
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);
#define POP_LOAD() JS_FrameJSONLoad8(&JS_FrameDenseArrayPopControl)
#define POP_CAS(e,v) JS_FrameJSONCAS8(&JS_FrameDenseArrayPopControl,e,v)
#define LEAF_CAS(e,v) JS_FrameJSONCAS8(&JS_FrameDensePopLeafControl,e,v)
#define LEAF_LOAD() JS_FrameJSONLoad8(&JS_FrameDensePopLeafControl)
#else
#include <stdatomic.h>
#define DENSE_POP_CODE __attribute__((section(".qjssrc$C"),noipa))
static _Atomic unsigned char dense_pop_control __attribute__((section(".qjssrm")));
static _Atomic unsigned char dense_pop_leaf_control __attribute__((section(".qjssrm")));
_Atomic uint64_t JS_FrameDensePopLeafHits __attribute__((section(".qjssrm")));
#define POP_LOAD() atomic_load_explicit(&dense_pop_control,memory_order_relaxed)
#define POP_CAS(e,v) atomic_compare_exchange_strong_explicit(&dense_pop_control,e,v,memory_order_relaxed,memory_order_relaxed)
#define LEAF_CAS(e,v) atomic_compare_exchange_strong_explicit(&dense_pop_leaf_control,e,v,memory_order_relaxed,memory_order_relaxed)
#define LEAF_LOAD() atomic_load_explicit(&dense_pop_leaf_control,memory_order_relaxed)
#endif
DENSE_POP_CODE static unsigned char dense_pop_initialize(void)
{
    unsigned char expected=0,leaf_expected=0;
    unsigned char value=getenv("QJS_DISABLE_DENSE_ARRAY_POP")?2:1;
    unsigned char leaf=getenv("QJS_DISABLE_DENSE_ARRAY_POP_LEAF")?2:1;
    LEAF_CAS(&leaf_expected,leaf);
    if(!POP_CAS(&expected,value))return expected;
    return value;
}
DENSE_POP_CODE unsigned JS_FrameDenseArrayPopState(void)
{
    return POP_LOAD();
}
DENSE_POP_CODE unsigned JS_FrameDensePopLeafState(void){return LEAF_LOAD();}
DENSE_POP_CODE uint64_t JS_FrameDensePopLeafCount(void)
{
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#ifdef _MSC_VER
    return (uint64_t)JS_FrameJSONSlotLoad64((const uintptr_t *)&JS_FrameDensePopLeafHits);
#else
    return atomic_load_explicit(&JS_FrameDensePopLeafHits,memory_order_relaxed);
#endif
#else
    return 0;
#endif
}
DENSE_POP_CODE JSValue JS_FrameDenseArrayPop(JSContext *ctx,JSValueConst this_val,
    int argc,JSValueConst *argv,int shift)
{
    JSObject *p;JSShapeProperty *length;JSValue result;uint32_t n;
    unsigned char control;
    if(shift || JS_VALUE_GET_TAG(this_val)!=JS_TAG_OBJECT)goto original;
    p=JS_VALUE_GET_OBJ(this_val);
    if(p->class_id!=JS_CLASS_ARRAY || !p->fast_array || !p->extensible)goto original;
    /* Count==length proves every indexed cell is an own present element;
       prototype methods/getters and altered prototypes cannot be observed.
       Nonextensible, frozen, sealed, readonly and sparse arrays use core. */
    length=&get_shape_prop(p->shape)[0];
    if(length->atom!=JS_ATOM_length ||
       length->flags!=(JS_PROP_WRITABLE|JS_PROP_LENGTH) ||
       JS_VALUE_GET_TAG(p->prop[0].u.value)!=JS_TAG_INT)goto original;
    n=p->u.array.count;
    if((uint32_t)JS_VALUE_GET_INT(p->prop[0].u.value)!=n)goto original;
    control=POP_LOAD();
    if((control?control:dense_pop_initialize())!=1)goto original;
    if(!n)return JS_UNDEFINED;
    --n;result=p->u.array.u.values[n];
    p->u.array.count=n;p->prop[0].u.value=js_int32(n);
    return result;
original:
    return js_array_pop(ctx,this_val,argc,argv,shift);
}
"""
