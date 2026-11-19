#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Valid headerless allocator. Two distinct live allocations may be adjacent;
 * all bookkeeping stays outside the returned storage. */
typedef struct Group {
    void *base;
    unsigned refs;
} Group;
typedef struct Record {
    void *p;
    size_t n;
    Group *g;
} Record;
static Record records[20000];
static Group *pending;
static unsigned live, paired, armed;
static size_t closure_bytes;
static void require(int ok)
{
    if (!ok)
        abort();
}
static Record *find(const void *p)
{
    for (unsigned i = 0; i < 20000; i++)
        if (records[i].p == p)
            return &records[i];
    abort();
}
static void record(void *p, size_t n, Group *g)
{
    for (unsigned i = 0; i < 20000; i++)
        if (!records[i].p) {
            records[i] = (Record){p, n, g};
            g->refs++;
            live++;
            return;
        }
    abort();
}
static void *amalloc(void *opaque, size_t n)
{
    (void)opaque;
    if (!n)
        return NULL;
    if (pending && n == 8) {
        Group *g = pending;
        pending = NULL;
        paired++;
        void *p = (char *)g->base + closure_bytes;
        record(p, n, g);
        return p;
    }
    Group *g = malloc(sizeof(*g));
    if (!g)
        return NULL;
    g->base = malloc(n + (armed && n == closure_bytes ? 16 : 0));
    g->refs = 0;
    if (!g->base) {
        free(g);
        return NULL;
    }
    if (armed && n == closure_bytes) {
        require(!pending);
        pending = g;
        armed = 0;
    }
    record(g->base, n, g);
    return g->base;
}
static void afree(void *opaque, void *p)
{
    (void)opaque;
    if (!p)
        return;
    Record *r = find(p);
    Group *g = r->g;
    r->p = NULL;
    live--;
    if (pending == g)
        pending = NULL;
    if (!--g->refs) {
        free(g->base);
        free(g);
    }
}
static size_t ausable(const void *p)
{
    return p ? find(p)->n : 0;
}
static void *acalloc(void *o, size_t n, size_t s)
{
    if (n && s > SIZE_MAX / n)
        return NULL;
    void *p = amalloc(o, n * s);
    if (p)
        memset(p, 0, n * s);
    return p;
}
static void *arealloc(void *o, void *p, size_t n)
{
    if (!p)
        return amalloc(o, n);
    if (!n) {
        afree(o, p);
        return NULL;
    }
    size_t old = ausable(p);
    void *q = amalloc(o, n);
    if (q) {
        memcpy(q, p, old < n ? old : n);
        afree(o, p);
    }
    return q;
}
int main(void)
{
    JSMallocFunctions f = {acalloc, amalloc, afree, arealloc, ausable};
    JSRuntime *rt = JS_NewRuntime2(&f, NULL);
    require(rt != NULL);
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL);
    const char *text = "(function maker(x){return function held(){return x;};})";
    JSValue maker = JS_Eval(ctx, text, strlen(text), "adjacent.js", JS_EVAL_TYPE_GLOBAL);
    require(!JS_IsException(maker));
    for (int i = 0; i < 3; i++) {
        JSValue arg = JS_NewInt32(ctx, 123);
        if (i == 2)
            armed = 1;
        unsigned before = paired;
        JSValue closure = JS_Call(ctx, maker, JS_UNDEFINED, 1, &arg);
        armed = 0;
        pending = NULL;
        require(!JS_IsException(closure));
        if (i == 1) {
            /* Observe this engine's allocation through the public value and
             * our allocator records; no private object layout is assumed. */
            require(JS_IsFunction(ctx, closure));
            closure_bytes = find(JS_VALUE_GET_PTR(closure))->n;
            require(closure_bytes && closure_bytes % _Alignof(void *) == 0);
        }
        if (paired > before) {
            /* Witness that the adjacent first allocation was this closure. */
            Record *obj = find(JS_VALUE_GET_PTR(closure));
            require(obj->n == closure_bytes && find((char *)obj->p + closure_bytes)->g == obj->g);
        }
        JSValue result = JS_Call(ctx, closure, JS_UNDEFINED, 0, NULL);
        int32_t value = 0;
        require(JS_ToInt32(ctx, &value, result) == 0 && value == 123);
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, closure);
        JS_RunGC(rt);
    }
    JS_FreeValue(ctx, maker);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    require(live == 0);
    if (getenv("QJS_DISABLE_CLOSURE_INLINE_REFS"))
        require(paired == 1);
    printf("ADJACENT_OK pairs=%u live=%u\n", paired, live);
}
