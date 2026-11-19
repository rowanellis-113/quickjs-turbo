/* Same-image controls and actual core types for the complete GNU comparisons. */
#include <stdatomic.h>
#define FRAME_CODE __attribute__((section(".text.qjs_linux_comparison"), noipa))
#define COMPARE_DATA __attribute__((section(".data.qjs_linux_comparison"), visibility("hidden")))
COMPARE_DATA _Atomic(unsigned char) JS_LinuxComparisonControl;
COMPARE_DATA _Atomic(unsigned) JS_FrameLooseEqMode;
extern int JS_LinuxStrictIdentityLeaf(JSContext *, JSValue *, bool)
    __attribute__((visibility("hidden")));

_Static_assert(sizeof(JSValue) == 16 && offsetof(JSValue, tag) == 8 && sizeof(JSString) == 24 &&
                   offsetof(JSStringSlice, parent) == 0 && offsetof(JSStringSlice, start) == 8 &&
                   offsetof(JSString, header.ref_count) == 0 && sizeof(_Atomic(unsigned)) == 4,
               "Compiler-measured inline reference and flat/slice/indirect string profile");
_Static_assert(JS_TAG_OBJECT == -1 && JS_TAG_STRING == -7 && JS_TAG_SYMBOL == -8 &&
                   JS_TAG_BIG_INT == -9 && JS_TAG_NULL == 2 && JS_TAG_UNDEFINED == 3 &&
                   JS_TAG_BOOL == 1 && JS_TAG_FLOAT64 == 8 && JS_TAG_SHORT_BIG_INT == 7,
               "Original comparison tag admission");

#define OWN_PRIVATE_ADDRESS(name) ((uintptr_t)&(name))
#include "src/common/call/reference-config.inc"
#undef OWN_PRIVATE_ADDRESS
FRAME_CODE int JS_LinuxComparisonInit(JSFrameRegisterState *state)
{
    (void)state;
    /* Both shared controls use only CRT environment and atomic scalar state. */
    frame_reference_configure();
    unsigned char expected = 0;
    unsigned char mode = getenv("QJS_DISABLE_LINUX_COMPARISONS") ? 2 : 1;
    if (getenv("QJS_DISABLE_LINUX_STRICT_COMPARE"))
        mode |= 4;
    if (getenv("QJS_DISABLE_LINUX_LOOSE_COMPARE"))
        mode |= 8;
    if (getenv("QJS_DISABLE_LINUX_C_IDENTITY"))
        mode |= 16;
    atomic_compare_exchange_strong_explicit(&JS_LinuxComparisonControl, &expected, mode,
                                            memory_order_release, memory_order_relaxed);
    return 1;
}
static inline unsigned js_linux_comparison_mode(void)
{
    unsigned mode = atomic_load_explicit(&JS_LinuxComparisonControl, memory_order_acquire);
    if (!mode) {
        JS_LinuxComparisonInit(NULL);
        mode = atomic_load_explicit(&JS_LinuxComparisonControl, memory_order_acquire);
    }
    return mode;
}
/* The only assembly-to-C fallthrough has the actual original three arguments. */
FRAME_CODE int JS_LinuxStrictIdentityFallback(JSContext *ctx, JSValue *sp, bool is_neq)
{
    return js_strict_eq_slow(ctx, sp, is_neq);
}
FRAME_CODE int JS_LinuxStrictIdentitySlow(JSContext *ctx, JSValue *sp, bool is_neq)
{
    if (js_linux_comparison_mode() & (2 | 16))
        return js_strict_eq_slow(ctx, sp, is_neq);
    return JS_LinuxStrictIdentityLeaf(ctx, sp, is_neq);
}
#undef COMPARE_DATA
