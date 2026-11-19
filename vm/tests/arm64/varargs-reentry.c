/* Real allocator callbacks with GC and foreign-context JS during large calls. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
typedef struct {
    Allocator ledger;
    JSRuntime *rt;
    JSContext *foreign;
    JSValue hook;
    unsigned active, inside, hits;
} Reentry;
static void observe(void *opaque, size_t n)
{
    Reentry *s = opaque;
    if (!s->active || s->inside || n < 32768)
        return;
    s->inside = 1;
    ++s->hits;
    JS_RunGC(s->rt);
    JSValue v = JS_Call(s->foreign, s->hook, JS_UNDEFINED, 0, NULL);
    int32_t result = 0;
    assert(!JS_IsException(v) && !JS_ToInt32(s->foreign, &result, v) && result == 42);
    JS_FreeValue(s->foreign, v);
    JS_RunGC(s->rt);
    s->inside = 0;
}
static void *r_malloc(void *o, size_t n)
{
    observe(o, n);
    return allocate(o, n);
}
static void *r_calloc(void *o, size_t n, size_t z)
{
    if (!z || n <= SIZE_MAX / z)
        observe(o, n * z);
    return allocate_zero(o, n, z);
}
static void *r_realloc(void *o, void *p, size_t n)
{
    observe(o, n);
    return resize(o, p, n);
}
static const JSMallocFunctions reentrant = {r_calloc, r_malloc, release, r_realloc, usable};
static uintptr_t word(JSRuntime *r, size_t p)
{
    uintptr_t v;
    memcpy(&v, (char *)r + p, sizeof(v));
    return v;
}
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "varargs-reentry", 0);
    assert(!JS_IsException(v));
    return v;
}
int main(void)
{
    unsigned hits = 0;
    for (unsigned variant = 0; variant < 3; variant++) {
        Reentry s = {0};
        s.hook = JS_UNDEFINED;
        s.rt = JS_NewRuntime2(&reentrant, &s);
        assert(s.rt);
        JS_SetMaxStackSize(s.rt, 4 * 1024 * 1024);
        JSContext *c = JS_NewContext(s.rt);
        s.foreign = JS_NewContext(s.rt);
        assert(c && s.foreign);
        s.hook =
            eval(s.foreign,
                 "(function(){function nested(n){return n===0?42:nested(n-1)}return nested(8)})");
        JSValue v = JS_Call(s.foreign, s.hook, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(v));
        JS_FreeValue(s.foreign, v);
        JSValue f = eval(c, "(function(a){return a})"), object = eval(c, "({value:42})"),
                list = JS_NewArray(c);
        for (unsigned i = 0; i < 2048; i++)
            assert(JS_SetPropertyUint32(c, list, i, JS_DupValue(c, object)) >= 0);
        JSValue driver =
            eval(c, variant == 0   ? "(function(f,o,list){let r=f(...list);return r})"
                    : variant == 1 ? "(function(f,o,list){let r=f(o,...list);return r})"
                                   : "(function(f,o,list){let r=f.apply(o,list);return r})");
        v = eval(c, "(function(){for(const x of [1]){};return Function.prototype.apply})()");
        JS_FreeValue(c, v);
        v = JS_Call(c, f, JS_UNDEFINED, 1, &object);
        assert(!JS_IsException(v));
        JS_FreeValue(c, v);
        uintptr_t top = word(s.rt, ARM_OFF_JSRuntime_stack_top),
                  limit = word(s.rt, ARM_OFF_JSRuntime_stack_limit);
        JSValue args[] = {f, object, list};
        s.active = 1;
        v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
        s.active = 0;
        assert(!JS_IsException(v) && JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(object));
        JS_FreeValue(c, v);
        assert(s.hits > 0 && word(s.rt, ARM_OFF_JSRuntime_stack_top) == top &&
               word(s.rt, ARM_OFF_JSRuntime_stack_limit) == limit);
        printf("REENTRY_COHORT variant=%u callbacks=%u\n", variant, s.hits);
        hits += s.hits;
        JS_FreeValue(c, driver);
        JS_FreeValue(c, list);
        JS_FreeValue(c, object);
        JS_FreeValue(c, f);
        JS_FreeValue(s.foreign, s.hook);
        JS_FreeContext(s.foreign);
        JS_FreeContext(c);
        JS_RunGC(s.rt);
        JS_FreeRuntime(s.rt);
        assert(s.ledger.live == 0 && s.ledger.bytes == 0);
    }
    printf("AARCH64_VARARGS_REENTRY_OK callbacks=%u variants=3 live=0 quota_restored=3\n", hits);
    return 0;
}
