#include "quickjs-interpreter-private.h"
extern int JS_FrameInstanceOf(JSContext *, JSValueConst, JSValueConst);
static int callbacks;
static int cancel;
static int interrupt(JSRuntime *rt, void *opaque)
{
    callbacks++;
    return cancel;
}
extern int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *, JSValue *);

#define LEAF_CHECK(c)                                                                              \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            fprintf(stderr, "FAIL line %d\n", __LINE__);                                           \
            return __LINE__;                                                                       \
        }                                                                                          \
    } while (0)

static JSValue detached_function(JSContext *ctx)
{
    const char *s = "(function F(){})";
    JSValue f = JS_Eval(ctx, s, strlen(s), "alias.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(f))
        return f;
    JSValue p = JS_GetPropertyStr(ctx, f, "prototype");
    if (JS_IsException(p) || JS_SetPropertyStr(ctx, p, "constructor", JS_UNDEFINED) < 0)
        return JS_EXCEPTION;
    JS_FreeValue(ctx, p);
    return f;
}

static int leaf_ownership_oracle(JSContext *ctx)
{
    const char *seed = "(function leafSeed(){return ({}) instanceof Object;})()";
    JSValue initialized = JS_Eval(ctx, seed, strlen(seed), "leaf-config.js", JS_EVAL_TYPE_GLOBAL);
    LEAF_CHECK(!JS_IsException(initialized));
    JS_FreeValue(ctx, initialized);
    JSValue f = detached_function(ctx);
    LEAF_CHECK(!JS_IsException(f));
    JSValue proto = JS_GetPropertyStr(ctx, f, "prototype");
    JSValue v = JS_NewObjectProto(ctx, proto);
    JS_FreeValue(ctx, proto);
    ctx->interrupt_counter = 10000;
    LEAF_CHECK(JS_FrameInstanceOf(ctx, v, f) == 1);
    int enabled =
        !(getenv("QJS_DISABLE_FRAME_INSTANCEOF_LEAF") || getenv("QJS_DISABLE_FRAME_INSTANCEOF") ||
          getenv("QJS_DISABLE_FRAME_INSTANCEOF_STEP") || getenv("QJS_DISABLE_FRAME_SLOW_DIRECT") ||
          getenv("QJS_OBSERVE_FRAME_INSTANCEOF") || getenv("QJS_DISABLE_INTERP_FRAME") ||
          getenv("QJS_DISABLE_INTERNAL_INTERP") || getenv("QJS_DISABLE_REGISTER_INTERP"));
    int cases = 0;
    for (int counter = 0; counter < 5; ++counter) {
        JSValue slots[2] = {JS_DupValue(ctx, v), JS_DupValue(ctx, f)};
        int vr = JS_VALUE_GET_OBJ(v)->header.ref_count;
        int fr = JS_VALUE_GET_OBJ(f)->header.ref_count;
        ctx->interrupt_counter = counter;
        int admitted = JS_FrameSlowDirectTryInstanceOfLeaf(ctx, slots + 2);
        LEAF_CHECK(admitted == (enabled && counter > 1));
        if (admitted) {
            LEAF_CHECK(JS_IsBool(slots[0]) && JS_VALUE_GET_INT(slots[0]) == 1);
            LEAF_CHECK(JS_VALUE_GET_OBJ(v)->header.ref_count == vr - 1);
            LEAF_CHECK(JS_VALUE_GET_OBJ(f)->header.ref_count == fr - 1);
            LEAF_CHECK(ctx->interrupt_counter == counter - 1);
        } else {
            LEAF_CHECK(JS_VALUE_GET_OBJ(slots[0]) == JS_VALUE_GET_OBJ(v));
            LEAF_CHECK(JS_VALUE_GET_OBJ(slots[1]) == JS_VALUE_GET_OBJ(f));
            LEAF_CHECK(JS_VALUE_GET_OBJ(v)->header.ref_count == vr);
            LEAF_CHECK(JS_VALUE_GET_OBJ(f)->header.ref_count == fr);
            LEAF_CHECK(ctx->interrupt_counter == counter);
            JS_FreeValue(ctx, slots[0]);
            JS_FreeValue(ctx, slots[1]);
        }
        ++cases;
    }
    /* A temporary function with its prototype constructor cycle removed has
       exactly the two references in these aliased operands. It must reject. */
    JSValue alias = detached_function(ctx);
    LEAF_CHECK(!JS_IsException(alias) && JS_VALUE_GET_OBJ(alias)->header.ref_count == 1);
    JSValue pair[2] = {alias, JS_DupValue(ctx, alias)};
    ctx->interrupt_counter = 10000;
    LEAF_CHECK(!JS_FrameSlowDirectTryInstanceOfLeaf(ctx, pair + 2));
    LEAF_CHECK(JS_VALUE_GET_OBJ(alias)->header.ref_count == 2 && ctx->interrupt_counter == 10000);
    JS_FreeValue(ctx, pair[0]);
    JS_FreeValue(ctx, pair[1]);
    ++cases;

    alias = detached_function(ctx);
    LEAF_CHECK(!JS_IsException(alias) && JS_VALUE_GET_OBJ(alias)->header.ref_count == 1);
    pair[0] = JS_DupValue(ctx, alias);
    pair[1] = JS_DupValue(ctx, alias);
    ctx->interrupt_counter = 10000;
    int admitted = JS_FrameSlowDirectTryInstanceOfLeaf(ctx, pair + 2);
    LEAF_CHECK(admitted == enabled);
    if (admitted) {
        LEAF_CHECK(JS_IsBool(pair[0]) && JS_VALUE_GET_INT(pair[0]) == 0);
        LEAF_CHECK(JS_VALUE_GET_OBJ(alias)->header.ref_count == 1 &&
                   ctx->interrupt_counter == 9999);
    } else {
        LEAF_CHECK(JS_VALUE_GET_OBJ(alias)->header.ref_count == 3 &&
                   ctx->interrupt_counter == 10000);
        JS_FreeValue(ctx, pair[0]);
        JS_FreeValue(ctx, pair[1]);
    }
    JS_FreeValue(ctx, alias);
    ++cases;

    pair[0] = JS_NewObject(ctx);
    pair[1] = JS_DupValue(ctx, f);
    ctx->interrupt_counter = 10000;
    LEAF_CHECK(!JS_FrameSlowDirectTryInstanceOfLeaf(ctx, pair + 2));
    LEAF_CHECK(JS_VALUE_GET_OBJ(pair[0])->header.ref_count == 1 && ctx->interrupt_counter == 10000);
    JS_FreeValue(ctx, pair[0]);
    JS_FreeValue(ctx, pair[1]);
    ++cases;
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, f);
    printf("LEAF-OWNERSHIP-POLL-ORACLE %d enabled=%d\n", cases, enabled);
    return 0;
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = JS_NewContext(rt);
    const char *source = "function F(){};var instance=new F();";
    JSValue init = JS_Eval(ctx, source, strlen(source), "poll-init.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(init))
        return 2;
    JS_FreeValue(ctx, init);
    JSValue global = JS_GetGlobalObject(ctx), f = JS_GetPropertyStr(ctx, global, "F"),
            v = JS_GetPropertyStr(ctx, global, "instance");
    if (JS_IsInstanceOf(ctx, v, f) != 1)
        return 3;
    JS_SetInterruptHandler(rt, interrupt, NULL);
    int counters[] = {0, 1, 2, 3, 10, 9999};
    for (int c = 0; c < 2; c++)
        for (unsigned i = 0; i < sizeof(counters) / sizeof(counters[0]); i++) {
            cancel = c;
            callbacks = 0;
            ctx->interrupt_counter = counters[i];
            int original = JS_IsInstanceOf(ctx, v, f), original_counter = ctx->interrupt_counter,
                original_callbacks = callbacks;
            if (original < 0) {
                JSValue e = JS_GetException(ctx);
                JS_FreeValue(ctx, e);
            }
            callbacks = 0;
            ctx->interrupt_counter = counters[i];
            int candidate = JS_FrameInstanceOf(ctx, v, f),
                candidate_counter = ctx->interrupt_counter;
            if (candidate < 0) {
                JSValue e = JS_GetException(ctx);
                JS_FreeValue(ctx, e);
            }
            printf("POLL %d %d %d/%d %d/%d %d/%d\n", c, counters[i], original, candidate,
                   original_counter, candidate_counter, original_callbacks, callbacks);
            if (original != candidate || original_counter != candidate_counter ||
                original_callbacks != callbacks)
                return 4;
        }
    JS_SetInterruptHandler(rt, NULL, NULL);
    ctx->interrupt_counter = 10000;
    int leaf_result = leaf_ownership_oracle(ctx);
    if (leaf_result)
        return leaf_result;
    JS_FreeValue(ctx, f);
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("POLL-ORACLE-OK");
    return 0;
}
