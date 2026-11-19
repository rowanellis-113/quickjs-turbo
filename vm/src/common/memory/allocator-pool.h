/* Experimental allocator ablation. Public allocator ABI only; no engine layout changes. */
#ifndef QJS_FRAME_POOL_H
#define QJS_FRAME_POOL_H
#include "quickjs.h"
#include <stddef.h>
#include <stdint.h>
typedef struct FramePool FramePool;
typedef struct FramePoolStats {
    size_t live_blocks, live_capacity, pages, retained_bytes;
    size_t peak_live_capacity, peak_retained_bytes, allocations, backing_allocations;
} FramePoolStats;
enum { FRAME_POOL_TRACK = 1 };
FramePool *FramePoolCreate(unsigned small_limit, unsigned flags);
/* Fails without freeing anything while allocations remain live. */
int FramePoolDestroy(FramePool *pool);
void FramePoolGetStats(const FramePool *pool, FramePoolStats *stats);
extern const JSMallocFunctions FramePoolFunctions;
JSRuntime *FrameExperiment_NewRuntime(void);
JSRuntime *FramePool_NewRuntime(const JSMallocFunctions *fallback, void *opaque);
#endif
