/* Coherent shared arenas,foreign-runtime blocking,realm and quota recovery. */
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
extern int JS_FrameSharedProbe(JSRuntime *, uintptr_t *);
extern unsigned JS_FrameAArch64ScopeProbe(JSRuntime *, uintptr_t *);
#ifdef QJS_AARCH64_VM_INSTRUMENT
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
#endif

typedef struct State {
    JSRuntime *rt, *foreign_rt;
    JSContext *ctx, *child_ctx, *foreign_ctx;
    JSValue child, foreign_root;
    int shared, vm, expected_shared;
    unsigned host_checks, shared_hits, blocked_hits, finalized, unwinds;
    uintptr_t min_used, max_used, child_bytes;
    Allocator *ledger;
} State;
static JSClassID token_class;

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "shared scope: %s\n", s ? s : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *source)
{
    return checked(ctx,
                   JS_Eval(ctx, source, strlen(source), "<arm-shared-scope>", JS_EVAL_TYPE_GLOBAL));
}
static void integer(JSContext *ctx, JSValue value, int expected)
{
    int32_t n;
    checked(ctx, value);
    assert(JS_ToInt32(ctx, &n, value) == 0 && n == expected);
    JS_FreeValue(ctx, value);
}
static uintptr_t word(JSRuntime *rt, size_t offset)
{
    uintptr_t n;
    memcpy(&n, (const unsigned char *)rt + offset, sizeof(n));
    return n;
}
static void host_snapshot(State *s)
{
    uintptr_t words[9] = {0};
    unsigned kind = JS_FrameAArch64ScopeProbe(s->rt, words);
    if (s->shared) {
        assert(kind == 1 && words[1] == words[2]);
        if (!s->min_used || words[1] < s->min_used)
            s->min_used = words[1];
        if (words[1] > s->max_used)
            s->max_used = words[1];
        if (s->child_bytes)
            assert(words[6] >= words[5] && words[6] - words[5] < s->child_bytes);
    } else
        assert(kind == (s->vm ? 4u : 0u));
    ++s->host_checks;
}
static JSValue child_probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    State *s = JS_GetContextOpaque(ctx);
    assert(ctx == s->child_ctx);
    uintptr_t words[6];
    int hit = JS_FrameSharedProbe(s->rt, words);
    assert(hit == s->expected_shared);
    if (hit) {
        assert(words[0] != words[3]);
        ++s->shared_hits;
    } else
        ++s->blocked_hits;
    JS_RunGC(s->rt);
    return JS_UNDEFINED;
}
static JSValue bounce(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    State *s = JS_GetContextOpaque(ctx);
    host_snapshot(s);
    s->expected_shared = s->shared;
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}
static JSValue bounce_receiver(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    State *s = JS_GetContextOpaque(ctx);
    host_snapshot(s);
    s->expected_shared = s->shared;
    return JS_Call(ctx, argv[0], argv[1], 0, NULL);
}
static void token_finalizer(JSRuntime *rt, JSValue value)
{
    (void)value;
    State *s = JS_GetRuntimeOpaque(rt);
    ++s->finalized;
    /* The foreign root is executing over a fresh arena under an older,
     * paused host in s->rt. Never look through that active foreign VM. */
    unsigned kind = JS_FrameAArch64ScopeProbe(rt, NULL);
    assert(kind == (s->vm ? 4u : 0u));
    int previous = s->expected_shared;
    s->expected_shared = 0;
    JSValue arg = JS_NewInt32(s->ctx, 40);
    integer(s->ctx, JS_Call(s->ctx, s->child, JS_UNDEFINED, 1, &arg), 42);
    s->expected_shared = previous;
}
static JSValue make_token(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewObjectClass(ctx, token_class);
}
static JSValue cross_runtime(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    State *s = JS_GetContextOpaque(ctx);
    host_snapshot(s);
    integer(s->foreign_ctx, JS_Call(s->foreign_ctx, s->foreign_root, JS_UNDEFINED, 0, NULL), 7);
    host_snapshot(s);
    s->expected_shared = s->shared;
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}
static void install(JSContext *ctx, const char *name, JSCFunction *fn, int argc)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, fn, name, argc)) == 1);
    JS_FreeValue(ctx, global);
}
static void setup_on_runtime(State *s, const char *mode, JSRuntime *rt, Allocator *ledger,
                             int foreign)
{
    memset(s, 0, sizeof(*s));
    s->ledger = ledger;
    s->vm = strcmp(mode, "register-off") && strcmp(mode, "legacy");
    s->shared = s->vm && strcmp(mode, "off") && strcmp(mode, "zero") && strcmp(mode, "slow-off");
    s->rt = rt;
    assert(s->rt);
    JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    s->ctx = JS_NewContext(s->rt);
    s->child_ctx = JS_NewContext(s->rt);
    assert(s->ctx && s->child_ctx);
    JS_SetContextOpaque(s->ctx, s);
    JS_SetContextOpaque(s->child_ctx, s);
    install(s->child_ctx, "probe", child_probe, 1);
    s->child = eval(s->child_ctx, "(function(x){probe(x);return x+2;})");
    if (foreign) {
        s->foreign_rt = JS_NewRuntime();
        assert(s->foreign_rt);
        JS_SetMaxStackSize(s->foreign_rt, 4 * 1024 * 1024);
        s->foreign_ctx = JS_NewContext(s->foreign_rt);
        assert(s->foreign_ctx);
        JS_SetRuntimeOpaque(s->foreign_rt, s);
        JS_NewClassID(s->foreign_rt, &token_class);
        JSClassDef def = {0};
        def.class_name = "BlockedForeignToken";
        def.finalizer = token_finalizer;
        assert(JS_NewClass(s->foreign_rt, token_class, &def) == 0);
        install(s->foreign_ctx, "makeToken", make_token, 0);
        s->foreign_root =
            eval(s->foreign_ctx, "(function(){var token=makeToken();token=null;return 7;})");
    }
}
static void setup(State *s, const char *mode, Allocator *ledger, int foreign)
{
    JSRuntime *rt = ledger ? JS_NewRuntime2(&functions, ledger) : JS_NewRuntime();
    setup_on_runtime(s, mode, rt, ledger, foreign);
}
static void cleanup(State *s)
{
    assert(JS_FrameAArch64ScopeProbe(s->rt, NULL) == 0);
    if (s->foreign_rt)
        assert(JS_FrameAArch64ScopeProbe(s->foreign_rt, NULL) == 0);
    if (s->foreign_rt) {
        JS_FreeValue(s->foreign_ctx, s->foreign_root);
        JS_FreeContext(s->foreign_ctx);
        JS_FreeRuntime(s->foreign_rt);
    }
    JS_FreeValue(s->child_ctx, s->child);
    JS_FreeContext(s->child_ctx);
    JS_FreeContext(s->ctx);
    JS_RunGC(s->rt);
    JS_FreeRuntime(s->rt);
}
static JSValue root(State *s)
{
    return eval(
        s->ctx,
        "(function root(n,child,bounce,x){if(n){var r=root(n-1,child,bounce,x);return r;}return bounce(child,x);})");
}
static void ordinary_and_blocked(const char *mode)
{
    State s;
    setup(&s, mode, NULL, 1);
    JSValue driver = root(&s);
    JSValue cb = JS_NewCFunction(s.ctx, bounce, "bounce", 2),
            cross = JS_NewCFunction(s.ctx, cross_runtime, "cross", 2);
    JSValue args[] = {JS_NewInt32(s.ctx, 0), s.child, cb, JS_NewInt32(s.ctx, 40)};
    integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 42);
    args[0] = JS_NewInt32(s.ctx, 8);
    for (unsigned i = 0; i < 16; i++) {
        args[2] = i & 1 ? cross : cb;
        integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 42);
    }
    assert(s.finalized == 8 && s.blocked_hits >= 8);
    if (s.shared)
        assert(s.shared_hits == 17 && s.max_used > s.min_used);
    else
        assert(s.shared_hits == 0);
    JSValue factory =
        eval(s.child_ctx, "(function(x,missing){probe(x);var y=x;return function(){return y;};})");
    args[1] = factory;
    args[2] = cb;
    JSValue closure = checked(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args));
    JS_RunGC(s.rt);
    integer(s.ctx, JS_Call(s.ctx, closure, JS_UNDEFINED, 0, NULL), 40);
    JS_FreeValue(s.ctx, closure);
    JS_FreeValue(s.ctx, factory);
    JSValue receiver_cb = JS_NewCFunction(s.ctx, bounce_receiver, "receiver", 2);
    JSValue sloppy = eval(s.child_ctx, "(function(){probe(0);return this;})");
    JSValue strict = eval(s.child_ctx, "(function(){'use strict';probe(0);return this;})");
    args[1] = sloppy;
    args[2] = receiver_cb;
    args[3] = JS_UNDEFINED;
    JSValue boxed = checked(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args)),
            global = JS_GetGlobalObject(s.child_ctx);
    assert(JS_VALUE_GET_PTR(boxed) == JS_VALUE_GET_PTR(global));
    JS_FreeValue(s.ctx, boxed);
    JS_FreeValue(s.ctx, global);
    args[1] = strict;
    boxed = checked(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args));
    assert(JS_IsUndefined(boxed));
    JS_FreeValue(s.ctx, boxed);
    args[1] = sloppy;
    args[3] = JS_NewInt32(s.ctx, 37);
    boxed = checked(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args));
    JSValue boxed_proto = JS_GetPrototype(s.ctx, boxed),
            number_proto = eval(s.child_ctx, "Number.prototype");
    assert(JS_VALUE_GET_PTR(boxed_proto) == JS_VALUE_GET_PTR(number_proto));
    JS_FreeValue(s.ctx, boxed_proto);
    JS_FreeValue(s.ctx, number_proto);
    integer(s.ctx, boxed, 37);
    JS_FreeValue(s.ctx, sloppy);
    JS_FreeValue(s.ctx, strict);
    JS_FreeValue(s.ctx, receiver_cb);
    /* Shared child exceptions retain the child's realm and restore TLS/quota. */
    JSValue thrower =
        eval(s.child_ctx, "(function(x){probe(x);throw new TypeError('shared child');})");
    args[1] = thrower;
    args[2] = cb;
    args[3] = JS_NewInt32(s.ctx, 40);
    uintptr_t top = word(s.rt, ARM_OFF_JSRuntime_stack_top),
              limit = word(s.rt, ARM_OFF_JSRuntime_stack_limit);
    JSValue v = JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args);
    assert(JS_IsException(v));
    JSValue error = JS_GetException(s.ctx), proto = JS_GetPrototype(s.ctx, error),
            expected = eval(s.child_ctx, "TypeError.prototype");
    assert(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(expected));
    JS_FreeValue(s.ctx, expected);
    JS_FreeValue(s.ctx, proto);
    JS_FreeValue(s.ctx, error);
    assert(word(s.rt, ARM_OFF_JSRuntime_stack_top) == top &&
           word(s.rt, ARM_OFF_JSRuntime_stack_limit) == limit);
    args[1] = s.child;
    integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 42);
    JS_SetMaxStackSize(s.rt, 16 * 1024);
    args[0] = JS_NewInt32(s.ctx, 500);
    v = JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args);
    assert(JS_IsException(v));
    JS_FreeValue(s.ctx, JS_GetException(s.ctx));
    JS_SetMaxStackSize(s.rt, 4 * 1024 * 1024);
    assert(word(s.rt, ARM_OFF_JSRuntime_stack_top) == top &&
           word(s.rt, ARM_OFF_JSRuntime_stack_limit) == limit);
    args[0] = JS_NewInt32(s.ctx, 8);
    integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 42);
    JS_FreeValue(s.ctx, thrower);
    JS_FreeValue(s.ctx, driver);
    JS_FreeValue(s.ctx, cb);
    JS_FreeValue(s.ctx, cross);
    printf(
        "AARCH64_SHARED_SCOPE_OK mode=%s shared=%u blocked=%u finalizers=%u host_checks=%u quota_restored=1\n",
        mode, s.shared_hits, s.blocked_hits, s.finalized, s.host_checks);
    cleanup(&s);
}
static JSValue wide_child(State *s)
{
    char source[10000];
    size_t at = 0;
    at += snprintf(source + at, sizeof(source) - at, "(function(x){var ");
    for (unsigned i = 0; i < 126; i++)
        at += snprintf(source + at, sizeof(source) - at, "%sa%u=x", i ? "," : "", i);
    at += snprintf(source + at, sizeof(source) - at, ";probe(x);return ");
    for (unsigned i = 0; i < 126; i++)
        at += snprintf(source + at, sizeof(source) - at, "%sa%u", i ? "+" : "", i);
    at += snprintf(source + at, sizeof(source) - at, ";})");
    assert(at < sizeof(source));
    return eval(s->child_ctx, source);
}
static void oom(const char *mode)
{
    unsigned faults = 0, success = 0;
    for (unsigned point = 1; point <= 12; point++) {
        Allocator ledger = {0};
        State s;
        setup(&s, mode, &ledger, 0);
        JSValue driver = root(&s), cb = JS_NewCFunction(s.ctx, bounce, "bounce", 2);
        JSValue wide = wide_child(&s), arg = JS_NewInt32(s.ctx, 1);
        s.expected_shared = 0;
        integer(s.ctx, JS_Call(s.ctx, wide, JS_UNDEFINED, 1, &arg), 126);
#ifdef QJS_AARCH64_VM_INSTRUMENT
        uintptr_t info[6];
        assert(qjs_aarch64_vm_function_info(wide, info));
        /* The real legacy control never runs the owned-frame classifier. */
        assert((info[0] & 7) == (!strcmp(mode, "legacy") ? 0u : 3u));
        s.child_bytes = ARM_FRAME_HEADER_BYTES + sizeof(JSValue) * (info[1] + info[2] + info[5]);
#endif
        JSValue args[] = {JS_NewInt32(s.ctx, 8), wide, cb, arg};
        uintptr_t top = word(s.rt, ARM_OFF_JSRuntime_stack_top),
                  limit = word(s.rt, ARM_OFF_JSRuntime_stack_limit);
        ledger.fail_at = ledger.sequence + point;
        JSValue v = JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args);
        ledger.fail_at = 0;
        if (JS_IsException(v)) {
            ++faults;
            JS_FreeValue(s.ctx, JS_GetException(s.ctx));
        } else {
            integer(s.ctx, v, 126);
            ++success;
        }
        assert(word(s.rt, ARM_OFF_JSRuntime_stack_top) == top &&
               word(s.rt, ARM_OFF_JSRuntime_stack_limit) == limit);
        integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 126);
        assert(word(s.rt, ARM_OFF_JSRuntime_stack_top) == top &&
               word(s.rt, ARM_OFF_JSRuntime_stack_limit) == limit);
        JS_FreeValue(s.ctx, wide);
        JS_FreeValue(s.ctx, driver);
        JS_FreeValue(s.ctx, cb);
        cleanup(&s);
        assert(ledger.live == 0 && ledger.bytes == 0);
    }
    if (strcmp(mode, "off") && strcmp(mode, "zero") && strcmp(mode, "register-off") &&
        strcmp(mode, "legacy") && strcmp(mode, "slow-off"))
        assert(faults > 0);
    assert(faults + success == 12);
    printf(
        "AARCH64_SHARED_OOM_OK mode=%s faults=%u successes=%u trials=12 live=0 quota_restored=12\n",
        mode, faults, success);
}
typedef struct Hook {
    Allocator ledger;
    State *state;
    unsigned armed, busy, hits;
} Hook;
static void allocation_reentry(Hook *h, size_t n)
{
    if (!h->armed || h->busy || n < 16384)
        return;
    h->busy = 1;
    State *s = h->state;
    assert(JS_FrameAArch64ScopeProbe(s->rt, NULL) == 2); /* uncommitted child barrier */
    uintptr_t top = word(s->rt, ARM_OFF_JSRuntime_stack_top),
              limit = word(s->rt, ARM_OFF_JSRuntime_stack_limit);
    int saved = s->expected_shared;
    s->expected_shared = 0;
    JSValue arg = JS_NewInt32(s->ctx, 40);
    integer(s->ctx, JS_Call(s->ctx, s->child, JS_UNDEFINED, 1, &arg), 42);
    s->expected_shared = saved;
    assert(JS_FrameAArch64ScopeProbe(s->rt, NULL) == 2);
    assert(word(s->rt, ARM_OFF_JSRuntime_stack_top) == top &&
           word(s->rt, ARM_OFF_JSRuntime_stack_limit) == limit);
    ++h->hits;
    h->busy = 0;
}
static void *hook_alloc(void *opaque, size_t n)
{
    Hook *h = opaque;
    allocation_reentry(h, n);
    return allocate(&h->ledger, n);
}
static void *hook_zero(void *opaque, size_t n, size_t size)
{
    if (size && n > SIZE_MAX / size)
        return NULL;
    void *p = hook_alloc(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}
static void hook_free(void *opaque, void *p)
{
    release(&((Hook *)opaque)->ledger, p);
}
static void *hook_resize(void *opaque, void *p, size_t n)
{
    Hook *h = opaque;
    allocation_reentry(h, n);
    return resize(&h->ledger, p, n);
}
static void allocator_callback(const char *mode)
{
    Hook h = {0};
    State s;
    h.state = &s;
    const JSMallocFunctions hooks = {hook_zero, hook_alloc, hook_free, hook_resize, usable};
    JSRuntime *rt = JS_NewRuntime2(&hooks, &h);
    setup_on_runtime(&s, mode, rt, &h.ledger, 0);
    JSValue driver = root(&s), cb = JS_NewCFunction(s.ctx, bounce, "bounce", 2),
            wide = wide_child(&s);
    JSValue arg = JS_NewInt32(s.ctx, 1);
    s.expected_shared = 0;
    integer(s.ctx, JS_Call(s.ctx, wide, JS_UNDEFINED, 1, &arg), 126);
    JSValue args[] = {JS_NewInt32(s.ctx, 8), wide, cb, arg};
    h.armed = 1;
    integer(s.ctx, JS_Call(s.ctx, driver, JS_UNDEFINED, 4, args), 126);
    h.armed = 0;
    assert(h.hits == (unsigned)s.shared);
    JS_FreeValue(s.ctx, wide);
    JS_FreeValue(s.ctx, driver);
    JS_FreeValue(s.ctx, cb);
    cleanup(&s);
    assert(h.ledger.live == 0 && h.ledger.bytes == 0);
    printf("AARCH64_SHARED_ALLOCATOR_REENTRY_OK mode=%s hits=%u live=0\n", mode, h.hits);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    ordinary_and_blocked(argv[1]);
    oom(argv[1]);
    allocator_callback(argv[1]);
    return 0;
}
