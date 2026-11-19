#ifdef NDEBUG
#undef NDEBUG
#endif
/* Inspect actual published arena frames across C callbacks and new roots. */
/* The engine is built with NDEBUG. Match its private ENABLE_DUMPS-dependent
 * runtime type, then reenable assertions in the fixture itself. */
#define NDEBUG
#include "quickjs-interpreter-private.h"
#undef NDEBUG
#include <assert.h>

_Static_assert(sizeof(JSRuntime) == 1488 && offsetof(JSRuntime, current_stack_frame) == 1264,
               "fixture must use the release engine's private runtime type");

typedef struct CompactSegment {
    struct CompactSegment *next;
    size_t capacity, used;
    uint8_t *data;
} CompactSegment;
typedef struct CompactFrame {
    JSStackFrame sf;
    JSFunctionBytecode *bytecode;
    JSValue this_value;
    JSValue *saved_sp;
    CompactSegment *segment;
    uint32_t frame_bytes;
    uint16_t owned_args, pending;
} CompactFrame;
_Static_assert(sizeof(CompactFrame) == 128 && offsetof(CompactFrame, bytecode) == 80 &&
                   offsetof(CompactFrame, frame_bytes) == 120 &&
                   offsetof(CompactFrame, pending) == 126,
               "compact private frame field contract");
_Static_assert(sizeof(JSStackFrame) == 80 && offsetof(JSStackFrame, is_constructor) == 61 &&
                   sizeof(bool) == 1 && offsetof(JSStackFrame, cur_sp) == 64,
               "root marker is padding byte 62 in original C type");
static unsigned probes, checked, foreign_roots, tail_parents, max_depth;
static int nested, enabled, inspect_scope;
static JSValue reentry;

static void inspect(JSRuntime *rt)
{
    if (!enabled || !inspect_scope)
        return;
    JSStackFrame *host = rt->current_stack_frame;
    assert(host && JS_VALUE_GET_TAG(host->cur_func) == JS_TAG_OBJECT &&
           JS_VALUE_GET_OBJ(host->cur_func)->class_id == JS_CLASS_C_FUNCTION);
    JSStackFrame *sf = host->prev_frame;
    unsigned depth = 0;
    assert(sf);
    for (;;) {
        CompactFrame *f = (CompactFrame *)sf;
        unsigned root = ((unsigned char *)sf)[62];
        assert(root <= 1);
        assert(JS_VALUE_GET_TAG(sf->cur_func) == JS_TAG_OBJECT);
        JSObject *function = JS_VALUE_GET_OBJ(sf->cur_func);
        assert(function->class_id == JS_CLASS_BYTECODE_FUNCTION);
        assert(f->bytecode == function->u.func.function_bytecode);
        assert(f->frame_bytes >= 128 && f->frame_bytes < 16384 && f->owned_args <= 128);
        size_t offset = (uint8_t *)sf->var_buf - (uint8_t *)f;
        assert(offset >= 128 && offset <= 128 + 16 * 128 && !(offset & 15));
        assert(f->owned_args <= (offset - 128) / 16);
        assert(f->segment && (uint8_t *)f >= f->segment->data);
        size_t mark = (uint8_t *)f - f->segment->data;
        assert(mark + f->frame_bytes <= f->segment->used &&
               f->segment->used <= f->segment->capacity);
        assert((f->pending & 0x7fff) > 0 && (f->pending & 0x7fff) <= 256);
        assert(f->saved_sp >= sf->var_buf + f->bytecode->var_count);
        if (f->pending & 0x8000)
            tail_parents++;
        checked++;
        assert(++depth < 1024);
        if (root) {
            if (sf->prev_frame)
                foreign_roots++;
            break;
        }
        sf = sf->prev_frame;
        assert(sf);
    }
    if (depth > max_depth)
        max_depth = depth;
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    JSStackFrame *outer = rt->current_stack_frame;
    int32_t value = 0;
    assert(argc == 1 && !JS_ToInt32(ctx, &value, argv[0]));
    probes++;
    inspect(rt);
    JS_RunGC(rt);
    assert(rt->current_stack_frame == outer);
    inspect(rt);
    if (!nested) {
        int saved_scope = inspect_scope;
        inspect_scope = 1;
        nested = 1;
        JSValue argument = JS_NewInt32(ctx, 5);
        JSValue result = JS_Call(ctx, reentry, JS_UNDEFINED, 1, (JSValueConst *)&argument);
        int32_t n = 0;
        assert(!JS_IsException(result) && !JS_ToInt32(ctx, &n, result) && n == 7);
        JS_FreeValue(ctx, result);
        nested = 0;
        inspect_scope = saved_scope;
        assert(rt->current_stack_frame == outer);
        inspect(rt);
    }
    return JS_NewInt32(ctx, value);
}
static void padding_probe(void)
{
    volatile JSStackFrame sf;
    memset((void *)&sf, 0xa5, sizeof(sf));
    sf.prev_frame = NULL;
    sf.cur_func = JS_UNDEFINED;
    sf.arg_buf = NULL;
    sf.var_buf = NULL;
    sf.var_refs = NULL;
    sf.cur_pc = NULL;
    sf.var_ref_count = 128;
    sf.arg_count = 128;
    sf.is_strict_mode = true;
    sf.is_constructor = false;
    sf.cur_sp = NULL;
    sf.cur_gc_obj = NULL;
    const volatile unsigned char *raw = (const volatile unsigned char *)&sf;
    assert(raw[62] == 0xa5 && raw[63] == 0xa5);
}
int main(void)
{
    padding_probe();
    enabled = !(getenv("QJS_DISABLE_INTERP_FRAME") || getenv("QJS_DISABLE_MIN_CALL_FRAME"));
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "probe", JS_NewCFunction(ctx, probe, "probe", 1)) == 1);
    JS_FreeValue(ctx, global);
    const char *source = "function inner(x){return probe(x)+1}"
                         "function mid(x){return inner(x)+1}"
                         "function driver(x){return mid(x)+1}"
                         "function reenter(x){return probe(x)+2}"
                         "function tailchain(){return inner(8)}"
                         "function hosttail(){return probe(7)}";
    JSValue result = JS_Eval(ctx, source, strlen(source), "compact-frame.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    global = JS_GetGlobalObject(ctx);
    reentry = JS_GetPropertyStr(ctx, global, "reenter");
    const char *names[] = {"driver", "tailchain", "hosttail"};
    int expected[] = {6, 9, 7};
    for (int i = 0; i < 3; i++) {
        JSValue function = JS_GetPropertyStr(ctx, global, names[i]);
        for (int j = 0; j < 64; j++) {
            JSValue argument = JS_NewInt32(ctx, 3);
            JSStackFrame *outer = rt->current_stack_frame;
            inspect_scope = 1;
            result =
                JS_Call(ctx, function, JS_UNDEFINED, i == 0 ? 1 : 0, (JSValueConst *)&argument);
            int32_t n = 0;
            assert(!JS_IsException(result) && !JS_ToInt32(ctx, &n, result) && n == expected[i]);
            JS_FreeValue(ctx, result);
            inspect_scope = 0;
            assert(rt->current_stack_frame == outer);
        }
        JS_FreeValue(ctx, function);
    }
    /* Enter through the original global-eval frame to exercise a foreign root. */
    inspect_scope = getenv("QJS_DISABLE_INTERNAL_INTERP") == NULL;
    source = "driver(3)+tailchain()+hosttail()";
    result = JS_Eval(ctx, source, strlen(source), "foreign-root.js", JS_EVAL_TYPE_GLOBAL);
    int32_t n = 0;
    assert(!JS_IsException(result) && !JS_ToInt32(ctx, &n, result) && n == 22);
    JS_FreeValue(ctx, result);
    if (enabled)
        assert(checked > 1000 && foreign_roots > 0 && tail_parents > 0 && max_depth >= 3);
    else
        assert(!checked);
    printf(
        "COMPACT PASS enabled=%d calls=%u checked=%u foreign_roots=%u tail_parents=%u max_depth=%u\n",
        enabled, probes, checked, foreign_roots, tail_parents, max_depth);
    JS_FreeValue(ctx, reentry);
    JS_FreeValue(ctx, global);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
