"""Pure-C async-generator capability source preparation."""

import hashlib
import importlib.util
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


def _load_mod(name):
    sp = importlib.util.spec_from_file_location(
        "c_extract_" + name.replace("-", "_"), _frame_tool_path(name)
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def prepare_source(source, source_contract):
    """Prepare the reviewed C algorithm independently of object-file routing.

    The caller validates its platform's source contract first.  Object-level
    adapters use their reviewed caller/callee shapes; a source-owned platform can
    compile this algorithm with the real private types in the core TU.
    """
    adapter = _load_mod("object-adapter-c")
    raw = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(raw)}
    begin = raw.index("typedef struct JSPromiseData {")
    end = raw.index("} JSPromiseReactionData;", begin) + len("} JSPromiseReactionData;")
    types = raw[begin:end]
    assert hashlib.sha256(types.encode()).hexdigest() == source_contract["promise_types_sha256"]
    begin = raw.index("typedef enum JSAsyncGeneratorStateEnum")
    end = raw.index("} JSAsyncGeneratorData;", begin) + len("} JSAsyncGeneratorData;")
    gen_types = raw[begin:end]
    assert (
        hashlib.sha256(gen_types.encode()).hexdigest() == source_contract["generator_types_sha256"]
    )
    expanded = raw.replace(
        "static inline bool double_is_int32",
        types + "\n" + gen_types + "\nstatic inline bool double_is_int32",
        1,
    )
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    boundary = "\n }\n\nstatic void js_async_generator_reject("
    assert expanded.count(boundary) == 1
    expanded = expanded.replace(boundary, "\n}\n\nstatic void js_async_generator_reject(", 1)
    formatted = "static int JS_PRINTF_FORMAT_ATTR(3, 4) JS_ThrowTypeErrorOrFalse("
    assert expanded.count(formatted) == 1
    expanded = expanded.replace(formatted, "static int JS_ThrowTypeErrorOrFalse(", 1)
    settle = functions["js_async_generator_resolve_or_reject"]
    call = "    ret = JS_Call(ctx, next->resolving_funcs[is_reject], JS_UNDEFINED, 1,\n                  &result);"
    assert settle.count(call) == 1
    settle = settle.replace(
        call,
        """    if (JS_IsUndefined(next->resolving_funcs[0]) && JS_IsUndefined(next->resolving_funcs[1]))
        ret = js_generator_capability_settle(ctx, next->promise, result, is_reject);
    else
"""
        + call,
        1,
    )
    assert expanded.count(functions["js_async_generator_resolve_or_reject"]) == 1
    expanded = expanded.replace(functions["js_async_generator_resolve_or_reject"], settle, 1)
    await_body = functions["js_async_generator_await"].replace(
        "static int js_async_generator_await(", "static int js_generator_capability_await(", 1
    )
    assert await_body.count("JSValue value)") == 1
    await_body = await_body.replace("JSValue value)", "JSValue value, unsigned await_flags)", 1)
    marker = "    if (JS_IsException(promise))\n        goto fail;"
    assert await_body.count(marker) == 1
    await_body = await_body.replace(
        marker,
        marker
        + """
    if (await_flags & 2) {
        int ready = js_ready_generator_await_try(ctx, s, promise);
        if (ready) {
            JS_FreeValue(ctx, promise);
            return ready < 0 ? -1 : 0;
        }
    }
""",
        1,
    )
    marker = "    promise = js_promise_resolve(ctx, ctx->promise_ctor,"
    assert await_body.count(marker) == 1
    await_body = await_body.replace(
        marker,
        """    if (await_flags & 1) {
        int ready = js_ready_generator_direct_try(ctx, s, value);
        if (ready) return ready < 0 ? -1 : 0;
    }
"""
        + marker,
        1,
    )
    parent = functions["js_async_generator_resume_next"].replace(
        "static void js_async_generator_resume_next(", "void JS_GeneratorCapabilityResume(", 1
    )
    opening = parent.index("\n{") + 2
    parent = (
        parent[:opening]
        + """
    unsigned char mode = js_generator_capability_get_mode();
    if (mode & 128) { qjs_generator_capability_original(ctx, s); return; }
"""
        + parent[opening:]
    )
    call = "js_async_generator_await(ctx, s, value)"
    assert parent.count(call) == 1
    parent = parent.replace(call, "js_generator_capability_await(ctx, s, value, mode & 3)", 1)
    promise_new = functions["js_promise_new"].replace(
        "static JSValue js_promise_new(", "static JSValue js_generator_capability_new(", 1
    )
    opening = promise_new.index("\n{") + 2
    promise_new = (
        promise_new[:opening]
        + "\n    resolving_funcs[0] = resolving_funcs[1] = JS_UNDEFINED;\n"
        + promise_new[opening:]
    )
    call = "    if (js_create_resolving_functions(ctx, resolving_funcs, obj)) {"
    assert promise_new.count(call) == 1
    promise_new = promise_new.replace(
        call,
        "    if (ctx->rt->promise_hook && js_create_resolving_functions(ctx, resolving_funcs, obj)) {",
        1,
    )
    next_body = functions["js_async_generator_next"].replace(
        "static JSValue js_async_generator_next(", "JSValue JS_GeneratorCapabilityNext(", 1
    )
    opening = next_body.index("\n{") + 2
    next_body = (
        next_body[:opening]
        + """
    if (!(js_generator_capability_get_mode() & 4) ||
        !JS_GetOpaque(this_val, JS_CLASS_ASYNC_GENERATOR) || !JS_IsObject(ctx->promise_ctor) ||
        ctx->rt->promise_hook ||
        js_check_stack_overflow(ctx->rt, 4096))
        return qjs_generator_capability_original_next(ctx, this_val, argc, argv, magic);
"""
        + next_body[opening:]
    )
    call = "JS_NewPromiseCapability(ctx, resolving_funcs)"
    assert next_body.count(call) == 1
    next_body = next_body.replace(
        call, "js_generator_capability_new(ctx, JS_UNDEFINED, resolving_funcs)", 1
    )
    call = "js_async_generator_resume_next(ctx, s)"
    assert next_body.count(call) == 1
    next_body = next_body.replace(call, "JS_GeneratorCapabilityResume(ctx, s)", 1)
    callback = functions["js_async_generator_resolve_function"].replace(
        "static JSValue js_async_generator_resolve_function(",
        "static JSValue JS_GeneratorCapabilityReaction(",
        1,
    )
    assert callback.count(call) == 1
    callback = callback.replace(call, "JS_GeneratorCapabilityResume(ctx, s)", 1)
    preface = """
#undef JS_CallInternal
#define JS_CallInternal JS_FrameDispatchInternal
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst,
                                       JSValueConst, int, JSValueConst *, int);
#define js_async_generator_resolve_function JS_GeneratorCapabilityReaction
static JSValue JS_GeneratorCapabilityReaction(JSContext *, JSValueConst, int,
                                               JSValueConst *, int, JSValueConst *);
static JSValue js_generator_capability_settle(JSContext *, JSValueConst, JSValueConst, bool);
"""
    body = (
        _frame_source_text(source, "generator-capability.inc")
        + "\n"
        + promise_new
        + "\n"
        + await_body
        + "\n"
        + parent
        + "\n"
        + next_body
        + "\n"
        + callback
    )
    return expanded, preface, body
