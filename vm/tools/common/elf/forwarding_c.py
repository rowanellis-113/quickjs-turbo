"""Complete shared .call normalization, logical frames and native ownership.

Private returning probes receive32 separate scratch bytes cleanly without cloning.
"""

import ast
import hashlib
import json
import re
from c_workers import module, replace_one


def literal(source, name, variable):
    import importlib.util
    from common.paths import tool_path

    if (name, variable) in {
        ("call-forward", "ENTER"),
        ("call-forward", "PARENTS"),
        ("call-forward-owned", "CAPTURED_PROOF"),
    }:
        import call_forward_c as m

        return getattr(m, variable)
    if (name, variable) in {("call-prepare-c", "DATA_TYPE"), ("call-prepare-c", "KERNEL")}:
        import call_prepare_c as m

        return getattr(m, variable)
    sp = importlib.util.spec_from_file_location(
        "fwd_lit_" + name.replace("-", "_"), tool_path(name)
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return getattr(m, variable)


def release(text):
    old = "    rt->current_stack_frame = frame->sf.prev_frame;"
    new = (
        """    /* Keep logical wrappers visible through every observable close/free. */
    size_t forward_bytes=js_frame_forward_take(frame);
    used_bytes-=forward_bytes;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_release_stack(rt,forward_bytes);
#endif
"""
        + old
    )
    return replace_one(text, old, new, "logical wrapper release after child cleanup")


def policy(source, output, loop, *, forward_binding):
    from admission_c import function

    prepare = module(source, "call-prepare-c")
    entry = literal(source, "call-forward", "ENTER")
    marker = "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)"
    body = function(entry, marker) + "\n"
    kernel = prepare.prepared_commit_body(body)
    kernel = replace_one(
        kernel,
        "    JSValue leaf_value;\n",
        "",
        "prepared kernel removes its unreachable leaf temporary",
    )
    data = literal(source, "call-prepare-c", "DATA_TYPE")
    header = (
        """/* Shared source algorithms; actual Linux private types and ABI. */
" + forward_binding + "#
"""
        + data
        + """
__attribute__((visibility("hidden"),section(".data.qjs_linux_forward")))
JSFramePrepareData JS_FrameCallPrepareData={.control=255};
"""
        + entry
        + "\n"
        + kernel
        + """
static FRAME_INLINE void js_linux_forward_controls_init(void)
{
    __atomic_store_n(&JS_FrameCallForwardBorrowMissingControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardBorrowControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardOwnedControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallPrepareData.owned_control,
        getenv("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED")?2:1,__ATOMIC_RELAXED);
    unsigned char mode=getenv("QJS_DISABLE_FRAME_CALL_PREPARE")?2:1;
    if(getenv("QJS_OBSERVE_FRAME_CALL_PREPARE"))mode|=4;
    __atomic_store_n(&JS_FrameCallPrepareData.control,mode,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardNativeControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE")?2:1,__ATOMIC_RELAXED);
}

FRAME_CODE int JS_FrameCallForwardNativeCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
FRAME_CODE int JS_FrameCallForwardOwnedCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
FRAME_CODE int JS_FrameCallPrepareCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
"""
    )
    (output / "quickjs-linux-forward.h").write_text(header)
    loop = replace_one(
        loop,
        '#include "src/common/call/interpreter-context-types.inc"',
        '#include "src/common/call/interpreter-retained-context.inc"',
        "shared logical parent context",
    )
    loop = replace_one(
        loop,
        "/* This is one C activation for the complete supported JS call chain.",
        '#include "quickjs-linux-forward.h"\n\n/* This is one C activation for the complete supported JS call chain.',
        "shared forward algorithms after actual register/state helpers",
    )
    loop = release(loop)
    owners = [
        "call-forward",
        "call-forward-native",
        "call-forward-owned",
        "call-forward-borrow",
        "call-forward-borrow-missing",
        "call-prepare-c",
        "call-prepare-owned",
    ]
    record = dict(
        status="generated-not-qualified",
        source_files={
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [source / "tools/common/c_extract" / (n + ".py") for n in owners]
        },
        generated_sha256=hashlib.sha256(header.encode()).hexdigest(),
        logical_frame_bytes=80,
        maximum_depth=64,
        private_scratch_bytes=32,
        entries=[
            "JS_FrameVarargsForwardTry",
            "JS_FrameCallPrepareCommit",
            "JS_FrameCallForwardNativeCold",
            "JS_FrameCallForwardOwnedCold",
            "JS_FrameCallPrepareCold",
        ],
        scope="Shared C normalizer/prepared constructor and native leaf/owned/borrow/missing/deep producers;not whole native entry/root/publication coverage",
    )
    (output / "FORWARDING.json").write_text(json.dumps(record, indent=2) + "\n")
    return loop
