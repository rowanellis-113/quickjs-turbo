/* RegExp flags: interrupt selection, abrupt completion and foreign realms. */
#include "quickjs-interpreter-private.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "REGEXP_FLAGS line %d: %s\n", __LINE__, #x);                           \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

typedef struct FlagInterrupt {
    JSContext *ctx;
    JSValue receiver;
    unsigned calls;
    int abort;
} FlagInterrupt;

static JSValue eval(JSContext *ctx, const char *source)
{
    JSValue value = JS_Eval(ctx, source, strlen(source), "regexp-flags-api", JS_EVAL_TYPE_GLOBAL);
    CHECK(!JS_IsException(value));
    return value;
}
static void expect(JSContext *ctx, JSValue value, const char *wanted)
{
    CHECK(!JS_IsException(value));
    const char *text = JS_ToCString(ctx, value);
    CHECK(text && !strcmp(text, wanted));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, value);
}
static int interrupt(JSContext *ctx, void *opaque)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    FlagInterrupt *state = opaque;
    state->calls++;
    if (state->abort)
        return 1;
    /* The first getter has already been resolved and must remain selected.
     * A later property must see this mutation. GC may release other objects. */
    CHECK(JS_DefinePropertyValueStr(state->ctx, state->receiver, "hasIndices", JS_TRUE,
                                    JS_PROP_C_W_E) >= 0);
    CHECK(JS_DefinePropertyValueStr(state->ctx, state->receiver, "global", JS_TRUE,
                                    JS_PROP_C_W_E) >= 0);
    JS_RunGC(rt);
    return 0;
}

static void symbol_names(JSRuntime *rt)
{
    /* Use a fresh realm: the public deletion sequence guarantees the slots
     * compact to the live proof's exact positions, independent of prior tests. */
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    const char *source =
        "// Public operations deliberately rebuild the canonical immediate prototype.\n"
        "// A power-of-two number of live slots compacts to an empty shape as removed.\n"
        "const proto = RegExp.prototype;\n"
        "const order = ['global','ignoreCase','multiline','dotAll','unicode','unicodeSets','sticky','hasIndices'];\n"
        "const descriptors = Object.fromEntries(order.map(n => [n,Object.getOwnPropertyDescriptor(proto,n)]));\n"
        "const getter = Object.getOwnPropertyDescriptor(proto,'flags').get;\n"
        "const rx = /x/dgimsuy;\n"
        "let count = Reflect.ownKeys(proto).length;\n"
        "let target = 8;\n"
        "while (target < count) target *= 2;\n"
        "while (count < target) {\n"
        "    Object.defineProperty(proto, 'padding'+count, {value:0,configurable:true});\n"
        "    count++;\n"
        "}\n"
        "for (const key of Reflect.ownKeys(proto)) {\n"
        "    if (!delete proto[key]) throw Error('delete failed');\n"
        "}\n"
        "Object.defineProperty(proto,'prefix0',{value:0,configurable:true});\n"
        "Object.defineProperty(proto,'prefix1',{value:0,configurable:true});\n"
        "for (const name of order) {\n"
        "    const key = name === 'global' || name === 'unicode' ? name : Symbol(name);\n"
        "    Object.defineProperty(proto,key,descriptors[name]);\n"
        "}\n"
        "const expected = 'gu';\n"
        "const actual = getter.call(rx);\n"
        "if (actual !== expected) throw Error('Symbol descriptions are not string property keys');\n"
        "actual;\n";
    expect(ctx, eval(ctx, source), "gu");
    JS_FreeContext(ctx);
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    symbol_names(rt);
    JSContext *ctx = JS_NewContext(rt), *other = JS_NewContext(rt);
    CHECK(ctx && other);
    JSValue getter = eval(ctx, "Object.getOwnPropertyDescriptor(RegExp.prototype,'flags').get");
    JSValue receiver, result;
    FlagInterrupt state = {ctx, JS_UNDEFINED, 0, 0};
    /* One public-call poll plus eight ordered getter polls. A due poll must
     * retain the already selected getter and observe later mutations. */
    for (unsigned counter = 2; counter <= 12; counter++) {
        receiver = eval(ctx, "/a/");
        state.receiver = receiver;
        state.calls = 0;
        JS_SetInterruptHandler(rt, interrupt, &state);
        ctx->interrupt_counter = counter;
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), counter == 2 ? "g" : "");
        CHECK(state.calls == (counter <= 9));
        JS_SetInterruptHandler(rt, NULL, NULL);
        JS_FreeValue(ctx, receiver);
    }
    state.abort = 1;
    for (unsigned counter = 2; counter <= 9; counter++) {
        receiver = eval(ctx, "/a/g");
        state.receiver = receiver;
        state.calls = 0;
        JS_SetInterruptHandler(rt, interrupt, &state);
        ctx->interrupt_counter = counter;
        result = JS_Call(ctx, getter, receiver, 0, NULL);
        CHECK(JS_IsException(result) && state.calls == 1);
        JS_SetInterruptHandler(rt, NULL, NULL);
        JS_FreeValue(ctx, JS_GetException(ctx));
        JS_FreeValue(ctx, receiver);
    }

    /* Borrow both outer and individual builtins from a distinct context. */
    JSValue foreign_getter =
        eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'flags').get");
    JSValue foreign_global =
        eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'sticky').get");
    receiver = eval(ctx, "/a/gm");
    CHECK(JS_DefinePropertyGetSet(ctx, receiver, JS_ATOM_global, foreign_global, JS_UNDEFINED,
                                  JS_PROP_CONFIGURABLE) >= 0);
    expect(ctx, JS_Call(ctx, foreign_getter, receiver, 0, NULL), "m");
    JSValue plain = JS_NewObject(ctx);
    JSValue foreign_flag =
        eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'global').get");
    CHECK(JS_DefinePropertyGetSet(ctx, plain, JS_ATOM_global, foreign_flag, JS_UNDEFINED,
                                  JS_PROP_CONFIGURABLE) >= 0);
    result = JS_Call(ctx, getter, plain, 0, NULL);
    CHECK(JS_IsException(result));
    JSValue error = JS_GetException(ctx), actual_proto = JS_GetPrototype(ctx, error);
    JSValue wanted_proto = eval(other, "TypeError.prototype");
    CHECK(JS_IsObject(actual_proto) && JS_IsObject(wanted_proto) &&
          JS_VALUE_GET_OBJ(actual_proto) == JS_VALUE_GET_OBJ(wanted_proto));
    JS_FreeValue(ctx, error);
    JS_FreeValue(ctx, actual_proto);
    JS_FreeValue(other, wanted_proto);
    JSValue foreign_receiver = eval(other, "/z/dg");
    expect(ctx, JS_Call(ctx, getter, foreign_receiver, 0, NULL), "dg");
    JS_FreeValue(other, foreign_receiver);
    JS_FreeValue(ctx, plain);
    JS_FreeValue(ctx, receiver);
    JS_FreeValue(other, foreign_getter);
    /* The live proof retains no per-object, per-shape or per-realm state. */
    receiver = eval(ctx, "/x/dgimsy");
    for (unsigned i = 0; i < 40; i++)
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), "dgimsy");
    JS_RunGC(rt);
    JSMemoryUsage before, after;
    JS_ComputeMemoryUsage(rt, &before);
    for (unsigned i = 0; i < 1000; i++)
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), "dgimsy");
    JS_RunGC(rt);
    JS_ComputeMemoryUsage(rt, &after);
    CHECK(before.obj_count == after.obj_count &&
          before.memory_used_size == after.memory_used_size &&
          before.malloc_count == after.malloc_count);
    for (unsigned i = 0; i < 24; i++) {
        JSValue empty = eval(ctx, "/x/");
        JS_SetMemoryLimit(rt, 0);
        result = JS_Call(ctx, getter, empty, 0, NULL);
        JS_SetMemoryLimit(rt, (size_t)-1);
        expect(ctx, result, "");
        JS_FreeValue(ctx, empty);
        JS_SetMemoryLimit(rt, 0);
        result = JS_Call(ctx, getter, receiver, 0, NULL);
        JS_SetMemoryLimit(rt, (size_t)-1);
        if (JS_IsException(result))
            JS_FreeValue(ctx, JS_GetException(ctx));
        else
            JS_FreeValue(ctx, result);
        JS_RunGC(rt);
    }
    JS_FreeValue(ctx, receiver);
    JS_FreeValue(ctx, getter);
    JS_RunGC(rt);
    JS_FreeContext(other);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("REGEXP_FLAGS_PASS poll-boundaries abort foreign-realms exception-realm oom memory");
    return 0;
}
