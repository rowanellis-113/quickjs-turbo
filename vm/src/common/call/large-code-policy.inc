/* Shared cold policy for the source-generated long validator. No VM fields,
 * allocation,callback or GC. Check native stack before entering its bitmap TU.
 * Ordinary <=4096 eligibility and2048 tail-hint capacities remain unchanged.
 */
enum {
    FRAME_LARGE_CODE_MAX = 65536,
    FRAME_LARGE_BITMAP_BYTES = (FRAME_LARGE_CODE_MAX + 7) / 8,
    FRAME_LARGE_STACK_GUARD = FRAME_LARGE_BITMAP_BYTES + 4096
};
#if defined(_MSC_VER)
#define FRAME_LARGE_CODE __declspec(code_seg(".qjslng")) no_inline
#elif defined(QJS_INTERP_FRAME_LINUX)
#define FRAME_LARGE_CODE __attribute__((section(".text.qjs_frame_large"), noipa))
#else
#define FRAME_LARGE_CODE __attribute__((section(".qjslng"), noipa))
#endif
static FRAME_LARGE_CODE bool JS_FrameLongValidate(JSFunctionBytecode *b);
static FRAME_LARGE_CODE bool js_frame_large_select(JSFunctionBytecode *b)
{
    if (b->byte_code_len <= 4096 || b->byte_code_len > FRAME_LARGE_CODE_MAX ||
        getenv("QJS_DISABLE_FRAME_LARGE_CODE") != NULL ||
        getenv("QJS_DISABLE_FRAME_LONG_CODE") != NULL ||
        js_check_stack_overflow(b->realm->rt, FRAME_LARGE_STACK_GUARD))
        return false;
    /* Backend policy is measured per compiler. Explicit disable wins;
     * presence including0 opts in when the backend defaults to OFF. */
    if (!FRAME_LARGE_CODE_DEFAULT && getenv("QJS_ENABLE_FRAME_LARGE_CODE") == NULL)
        return false;
    return JS_FrameLongValidate(b);
}
