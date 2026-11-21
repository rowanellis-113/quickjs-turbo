/* Verify physical literal capacities and keep ordinary shape transitions isolated. MIT. */
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error Literal reserve fixture requires active assertions.
#endif
#include "native_oom_allocator.h"

#define PREFIX "(function(probe) { let obj; for (let i = 0; i < 6; ++i) obj = {"
#define SUFFIX "}; probe(); return obj; })"

static const struct Fixture {
    const char *source;
    int fields, reserved, generic, first;
} fixtures[] = {
    {PREFIX "a:i,b:i,c:i" SUFFIX, 3, 4, 3, 5},
    {PREFIX "a:i,b:i,c:i,d:i,e:i" SUFFIX, 5, 8, 6, 5},
    {PREFIX "a:i,b:i,c:i,d:i,e:i,f:i,g:i,h:i,i:i" SUFFIX, 9, 16, 9, 5},
    {PREFIX "a:i+10,b:i,c:i,d:i,e:i" SUFFIX, 5, 6, 6, 15},
    {PREFIX "a:\"\",b:i,c:i" SUFFIX, 3, 4, 3, -1},
};

static JSValue probe_ordinary(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSRuntime *rt = JS_GetRuntime(ctx);
    JSMemoryUsage before, after;
    /* The reserved seed and its transitions are still held by the live VM scope. */
    JS_RunGC(rt);
    JS_ComputeMemoryUsage(rt, &before);
    JSValue object = JS_NewObject(ctx);
    if (JS_IsException(object))
        return object;
    JS_ComputeMemoryUsage(rt, &after);
    assert(after.prop_count == before.prop_count);
    assert(after.prop_size - before.prop_size == 2 * (int64_t)sizeof(JSValue));
    int ret = JS_DefinePropertyValueStr(ctx, object, "a", JS_NewInt32(ctx, 1),
                                        JS_PROP_C_W_E | JS_PROP_THROW);
    if (ret >= 0)
        ret = JS_DefinePropertyValueStr(ctx, object, "b", JS_NewInt32(ctx, 2),
                                        JS_PROP_C_W_E | JS_PROP_THROW);
    if (ret >= 0) {
        JS_ComputeMemoryUsage(rt, &after);
        assert(after.prop_count - before.prop_count == 2);
        assert(after.prop_size - before.prop_size == 2 * (int64_t)sizeof(JSValue));
    }
    JS_FreeValue(ctx, object);
    return ret < 0 ? JS_EXCEPTION : JS_UNDEFINED;
}

static void validate(JSContext *ctx, JSValueConst object, const struct Fixture *test)
{
    assert(JS_IsObject(object));
    for (int i = 0; i < test->fields; ++i) {
        char name[] = {(char)('a' + i), '\0'};
        JSValue field = JS_GetPropertyStr(ctx, object, name);
        if (i == 0 && test->first < 0) {
            const char *s = JS_ToCString(ctx, field);
            assert(s && s[0] == '\0');
            JS_FreeCString(ctx, s);
        } else {
            int32_t n;
            assert(JS_ToInt32(ctx, &n, field) == 0 && n == (i == 0 ? test->first : 5));
        }
        JS_FreeValue(ctx, field);
    }
}

static void check_capacity(JSRuntime *rt, const JSMemoryUsage *before, const struct Fixture *test,
                           bool reserve)
{
    JSMemoryUsage after;
    JS_ComputeMemoryUsage(rt, &after);
    int expected = reserve ? test->reserved : test->generic;
    assert(after.obj_count - before->obj_count == 1);
    assert(after.prop_count - before->prop_count == test->fields);
    if (after.prop_size - before->prop_size != expected * (int64_t)sizeof(JSValue)) {
        fprintf(stderr, "literal with %d fields: expected %d slots, found %lld\n", test->fields,
                expected,
                (long long)((after.prop_size - before->prop_size) / (int64_t)sizeof(JSValue)));
        abort();
    }
}

static void check_multi_site(bool reserve)
{
    static const char source[] = "(function(probe) {"
                                 " let a, b;"
                                 " for (let i = 0; i < 6; ++i) {"
                                 "  a = {x:i,y:i,z:i};"
                                 "  b = {x:i,y:i,z:i};"
                                 " }"
                                 " probe();"
                                 " return [a, b];"
                                 "})";
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue fn = JS_Eval(ctx, source, strlen(source), "literal-reserve-multi", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    JSValue probe = JS_NewCFunction(ctx, probe_ordinary, "probe", 0);
    assert(!JS_IsException(probe));
    JSMemoryUsage before, after;
    JS_ComputeMemoryUsage(rt, &before);
    JSValue pair = JS_Call(ctx, fn, JS_UNDEFINED, 1, &probe);
    assert(!JS_IsException(pair));
    JS_ComputeMemoryUsage(rt, &after);
    int expected_each = reserve ? 4 : 3;
    /* Array(2) uses 1 slot (length) + 2 objects with expected_each slots each. */
    assert(after.obj_count - before.obj_count == 3);
    assert(after.prop_size - before.prop_size ==
           (1 + 2 * expected_each) * (int64_t)sizeof(JSValue));
    JS_FreeValue(ctx, pair);
    JS_FreeValue(ctx, probe);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
}

static unsigned failures, rejected;

static size_t trial(const struct Fixture *test, bool reserve, size_t fault)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue fn =
        JS_Eval(ctx, test->source, strlen(test->source), "literal-reserve", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    JSValue probe = JS_NewCFunction(ctx, probe_ordinary, "probe", 0);
    assert(!JS_IsException(probe));
    JSMemoryUsage before;
    JS_ComputeMemoryUsage(rt, &before);
    size_t start = memory.sequence;
    memory.fail_at = fault ? start + fault : 0;
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 1, &probe);
    memory.fail_at = 0;
    size_t allocations = memory.sequence - start;
    rejected += memory.rejected;
    if (JS_IsException(value)) {
        assert(fault);
        failures++;
        value = JS_GetException(ctx);
        assert(!JS_IsUndefined(value));
    } else {
        if (!fault)
            check_capacity(rt, &before, test, reserve);
        validate(ctx, value, test);
    }
    JS_FreeValue(ctx, value);
    if (fault) {
        JS_ComputeMemoryUsage(rt, &before);
        value = JS_Call(ctx, fn, JS_UNDEFINED, 1, &probe);
        assert(!JS_IsException(value));
        check_capacity(rt, &before, test, reserve);
        validate(ctx, value, test);
        JS_FreeValue(ctx, value);
    }
    JS_FreeValue(ctx, probe);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
    return allocations;
}

int main(int argc, char **argv)
{
    assert(argc == 1 || (argc == 2 && !strcmp(argv[1], "off")));
    bool reserve = argc == 1;
    for (size_t i = 0; i < sizeof(fixtures) / sizeof(fixtures[0]); ++i)
        trial(&fixtures[i], reserve, 0);
    check_multi_site(reserve);
    size_t allocations = trial(&fixtures[2], reserve, 0);
    for (size_t fault = 1; fault <= allocations; ++fault)
        trial(&fixtures[2], reserve, fault);
    assert(rejected && failures);
    printf("LITERAL_RESERVE_OK reserve=%d allocations=%zu failures=%u rejected=%u\n", reserve,
           allocations, failures, rejected);
    return 0;
}
