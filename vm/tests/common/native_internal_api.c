#include "src/common/internal/upstream-compat.h"
#include "interpreter-private-abi-values.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
/* Internal seven-argument ABI, borrowed roots, lifetime and unwind checks. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "quickjs.h"

#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "internal entry check failed: %s:%d: %s\n", __FILE__, __LINE__, #x);   \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                        JSValueConst *, int);
extern JSValue qjs_frame_core_JS_CallInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst,
                                              int, JSValueConst *, int);
extern JSValue JS_FrameCEntry(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                              JSValueConst *, int);
extern void internal_select(void);
typedef JSValue (*InternalEntry)(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                 JSValueConst *, int);
static JSClassID resource_class;
static int finalized, reentries;
static JSContext *reentry_ctx;
static JSValue reentry_func;
static uintptr_t probe_stack;
static JSValue expected_this, expected_result;
static JSValue *released_root_args;
static uintptr_t budget_base_top;
static unsigned budget_finalizers, budget_interrupts;
static JSValue budget_reentry_func;
static uintptr_t runtime_word(JSRuntime *rt, size_t offset);

static void expect(JSContext *ctx, JSValue value, int expected)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "internal entry exception: %s\n", message ? message : "<unprintable>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        exit(1);
    }
    int32_t actual;
    CHECK(!JS_ToInt32(ctx, &actual, value) && actual == expected);
    JS_FreeValue(ctx, value);
}

static JSValue eval(JSContext *ctx, const char *source)
{
    return JS_Eval(ctx, source, strlen(source), "internal-interpreter-api", JS_EVAL_TYPE_GLOBAL);
}

static void finalizer(JSRuntime *rt, JSValue value)
{
    finalized++;
    if (reentry_ctx) {
        uintptr_t top = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top),
                  limit = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit);
        if (top > budget_base_top)
            budget_finalizers++;
        expect(reentry_ctx, JS_Call(reentry_ctx, reentry_func, JS_UNDEFINED, 0, NULL), 42);
        CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == top &&
              runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit) == limit);
        reentries++;
    }
}

static JSValue produce(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    JSValue value = JS_NewObjectClass(ctx, resource_class);
    if (!JS_IsException(value))
        CHECK(JS_SetPropertyStr(ctx, value, "value", JS_NewInt32(ctx, 40)) >= 0);
    return value;
}

static JSValue count_finalized(JSContext *ctx, JSValueConst this_value, int argc,
                               JSValueConst *argv)
{
    return JS_NewInt32(ctx, finalized);
}

static JSValue return_host(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    CHECK(argc == 1);
    return JS_DupValue(ctx, argv[0]);
}

static JSValue collect(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}

static JSValue resize_stack(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    int32_t bytes;
    CHECK(argc == 1 && !JS_ToInt32(ctx, &bytes, argv[0]) && bytes >= 0);
    JS_SetMaxStackSize(JS_GetRuntime(ctx), (size_t)bytes);
    return JS_UNDEFINED;
}

static JSValue release_root(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    CHECK(released_root_args);
    JS_FreeValue(ctx, released_root_args[0]);
    released_root_args[0] = JS_UNDEFINED;
    return JS_UNDEFINED;
}

/* The backend's compile-time assertions and PDB/DWARF checks bind these
 * offsets to the unchanged original runtime. Verify observable API updates
 * survive both normal returns and unlimited/limited transitions in callbacks. */
static uintptr_t runtime_word(JSRuntime *rt, size_t offset)
{
    uintptr_t value;
    memcpy(&value, (unsigned char *)rt + offset, sizeof(value));
    return value;
}

static JSValue budget_probe(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    uintptr_t top = runtime_word(JS_GetRuntime(ctx), QJS_ABI_OFF_JSRuntime_stack_top);
    CHECK(top >= budget_base_top && top - budget_base_top < 1024 * 1024);
    return JS_NewInt32(ctx, (int32_t)(top - budget_base_top));
}

static JSValue budget_reenter(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    uintptr_t top = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top),
              limit = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit);
    JSValue argument = JS_NewInt32(ctx, 8);
    JSValue result = JS_Call(ctx, budget_reentry_func, JS_UNDEFINED, 1, &argument);
    int32_t nested;
    CHECK(!JS_IsException(result) && !JS_ToInt32(ctx, &nested, result));
    JS_FreeValue(ctx, result);
    CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == top &&
          runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit) == limit);
    CHECK(top == budget_base_top ? nested == 0 : (uintptr_t)nested > top - budget_base_top);
    return JS_UNDEFINED;
}

static int budget_interrupt(FrameInterruptSource *upgrade_interrupt_source, void *opaque)
{
    JSRuntime *rt = frame_interrupt_runtime(upgrade_interrupt_source);
    JSContext *ctx = opaque;
    uintptr_t top = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top),
              limit = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit);
    if (top > budget_base_top) {
        budget_interrupts++;
        expect(ctx, JS_Call(ctx, reentry_func, JS_UNDEFINED, 0, NULL), 42);
        CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == top &&
              runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit) == limit);
    }
    return 0;
}

static JSValue probe(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    volatile unsigned char marker = 0;
    probe_stack = (uintptr_t)&marker;
    CHECK(argc == 3);
    CHECK(JS_VALUE_GET_PTR(this_value) == JS_VALUE_GET_PTR(expected_this));
    int32_t integer;
    double number;
    CHECK(!JS_ToInt32(ctx, &integer, argv[0]) && integer == 73);
    CHECK(!JS_ToFloat64(ctx, &number, argv[1]) && number == 1.25);
    CHECK(JS_VALUE_GET_PTR(argv[2]) == JS_VALUE_GET_PTR(expected_result));
    return JS_DupValue(ctx, argv[2]);
}

#ifdef _MSC_VER
__declspec(noinline)
#else
__attribute__((noipa))
#endif
static JSValue invoke(InternalEntry entry, JSContext *ctx, JSValueConst func,
                      JSValueConst this_value, int argc, JSValueConst *argv, int flags)
{
    return entry(ctx, func, this_value, JS_UNDEFINED, argc, argv, flags);
}

/* Cleanup destroys the last reference to a resource in every frame. Its
 * finalizer reenters JS and produces 42, clobbering the volatile return
 * registers. The original object/string/float must survive that C boundary,
 * normal and tail continuations, borrowed/copy roots and the host return ABI. */
static void check_returns(JSContext *ctx)
{
    expect(
        ctx,
        eval(ctx,
             "function returnLeaf(v){var garbage=internalResource();return v;}"
             "function returnRegular(n,v){var garbage=internalResource();"
             " if(n){var result=returnRegular(n-1,v);return result;}return returnLeaf(v);}"
             "function returnTail(n,v){var garbage=internalResource();"
             " if(n)return returnTail(n-1,v);return returnLeaf(v);}"
             "function returnHost(n,v){var garbage=internalResource();"
             " if(n)return returnHost(n-1,v);return internalReturnHost(v);}"
             "function returnUndefined(n){var garbage=internalResource();"
             " if(n){returnUndefined(n-1);return;}}"
             "function returnOwned(){var garbage=internalResource();return internalResource();}0;"),
        0);
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue values[] = {JS_NewInt32(ctx, 73), JS_NewFloat64(ctx, 1.25),
                        JS_NewString(ctx, "register-return-owned-string"),
                        produce(ctx, JS_UNDEFINED, 0, NULL)};
    const char *functions[] = {"returnRegular", "returnTail", "returnHost"};
    for (unsigned i = 0; i < sizeof(functions) / sizeof(functions[0]); i++) {
        JSValue function = JS_GetPropertyStr(ctx, global, functions[i]);
        CHECK(!JS_IsException(function));
        for (int flags = 0; flags <= 2; flags += 2) {
            for (unsigned j = 0; j < sizeof(values) / sizeof(values[0]); j++) {
                JSValue arguments[] = {JS_NewInt32(ctx, 6), values[j]};
                int before = finalized, before_reentry = reentries;
                JSValue result = invoke(JS_FrameDispatchInternal, ctx, function, JS_UNDEFINED, 2,
                                        arguments, flags);
                CHECK(!JS_IsException(result) &&
                      JS_VALUE_GET_TAG(result) == JS_VALUE_GET_TAG(values[j]));
                if (j == 0)
                    CHECK(JS_VALUE_GET_INT(result) == 73);
                else if (j == 1)
                    CHECK(JS_VALUE_GET_FLOAT64(result) == 1.25);
                else
                    CHECK(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(values[j]));
                CHECK(finalized - before == (i == 2 ? 7 : 8));
                CHECK(reentries - before_reentry == finalized - before);
                JS_FreeValue(ctx, result);
                CHECK(finalized - before == (i == 2 ? 7 : 8));
            }
        }
        JS_FreeValue(ctx, function);
    }
    JSContext *other = JS_NewContext(JS_GetRuntime(ctx));
    CHECK(other);
    JSValue other_global = JS_GetGlobalObject(other);
    CHECK(JS_SetPropertyStr(other, other_global, "internalResource",
                            JS_NewCFunction(other, produce, "internalResource", 0)) >= 0);
    CHECK(JS_SetPropertyStr(other, other_global, "internalReturnHost",
                            JS_NewCFunction(other, return_host, "internalReturnHost", 1)) >= 0);
    JSValue realm_function =
        eval(other, "(function(v){var garbage=internalResource();return internalReturnHost(v);})");
    CHECK(!JS_IsException(realm_function));
    CHECK(JS_SetPropertyStr(ctx, global, "returnOtherRealm", realm_function) >= 0);
    JSValue realm_wrapper = eval(
        ctx,
        "(function(v){var garbage=internalResource();var result=returnOtherRealm(v);return result;})");
    CHECK(!JS_IsException(realm_wrapper));
    int realm_before = finalized, realm_reentry = reentries;
    JSValue realm_result = JS_Call(ctx, realm_wrapper, JS_UNDEFINED, 1, &values[3]);
    CHECK(JS_IsObject(realm_result) &&
          JS_VALUE_GET_PTR(realm_result) == JS_VALUE_GET_PTR(values[3]));
    CHECK(finalized - realm_before == 2 && reentries - realm_reentry == 2);
    JS_FreeValue(ctx, realm_result);
    JS_FreeValue(ctx, realm_wrapper);
    CHECK(JS_SetPropertyStr(ctx, global, "returnOtherRealm", JS_UNDEFINED) >= 0);
    JS_FreeValue(other, other_global);
    JS_FreeContext(other);
    JSValue function = JS_GetPropertyStr(ctx, global, "returnUndefined");
    JSValue depth = JS_NewInt32(ctx, 6);
    int before = finalized;
    JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 1, &depth);
    CHECK(JS_IsUndefined(result) && finalized - before == 7);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, function);
    function = JS_GetPropertyStr(ctx, global, "returnOwned");
    before = finalized;
    result = JS_Call(ctx, function, JS_UNDEFINED, 0, NULL);
    CHECK(JS_IsObject(result) && finalized - before == 1);
    expect(ctx, JS_GetPropertyStr(ctx, result, "value"), 40);
    JS_FreeValue(ctx, result);
    CHECK(finalized - before == 2);
    JS_FreeValue(ctx, function);
    for (unsigned j = 0; j < sizeof(values) / sizeof(values[0]); j++)
        JS_FreeValue(ctx, values[j]);
    JS_FreeValue(ctx, global);
    CHECK(runtime_word(JS_GetRuntime(ctx), QJS_ABI_OFF_JSRuntime_stack_top) == budget_base_top);
}

static void check_unwind(void)
{
    DWORD64 base = 0;
    PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry((DWORD64)(uintptr_t)internal_select, &base, NULL);
    CHECK(fn != NULL);
    const unsigned char *start = (const unsigned char *)(uintptr_t)(base + fn->BeginAddress);
    size_t length = fn->EndAddress - fn->BeginAddress;
#ifdef _MSC_VER
    __declspec(align(16)) ULONG64 stack[16] = {0};
#else
    ULONG64 stack[16] __attribute__((aligned(16))) = {0};
#endif
    stack[9] = (ULONG64)(uintptr_t)check_unwind;
    size_t offsets[6] = {0, 4};
    int count = 2;
    for (size_t i = 4; i + 10 <= length; i++) {
        if (!memcmp(start + i, "\x48\x83\xc4\x48\xff\x25", 6)) {
            CHECK(count + 2 <= 6);
            offsets[count++] = i;
            offsets[count++] = i + 4;
        }
    }
    CHECK(count == 6);
    for (int i = 0; i < count; i++) {
        CONTEXT c = {0};
        c.ContextFlags = CONTEXT_FULL;
        c.Rip = (DWORD64)(uintptr_t)(start + offsets[i]);
        int restored = offsets[i] == 0 || start[offsets[i]] == 0xff;
        c.Rsp = (DWORD64)(uintptr_t)(stack + (restored ? 9 : 0));
        void *data = NULL;
        DWORD64 establisher = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, fn, &c, &data, &establisher, NULL);
        CHECK(c.Rip == stack[9] && c.Rsp == (DWORD64)(uintptr_t)(stack + 10));
    }
}

int main(void)
{
    check_unwind();
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    budget_base_top = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top);
    JS_NewClassID(rt, &resource_class);
    JSClassDef def = {0};
    def.class_name = "InternalEntryResource";
    def.finalizer = finalizer;
    CHECK(!JS_NewClass(rt, resource_class, &def));
    JSValue global = JS_GetGlobalObject(ctx);
    CHECK(JS_SetPropertyStr(ctx, global, "internalResource",
                            JS_NewCFunction(ctx, produce, "internalResource", 0)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalFinalized",
                            JS_NewCFunction(ctx, count_finalized, "internalFinalized", 0)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalReturnHost",
                            JS_NewCFunction(ctx, return_host, "internalReturnHost", 1)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalGC",
                            JS_NewCFunction(ctx, collect, "internalGC", 0)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalResizeStack",
                            JS_NewCFunction(ctx, resize_stack, "internalResizeStack", 1)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalReleaseRoot",
                            JS_NewCFunction(ctx, release_root, "internalReleaseRoot", 0)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalBudgetProbe",
                            JS_NewCFunction(ctx, budget_probe, "internalBudgetProbe", 0)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "internalBudgetReenter",
                            JS_NewCFunction(ctx, budget_reenter, "internalBudgetReenter", 0)) >= 0);

    expected_this = JS_NewObject(ctx);
    expected_result = JS_NewObject(ctx);
    JSValue args[3] = {JS_NewInt32(ctx, 73), JS_NewFloat64(ctx, 1.25), expected_result};
    JSValue native = JS_NewCFunction(ctx, probe, "internalProbe", 3);
    for (int flags = 0; flags <= 2; flags += 2) {
        JSValue result =
            invoke(qjs_frame_core_JS_CallInternal, ctx, native, expected_this, 3, args, flags);
        uintptr_t old_stack = probe_stack;
        CHECK(!JS_IsException(result) &&
              JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(expected_result));
        JS_FreeValue(ctx, result);
        /* The accepted C entry bypasses CallInternal's frame. Compare the
         * dispatch tail with that entry, including when it declines to C. */
        result = invoke(JS_FrameCEntry, ctx, native, expected_this, 3, args, flags);
        uintptr_t entry_stack = probe_stack;
        CHECK(!JS_IsException(result) &&
              JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(expected_result));
        CHECK(entry_stack >= old_stack);
        JS_FreeValue(ctx, result);
        for (int warm = 0; warm < 2; warm++) {
            result = invoke(JS_FrameDispatchInternal, ctx, native, expected_this, 3, args, flags);
            CHECK(!JS_IsException(result) &&
                  JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(expected_result));
            CHECK(probe_stack == entry_stack);
            JS_FreeValue(ctx, result);
        }
    }
    JS_FreeValue(ctx, native);
    JS_FreeValue(ctx, expected_result);
    JS_FreeValue(ctx, expected_this);

    expect(
        ctx,
        eval(ctx,
             "function internalOverwrite(a){a=undefined;return internalFinalized();}"
             "function internalMissing(a,b,c){return a+(b===undefined?20:b)+(c===undefined?20:c);}"
             "function internalWritable(a,b){b=2;return a+b;} 0;"),
        0);
    JSValue overwrite = JS_GetPropertyStr(ctx, global, "internalOverwrite");
    args[0] = JS_NewObjectClass(ctx, resource_class);
    expect(ctx, invoke(JS_FrameDispatchInternal, ctx, overwrite, JS_UNDEFINED, 1, args, 0), 1);
    CHECK(JS_IsUndefined(args[0]) && finalized == 1);
    args[0] = JS_NewObjectClass(ctx, resource_class);
    expect(ctx, invoke(JS_FrameDispatchInternal, ctx, overwrite, JS_UNDEFINED, 1, args, 2), 1);
    CHECK(JS_IsObject(args[0]) && finalized == 1);
    JS_FreeValue(ctx, args[0]);
    CHECK(finalized == 2);
    JSValue missing = JS_GetPropertyStr(ctx, global, "internalMissing");
    args[0] = JS_NewInt32(ctx, 2);
    for (int warm = 0; warm < 2; warm++)
        expect(ctx, invoke(JS_FrameDispatchInternal, ctx, missing, JS_UNDEFINED, 1, args, 0), 42);
    JSValue writable = JS_GetPropertyStr(ctx, global, "internalWritable");
    args[0] = JS_NewInt32(ctx, 40);
    expect(ctx, invoke(JS_FrameDispatchInternal, ctx, writable, JS_UNDEFINED, 1, args, 0), 42);

    reentry_func = eval(ctx, "(function(){return 42;})");
    CHECK(!JS_IsException(reentry_func));
    reentry_ctx = ctx;
    for (int i = 0; i < 8; i++) {
        int next = finalized + 1;
        expect(
            ctx,
            eval(
                ctx,
                "function internalLegacy(){try{return internalOverwrite(internalResource());}finally{}} internalLegacy();"),
            next);
    }
    CHECK(reentries == 8);
    expect(
        ctx,
        eval(
            ctx,
            "function budgetDepth(n){if(n)return budgetDepth(n-1);return internalBudgetProbe();}"
            "function budgetOuter(n){if(n)return budgetOuter(n-1);internalBudgetReenter();return internalBudgetProbe();}"
            "function budgetFinal(n){var value=internalResource();if(n)return budgetFinal(n-1);return 42;}"
            "function budgetLoop(n){if(n)return budgetLoop(n-1);var sum=0;for(var i=0;i<150000;i++)sum+=(i&1);return sum;}0;"),
        0);
    budget_reentry_func = JS_GetPropertyStr(ctx, global, "budgetDepth");
    JSValue budget_outer = JS_GetPropertyStr(ctx, global, "budgetOuter");
    int32_t observed[2];
    for (int i = 0; i < 2; i++) {
        args[0] = JS_NewInt32(ctx, i ? 24 : 0);
        JSValue result = JS_Call(ctx, budget_outer, JS_UNDEFINED, 1, args);
        CHECK(!JS_IsException(result) && !JS_ToInt32(ctx, &observed[i], result));
        JS_FreeValue(ctx, result);
        CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == budget_base_top);
    }
    CHECK(observed[0] ? observed[1] > observed[0] : observed[1] == 0);
    JSValue budget_final = JS_GetPropertyStr(ctx, global, "budgetFinal");
    args[0] = JS_NewInt32(ctx, 4);
    expect(ctx, JS_Call(ctx, budget_final, JS_UNDEFINED, 1, args), 42);
    CHECK(reentries == 13);
    JS_SetInterruptHandler(rt, budget_interrupt, ctx);
    JSValue budget_loop = JS_GetPropertyStr(ctx, global, "budgetLoop");
    args[0] = JS_NewInt32(ctx, 16);
    expect(ctx, JS_Call(ctx, budget_loop, JS_UNDEFINED, 1, args), 75000);
    JS_SetInterruptHandler(rt, NULL, NULL);
    if (observed[0])
        CHECK(budget_finalizers >= 5 && budget_interrupts > 0);
    CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == budget_base_top);
    JS_FreeValue(ctx, budget_loop);
    JS_FreeValue(ctx, budget_final);
    JS_FreeValue(ctx, budget_outer);
    JS_FreeValue(ctx, budget_reentry_func);
    check_returns(ctx);
    reentry_ctx = NULL;
    JS_FreeValue(ctx, reentry_func);
    expect(
        ctx,
        eval(ctx,
             "function internalLive(a,b){internalGC();return a.value+(b===undefined?2:b);}"
             "function internalLiveLegacy(){try{return internalLive(internalResource());}finally{}}"
             "internalLiveLegacy();"),
        42);
    expect(ctx,
           eval(ctx, "function internalThrow(x){throw x;}"
                     "try{internalThrow('entry-error');}catch(e){if(e!=='entry-error')throw e;}"
                     "function InternalConstructor(x){this.value=x;}"
                     "function* internalGenerator(){yield internalMissing(2);}"
                     "new InternalConstructor(42).value+internalGenerator().next().value;"),
           84);
    expect(
        ctx,
        eval(
            ctx,
            "[3,1,2].sort(function(a,b){return internalMissing(a)-internalMissing(b);})[1]+"
            "[20,20].map(function(x){return internalWritable(x);}).reduce(function(a,b){return a+b;},0);"),
        46);

    JSContext *other = JS_NewContext(rt);
    CHECK(other);
    expect(other, eval(other, "var marker=40;function internalRealm(a){return marker+a;}0;"), 0);
    JSValue other_global = JS_GetGlobalObject(other);
    JSValue realm = JS_GetPropertyStr(other, other_global, "internalRealm");
    args[0] = JS_NewInt32(ctx, 2);
    expect(ctx, invoke(JS_FrameDispatchInternal, ctx, realm, JS_UNDEFINED, 1, args, 0), 42);
    JS_FreeValue(other, realm);
    JS_FreeValue(other, other_global);
    JS_FreeContext(other);
    uintptr_t original_top = runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top);
    JSValue resize = eval(
        ctx,
        "(function internalResize(n,bytes){if(n)return internalResize(n-1,bytes);internalResizeStack(bytes);return 42;})");
    CHECK(!JS_IsException(resize));
    int sizes[] = {1024 * 1024, 0, 2 * 1024 * 1024, 1024 * 1024};
    for (unsigned i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        args[0] = JS_NewInt32(ctx, 16);
        args[1] = JS_NewInt32(ctx, sizes[i]);
        expect(ctx, JS_Call(ctx, resize, JS_UNDEFINED, 2, args), 42);
        CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_top) == original_top);
        CHECK(runtime_word(rt, QJS_ABI_OFF_JSRuntime_stack_limit) ==
              (sizes[i] ? original_top - sizes[i] : 0));
    }
    JS_FreeValue(ctx, resize);
    JSValue retain_missing =
        eval(ctx, "(function(a,b){internalReleaseRoot();return a.value+(b===undefined?2:b);})");
    CHECK(!JS_IsException(retain_missing));
    int before_released_root = finalized;
    args[0] = produce(ctx, JS_UNDEFINED, 0, NULL);
    CHECK(!JS_IsException(args[0]));
    released_root_args = args;
    expect(ctx, invoke(JS_FrameDispatchInternal, ctx, retain_missing, JS_UNDEFINED, 1, args, 0),
           42);
    CHECK(JS_IsUndefined(args[0]) && finalized == before_released_root + 1);
    released_root_args = NULL;
    JS_FreeValue(ctx, retain_missing);
    JS_FreeValue(ctx, writable);
    JS_FreeValue(ctx, missing);
    JS_FreeValue(ctx, overwrite);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts(
        "internal entry: seven-argument ABI, borrowed/copy roots, arity, finalizers/reentry, object/string/float/undefined native/host/tail returns, callbacks, realms, exceptions, stack-budget updates and C-boundary visibility/reentry/interrupts, constructors/generators and six unwind positions passed");
    return 0;
}
