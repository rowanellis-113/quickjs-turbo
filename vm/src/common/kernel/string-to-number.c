/* Short, complete decimal strings have an exact integer numerator and scale.
 * Keep all other grammars and rounding modes in the original converter.
 * This module never changes JS frames, heap representations, or ownership. */
#include <stdint.h>
#include <stddef.h>
#include "qjs-number-rounding.h"
#include "dtoa.h"

#if defined(_MSC_VER)
#define FRAME_ATOD_CODE __declspec(code_seg(".qjscold$zznullfast")) __declspec(noinline)
#else
#define FRAME_ATOD_CODE __attribute__((section(".qjsleaf$zzzatod"), noipa))
#endif

FRAME_ATOD_CODE double JS_FrameAtod(const char *str, const char **pnext, int radix, int flags,
                                    JSATODTempMem *tmp_mem)
{
    const char *p = str;
    uint64_t mantissa = 0, scale = 1;
    unsigned digits = 0, fractional = 0;
    int negative = 0, dot = 0;
    union {
        double d;
        uint64_t bits;
    } result;

    if ((radix != 0 && radix != 10) || (flags & ~JS_ATOD_INT_ONLY))
        goto slow;
    if (*p == '-' || *p == '+') {
        negative = (*p == '-');
        p++;
    }
    for (;;) {
        unsigned digit = (unsigned)(unsigned char)*p - '0';
        if (digit <= 9) {
            /* At most15 total digits: numerator <= 10^15-1, scale <= 10^15.
             * Both convert exactly to binary64 (each is below2^53). */
            if (++digits > 15)
                goto slow;
            mantissa = mantissa * 10 + digit;
            if (dot) {
                fractional++;
                scale *= 10;
            }
            p++;
        } else if (*p == '.' && !dot && !(flags & JS_ATOD_INT_ONLY)) {
            dot = 1;
            p++;
        } else {
            break;
        }
    }
    if (!digits || *p)
        goto slow;
    /* Integer conversion is exact. Fraction conversion is one IEEE division
     * of two exact operands, so default rounding gives the exact decimal's
     * correctly rounded binary64. Unusual host rounding retains the old path. */
    if (fractional && !qjs_number_atod_nearest())
        goto slow;
    result.d = (double)mantissa;
    if (fractional)
        result.d /= (double)scale;
    if (negative)
        result.bits |= UINT64_C(0x8000000000000000); /* Preserve negative zero. */
    if (pnext)
        *pnext = p;
    return result.d;
slow:
    return js_atod(str, pnext, radix, flags, tmp_mem);
}
