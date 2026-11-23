#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID token_class;
static unsigned born, finalized, collections, reentries, interrupts;
static int expected_truth;
static JSValue nested_function;

static void finalize_token(JSRuntime *rt, JSValue value)
{
    (void)rt;
    unsigned *token = JS_GetOpaque(value, token_class);
    assert(token && *token && *token <= born);
    free(token);
    finalized++;
}

static JSValue visit(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 3);
    unsigned *token = JS_GetOpaque2(ctx, argv[0], token_class);
    assert(token && *token > 0 && *token <= born);
    int32_t branch;
    assert(JS_ToInt32(ctx, &branch, argv[1]) == 0);
    assert(branch == (expected_truth ? 7 : 9));
    assert(JS_ToBool(ctx, argv[2]) == !expected_truth);
    JS_RunGC(JS_GetRuntime(ctx));
    collections++;
    JSValue number = JS_NewFloat64(ctx, NAN);
    JSValue result = JS_Call(ctx, nested_function, JS_UNDEFINED, 1, &number);
    assert(!JS_IsException(result) && JS_ToBool(ctx, result) == 1);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, number);
    reentries++;
    assert(JS_GetOpaque(argv[0], token_class) == token);
    return JS_DupValue(ctx, argv[0]);
}

static void execute(JSContext *ctx, const char *source)
{
    JSValue result =
        JS_Eval(ctx, source, strlen(source), "<number-truth-host>", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "Number truth host: %s\n", text ? text : "<exception>");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, error);
        abort();
    }
    JS_FreeValue(ctx, result);
}

static int interrupt(JSContext *ctx, void *opaque)
{
    (void)opaque;
    JS_RunGC(JS_GetRuntime(ctx));
    interrupts++;
    return interrupts == 3;
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    assert(JS_NewClassID(rt, &token_class) != 0);
    JSClassDef def = {0};
    def.class_name = "NumberTruthToken";
    def.finalizer = finalize_token;
    assert(JS_NewClass(rt, token_class, &def) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "visit", JS_NewCFunction(ctx, visit, "visit", 3)) >= 0);
    execute(ctx, "function seedTruth(){return {};}for(let i=0;i<20;i++)seedTruth();"
                 "function nestedTruth(v){return !v;}"
                 "function numberOwner(v,o){let n;if(v)n=7;else n=9;return visit(o,n,!v);}");
    JSValue driver = JS_GetPropertyStr(ctx, global, "numberOwner");
    assert(JS_IsFunction(ctx, driver));
    nested_function = JS_GetPropertyStr(ctx, global, "nestedTruth");
    assert(JS_IsFunction(ctx, nested_function));
    const double values[] = {0.25, -0.25, -0.0, NAN, INFINITY, DBL_MIN};
    for (unsigned pass = 0; pass < 40; pass++)
        for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++) {
            expected_truth = !isnan(values[i]) && values[i] != 0;
            JSValue token = JS_NewObjectClass(ctx, token_class);
            assert(!JS_IsException(token));
            unsigned *identity = malloc(sizeof(*identity));
            assert(identity);
            *identity = ++born;
            JS_SetOpaque(token, identity);
            JSValue argv[] = {JS_NewFloat64(ctx, values[i]), token};
            JSValue result = JS_Call(ctx, driver, JS_UNDEFINED, 2, argv);
            assert(!JS_IsException(result) && JS_GetOpaque(result, token_class) == identity);
            JS_FreeValue(ctx, result);
            JS_FreeValue(ctx, argv[0]);
            JS_FreeValue(ctx, token);
            assert(finalized == born);
        }
    JS_SetInterruptHandler(rt, interrupt, NULL);
    const char *loop = "(function(v){let n=0;for(;;){if(v)n++;else n--;}})(0.25)";
    JSValue result =
        JS_Eval(ctx, loop, strlen(loop), "<number-truth-interrupt>", JS_EVAL_TYPE_GLOBAL);
    assert(JS_IsException(result) && interrupts == 3);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    execute(ctx, "if(nestedTruth(NaN)!==true||nestedTruth(0.25)!==false)throw Error('recovery');");
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, nested_function);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(born == 240 && finalized == born && collections == 240 && reentries == 240);
    printf("NUMBER_TRUTH_HOST_OK born=%u finalized=%u collections=%u reentries=%u interrupts=%u\n",
           born, finalized, collections, reentries, interrupts);
    return 0;
}
