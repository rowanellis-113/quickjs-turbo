/* Native selector ABI and process-wide policy control. Included by the
 * source-bound string module before the platform-independent rope worker. */
#include <stdatomic.h>

#ifdef _MSC_VER
#pragma section(".qjsstmd", read, write)
__declspec(allocate(".qjsstmd")) _Atomic(unsigned char) JS_FrameConcatMode = 0;
__declspec(allocate(".qjsstmd")) _Atomic(unsigned char) JS_FrameLocalRopeMode = 0;
/* Reuse the byte-atomic leaves. The static merger must retain
 * this writable byte and must not pull a second CRT atomic COMDAT. */
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *, unsigned char *, unsigned char);
#else
__attribute__((section(".qjsem$strings"))) _Atomic(unsigned char) JS_FrameConcatMode = 0;
__attribute__((section(".qjsem$strings"))) _Atomic(unsigned char) JS_FrameLocalRopeMode = 0;
#endif

#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(JS_TAG_STRING == -7 && offsetof(JSMallocBlockHeader, user_data) -
                                              offsetof(JSMallocBlockHeader, ref_count) ==
                                          4,
               "review native flat-string selector after upstream change");
_Static_assert(sizeof(JSValue) == 16 && offsetof(JSString, hash_next) == 8,
               "selector uses the pinned native value and string header");
_Static_assert(JS_STRING_ROPE_SHORT_LEN == 512 && JS_STRING_ROPE_SHORT2_LEN == 8192,
               "selector follows the pinned original flat/short-leaf limits");
_Static_assert(sizeof(JSString) == 24 && sizeof(JSStringRope) == 40 &&
                   offsetof(JSStringRope, len) == 0 && offsetof(JSStringRope, depth) == 5 &&
                   offsetof(JSStringRope, left) == 8 && offsetof(JSStringRope, right) == 24 &&
                   offsetof(JSMallocFunctions, js_malloc_usable_size) ==
                       QJS_ABI_OFF_JSMallocFunctions_js_malloc_usable_size &&
                   JS_STRING_LEN_MAX == 1073741823 && JS_STRING_ROPE_MAX_DEPTH == 60 &&
                   JS_STRING_KIND_NORMAL == 0 && JS_TAG_UNDEFINED == 3,
               "native append lane private offsets and limits");
#else
_Static_assert(JS_TAG_STRING == -7 && sizeof(JSRefCountHeader) == 4,
               "review native flat-string selector after upstream change");
_Static_assert(sizeof(JSValue) == 16 && offsetof(JSString, header) == 0 &&
                   offsetof(JSString, hash_next) == 12,
               "selector uses the pinned native value and string header");
_Static_assert(JS_STRING_ROPE_SHORT_LEN == 512 && JS_STRING_ROPE_SHORT2_LEN == 8192,
               "selector follows the pinned original flat/short-leaf limits");
_Static_assert(sizeof(JSString) == 24 && offsetof(JSStringRope, header) == 0 &&
                   offsetof(JSStringRope, len) == 4 && offsetof(JSStringRope, depth) == 9 &&
                   offsetof(JSStringRope, left) == 16 && offsetof(JSStringRope, right) == 32 &&
                   offsetof(JSRuntime, mf) == 0 &&
                   offsetof(JSMallocFunctions, js_malloc_usable_size) == 32 &&
                   JS_STRING_LEN_MAX == 1073741823 && JS_STRING_ROPE_MAX_DEPTH == 60 &&
                   JS_STRING_KIND_NORMAL == 0 && JS_TAG_UNDEFINED == 3,
               "native append lane private offsets and limits");
#endif

static inline unsigned char js_frame_shared_concat_mode(void)
{
#ifdef _MSC_VER
    unsigned char mode = JS_FrameJSONLoad8((const unsigned char *)&JS_FrameConcatMode);
#else
    unsigned char mode = atomic_load_explicit(&JS_FrameConcatMode, memory_order_relaxed);
#endif
    if (unlikely(!mode)) {
        mode = getenv("QJS_DISABLE_CONCAT_ROPE") ? 2 : 1;
#ifdef _MSC_VER
        unsigned char expected = 0;
        if (!JS_FrameJSONCAS8((unsigned char *)&JS_FrameConcatMode, &expected, mode))
            mode = expected;
#else
        atomic_store_explicit(&JS_FrameConcatMode, mode, memory_order_relaxed);
#endif
    }
    return mode;
}

unsigned char JS_FrameLocalRopeModeGet(void)
{
#ifdef _MSC_VER
    unsigned char mode = JS_FrameJSONLoad8((const unsigned char *)&JS_FrameLocalRopeMode);
#else
    unsigned char mode = atomic_load_explicit(&JS_FrameLocalRopeMode, memory_order_relaxed);
#endif
    if (unlikely(!mode)) {
        mode = getenv("QJS_DISABLE_LOCAL_ROPE_APPEND") ? 2 : 1;
#if defined(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        /* Low bits retain root mode 1/2; mask0x10 opts into proven pool spare
           capacity. The native selector only tests the disabled value 2. */
        if (mode == 1 && !getenv("QJS_DISABLE_LOCAL_ROPE_SPARE"))
            mode |= 16;
#endif
        /* GNU-only native lane: retain the original legacy policy/code path.
           Presence, including value 0, disables only the new native lane. */
#if !defined(_MSC_VER) && defined(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        if ((mode & 3) == 1 && getenv("QJS_DISABLE_FRAME_NATIVE_ROPE_APPEND"))
            mode |= 32;
#endif
#ifdef _MSC_VER
        unsigned char expected = 0;
        if (!JS_FrameJSONCAS8((unsigned char *)&JS_FrameLocalRopeMode, &expected, mode))
            mode = expected;
#else
        atomic_store_explicit(&JS_FrameLocalRopeMode, mode, memory_order_relaxed);
#endif
    }
    return mode;
}
