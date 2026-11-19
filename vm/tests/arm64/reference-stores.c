/* Original incoming ownership and finalizer-before-next-op semantics. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t words[2]);
static JSClassID token_class;
static JSContext *caller, *foreign, *other;
static JSValue reader, writer, nested;
static unsigned born, finalized, reentered, unwinds, collections;
static int native, observe_slot;
static int expect_driver;
static int oom_mode;
static const char *phase = "startup";

static JSValue checked(JSContext *ctx, JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "REFERENCE_STORE_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx,
                   JS_Eval(ctx, text, strlen(text), "arm-reference-stores", JS_EVAL_TYPE_GLOBAL));
}
static void number(JSContext *ctx, JSValue v, int expected)
{
    int32_t n = 0;
    v = checked(ctx, v);
    int status = JS_ToInt32(ctx, &n, v);
    if (status || n != expected)
        fprintf(stderr,
                "REFERENCE_STORE_VALUE phase=%s got=%d expected=%d born=%u final=%u reentered=%u\n",
                phase, n, expected, born, finalized, reentered);
    assert(!status && n == expected);
    JS_FreeValue(ctx, v);
}
static void read_slot(int expected)
{
    number(caller, JS_Call(caller, reader, JS_UNDEFINED, 0, NULL), expected);
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
    if (oom_mode) {
        JSValue probe = JS_NewObject(foreign);
        if (JS_IsException(probe))
            JS_FreeValue(foreign, JS_GetException(foreign));
        else
            JS_FreeValue(foreign, probe);
        return;
    }
    void *frames[64];
    int n = backtrace(frames, 64), vm = 0;
    for (int i = 0; i < n; i++)
        vm |= (uintptr_t)frames[i] > (uintptr_t)JS_FrameInterp &&
              (uintptr_t)frames[i] < (uintptr_t)qjs_aarch64_vm_end;
    assert(vm == native);
    unwinds += vm;
    if (expect_driver) {
        JSValue error = checked(foreign, JS_NewError(foreign));
        JSValue stack = checked(foreign, JS_GetPropertyStr(foreign, error, "stack"));
        const char *text = JS_ToCString(foreign, stack);
        assert(text && strstr(text, "storeAttached") && strstr(text, "storeDriver"));
        JS_FreeCString(foreign, text);
        JS_FreeValue(foreign, stack);
        JS_FreeValue(foreign, error);
    }
    // The original source allows this independent-runtime GC/reentry. The
    // old value's finalizer must see the already committed replacement.
    JS_RunGC(JS_GetRuntime(other));
    ++collections;
    number(other, JS_Call(other, nested, JS_UNDEFINED, 0, NULL), 77);
    if (observe_slot) {
        read_slot(17);
        JSValue a = JS_NewInt32(caller, 99);
        JS_FreeValue(caller, checked(caller, JS_Call(caller, writer, JS_UNDEFINED, 1, &a)));
        read_slot(99);
        ++reentered;
    }
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(ctx == foreign);
    JSValue v = JS_NewObjectClass(ctx, token_class);
    if (!JS_IsException(v))
        ++born;
    return v;
}
static JSValue remember(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(ctx == foreign && argc == 2);
    JS_FreeValue(caller, reader);
    JS_FreeValue(caller, writer);
    reader = JS_DupValue(caller, argv[0]);
    writer = JS_DupValue(caller, argv[1]);
    return JS_UNDEFINED;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(ctx == foreign);
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue v = checked(caller, JS_Call(caller, reader, JS_UNDEFINED, 0, NULL));
    assert(JS_GetClassID(v) == token_class);
    JS_FreeValue(caller, v);
    return JS_UNDEFINED;
}
static JSValue setter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(ctx == foreign && argc == 1);
    int32_t n = 0;
    assert(!JS_ToInt32(ctx, &n, argv[0]) && n == 71);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue checkpoint(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(ctx == foreign);
    read_slot(99);
    return JS_UNDEFINED;
}
static void counters(uint64_t out[8])
{
    qjs_aarch64_vm_store_counts(out);
}
static void oom_tests(void)
{
    unsigned failed = 0, succeeded = 0, rejected = 0;
    uint64_t start[8], end[8];
    counters(start);
    oom_mode = 1;
    for (unsigned point = 0; point < 96; point++) {
        Allocator memory = {0};
        JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
        assert(rt);
        JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
        foreign = JS_NewContext(rt);
        assert(foreign);
        token_class = 0;
        JS_NewClassID(rt, &token_class);
        JSClassDef d = {0};
        d.class_name = "StoreOOM";
        d.finalizer = finalizer;
        assert(!JS_NewClass(rt, token_class, &d));
        born = finalized = 0;
        JSValue maker = JS_NewCFunction(foreign, make, "make", 0);
        assert(!JS_IsException(maker));
        JSValue f = eval(foreign, "(function storeOOM(make){var value=make();value=17;return 7})");
        uintptr_t before[2], after[2];
        qjs_aarch64_vm_quota(rt, before);
        if (point)
            memory.fail_at = memory.sequence + point;
        JSValue result = JS_Call(foreign, f, JS_UNDEFINED, 1, &maker);
        memory.fail_at = 0;
        if (JS_IsException(result)) {
            assert(memory.rejected);
            JS_FreeValue(foreign, JS_GetException(foreign));
            ++failed;
        } else {
            number(foreign, result, 7);
            ++succeeded;
        }
        qjs_aarch64_vm_quota(rt, after);
        assert(before[0] == after[0] && before[1] == after[1]);
        rejected += memory.rejected;
        JS_FreeValue(foreign, f);
        JS_FreeValue(foreign, maker);
        JS_FreeContext(foreign);
        JS_RunGC(rt);
        JS_FreeRuntime(rt);
        assert(born == finalized && memory.live == 0 && memory.bytes == 0);
    }
    counters(end);
    assert(failed && succeeded && rejected);
    int slots = native && !getenv("QJS_DISABLE_NATIVE_SLOT_STORE");
    if (slots)
        assert(end[1] > start[1]);
    else
        assert(end[1] == start[1]);
    printf(
        "AARCH64_REFERENCE_STORES_OOM_OK trials=96 failed=%u succeeded=%u rejected=%u native_release=%llu exact_quota zero_ledgers\n",
        failed, succeeded, rejected, (unsigned long long)(end[1] - start[1]));
}
int main(int argc, char **argv)
{
    native = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        oom_tests();
        return 0;
    }
    Allocator memory = {0}, other_memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory),
              *other_rt = JS_NewRuntime2(&functions, &other_memory);
    assert(rt && other_rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JS_SetMaxStackSize(other_rt, 4 * 1024 * 1024);
    caller = JS_NewContext(rt);
    foreign = JS_NewContext(rt);
    other = JS_NewContext(other_rt);
    assert(caller && foreign && other);
    int slots = native && !getenv("QJS_DISABLE_NATIVE_SLOT_STORE");
    int generic = native && !getenv("QJS_DISABLE_AARCH64_PROPERTY_STORES");
    int pic = native && ARM_HAS_PROPERTY_IC && !getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") &&
              !getenv("QJS_DISABLE_PROPERTY_IC");
    JS_NewClassID(rt, &token_class);
    JSClassDef definition = {0};
    definition.class_name = "ArmReferenceStore";
    definition.finalizer = finalizer;
    assert(!JS_NewClass(rt, token_class, &definition));
    reader = writer = JS_UNDEFINED;
    nested = eval(other, "(function(){return 77})");
    JSValue callbacks[] = {JS_NewCFunction(foreign, make, "make", 0),
                           JS_NewCFunction(foreign, remember, "remember", 2),
                           JS_NewCFunction(foreign, collect, "collect", 0),
                           JS_NewCFunction(foreign, checkpoint, "checkpoint", 0)};
    JSValue attached = eval(
        caller,
        "(function storeAttached(make,remember,collect,checkpoint){var value=make();remember(function(){return value},function(v){value=v});value=value;collect();value=17;checkpoint();return value})");
    uint64_t a[8], b[8];
    counters(a);
    observe_slot = 1;
    phase = "attached";
    for (unsigned i = 0; i < 32; i++)
        number(caller, JS_Call(caller, attached, JS_UNDEFINED, 4, callbacks), 99);
    counters(b);
    assert(born == 32 && finalized == 32 && reentered == 32);
    assert(b[1] - a[1] == (slots ? 32u : 0u));
    if (slots)
        assert(b[0] > a[0]);
    else
        assert(b[0] == a[0]);
    // A real prepared child leaves the public SF Dirty. Natural Error.stack
    // inside its finalizer must still expose both logical JS frames.
    JSValue driver = eval(caller, "(function storeDriver(f,a,b,c,d){return f(a,b,c,d)+0})");
    JSValue child_args[] = {attached, callbacks[0], callbacks[1], callbacks[2], callbacks[3]};
    phase = "dirty-child";
    expect_driver = 1;
    number(caller, JS_Call(caller, driver, JS_UNDEFINED, 5, child_args), 99);
    counters(a);
    QJSArmVMCounts vm_a, vm_b;
    qjs_aarch64_vm_counts(&vm_a);
    uintptr_t quota_a[2], quota_b[2];
    qjs_aarch64_vm_quota(rt, quota_a);
    for (unsigned i = 0; i < 32; i++)
        number(caller, JS_Call(caller, driver, JS_UNDEFINED, 5, child_args), 99);
    counters(b);
    qjs_aarch64_vm_counts(&vm_b);
    qjs_aarch64_vm_quota(rt, quota_b);
    assert(quota_a[0] == quota_b[0] && quota_a[1] == quota_b[1]);
    assert(b[1] - a[1] == (slots ? 32u : 0u));
    assert(vm_b.native_calls - vm_a.native_calls == (native ? 32u : 0u));
    expect_driver = 0;
    JS_FreeValue(caller, driver);
    // A detached capture remains the current live pvalue owner after its
    // parent returns. The finalizer rewrites that same slot to99.
    JSValue detached = eval(
        caller,
        "(function(make,remember,collect,checkpoint){var value=make();remember(function(){return value},function(v){value=v});return function(v){value=v;checkpoint();return value}})");
    counters(a);
    phase = "detached";
    for (unsigned i = 0; i < 32; i++) {
        JSValue f = checked(caller, JS_Call(caller, detached, JS_UNDEFINED, 4, callbacks));
        JSValue v = JS_NewInt32(caller, 17);
        number(caller, JS_Call(caller, f, JS_UNDEFINED, 1, &v), 99);
        JS_FreeValue(caller, f);
    }
    counters(b);
    assert(born == 97 && finalized == 97 && reentered == 97);
    assert(b[1] - a[1] == (slots ? 32u : 0u));
    // Noncaptured locals use the identical continuation without creating a
    // closure or retaining the released object in a source slot.
    observe_slot = 0;
    phase = "local";
    JSValue local = eval(caller, "(function(make){var value=make();value=17;return value})");
    counters(a);
    for (unsigned i = 0; i < 32; i++)
        number(caller, JS_Call(caller, local, JS_UNDEFINED, 1, callbacks), 17);
    counters(b);
    assert(born == 129 && finalized == 129 && collections == 129 &&
           unwinds == (native ? 129u : 0u));
    assert(b[1] - a[1] == (slots ? 32u : 0u));
    // Existing active PIC learning is preserved. Core/base/compiled IC-OFF
    // use the independent live writable own hash instead.
    phase = "property";
    JSValue put = eval(caller, "(function(o,v){'use strict';o.value=v;return 7})");
    JSValue object = JS_NewObject(caller);
    assert(!JS_IsException(object));
    assert(JS_SetPropertyStr(caller, object, "value", JS_NewInt32(caller, 0)) >= 0);
    JSValue args[] = {object, JS_NewInt32(caller, 71)};
    for (unsigned i = 0; i < 8; i++)
        number(caller, JS_Call(caller, put, JS_UNDEFINED, 2, args), 7);
    uint64_t op_a[256], op_b[256];
    qjs_aarch64_vm_opcode_counts(op_a);
    counters(a);
    for (unsigned i = 0; i < 64; i++)
        number(caller, JS_Call(caller, put, JS_UNDEFINED, 2, args), 7);
    counters(b);
    qjs_aarch64_vm_opcode_counts(op_b);
    int hot = pic || generic;
    assert(b[2] - a[2] == (!pic && generic ? 64u : 0u));
    assert(op_b[ARM_OP_put_field] - op_a[ARM_OP_put_field] == (native && !hot ? 64u : 0u));
    // The transferred RHS can contain every supported heap/scalar tag.
    JSValue tags = eval(caller, "[0,-0,1.5,null,undefined,true,'text',{},Symbol('x'),123n]");
    JSValue same =
        eval(caller, "(function(o,v){'use strict';o.value=v;return Object.is(o.value,v)})");
    for (unsigned i = 0; i < 10; i++) {
        assert(JS_SetPropertyStr(caller, object, "value", JS_NewInt32(caller, 0)) >= 0);
        JSValue v = checked(caller, JS_GetPropertyUint32(caller, tags, i));
        JSValue pair[] = {object, v};
        JSValue result = checked(caller, JS_Call(caller, same, JS_UNDEFINED, 2, pair));
        assert(JS_ToBool(caller, result) == 1);
        JS_FreeValue(caller, result);
        JS_FreeValue(caller, v);
    }
    JS_FreeValue(caller, same);
    JS_FreeValue(caller, tags);
    // Readonly,accessor and array length retain original observable owners.
    JSValue readonly = JS_NewObject(caller);
    assert(!JS_IsException(readonly));
    assert(JS_DefinePropertyValueStr(caller, readonly, "value", JS_NewInt32(caller, 9), 0) >= 0);
    args[0] = readonly;
    JSValue failure = JS_Call(caller, put, JS_UNDEFINED, 2, args);
    assert(JS_IsException(failure));
    JS_FreeValue(caller, JS_GetException(caller));
    number(caller, JS_GetPropertyStr(caller, readonly, "value"), 9);
    JS_FreeValue(caller, readonly);
    JSValue accessor = JS_NewObject(caller);
    JSAtom key = JS_NewAtom(caller, "value");
    assert(JS_DefinePropertyGetSet(caller, accessor, key, JS_UNDEFINED,
                                   JS_NewCFunction(foreign, setter, "set", 1),
                                   JS_PROP_CONFIGURABLE) >= 0);
    JS_FreeAtom(caller, key);
    args[0] = accessor;
    number(caller, JS_Call(caller, put, JS_UNDEFINED, 2, args), 7);
    JS_FreeValue(caller, accessor);
    JSValue array = eval(caller, "[1,2,3,4]");
    JSValue length = eval(caller, "(function(o){o.length=1;return o.length})");
    number(caller, JS_Call(caller, length, JS_UNDEFINED, 1, &array), 1);
    JS_FreeValue(caller, length);
    JS_FreeValue(caller, array);
    JS_FreeValue(caller, object);
    JS_FreeValue(caller, put);
    JS_FreeValue(caller, local);
    JS_FreeValue(caller, attached);
    JS_FreeValue(caller, detached);
    JS_FreeValue(caller, reader);
    JS_FreeValue(caller, writer);
    for (unsigned i = 0; i < 4; i++)
        JS_FreeValue(foreign, callbacks[i]);
    JS_FreeValue(other, nested);
    JS_FreeContext(other);
    JS_RunGC(other_rt);
    JS_FreeRuntime(other_rt);
    JS_FreeContext(foreign);
    JS_FreeContext(caller);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0 && other_memory.live == 0 &&
           other_memory.bytes == 0);
    printf(
        "AARCH64_REFERENCE_STORES_OK slots=%d generic=%d pic=%d born=%u final=%u reentered=%u unwind=%u GC=%u zero_ledgers\n",
        slots, generic, pic, born, finalized, reentered, unwinds, collections);
    return 0;
}
