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
    upstream_root as _frame_upstream_root,
)

_frame_activate_tools()
from c_source_match import replace_one
from native_abi import current_or_load as load_layout, source_abi
from x86.common.build_tools import find_objdump

"""Extract JSON traversal bodies and current prepared-capsule declarations. MIT."""
import hashlib, re

sha_text = lambda t: hashlib.sha256(t.encode()).hexdigest()


def _probe_crt_flag(compiler_args):
    flags = [
        "/" + arg[1:]
        for arg in compiler_args[1:]
        if arg in ("/MD", "-MD", "/MT", "-MT", "/MDd", "-MDd", "/MTd", "-MTd")
    ]
    return flags[-1] if flags else "/MD"


def prepare(source, virtual):
    from pathlib import Path
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "json_callback_source_parser", _frame_tool_path("object-adapter")
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
    runtime = _frame_source_text(source, "quickjs-interpreter-json-callback.h")
    capsule = _frame_source_text(source, "quickjs-interpreter-prepared-callback.h")
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


def generate_owned(M, virtual, coff, backend, already_shared):
    # Keep the original JSON parser/lexer and large shared helpers external.
    # New small wrapper references can retain old optimized-away code in an
    # earlier core group. Own those bounded bodies in this callback island.
    known = set(already_shared) | {
        s["name"].removeprefix("qjs_frame_core_")
        for s in coff.all_symbols.values()
        if s["name"].startswith("qjs_frame_core_")
    }
    local_virtual = virtual
    local_backend = backend
    proof = []
    functions = {m[2]: m for m in M.FUNCTION.finditer(local_virtual)}
    stack_body = functions["js_get_stack_pointer"][0]
    before = "    return (uintptr_t)__builtin_frame_address(0);"
    assert stack_body.count(before) == 1
    after = (
        '#if defined(_WIN32) && defined(__x86_64__) && defined(__GNUC__) && !defined(_MSC_VER)\n    uintptr_t sp; __asm__ volatile("movq %%rsp,%0" : "=r"(sp)); return sp;\n#else\n'
        + before
        + "\n#endif"
    )
    private_stack = stack_body.replace(before, after, 1)
    assert local_virtual.count(stack_body) == 1
    local_virtual = local_virtual.replace(stack_body, private_stack, 1)
    proof.append(
        dict(
            original="js_get_stack_pointer",
            private="js_get_stack_pointer",
            body_sha256=sha_text(stack_body),
            generated_body_sha256=sha_text(private_stack),
            policy="Own inline helper uses live RSP on Windows GNU x64, including the allocated frame; all other targets retain the selected upstream body. Prevent inlined Proxy helper from imposing the previously reproduced RBP/XMM native unwind defect.",
        )
    )

    # Public atom duplication is also emitted out of line by the copied
    # reviver traversal. Keep this exact leaf inside the JSON callback island.
    functions = {m[2]: m for m in M.FUNCTION.finditer(local_virtual)}
    name = "JS_DupAtom"
    target = "frame_json_cb_local_" + name
    proof.append(
        dict(
            original=name,
            private=target,
            body_sha256=sha_text(functions[name][0]),
            policy="Exact public atom reference leaf; private identifier substitution only. Avoid retaining a formerly unreferenced core COMDAT.",
        )
    )
    pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
    local_virtual = re.sub(pattern, target, local_virtual)
    local_backend = re.sub(pattern, target, local_backend)
    local_virtual = local_virtual.replace(
        "JSAtom " + target + "(", "static inline JSAtom " + target + "(", 1
    )
    for iteration in range(64):
        header, exports, copies = M.generate(local_virtual, coff, local_backend)
        functions = {m[2]: m for m in M.FUNCTION.finditer(local_virtual)}
        new = []
        for name in sorted(set(exports) - known):
            if name == "JS_ParseJSON_internal":
                continue
            symbol = coff.symbols[name]
            rec = coff.section_records[symbol["section"] - 1]
            end = min(
                [
                    s["value"]
                    for s in coff.all_symbols.values()
                    if s["type"] & 32
                    and s["section"] == symbol["section"]
                    and s["value"] > symbol["value"]
                ]
                + [rec["size"]]
            )
            if end - symbol["value"] <= 512:
                new.append(name)
        if not new:
            return local_backend, (header, exports, copies), proof
        for name in new:
            target = "frame_json_cb_local_" + name
            assert target not in functions
            proof.append(
                dict(
                    original=name,
                    private=target,
                    body_sha256=sha_text(functions[name][0]),
                    policy="Exact bounded current-source helper; private identifier substitution only. Large parser/lexer/semantic helpers retain their original core ABI.",
                )
            )
            pattern = r"\b" + re.escape(name) + r"\b"
            local_virtual = re.sub(pattern, target, local_virtual)
            local_backend = re.sub(pattern, target, local_backend)
    raise RuntimeError("Small JSON callback helper closure did not converge")


def prepare_writable_backend(backend, C, *, msvc=False):
    def replace(before, after):
        nonlocal backend
        if before.startswith(".qjs"):
            if backend.count(before) != 1:
                raise ValueError("JSON section anchor missing or ambiguous: " + before)
            backend = backend.replace(before, after, 1)
        else:
            backend = replace_one(backend, before, after)

    replace(".qjsjson$C", ".qjsjcwr$C")
    if msvc:
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
    if msvc:
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


def compile_writable(
    source, build, callback_out, parser_out, writer_out, *, msvc=False, destination=None
):
    """Independent owned-formal JSON activation; preserve inherited entry code."""
    import importlib.util, json, os, struct
    from pathlib import Path

    here = Path(__file__).resolve().parent

    def module(name, file):
        spec = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    M = module("json_write_compiler", "atod.py")
    C = module("json_write_coff", "object-adapter.py")
    backend = (_frame_generated_file(build, "quickjs-json-callback-backend.h")).read_text(
        encoding="utf-8"
    )
    initial = backend
    backend = prepare_writable_backend(backend, C, msvc=msvc)
    split = json.loads((_frame_generated_file(build, "quickjs-json-split.json")).read_text())
    names = set(split["parts"]["callback"]["copied_helpers"])
    names |= {m[2] for m in C.FUNCTION.finditer(backend) if not m[2].startswith("JS_Frame")}
    prefix = "".join("#define " + n + " json_write_" + n + "\n" for n in sorted(names))
    declarations = """extern JSValue JS_FramePreparedCallbackWriteSelect(JSContext *,JSValueConst,JSValueConst,JSValueConst,int,JSValueConst *,int,void *);
extern JSValue JS_FrameJSONCallbackStringify(JSContext *,JSValueConst,JSValueConst,JSValueConst);
"""
    output = _frame_generated_file(build, "quickjs-interpreter-json-write.obj")

    def generate(source, path):
        header_name = "quickjs-json-callback-private.h"
        if msvc:
            # The copied traversal must retain the parent's guarded live-slot
            # lookup. This helper validates atom/type/bounds and reloads value;
            # no cached callable or stale shape pointer is introduced here.
            header = (_frame_build_file(build, header_name)).read_text(encoding="utf-8")
            signature = "static JSValue frame_json_replacer_check("
            old = "JSValue f = JS_GetProperty(ctx, val, JS_ATOM_toJSON);"
            new = "JSValue f = JS_FrameJSONToJSONProperty(ctx, val, JS_ATOM_toJSON, val, false);"
            assert (
                header.count(signature) == 2 and header.count(old) == 1
            )  # Forward declaration plus extracted definition.
            header = header.replace(
                signature,
                "extern JSValue JS_FrameJSONToJSONProperty(JSContext *,JSValueConst,JSAtom,JSValueConst,bool);\n"
                + signature,
                1,
            )
            header = header.replace(old, new, 1)
            header_name = "quickjs-json-write-private.h"
            (_frame_build_file(build, header_name)).write_text(header, encoding="utf-8")
        private = (_frame_build_file(build, header_name)).read_text(encoding="utf-8")
        private = direct_quote_private(source, private, msvc=msvc)
        header_name = "quickjs-json-direct-quote-private.h"
        (_frame_build_file(build, header_name)).write_text(private, encoding="utf-8")
        path.write_text(
            prefix + '#include "' + header_name + '"\n' + declarations + backend + "\n",
            encoding="utf-8",
        )

    merge = module("json_write_merge", "extension-merge.py")
    if msvc:
        from types import SimpleNamespace

        class WriteCoff(C.Coff):
            def finish(self):
                for index, symbol in self.all_symbols.items():
                    name = symbol["name"]
                    if (
                        symbol["storage"] != 2
                        or symbol["section"] <= 0
                        or not name.startswith(("??_C@", "__xmm@", "__real@"))
                    ):
                        continue
                    name = "qjs_ms_json_write_" + hashlib.sha256(name.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                for number, rec in enumerate(self.section_records, 1):
                    name = merge.section_name(self, number)
                    if name == ".qjssrc$C" or name.startswith(".pdata"):
                        struct.pack_into(
                            "<I", self.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040
                        )
                return super().finish()

        M.coff_module = lambda: SimpleNamespace(Coff=WriteCoff)
    original = M.win_argv
    M.win_argv = lambda cmd: [a for a in original(cmd) if not a.startswith("-g")] + (
        [] if msvc else ["-g0"]
    )
    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-json-write.c",
        late_name=".qjssrc$C" if msvc else ".qjsjcwr$C",
    )
    if msvc:
        # Caller merges these complete contributions into the existing source
        # carrier before its native-directory footer. Never add a PE section.
        (_frame_generated_file(build, "quickjs-json-write.json")).write_text(
            json.dumps(
                dict(
                    status="compiled",
                    namespace=sorted(names),
                    inherited_backend_sha256=sha_text(initial),
                    writable_backend_sha256=sha_text(backend),
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return output
    stamp = callback_out.stat()
    merge.append(
        callback_out,
        output,
        "JS_FrameJSONWriteCallbackStringify",
        "json-write",
        keep_all=True,
        code_input=".qjssrc$C" if msvc else ".qjsjcwr$C",
        code_output=".qjssrc$C" if msvc else ".qjsjcwr$C",
        pdata_output=".pdata$zzzzzznullfast" if msvc else ".qjscwfn$D",
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONParse" if msvc else "JS_FrameJSONCallbackStringify",
        baseline_sections=(),
    )
    os.utime(callback_out, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    routes = []
    route_specs = (
        (
            (callback_out, {"JS_LegacyJSONStringify"}, "JS_FrameJSONWriteCallbackStringify"),
            (
                callback_out,
                {"qjs_frame_core_js_json_stringify"},
                "JS_FrameJSONWriteNativeStringify",
            ),
        )
        if msvc
        else (
            (writer_out, {"JS_FrameJSONCallbackStringify"}, "JS_FrameJSONWriteCallbackStringify"),
        )
    )
    for image, old_names, target in route_specs:
        raw = image.read_bytes()
        obj = C.Coff(raw)
        index = obj.external(target)
        count = 0
        for number, rec in enumerate(obj.section_records, 1):
            if msvc and merge.section_name(obj, number) != ".qjs$zzjsonB":
                continue
            for i in range(rec["count"]):
                at = rec["reloc"] + i * 10
                off, sym, kind = struct.unpack_from("<IIH", obj.data, at)
                if sym not in obj.all_symbols or obj.all_symbols[sym]["name"] not in old_names:
                    continue
                assert kind == 4
                routes.append(
                    dict(
                        object=image.name,
                        section=number,
                        offset=off,
                        old=obj.all_symbols[sym]["name"],
                        target=target,
                    )
                )
                struct.pack_into("<I", obj.data, at + 4, index)
                count += 1
        assert count > 0, (image, old_names)
        if msvc:
            assert count == 1, (target, count)
        image.write_bytes(obj.finish())
    if msvc:
        os.utime(callback_out, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (_frame_generated_file(build, "quickjs-json-write.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                routes=routes,
                namespace=sorted(names),
                inherited_backend_sha256=sha_text(initial),
                writable_backend_sha256=sha_text(backend),
                policy=(
                    "MSVC typed public/native fallback routes, complete new C/unwind appended to existing late source carrier; "
                    if msvc
                    else "GNU: "
                )
                + "New TU after inherited code, same capsule ABI and unchanged owned ASM. Only the typed writer call target routes through admission; inherited parser objects and targets are unchanged. New reviver wrapper/traversal are not emitted. Replacer batch >=16; captured/eval/arguments/cold/disabled retain old paths. toJSON benefits only inside admitted writable-replacer traversal.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def compile_reviver_value(
    source, build, callback_out, parser_out, *, msvc=False, destination=None, source_owned=False
):
    """GNU late unit: extra argument is unobservable only under validated guards."""
    import importlib.util, json, os, struct
    from pathlib import Path

    here = Path(__file__).resolve().parent

    def module(name, file):
        sp = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    M = module("reviver_value_compiler", "atod.py")
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
    split = (
        dict(
            callback_generation=dict(owned_core_helpers=[]),
            parts=dict(callback=dict(copied_helpers=[])),
        )
        if source_owned
        else json.loads((_frame_generated_file(build, "quickjs-json-split.json")).read_text())
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
    private = (
        ""
        if source_owned
        else (_frame_generated_file(build, "quickjs-json-callback-private.h")).read_text(
            encoding="utf-8"
        )
    )
    inherited = private
    if not source_owned:
        for name in (
            "frame_json_reviver_property",
            "frame_json_reviver_parse",
            "frame_json_replacer_check",
            "frame_json_replacer_to_str",
            "frame_json_replacer_stringify",
        ):
            bodies = [m[0] for m in C.FUNCTION.finditer(private) if m[2] == name]
            assert len(bodies) == 1, (name, len(bodies))
            private = private.replace(bodies[0], "", 1)
            pattern = r"^static[^\n;{}]*\b" + name + r"\([^;{}]*\);[ \t]*\n"
            private, count = re.subn(pattern, "", private, flags=re.M)
            assert count == 1, (name, count)
        # The two callback-call prototypes belonged only to removed traversal copies.
        private = re.sub(
            r"^static[^\n;{}]*\bframe_json_callback_(?:call|free)\([^;{}]*\);[ \t]*\n",
            "",
            private,
            flags=re.M,
        )
    split = (
        dict(
            callback_generation=dict(owned_core_helpers=[]),
            parts=dict(callback=dict(copied_helpers=[])),
        )
        if source_owned
        else json.loads((_frame_generated_file(build, "quickjs-json-split.json")).read_text())
    )
    names = set(split["parts"]["callback"]["copied_helpers"]) | {
        "frame_json_value_property",
        "frame_json_callback_stack_overflow",
    }

    capsule = _frame_source_text(source, "quickjs-interpreter-prepared-callback.h")
    cs = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    ce = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", cs)
    declarations = capsule[cs:ce]
    callback = _frame_source_text(source, "quickjs-interpreter-json-callback.h")
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
    names |= {m[2] for m in C.FUNCTION.finditer(prepared + "\n" + run)}

    prefix = "".join("#define " + n + " reviver_value_" + n + "\n" for n in sorted(names))
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
    uintptr_t sp;__asm__ volatile("movq %%rsp,%0" : "=r"(sp));
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
    if source_owned:
        return body, dict(
            original_walk_sha256=sha_text(old),
            value_walk_sha256=sha_text(walker),
            removed_prepare_sha256=sha_text(removed_prepare),
            removed_source_sha256=sha_text(removed_source),
        )
    if msvc:
        # Existing qualified atomic leaf ABI, with a separately owned new byte.
        body = body.replace(
            '#define REVIVER_CODE __attribute__((section(".qjsjcrv$C"),noipa))',
            '#define REVIVER_CODE __declspec(code_seg(".qjsjcrv$C")) __declspec(noinline)',
        )
        body = body.replace(
            'static _Atomic unsigned char reviver_value_control __attribute__((section(".qjsrvmd"),used));',
            "extern unsigned char JS_FrameJSONReviverValueControl;\n#define reviver_value_control JS_FrameJSONReviverValueControl\n"
            "extern unsigned char JS_FrameJSONLoad8(const unsigned char *);\n"
            "extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);",
        )
        body = body.replace(
            "atomic_compare_exchange_strong_explicit(&reviver_value_control,&expected,value,\n            memory_order_relaxed,memory_order_relaxed)",
            "JS_FrameJSONCAS8(&reviver_value_control,&expected,value)",
        )
        body = body.replace("static inline __attribute__((always_inline))", "static __forceinline")
        body = body.replace(
            "#define REVIVER_INLINE static inline __attribute__((always_inline))",
            "#define REVIVER_INLINE static __forceinline",
        )
        body = body.replace(
            "atomic_load_explicit(&reviver_value_control,memory_order_relaxed)",
            "JS_FrameJSONLoad8(&reviver_value_control)",
        )
        body = body.replace(
            '    uintptr_t sp;__asm__ volatile("movq %%rsp,%0" : "=r"(sp));\n    return unlikely(sp<rt->stack_limit);',
            "    return js_check_stack_overflow(rt,0);",
        )
        # Copied capsule helpers retain compiler-conditional GNU branches.
        assert (
            "#define REVIVER_CODE __declspec" in body
            and "#define REVIVER_INLINE static __forceinline" in body
        )
        from types import SimpleNamespace

        Base = C.Coff

        class ReviverCoff(Base):
            def finish(self):
                # Namespace compiler constants before merging into one COFF;
                # keep COMDAT attributes, payloads and relocation indexes.
                for index, symbol in self.all_symbols.items():
                    name = symbol["name"]
                    if (
                        symbol["storage"] != 2
                        or symbol["section"] <= 0
                        or not name.startswith(("??_C@", "__xmm@", "__real@"))
                    ):
                        continue
                    assert self.section_records[symbol["section"] - 1]["flags"] & 0x1000
                    name = (
                        "qjs_reviver_value_const_" + hashlib.sha256(name.encode()).hexdigest()[:32]
                    )
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                for number, rec in enumerate(self.section_records, 1):
                    name = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode("ascii")
                    if name.startswith("/"):
                        at = int(name[1:])
                        name = self.strings[at : self.strings.index(0, at)].decode("ascii")
                    if name == ".qjsjcrv$C":
                        # Match the qualified MS JSON RX-data convention;
                        # retain full compiler bytes and fixups, without padding.
                        flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                        struct.pack_into(
                            "<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040
                        )
                return super().finish()

        M.coff_module = lambda: SimpleNamespace(Coff=ReviverCoff)
    output = _frame_generated_file(build, "quickjs-interpreter-json-reviver-value.obj")

    def generate(source, path):
        path.write_text(prefix + private + "\n" + body + "\n", encoding="utf-8")

    argv = M.win_argv
    M.win_argv = lambda cmd: [a for a in argv(cmd) if not a.startswith("-g")] + ["-g0"]
    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-json-reviver-value.c",
        late_name=".qjsjcrv$C",
    )
    if msvc:
        assert destination is not None
        callback_out = destination
    merge = module("reviver_value_merge", "extension-merge.py")
    stamp = callback_out.stat()
    merge.append(
        callback_out,
        output,
        "JS_FrameJSONReviverValue",
        "json-reviver-value",
        keep_all=True,
        writable_metadata_inputs=() if msvc else (".qjsrvmd",),
        code_input=".qjsjcrv$C",
        code_output=".qjs$zzzzzzzzzzrvV" if msvc else ".qjsjcrv$C",
        pdata_output=".pdata$zzzzzzjsonReviverV" if msvc else ".qjscwfn$E",
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONParse" if msvc else "JS_FrameJSONCallbackStringify",
        baseline_sections=(),
    )
    os.utime(callback_out, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    route_owner = callback_out if msvc else parser_out
    c = C.Coff(route_owner.read_bytes())
    index = c.external("JS_FrameJSONReviverValue")
    routes = []
    for number, rec in enumerate(c.section_records, 1):
        if msvc and merge.section_name(c, number) != ".qjs$zzjsonA":
            continue
        for i in range(rec["count"]):
            at = rec["reloc"] + i * 10
            off, sym, kind = struct.unpack_from("<IIH", c.data, at)
            if sym not in c.all_symbols or c.all_symbols[sym]["name"] not in (
                "js_json_parse",
                "qjs_frame_core_js_json_parse",
            ):
                continue
            assert kind == 4
            routes.append(
                dict(
                    object=route_owner.name,
                    section=number,
                    offset=off,
                    old=c.all_symbols[sym]["name"],
                    target="JS_FrameJSONReviverValue",
                )
            )
            struct.pack_into("<I", c.data, at + 4, index)
    assert len(routes) == 2, routes
    route_owner.write_bytes(c.finish())
    if msvc:
        os.utime(route_owner, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (_frame_generated_file(build, "quickjs-json-reviver-value.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                routes=routes,
                original_walk_sha256=sha_text(old),
                value_walk_sha256=sha_text(walker),
                removed_prepare_sha256=sha_text(removed_prepare),
                removed_source_sha256=sha_text(removed_source),
                inherited_private_header_sha256=sha_text(inherited),
                private_header_sha256=sha_text(private),
                namespace=sorted(names),
                toolchain="msvc" if msvc else "mingw",
                policy="Warm validated normal bytecode, simple <=2 formals, no own var refs. No mutable length hint. Native fast parse without source records; exact source-owned recursive mutations/errors/ownership; actual argc3 with unobservable undefined context. Non-string/third-formal/arguments/eval/rest/proxy/bound/cold/modes/disabled use core path. Atomic startup control cache in independent late RW byte; hot calls never query getenv. Existing argc3 readonly capsule for root batches >=16, one explicit scope propagated through source-owned traversal; startup bit2 disables value preparation. No core/ASM rewrite.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


SOURCE_RECORD_RUNTIME = '/* Per-parse source records. New native TU only; no interpreter/layout change. */\ntypedef struct FrameSourceNode {\n    JSValue value;\n    JSAtom atom;\n    uint32_t next;\n    union { struct {uint32_t first,count;} object;\n            struct {uint32_t pos,len;} source; } u;\n} FrameSourceNode;\ntypedef struct FrameSourceArena {\n    FrameSourceNode *nodes;\n    uint32_t count,capacity;\n    FrameSourceNode local[16];\n    uint32_t *hash,count_hash,capacity_hash;\n    uint32_t local_hash[64];\n    void *prepared_call;\n} FrameSourceArena;\n_Static_assert(offsetof(FrameSourceArena,nodes)==0 && offsetof(FrameSourceArena,local)==16 && offsetof(FrameSourceArena,hash)==528 && offsetof(FrameSourceArena,local_hash)==544,"retain accepted source-arena prefix");\n_Static_assert(sizeof(FrameSourceNode)==32,"32-byte source node on Windows x64");\n\n/* RECORD_HELPERS */\nstatic uint32_t frame_source_add(FrameJSONParser *p,JSAtom atom)\n{\n    FrameSourceArena *a=p->records;FrameSourceNode *nodes,*n;uint32_t capacity,index;\n    if(a->count==a->capacity) {\n        if(a->capacity>UINT32_MAX/2/sizeof(*nodes)){p->error=1;return UINT32_MAX;}\n        capacity=a->capacity<256?256:a->capacity*2;\n        if(a->nodes==a->local) {\n            nodes=js_malloc(p->ctx,(size_t)capacity*sizeof(*nodes));\n            if(nodes)memcpy(nodes,a->nodes,(size_t)a->count*sizeof(*nodes));\n        } else nodes=js_realloc(p->ctx,a->nodes,(size_t)capacity*sizeof(*nodes));\n        if(!nodes){p->error=2;return UINT32_MAX;}\n        a->nodes=nodes;a->capacity=capacity;\n    }\n    index=a->count++;n=&a->nodes[index];n->value=JS_UNDEFINED;\n    n->atom=atom==JS_ATOM_NULL?JS_ATOM_NULL:frame_json_dup_atom(p->ctx,atom);\n    n->next=UINT32_MAX;n->u.object.first=UINT32_MAX;n->u.object.count=0;\n    return index;\n}\nstatic int frame_source_index(FrameJSONParser *p,uint32_t record)\n{\n    FrameSourceArena *a=p->records;FrameSourceNode *node=&a->nodes[record];\n    uint32_t size=16,base=a->count_hash,n,slot,need,capacity,*table;\n    if(node->u.object.count<=8)return 0;\n    while(size<node->u.object.count*2u) {\n        if(size>=0x40000000u){p->error=1;return -1;}size*=2;\n    }\n    if(base>0x7fffffffu-size-1){p->error=1;return -1;}\n    need=base+size+1;\n    if(need>a->capacity_hash){\n        capacity=a->capacity_hash;\n        while(capacity<need){if(capacity>UINT32_MAX/2){p->error=1;return -1;}capacity*=2;}\n        if(a->hash==a->local_hash){table=js_malloc(p->ctx,(size_t)capacity*sizeof(*table));if(table)memcpy(table,a->hash,(size_t)base*sizeof(*table));}\n        else table=js_realloc(p->ctx,a->hash,(size_t)capacity*sizeof(*table));\n        if(!table){p->error=2;return -1;}a->hash=table;a->capacity_hash=capacity;\n    }\n    a->hash[base]=size-1;memset(a->hash+base+1,0,(size_t)size*sizeof(*table));\n    for(n=node->u.object.first;n!=UINT32_MAX;n=a->nodes[n].next){\n        slot=((uint32_t)a->nodes[n].atom*2654435761u)&(size-1);\n        while(a->hash[base+1+slot])slot=(slot+1)&(size-1);\n        a->hash[base+1+slot]=n+1;\n    }\n    a->count_hash=need;node->u.object.first=base|0x80000000u;return 0;\n}\nstatic uint32_t frame_source_find(FrameSourceArena *a,uint32_t first,JSAtom atom)\n{\n    if(first!=UINT32_MAX&&(first&0x80000000u)){\n        uint32_t base=first&0x7fffffffu,mask=a->hash[base],slot=((uint32_t)atom*2654435761u)&mask,n;\n        while((n=a->hash[base+1+slot])){if(a->nodes[n-1].atom==atom)return n-1;slot=(slot+1)&mask;}\n        return UINT32_MAX;\n    }\n    while(first!=UINT32_MAX) {\n        if(a->nodes[first].atom==atom)return first;\n        first=a->nodes[first].next;\n    }\n    return UINT32_MAX;\n}\nstatic void frame_source_free(JSContext *ctx,FrameSourceArena *a)\n{\n    uint32_t i=a->count;\n    while(i){FrameSourceNode *n=&a->nodes[--i];JS_FreeAtom(ctx,n->atom);JS_FreeValue(ctx,n->value);}\n    if(a->nodes!=a->local)js_free(ctx,a->nodes);\n    if(a->hash!=a->local_hash)js_free(ctx,a->hash);\n    a->nodes=a->local;a->count=0;a->capacity=16;\n}\n\n/* ENTRY_BODY */\n#ifdef _MSC_VER\nextern unsigned char JS_FrameJSONReviverSourceControl;\nextern unsigned char JS_FrameJSONLoad8(const unsigned char *);\nextern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);\n#define SOURCE_CONTROL JS_FrameJSONReviverSourceControl\n#pragma section(".qjs$zzzzzzzzzzzzsrcu0",read)\n#pragma section(".qjs$zzzzzzzzzzzzsrcu2",read)\n__declspec(allocate(".qjs$zzzzzzzzzzzzsrcu0")) __declspec(align(4)) const unsigned char frame_source_ms_header[32]={/* UNWIND_HEADER */};\n__declspec(allocate(".qjs$zzzzzzzzzzzzsrcu2")) __declspec(align(4)) const unsigned char frame_source_ms_footer[24+SOURCE_UNWIND_CAPACITY]={/* SOURCE_MSVC_FOOTER */};\n#else\nstatic _Atomic unsigned char frame_source_control __attribute__((section(".qjssrm"),used));\n#define SOURCE_CONTROL frame_source_control\nconst unsigned char frame_source_unwind_header[32] __attribute__((section(".qjssrf$0"),used,aligned(4)))={/* UNWIND_HEADER */};\nconst unsigned char frame_source_unwind_footer[16] __attribute__((section(".qjssrf$Z"),used,aligned(4)))={/* UNWIND_FOOTER */};\n#endif\nJSON_CODE static unsigned char frame_source_initialize_control(void)\n{\n    const char *mode=getenv("QJS_JSON_MODE");unsigned char expected=0;\n    unsigned char value=(!mode||!strcmp(mode,"00")||!strcmp(mode,"0"))&&!getenv("QJS_DISABLE_JSON_REVIVER_SOURCE")?1:2;\n    if(value==1&&(getenv("QJS_DISABLE_JSON_SOURCE_PREPARED")||getenv("QJS_DISABLE_PREPARED_CALLBACK")))value=5;\n#ifdef _MSC_VER\n    if(!JS_FrameJSONCAS8(&SOURCE_CONTROL,&expected,value))return expected;\n#else\n    if(!atomic_compare_exchange_strong_explicit(&SOURCE_CONTROL,&expected,value,memory_order_relaxed,memory_order_relaxed))return expected;\n#endif\n    return value;\n}\nJSON_INLINE int frame_source_enabled(void)\n{\n    unsigned char state;\n#ifdef _MSC_VER\n    state=JS_FrameJSONLoad8(&SOURCE_CONTROL);\n#else\n    state=atomic_load_explicit(&SOURCE_CONTROL,memory_order_relaxed);\n#endif\n    state=state?state:frame_source_initialize_control();return (state&1)!=0;\n}\nJSON_CODE JSValue JS_FrameJSONReviverSource(JSContext *ctx,JSValueConst this_val,int argc,JSValueConst *argv)\n{\n    JSObject *o;JSFunctionBytecode *b;JSString *input;FrameJSONText text;\n    FrameSourceArena records;JSValue root,obj,input_value;size_t i;int error;\n    if(argc<2||!JS_IsString(argv[0])||JS_VALUE_GET_TAG(argv[1])!=JS_TAG_OBJECT)goto original;\n    o=JS_VALUE_GET_OBJ(argv[1]);if(o->class_id!=JS_CLASS_BYTECODE_FUNCTION)goto original;\n    b=o->u.func.function_bytecode;\n    if(!b->has_simple_parameter_list||b->arg_count<3||b->var_ref_count||\n       ((FRAME_KIND(b)&7)!=1&&(FRAME_KIND(b)&7)!=3))goto original;\n    if(!frame_source_enabled())goto original;\n    input_value=JS_ToString(ctx,argv[0]);if(JS_IsException(input_value))return input_value;\n    input=JS_VALUE_GET_STRING(input_value);\n    /* Stage one: raw source offsets are exact ASCII byte offsets. Other text\n       stays on the inherited source-record path, including UTF-16/surrogates. */\n    if(input->is_wide_char)goto unsupported;\n    text.p8=str8(input);text.p16=NULL;text.wide=0;text.length=input->len;text.pos=0;\n    for(i=0;i<text.length;i++)if(text.p8[i]>=128)goto unsupported;\n    root=JS_NewObject(ctx);if(JS_IsException(root)){JS_FreeValue(ctx,input_value);return root;}\n    records.prepared_call=NULL;\n    records.nodes=records.local;records.count=0;records.capacity=16;\n    records.hash=records.local_hash;records.count_hash=0;records.capacity_hash=64;\n    obj=frame_json_parse_text(ctx,text,0,&error,&records);\n    if(error) {\n        frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);\n        if(error==2)return JS_EXCEPTION;\n        goto original; /* No reviver callback has run; diagnostics stay core-owned. */\n    }\n    if(JS_DefinePropertyValue(ctx,root,JS_ATOM_empty_string,obj,JS_PROP_C_W_E)<0) {\n        frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);return JS_EXCEPTION;\n    }\n    if(records.count>=16&&(FRAME_KIND(b)&7)==3&&b->arg_count<=3&&\n       frame_source_prepared_enabled()&&frame_source_prepared_available(ctx))\n        obj=frame_source_run_prepared(ctx,root,argv[1],(const char *)text.p8,&records);\n    else\n        obj=frame_source_property(ctx,root,JS_ATOM_empty_string,argv[1],(const char *)text.p8,&records,0);\n    frame_source_free(ctx,&records);JS_FreeValue(ctx,root);JS_FreeValue(ctx,input_value);return obj;\nunsupported:\n    JS_FreeValue(ctx,input_value);\noriginal:\n    return js_json_parse(ctx,this_val,argc,argv);\n}\n'


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


def prepare_source_records(source, virtual, coff, already_shared):
    old_header, old_backend, exports, proof = _prepare_source_variant(
        source, virtual, coff, already_shared
    )
    header, backend, unit_exports, unit_proof = _prepare_source_variant(
        source, virtual, coff, set(already_shared) | set(exports), True
    )
    assert set(unit_exports) <= set(already_shared) | set(exports), (
        "Unicode retained a new early core helper"
    )
    proof["codeunit_generated"] = dict(header=header, backend=backend)
    proof["codeunit_isolation"] = unit_proof
    proof["policy"] += (
        " Unicode is a separate private TU, one typed old-worker fallback, shared atomic control byte. Original ASCII backend/header remain verbatim."
    )
    return old_header, old_backend, exports, proof


def _prepare_source_variant(
    source, virtual, coff, already_shared, codeunits=False, *, source_owned=False
):
    """Trace the selected fast parser in an independent TU; retain core fallback."""
    import importlib.util, json

    here = __import__("pathlib").Path(__file__).resolve().parent

    def module(name, file):
        spec = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    C = module("source_record_generator", "object-adapter.py")
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in C.FUNCTION.finditer(original)}
    parser = _frame_source_text(source, "quickjs-interpreter-json.h")
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

    capsule = _frame_source_text(source, "quickjs-interpreter-prepared-callback.h")
    cs = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    ce = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", cs)
    declarations = capsule[cs:ce]
    callback = _frame_source_text(source, "quickjs-interpreter-json-callback.h")
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
    # No prepared-only control storage/COFF group; the existing source control
    # has states 1=source+prepared, 2=source disabled, 5=source only. Source admission tests bit0 identically in the on/off cases; bit2 disables preparation.
    if codeunits:
        prelude += 'JSON_INLINE int frame_source_codeunits_enabled(void)\n{\n    unsigned char state,expected,value;\n    for(;;) {\n#ifdef _MSC_VER\n        state=JS_FrameJSONLoad8(&SOURCE_CONTROL);\n#else\n        state=atomic_load_explicit(&SOURCE_CONTROL,memory_order_relaxed);\n#endif\n        if(!(state&1))return 0;\n        if(state&16)return (state&8)==0;\n        value=state|16;\n        if(getenv("QJS_DISABLE_JSON_SOURCE_CODEUNITS"))value|=8;\n        expected=state;\n#ifdef _MSC_VER\n        if(JS_FrameJSONCAS8(&SOURCE_CONTROL,&expected,value))return (value&8)==0;\n#else\n        if(atomic_compare_exchange_strong_explicit(&SOURCE_CONTROL,&expected,value,memory_order_relaxed,memory_order_relaxed))return (value&8)==0;\n#endif\n    }\n}\n'
    prelude = prelude.replace(
        "SOURCE_CONTROL",
        "JS_FrameJSONReviverSourceControl"
        if (coff is not None and any(s["name"] == ".drectve" for s in coff.sections))
        else "frame_source_control",
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
        controls = '#ifdef _MSC_VER\nextern unsigned char JS_FrameJSONReviverSourceControl;\nextern unsigned char JS_FrameJSONLoad8(const unsigned char *);\nextern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);\n#define SOURCE_CONTROL JS_FrameJSONReviverSourceControl\n#else\nextern _Atomic unsigned char frame_source_control;\nJSON_INLINE _Atomic unsigned char *frame_source_unit_control_slot(void)\n{\n    _Atomic unsigned char *p;\n    __asm__("leaq frame_source_control(%%rip),%0":"=r"(p));return p;\n}\n#define frame_source_control (*frame_source_unit_control_slot())\n#define SOURCE_CONTROL frame_source_control\n#endif\n'

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
#if defined(__GNUC__) && defined(_WIN32) && defined(__x86_64__) && !defined(_MSC_VER)
    uintptr_t sp;__asm__ volatile("movq %%rsp,%0" : "=r"(sp));return unlikely(sp<rt->stack_limit);
#else
    return js_check_stack_overflow(rt,0);
#endif
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
            selected_parser_sha256=sha_text(
                _frame_source_text(source, "quickjs-interpreter-json.h")
            ),
            generated_parser_sha256=sha_text(parser),
            codeunits=codeunits,
        )
    backend, (header, exports, copies), owned = generate_owned(
        C, virtual, coff, backend, already_shared
    )

    header += "\nextern JSValue frame_source_public_call(JSContext *,JSValueConst,JSValueConst,int,JSValueConst *);\n"
    names = set(copies) | {
        m[2] for m in C.FUNCTION.finditer(backend) if m[2] != "JS_FrameJSONReviverSource"
    }
    prefix = "".join(
        "#define " + n + (" source_unit_" if codeunits else " source_record_") + n + "\n"
        for n in sorted(names)
    )
    proof = dict(
        status="prepared",
        owned_core_helpers=owned,
        original_walk_sha256=sha_text(original_walk),
        generated_walk_sha256=sha_text(walk),
        removed_lookup_sha256=sha_text(old_lookup),
        selected_parser_sha256=sha_text(_frame_source_text(source, "quickjs-interpreter-json.h")),
        generated_parser_sha256=sha_text(parser),
        exports=exports,
        copied_helpers=copies,
        namespace=sorted(names),
        policy="Separate fast ASCII parser trace, 32-byte stable-index nodes, local16 then owned vector, linear reverse release. Original property snapshots/Get/mutations/context/source construction/argc3/errors retained. Duplicate keys, non-ASCII, cold/unsupported/captured/nonstring/modes/disabled stay core. Arrays use sequential record cursors; object lookup linked by exact atom.",
    )
    if codeunits:
        backend = re.sub(r"\bJS_FrameJSONReviverSource\b", "JS_FrameJSONReviverCodeUnits", backend)
        proof.update(
            namespace_prefix="source_unit_",
            policy="Native Latin1/UTF16 source coordinates and exact slices in an independent TU; copied parser/walker/owned helper bodies, existing capsule ABI, only unsupported nonASCII strings admitted; shared source control bit16 initialized / bit8 disabled. No new early helper/RW group.",
        )
    return prefix + header, backend, exports, proof


def source_unwind_capacity(build, coff):
    """Bound directory storage by a required compiler input, never ambient objects.

    The core-sized backend allowance and 512 frontend/CRT records are storage
    bounds, not instruction padding. Final image publication checks the bound.
    Test/frontend object scheduling must not move downstream VM contributions.
    """
    import hashlib, struct

    obj = _frame_generated_file(build, "quickjs-core-original.obj")
    raw = obj.read_bytes()
    cc = coff.Coff(raw)
    rows = 0
    for rr in cc.section_records:
        if rr["size"] and rr["size"] % 12 == 0 and rr["count"] == rr["size"] // 4:
            rel = [
                struct.unpack_from("<IIH", cc.data, rr["reloc"] + 10 * i)
                for i in range(rr["count"])
            ]
            if all(kind == 3 for off, idx, kind in rel) and sorted(
                off for off, idx, kind in rel
            ) == list(range(0, rr["size"], 4)):
                rows += rr["size"] // 12
    if not rows:
        raise RuntimeError("Pinned compiler core has no unwind records")
    return dict(
        capacity_bytes=12 * (2 * rows + 512),
        compiler_record_inputs=[
            dict(object=str(obj), sha256=hashlib.sha256(raw).hexdigest(), records=rows)
        ],
        backend_allowance_records=rows,
        frontend_crt_reserve_records=512,
        policy="One required pristine core input, one core-sized backend allowance, 512 frontend/CRT records; independent of unrelated objects and build history.",
    )


def compile_source_records(source, build, owner, *, msvc=False):
    import importlib.util, json, os, struct
    from pathlib import Path
    from types import SimpleNamespace

    here = Path(__file__).resolve().parent

    def module(name, file):
        spec = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    M = module("source_record_compiler", "atod.py")
    C = module("source_record_coff", "object-adapter.py")
    Base = C.Coff
    slot_output = compile_tojson_slot(source, build, msvc=msvc)
    slice_output = compile_slice_simple(source, build) if msvc else None
    release_output = module("bigint_release_compiler", "free-boundary.py").compile_big_release(
        source, build, msvc=msvc
    )
    pop_output = compile_dense_array_pop(source, build, msvc=msvc)

    class SourceCoff(Base):
        def finish(self):
            for index, s in self.all_symbols.items():
                n = s["name"]
                if n == "frame_source_control" and s["section"] > 0 and s["storage"] == 3:
                    self.data[self.table + index * self.stride + 16] = 2
                if n == "frame_source_public_call":
                    assert s["storage"] == 2 and s["section"] == 0
                    at = len(self.strings)
                    self.strings += b"JS_Call\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                    continue
                if (
                    s["storage"] == 2
                    and s["section"] > 0
                    and n.startswith(("??_C@", "__xmm@", "__real@"))
                ):
                    n = "qjs_source_record_const_" + hashlib.sha256(n.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += n.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for rec in self.section_records:
                n = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode("ascii")
                if n.startswith("/"):
                    at = int(n[1:])
                    n = self.strings[at : self.strings.index(0, at)].decode("ascii")
                if n in (
                    ".qjssrc$C",
                    ".qjssrf$0",
                    ".qjssrf$Z",
                    ".qjs$zzzzzzzzzzzzsrcu0",
                    ".qjs$zzzzzzzzzzzzsrcu2",
                ) or (msvc and n.startswith(".pdata")):
                    flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                    struct.pack_into("<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040)
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=SourceCoff)
    argv = M.win_argv
    M.win_argv = lambda cmd: [a for a in argv(cmd) if not a.startswith("-g")] + (
        [] if msvc else ["-g0"]
    )
    unit_output = _frame_generated_file(build, "quickjs-interpreter-json-source-codeunits.obj")

    class UnitCoff(SourceCoff):
        def finish(self):
            for index, s in self.all_symbols.items():
                n = s["name"]
                if (
                    s["storage"] == 2
                    and s["section"] > 0
                    and n.startswith(("??_C@", "__xmm@", "__real@"))
                ):
                    name = "qjs_source_unit_const_" + hashlib.sha256(n.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                    s["name"] = name
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=UnitCoff)

    def generate_unit(source, path):
        path.write_text(
            '#include "quickjs-json-source-codeunits-private.h"\n'
            + (_frame_generated_file(build, "quickjs-json-source-codeunits-backend.h")).read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        unit_output,
        generator=generate_unit,
        filename="quickjs-interpreter-json-source-codeunits.c",
        late_name=".qjssrc$C",
    )
    M.coff_module = lambda: SimpleNamespace(Coff=SourceCoff)
    output = _frame_generated_file(build, "quickjs-interpreter-json-source-record.obj")

    def generate(source, path):
        body = (_frame_generated_file(build, "quickjs-json-source-backend.h")).read_text(
            encoding="utf-8"
        )
        capacity = 0
        inputs = []
        capacity_proof = {}
        if msvc:
            capacity_proof = source_unwind_capacity(build, C)
            capacity = capacity_proof["capacity_bytes"]
            inputs = capacity_proof["compiler_record_inputs"]
            assert body.count("/* SOURCE_MSVC_FOOTER */") == 1
            body = body.replace(
                "/* SOURCE_MSVC_FOOTER */",
                ",".join(str(v) for v in b"QJSCW_END_v1!!!!" + struct.pack("<II", capacity, 1)),
            )
        path.write_text(
            "#define SOURCE_UNWIND_CAPACITY "
            + str(capacity)
            + '\n#include "quickjs-json-source-private.h"\n'
            + body,
            encoding="utf-8",
        )
        (_frame_generated_file(build, "quickjs-json-source-unwind-capacity.json")).write_text(
            json.dumps(
                dict(
                    capacity_bytes=capacity,
                    compiler_record_inputs=inputs,
                    frontend_crt_reserve_records=512 if msvc else 0,
                    **{
                        k: v
                        for k, v in capacity_proof.items()
                        if k
                        not in (
                            "capacity_bytes",
                            "compiler_record_inputs",
                            "frontend_crt_reserve_records",
                        )
                    },
                ),
                indent=2,
            )
            + "\n"
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-json-source-record.c",
        late_name=".qjssrc$C",
    )
    merge = module("source_record_merge", "extension-merge.py")
    stamp = owner.stat()
    # Preserve every old ASCII instruction; retarget only its typed fallback call.
    old_source = C.Coff(output.read_bytes())
    target = old_source.external("JS_FrameJSONReviverCodeUnits")
    fallbacks = []
    for number, rec in enumerate(old_source.section_records, 1):
        if not rec["flags"] & 0x20000000:
            continue
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", old_source.data, at)
            if old_source.all_symbols[sym]["name"] not in (
                "js_json_parse",
                "qjs_frame_core_js_json_parse",
            ):
                continue
            assert kind == 4
            fallbacks.append(
                dict(
                    section=number,
                    offset=off,
                    old=old_source.all_symbols[sym]["name"],
                    target="JS_FrameJSONReviverCodeUnits",
                )
            )
            struct.pack_into("<I", old_source.data, at + 4, target)
    assert len(fallbacks) == 1, fallbacks
    output.write_bytes(old_source.finish())
    merge.append(
        output,
        unit_output,
        "JS_FrameJSONReviverCodeUnits",
        "source-codeunits-isolated",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONReviverSource",
        baseline_sections=(),
    )
    (_frame_generated_file(build, "quickjs-json-source-codeunits-isolation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                fallbacks=fallbacks,
                private_header_sha256=sha_text(
                    (
                        _frame_generated_file(build, "quickjs-json-source-codeunits-private.h")
                    ).read_text(encoding="utf-8")
                ),
                backend_sha256=sha_text(
                    (
                        _frame_generated_file(build, "quickjs-json-source-codeunits-backend.h")
                    ).read_text(encoding="utf-8")
                ),
                policy="Two independent TUs. ASCII compiler payload unchanged except one fallback relocation; Unicode appended before the one owned native/unwind carrier. Shared control only; no early code or extra RW storage.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    merge.append(
        output,
        slot_output,
        "JS_FrameJSONToJSONProperty",
        "tojson-slot",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        writable_metadata_inputs=() if msvc else (".qjssrm",),
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONReviverSource",
        baseline_sections=(),
    )
    if slice_output is not None:
        merge.append(
            output,
            slice_output,
            "JS_FrameStringSliceSimple",
            "slice-simple",
            keep_all=True,
            code_input=".qjssrc$C",
            code_output=".qjssrc$C",
            pdata_output=".pdata$zzzzzznullfast",
            metadata_inputs=(".voltbl",),
            base_owner="JS_FrameJSONReviverSource",
            baseline_sections=(),
        )
    merge.append(
        output,
        release_output,
        "JS_FrameBigIntRelease",
        "bigint-release",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        writable_metadata_inputs=() if msvc else (".qjssrm",),
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONReviverSource",
        baseline_sections=(),
    )
    if msvc:
        write_output = module("ms_owned_callback", "prepared-callback.py").compile_msvc_write(
            source, build
        )
        merge.append(
            output,
            write_output,
            "JS_FrameCallbackWriteScopeRun",
            "ms-owned-callback",
            keep_all=True,
            code_input=".qjssrc$C",
            code_output=".qjssrc$C",
            pdata_output=".pdata$zzzzzznullfast",
            metadata_inputs=(".voltbl",),
            base_owner="JS_FrameJSONReviverSource",
            baseline_sections=(),
        )
    if msvc:
        json_write = compile_writable(source, build, None, None, None, msvc=True)
        merge.append(
            output,
            json_write,
            "JS_FrameJSONWriteCallbackStringify",
            "ms-json-owned",
            keep_all=True,
            code_input=".qjssrc$C",
            code_output=".qjssrc$C",
            pdata_output=".pdata$zzzzzznullfast",
            metadata_inputs=(".voltbl",),
            base_owner="JS_FrameJSONReviverSource",
            baseline_sections=(),
        )
    merge.append(
        output,
        pop_output,
        "JS_FrameDenseArrayPop",
        "dense-array-pop",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        allocated_metadata_inputs=() if msvc else (".qjssrc$Z",),
        writable_metadata_inputs=() if msvc else (".qjssrm",),
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONReviverSource",
        baseline_sections=(),
    )
    order = None
    section_outputs = None
    if msvc:
        obj = C.Coff(output.read_bytes())
        header = next(
            s["section"] for s in obj.all_symbols.values() if s["name"] == "frame_source_ms_header"
        )
        footer = next(
            s["section"] for s in obj.all_symbols.values() if s["name"] == "frame_source_ms_footer"
        )
        numbers = []
        native = []
        for n, r in enumerate(obj.section_records, 1):
            name = merge.section_name(obj, n)
            if not r["size"]:
                continue
            if name == ".qjssrc$C":
                numbers.append(n)
            elif name == ".pdata$zzzzzznullfast":
                native.append(n)
            elif n not in (header, footer) and name == ".voltbl":
                numbers.append(n)
        # Stable old group first, new code/helpers, then header/native/footer.
        order = [*numbers, header, *native, footer]
        section_outputs = {header: ".qjs$zzzzzzzzzzrvV", footer: ".qjs$zzzzzzzzzzrvV"}
    merge.append(
        owner,
        output,
        "JS_FrameJSONReviverSource",
        "json-source-record",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjs$zzzzzzzzzzrvV" if msvc else ".qjssrc$C",
        pdata_output=".qjs$zzzzzzzzzzrvV" if msvc else ".qjssrf$C",
        writable_metadata_inputs=() if msvc else (".qjssrm",),
        allocated_metadata_inputs=(".qjs$zzzzzzzzzzzzsrcu0", ".qjs$zzzzzzzzzzzzsrcu2")
        if msvc
        else (".qjssrf$0", ".qjssrf$Z", ".qjssrc$Z"),
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner="JS_FrameJSONReviverValue",
        baseline_sections=(),
        section_order=order,
        section_outputs=section_outputs,
    )
    if msvc:
        write_routes = []
        for old, target in (
            ("JS_LegacyJSONStringify", "JS_FrameJSONWriteCallbackStringify"),
            ("qjs_frame_core_js_json_stringify", "JS_FrameJSONWriteNativeStringify"),
        ):
            obj = C.Coff(owner.read_bytes())
            index = obj.external(target)
            count = 0
            for number, rec in enumerate(obj.section_records, 1):
                if merge.section_name(obj, number) != ".qjs$zzjsonB":
                    continue
                for i in range(rec["count"]):
                    at = rec["reloc"] + i * 10
                    off, sym, kind = struct.unpack_from("<IIH", obj.data, at)
                    if obj.all_symbols[sym]["name"] != old:
                        continue
                    assert kind == 4
                    count += 1
                    struct.pack_into("<I", obj.data, at + 4, index)
                    write_routes.append(dict(section=number, offset=off, old=old, target=target))
            assert count == 1, (old, count)
            owner.write_bytes(obj.finish())
        proof = json.loads((_frame_generated_file(build, "quickjs-json-write.json")).read_text())
        proof.update(
            status="passed",
            routes=write_routes,
            policy="Two typed retained native/public fallback operands. Complete new C and unwind contributions appended inside the existing source carrier before its directory, using the established owned-formal selector. No new PE group; no new reviver traversal.",
        )
        (_frame_generated_file(build, "quickjs-json-write.json")).write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
    boundary = json.loads(Path(str(owner) + ".json-source-record-merge.json").read_text())[
        "old_sections"
    ]
    c = C.Coff(owner.read_bytes())
    idx = c.external("JS_FrameJSONReviverSource")
    routes = []
    for number, rec in enumerate(c.section_records, 1):
        if msvc and number > boundary:
            continue
        if merge.section_name(c, number) != (".qjs$zzzzzzzzzzrvV" if msvc else ".qjsjcrv$C"):
            continue
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", c.data, at)
            if c.all_symbols[sym]["name"] not in ("js_json_parse", "qjs_frame_core_js_json_parse"):
                continue
            assert kind == 4
            routes.append(
                dict(
                    object=owner.name,
                    section=number,
                    offset=off,
                    old=c.all_symbols[sym]["name"],
                    target="JS_FrameJSONReviverSource",
                )
            )
            struct.pack_into("<I", c.data, at + 4, idx)
    assert len(routes) == 1, routes
    owner.write_bytes(c.finish())
    os.utime(owner, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (_frame_generated_file(build, "quickjs-json-source-record.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                routes=routes,
                toolchain="msvc" if msvc else "mingw",
                private_header_sha256=sha_text(
                    (_frame_generated_file(build, "quickjs-json-source-private.h")).read_text(
                        encoding="utf-8"
                    )
                ),
                backend_sha256=sha_text(
                    (_frame_generated_file(build, "quickjs-json-source-backend.h")).read_text(
                        encoding="utf-8"
                    )
                ),
                policy="Exactly one typed inherited value-worker fallback route. Source worker fallback targets core and is not retargeted. Full new compiler contributions/unwind retained.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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


def adapt_tojson_slot(source, object_path):
    """One typed/decoded CALL operand only; preserve original JSON traversal."""
    import importlib.util, json, struct, subprocess
    from pathlib import Path

    here = Path(__file__).resolve().parent
    sp = importlib.util.spec_from_file_location(
        "slot_route_coff", _frame_tool_path("object-adapter")
    )
    C = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(C)
    raw = object_path.read_bytes()
    c = C.Coff(raw)
    fn = c.symbols["js_json_check"]
    callee = c.symbols["JS_GetPropertyInternal"]
    rec = c.section_records[fn["section"] - 1]
    start = fn["value"]
    end = min(
        [
            s["value"]
            for s in c.all_symbols.values()
            if s["type"] & 32 and s["section"] == fn["section"] and s["value"] > start
        ]
        + [rec["size"]]
    )
    target = c.external("JS_FrameJSONToJSONProperty")
    routes = []
    for i in range(rec["count"]):
        at = rec["reloc"] + 10 * i
        off, sym, kind = struct.unpack_from("<IIH", c.data, at)
        if start <= off < end and c.all_symbols[sym]["name"] == "JS_GetPropertyInternal":
            assert kind == 4 and c.data[rec["raw"] + off - 1] == 0xE8
            struct.pack_into("<I", c.data, at + 4, target)
            routes.append(
                dict(section=fn["section"], offset=off, kind="typed-rel32", original_symbol=sym)
            )
    if not routes:
        assert fn["section"] == callee["section"]
        dump = find_objdump(object_path.parent)
        listing = subprocess.check_output(
            [str(dump), "-d", "-w", "-Mintel", "--disassemble=js_json_check", str(object_path)],
            text=True,
        )
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not m:
                continue
            address = int(m[1], 16)
            code = bytes.fromhex(m[2])
            if not (start <= address < end and len(code) == 5 and code[0] == 0xE8):
                continue
            if address + 5 + struct.unpack_from("<i", code, 1)[0] != callee["value"]:
                continue
            assert bytes(c.data[rec["raw"] + address : rec["raw"] + address + 5]) == code
            off = address + 1
            c.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
            c.extra_relocations.setdefault(fn["section"], []).append(
                struct.pack("<IIH", off, target, 4)
            )
            routes.append(
                dict(
                    section=fn["section"],
                    offset=off,
                    kind="decoded-rel32",
                    original_bytes=code[1:].hex(),
                )
            )
    assert len(routes) == 1, routes
    result = c.finish()
    backup = object_path.with_name(object_path.name + ".before-tojson-slot")
    assert not backup.exists()
    backup.write_bytes(raw)
    object_path.write_bytes(result)
    object_path.with_name(object_path.name + ".tojson-slot.json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                caller="js_json_check",
                target="JS_FrameJSONToJSONProperty",
                policy="Exactly one GetPropertyInternal CALL inside original js_json_check. No function body/traversal/argument setup/call ABI changes; GNU decoded rel32 gets one typed relocation.",
            ),
            indent=2,
        )
        + "\n"
    )


def compile_tojson_slot(source, build, *, msvc=False):
    import importlib.util, json, os, struct
    from pathlib import Path
    from types import SimpleNamespace

    here = Path(__file__).resolve().parent

    def module(n, file):
        sp = importlib.util.spec_from_file_location(n, _frame_tool_path(file))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("slot_private_coff", "object-adapter.py")
    M = module("slot_compiler", "atod.py")
    core = C.Coff((_frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")).read_bytes())
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, core, TOJSON_SLOT_BACKEND)
    assert (
        exports == ["JS_GetPropertyInternal"]
        and core.symbols["qjs_frame_core_JS_GetPropertyInternal"]["section"] > 0
    )
    prefix = "".join("#define " + n + " slot_json_" + n + "\n" for n in copies)
    (_frame_generated_file(build, "quickjs-json-tojson-slot-private.h")).write_text(
        prefix + header, encoding="utf-8"
    )
    if msvc:
        register = _frame_generated_file(build, "quickjs-interpreter-register.obj")
        stamp = register.stat()
        raw = register.read_bytes()
        rc = C.Coff(raw)
        sym = next(s for s in rc.all_symbols.values() if s["name"] == "JS_FrameCallbackControl")
        sn = sym["section"]
        rec = rc.section_records[sn - 1]
        before = raw[rec["raw"] : rec["raw"] + rec["size"]]
        aligned = (len(before) + 7) & ~7
        payload = before + bytes(aligned - len(before) + 112)
        assert rec["flags"] & 0xE0000000 == 0xC0000000 and not rec["count"]
        names = [
            ("JS_FrameJSONToJSONShape", aligned),
            ("JS_FrameJSONToJSONSlot", aligned + 8),
            ("JS_FrameJSONToJSONSlotControl", aligned + 12),
            ("JS_FrameStringSliceSimpleControl", aligned + 13),
            ("JS_FrameBigIntReleaseControl", aligned + 14),
            ("JS_FrameCallbackWriteControl", aligned + 15),
            ("JS_FrameDenseArrayPopControl", aligned + 16),
            ("JS_FrameDensePopLeafControl", aligned + 17),
            ("JS_FrameStringProtoControl", aligned + 18),
            ("JS_FrameObjectProtoControl", aligned + 19),
            ("JS_FrameStringProtoHits", aligned + 20),
            ("JS_FrameDensePopLeafHits", aligned + 24),
            ("JS_FrameObjectProtoHintControl", aligned + 32),
            ("JS_FrameObjectProtoHints", aligned + 36),
            ("JS_FrameObjectProtoHintHits", aligned + 104),
        ]
        for name, offset in names:
            at = len(rc.strings)
            rc.strings += name.encode() + b"\0"
            alias = bytearray(rc.stride)
            struct.pack_into("<III", alias, 0, 0, at, offset)
            struct.pack_into("<h", alias, 12, sn)
            alias[rc.class_offset] = 2
            rc.aliases.append(alias)
        for index, s in rc.all_symbols.items():
            at = rc.table + index * rc.stride
            if (
                s["section"] == sn
                and s["storage"] == 3
                and s["type"] == 0
                and raw[at + rc.class_offset + 1]
            ):
                struct.pack_into("<I", rc.data, at + rc.stride, len(payload))
        result = bytearray(rc.finish())
        old_end = rc.string_offset + struct.unpack_from("<I", raw, rc.string_offset)[0]
        tail_shift = len(result) - len(raw)
        pa = rc.table
        for rr in rc.section_records:
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
        struct.pack_into("<I", result, rc.table_offset, rc.table + len(payload))
        struct.pack_into("<II", result, rec["pos"] + 16, len(payload), pa)
        alignment = max(4, (rec["flags"] >> 20) & 15)
        struct.pack_into(
            "<I", result, rec["pos"] + 36, (rec["flags"] & ~0x00F00000) | (alignment << 20)
        )
        after = C.Coff(result)
        assert all(after.all_symbols[i] == s for i, s in rc.all_symbols.items())
        for i, (x, y) in enumerate(zip(rc.sections, after.sections), 1):
            if i != sn:
                assert x == y
        assert result[pa : pa + len(before)] == before
        backup = register.with_name(register.name + ".before-tojson-slot-control")
        assert not backup.exists()
        backup.write_bytes(raw)
        register.write_bytes(result)
        os.utime(register, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        register.with_name(register.name + ".tojson-slot-control.json").write_text(
            json.dumps(
                dict(
                    status="passed",
                    before_sha256=hashlib.sha256(raw).hexdigest(),
                    after_sha256=hashlib.sha256(result).hexdigest(),
                    old_size=len(before),
                    new_size=len(payload),
                    symbols=names,
                    appended_metadata_bytes=len(payload) - aligned,
                    policy="Natural 8-byte alignment; explicit scalar controls and aligned leaf diagnostic counter, sizes/alias offsets above; no extra TLS/RW section or changed inherited prefix.",
                ),
                indent=2,
            )
            + "\n"
        )

    class SlotCoff(C.Coff):
        def finish(self):
            for index, s in self.all_symbols.items():
                n = s["name"]
                if (
                    not msvc
                    and s["section"] > 0
                    and n
                    in (
                        "JS_FrameJSONToJSONShape",
                        "JS_FrameJSONToJSONSlot",
                        "JS_FrameJSONToJSONSlotControl",
                    )
                ):
                    self.data[self.table + index * self.stride + self.class_offset] = 2
                atomics = {
                    s["name"]
                    for s in self.all_symbols.values()
                    if s["section"] > 0
                    and s["storage"] == 2
                    and s["type"] & 32
                    and s["name"]
                    not in (
                        "JS_FrameJSONToJSONPropertySlow",
                        "JS_FrameJSONToJSONSlotState",
                        "JS_FrameJSONSlotDuplicate",
                    )
                }
                if n in atomics:
                    name = "slot_json_" + n
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                if (
                    s["storage"] == 2
                    and s["section"] > 0
                    and n.startswith(("??_C@", "__xmm@", "__real@"))
                ):
                    name = "qjs_slot_const_" + hashlib.sha256(n.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for rec in self.section_records:
                n = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode()
                if n.startswith("/"):
                    at = int(n[1:])
                    n = self.strings[at : self.strings.index(0, at)].decode()
                if n == ".qjssrc$C" or (msvc and n.startswith(".pdata")):
                    flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                    struct.pack_into("<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040)
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=SlotCoff)
    argv = M.win_argv
    M.win_argv = lambda cmd: [a for a in argv(cmd) if not a.startswith("-g")] + (
        [] if msvc else ["-g0"]
    )
    output = _frame_generated_file(build, "quickjs-interpreter-json-tojson-slot.obj")

    def generate(source, path):
        path.write_text(
            '#include "quickjs-json-tojson-slot-private.h"\n' + TOJSON_SLOT_BACKEND,
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-json-tojson-slot.c",
        late_name=".qjssrc$C",
    )
    if msvc:
        import subprocess

        asm = _frame_generated_file(build, "quickjs-interpreter-json-slot-atomic.asm")
        ao = _frame_generated_file(build, "quickjs-interpreter-json-slot-atomic.obj")
        functions = {
            "JS_FrameJSONSlotLoad64": ["mov rax, QWORD PTR [rcx]", "ret"],
            "JS_FrameJSONSlotLoad32": ["mov eax, DWORD PTR [rcx]", "ret"],
            "JS_FrameJSONSlotStore64": ["mov QWORD PTR [rcx], rdx", "ret"],
            "JS_FrameJSONSlotStore32": ["mov DWORD PTR [rcx], edx", "ret"],
        }
        lines = ["OPTION CASEMAP:NONE", "OPTION DOTNAME", ".qjssrc$C SEGMENT ALIGN(16) 'CODE'"]
        for name, instructions in functions.items():
            lines += [
                "PUBLIC " + name,
                name + " PROC FRAME",
                ".endprolog",
                *instructions,
                name + " ENDP",
            ]
        lines += [".qjssrc$C ENDS", "END"]
        asm.write_text("\n".join(lines) + "\n", encoding="ascii")
        compiler = Path(
            M.win_argv(
                json.loads((output.with_suffix(".compile.json")).read_text())["original_command"][
                    "command"
                ]
            )[0]
        ).with_name("ml64.exe")
        command = [str(compiler), "/nologo", "/c", "/Fo" + str(ao), str(asm)]
        result = subprocess.run(command, capture_output=True)
        asm.with_suffix(".log").write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0
        ac = C.Coff(ao.read_bytes())
        for number, rec in enumerate(ac.section_records, 1):
            name = ac.sections[number - 1]["name"]
            if name.startswith("/"):
                at = int(name[1:])
                name = ac.strings[at : ac.strings.index(0, at)].decode()
            renamed = (
                ".pdata$zzzzzznullfast"
                if name.startswith(".pdata")
                else ".qjssrc$C"
                if name.startswith(".xdata")
                else None
            )
            if renamed:
                at = len(ac.strings)
                ac.strings += renamed.encode() + b"\0"
                ac.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
                for index, sym in ac.all_symbols.items():
                    if (
                        sym["section"] == number
                        and sym["storage"] == 3
                        and sym["type"] == 0
                        and sym["name"] == name
                    ):
                        struct.pack_into("<II", ac.data, ac.table + index * ac.stride, 0, at)
            if name.startswith((".pdata", ".xdata")) or name == ".qjssrc$C":
                struct.pack_into(
                    "<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040
                )
        ao.write_bytes(ac.finish())
        merge = module("slot_atomic_merge", "extension-merge.py")
        merge.append(
            output,
            ao,
            "JS_FrameJSONSlotLoad64",
            "slot-atomic",
            keep_all=True,
            code_input=".qjssrc$C",
            code_output=".qjssrc$C",
            pdata_output=".pdata$zzzzzznullfast",
            base_owner="JS_FrameJSONToJSONPropertySlow",
            baseline_sections=(),
        )
        asm.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    status="passed",
                    command=command,
                    source_sha256=hashlib.sha256(asm.read_bytes()).hexdigest(),
                    object_sha256=hashlib.sha256(ao.read_bytes()).hexdigest(),
                    contract="Windows x64 naturally aligned scalar MOV loads/stores; volatile registers only; existing locked byte CAS initializes control; coherent cache pair not required. Exact native leaf unwind retained.",
                ),
                indent=2,
            )
            + "\n"
        )
    import subprocess

    probe = _frame_generated_file(build, "quickjs-json-tojson-slot-layout.c")
    pe = probe.with_suffix(".exe")
    probe.write_text(
        r"""#include "quickjs-json-tojson-slot-private.h"
#include <stdio.h>
#if QJS_ABI_HAS_PREFIX_RC
#define FRAME_SHAPE_PROPERTIES offsetof(JSShape,hash_table)
#else
#define FRAME_SHAPE_PROPERTIES offsetof(JSShape,prop)
#endif
int main(void) {
    JSObject object={0}; JSShapeProperty property={0}; unsigned char *p=(unsigned char *)&object;
    unsigned ex=0,mask=0; object.is_exotic=1;
    for(unsigned i=0;i<sizeof(object);i++) if(p[i]) {ex=i;mask=p[i];break;}
    property.flags=JS_PROP_TMASK; uint32_t type=0; memcpy(&type,&property,4);
    printf("SLOT_LAYOUT %zu %zu %zu %zu %zu %zu %u %u %zu %zu %zu %zu %zu %zu %u %d %u %u\n",
        sizeof(JSValue),offsetof(JSValue,tag),offsetof(JSObject,class_id),offsetof(JSObject,shape),
        offsetof(JSObject,prop),sizeof(JSProperty),ex,mask,offsetof(JSShape,is_hashed),offsetof(JSShape,prop_count),
        offsetof(JSShape,prop_hash_mask),FRAME_SHAPE_PROPERTIES,sizeof(JSShapeProperty),offsetof(JSShapeProperty,atom),
        type,JS_TAG_OBJECT,JS_ATOM_toJSON,JS_CLASS_OBJECT);
    return 0;
}
""",
        encoding="utf-8",
    )
    compiler_args = json.loads(output.with_suffix(".compile.json").read_text())["compiler_command"]
    compiler = Path(compiler_args[0])
    defines = [a for a in compiler_args[1:] if a.startswith(("-D", "/D"))]
    crt_flag = _probe_crt_flag(compiler_args)
    command = (
        [
            str(compiler),
            "/nologo",
            "/O2",
            crt_flag,
            "/std:c11",
            "/experimental:c11atomics",
            "/I" + str(build),
            "/I" + str(source),
            "/I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "/Fe:" + str(pe),
            "/Fo:" + str(probe.with_suffix(".obj")),
        ]
        if msvc
        else [
            str(compiler),
            "-O2",
            "-g0",
            "-I" + str(build),
            "-I" + str(source),
            "-I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "-o",
            str(pe),
        ]
    )
    result = subprocess.run(command, capture_output=True)
    probe.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0
    result = subprocess.run([str(pe)], capture_output=True)
    assert result.returncode == 0
    match = re.search(rb"SLOT_LAYOUT ([0-9 -]+)", result.stdout)
    assert match, result.stdout
    layout = list(map(int, match[1].split()))
    assert len(layout) == 18
    (
        size,
        tag,
        cls,
        shape,
        prop,
        psize,
        ex,
        exmask,
        hashed,
        count,
        hmask,
        table,
        spsize,
        atom,
        type_mask,
        objtag,
        tojson,
        object_class,
    ) = layout
    assert size == psize == 16 and spsize == 8 and atom == 4 and objtag == -1 and type_mask > 0
    properties = (
        [f"lea r10, [r10+{table}]"]
        if load_layout(source)["reference_count_model"] == "inline-header"
        else [f"mov r11d, DWORD PTR [r10+{hmask}]", f"lea r10, [r10+r11*4+{table + 4}]"]
    )
    # All failures preserve the original Win64 six-argument incoming state.
    # Own normal data reads ignore receiver/throw_ref_error in the original Get.
    ins = [
        "movzx eax, BYTE PTR [rip+JS_FrameJSONToJSONSlotControl]",
        "cmp eax, 1",
        "jne slot_property_slow",
        f"cmp r9d, {tojson}",
        "jne slot_property_slow",
        f"cmp QWORD PTR [r8+{tag}], {objtag}",
        "jne slot_property_slow",
        "mov r11, QWORD PTR [r8]",
        f"cmp WORD PTR [r11+{cls}], {object_class}",
        "jne slot_property_slow",
        f"test BYTE PTR [r11+{ex}], {exmask}",
        "jnz slot_property_slow",
        f"mov r10, QWORD PTR [r11+{shape}]",
        f"cmp BYTE PTR [r10+{hashed}], 0",
        "je slot_property_slow",
        "cmp r10, QWORD PTR [rip+JS_FrameJSONToJSONShape]",
        "jne slot_property_slow",
        "mov eax, DWORD PTR [rip+JS_FrameJSONToJSONSlot]",
        f"cmp eax, DWORD PTR [r10+{count}]",
        "jae slot_property_slow",
        *properties,
        "lea r10, [r10+rax*8]",
        f"test DWORD PTR [r10], {type_mask}",
        "jnz slot_property_slow",
        f"cmp DWORD PTR [r10+{atom}], {tojson}",
        "jne slot_property_slow",
        "mov r11, QWORD PTR [r8]",
        f"mov r11, QWORD PTR [r11+{prop}]",
        "shl rax, 4",
        "lea rdx, [r11+rax]",
        "jmp JS_FrameJSONSlotDuplicate",
        "slot_property_slow:",
        "jmp JS_FrameJSONToJSONPropertySlow",
    ]
    root = "JS_FrameJSONToJSONProperty"
    ao = _frame_generated_file(build, "quickjs-interpreter-json-slot-entry.obj")
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-json-slot-entry.asm"
        if msvc
        else "quickjs-interpreter-json-slot-entry.S",
    )
    if msvc:
        externs = [
            "JS_FrameJSONToJSONSlotControl:BYTE",
            "JS_FrameJSONToJSONShape:QWORD",
            "JS_FrameJSONToJSONSlot:DWORD",
            "JS_FrameJSONSlotDuplicate:PROC",
            "JS_FrameJSONToJSONPropertySlow:PROC",
        ]
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n for n in externs],
            ".qjssrc$C SEGMENT ALIGN(16) 'CODE'",
            "PUBLIC " + root,
            root + " PROC FRAME",
            ".endprolog",
            *[s.replace("rip+", "") for s in ins],
            root + " ENDP",
            ".qjssrc$C ENDS",
            "END",
        ]
        assembler = compiler.with_name("ml64.exe")
        command = [str(assembler), "/nologo", "/c", "/Fo" + str(ao), str(asm)]
    else:
        lines = [
            ".intel_syntax noprefix",
            '.section .qjssrc$C,"xr"',
            ".p2align 4",
            ".globl " + root,
            ".def " + root + "; .scl 2; .type 32; .endef",
            ".seh_proc " + root,
            root + ":",
            ".seh_endprologue",
            *ins,
            ".seh_endproc",
        ]
        command = [str(compiler), "-c", str(asm), "-o", str(ao)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    result = subprocess.run(command, capture_output=True)
    asm.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    ac = C.Coff(ao.read_bytes())
    for number, rec in enumerate(ac.section_records, 1):
        name = ac.sections[number - 1]["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = ac.strings[at : ac.strings.index(0, at)].decode()
        renamed = (
            ".pdata$zzzzzznullfast"
            if name.startswith(".pdata")
            else ".qjssrc$C"
            if name.startswith(".xdata")
            else None
        )
        if renamed:
            at = len(ac.strings)
            ac.strings += renamed.encode() + b"\0"
            ac.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            for index, sym in ac.all_symbols.items():
                if (
                    sym["section"] == number
                    and sym["storage"] == 3
                    and sym["type"] == 0
                    and sym["name"] == name
                ):
                    struct.pack_into("<II", ac.data, ac.table + index * ac.stride, 0, at)
        if name.startswith((".pdata", ".xdata")) or name == ".qjssrc$C":
            struct.pack_into("<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    ao.write_bytes(ac.finish())
    merge = module("slot_entry_merge", "extension-merge.py")
    merge.append(
        output,
        ao,
        root,
        "slot-entry",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameJSONToJSONPropertySlow",
        baseline_sections=(),
    )
    asm.with_suffix(".json").write_text(
        json.dumps(
            dict(
                status="passed",
                layout=layout,
                layout_probe_source_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                layout_probe_image_sha256=hashlib.sha256(pe.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(asm.read_bytes()).hexdigest(),
                object_sha256=hashlib.sha256(ao.read_bytes()).hexdigest(),
                policy="Actual types; Win64 leaf selector preserves all incoming state on failure, validates live atom/type/bounds, reloads current value, tailcalls C js_dup; no stack, allocator layout or reference-count rewrite.",
            ),
            indent=2,
        )
        + "\n"
    )
    (_frame_generated_file(build, "quickjs-json-tojson-slot-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                exports=exports,
                copied_helpers=copies,
                source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                private_sha256=hashlib.sha256((prefix + header).encode()).hexdigest(),
                policy="No traversal/call changes. Hashed ordinary own-data only, each hit validates live bounds/atom/type and rereads value. Two relaxed atomic cache fields need no coherent pair because every candidate slot is validated. No stored value/shape reference or pointer dereference.",
            ),
            indent=2,
        )
        + "\n"
    )
    return output


SLICE_SIMPLE_BACKEND = r"""
/* MSVC generic C ABI is retained, including the existing C stack frame and
   padded argv. The primitive-string reference is owned across allocation.
   No string allocation, copy/share threshold, or GC traversal is rewritten. */
#define SLICE_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
extern unsigned char JS_FrameStringSliceSimpleControl;
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);
SLICE_CODE static unsigned char slice_simple_initialize(void)
{
    unsigned char expected=0;
    unsigned char value=getenv("QJS_DISABLE_STRING_SLICE_SIMPLE")?2:1;
    if(!JS_FrameJSONCAS8(&JS_FrameStringSliceSimpleControl,&expected,value))return expected;
    return value;
}
/* Readonly qualification access; no hot counters or retained JS values. */
SLICE_CODE unsigned JS_FrameStringSliceSimpleState(void)
{
    return JS_FrameJSONLoad8(&JS_FrameStringSliceSimpleControl);
}
SLICE_CODE JSValue JS_FrameStringSliceSimple(JSContext *ctx,JSValueConst this_val,
    int argc,JSValueConst *argv)
{
    JSString *p;JSValue str,ret;int start,end,len;unsigned char control;
    if(argc<1||JS_VALUE_GET_TAG(this_val)!=JS_TAG_STRING||
       JS_VALUE_GET_TAG(argv[0])!=JS_TAG_INT||
       (!JS_IsUndefined(argv[1])&&JS_VALUE_GET_TAG(argv[1])!=JS_TAG_INT))
        goto original;
    control=JS_FrameJSONLoad8(&JS_FrameStringSliceSimpleControl);
    if((control?control:slice_simple_initialize())!=1)goto original;
    str=js_dup(this_val);p=JS_VALUE_GET_STRING(str);len=p->len;
    start=JS_VALUE_GET_INT(argv[0]);
    if(start<0){start+=len;if(start<0)start=0;}else if(start>len)start=len;
    end=len;
    if(!JS_IsUndefined(argv[1])){
        end=JS_VALUE_GET_INT(argv[1]);
        if(end<0){end+=len;if(end<0)end=0;}else if(end>len)end=len;
    }
    ret=js_sub_string(ctx,p,start,end<start?start:end);
    JS_FreeValue(ctx,str);
    return ret;
original:
    return js_string_slice(ctx,this_val,argc,argv);
}
"""


def adapt_slice_simple(source, object_path):
    """MSVC only: one typed builtin-table pointer, with unchanged core RX."""
    import importlib.util, json, struct
    from pathlib import Path

    here = Path(__file__).resolve().parent
    build = next(p for p in object_path.parents if (p / "compile_commands.json").is_file())
    command = next(
        x["command"]
        for x in json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
        if Path(x["file"]).name == "quickjs-interpreter.c"
    )
    adapt_dense_array_pop(source, object_path)
    if "/nologo" not in command.lower():
        return
    sp = importlib.util.spec_from_file_location(
        "slice_route_coff", _frame_tool_path("object-adapter")
    )
    C = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(C)
    raw = object_path.read_bytes()
    c = C.Coff(raw)
    before = C.Coff(raw)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, c, SLICE_SIMPLE_BACKEND)
    names = {s["name"] for s in c.all_symbols.values()}
    added = []
    for name in exports:
        if "qjs_frame_core_" + name not in names:
            c.expose(name)
            added.append(name)
    fn = c.symbols["js_string_slice"]
    target = c.external("JS_FrameStringSliceSimple")
    routes = []
    for si, rec in enumerate(c.section_records, 1):
        if rec["flags"] & 0x20000000 or not c.sections[si - 1]["name"].startswith(".rdata"):
            continue
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", c.data, at)
            s = c.all_symbols[sym]
            if kind != 1 or s["section"] != fn["section"]:
                continue
            addend = struct.unpack_from("<Q", c.data, rec["raw"] + off)[0]
            if addend + s["value"] != fn["value"]:
                continue
            struct.pack_into("<Q", c.data, rec["raw"] + off, 0)
            struct.pack_into("<I", c.data, at + 4, target)
            routes.append(
                dict(
                    section=si,
                    offset=off,
                    kind=1,
                    original_symbol=sym,
                    original_addend=addend,
                    target="JS_FrameStringSliceSimple",
                )
            )
    assert len(routes) == 1, routes
    result = bytearray(c.finish())
    old_end = before.string_offset + struct.unpack_from("<I", raw, before.string_offset)[0]
    for rec in before.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            v = struct.unpack_from("<I", raw, at)[0]
            if v and v >= old_end:
                struct.pack_into("<I", result, at, v + len(result) - len(raw))
    check = C.Coff(result)
    for si, (a, b) in enumerate(zip(before.section_records, check.section_records), 1):
        old = raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])
        new = bytearray(result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"]))
        rr = bytearray(result[b["reloc"] : b["reloc"] + b["count"] * 10])
        pr = raw[a["reloc"] : a["reloc"] + a["count"] * 10]
        for route in routes:
            if route["section"] != si:
                continue
            off = route["offset"]
            new[off : off + 8] = old[off : off + 8]
            hits = [i for i in range(a["count"]) if struct.unpack_from("<I", pr, 10 * i)[0] == off]
            assert len(hits) == 1
            at = 10 * hits[0] + 4
            rr[at : at + 4] = pr[at : at + 4]
        assert new == old and rr == pr, ("Unexpected slice adapter change", si)
    backup = object_path.with_name(object_path.name + ".before-slice-simple")
    assert not backup.exists()
    backup.write_bytes(raw)
    object_path.write_bytes(result)
    object_path.with_name(object_path.name + ".slice-simple.json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                exports=exports,
                added_exports=added,
                copied_helpers=copies,
                policy="Exactly one typed ADDR64 String.prototype.slice builtin pointer. Original mapped payload/relocations retained except this operand; no C ABI, core code, dispatch or threshold changes.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def compile_slice_simple(source, build):
    import importlib.util, json, struct
    from pathlib import Path
    from types import SimpleNamespace

    here = Path(__file__).resolve().parent

    def module(n, file):
        sp = importlib.util.spec_from_file_location(n, _frame_tool_path(file))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("slice_compile_coff", "object-adapter.py")
    M = module("slice_compiler", "atod.py")
    core = C.Coff((_frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")).read_bytes())
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, core, SLICE_SIMPLE_BACKEND)
    assert all("qjs_frame_core_" + name in core.symbols for name in exports), exports
    prefix = "".join("#define " + name + " slice_simple_" + name + "\n" for name in copies)
    private = _frame_generated_file(build, "quickjs-string-slice-simple-private.h")
    private.write_text(prefix + header, encoding="utf-8")

    class SliceCoff(C.Coff):
        def finish(self):
            for index, s in self.all_symbols.items():
                n = s["name"]
                if (
                    s["section"] > 0
                    and s["storage"] == 2
                    and (
                        (
                            s["type"] & 32
                            and n
                            not in ("JS_FrameStringSliceSimple", "JS_FrameStringSliceSimpleState")
                        )
                        or n.startswith(("??_C@", "__xmm@", "__real@"))
                    )
                ):
                    name = "slice_simple_emitted_" + hashlib.sha256(n.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for rec in self.section_records:
                n = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode()
                if n.startswith("/"):
                    at = int(n[1:])
                    n = self.strings[at : self.strings.index(0, at)].decode()
                if n == ".qjssrc$C" or n.startswith(".pdata"):
                    flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                    struct.pack_into("<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040)
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=SliceCoff)
    output = _frame_generated_file(build, "quickjs-interpreter-string-slice-simple.obj")

    def generate(source, path):
        path.write_text(
            '#include "quickjs-string-slice-simple-private.h"\n' + SLICE_SIMPLE_BACKEND,
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-string-slice-simple.c",
        late_name=".qjssrc$C",
    )
    (_frame_generated_file(build, "quickjs-string-slice-simple-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                exports=exports,
                copied_helpers=copies,
                source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                private_sha256=hashlib.sha256((prefix + header).encode()).hexdigest(),
                policy="MSVC C ABI, primitive flat-tag string and int32 parameters only; owned reference across original js_sub_string/JS_FreeValue, original clamp equivalence, no allocator or copy/share threshold rewrite. Unsupported/disabled inputs call original js_string_slice.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def direct_quote_private(source, header, *, msvc=False, reference_count_model=None):
    """Append string quotes to the live buffer; keep callback traversal owned."""
    import importlib.util

    sp = importlib.util.spec_from_file_location(
        "direct_quote_extract", _frame_tool_path("object-adapter")
    )
    C = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(C)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    selected = _frame_source_text(source, "quickjs-interpreter-json.h")
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
    if not msvc:
        # These two current-source helpers were absent from GNU's old callback
        # closure. Own their exact bodies inside this new late TU; no new core
        # exports or formerly unreferenced early COMDAT retention.
        text = funcs["string_buffer_widen"] + "\n" + funcs["string_buffer_write16"] + "\n" + text
        names += ("string_buffer_widen", "string_buffer_write16")
        from native_abi import current_or_load as load_layout

        if (
            reference_count_model
            if reference_count_model is not None
            else load_layout(source)["reference_count_model"]
        ) == "inline-header":
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
    prelude = """#include <emmintrin.h>
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


def _dense_pop_copied_helpers(source):
    # 0.15.1 uses the source-derived shape->prop compatibility inline; the
    # prefix-allocator core supplies the original get_shape_prop body instead.
    return (
        {"get_shape_prop", "js_int32"}
        if load_layout(source)["reference_count_model"] == "allocator-prefix"
        else {"js_int32"}
    )


def adapt_dense_array_pop(source, object_path):
    """One typed, signature-checked builtin descriptor; no core RX mutation."""
    import importlib.util, json, struct
    from pathlib import Path

    sp = importlib.util.spec_from_file_location(
        "dense_pop_coff", _frame_tool_path("object-adapter")
    )
    C = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(C)
    raw = object_path.read_bytes()
    c = C.Coff(raw)
    before = C.Coff(raw)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, c, DENSE_ARRAY_POP_BACKEND)
    assert exports == ["js_array_pop"] and set(copies) == _dense_pop_copied_helpers(source), (
        exports,
        copies,
    )
    names = {s["name"] for s in c.all_symbols.values()}
    added = []
    for name in exports:
        if "qjs_frame_core_" + name not in names:
            c.expose(name)
            added.append(name)
    fn = c.symbols["js_array_pop"]
    table = next(
        s
        for s in c.all_symbols.values()
        if s["name"] == "js_array_proto_funcs" and s["section"] > 0
    )
    target = c.external("JS_FrameDenseArrayPop")
    routes = []
    observed = []
    for si, rec in enumerate(c.section_records, 1):
        if si != table["section"]:
            continue
        assert c.sections[si - 1]["name"].startswith(".rdata") and not rec["flags"] & 0x20000000
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", c.data, at)
            s = c.all_symbols[sym]
            if kind != 1 or s["section"] != fn["section"]:
                continue
            addend = struct.unpack_from("<Q", c.data, rec["raw"] + off)[0]
            if addend + s["value"] != fn["value"]:
                continue
            begin = off - 24
            assert begin >= table["value"] and (begin - table["value"]) % 32 == 0
            entry = raw[rec["raw"] + begin : rec["raw"] + begin + 32]
            assert entry[8] == 3 and entry[9] == 0 and entry[16] == 0 and entry[17] == 1
            magic = struct.unpack_from("<h", entry, 10)[0]
            assert magic in (0, 1)
            # Resolve the descriptor name from its own typed name relocation.
            nameslots = [
                struct.unpack_from("<IIH", c.data, rec["reloc"] + 10 * j)
                for j in range(rec["count"])
                if struct.unpack_from("<I", c.data, rec["reloc"] + 10 * j)[0] == begin
            ]
            assert len(nameslots) == 1 and nameslots[0][2] == 1
            ns = c.all_symbols[nameslots[0][1]]
            nr = c.section_records[ns["section"] - 1]
            nameoff = ns["value"] + struct.unpack_from("<Q", entry, 0)[0]
            end = raw.index(b"\0", nr["raw"] + nameoff)
            name = raw[nr["raw"] + nameoff : end].decode("ascii")
            assert name == ("pop" if magic == 0 else "shift"), (name, magic)
            observed.append(dict(name=name, magic=magic, section=si, offset=off))
            if magic:
                continue
            struct.pack_into("<Q", c.data, rec["raw"] + off, 0)
            struct.pack_into("<I", c.data, at + 4, target)
            routes.append(
                dict(
                    section=si,
                    offset=off,
                    kind=1,
                    original_symbol=sym,
                    original_addend=addend,
                    name=name,
                    magic=magic,
                    target="JS_FrameDenseArrayPop",
                )
            )
    assert len(routes) == 1 and sorted(x["name"] for x in observed) == ["pop", "shift"], observed
    result = bytearray(c.finish())
    old_end = before.string_offset + len(before.strings)
    for rec in before.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            v = struct.unpack_from("<I", raw, at)[0]
            if v and v >= old_end:
                struct.pack_into("<I", result, at, v + len(result) - len(raw))
    check = C.Coff(result)
    for si, (a, b) in enumerate(zip(before.section_records, check.section_records), 1):
        old = raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])
        new = bytearray(result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"]))
        rr = bytearray(result[b["reloc"] : b["reloc"] + b["count"] * 10])
        pr = raw[a["reloc"] : a["reloc"] + a["count"] * 10]
        for route in routes:
            if route["section"] != si:
                continue
            off = route["offset"]
            new[off : off + 8] = old[off : off + 8]
            hits = [i for i in range(a["count"]) if struct.unpack_from("<I", pr, 10 * i)[0] == off]
            assert len(hits) == 1
            at = 10 * hits[0] + 4
            rr[at : at + 4] = pr[at : at + 4]
        assert new == old and rr == pr, ("Unexpected dense pop adapter change", si)
    assert all(check.all_symbols[i] == s for i, s in before.all_symbols.items())
    backup = object_path.with_name(object_path.name + ".before-dense-pop")
    assert not backup.exists()
    backup.write_bytes(raw)
    object_path.write_bytes(result)
    object_path.with_name(object_path.name + ".dense-pop.json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                observed_descriptors=observed,
                added_exports=added,
                exports=exports,
                copied_helpers=copies,
                policy="Exactly one typed ADDR64 array pop pointer validated by name, magic, private signature and table bounds; shift unchanged, every old payload and relocation otherwise fixed.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    link_spec = importlib.util.spec_from_file_location(
        "call_link_adapt", _frame_tool_path("call-link")
    )
    link_module = importlib.util.module_from_spec(link_spec)
    link_spec.loader.exec_module(link_module)
    link_module.adapt(source, object_path)


def compile_dense_array_pop(source, build, *, msvc=False):
    import importlib.util, json, struct
    from pathlib import Path
    from types import SimpleNamespace

    here = Path(__file__).resolve().parent

    def module(n, file):
        sp = importlib.util.spec_from_file_location(n, _frame_tool_path(file))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("dense_pop_compile_coff", "object-adapter.py")
    M = module("dense_pop_compiler", "atod.py")
    core = C.Coff((_frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")).read_bytes())
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, core, DENSE_ARRAY_POP_BACKEND)
    assert exports == ["js_array_pop"] and set(copies) == _dense_pop_copied_helpers(source)
    assert core.symbols["qjs_frame_core_js_array_pop"]["section"] > 0
    prefix = "".join("#define " + n + " dense_pop_local_" + n + "\n" for n in copies)
    header = prefix + header
    private = _frame_generated_file(build, "quickjs-dense-array-pop-private.h")
    private.write_text(header, encoding="utf-8")

    class PopCoff(C.Coff):
        def finish(self):
            for index, s in self.all_symbols.items():
                n = s["name"]
                if n in ("dense_pop_control", "dense_pop_leaf_control") and s["section"] > 0:
                    name = (
                        "JS_FrameDenseArrayPopControl"
                        if n == "dense_pop_control"
                        else "JS_FrameDensePopLeafControl"
                    )
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
                    self.data[self.table + index * self.stride + self.class_offset] = 2
                if (
                    s["section"] > 0
                    and s["storage"] == 2
                    and (
                        (
                            s["type"] & 32
                            and n
                            not in (
                                "JS_FrameDenseArrayPop",
                                "JS_FrameDenseArrayPopState",
                                "JS_FrameDensePopLeafState",
                                "JS_FrameDensePopLeafCount",
                            )
                        )
                        or n.startswith(("??_C@", "__xmm@", "__real@"))
                    )
                ):
                    name = "dense_pop_emitted_" + hashlib.sha256(n.encode()).hexdigest()[:32]
                    at = len(self.strings)
                    self.strings += name.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for rec in self.section_records:
                n = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode()
                if n.startswith("/"):
                    at = int(n[1:])
                    n = self.strings[at : self.strings.index(0, at)].decode()
                if n == ".qjssrc$C" or n.startswith(".pdata"):
                    flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                    struct.pack_into("<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040)
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=PopCoff)
    argv = M.win_argv
    M.win_argv = lambda cmd: [a for a in argv(cmd) if not a.startswith("-g")] + (
        [] if msvc else ["-g0"]
    )
    output = _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.obj")

    def generate(source, path):
        path.write_text(
            '#include "quickjs-dense-array-pop-private.h"\n' + DENSE_ARRAY_POP_BACKEND,
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-dense-array-pop.c",
        late_name=".qjssrc$C",
    )
    compile_dense_pop_leaf(source, build, output, msvc=msvc)
    module("call_link_native", "call-link.py").compile_backend(source, build, output, msvc=msvc)
    (_frame_generated_file(build, "quickjs-dense-array-pop-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                exports=exports,
                copied_helpers=copies,
                source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                private_sha256=hashlib.sha256(header.encode()).hexdigest(),
                backend_sha256=sha_text(DENSE_ARRAY_POP_BACKEND),
                policy="Existing native C frame, interrupts, borrowed argc, result ownership and fallback retained. Dense live array/int length/count/writable own slot only. Move owned tail, decrement count, update int length; no allocator, coercion, callback, Get/Set or GC root omission. Same-image QJS_DISABLE_DENSE_ARRAY_POP.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


@source_abi
def compile_dense_pop_leaf(source, build, output, *, msvc=False):
    import importlib.util, json, struct, subprocess
    from pathlib import Path

    here = Path(__file__).resolve().parent

    def module(n, file):
        sp = importlib.util.spec_from_file_location(n, _frame_tool_path(file))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("dense_leaf_coff", "object-adapter.py")
    M = module("dense_leaf_compile", "atod.py")
    K = module("dense_leaf_kernel", "c-invoke.py")
    merge = module("dense_leaf_merge", "extension-merge.py")
    proof = json.loads(output.with_suffix(".compile.json").read_text())
    compiler = Path(proof["compiler_command"][0])
    defines = [x for x in proof["compiler_command"][1:] if x.startswith(("-D", "/D"))]
    crt_flag = _probe_crt_flag(proof["compiler_command"])
    diag = any("QJS_INTERP_FRAME_DIAGNOSTICS" in x for x in defines)
    probe = _frame_generated_file(build, "quickjs-dense-pop-leaf-layout.c")
    pe = probe.with_suffix(".exe")
    probe.write_text(
        r"""#include "quickjs-dense-array-pop-private.h"
#include <stdio.h>
#if QJS_ABI_HAS_PREFIX_RC
#define FRAME_SHAPE_PROPERTIES offsetof(JSShape,hash_table)
#else
#define FRAME_SHAPE_PROPERTIES offsetof(JSShape,prop)
#endif
int main(void) {
    JSObject p={0}; JSShapeProperty q={0}; unsigned f=0,m=0; uint32_t v=0;
    p.fast_array=1; p.extensible=1;
    for(unsigned i=0;i<sizeof(p);i++) if(((unsigned char*)&p)[i]) {f=i;m=((unsigned char*)&p)[i];break;}
    q.flags=1; memcpy(&v,&q,4); unsigned shift=0; while(v>1) {v>>=1;shift++;}
    printf("POP_LEAF_LAYOUT %zu %zu %zu %u %u %zu %zu %zu %zu %zu %zu %zu %u %u %zu\n",
        sizeof(JSValue),offsetof(JSValue,tag),offsetof(JSObject,class_id),f,m,
        offsetof(JSObject,shape),offsetof(JSObject,prop),offsetof(JSObject,u.array.u.values),
        offsetof(JSObject,u.array.count),offsetof(JSShape,prop_hash_mask),FRAME_SHAPE_PROPERTIES,
        offsetof(JSShapeProperty,atom),shift,JS_ATOM_length,offsetof(JSContext,rt));
    p=(JSObject){0}; p.is_exotic=1; f=0; m=0;
    for(unsigned i=0;i<sizeof(p);i++) if(((unsigned char*)&p)[i]) {f=i;m=((unsigned char*)&p)[i];break;}
    _Static_assert(offsetof(JSShape,proto)==QJS_ABI_OFF_JSShape_proto,"ordinary prototype layout");
    _Static_assert(offsetof(JSShape,prop_count)==QJS_ABI_OFF_JSShape_prop_count && sizeof(JSShapeProperty)==8,"scalar hint slot layout");
    printf("STRING_PROTO_LAYOUT %u %zu %u %u %zu %zu %zu %zu %zu %zu %zu %zu %u %u %u %u\n",
        JS_ATOM_length,offsetof(JSContext,class_proto),JS_CLASS_STRING,JS_CLASS_OBJECT,sizeof(JSValue),
        offsetof(JSValue,tag),offsetof(JSObject,class_id),offsetof(JSObject,shape),offsetof(JSObject,prop),
        offsetof(JSShape,prop_hash_mask),FRAME_SHAPE_PROPERTIES,offsetof(JSShapeProperty,atom),shift,JS_PROP_TMASK,f,m);
    return 0;
}
""",
        encoding="utf-8",
    )
    command = (
        [
            str(compiler),
            "/nologo",
            "/O2",
            crt_flag,
            "/std:c11",
            "/experimental:c11atomics",
            "/I" + str(build),
            "/I" + str(source),
            "/I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "/Fe:" + str(pe),
            "/Fo:" + str(probe.with_suffix(".obj")),
        ]
        if msvc
        else [
            str(compiler),
            "-O2",
            "-g0",
            "-I" + str(build),
            "-I" + str(source),
            "-I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "-o",
            str(pe),
        ]
    )
    result = subprocess.run(command, capture_output=True)
    probe.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    result = subprocess.run([str(pe)], capture_output=True)
    assert result.returncode == 0
    match = re.search(rb"POP_LEAF_LAYOUT ([0-9 ]+)", result.stdout)
    assert match, result.stdout
    layout = list(map(int, match[1].split()))
    assert len(layout) == 15
    blocks = K.dense_pop_leaf_kernel(diag, not msvc, layout)
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-dense-pop-leaf.asm"
        if msvc
        else "quickjs-interpreter-dense-pop-leaf.S",
    )
    ao = _frame_generated_file(build, "quickjs-interpreter-dense-pop-leaf.obj")
    if msvc:
        proto_match = re.search(rb"STRING_PROTO_LAYOUT ([0-9 ]+)", result.stdout)
        assert proto_match, result.stdout
        proto_layout = list(map(int, proto_match[1].split()))
        assert len(proto_layout) == 16
        template = json.loads(
            (_frame_build_file(build, "msvc-string-proto-template.json")).read_text()
        )
        assert template["status"] == "passed" and template["diagnostics"] == diag
        blocks += K.string_proto_data_kernel(diag, proto_layout, template["own_probe"])
        blocks += K.object_proto_data_kernel(diag, proto_layout, template["own_probe"])
        blocks += K.object_proto_hint_kernel(diag)
    if msvc:
        refs = [
            "JS_FrameDenseArrayPop:PROC",
            "JS_FrameDenseArrayPopControl:BYTE",
            "JS_FrameDensePopLeafControl:BYTE",
            "JS_FrameDensePopLeafHits:QWORD",
            "JS_FrameCInvokeControl:BYTE",
            "JS_FrameCInvokeConfig:PROC",
            "JS_FrameCInvokeContinue:PROC",
            "JS_FrameInterpPropertyCold_unwind:BYTE",
            "JS_FrameStringProtoControl:BYTE",
            "JS_FrameObjectProtoControl:BYTE",
            "JS_FrameObjectProtoHintControl:BYTE",
            "JS_FrameObjectProtoHints:DWORD",
            "JS_FrameObjectProtoHintHits:QWORD",
            "JS_FrameStringProtoHits:DWORD",
            "JS_FrameInterpProperty_get_field2:PROC",
            "JS_FrameStringProtoReturn:BYTE",
            "__imp_getenv:QWORD",
        ]
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + x for x in refs],
            ".qjssrc$C SEGMENT ALIGN(16) 'CODE'",
        ]
        for name, stream in blocks:
            lines += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for x in stream:
                x = x.replace("rip+", "")
                if x.endswith(":"):
                    lines += ["PUBLIC " + x[:-1], x[:-1] + "::"]
                else:
                    lines += [re.sub(r"^(j\w+) (JS_Frame\w+|denseleaf_\w+)$", r"\1 NEAR PTR \2", x)]
            lines += [name + "_end LABEL BYTE", name + " ENDP"]
        lines += [
            "ALIGN 4",
            "stringproto_api_unwind LABEL BYTE",
            "DB 1,0,0,0",
            'JS_FrameStringProtoDisable DB "QJS_DISABLE_STRING_PROTO_DATA",0',
            'JS_FrameObjectProtoDisable DB "QJS_DISABLE_OBJECT_PROTO_DATA",0',
            'JS_FrameObjectProtoHintDisable DB "QJS_DISABLE_OBJECT_PROTO_HINT",0',
            ".qjssrc$C ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        for name, _ in blocks:
            unwind = (
                "stringproto_api_unwind"
                if name
                in (
                    "JS_FrameStringProtoState",
                    "JS_FrameStringProtoCount",
                    "JS_FrameObjectProtoState",
                    "JS_FrameObjectProtoHit",
                    "JS_FrameObjectProtoHintState",
                    "JS_FrameObjectProtoHintCount",
                )
                else "JS_FrameInterpPropertyCold_unwind"
            )
            lines += ["DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + unwind]
        lines += [".pdata$zzzzzznullfast ENDS", "END"]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(ao), str(asm)]
    else:
        lines = [".intel_syntax noprefix", '.section .qjssrc$C,"xr"']
        for name, stream in blocks:
            lines += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
            ]
            for x in stream:
                if x.endswith(":"):
                    lines += [".globl " + x[:-1]]
                lines.append(x)
            lines += [name + "_end:"]
        lines += [
            ".p2align 2",
            "denseleaf_unwind:",
            ".byte 33,0,0,0",
            ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _ in blocks:
            lines += [".rva " + name + ", " + name + "_end, denseleaf_unwind"]
        command = [str(compiler), "-c", str(asm), "-o", str(ao)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    result = subprocess.run(command, capture_output=True)
    asm.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    ac = C.Coff(ao.read_bytes())
    rel32_corrections = []
    # AMD64 REL32_n computes S+A-(P+4+n). Keep instruction bytes/widths;
    # absorb the trailing n bytes into the addend before the REL32-only merge.
    for rec in ac.section_records:
        for i in range(rec["count"]):
            pos = rec["reloc"] + 10 * i
            off, symbol, kind = struct.unpack_from("<IIH", ac.data, pos)
            if 5 <= kind <= 9:
                assert msvc and off + 4 <= rec["size"]
                at = rec["raw"] + off
                before = struct.unpack_from("<i", ac.data, at)[0]
                after = before - (kind - 4)
                struct.pack_into("<i", ac.data, at, after)
                struct.pack_into("<H", ac.data, pos + 8, 4)
                rel32_corrections.append(
                    dict(
                        offset=off,
                        symbol=ac.all_symbols[symbol]["name"],
                        old_kind=kind,
                        old_addend=before,
                        new_addend=after,
                    )
                )
    for number, rec in enumerate(ac.section_records, 1):
        name = merge.section_name(ac, number)
        if name.startswith(".xdata"):
            at = len(ac.strings)
            ac.strings += b".qjssrc$C\0"
            ac.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            for index, s in ac.all_symbols.items():
                if (
                    s["section"] == number
                    and s["storage"] == 3
                    and s["type"] == 0
                    and s["name"] == name
                ):
                    struct.pack_into("<II", ac.data, ac.table + index * ac.stride, 0, at)
        if name.startswith((".pdata", ".xdata")) or name == ".qjssrc$C":
            struct.pack_into("<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    ao.write_bytes(ac.finish())
    merge.append(
        output,
        ao,
        "JS_FrameDensePopLeafEntry",
        "dense-pop-leaf",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameDenseArrayPop",
        baseline_sections=(),
    )
    asm.with_suffix(".json").write_text(
        json.dumps(
            dict(
                status="passed",
                layout=layout,
                diagnostics=diag,
                toolchain="msvc" if msvc else "mingw",
                rel32_corrections=rel32_corrections,
                source_sha256=hashlib.sha256(asm.read_bytes()).hexdigest(),
                object_sha256=hashlib.sha256(ao.read_bytes()).hexdigest(),
                probe_image_sha256=hashlib.sha256(pe.read_bytes()).hexdigest(),
                policy="One old zero-actual near-Jcc retarget, old native bodies/PCs retained. Live exact descriptor and int dense/writable slot only; old runtime/quota/interrupt controls before publication. Success uses no C call/native SF/TLS mutation/allocator/callback. Existing PC/SP/pending commit and XMM0 ownership consumer retain reentrant GC cleanup. QJS_DISABLE_DENSE_ARRAY_POP_LEAF; diagnostic-only hit increments.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
