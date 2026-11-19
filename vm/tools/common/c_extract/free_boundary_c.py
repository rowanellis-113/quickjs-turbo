"""Shared BigInt release backend C source."""

BIGINT_RELEASE_BACKEND = r"""
#include <stdatomic.h>
#ifdef _MSC_VER
#define RELEASE_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
extern unsigned char JS_FrameBigIntReleaseControl;
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);
#define RELEASE_LOAD() JS_FrameJSONLoad8(&JS_FrameBigIntReleaseControl)
#define RELEASE_CAS(p,v) JS_FrameJSONCAS8(&JS_FrameBigIntReleaseControl,p,v)
#else
#define RELEASE_CODE __attribute__((section(".qjssrc$C"),noipa))
static _Atomic unsigned char JS_FrameBigIntReleaseControl __attribute__((section(".qjssrm"),used));
#define RELEASE_LOAD() atomic_load_explicit(&JS_FrameBigIntReleaseControl,memory_order_relaxed)
#define RELEASE_CAS(p,v) atomic_compare_exchange_strong_explicit(&JS_FrameBigIntReleaseControl,p,v,memory_order_relaxed,memory_order_relaxed)
#endif
/* First invocation and the disabled path preserve the entire original release. */
RELEASE_CODE void JS_FrameBigIntReleaseSlow(JSContext *ctx,JSValue value)
{
    if (!RELEASE_LOAD()) {
        unsigned char expected=0;
        unsigned char mode=getenv("QJS_DISABLE_BIGINT_RELEASE")?2:1;
        (void)RELEASE_CAS(&expected,mode);
    }
    JS_FreeValue(ctx,value);
}
/* Readonly qualification entry; no counters, roots or per-runtime ownership. */
RELEASE_CODE unsigned JS_FrameBigIntReleaseState(void)
{
    return RELEASE_LOAD();
}
"""
