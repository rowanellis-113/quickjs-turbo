"""Pure-C null-prototype arena allocator extractor."""

import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import source_file as _frame_source_file


def inline_header_body(source, hashes, initialize):
    """Specialize the actual 0.15 constructor while retaining its allocator/GC."""
    from common.c_extract import object_adapter_c as adapter

    functions = {
        match[2]: match[0]
        for match in adapter.FUNCTION.finditer(
            _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
        )
    }
    trigger = functions["js_trigger_gc"].replace(
        "static void js_trigger_gc(", "static FRAME_NULL_INLINE void frame_null_trigger_gc(", 1
    )
    release = functions["js_free_shape"].replace(
        "static void js_free_shape(", "static FRAME_NULL_INLINE void frame_null_release_shape(", 1
    )
    assert trigger.count("frame_null_trigger_gc(") == 1
    assert release.count("js_free_shape0(") == 1
    release = release.replace("js_free_shape0(", "qjs_frame_core_js_free_shape0(")
    link = functions["add_gc_object"].replace(
        "static void add_gc_object(", "static FRAME_NULL_INLINE void frame_null_add_gc_object(", 1
    )
    assert link.count("frame_null_add_gc_object(") == 1
    hashes = hashes.replace("shape_initial_hash(", "frame_null_shape_initial_hash(")
    return (
        """
/* Inline-header upstreams have no small-block arenas. Keep the warm null-shape
 * specialization, and fuse the ordinary-object constructor with its actual
 * malloc/GC protocol. There is no new allocation representation or free list. */
extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);
_Static_assert(QJS_ABI_HAS_PREFIX_RC == 0 && QJS_ABI_REF_COUNT_OFFSET == 0,
               "inline-header object/shape ownership");
_Static_assert(offsetof(JSRuntime,module_loader_has_attr)+6<offsetof(JSRuntime,u),
               "warm allocation control uses measured runtime padding");
"""
        + hashes
        + "\n"
        + trigger
        + "\n"
        + release
        + "\n"
        + link
        + """
FRAME_NULL_CODE JSValue JS_FrameNewNullObject(JSContext *ctx, JSValueConst proto_val, JSClassID class_id)
{
    JSRuntime *rt=ctx->rt;
    JSShape *sh;
    JSObject *p;
    uint32_t hash;
    if(class_id!=JS_CLASS_OBJECT || !JS_IsNull(proto_val) ||
       ((unsigned char *)rt)[offsetof(JSRuntime,module_loader_has_attr)+6] ||
       rt->in_free || rt->gc_phase!=JS_GC_PHASE_NONE)
        return JS_NewObjectProtoClass(ctx,proto_val,class_id);
    hash=frame_null_shape_initial_hash(NULL);
    for(sh=rt->shape_hash[hash>>(32-rt->shape_hash_bits)];sh;sh=sh->shape_hash_next)
        if(sh->hash==hash && sh->proto==NULL && sh->prop_count==0)
            break;
    if(!sh || sh->prop_size!=JS_PROP_INITIAL_SIZE)
        return JS_NewObjectProtoClass(ctx,proto_val,class_id);
    /* The original prototype constructor duplicates this owner BEFORE the
     * trigger or allocator can run GC/reenter. Every failure consumes it. */
    JS_REF_COUNT(sh)++;
    frame_null_trigger_gc(rt,sizeof(JSObject));
    p=js_malloc(ctx,sizeof(JSObject));
    if(unlikely(!p)) {
        frame_null_release_shape(rt,sh);
        return JS_EXCEPTION;
    }
"""
        + initialize
        + """    p->prop=js_malloc(ctx,sizeof(JSProperty)*sh->prop_size);
    if(unlikely(!p->prop)) {
        js_free(ctx,p);
        frame_null_release_shape(rt,sh);
        return JS_EXCEPTION;
    }
    /* Exact ordinary-object case: no properties are live yet. Publish the
     * complete object to the GC list only after both allocations succeed. */
    p->header.ref_count=1;
    frame_null_add_gc_object(rt,&p->header,JS_GC_OBJ_TYPE_JS_OBJECT);
    return JS_MKPTR(JS_TAG_OBJECT,p);
}
"""
    )


def generate_body(source, *, reference_count_model="inline-header"):
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    start = text.index("static uint32_t shape_hash(uint32_t h, uint32_t val)")
    end = text.index("\nstatic int resize_shape_hash", start)
    hashes = text[start:end]
    assert hashes.count("shape_initial_hash(JSObject *proto)") == 1
    hashes = hashes.replace("shape_hash", "frame_null_shape_hash").replace(
        "static uint32_t", "static FRAME_NULL_INLINE uint32_t"
    )
    constructor = text.index(
        "static JSValue JS_NewObjectFromShape(JSContext *ctx, JSShape *sh, JSClassID class_id,\n                                     JSProperty *props)\n{"
    )
    begin = text.index("    p->class_id = class_id;", constructor)
    end = text.index("    p->prop = js_malloc(", begin)
    initialize = text[begin:end]
    assert (
        initialize.count("p->shape = sh;") == 1
        and initialize.count("p->first_weak_ref = NULL;") == 1
    )
    if reference_count_model == "inline-header":
        return inline_header_body(source, hashes, initialize)
    return (
        """
/* Only the native NULL_PROTO opcode calls this helper. Its compiler ABI is
   identical to JS_NewObjectProtoClass (matching the target platform aggregate C ABI).
   Runtime byte1366 is unused original padding: zero enables this fast path.
   Never commit an allocation before every guard succeeds. */
_Static_assert(offsetof(JSRuntime,module_loader_has_attr)==1360 && offsetof(JSRuntime,u)==1368, "null arena switch1366 remains original padding");
_Static_assert(JS_ARENA_ALIGN==8 && sizeof(JSMallocBlockHeader)==8, "original arena prefix");
_Static_assert(sizeof(JSObject)>=16 && sizeof(JSObject)+8<=128, "object stays in exact eight-byte size classes");
_Static_assert(sizeof(JSProperty)*JS_PROP_INITIAL_SIZE>=16 && sizeof(JSProperty)*JS_PROP_INITIAL_SIZE+8<=128, "properties stay in exact eight-byte size classes");
"""
        + hashes
        + """
static FRAME_NULL_INLINE void *frame_null_take(JSArena *ar, unsigned block_size)
{
    unsigned index=ar->first_free_block;
    JSMallocBlockHeader *b=(JSMallocBlockHeader *)(ar->blocks+(size_t)index*block_size);
    ar->first_free_block=b->u.free_next;
    b->u.block_idx=index;
    ar->n_used_blocks++;
    return b->user_data;
}

FRAME_NULL_CODE JSValue JS_FrameNewNullObject(JSContext *ctx, JSValueConst proto_val, JSClassID class_id)
{
#if !JS_ARENA_LARGE_BLOCKS_ONLY
    enum { OB=((sizeof(JSObject)+7)&~7)+8,
           PB=((sizeof(JSProperty)*JS_PROP_INITIAL_SIZE+7)&~7)+8,
           OI=OB/8-2, PI=PB/8-2 };
    JSRuntime *rt=ctx->rt;
    JSShape *sh;
    JSObject *p;
    JSProperty *props;
    JSArena *oa,*pa;
    struct list_head *oh,*ph;
    size_t used,limit,budget;
    uint32_t hash;
    if (class_id!=JS_CLASS_OBJECT || !JS_IsNull(proto_val) ||
        ((unsigned char *)rt)[1366] || rt->gc_phase!=JS_GC_PHASE_NONE)
        goto slow;
    used=rt->malloc_state.malloc_size;
    /* Original constructor triggers GC before the object allocation. */
    if (used>rt->malloc_gc_threshold ||
        sizeof(JSObject)>rt->malloc_gc_threshold-used)
        goto slow;
    budget=(OB-8)+(PB-8)+2*MALLOC_OVERHEAD;
    limit=rt->malloc_state.malloc_limit-1; /* zero is unlimited */
    if (used>limit || budget>limit-used)
        goto slow;
    hash=frame_null_shape_hash(frame_null_shape_hash(1,0),0);
    for (sh=rt->shape_hash[hash>>(32-rt->shape_hash_bits)];sh;sh=sh->shape_hash_next) {
        if (sh->hash==hash && sh->proto==NULL && sh->prop_count==0)
            break;
    }
    if (!sh || sh->prop_size!=JS_PROP_INITIAL_SIZE)
        goto slow;
    oh=&rt->arena_state.free_arena_list[OI];
    ph=&rt->arena_state.free_arena_list[PI];
    if (oh->next==oh || ph->next==ph)
        goto slow;
    oa=list_entry(oh->next,JSArena,free_link);
    pa=list_entry(ph->next,JSArena,free_link);
    /* Leave at least one free cell, so no free-list removal is needed.
       The same-arena case reserves both cells before either is committed. */
    if (oa==pa) {
        if ((unsigned)oa->n_used_blocks+2>=oa->n_blocks)
            goto slow;
    } else if ((unsigned)oa->n_used_blocks+1>=oa->n_blocks ||
               (unsigned)pa->n_used_blocks+1>=pa->n_blocks) {
        goto slow;
    }
    /* No GC, native callback, allocation failure or reentry after this point. */
    JS_REF_COUNT(sh)++;
    p=frame_null_take(oa,OB);
    props=frame_null_take(pa,PB);
    rt->malloc_state.malloc_count+=2;
    rt->malloc_state.malloc_size+=budget;
"""
        + initialize
        + """    p->prop=props;
    JS_REF_COUNT(p)=1;
    JS_GC_MARK(p)=0;
    JS_GC_TYPE(p)=JS_GC_OBJ_TYPE_JS_OBJECT;
    list_add_tail(&p->header.link,&rt->gc_obj_list);
    return JS_MKPTR(JS_TAG_OBJECT,p);
slow:
#endif
    /* GC, sanitizer/stress allocation, arena refill/full, memory limit, cold
       shape and unsupported class/prototype retain the complete old path. */
    return JS_NewObjectProtoClass(ctx,proto_val,class_id);
}
"""
    )
