/* Public character/Symbol semantics, bounded owner saturation, threads and OOM. */
#include "quickjs.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error String ownership qualification needs assertions.
#endif
#include "../native_oom_allocator.h"
#ifdef STRING_NO_PRIVATE_CACHE_OBSERVATION
static _Atomic(JSRuntime *) JS_FrameSmallCharOwners[16];
#else
extern _Atomic(JSRuntime *) JS_FrameSmallCharOwners[16];
#endif
static const char *semantics =
    "(()=>{for(let i=0;i<256;i++){const a=String.fromCharCode(i),b=String.fromCharCode(i);"
    "if(a!==b||a.length!==1||a.charCodeAt(0)!==i||a[0]!==a)throw Error('character');"
    "const s=Symbol(a),t=Symbol(a);if(s===t||s.description!==a||t.description!==a||typeof a!=='string')throw Error('symbol');"
    "if(String.fromCharCode(i)!==a||JSON.parse(JSON.stringify(a))!==a)throw Error('mutated character');}return 256})()";
static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue value = JS_Eval(ctx, source, strlen(source), "linux-string-owner", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(value));
    return value;
}
static void check(JSContext *ctx)
{
    JSValue value = evaluate(ctx, semantics);
    int32_t result = 0;
    assert(JS_ToInt32(ctx, &result, value) == 0 && result == 256);
    JS_FreeValue(ctx, value);
    JS_RunGC(JS_GetRuntime(ctx));
}
static unsigned owners(void)
{
    unsigned count = 0;
    for (unsigned i = 0; i < 16; ++i)
        count += atomic_load_explicit(&JS_FrameSmallCharOwners[i], memory_order_acquire) != NULL;
    return count;
}
static void saturation(void)
{
    Allocator memory[18] = {0};
    JSRuntime *rt[18];
    JSContext *ctx[18];
    assert(owners() == 0);
    for (unsigned i = 0; i < 18; ++i) {
        rt[i] = JS_NewRuntime2(&functions, &memory[i]);
        assert(rt[i]);
        ctx[i] = JS_NewContext(rt[i]);
        assert(ctx[i]);
        check(ctx[i]);
    }
    assert(owners() == (getenv("QJS_DISABLE_SMALL_CHAR_CACHE") ? 0 : 16));
    for (unsigned i = 0; i < 18; ++i) {
        unsigned index = (i * 5) % 18;
        check(ctx[index]);
        JS_FreeContext(ctx[index]);
        JS_FreeRuntime(rt[index]);
        assert(memory[index].live == 0 && memory[index].bytes == 0);
    }
    assert(owners() == 0);
}
static pthread_barrier_t barrier;
static void *thread(void *unused)
{
    int waited = pthread_barrier_wait(&barrier);
    assert(waited == 0 || waited == PTHREAD_BARRIER_SERIAL_THREAD);
    for (unsigned i = 0; i < 6; ++i) {
        Allocator memory = {0};
        JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        check(ctx);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(!memory.live && !memory.bytes);
    }
    return unused;
}
static unsigned failures, injected;
static size_t trial(size_t fault, int cold)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue value = evaluate(ctx, cold ? "(function(){return String.fromCharCode(243);})"
                                       : "(function(c){return String.fromCharCode(c);})");
    JSValue argument = JS_NewInt32(ctx, 257);
    if (!cold) {
        /* Warm function/intrinsic metadata with an uncached wide character;
         * every Latin-1 cache miss and atom-table growth remains cold below. */
        for (unsigned i = 0; i < 2; ++i) {
            JSValue warm = JS_Call(ctx, value, JS_UNDEFINED, 1, &argument);
            assert(!JS_IsException(warm) && JS_IsString(warm));
            JS_FreeValue(ctx, warm);
        }
    }
    size_t before = memory.sequence;
    memory.fail_at = fault ? before + fault : 0;
    JSValue result = JS_UNDEFINED;
    for (unsigned i = 0; i < (cold ? 1 : 256); ++i) {
        argument = JS_NewInt32(ctx, i);
        result = JS_Call(ctx, value, JS_UNDEFINED, cold ? 0 : 1, cold ? NULL : &argument);
        if (JS_IsException(result))
            break;
        assert(JS_IsString(result));
        JS_FreeValue(ctx, result);
        result = JS_UNDEFINED;
    }
    memory.fail_at = 0;
    size_t count = memory.sequence - before;
    injected += memory.rejected;
    if (JS_IsException(result)) {
        ++failures;
        result = JS_GetException(ctx);
    }
    JS_FreeValue(ctx, result);
    argument = JS_NewInt32(ctx, 243);
    result = JS_Call(ctx, value, JS_UNDEFINED, cold ? 0 : 1, cold ? NULL : &argument);
    if (JS_IsException(result) || !JS_IsString(result)) {
        fprintf(stderr, "STRING_RECOVERY_FAILURE fault=%zu attempts=%zu rejected=%u\n", fault,
                count, memory.rejected);
        if (JS_IsException(result)) {
            JSValue error = JS_GetException(ctx);
            const char *text = JS_ToCString(ctx, error);
            fprintf(stderr, "STRING_RECOVERY_EXCEPTION %s\n", text ? text : "<conversion failed>");
            JS_FreeCString(ctx, text);
            JS_FreeValue(ctx, error);
        }
    }
    assert(!JS_IsException(result) && JS_IsString(result));
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    assert(owners() == 0);
    return count;
}
int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "cold")) {
        trial((size_t)strtoull(argv[2], NULL, 10), 1);
        return 0;
    }
    if (argc == 2) {
        trial((size_t)strtoull(argv[1], NULL, 10), 0);
        return 0;
    }
    saturation();
    pthread_t workers[2];
    assert(pthread_barrier_init(&barrier, NULL, 2) == 0);
    for (unsigned i = 0; i < 2; ++i)
        assert(pthread_create(&workers[i], NULL, thread, NULL) == 0);
    for (unsigned i = 0; i < 2; ++i)
        assert(pthread_join(workers[i], NULL) == 0);
    assert(pthread_barrier_destroy(&barrier) == 0 && owners() == 0);
    size_t count = trial(0, 0);
    for (size_t fault = 1; fault <= count + 1; ++fault)
        trial(fault, 0);
    assert(injected && failures);
    printf(
        "LINUX_STRING_OWNERSHIP_OK runtimes=18 threads=2 allocations=%zu injected=%u exceptions=%u\n",
        count, injected, failures);
    return 0;
}
