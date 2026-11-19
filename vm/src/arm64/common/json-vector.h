/* Typed AdvSIMD operations for the shared bounded JSON algorithms. MIT. */
#ifndef QJS_AARCH64_JSON_VECTOR_H
#define QJS_AARCH64_JSON_VECTOR_H
#if !defined(__aarch64__) || !defined(__ARM_NEON) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error AArch64 little-endian AdvSIMD is required for this JSON profile
#endif
#include <arm_neon.h>
#include <stdint.h>
#ifdef QJS_AARCH64_VM_INSTRUMENT
void qjs_aarch64_json_vector_loaded(void);
void qjs_aarch64_json_vector_stored(void);
#endif
typedef uint8x16_t QJSJSONVector;
#define QJS_JSON_VECTOR_INLINE static inline __attribute__((always_inline))
_Static_assert(sizeof(QJSJSONVector) == 16 && _Alignof(QJSJSONVector) == 16,
               "Actual ARM JSON vector");
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_zero(void)
{
    return vdupq_n_u8(0);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_splat8(int v)
{
    return vdupq_n_u8((uint8_t)v);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_splat16(int v)
{
    return vreinterpretq_u8_u16(vdupq_n_u16((uint16_t)v));
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_load(const void *p)
{
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_json_vector_loaded();
#endif
    return vld1q_u8((const uint8_t *)p);
}
QJS_JSON_VECTOR_INLINE void qjs_json_vec_store(void *p, QJSJSONVector v)
{
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_json_vector_stored();
#endif
    vst1q_u8((uint8_t *)p, v);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_or(QJSJSONVector a, QJSJSONVector b)
{
    return vorrq_u8(a, b);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_and(QJSJSONVector a, QJSJSONVector b)
{
    return vandq_u8(a, b);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_eq8(QJSJSONVector a, QJSJSONVector b)
{
    return vceqq_u8(a, b);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_eq16(QJSJSONVector a, QJSJSONVector b)
{
    return vreinterpretq_u8_u16(vceqq_u16(vreinterpretq_u16_u8(a), vreinterpretq_u16_u8(b)));
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_subsat8(QJSJSONVector a, QJSJSONVector b)
{
    return vqsubq_u8(a, b);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_subsat16(QJSJSONVector a, QJSJSONVector b)
{
    return vreinterpretq_u8_u16(vqsubq_u16(vreinterpretq_u16_u8(a), vreinterpretq_u16_u8(b)));
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_sub16(QJSJSONVector a, QJSJSONVector b)
{
    return vreinterpretq_u8_u16(vsubq_u16(vreinterpretq_u16_u8(a), vreinterpretq_u16_u8(b)));
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_interleave_low(QJSJSONVector a, QJSJSONVector b)
{
    return vzip1q_u8(a, b);
}
QJS_JSON_VECTOR_INLINE QJSJSONVector qjs_json_vec_interleave_high(QJSJSONVector a, QJSJSONVector b)
{
    return vzip2q_u8(a, b);
}
QJS_JSON_VECTOR_INLINE unsigned qjs_json_vec_sign_mask(QJSJSONVector v)
{
    const uint8x16_t weights = {1, 2, 4, 8, 16, 32, 64, 128, 1, 2, 4, 8, 16, 32, 64, 128};
    uint8x16_t packed = vmulq_u8(vshrq_n_u8(v, 7), weights);
    return (unsigned)vaddv_u8(vget_low_u8(packed)) |
           ((unsigned)vaddv_u8(vget_high_u8(packed)) << 8);
}
#undef QJS_JSON_VECTOR_INLINE
#endif
