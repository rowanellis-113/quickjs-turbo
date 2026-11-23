/* Public ownership,GC,interrupt,realm,thread and warmed fault qualification. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <pthread.h>
#ifdef __APPLE__
#ifndef PTHREAD_BARRIER_SERIAL_THREAD
#define PTHREAD_BARRIER_SERIAL_THREAD (-1)
typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    unsigned count;
    unsigned waiting;
    unsigned generation;
} pthread_barrier_t;
static int pthread_barrier_init(pthread_barrier_t *b, const void *attr, unsigned count)
{
    (void)attr;
    if (count == 0)
        return -1;
    if (pthread_mutex_init(&b->mutex, NULL) != 0)
        return -1;
    if (pthread_cond_init(&b->cond, NULL) != 0) {
        pthread_mutex_destroy(&b->mutex);
        return -1;
    }
    b->count = count;
    b->waiting = 0;
    b->generation = 0;
    return 0;
}
static int pthread_barrier_destroy(pthread_barrier_t *b)
{
    pthread_cond_destroy(&b->cond);
    pthread_mutex_destroy(&b->mutex);
    return 0;
}
static int pthread_barrier_wait(pthread_barrier_t *b)
{
    pthread_mutex_lock(&b->mutex);
    unsigned gen = b->generation;
    if (++b->waiting == b->count) {
        b->waiting = 0;
        b->generation++;
        pthread_cond_broadcast(&b->cond);
        pthread_mutex_unlock(&b->mutex);
        return PTHREAD_BARRIER_SERIAL_THREAD;
    }
    while (gen == b->generation)
        pthread_cond_wait(&b->cond, &b->mutex);
    pthread_mutex_unlock(&b->mutex);
    return 0;
}
#endif
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

typedef struct {
    JSClassID id;
    unsigned finalized, order[4], polls;
    int abort_poll;
} Host;
static void finalizer(JSRuntime *rt, JSValue value)
{
    Host *h = JS_GetRuntimeOpaque(rt);
    assert(h->finalized < 4);
    h->order[h->finalized++] = (unsigned)(uintptr_t)JS_GetOpaque(value, h->id);
}
static JSValue tracked(JSContext *ctx, Host *host, unsigned id)
{
    JSValue value = JS_NewObjectClass(ctx, host->id);
    assert(!JS_IsException(value));
    JS_SetOpaque(value, (void *)(uintptr_t)id);
    return value;
}
static JSValue eval(JSContext *ctx, const char *source)
{
    JSValue value =
        JS_Eval(ctx, source, strlen(source), "linux-global-public", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", s ? s : "exception");
        abort();
    }
    return value;
}
static void discard(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value))
        value = JS_GetException(ctx);
    JS_FreeValue(ctx, value);
}
static void set_global(JSContext *ctx, const char *name, JSValue value)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, name, value) > 0);
    JS_FreeValue(ctx, global);
}
static void erase(JSContext *ctx, const char *name)
{
    JSValue global = JS_GetGlobalObject(ctx);
    JSAtom atom = JS_NewAtom(ctx, name);
    assert(JS_DeleteProperty(ctx, global, atom, JS_PROP_THROW) > 0);
    JS_FreeAtom(ctx, atom);
    JS_FreeValue(ctx, global);
}
static JSValue mutate(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *h = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    erase(ctx, "linuxGlobalOwned");
    JS_RunGC(JS_GetRuntime(ctx));
    assert(!h->finalized);
    for (unsigned i = 0; i < 160; ++i) {
        char key[40];
        snprintf(key, sizeof(key), "globalRelocate%u", i);
        set_global(ctx, key, JS_NewInt32(ctx, (int)i));
    }
    set_global(ctx, "linuxGlobalOwned", tracked(ctx, h, 2));
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static int interrupt(JSContext *ctx, void *opaque)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    Host *h = opaque;
    ++h->polls;
    JS_RunGC(rt);
    return h->abort_poll;
}
static JSRuntime *runtime(Allocator *ledger, Host *host)
{
    JSRuntime *rt = JS_NewRuntime2(&functions, ledger);
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JS_SetRuntimeOpaque(rt, host);
    JS_NewClassID(rt, &host->id);
    JSClassDef def = {0};
    def.class_name = "GlobalOwner";
    def.finalizer = finalizer;
    assert(JS_NewClass(rt, host->id, &def) == 0);
    return rt;
}
static void ownership_and_realms(void)
{
    Allocator ledger = {0};
    Host host = {0};
    JSRuntime *rt = runtime(&ledger, &host);
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    assert(a && b);
    set_global(b, "linuxGlobalOwned", tracked(b, &host, 1));
    set_global(b, "mutateGlobalPort", JS_NewCFunction(b, mutate, "mutateGlobalPort", 0));
    JSValue fn = eval(
        b,
        "(function(n){let first;for(let i=0;i<n;++i)first=linuxGlobalOwned;mutateGlobalPort();let last;for(let i=0;i<n;++i)last=linuxGlobalOwned;return [first,last];})");
    JSValue count = JS_NewInt32(a, 48), array = JS_Call(a, fn, JS_UNDEFINED, 1, &count);
    assert(!JS_IsException(array) && !host.finalized);
    JSValue first = JS_GetPropertyUint32(a, array, 0), last = JS_GetPropertyUint32(a, array, 1);
    assert((uintptr_t)JS_GetOpaque(first, host.id) == 1 &&
           (uintptr_t)JS_GetOpaque(last, host.id) == 2);
    erase(b, "linuxGlobalOwned");
    JS_RunGC(rt);
    assert(!host.finalized);
    JS_FreeValue(a, array);
    JS_FreeValue(a, first);
    assert(host.finalized == 1 && host.order[0] == 1);
    JS_FreeValue(a, last);
    assert(host.finalized == 2 && host.order[1] == 2);
    JS_FreeValue(b, fn);
    set_global(a, "foreignNumber", JS_NewInt32(a, 11));
    set_global(b, "foreignNumber", JS_NewInt32(b, 23));
    fn = eval(b, "(function(n){let sum=0;for(let i=0;i<n;++i)sum+=foreignNumber;return sum;})");
    JSValue n = JS_NewInt32(a, 25000), result;
    JS_SetInterruptHandler(rt, interrupt, &host);
    result = JS_Call(a, fn, JS_UNDEFINED, 1, &n);
    int32_t sum = 0;
    assert(!JS_IsException(result) && JS_ToInt32(a, &sum, result) == 0 && sum == 575000 &&
           host.polls > 0);
    JS_FreeValue(a, result);
    host.abort_poll = 1;
    result = JS_Call(a, fn, JS_UNDEFINED, 1, &n);
    assert(JS_IsException(result));
    discard(a, result);
    host.abort_poll = 0;
    JS_SetInterruptHandler(rt, NULL, NULL);
    result = JS_Call(a, fn, JS_UNDEFINED, 1, &count);
    assert(!JS_IsException(result));
    JS_FreeValue(a, result);
    JS_FreeValue(b, fn);
    fn = eval(b, "(function(){return foreignMissingGlobal;})");
    result = JS_Call(a, fn, JS_UNDEFINED, 0, NULL);
    assert(JS_IsException(result));
    JSValue error = JS_GetException(a), actual = JS_GetPrototype(a, error),
            wanted = eval(b, "ReferenceError.prototype");
    assert(JS_VALUE_GET_PTR(actual) == JS_VALUE_GET_PTR(wanted));
    JS_FreeValue(a, error);
    JS_FreeValue(a, actual);
    JS_FreeValue(b, wanted);
    JS_FreeValue(b, fn);
    JS_FreeContext(a);
    JS_FreeContext(b);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes && host.finalized == 2);
}
static size_t fault_sample(size_t fault, unsigned *rejected)
{
    Allocator ledger = {0};
    Host host = {0};
    JSRuntime *rt = runtime(&ledger, &host);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    set_global(ctx, "linuxGlobalOwned", tracked(ctx, &host, 1));
    JSValue fn =
        eval(ctx, "(function(n){let x;for(let i=0;i<n;++i)x=linuxGlobalOwned;return {x,n};})");
    JSValue n = JS_NewInt32(ctx, 32), result;
    for (unsigned warm = 0; warm < 3; ++warm) {
        result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &n);
        assert(!JS_IsException(result));
        JS_FreeValue(ctx, result);
    }
    JS_RunGC(rt);
    ledger.sequence = 0;
    ledger.fail_at = fault;
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &n);
    size_t requests = ledger.sequence;
    *rejected = ledger.rejected;
    ledger.fail_at = 0;
    discard(ctx, result);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &n);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes && host.finalized == 1);
    return requests;
}
typedef struct {
    unsigned id;
} Thread;
static pthread_barrier_t barrier;
static void *thread(void *opaque)
{
    Thread *t = opaque;
    Allocator ledger = {0};
    Host host = {0};
    JSRuntime *rt = runtime(&ledger, &host);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    set_global(ctx, "globalThreadValue", JS_NewInt32(ctx, (int)t->id));
    JSValue fn = eval(
        ctx, "(function(n){let sum=0;for(let i=0;i<n;++i)sum+=globalThreadValue;return sum;})");
    int code = pthread_barrier_wait(&barrier);
    assert(code == 0 || code == PTHREAD_BARRIER_SERIAL_THREAD);
    JSValue n = JS_NewInt32(ctx, 2048), result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &n);
    int32_t value = 0;
    assert(!JS_IsException(result) && JS_ToInt32(ctx, &value, result) == 0 &&
           value == (int)t->id * 2048);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes);
    return NULL;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        unsigned rejected = 0, total = 0;
        size_t requests = fault_sample(0, &rejected);
        assert(!rejected && requests > 0 && requests < 128);
        for (size_t i = 1; i <= requests + 2; ++i) {
            fault_sample(i, &rejected);
            total += rejected;
        }
        assert(total == requests);
        printf("LINUX_GLOBAL_BINDINGS_OOM_OK faults=%u\n", total);
        return 0;
    }
    assert(argc == 1);
    Thread data[2] = {{17}, {31}};
    pthread_t ids[2];
    assert(pthread_barrier_init(&barrier, NULL, 2) == 0);
    for (unsigned i = 0; i < 2; ++i)
        assert(pthread_create(ids + i, NULL, thread, data + i) == 0);
    for (unsigned i = 0; i < 2; ++i)
        assert(pthread_join(ids[i], NULL) == 0);
    assert(pthread_barrier_destroy(&barrier) == 0);
    ownership_and_realms();
    puts("LINUX_GLOBAL_BINDINGS_PUBLIC_OK threads=2 owners=2");
    return 0;
}
