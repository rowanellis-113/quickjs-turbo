/* MIT. Public empty-replacement allocation fault injection and interrupt regression. */
#include "quickjs.h"
#include <assert.h>
#ifdef NDEBUG
#error Fault fixture requires active assertions.
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    size_t bytes, reserved;
} Header;
typedef struct {
    size_t live, bytes, peak, sequence, fail_at;
    size_t reallocs, requested, max_request;
    int observe;
} Allocator;
static int reject(Allocator *a)
{
    return ++a->sequence == a->fail_at;
}
static void *allocate(void *opaque, size_t n)
{
    Allocator *a = opaque;
    Header *h;
    if (n > SIZE_MAX - sizeof(*h) || reject(a))
        return NULL;
    h = malloc(sizeof(*h) + n);
    if (!h)
        return NULL;
    h->bytes = n;
    ++a->live;
    a->bytes += n;
    if (a->bytes > a->peak)
        a->peak = a->bytes;
    return h + 1;
}
static void *allocate_zero(void *opaque, size_t n, size_t size)
{
    void *p;
    if (size && n > SIZE_MAX / size)
        return NULL;
    p = allocate(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}
static void release(void *opaque, void *ptr)
{
    Allocator *a = opaque;
    Header *h;
    if (!ptr)
        return;
    h = (Header *)ptr - 1;
    assert(a->live && a->bytes >= h->bytes);
    --a->live;
    a->bytes -= h->bytes;
    free(h);
}
static void *resize(void *opaque, void *ptr, size_t n)
{
    Allocator *a = opaque;
    Header *h, *p;
    size_t old;
    if (a->observe) {
        ++a->reallocs;
        a->requested += n;
        if (n > a->max_request)
            a->max_request = n;
    }
    if (!ptr)
        return allocate(opaque, n);
    if (!n) {
        release(opaque, ptr);
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(*h) || reject(a))
        return NULL;
    h = (Header *)ptr - 1;
    old = h->bytes;
    p = realloc(h, sizeof(*h) + n);
    if (!p)
        return NULL;
    p->bytes = n;
    a->bytes = a->bytes - old + n;
    if (a->bytes > a->peak)
        a->peak = a->bytes;
    return p + 1;
}
static size_t usable(const void *ptr)
{
    return ptr ? ((const Header *)ptr - 1)->bytes : 0;
}
static const JSMallocFunctions functions = {allocate_zero, allocate, release, resize, usable};

static unsigned failures, successes, trials;
static const char *preparations[] = {
    "(function(){const r=/(?:)/gv;return function(){r.lastIndex=7;const s='\\ud83d\\ude00a'.replace(r,'');"
    "if(s!=='\\ud83d\\ude00a'||r.lastIndex!==0)throw Error('empty-v');return s;};})()",
    "(function(){const r=/a/;return function(){r.lastIndex=7;const s='baa'.replace(r,'');"
    "if(s!=='ba'||r.lastIndex!==7)throw Error('nonglobal');return s;};})()",
    "(function(){const r=/a/g;return function(){r.lastIndex=7;const s='baa'.replace(r,'');"
    "if(s!=='b'||r.lastIndex!==0)throw Error('global');return s;};})()",
    "(function(){const r=/(?<x>a)(b)?/du;return function(){r.lastIndex=7;const s='\\u0100aba'.replace(r,'');"
    "if(s!=='\\u0100a'||r.lastIndex!==7)throw Error('wide');return s;};})()",
    "(function(){const r=/a/gv;return function(){r.lastIndex=7;const s='\\u0100aba'.replace(r,'');"
    "if(s!=='\\u0100b'||r.lastIndex!==0)throw Error('wide-global');return s;};})()",
    "(function(){const r=new RegExp('(a?)'.repeat(80));return function(){r.lastIndex=7;const s='aaaZaaa'.replace(r,'');"
    "if(s!=='Zaaa'||r.lastIndex!==7)throw Error('large');return s;};})()",
    "(function(){const r=new RegExp('(a?)'.repeat(80),'g');return function(){r.lastIndex=7;const s='aaaZaaa'.replace(r,'');"
    "if(s!=='Z'||r.lastIndex!==0)throw Error('large-global');return s;};})()",
    "(function(){const r=/notpresent/g;return function(){r.lastIndex=7;const s='aba'.replace(r,'');"
    "if(s!=='aba'||r.lastIndex!==0)throw Error('miss');return s;};})()",
    "(function(){const r=/(?:)/gu;return function(){r.lastIndex=7;const s='\\ud83d\\ude00a'.replace(r,'');"
    "if(s!=='\\ud83d\\ude00a'||r.lastIndex!==0)throw Error('empty');return s;};})()",
};
static const char *expected[] = {"\xf0\x9f\x98\x80"
                                 "a",
                                 "ba",
                                 "b",
                                 "\xc4\x80"
                                 "a",
                                 "\xc4\x80"
                                 "b",
                                 "Zaaa",
                                 "Z",
                                 "aba",
                                 "\xf0\x9f\x98\x80"
                                 "a"};

static size_t run_trial(unsigned mode, size_t at)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *code = preparations[mode];
    JSValue fn = JS_Eval(ctx, code, strlen(code), "replace-fault-prepare", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    for (unsigned warm = 0; warm < 3; warm++) {
        JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(value));
        JS_FreeValue(ctx, value);
    }
    JS_RunGC(rt);
    size_t before = memory.sequence;
    memory.fail_at = at ? memory.sequence + at : 0;
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t calls = memory.sequence - before;
    if (!at)
        printf("REPLACE_NOFAULT_ALLOC mode=%u allocations=%zu\n", mode, calls);
    if (JS_IsException(result)) {
        assert(at && JS_HasException(ctx));
        failures++;
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        assert(message && strstr(message, "out of memory"));
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
    } else {
        successes++;
        const char *text = JS_ToCString(ctx, result);
        assert(text && !strcmp(text, expected[mode]));
        JS_FreeCString(ctx, text);
    }
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    trials++;
    return calls;
}

static int interrupt(JSRuntime *rt, void *opaque)
{
    unsigned *calls = opaque;
    (void)rt;
    ++*calls;
    return 1;
}

int main(void)
{
    for (unsigned mode = 0; mode < sizeof(preparations) / sizeof(preparations[0]); mode++) {
        size_t allocations = run_trial(mode, 0);
        for (size_t at = 1; at <= allocations; at++)
            run_trial(mode, at);
    }
    assert(failures && successes);
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *code =
        "(function(){const r=/a/g;let s='';for(let i=0;i<100000;i++)s+='aaaa'.replace(r,'');return s;})";
    JSValue fn = JS_Eval(ctx, code, strlen(code), "replace-interrupt", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    unsigned calls = 0;
    JS_SetInterruptHandler(rt, interrupt, &calls);
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(JS_IsException(result) && calls && JS_HasException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("REPLACE_FAULT_OK %u trials %u failures %u successes; interrupt %u\n", trials, failures,
           successes, calls);
    return 0;
}
