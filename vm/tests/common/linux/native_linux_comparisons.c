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
#include "../native_oom_allocator.h"

_Static_assert(sizeof(JSValue) == 16 && JS_TAG_OBJECT == -1 && JS_TAG_SYMBOL == -8 &&
                   JS_TAG_BOOL == 1,
               "strict identity leaf value/tag ABI");
#ifdef QJS_TEST_DIRECT_COMPARISON
extern int JS_LinuxStrictIdentitySlow(JSContext *, JSValue *, bool);
#else
static JSValue comparison_functions[2];
#endif
static JSClassID finalizer_class;
static unsigned finalizer_count, finalizer_order[16];

static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    assert(finalizer_count < 16);
    finalizer_order[finalizer_count++] = (unsigned)(uintptr_t)JS_GetOpaque(value, finalizer_class);
}
static JSValue object(JSContext *ctx, unsigned id)
{
    JSValue value = JS_NewObjectClass(ctx, finalizer_class);
    assert(!JS_IsException(value));
    JS_SetOpaque(value, (void *)(uintptr_t)id);
    return value;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "strict-identity.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(value));
    return value;
}
static JSValue floating(double d)
{
    JSValue value;
    value.tag = JS_TAG_FLOAT64;
    value.u.float64 = d;
    return value;
}
/* The helper consumes both slots, replaces slot0, and leaves popping to its
 * interpreter caller. Never release the stale, already-consumed slot1. */
static void consume(JSContext *ctx, JSValue left, JSValue right, bool invert, bool expected)
{
    JSValue values[] = {left, right};
#ifdef QJS_TEST_DIRECT_COMPARISON
    assert(JS_LinuxStrictIdentitySlow(ctx, values + 2, invert) == 0);
#else
    JSValue result = JS_Call(ctx, comparison_functions[invert ? 1 : 0], JS_UNDEFINED, 2, values);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, left);
    JS_FreeValue(ctx, right);
    values[0] = result;
#endif
    assert(JS_IsBool(values[0]) && JS_ToBool(ctx, values[0]) == (expected ^ invert));
    JS_FreeValue(ctx, values[0]);
}

static JSValue maker(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    int id = 0;
    assert(argc == 1 && JS_ToInt32(ctx, &id, argv[0]) == 0);
    return object(ctx, (unsigned)id);
}
static void vm_last_owners(JSContext *ctx)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "makeCompareObject",
                             JS_NewCFunction(ctx, maker, "makeCompareObject", 1)) >= 0);
    JS_FreeValue(ctx, global);
    JSValue result = evaluate(ctx, "makeCompareObject(6)===makeCompareObject(7)");
    assert(JS_IsBool(result) && !JS_ToBool(ctx, result));
    JS_FreeValue(ctx, result);
    assert(finalizer_count == 7 && finalizer_order[5] == 6 && finalizer_order[6] == 7);
    result = evaluate(ctx, "(()=>{let x=makeCompareObject(8);return x===x})()");
    assert(JS_ToBool(ctx, result) == 1);
    JS_FreeValue(ctx, result);
    assert(finalizer_count == 8 && finalizer_order[7] == 8);
    result = evaluate(ctx, "makeCompareObject(9)==null");
    assert(JS_ToBool(ctx, result) == 0);
    JS_FreeValue(ctx, result);
    assert(finalizer_count == 9 && finalizer_order[8] == 9);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static const char oom_program[] =
    "(()=>{return ()=>{let a='x'.repeat(8192)+'b',b=['x'.repeat(8192),'b'].join('');"
    "let o={[Symbol.toPrimitive](hint){if(hint!=='default')throw Error('hint');gcPort();return a}};"
    "if(!(a===b)||!(b==o)||o!=b)throw Error('compare');"
    "let s=Symbol('kept');if(s!==s||({})==null)throw Error('identity');return 'ok';};})()";
static size_t oom_trial(size_t fault)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "gcPort", JS_NewCFunction(ctx, collect, "gcPort", 0)) >=
           0);
    JS_FreeValue(ctx, global);
    JSValue fn = evaluate(ctx, oom_program);
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    size_t start = memory.sequence;
    memory.fail_at = fault ? start + fault : 0;
    result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t count = memory.sequence - start;
    if (JS_IsException(result))
        JS_FreeValue(ctx, JS_GetException(ctx));
    else
        JS_FreeValue(ctx, result);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(result));
    const char *text = JS_ToCString(ctx, result);
    assert(text && !strcmp(text, "ok"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    return count;
}
static int interrupt(JSRuntime *rt, void *opaque)
{
    unsigned *count = opaque;
    ++*count;
    JS_RunGC(rt);
    return *count == 3;
}
static void interrupt_recovery(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    unsigned polls = 0;
    JSValue fn = evaluate(
        ctx,
        "(function(){let x={},s=Symbol('s'),i=0;while(i<10000000){if(x!==x||s!==s||x==null)throw Error('compare');++i;}return i;})");
    JS_SetInterruptHandler(rt, interrupt, &polls);
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(JS_IsException(result) && polls == 3);
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_FreeValue(ctx, fn);
    result = evaluate(ctx, "(()=>{let x={};return x===x&&x!=null})()");
    assert(JS_ToBool(ctx, result) == 1);
    JS_FreeValue(ctx, result);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        size_t count = oom_trial(0);
        for (size_t i = 1; i <= count + 2; ++i)
            oom_trial(i);
        printf("LINUX_COMPARISON_OOM_OK allocations=%zu\n", count);
        return 0;
    }
    interrupt_recovery();
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
#ifndef QJS_TEST_DIRECT_COMPARISON
    comparison_functions[0] = evaluate(ctx, "(function(a,b){return a===b;})");
    comparison_functions[1] = evaluate(ctx, "(function(a,b){return a!==b;})");
#endif
    JSValue symbol = evaluate(ctx, "Symbol('same')"), plain = JS_NewObject(ctx);
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_FALSE,
                        JS_TRUE,
                        JS_NewInt32(ctx, -1),
                        JS_NewInt32(ctx, 0),
                        JS_NewInt32(ctx, 1),
                        floating(-0.0),
                        floating(NAN),
                        floating(INFINITY),
                        floating(1.0),
                        floating(1.5),
                        JS_NewBigInt64(ctx, 0),
                        JS_NewBigInt64(ctx, 1),
                        evaluate(ctx, "2n**90n"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "different"),
                        evaluate(ctx, "'a'.repeat(32)+'b'.repeat(32)"),
                        JS_DupValue(ctx, symbol),
                        JS_DupValue(ctx, symbol),
                        evaluate(ctx, "Symbol('same')"),
                        JS_DupValue(ctx, plain),
                        JS_DupValue(ctx, plain),
                        JS_NewObject(ctx)};
    unsigned count = sizeof(values) / sizeof(values[0]), calls = 0;
    for (unsigned round = 0; round < 3; round++)
        for (unsigned i = 0; i < count; i++)
            for (unsigned j = 0; j < count; j++) {
                bool expected = JS_IsStrictEqual(ctx, values[i], values[j]);
                for (int invert = 0; invert < 2; invert++) {
                    consume(ctx, JS_DupValue(ctx, values[i]), JS_DupValue(ctx, values[j]),
                            invert != 0, expected);
                    calls++;
                }
                if ((calls & 127) == 0)
                    JS_RunGC(rt);
            }
    JS_NewClassID(rt, &finalizer_class);
    JSClassDef definition = {0};
    definition.class_name = "StrictIdentityFinalizer";
    definition.finalizer = finalize;
    assert(JS_NewClass(rt, finalizer_class, &definition) == 0);
    consume(ctx, object(ctx, 1), object(ctx, 2), false, false);
    assert(finalizer_count == 2 && finalizer_order[0] == 1 && finalizer_order[1] == 2);
    JSValue same = object(ctx, 3);
    consume(ctx, same, JS_DupValue(ctx, same), true, true);
    assert(finalizer_count == 3 && finalizer_order[2] == 3);
    JSValue anchored = object(ctx, 4);
    consume(ctx, JS_DupValue(ctx, anchored), JS_DupValue(ctx, anchored), false, true);
    assert(finalizer_count == 3);
    JS_FreeValue(ctx, anchored);
    assert(finalizer_count == 4);
    JSValue cycle = object(ctx, 5);
    assert(JS_SetPropertyStr(ctx, cycle, "self", JS_DupValue(ctx, cycle)) > 0);
    consume(ctx, cycle, JS_DupValue(ctx, cycle), false, true);
    assert(finalizer_count == 4);
    JS_RunGC(rt);
    assert(finalizer_count == 5 && finalizer_order[4] == 5);
    vm_last_owners(ctx);
    for (unsigned i = 0; i < count; i++)
        JS_FreeValue(ctx, values[i]);
    JS_FreeValue(ctx, symbol);
    JS_FreeValue(ctx, plain);
    JS_RunGC(rt);
#ifndef QJS_TEST_DIRECT_COMPARISON
    JS_FreeValue(ctx, comparison_functions[0]);
    JS_FreeValue(ctx, comparison_functions[1]);
#endif
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf("STRICT IDENTITY PASS differential=%u finalizers=%u\n", calls, finalizer_count);
    puts("LINUX_COMPARISON_API_OK");
    return 0;
}
