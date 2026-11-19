/* Original public720-case ABI workload,passive actual-entry/CFI observation. */
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdlib.h>
struct JSFrameRegisterState;
extern JSValue JS_FrameAArch64GenericInvoke(struct JSFrameRegisterState *, JSValue *, int, bool);
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
static uintptr_t generic_end, gate_start, gate_end, step_start, step_end;
static uint64_t native_gc, gate_frames, native_step;
static void observe_gc(JSRuntime *);
#define main original_c_invoke_main
#define JS_RunGC observe_gc
#include "../common/linux/native_linux_c_invoke.c"
#undef JS_RunGC
#undef main
static void observe_gc(JSRuntime *rt)
{
    void *frames[64];
    int count = backtrace(frames, 64), native = 0, vm = 0, step = 0, gate = 0;
    for (int i = 0; i < count; i++) {
        uintptr_t ip = (uintptr_t)frames[i];
        native |= ip > (uintptr_t)JS_FrameAArch64GenericInvoke && ip < generic_end;
        vm += ip > (uintptr_t)JS_FrameInterp && ip < (uintptr_t)qjs_aarch64_vm_end;
        gate |= ip > gate_start && ip < gate_end;
        step |= ip > step_start && ip < step_end;
    }
    if (native) {
        assert(vm == 1);
        ++native_gc;
        gate_frames += gate;
        native_step += step;
    }
    JS_RunGC(rt);
}
int main(int argc, char **argv)
{
    assert(argc == 6);
    generic_end = (uintptr_t)JS_FrameAArch64GenericInvoke + strtoull(argv[1], NULL, 10);
    gate_start = (uintptr_t)JS_FrameAArch64GenericInvoke + strtoll(argv[2], NULL, 10);
    gate_end = gate_start + strtoull(argv[3], NULL, 10);
    step_start = (uintptr_t)JS_FrameAArch64GenericInvoke + strtoll(argv[4], NULL, 10);
    step_end = step_start + strtoull(argv[5], NULL, 10);
    int result = original_c_invoke_main();
    assert(!result);
    uint64_t counts[8];
    qjs_aarch64_vm_c_entry_counts(counts);
    int enabled = !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_SHARED_ENTRY") &&
                  !getenv("QJS_DISABLE_DIRECT_HOST_CALL") && !getenv("QJS_RETAIN_SCOPED_HOST") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    assert(!gate_frames && !native_step && native_gc == counts[0]);
    if (enabled)
        assert(native_gc);
    else
        assert(!native_gc);
    printf("AARCH64_C_INVOKE_UNWIND_OK native_gc=%llu no_gate=%llu no_step=%llu\n",
           (unsigned long long)native_gc, (unsigned long long)gate_frames,
           (unsigned long long)native_step);
    return 0;
}
