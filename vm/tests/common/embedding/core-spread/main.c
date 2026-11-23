#include "quickjs.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef union Allocation Allocation;
union Allocation {
    long double align;
    unsigned char padding[32];
    struct {
        size_t size;
        Allocation *next;
    } h;
};
typedef struct Moving {
    size_t live, moves, retired, failed;
    int blocked;
    Allocation *old;
} Moving;
typedef struct Host {
    Moving memory;
    JSClassID owner;
    unsigned born, finalized, callbacks, oom, interrupts;
    int moving, action;
} Host;

static void require(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "CORE_SPREAD_HOST_FAIL %s\n", message);
        exit(40);
    }
}
static void *moving_malloc(void *opaque, size_t n)
{
    Moving *s = opaque;
    if (s->blocked) {
        ++s->failed;
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(Allocation))
        return NULL;
    Allocation *p = malloc(sizeof(*p) + (n ? n : 1));
    if (!p)
        return NULL;
    p->h.size = n ? n : 1;
    p->h.next = NULL;
    ++s->live;
    return p + 1;
}
static void moving_free(void *opaque, void *ptr)
{
    if (!ptr)
        return;
    Moving *s = opaque;
    require(s->live > 0, "allocator live underflow");
    --s->live;
    free((Allocation *)ptr - 1);
}
static void *moving_calloc(void *opaque, size_t count, size_t n)
{
    if (count && n > SIZE_MAX / count)
        return NULL;
    void *p = moving_malloc(opaque, count * n);
    if (p)
        memset(p, 0, count * n);
    return p;
}
static size_t moving_size(const void *ptr)
{
    return ptr ? ((const Allocation *)ptr - 1)->h.size : 0;
}
static void *moving_realloc(void *opaque, void *ptr, size_t n)
{
    Moving *s = opaque;
    if (!ptr)
        return moving_malloc(opaque, n);
    if (!n) {
        moving_free(opaque, ptr);
        return NULL;
    }
    Allocation *old = (Allocation *)ptr - 1;
    size_t size = old->h.size;
    void *p = moving_malloc(opaque, n);
    if (!p)
        return NULL;
    memcpy(p, ptr, n < size ? n : size);
    /* Poison and quarantine retired storage until after runtime destruction. */
    memset(ptr, 0, size);
    old->h.next = s->old;
    s->old = old;
    --s->live;
    ++s->moves;
    ++s->retired;
    return p;
}
static void report_exception(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    const char *message = JS_ToCString(ctx, e);
    fprintf(stderr, "exception:%s\n", message ? message : "<oom>");
    JS_FreeCString(ctx, message);
    JS_FreeValue(ctx, e);
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "core_spread_host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        report_exception(ctx);
        require(0, "eval");
    }
    return value;
}
static void run(JSContext *ctx, const char *text)
{
    JS_FreeValue(ctx, evaluate(ctx, text));
}
static Host *host(JSContext *ctx)
{
    return JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
}
static void owner_finalizer(JSRuntime *rt, JSValue value)
{
    Host *s = JS_GetRuntimeOpaque(rt);
    if (JS_GetOpaque(value, s->owner))
        ++s->finalized;
    /* No JS, allocation, or reentry from a finalizer. */
}
static JSValue make_owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = host(ctx);
    JSValue value = JS_NewObjectClass(ctx, s->owner);
    if (JS_IsException(value))
        return value;
    JS_SetOpaque(value, (void *)(uintptr_t)(++s->born));
    return value;
}
static JSValue alive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = host(ctx);
    return JS_NewInt32(ctx, (int32_t)(s->born - s->finalized));
}
static JSValue is_owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    return JS_NewBool(ctx, argc == 1 && JS_GetOpaque(argv[0], host(ctx)->owner) != NULL);
}
static JSValue target(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    Host *s = host(ctx);
    require(argc == 3, "all actual arguments reached C callback");
    for (int i = 0; i < argc; ++i)
        require(JS_GetOpaque(argv[i], s->owner) != NULL, "live callback argument");
    size_t moves = s->memory.moves;
    run(ctx, "for(let i=0;i<96;i++)tail.push(i);tail=null;prefix=null;"
             "if(restCall((a,b,c)=>a+b+c,1,2,3)!==6)throw Error('nested spread');");
    if (s->moving)
        require(s->memory.moves > moves, "actual source buffer relocation");
    JS_RunGC(JS_GetRuntime(ctx));
    for (int i = 0; i < argc; ++i)
        require(JS_GetOpaque(argv[i], s->owner) != NULL,
                "argument survives source release/reentry/GC");
    ++s->callbacks;
    if (s->action == 1) {
        char bytes[8192];
        memset(bytes, 'x', sizeof(bytes));
        if (s->moving)
            s->memory.blocked = 1;
        else
            JS_SetMemoryLimit(JS_GetRuntime(ctx), 1);
        JSValue value = JS_NewStringLen(ctx, bytes, sizeof(bytes));
        s->memory.blocked = 0;
        JS_SetMemoryLimit(JS_GetRuntime(ctx), SIZE_MAX);
        require(JS_IsException(value), "actual callback OOM");
        ++s->oom;
        return value;
    }
    return JS_DupValue(ctx, argv[2]);
}
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    Host *s = opaque;
    ++s->interrupts;
    return 1;
}
static void install(JSContext *ctx, JSValue global, const char *name, JSCFunction *fn, int argc)
{
    require(JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, fn, name, argc)) == 1,
            "host function install");
}
static void exercise(int moving)
{
    Host s = {0};
    s.moving = moving;
    JSMallocFunctions functions = {moving_calloc, moving_malloc, moving_free, moving_realloc,
                                   moving_size};
    JSRuntime *rt = moving ? JS_NewRuntime2(&functions, &s.memory) : JS_NewRuntime();
    require(rt != NULL, "runtime");
    JS_SetRuntimeOpaque(rt, &s);
    JS_NewClassID(rt, &s.owner);
    JSClassDef cls = {0};
    cls.class_name = "CoreSpreadOwner";
    cls.finalizer = owner_finalizer;
    require(JS_NewClass(rt, s.owner, &cls) == 0, "owner class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    install(ctx, global, "makeOwner", make_owner, 0);
    install(ctx, global, "alive", alive, 0);
    install(ctx, global, "isOwner", is_owner, 1);
    install(ctx, global, "hostTarget", target, 3);
    run(ctx,
        "globalThis.prefix=null;globalThis.tail=null;"
        "function restCall(f,a,...tail){return f(a,...tail);}"
        "function sharedCall(f,a,tail,...forceC){return f(a,...tail);}"
        "function methodCall(o,a,...tail){return o.f(a,...tail);}"
        "function testAliases(kind){for(let i=0;i<32;i++){"
        "prefix=makeOwner();tail=[makeOwner(),makeOwner()];"
        "let result=kind===0?sharedCall(hostTarget,prefix,tail):"
        "kind===1?restCall(hostTarget,prefix,...tail):methodCall({f:hostTarget},prefix,...tail);"
        "if(!isOwner(result)||tail!==null||prefix!==null)throw Error('alias result');"
        "if(alive()!==1)throw Error('temporary owners retained');result=null;"
        "if(alive()!==0)throw Error('returned owner retained');"
        "}}"
        "testAliases(0);testAliases(1);testAliases(2);");
    s.action = 1;
    run(ctx, "prefix=makeOwner();tail=[makeOwner(),makeOwner()];let caught=false;"
             "try{sharedCall(hostTarget,prefix,tail);}catch(e){caught=true;}"
             "if(!caught||alive()!==0)throw Error('OOM cleanup');");
    s.action = 0;
    run(ctx, "testAliases(0);");

    JSContext *other = JS_NewContext(rt);
    require(other != NULL, "foreign realm");
    JSValue iterator =
        evaluate(other, "[][Symbol.iterator]().next;Array.prototype[Symbol.iterator];");
    require(JS_SetPropertyStr(ctx, global, "foreignIterator", iterator) == 1,
            "foreign iterator install");
    JS_FreeContext(other);
    run(ctx,
        "const localIteratorProto=Object.getPrototypeOf([][Symbol.iterator]());"
        "const localNext=localIteratorProto.next;"
        "Object.defineProperty(localIteratorProto,'next',{configurable:true,get(){throw Error('wrong realm next');}});"
        "try{for(let i=0;i<8;i++){let array=[2,3];array[Symbol.iterator]=foreignIterator;"
        "if(sharedCall((a,b,c)=>a+b+c,1,array)!==6)throw Error('foreign realm spread');}}"
        "finally{Object.defineProperty(localIteratorProto,'next',{value:localNext,writable:true,configurable:true});}"
        "foreignIterator=null;");
    JS_RunGC(rt);

    JS_SetInterruptHandler(rt, interrupt, &s);
    const char *loop = "sharedCall(function(){while(true){}},1,[2,3]);";
    JSValue interrupted =
        JS_Eval(ctx, loop, strlen(loop), "core_spread_interrupt.js", JS_EVAL_TYPE_GLOBAL);
    JS_SetInterruptHandler(rt, NULL, NULL);
    require(JS_IsException(interrupted) && s.interrupts > 0, "interrupt propagation");
    JS_FreeValue(ctx, JS_GetException(ctx));
    run(ctx, "if(sharedCall((a,b,c)=>a+b+c,1,[2,3])!==6)throw Error('interrupt recovery');");
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == s.finalized && s.born == 387, "host owner balance");
    require(s.callbacks == 129 && s.oom == 1, "callback coverage");
    if (moving) {
        require(s.memory.live == 0 && s.memory.moves > 0 && s.memory.failed > 0,
                "moving allocator/OOM balance");
        while (s.memory.old) {
            Allocation *next = s.memory.old->h.next;
            free(s.memory.old);
            s.memory.old = next;
        }
    }
    printf(
        "CORE_SPREAD_HOST_OK moving=%d born=%u finalized=%u callbacks=%u oom=%u interrupts=%u moves=%zu failed=%zu\n",
        moving, s.born, s.finalized, s.callbacks, s.oom, s.interrupts, s.memory.moves,
        s.memory.failed);
}
int main(void)
{
    exercise(0);
    exercise(1);
    return 0;
}
