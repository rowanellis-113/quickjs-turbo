/* Internal inline fast paths for JS_FreeValue / set_value, scoped strictly to
 * hot interpreter loops (JS_LegacyCallInternal / JS_CVMResumeInternal) so cold
 * functions across quickjs.c stay compact and never exhaust compiler inline budgets. */
#if defined(QJS_FREE_INLINE_UNDEF)
#undef JS_FreeValue
#undef set_value
#undef QJS_FREE_INLINE_UNDEF
#elif defined(QJS_FREE_INLINE_DEF)
#define JS_FreeValue(ctx, v) js_free_val_inline((ctx), (v))
#define set_value(ctx, pval, new_val) js_set_val_inline((ctx), (pval), (new_val))
#undef QJS_FREE_INLINE_DEF
#else
#if defined(_MSC_VER)
#define QJS_FREE_INLINE static __forceinline
#elif defined(__GNUC__) || defined(__clang__)
#define QJS_FREE_INLINE static inline __attribute__((always_inline))
#else
#define QJS_FREE_INLINE static inline
#endif

QJS_FREE_INLINE void js_free_val_rt_inline(JSRuntime *rt, JSValue v)
{
    if (JS_VALUE_HAS_REF_COUNT(v)) {
        void *p = JS_VALUE_GET_PTR(v);
        if (unlikely(--JS_REF_COUNT(p) <= 0))
            js_free_value_rt(rt, v);
    }
}

QJS_FREE_INLINE void js_free_val_inline(JSContext *ctx, JSValue v)
{
    js_free_val_rt_inline(ctx->rt, v);
}

QJS_FREE_INLINE void js_set_val_inline(JSContext *ctx, JSValue *pval, JSValue new_val)
{
    JSValue old_val = *pval;
    *pval = new_val;
    js_free_val_rt_inline(ctx->rt, old_val);
}
#endif
