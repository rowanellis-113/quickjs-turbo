"""Thin #include/macro wiring pass attaching external C fast-path files for ARM64."""

import re
from arm64.vm.specialize import _replace_exact, sha


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
    fast_includes = (
        "\n#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "#define QJS_FAST_INSTANCEOF_STATE_ENTRY\n"
        "#define QJS_EMIT_FAST_CORE_BUILTINS\n"
        '#include "src/common/kernel/fast-construct.inc"\n'
        '#include "src/common/value/instanceof-fast.inc"\n'
        '#include "src/common/property/fast-get-field.inc"\n'
        '#include "src/common/call/compound-leaf.inc"\n'
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
    va_path = output / "quickjs-linux-virtual-arguments.c"
    va_path.write_text(
        '#include "quickjs-linux-virtual-arguments-private.h"\n'
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        '#include "src/common/linux/interpreter-virtual-arguments.inc"\n'
        "#else\n"
        '#include "src/common/linux/virtual-arguments-fast.inc"\n'
        '#include "src/common/kernel/fast-array-from.inc"\n'
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
        '#include "src/common/linux/virtual-arguments-fast.inc"\n'
        "#undef QJS_DEFINE_ARGUMENTS_CONSTRUCT_FAST_OK\n"
        "#endif\n"
    )
    arg_path.write_text(arg_text)
    updated["arguments"] = sha(arg_path)

    # 5. Wire common inline-properties, BigInt stack/PM fast path, and JS_FastCfuncForOfNext.
    def _wire_inline_ctor(src_txt):
        src_txt = _replace_exact(
            src_txt,
            "    p = js_malloc(ctx, sizeof(JSObject));",
            "    size_t inline_bytes = qjs_inline_property_plan(\n"
            "        sh, 0, ((props && class_id == JS_CLASS_OBJECT) ? 4u : 0u));\n"
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
    core, n_core_birth = re.subn(r"(\bp->is_prototype\s*=\s*0\s*;)", r"\1 p->__gc_mark = 0;", core)
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
    null_text, n_null = re.subn(
        r"(\bp->is_prototype\s*=\s*0\s*;)",
        r"\1 p->__gc_mark = 0;",
        null_path.read_text(),
    )
    if n_null != 1:
        raise ValueError(f"Expected 1 null-proto birth initializer, got {n_null}")
    null_path.write_text(null_text)
    updated["null_proto"] = sha(null_path)

    return updated
