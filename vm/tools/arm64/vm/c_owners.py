"""Thin #include/macro wiring pass attaching external C fast-path files for ARM64."""

import re
from arm64.vm.specialize import _replace_exact, sha


def _tls_fast_inc(source, rel_path, old_decl, new_decl):
    text = (source / rel_path).read_text(encoding="utf-8")
    return _replace_exact(text, old_decl, new_decl, 1, f"{rel_path} TLS isolation")


def _specialize_c_owners(source, output):
    updated = {}

    # 1. Wire literal Release helpers and common C fast-path headers into quickjs-linux-literals.h.
    lit_path = output / "quickjs-linux-literals.h"
    lit = lit_path.read_text()
    for pat, repl in (
        ("JS_LinuxLiteralRunVM(state)", "QJS_FAST_LITERAL_RUN_VM(state)"),
        ("JS_LinuxLiteralRunVM(s)", "QJS_FAST_LITERAL_RUN_VM(s)"),
    ):
        if pat not in lit:
            raise ValueError(f"fast_vm literals anchor missing: {pat}")
        lit = lit.replace(pat, repl)
    lit = _replace_exact(
        lit,
        '#include "src/arm64/linux/interpreter-literals.inc"\n',
        '#include "src/arm64/linux/interpreter-literals.inc"\n'
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_FAST_LITERAL_RUN_VM(s) JS_FrameInterp(s)\n"
        "#else\n"
        "#define QJS_FAST_LITERAL_RUN_VM(s) JS_LinuxLiteralRunVM(s)\n"
        "#endif\n",
        1,
        "literals macro",
    )
    lit, n_lit = re.subn(
        r"FRAME_CODE int JS_LinuxLiteralEnter\(JSFrameRegisterState \*state\)\n\{.*?\n\}",
        '#include "src/arm64/linux/interpreter-literals-fast.inc"',
        lit,
        count=1,
        flags=re.S,
    )
    if n_lit != 1:
        raise ValueError(f"Expected 1 JS_LinuxLiteralEnter anchor, got {n_lit}")
    fast_ctor_inc = (source / "src/common/kernel/fast-construct.inc").read_text(encoding="utf-8")
    instof_inc = (source / "src/common/value/instanceof-fast.inc").read_text(encoding="utf-8")
    fg_inc = _tls_fast_inc(
        source,
        "src/common/property/fast-get-field.inc",
        "static FastGetFieldCache fg_cache[32];",
        "static _Thread_local FastGetFieldCache fg_cache[32];",
    )
    cl_inc = _tls_fast_inc(
        source,
        "src/common/call/compound-leaf.inc",
        "static CLCacheEntry cl_cache[64];",
        "static _Thread_local CLCacheEntry cl_cache[64];",
    )
    cl_inc = _replace_exact(
        cl_inc,
        "typedef struct {\n    JSContext *ctx;\n    JSFunctionBytecode *b;",
        "typedef struct {\n    JSContext *ctx;\n    uint64_t epoch;\n    JSFunctionBytecode *b;",
        1,
        "compound-leaf epoch field",
    )
    cl_inc = _replace_exact(
        cl_inc,
        "    if (unlikely(e->b != b || e->ctx != ctx || e->bc_len != len || e->bc_head != head ||\n"
        "                 e->bc_tail != tail)) {\n"
        "        memset(e, 0, sizeof(*e));\n"
        "        e->ctx = ctx;\n"
        "        e->b = b;",
        "    if (unlikely(e->epoch != state->rt->property_ic_epoch || e->b != b || e->ctx != ctx ||\n"
        "                 e->bc_len != len || e->bc_head != head || e->bc_tail != tail)) {\n"
        "        memset(e, 0, sizeof(*e));\n"
        "        e->ctx = ctx;\n"
        "        e->epoch = state->rt->property_ic_epoch;\n"
        "        e->b = b;",
        1,
        "compound-leaf epoch check and store",
    )
    fast_includes = (
        "\n#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_FAST_INSTANCEOF_STATE_ENTRY\n"
        "#define QJS_EMIT_FAST_CORE_BUILTINS\n"
        + fast_ctor_inc.rstrip()
        + "\n"
        + instof_inc.rstrip()
        + "\n"
        + fg_inc.rstrip()
        + "\n"
        + cl_inc.rstrip()
        + "\n"
        "#undef QJS_EMIT_FAST_CORE_BUILTINS\n"
        "#undef QJS_FAST_INSTANCEOF_STATE_ENTRY\n"
        "#endif\n"
    )
    lit = _replace_exact(
        lit,
        '#pragma pop_macro("FRAME_INLINE")\n#pragma pop_macro("FRAME_CODE")\n',
        fast_includes + '#pragma pop_macro("FRAME_INLINE")\n#pragma pop_macro("FRAME_CODE")\n',
        1,
        "JS_FastConstructCall literals anchor",
    )
    lit_path.write_text(lit)
    updated["literals"] = sha(lit_path)

    # 2. Wire Release callback & Array.prototype.sort leaf bypasses.
    prep_path = output / "quickjs-linux-prepared-callback.h"
    prep = _replace_exact(
        prep_path.read_text(),
        "    --ctx->interrupt_counter;\n    frame = (JSFrame *)call->data;",
        "#if defined(QJS_AARCH64_CALL_LEAVES) && !defined(QJS_AARCH64_VM_INSTRUMENT)\n"
        "    {\n"
        "        extern JSValue JS_FrameAArch64CallLeaf(JSContext *, JSValueConst, JSValueConst, int, const JSValue *, unsigned);\n"
        "        JSValue leaf_res = JS_FrameAArch64CallLeaf(ctx, func, this_value, argc, argv, 2);\n"
        "        if (!JS_IsException(leaf_res))\n"
        "            return leaf_res;\n"
        "    }\n"
        "#endif\n"
        "    --ctx->interrupt_counter;\n    frame = (JSFrame *)call->data;",
        1,
        "prepared-callback leaf bypass",
    )
    prep_path.write_text(prep)
    updated["prepared_callbacks"] = sha(prep_path)

    arr_path = output / "quickjs-linux-arrays.h"
    arr_text = arr_path.read_text()
    arr_text = _replace_exact(
        arr_text,
        "    --ctx->interrupt_counter;\n    frame = (JSFrame *)call->data;",
        "#if defined(QJS_AARCH64_CALL_LEAVES) && !defined(QJS_AARCH64_VM_INSTRUMENT)\n"
        "    {\n"
        "        extern JSValue JS_FrameAArch64CallLeaf(JSContext *, JSValueConst, JSValueConst, int, const JSValue *, unsigned);\n"
        "        JSValue leaf_res = JS_FrameAArch64CallLeaf(ctx, call->cache.callee, JS_UNDEFINED, 2, argv, 2);\n"
        "        if (!JS_IsException(leaf_res))\n"
        "            return leaf_res;\n"
        "    }\n"
        "#endif\n"
        "    --ctx->interrupt_counter;\n    frame = (JSFrame *)call->data;",
        1,
        "sort compare leaf bypass",
    )
    arr_text = _replace_exact(
        arr_text,
        "    JS_FrameInterp(&state);\n",
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    extern int JS_LinuxLiteralEnter(JSFrameRegisterState *);\n"
        "    JS_LinuxLiteralEnter(&state);\n"
        "#else\n"
        "    JS_FrameInterp(&state);\n"
        "#endif\n",
        1,
        "arrays sort state enter",
    )
    arr_text = _replace_exact(
        arr_text,
        "    JS_FrameInterp(state);\n",
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    extern int JS_LinuxLiteralEnter(JSFrameRegisterState *);\n"
        "    JS_LinuxLiteralEnter(state);\n"
        "#else\n"
        "    JS_FrameInterp(state);\n"
        "#endif\n",
        1,
        "arrays sort direct state enter",
    )
    arr_path.write_text(arr_text)
    updated["array_workers"] = sha(arr_path)

    # 3. Switch C-entry and call-leaves to external Release -fast.inc owners.
    centry_path = output / "interpreter-aarch64-c-entry.h"
    centry_text = _replace_exact(
        centry_path.read_text(),
        '#include "src/arm64/linux/interpreter-c-entry.inc"\n',
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/arm64/linux/interpreter-c-entry.inc"\n'
        "#else\n"
        '#include "src/arm64/linux/interpreter-c-entry-fast.inc"\n'
        "#endif\n",
        1,
        "interpreter-aarch64-c-entry.h flatten",
    )
    centry_path.write_text(centry_text)
    updated["c_entry"] = sha(centry_path)

    cl_path = output / "quickjs-aarch64-call-leaves.c"
    cl_path.write_text(
        '#include "quickjs-aarch64-call-leaves-private.h"\n'
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/arm64/linux/interpreter-call-leaves.inc"\n'
        "#else\n"
        '#include "src/arm64/linux/interpreter-call-leaves-fast.inc"\n'
        "#endif\n"
    )
    updated["call_leaves"] = sha(cl_path)

    # 4. Wire common virtual-arguments cache + JS_FastArrayFrom + arguments fast guard.
    va_fast_inc = (source / "src/common/linux/virtual-arguments-fast.inc").read_text(
        encoding="utf-8"
    )
    va_path = output / "quickjs-linux-virtual-arguments.c"
    va_path.write_text(
        '#include "quickjs-linux-virtual-arguments-private.h"\n'
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/common/linux/interpreter-virtual-arguments.inc"\n'
        "#else\n" + va_fast_inc.rstrip() + '\n#include "src/common/kernel/fast-array-from.inc"\n'
        "#endif\n"
        '__attribute__((visibility("hidden"))) FRAME_CODE\n'
        "int JS_LinuxVirtualArgumentsStep(JSFrameRegisterState *state)\n"
        "{\n    return js_linux_virtual_arguments_step(state);\n}\n"
    )
    updated["virtual_arguments"] = sha(va_path)

    arg_path = output / "quickjs-linux-arguments.h"
    arg_text = _replace_exact(
        arg_path.read_text(),
        "    while (!JS_FrameInterp(&state)) {\n",
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    extern int JS_LinuxLiteralEnter(JSFrameRegisterState *);\n"
        "    while (!JS_LinuxLiteralEnter(&state)) {\n"
        "#else\n"
        "    while (!JS_FrameInterp(&state)) {\n"
        "#endif\n",
        1,
        "arguments state enter",
    )
    arg_text += (
        "\n#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_DEFINE_ARGUMENTS_CONSTRUCT_FAST_OK\n"
        + va_fast_inc.rstrip()
        + "\n#undef QJS_DEFINE_ARGUMENTS_CONSTRUCT_FAST_OK\n"
        "#endif\n"
    )
    arg_path.write_text(arg_text)
    updated["arguments"] = sha(arg_path)

    # 5. Wire common inline-properties, BigInt stack/PM fast path, and JS_FastCfuncForOfNext.
    def _wire_inline_ctor(src_txt):
        src_txt = _replace_exact(
            src_txt,
            "    p = js_malloc(ctx, sizeof(JSObject));",
            "    size_t inline_bytes = (class_id == JS_CLASS_OBJECT || (props && class_id == JS_CLASS_ARRAY))\n"
            "        ? qjs_inline_property_plan(sh, 0, props ? 4u : 0u) : 0;\n"
            "    p = js_malloc(ctx, inline_bytes ? inline_bytes : sizeof(JSObject));",
            1,
            "inline property ctor",
        )
        src_txt = _replace_exact(
            src_txt,
            "    p->prop = js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
            "    p->prop = inline_bytes\n"
            "                  ? qjs_inline_property_initialize(p, sh, 0, inline_bytes)\n"
            "                  : js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
            1,
            "inline property prop init",
        )
        return src_txt

    core_path = output / "quickjs-aarch64.c"
    core = core_path.read_text()
    inline_inc = (
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_VM_INSTRUMENT\n"
        "#else\n"
        "#define QJS_INLINE_PROPERTY_DEFINE_REALLOC_RT\n"
        "#endif\n"
        '#include "src/common/property/inline-properties.h"\n'
        "#define QJS_HYBRID_INLINE_PROPERTIES 1\n"
        "#undef QJS_INLINE_PROPERTY_DEFINE_REALLOC_RT\n"
        "#undef QJS_VM_INSTRUMENT\n\n"
    )
    core = _replace_exact(
        core,
        "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        inline_inc + "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        1,
        "core inline-properties header include",
    )
    core = _wire_inline_ctor(core)
    n_core_birth = len(
        re.findall(r"\bp->is_prototype\s*=\s*0\s*;\s*p->turbo_obj_flags\s*=\s*0\s*;", core)
    )
    if n_core_birth != 1:
        raise ValueError(f"Expected 1 core birth initializer, got {n_core_birth}")
    core = _replace_exact(
        core,
        '#include "src/common/function/closure-template.inc"',
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/common/function/closure-template.inc"\n'
        "#else\n"
        '#include "src/common/property/inline-closure-properties.inc"\n'
        "#endif",
        1,
        "core closure-properties include",
    )
    core = _replace_exact(
        core,
        '#include "src/common/property/property-ic.inc"',
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/common/property/property-ic.inc"\n'
        "#else\n"
        '#include "src/common/property/inline-property-ic-storage.inc"\n'
        "#endif",
        1,
        "core property-ic-storage include",
    )
    core = _replace_exact(
        core,
        "rt->property_ic_epoch = 1;",
        "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    rt->property_ic_epoch = 1;\n"
        "#else\n"
        "    {\n"
        "        static uint64_t qjs_arm_ic_epoch_seq;\n"
        "        rt->property_ic_epoch =\n"
        "            (__atomic_add_fetch(&qjs_arm_ic_epoch_seq, UINT64_C(1) << 32, __ATOMIC_RELAXED)) |\n"
        "            1u;\n"
        "    }\n"
        "#endif\n",
        1,
        "core unique per-runtime property_ic_epoch",
    )
    for pat, expected in (
        (r"js_realloc\(ctx,\s*p->prop,\s*(sizeof\(new_prop\[0\]\)\s*\*\s*new_size)\)", 2),
        (r"js_realloc\(ctx,\s*p->prop,\s*(sizeof\(p->prop\[0\]\)\s*\*\s*new_sh->prop_size)\)", 1),
    ):
        core, n_sub = re.subn(pat, r"qjs_inline_property_realloc(ctx, p, \1)", core)
        if n_sub != expected:
            raise ValueError(f"Expected {expected} core property reallocs for {pat}, got {n_sub}")
    core = _replace_exact(
        core,
        "    js_free_rt(rt, p->prop);",
        "    if (!qjs_inline_property_current(p)) js_free_rt(rt, p->prop);",
        1,
        "core object property free owner",
    )
    core = _replace_exact(
        core,
        "            s->prop_count += sh->prop_count;",
        "            s->prop_count += sh->prop_count;\n            qjs_inline_property_account(s, p);",
        1,
        "core memory usage accounting",
    )
    if '#include "src/common/value/bigint-divrem-fast.inc"' in core:
        if "js_bigint_try_divrem_stack(" not in core:
            raise ValueError("fast_vm core bigint-divrem-fast.inc included without call site")
    else:
        core = _replace_exact(
            core,
            "static JSBigInt *js_bigint_divrem(JSContext *ctx, const JSBigInt *a,\n",
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            '#include "src/common/value/bigint-divrem-fast.inc"\n'
            "#endif\n\n"
            "static JSBigInt *js_bigint_divrem(JSContext *ctx, const JSBigInt *a,\n",
            1,
            "core bigint helpers for divrem",
        )
        core = _replace_exact(
            core,
            "    a_sign = js_bigint_sign(a);\n"
            "    b_sign = js_bigint_sign(b);\n"
            "    na = a->len;\n"
            "    nb = b->len;\n\n"
            "    r = js_bigint_new(ctx, na + 2);\n",
            "    a_sign = js_bigint_sign(a);\n"
            "    b_sign = js_bigint_sign(b);\n"
            "    na = a->len;\n"
            "    nb = b->len;\n\n"
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    {\n"
            "        JSBigInt *fast_r = NULL;\n"
            "        if (js_bigint_try_divrem_stack(ctx, a, b, na, nb, a_sign, b_sign, is_rem, &fast_r))\n"
            "            return fast_r;\n"
            "    }\n"
            "#endif\n\n"
            "    r = js_bigint_new(ctx, na + 2);\n",
            1,
            "core bigint divrem stack + pseudo-Mersenne fast path",
        )
    core += (
        "\n#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_EMIT_FAST_FOR_OF_NEXT_SYMBOL\n"
        '#include "src/common/call/fast-for-of-next.inc"\n'
        "#undef QJS_EMIT_FAST_FOR_OF_NEXT_SYMBOL\n"
        "#endif\n"
    )
    core_path.write_text(core)
    updated["core"] = sha(core_path)

    json_path = output / "quickjs-linux-json.h"
    json_text, n_json = re.subn(
        r"js_realloc\(p->ctx,\s*o->prop,\s*(sizeof\(JSProperty\)\s*\*\s*\(size_t\)e->to->prop_size)\)",
        r"qjs_inline_property_realloc(p->ctx, o, \1)",
        json_path.read_text(),
    )
    if n_json != 3:
        raise ValueError(f"Expected 3 JSON property reallocs, got {n_json}")
    json_path.write_text(json_text)
    updated["json_workers"] = sha(json_path)

    null_path = output / "quickjs-linux-null-proto.h"
    null_text = null_path.read_text()
    n_null = len(re.findall(r"\bp->is_prototype\s*=\s*0\s*;", null_text))
    n_null_flags = len(re.findall(r"\bp->turbo_obj_flags\s*=\s*0\s*;", null_text))
    if n_null != 1 or n_null_flags < 1:
        raise ValueError(f"Expected 1 null-proto birth initializer, got {n_null}/{n_null_flags}")
    updated["null_proto"] = sha(null_path)

    return updated
