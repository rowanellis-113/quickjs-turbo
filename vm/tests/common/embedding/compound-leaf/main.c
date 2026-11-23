#include "quickjs.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Stable private test markers for compiler-specific native coverage checks. */
#if defined(_MSC_VER)
#define HOST_NOINLINE __declspec(noinline)
#elif defined(__GNUC__)
#define HOST_NOINLINE __attribute__((noinline))
#else
#define HOST_NOINLINE
#endif

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
        fprintf(stderr, "COMPOUND_HOST_FAIL %s\n", message);
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
    JSValue value = JS_GetException(ctx);
    const char *text = JS_ToCString(ctx, value);
    fprintf(stderr, "exception:%s\n", text ? text : "<oom>");
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, value);
}
static JSValue evaluate(JSContext *ctx, const char *text, int flags)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "compound_host.js", flags);
    if (JS_IsException(value)) {
        report_exception(ctx);
        require(0, "eval");
    }
    return value;
}
static void run(JSContext *ctx, const char *text)
{
    JS_FreeValue(ctx, evaluate(ctx, text, JS_EVAL_TYPE_GLOBAL));
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
    /* Public finalizer contract: no allocation, JavaScript or reentry. */
}
static JSValue make_owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    Host *s = host(ctx);
    if (argc != 1 || !JS_IsString(argv[0]))
        return JS_ThrowTypeError(ctx, "owner string");
    JSValue value = JS_NewObjectClass(ctx, s->owner);
    if (JS_IsException(value))
        return value;
    JS_SetOpaque(value, (void *)(uintptr_t)(++s->born));
    if (JS_SetPropertyStr(ctx, value, "left", JS_DupValue(ctx, argv[0])) < 0 ||
        JS_SetPropertyStr(ctx, value, "right", JS_DupValue(ctx, argv[0])) < 0) {
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    return value;
}
static JSValue alive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewInt32(ctx, (int32_t)(host(ctx)->born - host(ctx)->finalized));
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = host(ctx);
    require(s->born - s->finalized == 1, "original receiver alive at fallback getter");
    size_t moves = s->memory.moves;
    run(ctx, "for(let i=0;i<96;i++)tailBuffer.push(i);"
             "if(reenter()!==-1)throw Error('reentrant result');tailBuffer.length=0;");
    JS_RunGC(JS_GetRuntime(ctx));
    require(s->born - s->finalized == 1, "original receiver survives reentry and GC");
    if (s->moving)
        require(s->memory.moves > moves, "real backing buffer relocation");
    ++s->callbacks;
    return JS_UNDEFINED;
}
static JSValue oom_string(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = host(ctx);
    JSRuntime *rt = JS_GetRuntime(ctx);
    char bytes[8192];
    memset(bytes, 'x', sizeof(bytes));
    if (s->moving)
        s->memory.blocked = 1;
    else
        JS_SetMemoryLimit(rt, 1);
    JSValue value = JS_NewStringLen(ctx, bytes, sizeof(bytes));
    s->memory.blocked = 0;
    JS_SetMemoryLimit(rt, SIZE_MAX);
    require(JS_IsException(value), "actual fallback coercion allocation fails");
    ++s->oom;
    return value;
}
static int interrupt(JSContext *ctx, void *opaque)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    Host *s = opaque;
    ++s->interrupts;
    if (s->interrupts == 2)
        JS_RunGC(rt);
    return s->interrupts == 3;
}
static void install(JSContext *ctx, JSValue global, const char *name, JSCFunction *fn, int argc)
{
    require(JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, fn, name, argc)) == 1,
            "install");
}
static HOST_NOINLINE void wire_roundtrip(JSContext *ctx)
{
    JSValue program = evaluate(
        ctx, "globalThis.wireF=function(other){return this.left.localeCompare(other.right);};",
        JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    size_t na = 0, nb = 0;
    uint8_t *a = JS_WriteObject(ctx, &na, program, JS_WRITE_OBJ_BYTECODE);
    require(a != NULL, "serialize unexecuted wrapper");
    JSValue value = JS_EvalFunction(ctx, JS_DupValue(ctx, program));
    if (JS_IsException(value)) {
        report_exception(ctx);
        require(0, "execute compiled wrapper");
    }
    JS_FreeValue(ctx, value);
    run(ctx,
        "{let target={left:'a',f:wireF},arg={right:'b'};for(let i=0;i<64;i++)if(target.f(arg)!==-1)throw Error('wire warm');}");
    uint8_t *b = JS_WriteObject(ctx, &nb, program, JS_WRITE_OBJ_BYTECODE);
    require(b != NULL && na == nb && memcmp(a, b, na) == 0,
            "warm metadata absent from public wire");
    value = JS_ReadObject(ctx, b, nb, JS_READ_OBJ_BYTECODE);
    require(!JS_IsException(value), "deserialize wrapper");
    value = JS_EvalFunction(ctx, value);
    if (JS_IsException(value)) {
        report_exception(ctx);
        require(0, "execute read wrapper");
    }
    JS_FreeValue(ctx, value);
    run(ctx,
        "{let target={left:'z',f:wireF},arg={right:'b'};for(let i=0;i<64;i++)if(target.f(arg)!==1)throw Error('wire restored');}wireF=null;");
    js_free(ctx, a);
    js_free(ctx, b);
    JS_FreeValue(ctx, program);
}
static void foreign_realm(JSContext *ctx, JSValue global)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    JSContext *other = JS_NewContext(rt);
    require(other != NULL, "foreign context");
    JSValue fn = evaluate(other, "(function(other){return this.left.localeCompare(other.right);})",
                          JS_EVAL_TYPE_GLOBAL);
    require(JS_SetPropertyStr(ctx, global, "foreignF", fn) == 1, "foreign function");
    run(ctx,
        "for(let i=0;i<32;i++)if(foreignF.call({left:'a'},{right:'b'})!==-1)throw Error('foreign canonical');");
    run(other, "String.prototype.localeCompare=function(){return 51;};");
    JS_FreeContext(other);
    JS_RunGC(rt);
    run(ctx,
        "for(let i=0;i<32;i++)if(foreignF.call({left:'a'},{right:'b'})!==51)throw Error('foreign live realm');foreignF=null;");
    JS_RunGC(rt);
}
static HOST_NOINLINE void exercise(int moving)
{
    Host s = {0};
    s.moving = moving;
    JSMallocFunctions functions = {moving_calloc, moving_malloc, moving_free, moving_realloc,
                                   moving_size};
    JSRuntime *rt = moving ? JS_NewRuntime2(&functions, &s.memory) : JS_NewRuntime();
    require(rt != NULL, "runtime");
    JS_SetRuntimeOpaque(rt, &s);
    JS_SetGCThreshold(rt, 4096);
    JS_NewClassID(rt, &s.owner);
    JSClassDef cls = {0};
    cls.class_name = "CompoundOwner";
    cls.finalizer = owner_finalizer;
    require(JS_NewClass(rt, s.owner, &cls) == 0, "owner class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    install(ctx, global, "makeOwner", make_owner, 1);
    install(ctx, global, "alive", alive, 0);
    install(ctx, global, "hostProbe", probe, 0);
    install(ctx, global, "oomString", oom_string, 0);
    run(ctx,
        "globalThis.f=function(other){return this.left.localeCompare(other.right);};"
        "globalThis.a={left:'a',f:f};globalThis.b={right:'b'};"
        "globalThis.tailBuffer=[];globalThis.reenter=function(){return a.f(b);};"
        "globalThis.fresh=function(text){let o=makeOwner(text);o.f=f;return o;};"
        "for(let i=0;i<64;i++)if(a.f(b)!==-1)throw Error('warm');"
        "for(let i=0;i<128;i++){"
        "if(fresh('a').f(fresh('b'),fresh('c'))!==-1)throw Error('last owners');"
        "if(alive()!==0)throw Error('temporary owner retained');"
        "let x=fresh('same');if(x.f(x)!==0)throw Error('aliased argument');x=null;"
        "if(alive()!==0)throw Error('aliased owner retained');"
        "}"
        "globalThis.freshPlain=function(text){return {left:text,right:text,f:f,keep:makeOwner(text)};};"
        "globalThis.plainDistinct=function(){return freshPlain('a').f(freshPlain('b'));};"
        "globalThis.plainExtra=function(){return freshPlain('a').f(freshPlain('b'),freshPlain('c'));};"
        "globalThis.aliasHold=null;"
        "globalThis.aliasMake=function(){let x=freshPlain('same');aliasHold=x;return x;};"
        "globalThis.aliasTake=function(){let x=aliasHold;aliasHold=null;return x;};"
        "globalThis.plainAlias=function(){return aliasMake().f(aliasTake());};"
        "for(let i=0;i<32;i++){"
        "if(plainExtra()!==-1)throw Error('plain extra owners');"
        "if(alive()!==0)throw Error('plain extra owner retained');"
        "if(plainDistinct()!==-1)throw Error('plain last owners');"
        "if(alive()!==0)throw Error('plain last owner retained');"
        "if(plainAlias()!==0)throw Error('plain alias owner');"
        "if(alive()!==0)throw Error('plain alias owner retained');"
        "}"
        "for(let i=0;i<16;i++){"
        "if(({left:'a',f:function(other){return this.left.localeCompare(other.right);}}).f(fresh('b'))!==-1)throw Error('temporary function');"
        "if(alive()!==0)throw Error('temporary function operand retained');"
        "if(fresh('a').f({get right(){hostProbe();return 'b';}})!==-1)throw Error('fallback getter');"
        "if(alive()!==0)throw Error('fallback owner retained');"
        "}"
        "let failed=false;try{fresh('a').f(Object.assign(fresh('b'),{right:{toString:oomString}}));}catch(e){failed=true;}"
        "if(!failed||alive()!==0)throw Error('OOM cleanup');"
        "if(a.f(b)!==-1)throw Error('OOM recovery');");
    require(s.callbacks == 16 && s.oom == 1 && s.born == s.finalized,
            "semantic coverage and owner balance");
    wire_roundtrip(ctx);
    foreign_realm(ctx, global);
    JS_SetInterruptHandler(rt, interrupt, &s);
    const char *loop = "(function(){for(;;)fresh('a').f(fresh('b'));})()";
    JSValue value = JS_Eval(ctx, loop, strlen(loop), "compound_interrupt.js", JS_EVAL_TYPE_GLOBAL);
    JS_SetInterruptHandler(rt, NULL, NULL);
    require(JS_IsException(value) && s.interrupts == 3, "third interrupt with GC");
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_RunGC(rt);
    require(s.born == s.finalized, "interrupt operand owners released");
    run(ctx, "if(a.f(b)!==-1||alive()!==0)throw Error('interrupt recovery');");
    JS_SetMaxStackSize(rt, 64 * 1024);
    run(ctx,
        "(function(){let good=0,bad=0;function depth(n){if(n<=0)return a.f(b);return depth(n-1)+0;}"
        "for(const n of[1,8,32,128,512,2048]){try{if(depth(n)!==-1)throw Error('depth result');good++;}"
        "catch(e){if(!String(e).includes('stack'))throw e;bad++;}}"
        "if(good===0||bad===0)throw Error('stack guard coverage');})();");
    JS_SetMaxStackSize(rt, 1024 * 1024);
    run(ctx, "if(a.f(b)!==-1)throw Error('quota recovery');");
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == s.finalized && s.callbacks == 16 && s.oom == 1, "final owner balance");
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
        "COMPOUND_HOST_OK moving=%d born=%u finalized=%u callbacks=%u oom=%u interrupts=%u moves=%zu failed=%zu wire=1 realm=1 quota=1\n",
        moving, s.born, s.finalized, s.callbacks, s.oom, s.interrupts, s.memory.moves,
        s.memory.failed);
}
int main(void)
{
    exercise(0);
    exercise(1);
    return 0;
}
