/* Reuse the already validated moving allocator/owner callbacks unchanged. */
#define main closure_existing_main
#include "main.c"
#undef main

typedef struct FaultHost {
    Host core;
    unsigned point, calls, injected;
} FaultHost;
static int fault_now(FaultHost *s)
{
    if (!s->point)
        return 0;
    if (++s->calls != s->point)
        return 0;
    s->point = 0;
    s->injected++;
    return 1;
}
static void *fault_malloc(void *opaque, size_t n)
{
    FaultHost *s = opaque;
    return fault_now(s) ? NULL : moving_malloc(&s->core, n);
}
static void *fault_calloc(void *opaque, size_t count, size_t n)
{
    if (count && n > SIZE_MAX / count)
        return NULL;
    void *p = fault_malloc(opaque, count * n);
    if (p)
        memset(p, 0, count * n);
    return p;
}
static void fault_free(void *opaque, void *ptr)
{
    moving_free(&((FaultHost *)opaque)->core, ptr);
}
static void *fault_realloc(void *opaque, void *ptr, size_t n)
{
    FaultHost *s = opaque;
    if (!ptr)
        return fault_malloc(opaque, n);
    if (!n) {
        fault_free(opaque, ptr);
        return NULL;
    }
    Allocation *old = (Allocation *)ptr - 1;
    size_t before = old->h.size;
    void *p = fault_malloc(opaque, n);
    if (!p)
        return NULL;
    memcpy(p, ptr, n < before ? n : before);
    memset(ptr, 0, before);
    old->h.next = s->core.retired;
    s->core.retired = old;
    s->core.live--;
    s->core.moves++;
    return p;
}
int main(void)
{
    FaultHost s = {0};
    s.core.replacement = s.core.maker = JS_UNDEFINED;
    JSMallocFunctions functions = {fault_calloc, fault_malloc, fault_free, fault_realloc,
                                   moving_size};
    JSRuntime *rt = JS_NewRuntime2(&functions, &s);
    require(rt != NULL, "fault runtime");
    s.core.rt = rt;
    JS_SetRuntimeOpaque(rt, &s.core);
    JS_NewClassID(rt, &s.core.owner);
    JSClassDef def = {"FaultClosureOwner", .finalizer = finalizer};
    require(JS_NewClass(rt, s.core.owner, &def) == 0, "fault owner class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "fault context");
#ifdef QJS_TEST_WIDE_CAPTURE
    JSValue maker = eval(
        ctx,
        "(function factory(value){let a0=value,a1=value,a2=value,a3=value,a4=value,a5=value,a6=value,a7=value,a8=value,a9=value,a10=value,a11=value,a12=value,a13=value,a14=value,a15=value,a16=value,a17=value,a18=value,a19=value,a20=value,a21=value;return function retained(){return a0===a1&&a0===a2&&a0===a3&&a0===a4&&a0===a5&&a0===a6&&a0===a7&&a0===a8&&a0===a9&&a0===a10&&a0===a11&&a0===a12&&a0===a13&&a0===a14&&a0===a15&&a0===a16&&a0===a17&&a0===a18&&a0===a19&&a0===a20&&a0===a21?a0:undefined;};})");
    /* Warm the ordinary creation recipe before sweeping actual allocations. */
#else
    JSValue maker =
        eval(ctx, "(function factory(value){return function retained(){return value;};})");
    /* Warm the ordinary creation recipe before sweeping actual allocations. */
#endif
    for (int k = 0; k < 8; k++) {
        JSValue v = make_inner(ctx, maker, k);
        JS_FreeValue(ctx, v);
    }
    for (unsigned n = 1; n <= 32; n++) {
        JSValue marker = owner(ctx, JS_UNDEFINED, 0, NULL);
        require(!JS_IsException(marker), "fault marker");
        unsigned before = s.injected;
        s.calls = 0;
        s.point = n;
        JSValue f = JS_Call(ctx, maker, JS_UNDEFINED, 1, &marker);
        s.point = 0;
        require(s.core.freed == n - 1, "borrowed marker survives creation failure");
        if (JS_IsException(f))
            JS_FreeValue(ctx, JS_GetException(ctx));
        else {
            /* Without a fault, require the complete captured-value behavior.
               Under an injected failure, exercise ownership/cleanup; the
               fixed parent's ignored property-definition OOM is not repaired
               or hidden by imposing identical allocation schedules. */
            if (s.injected == before) {
                JSValue value = JS_Call(ctx, f, JS_UNDEFINED, 0, NULL);
                require(!JS_IsException(value) &&
                            JS_VALUE_GET_PTR(value) == JS_VALUE_GET_PTR(marker),
                        "capture without fault");
                JS_FreeValue(ctx, value);
            }
            JS_FreeValue(ctx, f);
        }
        JS_FreeValue(ctx, JS_GetException(ctx));
        JS_FreeValue(ctx, marker);
        JS_RunGC(rt);
        require(s.core.born == n && s.core.freed == n, "all failed-creation owners reclaimed");
        require(number(ctx, eval(ctx, "40+2")) == 42, "runtime recovers after allocation failure");
    }
    require(s.injected > 0, "actual allocation faults observed");
    JS_FreeValue(ctx, maker);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.core.live == 0 && s.core.born == 32 && s.core.freed == 32,
            "fault final allocation and owner balance");
    while (s.core.retired) {
        Allocation *p = s.core.retired;
        s.core.retired = p->h.next;
        free(p);
    }
    printf("CLOSURE_FAULT_OK cases=32 injected=%u born=%u finalized=%u moves=%zu\n", s.injected,
           s.core.born, s.core.freed, s.core.moves);
    return 0;
}
