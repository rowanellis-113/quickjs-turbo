/* Natural same-caller four-way/transition/epoch routes;no private mutation. */
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
/* Source-owned read-only kind histogram;indices follow property-ic.h's
 * pinned enum (5=same-capacity transition,6=resize transition). */
extern int js_property_ic_inspect(JSValueConst, uint32_t counts[7]);
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "arm-property-ic", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "PROPERTY_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return value;
}
static void call(JSContext *ctx, JSValue f, JSValue object, int input, int expected)
{
    JSValue args[] = {object, JS_NewInt32(ctx, input)},
            value = JS_Call(ctx, f, JS_UNDEFINED, 2, args);
    int32_t n = 0;
    assert(!JS_IsException(value) && !JS_ToInt32(ctx, &n, value) && n == expected);
    JS_FreeValue(ctx, value);
}
static unsigned gc_calls;
__attribute__((noipa)) static void property_warmed(void)
{
    __asm__ volatile("" ::: "memory");
}
static JSValue gc_probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    ++gc_calls;
    return JS_NewInt32(ctx, 91);
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    int native = !getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") &&
                 !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
                 !getenv("QJS_DISABLE_PROPERTY_IC");
    JSValue rw = eval(ctx, "(function(o,v){o.value=v;return o.value})");
    JSValue get = eval(ctx, "(function(o){return o.value})");
    JSValue put = eval(ctx, "(function(o,v){o.value=v;return v})");
    JSValue method = eval(ctx, "(function(o){return o.fn()})");
    JSValue fn = eval(ctx, "(function(){return 73})"), objects[4];
    for (unsigned i = 0; i < 4; i++) {
        objects[i] = JS_NewObject(ctx);
        char key[16];
        snprintf(key, sizeof(key), "shape%u", i);
        assert(!JS_IsException(objects[i]) &&
               JS_SetPropertyStr(ctx, objects[i], key, JS_NewInt32(ctx, i)) >= 0);
        assert(JS_SetPropertyStr(ctx, objects[i], "value", JS_NewInt32(ctx, 0)) >= 0);
        assert(JS_SetPropertyStr(ctx, objects[i], "fn", JS_DupValue(ctx, fn)) >= 0);
    }
    for (unsigned i = 0; i < 32; i++) {
        call(ctx, rw, objects[i % 4], i, i);
        call(ctx, method, objects[i % 4], 0, 73);
    }
    property_warmed();
    uint64_t before[8], after[8];
    qjs_aarch64_vm_property_counts(before);
    uint64_t ops_before[256], ops_after[256];
    qjs_aarch64_vm_opcode_counts(ops_before);
    QJSArmVMCounts vm_before, vm_after;
    qjs_aarch64_vm_counts(&vm_before);
    for (unsigned i = 0; i < 256; i++) {
        call(ctx, rw, objects[i % 4], i + 100, i + 100);
        call(ctx, method, objects[i % 4], 0, 73);
    }
    qjs_aarch64_vm_counts(&vm_after);
    qjs_aarch64_vm_property_counts(after);
    qjs_aarch64_vm_opcode_counts(ops_after);
    if (native) {
        fprintf(stderr, "PROPERTY_ROUTE secondary=%llu steps=%llu slow=%llu\n",
                (unsigned long long)(after[4] - before[4]),
                (unsigned long long)(vm_after.c_steps - vm_before.c_steps),
                (unsigned long long)(vm_after.slow_entries - vm_before.slow_entries));
        assert(after[0] - before[0] == 256 && after[1] - before[1] == 256 &&
               after[2] - before[2] == 256);
        assert(after[4] > before[4]);
        assert(ops_after[ARM_OP_get_field] == ops_before[ARM_OP_get_field]);
        assert(ops_after[ARM_OP_get_field2] == ops_before[ARM_OP_get_field2]);
        assert(ops_after[ARM_OP_put_field] == ops_before[ARM_OP_put_field]);
        // Root/tail ownership may retain its original return continuation.
        // Attribute EVERY remaining opcode step;do not mistake it for an IC
        // miss or weaken this check to allow unidentified C property work.
        for (unsigned i = 0; i < 256; i++)
            if (i != ARM_OP_return)
                assert(ops_after[i] == ops_before[i]);
        assert(ops_after[ARM_OP_return] - ops_before[ARM_OP_return] ==
               vm_after.slow_entries - vm_before.slow_entries);
    } else
        for (unsigned i = 0; i < 8; i++)
            assert(after[i] == before[i]);
    unsigned secondary = (unsigned)(after[4] - before[4]);
    JSValue fresh = JS_NewObject(ctx);
    call(ctx, put, fresh, 1, 1);
    JS_FreeValue(ctx, fresh);
    qjs_aarch64_vm_property_counts(before);
    for (unsigned i = 0; i < 128; i++) {
        fresh = JS_NewObject(ctx);
        assert(!JS_IsException(fresh));
        call(ctx, put, fresh, i, i);
        call(ctx, get, fresh, 0, i);
        JS_FreeValue(ctx, fresh);
        if (!(i % 16))
            JS_RunGC(rt);
    }
    qjs_aarch64_vm_property_counts(after);
    if (native) {
        uint32_t kinds[7];
        int sites = js_property_ic_inspect(put, kinds);
        fprintf(stderr, "PROPERTY_EMPTY sites=%d kinds=%u,%u,%u,%u,%u,%u,%u transitions=%llu\n",
                sites, kinds[0], kinds[1], kinds[2], kinds[3], kinds[4], kinds[5], kinds[6],
                (unsigned long long)(after[3] - before[3]));
        assert(sites > 0 && kinds[5]);
        // Eight public collections discard orphaned transition proofs. Their
        // next execution must relearn through C;the remaining120 are native.
        assert(after[3] - before[3] == 120);
    }
    // A continuous naturally spare-slot cohort keeps all128 proofs hot.
    fresh = JS_NewObject(ctx);
    assert(JS_SetPropertyStr(ctx, fresh, "seed", JS_NewInt32(ctx, 0)) >= 0);
    call(ctx, put, fresh, 1, 1);
    JS_FreeValue(ctx, fresh);
    qjs_aarch64_vm_property_counts(before);
    for (unsigned i = 0; i < 128; i++) {
        fresh = JS_NewObject(ctx);
        assert(!JS_IsException(fresh));
        assert(JS_SetPropertyStr(ctx, fresh, "seed", JS_NewInt32(ctx, 0)) >= 0);
        call(ctx, put, fresh, i, i);
        call(ctx, get, fresh, 0, i);
        JS_FreeValue(ctx, fresh);
    }
    qjs_aarch64_vm_property_counts(after);
    if (native) {
        uint32_t kinds[7];
        assert(js_property_ic_inspect(put, kinds) > 0 && kinds[5]);
        assert(after[3] - before[3] == 128);
    }
    unsigned transitions = (unsigned)(after[3] - before[3]);
    qjs_aarch64_vm_property_counts(before);
    qjs_aarch64_vm_opcode_counts(ops_before);
    for (unsigned i = 0; i < 128; i++) {
        fresh = JS_NewObject(ctx);
        assert(!JS_IsException(fresh));
        assert(JS_SetPropertyStr(ctx, fresh, "seedA", JS_NewInt32(ctx, 0)) >= 0);
        assert(JS_SetPropertyStr(ctx, fresh, "seedB", JS_NewInt32(ctx, 0)) >= 0);
        call(ctx, put, fresh, i, i);
        call(ctx, get, fresh, 0, i);
        JS_FreeValue(ctx, fresh);
    }
    qjs_aarch64_vm_property_counts(after);
    qjs_aarch64_vm_opcode_counts(ops_after);
    if (native) {
        uint32_t kinds[7];
        assert(js_property_ic_inspect(put, kinds) > 0 && kinds[6]);
        assert(after[3] == before[3] &&
               ops_after[ARM_OP_put_field] - ops_before[ARM_OP_put_field] == 128);
    }
    JSValue proto = JS_NewObject(ctx), child = JS_NewObjectProto(ctx, proto);
    assert(!JS_IsException(proto) && !JS_IsException(child));
    assert(JS_SetPropertyStr(ctx, proto, "value", JS_NewInt32(ctx, 41)) >= 0);
    for (unsigned i = 0; i < 8; i++)
        call(ctx, get, child, 0, 41);
    qjs_aarch64_vm_property_counts(before);
    for (unsigned i = 0; i < 64; i++) {
        assert(JS_SetPropertyStr(ctx, proto, "value", JS_NewInt32(ctx, i)) >= 0);
        call(ctx, get, child, 0, i);
    }
    qjs_aarch64_vm_property_counts(after);
    if (native)
        assert(after[6] - before[6] == 64);
    JSValue getter = JS_NewCFunction(ctx, gc_probe, "propertyGC", 0);
    JSAtom atom = JS_NewAtom(ctx, "value");
    assert(atom);
    assert(JS_DefinePropertyGetSet(ctx, proto, atom, getter, JS_UNDEFINED, JS_PROP_CONFIGURABLE) >=
           0);
    for (unsigned i = 0; i < 32; i++)
        call(ctx, get, child, 0, 91);
    assert(gc_calls == 32);
    assert(JS_DeleteProperty(ctx, proto, atom, JS_PROP_THROW) >= 0);
    JS_FreeAtom(ctx, atom);
    JSValue absent = JS_Call(ctx, get, JS_UNDEFINED, 1, &child);
    assert(JS_IsUndefined(absent));
    JS_FreeValue(ctx, absent);
    qjs_aarch64_vm_property_counts(before);
    for (unsigned i = 0; i < 32; i++) {
        absent = JS_Call(ctx, get, JS_UNDEFINED, 1, &child);
        assert(JS_IsUndefined(absent));
        JS_FreeValue(ctx, absent);
    }
    qjs_aarch64_vm_property_counts(after);
    if (native)
        assert(after[7] - before[7] == 32);
    assert(JS_SetPropertyStr(ctx, proto, "value", JS_NewInt32(ctx, 57)) >= 0);
    call(ctx, get, child, 0, 57);
    for (unsigned i = 0; i < 4; i++)
        JS_FreeValue(ctx, objects[i]);
    JS_FreeValue(ctx, proto);
    JS_FreeValue(ctx, child);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, rw);
    JS_FreeValue(ctx, get);
    JS_FreeValue(ctx, put);
    JS_FreeValue(ctx, method);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf(
        "AARCH64_PROPERTY_IC_OK native=%d four_way_secondary=%u transitions=%u proto=64 unset=32 getter_gc=%u zero_ledgers\n",
        native, secondary, transitions, gc_calls);
    return 0;
}
