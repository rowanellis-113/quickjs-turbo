/* Public callback ownership,realm,poll transcript and warm runtime OOM. MIT. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error RegExp fixture requires active assertions.
#endif
#include "../native_oom_allocator.h"
typedef struct {
    unsigned gc, probes, id, interrupts, abort_poll;
    JSContext *ctx;
    JSValue receiver;
} Host;
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = JS_GetContextOpaque(ctx);
    ++s->gc;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = JS_GetContextOpaque(ctx);
    ++s->probes;
    return JS_NewInt32(ctx, (int32_t)s->id);
}
static void install(JSContext *ctx, Host *state)
{
    JS_SetContextOpaque(ctx, state);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "gcPort", JS_NewCFunction(ctx, collect, "gcPort", 0)) >=
           0);
    assert(JS_SetPropertyStr(ctx, global, "realmProbe",
                             JS_NewCFunction(ctx, probe, "realmProbe", 0)) >= 0);
    JS_FreeValue(ctx, global);
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return JS_Eval(ctx, text, strlen(text), "regexp-public", JS_EVAL_TYPE_GLOBAL);
}
static void expect(JSContext *ctx, JSValue value, const char *expected)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, error);
        fprintf(stderr, "regexp public exception:%s\n", s ? s : "<oom>");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, error);
        abort();
    }
    const char *s = JS_ToCString(ctx, value);
    assert(s && !strcmp(s, expected));
    JS_FreeCString(ctx, s);
    JS_FreeValue(ctx, value);
}
static const char program[] =
    "(function(){const r=/(?<a>a)(b)(c)(d)(e)(f)(g)(h)(i)/g;let held=[];"
    "function replace(m,a,b,c,d,e,f,g,h,i,offset,input,groups){"
    "if(arguments.length!==13||groups.a!=='a'||i!=='i')throw Error('argv');"
    "gcPort();held.push(arguments);return 'X';}"
    "return function(){held=[];let s='abcdefghi|abcdefghi'.replace(r,replace);"
    "gcPort();if(s!=='X|X'||held.length!==2||held[0][10]!==0||held[1][10]!==10||held[0][12].a!=='a')throw Error('ownership');return s;};})()";
static size_t trial(size_t fault)
{
    Allocator memory = {0};
    Host host = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx, &host);
    JSValue fn = eval(ctx, program);
    assert(!JS_IsException(fn));
    expect(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL), "X|X");
    size_t start = memory.sequence;
    memory.fail_at = fault ? start + fault : 0;
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t count = memory.sequence - start;
    if (JS_IsException(value)) {
        value = JS_GetException(ctx);
        assert(!JS_IsUndefined(value));
        JS_FreeValue(ctx, value);
    } else
        expect(ctx, value, "X|X");
    expect(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL), "X|X");
    assert(host.gc >= 6);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    return count;
}
static void realms(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    assert(a && b);
    Host ha = {.id = 11}, hb = {.id = 22};
    install(a, &ha);
    install(b, &hb);
    JSValue fn = eval(
        a,
        "(function(){'use strict';if(this!==undefined)throw Error('this');gcPort();return {toString(){gcPort();return realmProbe();}};})");
    assert(!JS_IsException(fn));
    JSValue global = JS_GetGlobalObject(b);
    assert(JS_SetPropertyStr(b, global, "foreignReplace", JS_DupValue(b, fn)) >= 0);
    JS_FreeValue(b, global);
    for (unsigned i = 0; i < 16; ++i)
        expect(b, eval(b, "'ab'.replace(/./g,foreignReplace)"), "1111");
    assert(ha.probes == 32 && !hb.probes && ha.gc == 64);
    JS_FreeValue(a, fn);
    JS_FreeContext(a);
    JS_FreeContext(b);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}
static int interrupt(JSContext *ctx, void *opaque)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    Host *s = opaque;
    ++s->interrupts;
    if (s->abort_poll)
        return 1;
    assert(JS_DefinePropertyValueStr(s->ctx, s->receiver, "hasIndices", JS_TRUE, JS_PROP_C_W_E) >=
           0);
    assert(JS_DefinePropertyValueStr(s->ctx, s->receiver, "global", JS_TRUE, JS_PROP_C_W_E) >= 0);
    JS_RunGC(rt);
    return 0;
}
static void flags_transcript(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    Host state = {.ctx = ctx};
    install(ctx, &state);
    JSValue getter = eval(ctx, "Object.getOwnPropertyDescriptor(RegExp.prototype,'flags').get");
    state.receiver = eval(ctx, "/a/");
    assert(!JS_IsException(getter) && !JS_IsException(state.receiver));
    JSAtom indices = JS_NewAtom(ctx, "hasIndices"), global = JS_NewAtom(ctx, "global");
    assert(indices && global);
    uint64_t digest = 1469598103934665603ull;
    unsigned changed = 0;
    JS_SetInterruptHandler(rt, interrupt, &state);
    for (unsigned i = 0; i < 32768; ++i) {
        assert(JS_DeleteProperty(ctx, state.receiver, indices, 0) >= 0);
        assert(JS_DeleteProperty(ctx, state.receiver, global, 0) >= 0);
        JSValue value = JS_Call(ctx, getter, state.receiver, 0, NULL);
        assert(!JS_IsException(value));
        const char *s = JS_ToCString(ctx, value);
        assert(s);
        if (*s)
            ++changed;
        for (const unsigned char *p = (const unsigned char *)s; *p; ++p)
            digest = (digest ^ *p) * 1099511628211ull;
        digest = (digest ^ i) * 1099511628211ull;
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, value);
    }
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(state.interrupts >= 20 && changed);
    printf("LINUX_REGEXP_FLAGS_TRANSCRIPT polls=%u changed=%u digest=%llu\n", state.interrupts,
           changed, (unsigned long long)digest);
    state.abort_poll = 1;
    JS_SetInterruptHandler(rt, interrupt, &state);
    unsigned aborted = 0;
    for (unsigned i = 0; i < 32768; ++i) {
        JSValue value = JS_Call(ctx, getter, state.receiver, 0, NULL);
        if (JS_IsException(value)) {
            JS_FreeValue(ctx, JS_GetException(ctx));
            aborted = 1;
            break;
        }
        JS_FreeValue(ctx, value);
    }
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(aborted);
    assert(JS_DeleteProperty(ctx, state.receiver, indices, 0) >= 0);
    assert(JS_DeleteProperty(ctx, state.receiver, global, 0) >= 0);
    expect(ctx, JS_Call(ctx, getter, state.receiver, 0, NULL), "");
    JS_FreeAtom(ctx, indices);
    JS_FreeAtom(ctx, global);
    JS_FreeValue(ctx, getter);
    JS_FreeValue(ctx, state.receiver);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}

static void flags_guards(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt), *other = JS_NewContext(rt);
    assert(ctx && other);
    JSValue getter = eval(ctx, "Object.getOwnPropertyDescriptor(RegExp.prototype,'flags').get");
    JSValue foreign = eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'flags').get");
    JSValue receiver = eval(ctx, "/a/gm");
    JSValue flag = eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'sticky').get");
    JSAtom global = JS_NewAtom(ctx, "global");
    assert(global && !JS_IsException(getter) && !JS_IsException(foreign) && !JS_IsException(flag));
    assert(JS_DefinePropertyGetSet(ctx, receiver, global, flag, JS_UNDEFINED,
                                   JS_PROP_CONFIGURABLE) >= 0);
    expect(ctx, JS_Call(ctx, foreign, receiver, 0, NULL), "m");
    JS_FreeValue(ctx, receiver);
    receiver = JS_NewObject(ctx);
    flag = eval(other, "Object.getOwnPropertyDescriptor(RegExp.prototype,'global').get");
    assert(JS_DefinePropertyGetSet(ctx, receiver, global, flag, JS_UNDEFINED,
                                   JS_PROP_CONFIGURABLE) >= 0);
    JSValue result = JS_Call(ctx, getter, receiver, 0, NULL);
    assert(JS_IsException(result));
    JSValue error = JS_GetException(ctx), actual = JS_GetPrototype(ctx, error);
    JSValue wanted = eval(other, "TypeError.prototype");
    assert(JS_IsObject(actual) && JS_IsObject(wanted) &&
           JS_VALUE_GET_PTR(actual) == JS_VALUE_GET_PTR(wanted));
    JS_FreeValue(ctx, error);
    JS_FreeValue(ctx, actual);
    JS_FreeValue(other, wanted);
    JS_FreeValue(ctx, receiver);
    receiver = eval(other, "/z/dgimsy");
    for (unsigned i = 0; i < 40; ++i)
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), "dgimsy");
    JS_RunGC(rt);
    JSMemoryUsage before, after;
    JS_ComputeMemoryUsage(rt, &before);
    for (unsigned i = 0; i < 1000; ++i)
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), "dgimsy");
    JS_RunGC(rt);
    JS_ComputeMemoryUsage(rt, &after);
    assert(before.obj_count == after.obj_count &&
           before.memory_used_size == after.memory_used_size &&
           before.malloc_count == after.malloc_count);
    for (unsigned i = 0; i < 24; ++i) {
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
            expect(ctx, result, "dgimsy");
        expect(ctx, JS_Call(ctx, getter, receiver, 0, NULL), "dgimsy");
    }
    JS_FreeAtom(ctx, global);
    JS_FreeValue(ctx, getter);
    JS_FreeValue(other, foreign);
    JS_FreeValue(other, receiver);
    JS_FreeContext(ctx);
    JS_FreeContext(other);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}
static void symbol_names(JSRuntime *rt)
{
    /* Use a fresh realm: the public deletion sequence guarantees the slots
     * compact to the live proof's exact positions, independent of prior tests. */
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
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

static void flag_symbol_names(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    symbol_names(rt);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        size_t count = trial(0);
        for (size_t fault = 1; fault <= count + 2; ++fault)
            trial(fault);
        printf("LINUX_REGEXP_OWNED_OOM_OK allocations=%zu\n", count);
    } else if (argc > 1 && !strcmp(argv[1], "flags"))
        flags_transcript();
    else {
        trial(0);
        realms();
        flags_guards();
        flag_symbol_names();
        flags_transcript();
        puts("LINUX_REGEXP_API_OK");
    }
    return 0;
}
