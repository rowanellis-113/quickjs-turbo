/* Test-only read-only adapter through the existing typed shared-scope reader.
 * Every private offset below comes from THIS ARM compiler's emitted values.
 */
#include <quickjs.h>
#include <stdint.h>
#include <string.h>
#include "interpreter-aarch64-values.h"
extern unsigned JS_FrameAArch64ScopeProbe(JSRuntime *, uintptr_t *);
static uintptr_t word(uintptr_t p, size_t n)
{
    uintptr_t v;
    memcpy(&v, (void *)(p + n), 8);
    return v;
}
static unsigned half(uintptr_t p, size_t n)
{
    uint16_t v;
    memcpy(&v, (void *)(p + n), 2);
    return v;
}
static unsigned byte(uintptr_t p, size_t n)
{
    uint8_t v;
    memcpy(&v, (void *)(p + n), 1);
    return v;
}
int JS_LinuxJSFrameProbe(JSRuntime *rt, uintptr_t *out)
{
    uintptr_t w[9];
    if (JS_FrameAArch64ScopeProbe(rt, w) != 1 || !w[3])
        return 0;
    uintptr_t f = w[3], b = word(f, ARM_OFF_JSFrame_bytecode);
    if ((int64_t)word(f, ARM_OFF_JSStackFrame_cur_func + 8) != -1)
        return 0;
    out[0] = word(f, ARM_OFF_JSStackFrame_arg_buf);
    out[1] = f + ARM_FRAME_HEADER_BYTES;
    out[2] = half(f, ARM_OFF_JSFrame_owned_args);
    out[3] = half(f, ARM_OFF_JSStackFrame_arg_count);
    out[4] = half(f, ARM_OFF_JSStackFrame_var_ref_count);
    out[5] = byte(b, ARM_FRAME_KIND_OFFSET);
    out[6] = w[1];
    out[7] = w[2];
    out[8] = word(f, ARM_OFF_JSStackFrame_cur_func);
    out[9] = byte(f, ARM_FRAME_ROOT_OFFSET);
    return 1;
}
