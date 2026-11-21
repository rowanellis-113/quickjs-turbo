/* Public producers/reader,realm,GC and fresh-child OOM qualification. MIT. */
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <limits.h>
#endif
#ifdef NDEBUG
#error Property fixture needs active assertions.
#endif
#include "../native_oom_allocator.h"

static unsigned gc_calls;
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    ++gc_calls;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue eval(JSContext *ctx, const char *source)
{
    return JS_Eval(ctx, source, strlen(source), "property-public", JS_EVAL_TYPE_GLOBAL);
}
static void expect(JSContext *ctx, JSValue value, int expected)
{
    int32_t actual = 0;
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "unexpected:%s\n", text ? text : "<oom>");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, error);
        abort();
    }
    assert(!JS_ToInt32(ctx, &actual, value) && actual == expected);
    JS_FreeValue(ctx, value);
}
static void install(JSContext *ctx)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "gcPort", JS_NewCFunction(ctx, collect, "gcPort", 0)) >=
           0);
    JS_FreeValue(ctx, global);
}
static const char program[] =
    "(function(){var p={value:17,method:function(n){gcPort();return this.value+n}};"
    "var o=Object.create(p);o.self=o;var sum=0;for(var i=0;i<32;++i)sum+=o.method(i);"
    "gcPort();return sum;})()";

static size_t trial(unsigned reader, size_t fault)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx);
    JSValue compiled = JS_UNDEFINED;
    uint8_t *wire = NULL;
    size_t length = 0;
    if (reader) {
        compiled =
            JS_Eval(ctx, program, strlen(program), "property-wire", JS_EVAL_FLAG_COMPILE_ONLY);
        assert(!JS_IsException(compiled));
        wire = JS_WriteObject(ctx, &length, compiled, JS_WRITE_OBJ_BYTECODE);
        assert(wire && length);
        JS_FreeValue(ctx, compiled);
        compiled = JS_UNDEFINED;
        JS_RunGC(rt);
    }
    size_t start = memory.sequence;
    memory.fail_at = fault ? start + fault : 0;
    compiled = reader ? JS_ReadObject(ctx, wire, length, JS_READ_OBJ_BYTECODE)
                      : JS_Eval(ctx, program, strlen(program), "property-compile",
                                JS_EVAL_FLAG_COMPILE_ONLY);
    size_t allocations = memory.sequence - start;
    memory.fail_at = 0;
    /* Qualify the producer,then execute its result without injecting an
     * unrelated first-use builtin allocation failure. */
    JSValue result = JS_IsException(compiled) ? compiled : JS_EvalFunction(ctx, compiled);
    if (JS_IsException(result)) {
        result = JS_GetException(ctx);
        assert(!JS_IsUndefined(result));
        JS_FreeValue(ctx, result);
    } else
        expect(ctx, result, 1040);
    assert(!fault || memory.rejected || fault > allocations);
    JS_RunGC(rt);
    /* Recovery through the same producer after an optional permanent OFF. */
    compiled = reader ? JS_ReadObject(ctx, wire, length, JS_READ_OBJ_BYTECODE)
                      : JS_Eval(ctx, program, strlen(program), "property-recover",
                                JS_EVAL_FLAG_COMPILE_ONLY);
    assert(!JS_IsException(compiled));
    expect(ctx, JS_EvalFunction(ctx, compiled), 1040);
    if (wire)
        js_free(ctx, wire);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    return allocations;
}

static void realms(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    assert(a && b);
    install(a);
    install(b);
    expect(a, eval(a, "Number.prototype.portMethod=function(){gcPort();return 17};0"), 0);
    expect(b, eval(b, "Number.prototype.portMethod=function(){gcPort();return 29};0"), 0);
    expect(a, eval(a, "String.prototype.portMethod=function(){gcPort();return 17};0"), 0);
    expect(b, eval(b, "String.prototype.portMethod=function(){gcPort();return 29};0"), 0);
    JSValue fa = eval(a, "(function(){return (3).portMethod()})");
    JSValue fb = eval(b, "(function(){return (3).portMethod()})");
    JSValue sa = eval(a, "(function(){return 'abc'.portMethod()})");
    JSValue sb = eval(b, "(function(){return 'abc'.portMethod()})");
    assert(!JS_IsException(fa) && !JS_IsException(fb));
    assert(!JS_IsException(sa) && !JS_IsException(sb));
    for (unsigned i = 0; i < 64; ++i) {
        expect(b, JS_Call(b, fa, JS_UNDEFINED, 0, NULL), 17);
        expect(a, JS_Call(a, fb, JS_UNDEFINED, 0, NULL), 29);
        expect(b, JS_Call(b, sa, JS_UNDEFINED, 0, NULL), 17);
        expect(a, JS_Call(a, sb, JS_UNDEFINED, 0, NULL), 29);
    }
    JS_FreeValue(a, fa);
    JS_FreeValue(b, fb);
    JS_FreeValue(a, sa);
    JS_FreeValue(b, sb);
    JS_FreeContext(a);
    JS_FreeContext(b);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
}
int main(int argc, char **argv)
{
    if (argc == 4 && !strcmp(argv[1], "single")) {
        unsigned reader = (unsigned)strtoul(argv[2], NULL, 10);
        size_t fault = (size_t)strtoull(argv[3], NULL, 10);
        assert(reader < 2);
        size_t count = trial(reader, fault);
        printf("LINUX_PROPERTY_FAULT_OK reader=%u fault=%zu allocations=%zu\n", reader, fault,
               count);
    } else if (argc > 1 && (!strcmp(argv[1], "oom") || !strcmp(argv[1], "reader-oom"))) {
        size_t counts[2] = {trial(0, 0), trial(1, 0)};
        unsigned children = 0;
        unsigned first = !strcmp(argv[1], "reader-oom") ? 1 : 0;
        for (unsigned reader = first; reader < 2; ++reader)
            for (size_t fault = 1; fault <= counts[reader] + 2; ++fault) {
                fflush(NULL);
                pid_t pid = fork();
                assert(pid >= 0);
                if (!pid) {
                    char phase_text[16], fault_text[32];
                    snprintf(phase_text, sizeof(phase_text), "%u", reader);
                    snprintf(fault_text, sizeof(fault_text), "%zu", fault);
                /* A fresh process also resets the monotonic hint policy.
                 * Retained pre-exec fork failures reproduce on stock/prior. */
#ifdef __APPLE__
                    char self_path[PATH_MAX];
                    uint32_t self_size = sizeof(self_path);
                    const char *exe_path =
                        _NSGetExecutablePath(self_path, &self_size) == 0 ? self_path : argv[0];
                    execl(exe_path, argv[0], "single", phase_text, fault_text, (char *)NULL);
#else
                    execl("/proc/self/exe", argv[0], "single", phase_text, fault_text,
                          (char *)NULL);
#endif
                    perror("property-fault-exec");
                    _Exit(127);
                }
                int status;
                assert(waitpid(pid, &status, 0) == pid);
                if (!WIFEXITED(status) || WEXITSTATUS(status)) {
                    fprintf(stderr, "PROPERTY_OOM_CHILD reader=%u fault=%zu status=%d\n", reader,
                            fault, status);
                    abort();
                }
                ++children;
            }
        printf("LINUX_PROPERTY_%sOOM_OK compile=%zu reader=%zu children=%u\n",
               first ? "READER_" : "", counts[0], counts[1], children);
    } else {
        trial(0, 0);
        trial(1, 0);
        realms();
        assert(gc_calls >= 128);
        printf("LINUX_PROPERTY_API_OK gc=%u\n", gc_calls);
    }
    return 0;
}
