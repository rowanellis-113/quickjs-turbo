/* Comprehensive verification of QuickJS-Turbo explicit C API (P0/P1/P2):
 * - P0.1: Decoupled own_bytecode tail OFF with native Property IC ON (PIC-only)
 * - P0.2: Low-bit tagged warmup lazy IC allocation + JS_PurgePropertyIC(rt)
 * - P1.3: Explicit QJS_SetTurboDefaults / JS_SetRuntimeTurboOptions without getenv races
 * - P2.7: Structured read-only QJS_GetTurboInfo(rt, &info) diagnostics */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs-turbo.h"
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int32_t eval_int32(JSContext *ctx, const char *code, const char *filename)
{
    JSValue val = JS_Eval(ctx, code, strlen(code), filename, JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(val));
    int32_t out = 0;
    assert(JS_ToInt32(ctx, &out, val) == 0);
    JS_FreeValue(ctx, val);
    return out;
}

static void test_process_info_and_defaults(void)
{
    QJSTurboInfo info;
    assert(QJS_GetTurboInfo(NULL, &info) == 0);
    assert(info.struct_size == sizeof(QJSTurboInfo));
    assert(info.backend_name != NULL && info.backend_name[0] != '\0');

    QJSTurboOptions opts;
    QJS_TurboOptionsInit(&opts);
    assert(opts.struct_size == sizeof(QJSTurboOptions));
    assert(opts.property_ic == QJS_TURBO_DEFAULT);
    assert(opts.own_bytecode_tail == QJS_TURBO_DEFAULT);
    assert(opts.property_ic_warmup == -1);

    /* Reject malformed struct_size cleanly. */
    QJSTurboOptions bad = opts;
    bad.struct_size = 4;
    assert(QJS_SetTurboDefaults(&bad) != 0);
    QJSTurboOptions got;
    QJS_GetTurboDefaults(&got);
    assert(got.struct_size == sizeof(QJSTurboOptions));
    assert(QJS_GetTurboInfo(NULL, NULL) != 0);

    printf("TURBO_INFO backend=%s id=%d pic_compiled=%d tail_on=%d pregen=%d\n", info.backend_name,
           (int)info.backend, info.property_ic_compiled, info.own_bytecode_tail_on,
           info.pregenerated_asm);
}

static void test_pic_only_no_tail_mode(void)
{
    QJSTurboOptions opts;
    QJS_TurboOptionsInit(&opts);
    opts.own_bytecode_tail = QJS_TURBO_OFF;
    opts.property_ic = QJS_TURBO_ON;
    opts.property_ic_warmup = 0;
    assert(QJS_SetTurboDefaults(&opts) == 0);

    JSRuntime *rt = JS_NewRuntime();
    assert(rt != NULL);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx != NULL);

    QJSTurboInfo info;
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    assert(info.own_bytecode_tail_on == 0);
    if (info.property_ic_compiled)
        assert(info.property_ic_enabled == 1);

    /* Exercise own-property get, method get (get_field2), prototype lookup,
     * missing property, property replace, shape transition, megamorphic site,
     * exotic array receiver, and GC while tail copy is disabled. */
    const char *src =
        "(function() {"
        "  function Proto() {}"
        "  Proto.prototype.base = 7;"
        "  Proto.prototype.add = function(v) { return this.x + this.y + this.base + v; };"
        "  function makeObj(a, b) { var o = new Proto(); o.x = a; o.y = b; return o; }"
        "  function run(o) {"
        "    var m = o.missing === undefined ? 1 : 0;"
        "    o.x = o.x + 1;"
        "    return o.add(m);"
        "  }"
        "  var sum = 0;"
        "  for (var i = 0; i < 60; i++) {"
        "    var o = makeObj(i, i * 2);"
        "    sum += run(o);"
        "  }"
        "  /* Transition + polymorphic + megamorphic + exotic array */"
        "  function getA(obj) { return obj.a; }"
        "  var objs = ["
        "    {a:1}, {b:0,a:2}, {c:0,b:0,a:3}, {d:0,c:0,b:0,a:4},"
        "    {e:0,d:0,c:0,b:0,a:5}, {f:0,e:0,d:0,c:0,b:0,a:6}"
        "  ];"
        "  for (var k = 0; k < 20; k++) {"
        "    for (var j = 0; j < objs.length; j++) sum += getA(objs[j]);"
        "  }"
        "  var arr = [10, 20, 30];"
        "  function arrLen(a) { return a.length; }"
        "  for (var n = 0; n < 20; n++) sum += arrLen(arr);"
        "  return sum;"
        "})()";
    int32_t res = eval_int32(ctx, src, "pic_only.js");
    /* sum1 = sum_{i=0..59} ((i+1) + 2i + 7 + 1) = sum(3i + 9) = 3*1770 + 540 = 5850
     * sum2 = 20 * (1+2+3+4+5+6) = 420
     * sum3 = 20 * 3 = 60
     * total = 6330 */
    assert(res == 6330);

    if (info.property_ic_compiled) {
        assert(QJS_GetTurboInfo(rt, &info) == 0);
        assert(info.property_ic_slab_count > 0);
        assert(info.property_ic_bytes > 0);
    }

    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}

static void test_warmup_and_purge(void)
{
    QJSTurboOptions defaults;
    QJS_TurboOptionsInit(&defaults);
    defaults.own_bytecode_tail = QJS_TURBO_OFF;
    defaults.property_ic = QJS_TURBO_ON;
    defaults.property_ic_warmup = 0;
    assert(QJS_SetTurboDefaults(&defaults) == 0);

    JSRuntime *rt = JS_NewRuntime();
    assert(rt != NULL);

    /* Configure per-runtime warmup=12 explicitly via C API. */
    QJSTurboOptions rt_opts;
    QJS_TurboOptionsInit(&rt_opts);
    rt_opts.property_ic_warmup = 12;
    assert(JS_SetRuntimeTurboOptions(rt, &rt_opts) == 0);

    JSContext *ctx = JS_NewContext(rt);
    assert(ctx != NULL);

    QJSTurboInfo info;
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    if (!info.property_ic_compiled) {
        assert(JS_PurgePropertyIC(rt) == 0);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        return;
    }
    assert(info.property_ic_enabled == 1);
    assert(info.property_ic_warmup == 12);
    assert(info.property_ic_slab_count == 0);
    assert(info.property_ic_bytes == 0);

    const char *setup = "globalThis.readX = function(o) { return o.x + o.y; };"
                        "globalThis.pt = { x: 10, y: 32 };"
                        "0;";
    assert(eval_int32(ctx, setup, "warmup_setup.js") == 0);

    /* 5 calls -> 10 property accesses < 12 warmup threshold => 0 slabs! */
    const char *cold_loop =
        "(function(){ var s = 0; for (var i = 0; i < 5; i++) s += readX(pt); return s; })()";
    assert(eval_int32(ctx, cold_loop, "warmup_cold.js") == 210);
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    assert(info.property_ic_slab_count == 0);
    assert(info.property_ic_bytes == 0);

    /* 20 more calls -> exceeds 12 warmup threshold => slab allocated! */
    const char *hot_loop =
        "(function(){ var s = 0; for (var i = 0; i < 20; i++) s += readX(pt); return s; })()";
    assert(eval_int32(ctx, hot_loop, "warmup_hot.js") == 840);
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    assert(info.property_ic_slab_count > 0);
    assert(info.property_ic_bytes > 0);
    size_t bytes_before_purge = info.property_ic_bytes;

    /* Purge idle IC slabs and verify complete reclamation. */
    size_t freed = JS_PurgePropertyIC(rt);
    assert(freed >= bytes_before_purge);
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    assert(info.property_ic_slab_count == 0);
    assert(info.property_ic_bytes == 0);

    /* Second purge on empty list returns 0. */
    assert(JS_PurgePropertyIC(rt) == 0);

    /* Re-warming after purge works identically and allocates fresh slab. */
    assert(eval_int32(ctx, hot_loop, "warmup_reheat.js") == 840);
    assert(QJS_GetTurboInfo(rt, &info) == 0);
    assert(info.property_ic_slab_count > 0);
    assert(info.property_ic_bytes > 0);

    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}

static void test_per_runtime_isolation(void)
{
    /* Verify two runtimes in the same process maintain independent warmup/IC state
     * without any environment variable mutation. */
    QJSTurboOptions def;
    QJS_TurboOptionsInit(&def);
    def.property_ic = QJS_TURBO_ON;
    def.property_ic_warmup = 0;
    assert(QJS_SetTurboDefaults(&def) == 0);

    JSRuntime *rt_eager = JS_NewRuntime();
    JSRuntime *rt_lazy = JS_NewRuntime();
    assert(rt_eager != NULL && rt_lazy != NULL);

    QJSTurboOptions lazy_opts;
    QJS_TurboOptionsInit(&lazy_opts);
    lazy_opts.property_ic_warmup = 50;
    assert(JS_SetRuntimeTurboOptions(rt_lazy, &lazy_opts) == 0);

    JSContext *ctx_eager = JS_NewContext(rt_eager);
    JSContext *ctx_lazy = JS_NewContext(rt_lazy);
    assert(ctx_eager != NULL && ctx_lazy != NULL);

    const char *code = "globalThis.isoFn = function(x){ return x.a + x.b; };"
                       "var o = {a: 3, b: 4};"
                       "isoFn(o) + isoFn(o);";
    assert(eval_int32(ctx_eager, code, "iso_eager.js") == 14);
    assert(eval_int32(ctx_lazy, code, "iso_lazy.js") == 14);

    QJSTurboInfo info_eager, info_lazy;
    assert(QJS_GetTurboInfo(rt_eager, &info_eager) == 0);
    assert(QJS_GetTurboInfo(rt_lazy, &info_lazy) == 0);
    if (info_eager.property_ic_compiled) {
        assert(info_eager.property_ic_warmup == 0);
        assert(info_lazy.property_ic_warmup == 50);
        assert(info_eager.property_ic_slab_count > 0);
        assert(info_lazy.property_ic_slab_count == 0);
    }

    JS_FreeContext(ctx_lazy);
    JS_FreeContext(ctx_eager);
    JS_FreeRuntime(rt_lazy);
    JS_FreeRuntime(rt_eager);
}

int main(void)
{
    test_process_info_and_defaults();
    test_pic_only_no_tail_mode();
    test_warmup_and_purge();
    test_per_runtime_isolation();
    puts("TURBO_API_PASS");
    return 0;
}
