/* Public-API safety host, sharing the existing moving allocator. */
#define main closure_unused_main
#include "main.c"
#undef main

typedef struct InternalHost {
    Host core;
    JSValue root;
    unsigned fail_point, calls, injected, reenter_at, reentries;
    int busy;
} InternalHost;

static JSValue internal_callback(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                                 int magic, JSValueConst *data)
{
    (void)self;
    (void)argc;
    (void)argv;
    require(magic == 81, "C callback magic");
    return JS_DupValue(ctx, data[0]);
}
static void internal_on_allocation(InternalHost *s)
{
    if (!s->reenter_at || s->busy || !s->core.ctx)
        return;
    if (--s->reenter_at)
        return;
    s->busy = 1;
    JSValue f = JS_NewCFunctionData2(s->core.ctx, internal_callback, NULL, 3, 81, 1, &s->root);
    require(!JS_IsException(f), "allocator reentry creates callback");
    JS_FreeValue(s->core.ctx, f);
    JS_RunGC(s->core.rt);
    s->reentries++;
    s->busy = 0;
}
static int internal_fault(InternalHost *s)
{
    if (s->fail_point && ++s->calls == s->fail_point) {
        s->fail_point = 0;
        s->injected++;
        return 1;
    }
    return 0;
}
static void *internal_malloc(void *opaque, size_t size)
{
    InternalHost *s = opaque;
    if (internal_fault(s))
        return NULL;
    void *p = moving_malloc(&s->core, size);
    internal_on_allocation(s);
    return p;
}
static void *internal_calloc(void *opaque, size_t count, size_t size)
{
    if (count && size > SIZE_MAX / count)
        return NULL;
    void *p = internal_malloc(opaque, count * size);
    if (p)
        memset(p, 0, count * size);
    return p;
}
static void internal_free(void *opaque, void *p)
{
    moving_free(&((InternalHost *)opaque)->core, p);
}
static void *internal_realloc(void *opaque, void *p, size_t size)
{
    InternalHost *s = opaque;
    if (size && internal_fault(s))
        return NULL;
    void *result = moving_realloc(&s->core, p, size);
    internal_on_allocation(s);
    return result;
}
static void internal_clear_error(JSContext *ctx)
{
    JS_FreeValue(ctx, JS_GetException(ctx));
}
static void internal_properties(JSContext *ctx, JSValue f, const char *name, int length)
{
    require(number(ctx, JS_GetPropertyStr(ctx, f, "length")) == length, "C function length");
    JSValue value = JS_GetPropertyStr(ctx, f, "name");
    const char *text = JS_ToCString(ctx, value);
    require(text && !strcmp(text, name ? name : ""), "C function name");
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, value);
    for (int i = 0; i < 2; i++) {
        JSAtom atom = JS_NewAtom(ctx, i ? "name" : "length");
        JSPropertyDescriptor d;
        require(JS_GetOwnProperty(ctx, &d, f, atom) == 1, "own C function descriptor");
        require((d.flags & (JS_PROP_CONFIGURABLE | JS_PROP_WRITABLE | JS_PROP_ENUMERABLE |
                            JS_PROP_GETSET)) == JS_PROP_CONFIGURABLE,
                "C function descriptor flags");
        JS_FreeValue(ctx, d.value);
        JS_FreeValue(ctx, d.getter);
        JS_FreeValue(ctx, d.setter);
        JS_FreeAtom(ctx, atom);
    }
}
int main(void)
{
    InternalHost s = {0};
    s.root = JS_UNDEFINED;
    JSMallocFunctions alloc = {internal_calloc, internal_malloc, internal_free, internal_realloc,
                               moving_size};
    JSRuntime *rt = JS_NewRuntime2(&alloc, &s);
    require(rt != NULL, "internal runtime");
    s.core.rt = rt;
    JS_SetRuntimeOpaque(rt, &s.core);
    JS_NewClassID(rt, &s.core.owner);
    JSClassDef def = {"InternalOwner", .finalizer = finalizer};
    require(JS_NewClass(rt, s.core.owner, &def) == 0, "internal owner class");
    JSContext *ctx = JS_NewContext(rt), *other = JS_NewContext(rt);
    require(ctx && other, "internal contexts");
    s.core.ctx = ctx;
    s.root = owner(ctx, JS_UNDEFINED, 0, NULL);
    const char *names[] = {NULL, "", "named", "123"};
    for (int round = 0; round < 96; round++) {
        const char *name = names[round % 4];
        int length = round % 19 - 1;
        JSValue f = JS_NewCFunctionData2(ctx, internal_callback, name, length, 81, 1, &s.root);
        require(!JS_IsException(f), "C function creation");
        internal_properties(ctx, f, name, length);
        JS_RunGC(rt);
        JSValue result = JS_Call(other, f, JS_UNDEFINED, 0, NULL);
        require(!JS_IsException(result) && JS_IsSameValue(other, result, s.root),
                "foreign caller and callback data ownership");
        JS_FreeValue(other, result);
        JS_FreeValue(ctx, f);
    }
    JSValue warm = JS_NewCFunctionData(ctx, internal_callback, 1, 81, 1, &s.root);
    require(!JS_IsException(warm), "warm callback");
    JS_FreeValue(ctx, warm);
    for (unsigned point = 1; point <= 8; point++) {
        s.reenter_at = point;
        JSValue f = JS_NewCFunctionData(ctx, internal_callback, 2, 81, 1, &s.root);
        s.reenter_at = 0;
        require(!JS_IsException(f), "inflight C function across allocator reentry");
        internal_properties(ctx, f, NULL, 2);
        JS_FreeValue(ctx, f);
    }
    for (unsigned point = 1; point <= 24; point++) {
        for (int named = 0; named < 2; named++) {
            s.calls = 0;
            s.fail_point = point;
            JSValue f = JS_NewCFunctionData2(ctx, internal_callback, named ? "123" : NULL, 17, 81,
                                             1, &s.root);
            s.fail_point = 0;
            JS_FreeValue(ctx, f);
            internal_clear_error(ctx);
            JS_RunGC(rt);
        }
        s.calls = 0;
        s.fail_point = point;
        JSValue callbacks[2] = {JS_UNDEFINED, JS_UNDEFINED};
        JSValue promise = JS_NewPromiseCapability(ctx, callbacks);
        s.fail_point = 0;
        if (!JS_IsException(promise)) {
            JSValue result = JS_Call(ctx, callbacks[0], JS_UNDEFINED, 1, &s.root);
            JS_FreeValue(ctx, result);
            JS_FreeValue(ctx, callbacks[0]);
            JS_FreeValue(ctx, callbacks[1]);
            JS_FreeValue(ctx, promise);
        }
        internal_clear_error(ctx);
        JS_RunGC(rt);
    }
    JSValue object = owner(ctx, JS_UNDEFINED, 0, NULL);
    JSValue cycle = JS_NewCFunctionData(ctx, internal_callback, 1, 81, 1, &object);
    require(!JS_IsException(cycle), "cyclic callback");
    require(JS_SetPropertyStr(ctx, object, "back", cycle) == 1, "callback data cycle");
    JS_FreeValue(ctx, object);
    JS_RunGC(rt);
    JS_FreeValue(ctx, s.root);
    s.root = JS_UNDEFINED;
    s.core.ctx = NULL;
    JS_FreeContext(ctx);
    JS_FreeContext(other);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.core.live == 0 && s.core.born == s.core.freed,
            "all data/shape/context owners released");
    require(s.injected && s.reentries, "actual OOM and allocator reentry");
    while (s.core.retired) {
        Allocation *p = s.core.retired;
        s.core.retired = p->h.next;
        free(p);
    }
    printf("INTERNAL_HOST_OK finalized=%u injected=%u reentries=%u moves=%zu\n", s.core.freed,
           s.injected, s.reentries, s.core.moves);
    return 0;
}
