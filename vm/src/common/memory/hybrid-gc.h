/* Hybrid Reference Counting + Generational Partial Mark-Sweep + Fast Synchronous RC.
 * Private to core compilation; public API and original ABI offsets are preserved. */
#ifndef QJS_HYBRID_GC_H
#define QJS_HYBRID_GC_H

#define JS_HYBRID_MODE_PARTIAL 1u
#define JS_HYBRID_MODE_FAST_RC 2u

_Static_assert(JS_CLASS_OBJECT == 1 && JS_CLASS_ARRAY == 2,
               "fast RC and array helpers rely on contiguous object/array class ids");
_Static_assert(offsetof(JSMallocBlockHeader, user_data) == 8 &&
                   offsetof(JSHybridGCBoundary, node) == offsetof(JSMallocBlockHeader, user_data) &&
                   _Alignof(JSHybridGCBoundary) >= _Alignof(JSMallocBlockHeader),
               "hybrid GC boundary node must keep ISO C11 prefix header alignment");

#ifdef ENABLE_DUMPS // JS_DUMP_FREE
#define js_hybrid_dump_free_enabled(rt) check_dump_flag((rt), JS_DUMP_FREE)
#else
#define js_hybrid_dump_free_enabled(rt) 0
#endif

static void js_hybrid_gc_init(JSRuntime *rt, const JSMallocFunctions *mf);
static void js_hybrid_on_free_runtime(JSRuntime *rt);
static void js_hybrid_unlink_boundary(JSRuntime *rt);
static void js_hybrid_run_full_gc(JSRuntime *rt);
static no_inline void js_hybrid_trigger_gc_slow(JSRuntime *rt);
static no_inline void js_hybrid_free_object_root(JSRuntime *rt, JSGCObjectHeader *root);
void js_hybrid_drop_string1(JSRuntime *rt, void *ptr, uint32_t is_rope);

#endif
