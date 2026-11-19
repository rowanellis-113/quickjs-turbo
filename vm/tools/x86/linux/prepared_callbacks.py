"""x86-64 Linux prepared callback adapter."""

from c_workers import replace_one
from common.elf.prepared_callbacks import generate as shared_generate


def _adapt(source, runtime, selector):
    runtime = replace_one(
        runtime,
        "/* @QJS_MSC_INTRIN@ */",
        "#include <intrin.h>",
        "restore optional compiler intrinsic marker",
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
    __asm__ volatile("movq %%rsp,%0" : "=r"(sp));
    return sp;
}""",
        "actual SysV callback host TLS and RSP",
    )
    for name in ("Control", "ArityControl", "WriteControl"):
        runtime = replace_one(
            runtime,
            f"QJS_CONTROL_SLOT_ADDR(p, JS_FrameCallback{name});",
            f'__asm__("leaq JS_FrameCallback{name}(%%rip),%0" : "=r"(p));',
            "x86 RIP-relative callback control " + name,
        )
    for name in ("Every", "Reduce"):
        runtime = replace_one(
            runtime,
            f"QJS_CONTROL_SLOT_ADDR(loop, JS_FrameCallbackArray{name});",
            f'__asm__("leaq JS_FrameCallbackArray{name}(%%rip),%0" : "=r"(loop));',
            "x86 RIP-relative callback function " + name,
        )
    return (
        runtime,
        '#include "src/x86/linux/interpreter-prepared-callback.inc"\n',
        dict(entry="typed SysV C; same register VM"),
    )


def generate(source, output, core, adapter):
    return shared_generate(source, output, core, adapter, arch_adapt=_adapt)
