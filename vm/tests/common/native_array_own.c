#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

extern bool JS_FrameFastArrayOwnGet(JSContext *, void *, uint32_t, JSValue *);
extern void JS_FrameFastArrayOwnGet_end(void);
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
    bool hit = JS_FrameFastArrayOwnGet(ctx, JS_VALUE_GET_PTR(object), index, &out);
    assert(hit == expected_hit);
    if (hit) {
        assert(JS_IsSameValue(ctx, out, expected));
        JS_FreeValue(ctx, out);
    } else
        assert(memcmp(&out, &sentinel, sizeof(out)) == 0);
    JS_FreeValue(ctx, expected);
    checks++;
}
static void unwind_leaf(void)
{
    DWORD64 base = 0;
    DWORD64 ip = (DWORD64)(uintptr_t)JS_FrameFastArrayOwnGet;
    PRUNTIME_FUNCTION row = RtlLookupFunctionEntry(ip, &base, NULL);
    assert(row && base + row->BeginAddress == ip);
    assert(base + row->EndAddress == (DWORD64)(uintptr_t)JS_FrameFastArrayOwnGet_end);
    DWORD64 stack[2] = {0x12345678};
    CONTEXT state;
    memset(&state, 0, sizeof(state));
    state.ContextFlags = CONTEXT_FULL;
    state.Rip = ip;
    state.Rsp = (DWORD64)(uintptr_t)stack;
    state.Rbx = 0x1111;
    state.R12 = 0x2222;
    state.R15 = 0x3333;
    PVOID handler = NULL;
    DWORD64 frame = 0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, ip, row, &state, &handler, &frame, NULL);
    assert(state.Rip == stack[0] && state.Rsp == (DWORD64)(uintptr_t)(stack + 1));
    assert(state.Rbx == 0x1111 && state.R12 == 0x2222 && state.R15 == 0x3333);
}
int main(void)
{
    unwind_leaf();
    JSRuntime *rt = JS_NewRuntime();
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
    assert(JS_FrameFastArrayOwnGet(ctx, JS_VALUE_GET_PTR(owner), 3, &result));
    JS_FreeValue(ctx, owner);
    assert(finalizers == 0);
    JS_FreeValue(ctx, result);
    assert(finalizers == 1);
    /* Borrowing a receiver with only one host reference is valid; a self value
     * must be duplicated before the caller releases that receiver. */
    JSValue self = JS_NewArray(ctx);
    assert(JS_DefinePropertyValueUint32(ctx, self, 3, JS_DupValue(ctx, self),
                                        JS_PROP_CONFIGURABLE) > 0);
    assert(JS_FrameFastArrayOwnGet(ctx, JS_VALUE_GET_PTR(self), 3, &result));
    assert(JS_IsSameValue(ctx, self, result));
    JS_FreeValue(ctx, self);
    JS_FreeValue(ctx, result);
    JS_RunGC(rt);
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
    printf("ARRAY OWN PASS checks=%u finalizers=%u reentries=%u getter_gc=16\n", checks, finalizers,
           reentries);
    return 0;
}
