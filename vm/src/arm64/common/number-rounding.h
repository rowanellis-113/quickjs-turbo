/* Linux/glibc exposes the actual AArch64 FPCR Rmode representation. MIT. */
#ifndef QJS_AARCH64_NUMBER_ROUNDING_H
#define QJS_AARCH64_NUMBER_ROUNDING_H
#if !defined(__aarch64__) || !defined(__linux__)
#error AArch64 Linux FPCR binding required
#endif
#include <fenv.h>
#include <stdint.h>
_Static_assert(FE_TONEAREST == 0, "actual glibc nearest representation");
static inline int qjs_aarch64_atod_nearest(void)
{
    uint64_t fpcr;
    __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
    return (fpcr & (FE_UPWARD | FE_DOWNWARD | FE_TOWARDZERO)) == FE_TONEAREST;
}
#endif
