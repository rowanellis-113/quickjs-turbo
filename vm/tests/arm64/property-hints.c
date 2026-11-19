/* Public producer/free lifetimes,live own hints and borrowed PICs. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"

typedef struct {
    Allocator memory;
    int armed, fail_original, targeted, fallback_seen;
    uintptr_t allocations, base_bytes;
    size_t original_request, reservation_request;
    unsigned reservation_rejects;
} State;
static int reject_reservation(State *s, size_t n)
{
    uintptr_t a[6];
    if (!s->armed)
        return 0;
    qjs_aarch64_vm_own_allocation_counts(a);
    if (!s->targeted && a[1] > s->allocations) {
        assert(a[0] == 1 && a[1] == s->allocations + 1);
        s->targeted = 1;
        s->original_request = a[2] - s->base_bytes;
        s->reservation_request = n;
        assert(n ==
               s->original_request + 6 + (s->original_request < 2048 ? s->original_request : 2048));
    }
    if (!s->targeted)
        return 0;
    if (a[0] != 2) {
        ++s->reservation_rejects;
        return 1;
    }
    if (!s->fallback_seen) {
        assert(n == s->original_request);
        s->fallback_seen = 1;
    }
    return s->fail_original;
}
static void *wrapped_calloc(void *opaque, size_t n, size_t size)
{
    State *s = opaque;
    if (size && n > SIZE_MAX / size)
        return NULL;
    return reject_reservation(s, n * size) ? NULL : allocate_zero(&s->memory, n, size);
}
static void *wrapped_malloc(void *opaque, size_t n)
{
    State *s = opaque;
    return reject_reservation(s, n) ? NULL : allocate(&s->memory, n);
}
static void wrapped_free(void *opaque, void *p)
{
    State *s = opaque;
    release(&s->memory, p);
}
static void *wrapped_realloc(void *opaque, void *p, size_t n)
{
    State *s = opaque;
    if (s->armed && s->targeted && s->fail_original && n)
        return NULL;
    return resize(&s->memory, p, n);
}
static const JSMallocFunctions wrapped = {wrapped_calloc, wrapped_malloc, wrapped_free,
                                          wrapped_realloc, usable};

static JSValue eval(JSContext *ctx, const char *text, int flags)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "arm-own-hints", flags);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "OWN_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static JSValue call(JSContext *ctx, JSValue f, JSValue object)
{
    JSValue v = JS_Call(ctx, f, JS_UNDEFINED, 1, &object);
    assert(!JS_IsException(v));
    return v;
}
static void integer(JSContext *ctx, JSValue f, JSValue object, int expected)
{
    JSValue v = call(ctx, f, object);
    int32_t n = 0;
    assert(!JS_ToInt32(ctx, &n, v) && n == expected);
    JS_FreeValue(ctx, v);
}
static void dispose(JSRuntime *rt, JSContext *ctx, State *s)
{
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(s->memory.live == 0 && s->memory.bytes == 0);
}

#ifdef ARM_OWN_EARLY_PRODUCER
static int early_produced;
__attribute__((constructor(101))) static void early_producer(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue v = eval(ctx, "(function(o){return o.value})", JS_EVAL_TYPE_GLOBAL);
    JS_FreeValue(ctx, v);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    early_produced = 1;
}
#endif

static JSContext *foreign;
static JSValue foreign_fn;
static unsigned getters;
static JSValue clear_live;
static unsigned finalized, capture_getters;
static void finalizer(JSRuntime *rt, JSValue object)
{
    (void)rt;
    (void)object;
    ++finalized;
}
static JSValue capture_getter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)argc;
    (void)argv;
    assert(JS_IsObject(self));
    unsigned before = finalized;
    JSValue null_value = JS_NULL;
    JSValue v = JS_Call(ctx, clear_live, JS_UNDEFINED, 1, &null_value);
    assert(!JS_IsException(v));
    JS_FreeValue(ctx, v);
    JS_RunGC(JS_GetRuntime(ctx));
    assert(finalized == before);
    ++capture_getters;
    return JS_NewInt32(ctx, 91);
}
static void captured_owner(JSContext *ctx)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    JSClassID id = 0;
    JS_NewClassID(rt, &id);
    JSClassDef def = {0};
    def.class_name = "OwnedHintReceiver";
    def.finalizer = finalizer;
    assert(JS_NewClass(rt, id, &def) == 0);
    JSValue pair = eval(
        ctx,
        "(function(){let slot;return {set:function(v){slot=v},get:function(){return slot.value}}})()",
        JS_EVAL_TYPE_GLOBAL);
    clear_live = JS_GetPropertyStr(ctx, pair, "set");
    JSValue get = JS_GetPropertyStr(ctx, pair, "get");
    assert(JS_IsFunction(ctx, clear_live) && JS_IsFunction(ctx, get));
    JS_FreeValue(ctx, pair);
    JSAtom atom = JS_NewAtom(ctx, "value");
    assert(atom);
    uint64_t a[8], b[8];
    qjs_aarch64_vm_hint_counts(a);
    for (unsigned i = 0; i < 32; i++) {
        JSValue object = JS_NewObjectClass(ctx, id);
        assert(!JS_IsException(object));
        assert(JS_DefinePropertyGetSet(ctx, object, atom,
                                       JS_NewCFunction(ctx, capture_getter, "captureGetter", 0),
                                       JS_UNDEFINED, JS_PROP_CONFIGURABLE) >= 0);
        JSValue v = JS_Call(ctx, clear_live, JS_UNDEFINED, 1, &object);
        assert(!JS_IsException(v));
        JS_FreeValue(ctx, v);
        JS_FreeValue(ctx, object);
        unsigned before = finalized;
        v = JS_Call(ctx, get, JS_UNDEFINED, 0, NULL);
        int32_t n = 0;
        assert(!JS_IsException(v) && !JS_ToInt32(ctx, &n, v) && n == 91);
        JS_FreeValue(ctx, v);
        assert(finalized == before + 1);
    }
    assert(capture_getters == 32 && finalized == 32);
    qjs_aarch64_vm_hint_counts(b);
    fprintf(stderr, "OWN_CAPTURE drop_gc_finalizers=32 borrowed_fallbacks=%llu\n",
            (unsigned long long)(b[5] - a[5]));
    if (ARM_HAS_PROPERTY_IC && !getenv("QJS_DISABLE_REGISTER_INTERP") &&
        !getenv("QJS_DISABLE_INTERP_FRAME"))
        assert(b[5] - a[5] >= 32);
    JS_FreeAtom(ctx, atom);
    JS_FreeValue(ctx, get);
    JS_FreeValue(ctx, clear_live);
    clear_live = JS_UNDEFINED;
}
static JSValue getter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue v = JS_Call(foreign, foreign_fn, JS_UNDEFINED, 0, NULL);
    int32_t n = 0;
    assert(!JS_IsException(v) && !JS_ToInt32(foreign, &n, v) && n == 77);
    JS_FreeValue(foreign, v);
    ++getters;
    return JS_NewInt32(ctx, 91);
}

static void wire(JSContext *ctx, JSValue object, int own_on)
{
    JSValue bc =
        eval(ctx, "(function(o){return o.value})", JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    size_t size = 0;
    uint8_t *bytes = JS_WriteObject(ctx, &size, bc, JS_WRITE_OBJ_BYTECODE);
    assert(bytes && size);
    JS_FreeValue(ctx, bc);
    uintptr_t a[6], b[6];
    qjs_aarch64_vm_own_allocation_counts(a);
    bc = JS_ReadObject(ctx, bytes, size, JS_READ_OBJ_BYTECODE);
    assert(!JS_IsException(bc));
    qjs_aarch64_vm_own_allocation_counts(b);
    if (own_on)
        assert(b[1] > a[1] && b[3] > a[3]);
    else
        assert(b[1] == a[1] && b[3] == a[3]);
    js_free(ctx, bytes);
    JSValue f = JS_EvalFunction(ctx, bc);
    assert(!JS_IsException(f));
    for (unsigned i = 0; i < 32; i++)
        integer(ctx, f, object, 123);
    JS_FreeValue(ctx, f);
}

static void semantics(void)
{
    State s = {0};
    JSRuntime *rt = JS_NewRuntime2(&wrapped, &s);
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    foreign = JS_NewContext(rt);
    assert(foreign);
    foreign_fn = eval(foreign, "(function(){return 77})", JS_EVAL_TYPE_GLOBAL);
    int native = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    int own_on = native && !getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") &&
                 !getenv("QJS_DISABLE_AARCH64_PROPERTY_HINTS");
    int borrow_on = ARM_HAS_PROPERTY_IC && own_on && !getenv("QJS_DISABLE_FRAME_LOCAL_FIELD") &&
                    !getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") &&
                    !getenv("QJS_DISABLE_PROPERTY_IC");
    uintptr_t config[6];
    qjs_aarch64_vm_own_allocation_counts(config);
    assert(config[0] == (own_on ? 1 : 2));
    JSValue f = eval(ctx, "(function(o){return o.value})", JS_EVAL_TYPE_GLOBAL);
    JSValue method = eval(ctx, "(function(o){return o.fn()})", JS_EVAL_TYPE_GLOBAL);
    JSValue fn = eval(ctx, "(function(){return 73})", JS_EVAL_TYPE_GLOBAL);
    JSValue o = JS_NewObject(ctx);
    assert(!JS_IsException(o));
    assert(JS_SetPropertyStr(ctx, o, "value", JS_NewInt32(ctx, 123)) >= 0);
    assert(JS_SetPropertyStr(ctx, o, "fn", JS_DupValue(ctx, fn)) >= 0);
    for (unsigned i = 0; i < 16; i++) {
        integer(ctx, f, o, 123);
        integer(ctx, method, o, 73);
    }
    uint64_t a[8], b[8];
    qjs_aarch64_vm_hint_counts(a);
    for (unsigned i = 0; i < 128; i++) {
        integer(ctx, f, o, 123);
        integer(ctx, method, o, 73);
    }
    qjs_aarch64_vm_hint_counts(b);
    fprintf(
        stderr,
        "OWN_ROUTE read=%llu method=%llu fill=%llu borrowed=%llu fallback=%llu expected_borrowed=%d\n",
        (unsigned long long)(b[0] - a[0]), (unsigned long long)(b[1] - a[1]),
        (unsigned long long)(b[2] - a[2]), (unsigned long long)(b[4] - a[4]),
        (unsigned long long)(b[5] - a[5]), borrow_on);
    assert(b[4] - a[4] == (borrow_on ? 128 : 0));
    if (own_on && (getenv("QJS_DISABLE_PROPERTY_IC") || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
                   !ARM_HAS_PROPERTY_IC))
        assert(b[0] - a[0] == 128 && b[1] - a[1] == 128);
    if (!own_on)
        assert(b[0] == a[0] && b[1] == a[1] && b[2] == a[2]);
    if (native && !own_on &&
        (getenv("QJS_DISABLE_PROPERTY_IC") || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
         !ARM_HAS_PROPERTY_IC))
        assert(b[6] - a[6] == 128 && b[7] - a[7] == 128);
    wire(ctx, o, own_on);
    char long_source[6000];
    strcpy(long_source, "(function(o){");
    for (unsigned i = 0; i < 450; i++)
        strcat(long_source, "o.value;");
    strcat(long_source, "return o.fn()})");
    JSValue long_fn = eval(ctx, long_source, JS_EVAL_TYPE_GLOBAL);
    integer(ctx, long_fn, o, 73);
    uintptr_t info[6];
    extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
    assert(qjs_aarch64_vm_function_info(long_fn, info) && info[4] > 2048 && info[4] <= 4096);
    uint64_t la[8], lb[8];
    qjs_aarch64_vm_hint_counts(la);
    for (unsigned i = 0; i < 3; i++)
        integer(ctx, long_fn, o, 73);
    qjs_aarch64_vm_hint_counts(lb);
    assert(la[0] == lb[0] && la[1] == lb[1] && la[2] == lb[2]);
    if (native && (getenv("QJS_DISABLE_PROPERTY_IC") || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
                   !ARM_HAS_PROPERTY_IC))
        assert(lb[6] - la[6] == 1350 && lb[7] - la[7] == 3);
    fprintf(stderr, "OWN_LONG bytes=%llu generic_reads=%llu generic_methods=%llu tail_hits=0\n",
            (unsigned long long)info[4], (unsigned long long)(lb[6] - la[6]),
            (unsigned long long)(lb[7] - la[7]));
    JS_FreeValue(ctx, long_fn);
    JSValue values[] = {JS_NewInt32(ctx, -19),
                        JS_NewFloat64(ctx, 2.5),
                        JS_NewFloat64(ctx, -0.0),
                        JS_TRUE,
                        JS_NULL,
                        JS_UNDEFINED,
                        JS_NewString(ctx, "hint"),
                        eval(ctx, "Symbol('hint')", JS_EVAL_TYPE_GLOBAL),
                        eval(ctx, "1234567890123456789n", JS_EVAL_TYPE_GLOBAL),
                        JS_DupValue(ctx, o)};
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++) {
        assert(JS_SetPropertyStr(ctx, o, "value", JS_DupValue(ctx, values[i])) >= 0);
        for (unsigned j = 0; j < 16; j++) {
            JSValue v = call(ctx, f, o);
            assert(JS_IsSameValue(ctx, v, values[i]));
            JS_FreeValue(ctx, v);
        }
        JS_FreeValue(ctx, values[i]);
    }
    assert(JS_SetPropertyStr(ctx, o, "value", JS_UNDEFINED) >= 0);
    JSAtom atom = JS_NewAtom(ctx, "value");
    assert(atom);
    assert(JS_DefinePropertyGetSet(ctx, o, atom, JS_NewCFunction(ctx, getter, "hintGetter", 0),
                                   JS_UNDEFINED, JS_PROP_CONFIGURABLE) >= 0);
    for (unsigned i = 0; i < 32; i++)
        integer(ctx, f, o, 91);
    assert(getters == 32);
    assert(JS_DeleteProperty(ctx, o, atom, JS_PROP_THROW) >= 0);
    JSValue v = call(ctx, f, o);
    assert(JS_IsUndefined(v));
    JS_FreeValue(ctx, v);
    assert(JS_SetPropertyStr(ctx, o, "value", JS_NewInt32(ctx, 123)) >= 0);
    integer(ctx, f, o, 123);
    JS_FreeAtom(ctx, atom);
    captured_owner(ctx);
    for (unsigned k = 0; k < 24; k++) {
        JSValue object = JS_NewObject(ctx);
        assert(!JS_IsException(object));
        for (unsigned j = 0; j < k; j++) {
            char key[24];
            snprintf(key, sizeof(key), "prefix%u", j);
            assert(JS_SetPropertyStr(ctx, object, key, JS_NewInt32(ctx, j)) >= 0);
        }
        assert(JS_SetPropertyStr(ctx, object, "value", JS_NewInt32(ctx, 1000 + k)) >= 0);
        for (unsigned j = 0; j < 8; j++)
            integer(ctx, f, object, 1000 + k);
        JS_FreeValue(ctx, object);
        JS_RunGC(rt);
    }
    JS_FreeValue(ctx, o);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, method);
    JS_FreeValue(ctx, f);
    JS_FreeValue(foreign, foreign_fn);
    JS_FreeContext(foreign);
    foreign = NULL;
    dispose(rt, ctx, &s);
    qjs_aarch64_vm_own_allocation_counts(config);
    printf(
        "OWN_HEAP peak_requested=%zu total_base=%llu total_reserved=%llu bytecode_allocations=%llu\n",
        s.memory.peak, (unsigned long long)config[2], (unsigned long long)config[3],
        (unsigned long long)config[1]);
    printf(
        "AARCH64_PROPERTY_HINTS_OK borrowed=%llu own_read=%llu own_method=%llu getter_gc_reentry=32 capture_drop_gc_finalizers=32 tags=10 shapes=24 wire_reader zero_ledgers\n",
        (unsigned long long)(b[4] - a[4]), (unsigned long long)(b[0] - a[0]),
        (unsigned long long)(b[1] - a[1]));
}

static void allocation_failure(int fail_original)
{
    State s = {0};
    JSRuntime *rt = JS_NewRuntime2(&wrapped, &s);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue old = eval(ctx, "(function(o){return o.value})", JS_EVAL_TYPE_GLOBAL),
            o = JS_NewObject(ctx);
    assert(JS_SetPropertyStr(ctx, o, "value", JS_NewInt32(ctx, 123)) >= 0);
    for (unsigned i = 0; i < 16; i++)
        integer(ctx, old, o, 123);
    uintptr_t counts[6];
    qjs_aarch64_vm_own_allocation_counts(counts);
    assert(counts[0] == 1);
    s.allocations = counts[1];
    s.base_bytes = counts[2];
    s.fail_original = fail_original;
    s.armed = 1;
    const char *text = "(function(o){return o.value})";
    JSValue f = JS_Eval(ctx, text, strlen(text), "arm-own-fault", JS_EVAL_TYPE_GLOBAL);
    s.armed = 0;
    assert(s.targeted && s.fallback_seen && s.reservation_rejects);
    assert(JS_IsException(f) == !!fail_original);
    if (fail_original) {
        JSValue e = JS_GetException(ctx);
        JS_FreeValue(ctx, e);
    } else {
        integer(ctx, f, o, 123);
        JS_FreeValue(ctx, f);
    }
    qjs_aarch64_vm_own_allocation_counts(counts);
    assert(counts[0] == 2 && counts[4] >= 1);
    uint64_t a[8], b[8];
    qjs_aarch64_vm_hint_counts(a);
    for (unsigned i = 0; i < 64; i++)
        integer(ctx, old, o, 123);
    f = eval(ctx, text, JS_EVAL_TYPE_GLOBAL);
    integer(ctx, f, o, 123);
    JS_FreeValue(ctx, f);
    qjs_aarch64_vm_hint_counts(b);
    assert(a[0] == b[0] && a[1] == b[1] && a[2] == b[2]);
    JS_FreeValue(ctx, old);
    JS_FreeValue(ctx, o);
    dispose(rt, ctx, &s);
    for (unsigned i = 0; i < 2; i++) {
        State t = {0};
        rt = JS_NewRuntime2(&wrapped, &t);
        assert(rt);
        ctx = JS_NewContext(rt);
        assert(ctx);
        JSValue v = eval(ctx, "(function(){return 7})()", JS_EVAL_TYPE_GLOBAL);
        int32_t n;
        assert(!JS_ToInt32(ctx, &n, v) && n == 7);
        JS_FreeValue(ctx, v);
        qjs_aarch64_vm_own_allocation_counts(counts);
        assert(counts[0] == 2);
        dispose(rt, ctx, &t);
    }
    printf(
        "AARCH64_PROPERTY_HINTS_OOM_OK original_fail=%d rejected=%u reservation=%zu original=%zu monotonic_off old_and_new_bytecodes new_runtimes=2 zero_ledgers\n",
        fail_original, s.reservation_rejects, s.reservation_request, s.original_request);
}
int main(int argc, char **argv)
{
#ifdef ARM_OWN_EARLY_PRODUCER
    uintptr_t c[6];
    qjs_aarch64_vm_own_allocation_counts(c);
    assert(early_produced && c[0] == 2 && c[1] == 0);
    puts("AARCH64_PROPERTY_HINTS_PRECRT_OK original_size_before_ctor permanent_off");
    return 0;
#endif
    if (argc > 1)
        allocation_failure(!strcmp(argv[1], "oom-original"));
    else
        semantics();
    return 0;
}
