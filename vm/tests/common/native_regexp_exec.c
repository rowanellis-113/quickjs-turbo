/*
 * QuickJS Javascript Engine
 *
 * Copyright (c) 2017-2026 Fabrice Bellard
 * Copyright (c) 2017-2025 Charlie Gordon
 * Copyright (c) 2023-2026 Ben Noordhuis
 * Copyright (c) 2023-2026 Saúl Ibarra Corretgé
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
/* Public exec allocation/fault, GC and interrupt reentry regression checks. */
#include "quickjs.h"
#include <assert.h>
#ifdef NDEBUG
#error Assertions required
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
    JSRuntime *stress_rt;
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
    if (a->stress_rt)
        JS_SetGCThreshold(a->stress_rt, 0);
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
    if (a->stress_rt)
        JS_SetGCThreshold(a->stress_rt, 0);
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

static const char *cases[] = {
    "(function(){const r=/a/;return function(){const a=r.exec('ba');if(!a||a.index!==1||a[0]!=='a'||a.length!==1)throw Error('literal');return 1;};})()",
    "(function(){const r=/(a)(b)?/;return function(){const a=r.exec('a');if(!a||a.length!==3||a[2]!==undefined||!a.hasOwnProperty(2))throw Error('optional');return 3;};})()",
    "(function(){const r=new RegExp('(a)'.repeat(15));const s='a'.repeat(15);return function(){const a=r.exec(s);if(!a||a.length!==16||a[15]!=='a')throw Error('cap16');return 16;};})()",
    "(function(){const r=new RegExp('(a)'.repeat(16));const s='a'.repeat(16);return function(){const a=r.exec(s);if(!a||a.length!==17||a[16]!=='a')throw Error('cap17');return 17;};})()",
    "(function(){const r=new RegExp('(a)'.repeat(64));const s='a'.repeat(64);return function(){const a=r.exec(s);if(!a||a.length!==65||a[64]!=='a')throw Error('cap65');return 65;};})()",
    "(function(){const r=/(?<x>a)(b)?/d;return function(){const a=r.exec('a');if(!a||a.length!==3||a.groups.x!=='a'||a.indices[1][1]!==1||a.indices[2]!==undefined||!a.hasOwnProperty(2))throw Error('named');return 3;};})()",
    "(function(){const r=/(?<x>\u0100)(a)?(b)?/du;return function(){const a=r.exec('\u0100a');if(!a||a.length!==4||a.groups.x!=='\u0100'||a[3]!==undefined||!a.hasOwnProperty(3)||a.indices[2][1]!==2)throw Error('wide');return 4;};})()",
    "(function(){const r=/notpresent/g;return function(){r.lastIndex=0;const a=r.exec('aaa');if(a!==null||r.lastIndex!==0)throw Error('miss');return 0;};})()"};
static const int expected[] = {1, 3, 16, 17, 65, 3, 4, 0};
static unsigned trials, failures;
static size_t trial(unsigned mode, size_t at)
{
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue fn =
        JS_Eval(ctx, cases[mode], strlen(cases[mode]), "exec-owned-prepare", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    for (unsigned i = 0; i < 3; i++) {
        JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(v));
        JS_FreeValue(ctx, v);
    }
    JS_RunGC(rt);
    size_t before = a.sequence, base_bytes = a.bytes;
    a.peak = a.bytes;
    a.observe = 1;
    a.fail_at = at ? before + at : 0;
    JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    a.observe = 0;
    a.fail_at = 0;
    size_t attempts = a.sequence - before;
    if (!at)
        printf(
            "EXEC_ALLOC mode=%u attempts=%zu reallocs=%zu requested=%zu base_bytes=%zu peak_delta=%zu\n",
            mode, attempts, a.reallocs, a.requested, base_bytes, a.peak - base_bytes);
    if (JS_IsException(v)) {
        assert(at && JS_HasException(ctx));
        failures++;
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        if (!s || !strstr(s, "out of memory")) {
            fprintf(stderr, "Unexpected fault mode=%u at=%zu %s\n", mode, at, s ? s : "null");
            abort();
        }
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
    } else {
        int32_t n;
        assert(!JS_ToInt32(ctx, &n, v) && n == expected[mode]);
    }
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes);
    trials++;
    return attempts;
}
typedef struct {
    JSContext *ctx;
    JSValue fn;
    unsigned calls;
    int inside;
} Reentry;
static int poll(JSRuntime *rt, void *opaque)
{
    Reentry *r = opaque;
    if (r->inside)
        return 0;
    r->inside = 1;
    r->calls++;
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_RunGC(rt);
    JSValue v = JS_Call(r->ctx, r->fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(v));
    int32_t n;
    assert(!JS_ToInt32(r->ctx, &n, v) && n == 3);
    JS_FreeValue(r->ctx, v);
    JS_SetInterruptHandler(rt, poll, r);
    r->inside = 0;
    return 0;
}

static void gc_stress(void)
{
    for (unsigned mode = 0; mode < 9; mode++) {
        Allocator a = {0};
        JSRuntime *rt = JS_NewRuntime2(&functions, &a);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        const char *large =
            "(function(){const s='a'.repeat(241);const r=new RegExp('(?<n>a)'+'(a)'.repeat(240),'d');return function(){const a=r.exec(s);if(!a||a.length!==242||a.groups.n!=='a'||a[241]!=='a'||a.indices[241][1]!==241)throw Error('large-indices');return 242;};})()";
        const char *source = mode < 8 ? cases[mode] : large;
        JSValue fn = JS_Eval(ctx, source, strlen(source), "exec-gc-stress", JS_EVAL_TYPE_GLOBAL);
        assert(!JS_IsException(fn));
        a.stress_rt = rt;
        JS_SetGCThreshold(rt, 0);
        for (unsigned i = 0; i < 4; i++) {
            JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
            assert(!JS_IsException(v));
            int32_t n;
            assert(!JS_ToInt32(ctx, &n, v) && n == (mode < 8 ? expected[mode] : 242));
            JS_FreeValue(ctx, v);
        }
        a.stress_rt = NULL;
        JS_FreeValue(ctx, fn);
        JS_RunGC(rt);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(!a.live && !a.bytes);
    }
    puts("EXEC_GC_STRESS_OK modes=9");
}

static JSMemoryUsage guard_atom_usage_after_context(int exercise)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *source = "(function(exercise){for(let i=0;i<200;i++){if(exercise){"
                         "if('aba'.replace(/a/g,'')!=='b')throw Error('replace');"
                         "if('aba'.split(/a/).length!==3)throw Error('split');"
                         "}}})";
    JSValue fn = JS_Eval(ctx, source, strlen(source), "atom-lifetime", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    JSValue arg = JS_NewBool(ctx, exercise);
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &arg);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JSMemoryUsage usage;
    JS_ComputeMemoryUsage(rt, &usage);
    JS_FreeRuntime(rt);
    return usage;
}

static void guard_atom_lifetime(void)
{
    JSMemoryUsage control = guard_atom_usage_after_context(0);
    JSMemoryUsage exercise = guard_atom_usage_after_context(1);
    assert(exercise.atom_count == control.atom_count);
    puts("REGEXP_ATOM_LIFETIME_OK");
}

int main(void)
{
    guard_atom_lifetime();
    for (unsigned mode = 0; mode < sizeof(cases) / sizeof(cases[0]); mode++) {
        size_t n = trial(mode, 0);
        for (size_t at = 1; at <= n; at++)
            trial(mode, at);
    }
    assert(failures);
    gc_stress();
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    Reentry r = {0};
    r.ctx = ctx;
    r.fn = JS_Eval(ctx, cases[5], strlen(cases[5]), "exec-inner", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(r.fn));
    const char *code =
        "(function(){const s='a'.repeat(256)+'b';const r=/(?<x>a+)(b)$/du;return function(){for(let k=0;k<2000;k++){const a=r.exec(s);if(!a||a.length!==3||a[0].length!==257||a.groups.x.length!==256||a.indices[2][1]!==257)throw Error('outer');}return 7;};})()";
    JSValue fn = JS_Eval(ctx, code, strlen(code), "exec-outer", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    JS_SetInterruptHandler(rt, poll, &r);
    JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(!JS_IsException(v) && r.calls);
    int32_t n;
    assert(!JS_ToInt32(ctx, &n, v) && n == 7);
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, r.fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes);
    printf("EXEC_OWNERSHIP_OK trials=%u faults=%u reentry=%u\n", trials, failures, r.calls);
    return 0;
}
