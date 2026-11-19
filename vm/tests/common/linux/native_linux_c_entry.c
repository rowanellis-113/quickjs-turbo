/* Public ABI/coercion/GC/realm/limit checks of numeric and builtin entries.
 * The sole private hook reads live anchors; it never infers hits from modes. */
#include "quickjs.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

extern int JS_LinuxBuiltinProbe(JSRuntime *, uintptr_t *);
static JSContext *caller, *foreign;
static JSValue nested;
static double returned, input0, input1;
static unsigned numeric_calls, observed, views, window_views, stack_views, transient_views,
    reentries;

static size_t oom_case(size_t fail_at)
{
    Allocator allocation = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocation);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *text =
        "(function(){return 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'.slice(1,49)+(new Number(123)).toString()})";
    JSValue root = JS_Eval(ctx, text, strlen(text), "builtin-oom", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(root));
    JSValue value = JS_Call(ctx, root, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    JS_FreeValue(ctx, value);
    allocation.sequence = 0;
    allocation.fail_at = fail_at;
    value = JS_Call(ctx, root, JS_UNDEFINED, 0, NULL);
    size_t count = allocation.sequence;
    allocation.fail_at = 0;
    if (JS_IsException(value))
        JS_FreeValue(ctx, JS_GetException(ctx));
    else {
        const char *result = JS_ToCString(ctx, value);
        assert(result && strlen(result) == 51);
        JS_FreeCString(ctx, result);
    }
    JS_FreeValue(ctx, value);
    if (fail_at && fail_at <= count)
        assert(allocation.rejected == 1);
    value = JS_Call(ctx, root, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    JS_FreeValue(ctx, root);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocation.live && !allocation.bytes);
    return count;
}
static int interrupt(JSRuntime *rt, void *opaque)
{
    (void)rt;
    return ++*(unsigned *)opaque > 2;
}

static void collect_and_reenter(void)
{
    JSRuntime *rt = JS_GetRuntime(caller);
    JS_RunGC(rt);
    JSValue value = JS_Call(foreign, nested, JS_UNDEFINED, 0, NULL);
    int32_t n = 0;
    assert(!JS_IsException(value) && JS_ToInt32(foreign, &n, value) == 0 && n == 31);
    JS_FreeValue(foreign, value);
    ++reentries;
}
static double unary(double a)
{
    input0 = a;
    ++numeric_calls;
    if (!(numeric_calls % 31))
        collect_and_reenter();
    return returned;
}
static double binary(double a, double b)
{
    input1 = b;
    return unary(a);
}
static JSValue observe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    uintptr_t words[7];
    ++observed;
    if (JS_LinuxBuiltinProbe(JS_GetRuntime(ctx), words)) {
        assert(words[1] == words[2]);
        assert(words[0] == 1 || words[0] == 3 || words[0] == 4);
        ++views;
        if (words[0] == 1) {
            ++window_views;
            assert(words[5] >= words[6] && words[5] + 128 <= words[6] + words[3]);
        }
        if (words[0] == 3)
            ++stack_views;
        if (words[0] == 4)
            ++transient_views;
    }
    collect_and_reenter();
    JS_SetMaxStackSize(JS_GetRuntime(ctx), (observed & 1) ? 0 : 1024 * 1024);
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "linux-c-entry", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "ENTRY ERROR %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        abort();
    }
    return value;
}
static int same(double a, double b)
{
    if (isnan(a))
        return isnan(b);
    return a == b && (a != 0 || !!signbit(a) == !!signbit(b));
}
int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        size_t count = oom_case(0);
        assert(count > 0 && count < 1000);
        for (size_t i = 1; i <= count + 2; ++i)
            (void)oom_case(i);
        printf("LINUX_C_ENTRY_OOM_OK injections=%zu recovery-and-zero-ledgers\n", count);
        return 0;
    }
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    caller = JS_NewContext(rt);
    foreign = JS_NewContext(rt);
    assert(caller && foreign);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    nested = evaluate(foreign, "(function(){return 31})");
    JSValue global = JS_GetGlobalObject(caller);
    JSValue foreign_global = JS_GetGlobalObject(foreign);
    assert(JS_SetPropertyStr(caller, global, "ForeignTypeError",
                             JS_GetPropertyStr(foreign, foreign_global, "TypeError")) >= 0);
    JS_FreeValue(foreign, foreign_global);
    assert(JS_SetPropertyStr(caller, global, "observe",
                             JS_NewCFunction(caller, observe, "observe", 0)) >= 0);
    static const double results[] = {
        0,   -0.0, 1,       -1,      2147483647.0, -2147483648.0, 2147483648.0, -2147483649.0,
        1.5, -1.5, DBL_MIN, DBL_MAX, NAN,          INFINITY,      -INFINITY};
    const int formals[] = {0, 1, 2, 7, 255}, actuals[] = {0, 1, 2, 7, 256};
    for (unsigned proto = 0; proto < 2; ++proto)
        for (unsigned f = 0; f < sizeof(formals) / sizeof(formals[0]); ++f)
            for (unsigned a = 0; a < sizeof(actuals) / sizeof(actuals[0]); ++a) {
                /* The original typed C switch reads its prototype's arity
                 * from max(formal,actual) slots. Do not construct an invalid
                 * host descriptor with fewer than that many available cells. */
                if (formals[f] < (int)proto + 1 && actuals[a] < (int)proto + 1)
                    continue;
                JSCFunctionType function;
                if (proto)
                    function.f_f_f = binary;
                else
                    function.f_f = unary;
                JSValue fn = JS_NewCFunction2(foreign, function.generic, "numeric", formals[f],
                                              proto ? JS_CFUNC_f_f_f : JS_CFUNC_f_f, 0);
                assert(!JS_IsException(fn));
                assert(JS_SetPropertyStr(caller, global, "numeric", fn) >= 0);
                char code[4096];
                size_t used = (size_t)snprintf(code, sizeof(code), "(function(){return numeric(");
                for (int i = 0; i < actuals[a]; ++i)
                    used += (size_t)snprintf(code + used, sizeof(code) - used, "%s%d", i ? "," : "",
                                             i - 13);
                used += (size_t)snprintf(code + used, sizeof(code) - used, ")})");
                assert(used < sizeof(code));
                JSValue root = evaluate(caller, code);
                for (unsigned r = 0; r < sizeof(results) / sizeof(results[0]); ++r) {
                    returned = results[r];
                    JSValue value = JS_Call(caller, root, JS_UNDEFINED, 0, NULL);
                    double out;
                    assert(!JS_IsException(value) && JS_ToFloat64(caller, &out, value) == 0 &&
                           same(returned, out));
                    assert(actuals[a] ? same(input0, -13) : isnan(input0));
                    if (proto)
                        assert(actuals[a] >= 2 ? same(input1, -12) : isnan(input1));
                    JS_FreeValue(caller, value);
                }
                JS_FreeValue(caller, root);
            }
    JSCFunctionType checked_function = {.f_f_f = binary};
    JSValue checked_numeric =
        JS_NewCFunction2(foreign, checked_function.generic, "numeric", 2, JS_CFUNC_f_f_f, 0);
    assert(!JS_IsException(checked_numeric) &&
           JS_SetPropertyStr(caller, global, "numeric", checked_numeric) >= 0);
    JSValue argument_root = evaluate(caller, "(function(a,b){return numeric(a,b)})");
    for (unsigned i = 0; i < sizeof(results) / sizeof(results[0]); ++i) {
        JSValue arguments[2] = {JS_NewFloat64(caller, results[i]),
                                JS_NewFloat64(caller, results[(i + 1) % 15])};
        JSValue result = JS_Call(caller, argument_root, JS_UNDEFINED, 2, arguments);
        assert(!JS_IsException(result) && same(input0, results[i]) &&
               same(input1, results[(i + 1) % 15]));
        JS_FreeValue(caller, result);
        JS_FreeValue(caller, arguments[0]);
        JS_FreeValue(caller, arguments[1]);
    }
    JS_FreeValue(caller, argument_root);
    JSValue value = evaluate(
        caller,
        "function repeatViews(b,s,e){let n=0;for(let i=0;i<250;i++){n+=b.slice(1,4).length;n+='abcdef'.slice(s,e).length}return n}"
        "function sameWindow(b){b.slice(1,4);b.slice(1,4);b.slice(1,4);return b.slice(1,4)}"
        "function sliceZero(s){return s.slice()}function sliceOne(s,a){return s.slice(a)}"
        "function numberView(n){return n.toString()}"
        "(function(){let n=0;let x={valueOf(){observe();return -13}};"
        "numeric(x,x);numeric(null,true);numeric('17','-0');"
        "if(!Object.is(Math.sin(-0),-0)||!Object.is(Math.pow(-0,3),-0))throw Error('numeric input');"
        "try{numeric(1n,1);throw 1}catch(e){if(!(e instanceof ForeignTypeError))throw e}"
        "try{numeric(Symbol(),1);throw 2}catch(e){if(!(e instanceof ForeignTypeError))throw e}"
        "let stop={valueOf(){throw 39}};try{numeric(stop);throw 3}catch(e){if(e!==39)throw e}"
        "let box={slice:String.prototype.slice,toString(){observe();return 'abcdef'}};"
        "if(sameWindow(box)!=='bcd')throw Error('consecutive window reuse');"
        "let start={valueOf(){observe();return -3}},end={valueOf(){observe();return 99}};"
        "if(repeatViews(box,start,end)!==1500)throw Error('coercion');"
        "for(let i=0;i<250;i++){"
        "if(sliceZero('abcdef')!=='abcdef'||sliceOne('abcdef',2)!=='cdef')throw Error('missing');"
        "if(numberView(new Number(i))!==String(i))throw Error('number');"
        "if((123).toString(16)!=='7b')throw Error('radix');n++}"
        "if(numberView(-0)!=='0'||numberView(NaN)!=='NaN'||numberView(Infinity)!=='Infinity'||numberView(-1.25)!=='-1.25')throw Error('number view');"
        "let sl=String.prototype.slice;try{sl.call(null);throw 4}catch(e){if(!(e instanceof TypeError))throw e}"
        "let bad={slice:sl,toString(){throw 41}};try{bad.slice();throw 5}catch(e){if(e!==41)throw e}"
        "let spoof={toString:Number.prototype.toString};try{spoof.toString();throw 6}catch(e){if(!(e instanceof TypeError))throw e}"
        "function recurse(n){let s='abcdef'.slice(1);return n?recurse(n-1)+s.length:s.length}"
        "if(recurse(80)!==405)throw Error('window lifetime');return n})()");
    int32_t n;
    assert(JS_ToInt32(caller, &n, value) == 0 && n == 250);
    JS_FreeValue(caller, value);
    int active = !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_SHARED_ENTRY") &&
                 !getenv("QJS_DISABLE_DIRECT_HOST_CALL") && !getenv("QJS_RETAIN_SCOPED_HOST") &&
                 !getenv("QJS_DISABLE_NATIVE_SLICE") && !getenv("QJS_DISABLE_NATIVE_CALL_LINK") &&
                 !getenv("QJS_DISABLE_NATIVE_VM_BRIDGE") &&
                 !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    assert(observed >= 750 && (active ? views >= 750 : views == 0));
    if (active && getenv("QJS_DISABLE_NATIVE_FRAME_ARENA"))
        assert(stack_views >= 750 && !window_views && !transient_views);
    else if (active && getenv("QJS_DISABLE_NATIVE_FRAME_REUSE"))
        assert(transient_views > 0 && !window_views);
    else if (active)
        assert(window_views >= 750 && !transient_views);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSValue interrupt_root = evaluate(caller, "(function(x){return x.slice(1)})");
    JSValue interrupt_receiver =
        evaluate(caller, "({slice:String.prototype.slice,toString(){for(;;){}}})");
    unsigned interruptions = 0;
    JS_SetInterruptHandler(rt, interrupt, &interruptions);
    value = JS_Call(caller, interrupt_root, JS_UNDEFINED, 1, &interrupt_receiver);
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(JS_IsException(value) && interruptions >= 3);
    JS_FreeValue(caller, JS_GetException(caller));
    JS_FreeValue(caller, value);
    JS_FreeValue(caller, interrupt_receiver);
    JS_FreeValue(caller, interrupt_root);
    value = evaluate(caller, "sliceOne('abcdef',2)");
    const char *recovery = JS_ToCString(caller, value);
    assert(recovery && !strcmp(recovery, "cdef"));
    JS_FreeCString(caller, recovery);
    JS_FreeValue(caller, value);
    JS_FreeValue(caller, global);
    JS_FreeValue(foreign, nested);
    JS_FreeContext(foreign);
    JS_FreeContext(caller);
    JS_FreeRuntime(rt);
    printf(
        "LINUX_C_ENTRY_OK numeric=%u observations=%u views=%u window=%u stack=%u transient=%u reentry=%u interrupts=%u\n",
        numeric_calls, observed, views, window_views, stack_views, transient_views, reentries,
        interruptions);
    return 0;
}
