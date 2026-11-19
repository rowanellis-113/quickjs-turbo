"""ARM64 prepared-callback adapter (zero foreign assembly or tokens)."""

from c_workers import replace_one
from prepared_callbacks import generate as shared_generate


def _adapt(source, runtime, selector):
    runtime = replace_one(
        runtime,
        "/* @QJS_MSC_INTRIN@ */",
        "",
        "remove optional foreign intrinsic include marker",
    )
    runtime = replace_one(
        runtime,
        "/* @QJS_CALLBACK_TLS_SP@ */",
        """CALLBACK_INLINE JSFrameCallbackHost *frame_callback_host(void)
{
    return *js_frame_shared_slot();
}
CALLBACK_INLINE uintptr_t frame_callback_sp(void)
{
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    return sp;
}""",
        "actual AAPCS64 callback host TLS and stack pointer",
    )
    runtime = replace_one(
        runtime,
        "extern _Atomic unsigned char JS_FrameCallbackControl, JS_FrameCallbackArityControl;",
        "extern _Atomic unsigned char JS_FrameCallbackControl, JS_FrameCallbackArityControl, JS_FrameCallbackWriteControl;",
        "typed callback control declarations",
    )
    for name in ("Control", "ArityControl", "WriteControl"):
        runtime = replace_one(
            runtime,
            f"QJS_CONTROL_SLOT_ADDR(p, JS_FrameCallback{name});",
            f"p = &JS_FrameCallback{name};",
            "compiler-managed callback control " + name,
        )
    for name in ("Every", "Reduce"):
        runtime = replace_one(
            runtime,
            f"QJS_CONTROL_SLOT_ADDR(loop, JS_FrameCallbackArray{name});",
            f"loop = JS_FrameCallbackArray{name};",
            "typed callback function " + name,
        )
    start = runtime.index("/* Keep recognized primitive ChildLeaf bytecode")
    end = runtime.index("extern JSValue JS_FramePreparedCallbackWriteSelect", start)
    runtime = runtime[:start] + runtime[end:]
    if runtime.count(" || frame_callback_may_have_leaf(b)") != 2:
        raise ValueError("Review primitive-leaf callback exclusion owners")
    runtime = runtime.replace(" || frame_callback_may_have_leaf(b)", "")
    substitutions = {
        "memcpy(call.state + 56, &ctx->rt, 8);": "call.native_state.rt = ctx->rt;",
        "memcpy(call.state + CALLBACK_CALLER, &ctx, 8);": "call.native_state.caller_ctx = ctx;",
        "memcpy(call.state + CALLBACK_SITES, (unsigned char *)host->state + CALLBACK_SITES, 8);": "call.native_state.sites = host->state->sites;",
        "memcpy(call.state + CALLBACK_NEXT, (unsigned char *)host->state + CALLBACK_NEXT, 8);": "call.native_state.cache_next = host->state->cache_next;",
        "call.state[CALLBACK_DIRECT] = host->state->direct_host_calls;": "call.native_state.direct_host_calls = host->state->direct_host_calls;",
        "memcpy(&host_rt, (unsigned char *)host->state + 56, 8);": "host_rt = host->state->rt;",
        "memcpy(&used, (unsigned char *)host->state + 32, 8);": "used = host->state->used_bytes;",
        "memcpy(&committed, (unsigned char *)host->state + CALLBACK_COMMITTED, 8);": "committed = host->state->committed_bytes;",
        "call.data + 128": "call.data + FRAME_HEADER_BYTES",
        "bytes = 128 +": "bytes = FRAME_HEADER_BYTES +",
        "        128 + sizeof(JSValue)": "        FRAME_HEADER_BYTES + sizeof(JSValue)",
        "(unsigned char *)barrier - 56": "(unsigned char *)barrier - offsetof(JSFrameCallbackScope,barrier)",
        "argc, argv, 2,": "argc, argv, JS_CALL_FLAG_COPY_ARGV,",
    }
    for old, new in substitutions.items():
        if old not in runtime:
            raise ValueError("Review actual-type callback owner: " + old)
        runtime = runtime.replace(old, new)
    selector = replace_one(
        selector,
        "    JS_FrameInterp(state);",
        "    JS_FrameAArch64Run(state);",
        "blocked ARM prepared VM",
    )
    selector += """
/* Actual target compiler geometry,checked in the linked ELF. */
__attribute__((used,section(".qjs.callback.abi"),aligned(8)))
static const uint64_t qjs_aarch64_callback_abi[]={
    sizeof(JSFrameCallbackScope),_Alignof(JSFrameCallbackScope),
    offsetof(JSFrameCallbackScope,barrier),offsetof(JSFrameCallbackScope,state),
    offsetof(JSFrameCallbackScope,data),sizeof(JSFrameRegisterState),sizeof(JSFrame)
};
"""
    return (
        runtime,
        selector,
        dict(
            entry="typed AAPCS64 C; same ARM register VM with blocked activation",
            architecture="aarch64",
            native_leaf_provider=False,
            private_struct_clones=False,
            object_patching=False,
        ),
    )


def generate(source, output, core, adapter):
    return shared_generate(source, output, core, adapter, arch_adapt=_adapt)
