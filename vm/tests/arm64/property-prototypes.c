/* Natural weak/private/persistent/direct prototype proofs;public API. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <execinfo.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
static JSContext *caller, *foreign;
static JSValue nested;
static unsigned calls, gc_reentries, unwinds, getters;
static int native, quiet;
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "arm-prototype-hints", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "PROTO_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static void integer(JSContext *ctx, JSValue f, JSValue object, int expected)
{
    JSValue v = JS_Call(ctx, f, JS_UNDEFINED, 1, &object);
    int32_t n = 0;
    assert(!JS_IsException(v) && !JS_ToInt32(ctx, &n, v) && n == expected);
    JS_FreeValue(ctx, v);
}
static JSValue mark(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)argc;
    (void)argv;
    assert(ctx == foreign && (JS_IsString(self) || JS_IsObject(self)));
    ++calls;
    if (!quiet) {
        void *frames[48];
        int n = backtrace(frames, 48), vm = 0;
        for (int i = 0; i < n; i++)
            vm |= (uintptr_t)frames[i] > (uintptr_t)JS_FrameInterp &&
                  (uintptr_t)frames[i] < (uintptr_t)qjs_aarch64_vm_end;
        assert(vm == native);
        unwinds += vm;
        JS_RunGC(JS_GetRuntime(ctx));
        JSValue v = JS_Call(caller, nested, JS_UNDEFINED, 0, NULL);
        int32_t value = 0;
        assert(!JS_IsException(v) && !JS_ToInt32(caller, &value, v) && value == 77);
        JS_FreeValue(caller, v);
        ++gc_reentries;
    }
    return JS_NewInt32(ctx, 7);
}
static JSValue getter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(ctx == foreign);
    ++getters;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_NewCFunction(ctx, mark, "freshMark", 0);
}
static JSValue prototype(JSContext *ctx)
{
    JSValue p = JS_NewObject(ctx);
    assert(!JS_IsException(p));
    assert(JS_SetPropertyStr(ctx, p, "mark", JS_NewCFunction(ctx, mark, "mark", 0)) >= 0);
    return p;
}
static void counters(uint64_t out[16])
{
    qjs_aarch64_vm_proto_counts(out);
}
__attribute__((noipa)) static void pair_native_ready(uintptr_t object)
{
    __asm__ volatile("" ::"r"(object) : "memory");
}
static void set_prototype(JSContext *ctx, JSValue object, JSValue proto)
{
    assert(JS_SetPrototype(ctx, object, proto) == 1);
}
static void semantics(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    caller = JS_NewContext(rt);
    foreign = JS_NewContext(rt);
    assert(caller && foreign);
    native = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    int feature = native && !getenv("QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES");
    int cache = feature && !getenv("QJS_DISABLE_PROTO_LOAD_CACHE");
    int persist = cache && !getenv("QJS_DISABLE_PROTO_LOAD_PERSIST");
    int direct = persist && !getenv("QJS_DISABLE_PROTO_DIRECT");
    nested = eval(caller, "(function(){return 77})");
    JSValue proto = prototype(foreign), array = JS_NewArray(caller);
    assert(!JS_IsException(array));
    set_prototype(caller, array, proto);
    JSValue loop = eval(caller, "(function(o){for(let i=0;i<32;i++)o.mark();return 7})");
    integer(caller, loop, array, 7);
    uint64_t a[16], b[16];
    counters(a);
    unsigned old_calls = calls, old_gc = gc_reentries, old_unwind = unwinds;
    for (unsigned i = 0; i < 2; i++) {
        integer(caller, loop, array, 7);
    }
    counters(b);
    fprintf(
        stderr,
        "PROTO_ACTIVATE first=%llu second=%llu promote=%llu direct=%llu fill=%llu cache=%d persist=%d\n",
        (unsigned long long)(b[0] - a[0]), (unsigned long long)(b[1] - a[1]),
        (unsigned long long)(b[2] - a[2]), (unsigned long long)(b[3] + b[4] - a[3] - a[4]),
        (unsigned long long)(b[5] - a[5]), cache, persist);
    assert(calls - old_calls == 64 && gc_reentries - old_gc == 64 &&
           unwinds - old_unwind == (native ? 64 : 0));
    if (cache)
        assert(b[0] + b[1] - a[0] - a[1] == 64);
    else
        assert(b[0] == a[0] && b[1] == a[1]);
    if (persist)
        assert(b[2] > a[2] && b[5] == a[5]);
    else
        assert(b[2] == a[2]);
    // Fresh public activations,48distinct property/call PCs share only16
    // original private cells. Persistent snapshots can serve full buckets.
    char body[2048];
    strcpy(body, "(function(o){");
    for (unsigned i = 0; i < 48; i++)
        strcat(body, "o.mark();");
    strcat(body, "return 7})");
    JSValue wide = eval(caller, body);
    quiet = 1;
    integer(caller, wide, array, 7);
    counters(a);
    for (unsigned i = 0; i < 4; i++) {
        integer(caller, wide, array, 7);
    }
    counters(b);
    quiet = 0;
    fprintf(stderr,
            "PROTO_FULL_BUCKET direct_object=%llu promote=%llu fill=%llu expected_direct=%d\n",
            (unsigned long long)(b[3] - a[3]), (unsigned long long)(b[2] - a[2]),
            (unsigned long long)(b[5] - a[5]), direct);
    if (direct)
        assert(b[3] > a[3]);
    else
        assert(b[3] == a[3] && b[4] == a[4]);
    // Current bytecode realm's foreign-owned String prototype and live values.
    JSValue old_string = JS_GetClassProto(caller, ARM_CONST_JS_CLASS_STRING);
    assert(!JS_IsException(old_string));
    JS_SetClassProto(caller, ARM_CONST_JS_CLASS_STRING, JS_DupValue(caller, proto));
    JSValue string = JS_NewString(caller, "live"),
            single = eval(caller, "(function(o){return o.mark()})");
    integer(caller, single, string, 7);
    counters(a);
    for (unsigned i = 0; i < 16; i++) {
        integer(caller, single, string, 7);
    }
    counters(b);
    if (cache && !getenv("QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES"))
        assert(b[0] + b[1] > a[0] + a[1]);
    counters(a);
    quiet = 1;
    for (unsigned i = 0; i < 4; i++) {
        integer(caller, wide, string, 7);
    }
    counters(b);
    quiet = 0;
    fprintf(stderr, "PROTO_STRING_DIRECT hits=%llu\n", (unsigned long long)(b[4] - a[4]));
    if (direct && !getenv("QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES"))
        assert(b[4] > a[4]);
    else
        assert(b[4] == a[4]);
    // Primitive and Array own length wins over a callable prototype length.
    assert(JS_SetPropertyStr(foreign, proto, "length", eval(caller, "(function(){return 123})")) >=
           0);
    JSValue length_call = eval(caller, "(function(o){return o.length()})");
    JSValue bad = JS_Call(caller, length_call, JS_UNDEFINED, 1, &string);
    assert(JS_IsException(bad));
    bad = JS_GetException(caller);
    JS_FreeValue(caller, bad);
    bad = JS_Call(caller, length_call, JS_UNDEFINED, 1, &array);
    assert(JS_IsException(bad));
    bad = JS_GetException(caller);
    JS_FreeValue(caller, bad);
    JS_FreeValue(caller, length_call);
    JSValue replacement = prototype(foreign);
    JS_SetClassProto(caller, ARM_CONST_JS_CLASS_STRING, JS_DupValue(caller, replacement));
    integer(caller, single, string, 7);
    JS_SetClassProto(caller, ARM_CONST_JS_CLASS_STRING, old_string);
    JS_FreeValue(caller, replacement);
    // Two live prototype identities at one property PC exercise both private ways.
    JSValue array2 = JS_NewArray(caller), proto2 = prototype(foreign);
    set_prototype(caller, array2, proto2);
    JSValue pair =
        eval(caller, "(function(a,b){for(let i=0;i<32;i++){let o=i&1?b:a;o.mark()}return 7})");
    JSValue args[] = {array, array2};
    JSValue result = JS_Call(caller, pair, JS_UNDEFINED, 2, args);
    int32_t n;
    assert(!JS_IsException(result) && !JS_ToInt32(caller, &n, result) && n == 7);
    JS_FreeValue(caller, result);
    // Native JS callees do not compete for a third C-call identity at this
    // bucket. Two current holders at this SAME opcode must use both ways.
    JSValue leaf = eval(foreign, "(function(){return 7})"), p3 = JS_NewObject(caller),
            p4 = JS_NewObject(caller);
    // A cold JS callee uses the original call learner,which can occupy one
    // shared way. Prepare the callee through its public entry first,then
    // measure two prototype hints without that separate cold-call identity.
    result = JS_Call(foreign, leaf, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(result) && !JS_ToInt32(foreign, &n, result) && n == 7);
    JS_FreeValue(foreign, result);
    JSValue a3 = JS_NewArray(caller), a4 = JS_NewArray(caller);
    assert(JS_SetPropertyStr(caller, p3, "mark", JS_DupValue(caller, leaf)) >= 0 &&
           JS_SetPropertyStr(caller, p4, "mark", JS_DupValue(caller, leaf)) >= 0);
    set_prototype(caller, a3, p3);
    set_prototype(caller, a4, p4);
    JSValue jsargs[] = {a3, a4};
    counters(a);
    pair_native_ready((uintptr_t)JS_VALUE_GET_PTR(pair));
    result = JS_Call(caller, pair, JS_UNDEFINED, 2, jsargs);
    assert(!JS_IsException(result) && !JS_ToInt32(caller, &n, result) && n == 7);
    JS_FreeValue(caller, result);
    counters(b);
    fprintf(stderr, "PROTO_TWO_WAYS first=%llu second=%llu\n", (unsigned long long)(b[0] - a[0]),
            (unsigned long long)(b[1] - a[1]));
    if (cache)
        assert(b[0] > a[0] && b[1] > a[1]);
    JS_FreeValue(caller, a3);
    JS_FreeValue(caller, a4);
    JS_FreeValue(caller, p3);
    JS_FreeValue(caller, p4);
    JS_FreeValue(foreign, leaf);
    // Live descriptor/slot deletion/recreation must invalidate a captured slot.
    JSAtom atom = JS_NewAtom(foreign, "mark");
    assert(atom);
    assert(JS_DeleteProperty(foreign, proto, atom, JS_PROP_THROW) >= 0);
    assert(JS_SetPropertyStr(foreign, proto, "before", JS_NewInt32(foreign, 4)) >= 0);
    assert(JS_SetPropertyStr(foreign, proto, "mark",
                             JS_NewCFunction(foreign, mark, "newMark", 0)) >= 0);
    integer(caller, single, array, 7);
    assert(JS_DefinePropertyGetSet(foreign, proto, atom,
                                   JS_NewCFunction(foreign, getter, "markGetter", 0), JS_UNDEFINED,
                                   JS_PROP_CONFIGURABLE) >= 0);
    unsigned old_getters = getters;
    for (unsigned i = 0; i < 16; i++)
        integer(caller, single, array, 7);
    assert(getters - old_getters == 16);
    JS_FreeAtom(foreign, atom);
    // A direct-prototype negative is weak;missing methods still throw and
    // restoring a current prototype must immediately recover.
    JSValue empty = JS_NewObject(caller);
    set_prototype(caller, array, empty);
    counters(a);
    for (unsigned i = 0; i < 16; i++) {
        result = JS_Call(caller, single, JS_UNDEFINED, 1, &array);
        assert(JS_IsException(result));
        result = JS_GetException(caller);
        JS_FreeValue(caller, result);
    }
    counters(b);
    if (cache)
        assert(b[6] > a[6]);
    set_prototype(caller, array, proto2);
    integer(caller, single, array, 7);
    // A new receiver own property must shadow every older weak proto hint.
    assert(JS_SetPropertyStr(caller, array, "mark", eval(foreign, "(function(){return 31})")) >= 0);
    integer(caller, single, array, 31);
    JSAtom own_atom = JS_NewAtom(caller, "mark");
    assert(own_atom);
    assert(JS_DeleteProperty(caller, array, own_atom, JS_PROP_THROW) == 1);
    JS_FreeAtom(caller, own_atom);
    integer(caller, single, array, 7);
    // Deeper ordinary live data uses the accepted bounded deep-only probe.
    JSValue middle = JS_NewObjectProto(caller, proto2), child = JS_NewObjectProto(caller, middle);
    counters(a);
    for (unsigned i = 0; i < 16; i++) {
        integer(caller, single, child, 7);
    }
    counters(b);
    if (cache && (getenv("QJS_DISABLE_PROPERTY_IC") || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
                  !ARM_HAS_PROPERTY_IC))
        assert(b[10] > a[10]);
    JS_FreeValue(caller, child);
    JS_FreeValue(caller, middle);
    JS_FreeValue(caller, empty);
    // More than32 live prototype edges keeps the complete original getter.
    JSValue bottom = JS_NewObject(caller);
    assert(JS_SetPropertyStr(caller, bottom, "mark", eval(foreign, "(function(){return 73})")) >=
           0);
    JSValue chain = JS_DupValue(caller, bottom);
    for (unsigned i = 0; i < 40; i++) {
        JSValue next = JS_NewObjectProto(caller, chain);
        assert(!JS_IsException(next));
        JS_FreeValue(caller, chain);
        chain = next;
    }
    uint64_t op_a[256], op_b[256];
    qjs_aarch64_vm_opcode_counts(op_a);
    integer(caller, single, chain, 73);
    qjs_aarch64_vm_opcode_counts(op_b);
    if (native && (getenv("QJS_DISABLE_PROPERTY_IC") || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
                   !ARM_HAS_PROPERTY_IC))
        assert(op_b[ARM_OP_get_field2] - op_a[ARM_OP_get_field2] == 1);
    JS_FreeValue(caller, chain);
    JS_FreeValue(caller, bottom);
    JS_FreeValue(caller, pair);
    JS_FreeValue(caller, array2);
    JS_FreeValue(foreign, proto2);
    JS_FreeValue(caller, string);
    JS_FreeValue(caller, single);
    JS_FreeValue(caller, wide);
    JS_FreeValue(caller, loop);
    JS_FreeValue(caller, array);
    JS_FreeValue(foreign, proto);
    JS_FreeValue(caller, nested);
    counters(b);
    if (!feature)
        for (unsigned i = 0; i < 16; i++)
            assert(b[i] == 0);
    printf(
        "AARCH64_PROPERTY_PROTOTYPES_OK calls=%u gc_reentry=%u unwind=%u getter=16 activation=%llu promotion=%llu direct=%llu fill=%llu deep=%llu weak_negative=%llu\n",
        calls, gc_reentries, unwinds, (unsigned long long)(b[0] + b[1]), (unsigned long long)b[2],
        (unsigned long long)(b[3] + b[4]), (unsigned long long)b[5], (unsigned long long)b[10],
        (unsigned long long)b[6]);
    JS_RunGC(rt);
    JS_FreeContext(foreign);
    JS_FreeContext(caller);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
}
typedef struct {
    unsigned iterations;
    int ok;
} Thread;
static JSValue quiet_mark(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewInt32(ctx, 7);
}
static void *worker(void *opaque)
{
    Thread *t = opaque;
    for (unsigned k = 0; k < t->iterations; k++) {
        Allocator memory = {0};
        JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        JSValue p = JS_NewObject(ctx), array = JS_NewArray(ctx);
        assert(!JS_IsException(p) && !JS_IsException(array));
        assert(JS_SetPropertyStr(ctx, p, "mark", JS_NewCFunction(ctx, quiet_mark, "mark", 0)) >= 0);
        set_prototype(ctx, array, p);
        JSValue f = eval(ctx, "(function(o){for(let i=0;i<16;i++)o.mark();return 7})");
        for (unsigned i = 0; i < 16; i++)
            integer(ctx, f, array, 7);
        JS_FreeValue(ctx, f);
        JS_FreeValue(ctx, array);
        JS_FreeValue(ctx, p);
        JS_RunGC(rt);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(memory.live == 0 && memory.bytes == 0);
    }
    t->ok = 1;
    return NULL;
}
static void threads(void)
{
    pthread_t ids[4];
    Thread state[4] = {{12, 0}, {12, 0}, {12, 0}, {12, 0}};
    for (unsigned i = 0; i < 4; i++)
        assert(pthread_create(&ids[i], NULL, worker, state + i) == 0);
    for (unsigned i = 0; i < 4; i++) {
        assert(pthread_join(ids[i], NULL) == 0 && state[i].ok);
    }
    puts(
        "AARCH64_PROPERTY_PROTOTYPES_THREADS_OK threads=4 runtimes=48 weak_global_contention zero_ledgers");
}
int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "threads"))
        threads();
    else
        semantics();
    return 0;
}
