"""Source-owned shared array loops and typed Linux prepared-call boundaries."""

import hashlib
import re
from c_workers import module, replace_one


def generate(source, output, core, adapter, *, arch_adapt):
    from common.paths import source_text

    preparer = module(source, "prepared-callback-c")
    virtual, proofs = preparer.prepare_source(source)
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(virtual)}
    bodies = "\n".join(
        '__attribute__((section(".text.qjs_callback_loop"), noipa))\n' + functions[p["prepared"]]
        for p in proofs
    )
    runtime = source_text(source, "linux-prepared-callback.inc")
    before = hashlib.sha256(runtime.encode()).hexdigest()

    # Reuse the complete common admission/activation/release algorithms.  The
    # Linux owner aliases real types; no foreign private struct clone or TLS
    # sequence crosses the platform boundary.
    begin = runtime.index("typedef struct JSFrameCallbackHost {")
    end = runtime.index("typedef struct JSFrameCallbackScope {", begin)
    runtime = (
        runtime[:begin]
        + """typedef JSFrameSharedAnchor JSFrameCallbackHost;
typedef JSFrameSegment JSFrameCallbackSegment;
typedef JSFrame JSFrameCallbackHeader;
"""
        + runtime[end:]
    )
    runtime = replace_one(
        runtime,
        "_Alignas(16) unsigned char state[CALLBACK_STATE_BYTES];",
        "union { _Alignas(16) JSFrameRegisterState native_state; "
        "unsigned char state[CALLBACK_STATE_BYTES]; };",
        "typed prepared state",
    )

    runtime = runtime.replace("host->state +", "(unsigned char *)host->state +")
    runtime = runtime.replace("host->state[CALLBACK_DIRECT]", "host->state->direct_host_calls")
    if runtime.count("call.barrier.state = call.state;") != 2:
        raise ValueError("Prepared barrier owner changed")
    runtime = runtime.replace(
        "call.barrier.state = call.state;", "call.barrier.state = &call.native_state;"
    )
    runtime = runtime.replace("((unsigned char *)&frame->sf)[62] = 1;", "FRAME_ROOT(frame) = 1;")
    # Compile readonly and owned-formal variants together with their common
    # scope declarations, rather than duplicating their private state owner.
    for marker in (
        "#ifndef QJS_CALLBACK_WRITABLE\n",
        "#endif /* inherited readonly implementation */",
        "#if defined(QJS_CALLBACK_WRITABLE)\n",
        "#endif /* writable implementation */",
    ):
        runtime = replace_one(runtime, marker, "", marker)
    runtime = runtime.replace(".qjscbck$C", ".text.qjs_callback")
    runtime = runtime.replace(".qjscbwr$C", ".text.qjs_callback_write")
    for name in ("every", "reduce"):
        old = "QJS_CONTROL_SLOT_ADDR(loop, qjs_frame_core_js_array_" + name + ");"
        runtime = replace_one(
            runtime, old, "loop = js_array_" + name + ";", "original array " + name
        )
    runtime = replace_one(
        runtime,
        "for (barrier = top->prev; barrier && !barrier->kind; barrier = barrier->prev) {}",
        "for (barrier = top->prev; barrier && (!barrier->kind || barrier->kind == 3); "
        "barrier = barrier->prev) {}",
        "Linux blocked VM anchor traversal",
    )
    runtime, selector, extra_record = arch_adapt(
        source,
        runtime,
        (source / "src/common/linux/interpreter-linux-prepared-callback.inc").read_text(),
    )
    prologue = """
static inline __attribute__((always_inline)) JSValue frame_callback_prepared_call(
    JSContext *, JSValueConst, JSValueConst, int, JSValueConst *, void *);
static inline __attribute__((always_inline)) JSValue frame_callback_write_prepared_call(
    JSContext *, JSValueConst, JSValueConst, int, JSValueConst *, void *);
"""
    worker = prologue + bodies + "\n" + runtime + "\n" + selector
    (output / "quickjs-linux-prepared-callback.h").write_text(worker)
    # All array/typed-array builtin routes are explicit. Original loop bodies
    # remain available to each common admission and per-call miss path.
    for name, expected in (("every", 10), ("reduce", 4)):
        pattern = r'(JS_CFUNC_MAGIC_DEF\("[^"\n]+",\s*\d+,\s*)js_array_' + name + r"(\s*,)"
        replacement = "JS_FrameCallbackWriteArray" + name.title()
        core, count = re.subn(pattern, lambda m: m[1] + replacement + m[2], core)
        if count != expected:
            raise ValueError(
                "Review all array/typed-array callback table routes: " + name + " " + str(count)
            )
    declaration = """
JSValue JS_FrameCallbackWriteArrayEvery(JSContext *, JSValueConst, int, JSValueConst *, int);
JSValue JS_FrameCallbackWriteArrayReduce(JSContext *, JSValueConst, int, JSValueConst *, int);
"""
    anchor = "static const JSCFunctionListEntry js_array_proto_funcs[] = {"
    core = replace_one(core, anchor, declaration + anchor, "array method table declarations")
    core += '\n#include "quickjs-linux-prepared-callback.h"\n'
    return core, dict(
        status="generated-not-qualified",
        common_runtime_sha256=before,
        generated_sha256=hashlib.sha256(worker.encode()).hexdigest(),
        loops=proofs,
        routes=dict(every=10, reduce=4),
        scope_types="actual core frame, segment, shared anchor and state",
        tls="compiler-managed Linux thread local slot",
        **extra_record,
    )
