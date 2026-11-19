/* Native owned missing/captured child lifetime and component controls. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID token_class;
static unsigned born, finalized, reentries;
static JSValue saved;
static uintptr_t host_sp;

static void finalizer(JSRuntime *rt, JSValue v)
{
    (void)rt;
    (void)v;
    ++finalized;
}
static JSValue checked(JSContext *ctx, JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "captured child: %s\n", s ? s : "<exception>");
        abort();
    }
    return v;
}
static JSValue eval(JSContext *ctx, const char *s)
{
    return checked(ctx, JS_Eval(ctx, s, strlen(s), "<arm-owned-captures>", JS_EVAL_TYPE_GLOBAL));
}
static JSValue token(JSContext *ctx)
{
    JSValue v = checked(ctx, JS_NewObjectClass(ctx, token_class));
    ++born;
    return v;
}
static void same(JSValue a, JSValue b)
{
    assert(JS_VALUE_GET_TAG(a) == JS_VALUE_GET_TAG(b));
    if (JS_IsUndefined(a))
        return;
    assert(JS_VALUE_GET_PTR(a) == JS_VALUE_GET_PTR(b));
}
static JSValue observe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue v = checked(ctx, JS_Call(ctx, argv[0], JS_UNDEFINED, 0, NULL));
    same(v, argv[1]);
    JS_FreeValue(ctx, v);
    ++reentries;
    return JS_UNDEFINED;
}
static JSValue retain(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    assert(JS_IsUndefined(saved));
    saved = JS_DupValue(ctx, argv[0]);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue recursion_probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    host_sp = (uintptr_t)__builtin_frame_address(0);
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue v = checked(ctx, JS_Call(ctx, argv[0], JS_UNDEFINED, 0, NULL));
    int32_t n;
    assert(JS_ToInt32(ctx, &n, v) == 0 && n == 0);
    JS_FreeValue(ctx, v);
    return JS_NewInt32(ctx, 37);
}
static void check_name(JSContext *ctx, JSValue function)
{
    JSValue name = checked(ctx, JS_GetPropertyStr(ctx, function, "name"));
    const char *text = JS_ToCString(ctx, name);
    assert(text && !strcmp(text, "f"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, name);
    JSAtom atom = JS_NewAtom(ctx, "name");
    JSPropertyDescriptor d = {0};
    assert(JS_GetOwnProperty(ctx, &d, function, atom) == 1);
    assert((d.flags & (JS_PROP_WRITABLE | JS_PROP_ENUMERABLE | JS_PROP_CONFIGURABLE)) ==
           JS_PROP_CONFIGURABLE);
    JS_FreeValue(ctx, d.value);
    JS_FreeValue(ctx, d.getter);
    JS_FreeValue(ctx, d.setter);
    JS_FreeAtom(ctx, atom);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int native = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    int capture_off = !strcmp(argv[1], "capture-off") || !strcmp(argv[1], "capture-zero");
    int missing_off = !strcmp(argv[1], "missing-off") || !strcmp(argv[1], "missing-zero");
    int owned_off = !strcmp(argv[1], "owned-off");
#ifdef QJS_AARCH64_VM_INSTRUMENT
    int readonly_captured = ARM_HAS_FORWARDING && !getenv("QJS_DISABLE_FRAME_CAPTURED_READONLY");
#endif
    int window_off = !strcmp(argv[1], "window-off");
    int name_off = !strcmp(argv[1], "name-off") || !strcmp(argv[1], "name-zero");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    saved = JS_UNDEFINED;
    JS_NewClassID(rt, &token_class);
    JSClassDef def = {0};
    def.class_name = "ArmCapturedToken";
    def.finalizer = finalizer;
    assert(JS_NewClass(rt, token_class, &def) == 0);
    JSValue driver = eval(ctx, "(function(f,a,b,c){var r=f(a,b,c);return r;})");
    JSValue missing_driver = eval(ctx, "(function(f,a){var r=f(a);return r;})");
    JSValue tails[] = {eval(ctx, "(function(f,a,b,c){return f(a,b,c);})"),
                       eval(ctx, "(function(f,a){return f(a);})")};
    JSValue functions[] = {
        eval(ctx, "(function(a,b,c){a=b;b=c;return a;})"),
        eval(ctx, "(function(a,b){return function(){return a;};})"),
        eval(ctx, "(function(a,b){var x=a,y=a,z=a;return function(){return x===y?z:x;};})"),
        eval(ctx, "(function(a,b){var f=function(){return a;};a=b;return f;})"),
        eval(ctx, "(function(a,check,b){var f=function(){return a;};check(f,a);a=b;return f;})"),
        eval(ctx, "(function(a,save){save(function(){return a;});throw 19;})")};
    JSValue cb = JS_NewCFunction(ctx, observe, "observe", 2);
    JSValue save = JS_NewCFunction(ctx, retain, "retain", 1);
    /* Prepare via actual public calls. No private flags or memory writes. */
    JSValue warm[] = {JS_UNDEFINED, cb, JS_UNDEFINED};
    for (unsigned k = 0; k < 5; k++) {
        JSValue v = checked(ctx, JS_Call(ctx, functions[k], JS_UNDEFINED, 3, warm));
        JS_FreeValue(ctx, v);
#ifdef QJS_AARCH64_VM_INSTRUMENT
        uintptr_t info[6];
        assert(qjs_aarch64_vm_function_info(functions[k], info));
        assert(info[3] == (k == 0 ? 0 : k == 2 ? 3 : 1));
        assert(info[0] == (!strcmp(argv[1], "legacy")    ? 0
                           : k >= 3 && name_off          ? 2
                           : k == 0                      ? 1
                           : k == 2                      ? 11
                           : k == 1 && readonly_captured ? 15
                                                         : 13));
#endif
    }
    JSValue throw_warm[] = {JS_UNDEFINED, save};
    JSValue v = JS_Call(ctx, functions[5], JS_UNDEFINED, 2, throw_warm);
    assert(JS_IsException(v));
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_FreeValue(ctx, saved);
    saved = JS_UNDEFINED;
    uint64_t calls = 0;
    unsigned cases = 0;
    for (unsigned pass = 0; pass < 12; pass++)
        for (unsigned k = 0; k < 5; k++) {
            JSValue a = token(ctx), b = token(ctx);
            for (unsigned missing = 0; missing < 2; missing++) {
                /* Reentrant case needs its real host argument. Missing semantics
             * are covered separately by the other four capture shapes. */
                if (k == 4 && missing)
                    continue;
                JSValue args[] = {functions[k], a, k == 4 ? cb : b, b};
#ifdef QJS_AARCH64_VM_INSTRUMENT
                QJSArmVMCounts before, after;
                qjs_aarch64_vm_counts(&before);
#endif
                JSValue selected = missing ? (pass & 1 ? tails[1] : missing_driver)
                                           : (pass & 1 ? tails[0] : driver);
                v = checked(ctx, JS_Call(ctx, selected, JS_UNDEFINED, missing ? 2 : 4, args));
#ifdef QJS_AARCH64_VM_INSTRUMENT
                qjs_aarch64_vm_counts(&after);
                calls += after.native_calls - before.native_calls;
                int expected_call = native;
                if (k == 0)
                    expected_call &= !owned_off && (!missing || !missing_off);
                else if (k == 1 && readonly_captured)
                    expected_call &=
                        !capture_off && (!missing || !window_off || (!owned_off && !missing_off));
                else
                    expected_call &= !capture_off && (k == 2 || !owned_off) &&
                                     (!missing || k == 2 || !missing_off);
                if (k == 2 && missing && window_off)
                    expected_call = 0;
                if (k >= 3 && name_off)
                    expected_call = 0;
                if (after.native_calls - before.native_calls != (uint64_t)expected_call) {
                    uintptr_t info[6];
                    assert(qjs_aarch64_vm_function_info(functions[k], info));
                    fprintf(
                        stderr,
                        "CAPTURE_METADATA kind=%llu formal=%llu locals=%llu refs=%llu code=%llu stack=%llu\n",
                        (unsigned long long)info[0], (unsigned long long)info[1],
                        (unsigned long long)info[2], (unsigned long long)info[3],
                        (unsigned long long)info[4], (unsigned long long)info[5]);
                    fprintf(stderr,
                            "CAPTURE_ROUTE k=%u missing=%u mode=%s calls=%llu expected=%d\n", k,
                            missing, argv[1],
                            (unsigned long long)(after.native_calls - before.native_calls),
                            expected_call);
                }
                assert(after.native_calls - before.native_calls == (uint64_t)expected_call);
                if (native)
                    assert(after.activations > before.activations);
                else
                    assert(after.activations == 0);
#endif
                JSValue expected = (k == 0 || k == 3) ? (missing ? JS_UNDEFINED : b)
                                   : k == 4           ? b
                                                      : a;
                if (k) {
                    if (k >= 3)
                        check_name(ctx, v);
                    JS_RunGC(rt);
                    JSValue result = checked(ctx, JS_Call(ctx, v, JS_UNDEFINED, 0, NULL));
                    same(result, expected);
                    JS_FreeValue(ctx, result);
                } else
                    same(v, expected);
                JS_FreeValue(ctx, v);
                ++cases;
            }
            JS_FreeValue(ctx, a);
            JS_FreeValue(ctx, b);
            JS_RunGC(rt);
            assert(finalized == born);
        }
    /* Zero actual arguments must never read the absent input prefix. */
    JSValue zero_driver = eval(ctx, "(function(f){var r=f();return r;})");
    for (unsigned k = 0; k < 4; k++) {
        JSValue arg = functions[k];
#ifdef QJS_AARCH64_VM_INSTRUMENT
        QJSArmVMCounts before, after;
        qjs_aarch64_vm_counts(&before);
#endif
        v = checked(ctx, JS_Call(ctx, zero_driver, JS_UNDEFINED, 1, &arg));
#ifdef QJS_AARCH64_VM_INSTRUMENT
        qjs_aarch64_vm_counts(&after);
        calls += after.native_calls - before.native_calls;
        int expected_call =
            native && (k == 0 ? !owned_off && !missing_off
                       : k == 1 && readonly_captured
                           ? !capture_off && (!window_off || (!owned_off && !missing_off))
                           : !capture_off && (k == 2 ? !window_off : !owned_off && !missing_off));
        if (k == 3 && name_off)
            expected_call = 0;
        assert(after.native_calls - before.native_calls == (uint64_t)expected_call);
#endif
        if (k) {
            JSValue r = checked(ctx, JS_Call(ctx, v, JS_UNDEFINED, 0, NULL));
            assert(JS_IsUndefined(r));
            JS_FreeValue(ctx, r);
        } else
            assert(JS_IsUndefined(v));
        JS_FreeValue(ctx, v);
        ++cases;
    }
    JS_FreeValue(ctx, zero_driver);
    JSValue recurse = eval(ctx, "(function rec(n,probe,unused){var c=function readN(){return n;};"
                                "if(n){var r=rec(n-1,probe);return r+1;}return probe(c);})");
    JSValue probe = JS_NewCFunction(ctx, recursion_probe, "recursionProbe", 1);
    JSValue recursive_args[] = {JS_NewInt32(ctx, 0), probe, JS_UNDEFINED};
    v = checked(ctx, JS_Call(ctx, recurse, JS_UNDEFINED, 3, recursive_args));
    int32_t recursive_result;
    assert(JS_ToInt32(ctx, &recursive_result, v) == 0 && recursive_result == 37);
    JS_FreeValue(ctx, v);
    uintptr_t shallow_sp = host_sp;
    recursive_args[0] = JS_NewInt32(ctx, 100);
#ifdef QJS_AARCH64_VM_INSTRUMENT
    QJSArmVMCounts recursive_before, recursive_after;
    qjs_aarch64_vm_counts(&recursive_before);
#endif
    v = checked(ctx, JS_Call(ctx, recurse, JS_UNDEFINED, 3, recursive_args));
    assert(JS_ToInt32(ctx, &recursive_result, v) == 0 && recursive_result == 137);
    JS_FreeValue(ctx, v);
    uintptr_t delta = shallow_sp > host_sp ? shallow_sp - host_sp : host_sp - shallow_sp;
    if (strcmp(argv[1], "legacy"))
        assert(delta == 0);
    else
        assert(delta > 0);
    uint64_t recursive_calls = 0;
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_counts(&recursive_after);
    recursive_calls = recursive_after.native_calls - recursive_before.native_calls;
    if (native && !capture_off && !missing_off && !owned_off)
        assert(recursive_calls >= 85);
    else
        assert(recursive_calls == 0);
    if (native)
        assert(recursive_after.activations - recursive_before.activations == 2);
    else
        assert(recursive_after.activations == 0);
#endif
    JS_FreeValue(ctx, recurse);
    JS_FreeValue(ctx, probe);
    /* Captures must detach on the exceptional return as well. */
    for (unsigned pass = 0; pass < 12; pass++) {
        JSValue a = token(ctx), args[] = {functions[5], a, save, JS_UNDEFINED};
        v = JS_Call(ctx, driver, JS_UNDEFINED, 4, args);
        assert(JS_IsException(v));
        JSValue e = JS_GetException(ctx);
        int32_t n;
        assert(JS_ToInt32(ctx, &n, e) == 0 && n == 19);
        JS_FreeValue(ctx, e);
        JS_FreeValue(ctx, a);
        JS_RunGC(rt);
        assert(finalized + 1 == born);
        v = checked(ctx, JS_Call(ctx, saved, JS_UNDEFINED, 0, NULL));
        assert(JS_VALUE_GET_TAG(v) == JS_TAG_OBJECT);
        JS_FreeValue(ctx, v);
        JS_FreeValue(ctx, saved);
        saved = JS_UNDEFINED;
        JS_RunGC(rt);
        assert(finalized == born);
        ++cases;
    }
    JS_FreeValue(ctx, cb);
    JS_FreeValue(ctx, save);
    for (unsigned k = 0; k < 6; k++)
        JS_FreeValue(ctx, functions[k]);
    for (unsigned k = 0; k < 2; k++)
        JS_FreeValue(ctx, tails[k]);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, missing_driver);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(finalized == born);
    printf(
        "AARCH64_CAPTURED_ENTRY_OK mode=%s cases=%u born=%u finalized=%u reentries=%u native_calls=%llu recursive_calls=%llu host_sp_delta=%llu\n",
        argv[1], cases, born, finalized, reentries, (unsigned long long)calls,
        (unsigned long long)recursive_calls, (unsigned long long)delta);
    return 0;
}
