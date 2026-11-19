#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "tests/common/native_oom_allocator.h"

extern bool JS_AArch64FastArrayOwnGet(JSContext *, void *, uint32_t, JSValue *);
#ifdef QJS_AARCH64_VM_INSTRUMENT
extern void qjs_aarch64_vm_array_own_counts(uint64_t words[4]);
#ifdef QJS_TEST_AARCH64_INDEXED
extern void qjs_aarch64_vm_indexed_counts(uint64_t words[10]);
#endif
#endif
static unsigned checks, finalizers, reentries;
static JSClassID finalizer_class;
static JSContext *reentry_context;
static JSValue reentry_function;

static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "array-own.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(value));
    return value;
}
static JSValue floating(double number)
{
    JSValue value;
    value.tag = JS_TAG_FLOAT64;
    value.u.float64 = number;
    return value;
}
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    finalizers++;
    if (reentry_context) {
        JSValue result = JS_Call(reentry_context, reentry_function, JS_UNDEFINED, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result));
        assert(JS_ToInt32(reentry_context, &number, result) == 0 && number == 43);
        JS_FreeValue(reentry_context, result);
        reentries++;
    }
}
static JSValue temporary_array(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue array = JS_NewArray(ctx), resource = JS_NewObjectClass(ctx, finalizer_class);
    assert(!JS_IsException(array) && !JS_IsException(resource));
    assert(JS_DefinePropertyValueUint32(ctx, array, 3, JS_NewInt32(ctx, 42), JS_PROP_CONFIGURABLE) >
           0);
    assert(JS_SetPropertyUint32(ctx, array, 5, resource) > 0);
    return array;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static void check(JSContext *ctx, JSValueConst object, uint32_t index, bool expected_hit)
{
    char key[32];
    snprintf(key, sizeof(key), "%lu", (unsigned long)index);
    /* String-key lookup reaches the independent generic property algorithm,
     * not the integer helper that this candidate routes. */
    JSValue expected = JS_GetPropertyStr(ctx, object, key), out = JS_NewInt32(ctx, 1234567),
            sentinel = out;
    assert(!JS_IsException(expected));
    bool hit = JS_AArch64FastArrayOwnGet(ctx, JS_VALUE_GET_PTR(object), index, &out);
    assert(hit == expected_hit);
    if (hit) {
        assert(JS_IsSameValue(ctx, out, expected));
        JS_FreeValue(ctx, out);
    } else
        assert(memcmp(&out, &sentinel, sizeof(out)) == 0);
    JS_FreeValue(ctx, expected);
    checks++;
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue array = JS_NewArray(ctx);
    assert(!JS_IsException(array));
    /* Non-default data attributes force a shape-backed array. Reads still
     * accept readonly data, while getters/prototype holes must miss. */
    assert(JS_DefinePropertyValueUint32(ctx, array, 3, JS_NewInt32(ctx, 7),
                                        JS_PROP_CONFIGURABLE | JS_PROP_ENUMERABLE) > 0);
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_FALSE,
                        JS_TRUE,
                        JS_NewInt32(ctx, -1),
                        JS_NewInt32(ctx, INT32_MAX),
                        floating(-0.0),
                        floating(NAN),
                        floating(INFINITY),
                        floating(1.5),
                        JS_NewBigInt64(ctx, 1),
                        eval(ctx, "2n**90n"),
                        JS_NewString(ctx, "hello"),
                        eval(ctx, "'x'.repeat(4096)+'y'.repeat(4096)"),
                        eval(ctx, "Symbol('value')"),
                        JS_NewObject(ctx),
                        JS_NewArray(ctx),
                        eval(ctx, "(function f(){})")};
    unsigned count = sizeof(values) / sizeof(values[0]);
    for (unsigned round = 0; round < 8; round++) {
        for (unsigned i = 0; i < count; i++) {
            assert(JS_SetPropertyUint32(ctx, array, 10 + i, JS_DupValue(ctx, values[i])) > 0);
            check(ctx, array, 10 + i, true);
        }
        JSAtom key = JS_NewAtom(ctx, "10");
        assert(key);
        assert(JS_DeleteProperty(ctx, array, key, JS_PROP_THROW) > 0);
        JS_FreeAtom(ctx, key);
        check(ctx, array, 10, false);
        assert(JS_SetPropertyUint32(ctx, array, 1000 + round, JS_NewInt32(ctx, round)) > 0);
        check(ctx, array, 1000 + round, true);
        check(ctx, array, 3, true);
        JS_RunGC(rt);
    }
    const uint32_t indices[] = {0x7ffffffeu, 0x7fffffffu, 0x80000000u, 0xfffffffeu, 0xffffffffu};
    for (unsigned i = 0; i < sizeof(indices) / sizeof(indices[0]); i++) {
        assert(JS_SetPropertyUint32(ctx, array, indices[i], JS_NewInt32(ctx, (int)i)) > 0);
        check(ctx, array, indices[i], indices[i] <= INT32_MAX);
    }
    JSValue dense = eval(ctx, "[1,2,3]");
    check(ctx, dense, 1, true);
    check(ctx, dense, 9, false);
    JS_FreeValue(ctx, dense);
    JSValue typed = eval(ctx, "new Int32Array([1,-2,3])");
    check(ctx, typed, 1, true);
    check(ctx, typed, 9, false);
    JS_FreeValue(ctx, typed);
    typed = eval(ctx, "new Float64Array([NaN,-0,Infinity])");
    check(ctx, typed, 0, true);
    check(ctx, typed, 1, true);
    JS_FreeValue(ctx, typed);
    typed = eval(ctx, "new BigInt64Array([1n,-2n,9223372036854775807n])");
    check(ctx, typed, 2, true);
    /* A native miss must preserve the complete allocating typed-array owner.
     * Force the actual first large-BigInt allocation, then recover in place. */
    JSValue faulted = JS_UNDEFINED;
    unsigned rejected_before = memory.rejected;
    memory.fail_at = memory.sequence + 1;
    bool allocated = JS_AArch64FastArrayOwnGet(ctx, JS_VALUE_GET_PTR(typed), 2, &faulted);
    memory.fail_at = 0;
    assert(memory.rejected == rejected_before + 1 && allocated && JS_IsException(faulted));
    JSValue allocation_error = JS_GetException(ctx);
    assert(!JS_IsUndefined(allocation_error));
    JS_FreeValue(ctx, allocation_error);
    check(ctx, typed, 2, true);
    puts("ARRAY_OWN_TYPED_FALLBACK_OOM_RECOVERED");
    JS_FreeValue(ctx, typed);
    JSValue inherited = eval(
        ctx,
        "(()=>{let p=[];p[5]=19;let a=[];Object.defineProperty(a,'1',{value:1});Object.setPrototypeOf(a,p);return a})()");
    check(ctx, inherited, 5, false);
    JS_FreeValue(ctx, inherited);
    JSValue getter = eval(
        ctx,
        "(()=>{globalThis.arrayOwnGets=0;let a=[];Object.defineProperty(a,'5',{get(){arrayOwnGets++;return 42}});return a})()");
    check(ctx, getter, 5, false);
    JSValue seen = eval(ctx, "arrayOwnGets===1");
    assert(JS_ToBool(ctx, seen));
    JS_FreeValue(ctx, seen);
    JS_FreeValue(ctx, getter);
    JSValue proxy =
        eval(ctx, "new Proxy([],{get(t,k,r){if(k==='5')return 21;return Reflect.get(t,k,r)}})");
    check(ctx, proxy, 5, false);
    JS_FreeValue(ctx, proxy);
    JSValue object = eval(ctx, "({5:8})");
    check(ctx, object, 5, false);
    JS_FreeValue(ctx, object);
    JS_NewClassID(rt, &finalizer_class);
    JSClassDef definition = {0};
    definition.class_name = "ArrayOwnFinalizer";
    definition.finalizer = finalize;
    assert(JS_NewClass(rt, finalizer_class, &definition) == 0);
    JSValue owner = JS_NewArray(ctx), value = JS_NewObjectClass(ctx, finalizer_class);
    assert(!JS_IsException(owner) && !JS_IsException(value));
    assert(JS_DefinePropertyValueUint32(ctx, owner, 3, value, JS_PROP_CONFIGURABLE) > 0);
    JSValue result = JS_UNDEFINED;
    assert(JS_AArch64FastArrayOwnGet(ctx, JS_VALUE_GET_PTR(owner), 3, &result));
    JS_FreeValue(ctx, owner);
    assert(finalizers == 0);
    JS_FreeValue(ctx, result);
    assert(finalizers == 1);
    /* Borrowing a receiver with only one host reference is valid; a self value
     * must be duplicated before the caller releases that receiver. */
    JSValue self = JS_NewArray(ctx);
    assert(JS_DefinePropertyValueUint32(ctx, self, 3, JS_DupValue(ctx, self),
                                        JS_PROP_CONFIGURABLE) > 0);
    assert(JS_AArch64FastArrayOwnGet(ctx, JS_VALUE_GET_PTR(self), 3, &result));
    assert(JS_IsSameValue(ctx, self, result));
    JS_FreeValue(ctx, self);
    JS_FreeValue(ctx, result);
    JS_RunGC(rt);
#ifdef QJS_AARCH64_VM_INSTRUMENT
    /* Original integer property caller, not a direct probe-only observation. */
    JSValue load = eval(ctx, "(function arrayOwnLoad(a,k){return a[k]})");
    uint64_t counts_before[4], counts_after[4];
    qjs_aarch64_vm_array_own_counts(counts_before);
    uint64_t vm_hits = 0;
#ifdef QJS_TEST_AARCH64_INDEXED
    uint64_t vm_before[10], vm_after[10];
    qjs_aarch64_vm_indexed_counts(vm_before);
#endif
    for (unsigned i = 0; i < 32; i++) {
        JSValue args[2] = {array, JS_NewInt32(ctx, 3)};
        JSValue got = JS_Call(ctx, load, JS_UNDEFINED, 2, args);
        int32_t number;
        assert(!JS_IsException(got) && !JS_ToInt32(ctx, &number, got) && number == 7);
        JS_FreeValue(ctx, got);
    }
    qjs_aarch64_vm_array_own_counts(counts_after);
#ifdef QJS_TEST_AARCH64_INDEXED
    qjs_aarch64_vm_indexed_counts(vm_after);
    vm_hits = vm_after[3] - vm_before[3];
    unsigned native_indexed = !getenv("QJS_DISABLE_REGISTER_INTERP") &&
                              !getenv("QJS_DISABLE_INTERP_FRAME") &&
                              !getenv("QJS_DISABLE_FRAME_INDEXED_OWN");
    assert(vm_hits == (native_indexed ? 32 : 0));
#endif
    /* The new same-activation VM leaf supersedes the original C consumer.
     * Prove exactly one complete path per original caller,and require the
     * C helper under either broad VM OFF or the independent own-leaf OFF. */
    assert(counts_after[1] - counts_before[1] == 32 - vm_hits);
    assert(counts_after[0] - counts_before[0] == 32 - vm_hits);
    assert(counts_after[2] == counts_before[2]);
    assert(counts_after[0] == counts_after[1] + counts_after[2]);
    assert(counts_after[1] > 160 && counts_after[2] > 0 && counts_after[3] == 0);
    printf(
        "ARRAY_OWN_NATIVE_PATH_OK original_caller_hits=32 vm_indexed_hits=%llu entries=%llu hits=%llu fallback=%llu\n",
        (unsigned long long)vm_hits, (unsigned long long)counts_after[0],
        (unsigned long long)counts_after[1], (unsigned long long)counts_after[2]);
    JS_FreeValue(ctx, load);
#endif
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "arrayOwnTemporary",
                             JS_NewCFunction(ctx, temporary_array, "arrayOwnTemporary", 0)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "arrayOwnCollect",
                             JS_NewCFunction(ctx, collect, "arrayOwnCollect", 0)) > 0);
    /* Keep the project's existing JS reentry stress, without introducing an
     * explicit nested GC from a finalizer. GC runs in the legal getter below. */
    reentry_function = eval(ctx, "(function arrayOwnReenter(){return 43})");
    reentry_context = ctx;
    JSValue consume = eval(
        ctx,
        "(function arrayOwnConsume(){let live={n:1};live.self=live;let result=arrayOwnTemporary()[3];if(live.self!==live)throw 'lost live root';return result+live.n-1})");
    unsigned before = finalizers;
    for (unsigned i = 0; i < 16; i++) {
        result = JS_Call(ctx, consume, JS_UNDEFINED, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result) && JS_ToInt32(ctx, &number, result) == 0 && number == 42);
        JS_FreeValue(ctx, result);
    }
    assert(finalizers == before + 16 && reentries == 16);
    reentry_context = NULL;
    JS_FreeValue(ctx, reentry_function);
    JS_FreeValue(ctx, consume);
    JS_FreeValue(ctx, global);
    JSValue getter_gc = eval(
        ctx,
        "(function arrayOwnGetterGC(){let live={n:42};live.self=live;let a=[];Object.defineProperty(a,'3',{get(){arrayOwnCollect();return live}});let loaded=a[3];if(loaded!==live||live.self!==live)throw 'getter lost root';return loaded.n})");
    for (unsigned i = 0; i < 16; i++) {
        result = JS_Call(ctx, getter_gc, JS_UNDEFINED, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result) && JS_ToInt32(ctx, &number, result) == 0 && number == 42);
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, getter_gc);
    for (unsigned i = 0; i < count; i++)
        JS_FreeValue(ctx, values[i]);
    JS_FreeValue(ctx, array);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf("ARRAY_OWN_ZERO_LEDGERS peak=%zu attempts=%zu\n", memory.peak, memory.sequence);
    printf("ARRAY OWN PASS checks=%u finalizers=%u reentries=%u getter_gc=16\n", checks, finalizers,
           reentries);
    return 0;
}
