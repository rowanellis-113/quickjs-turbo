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
        fprintf(stderr, "CHARACTER_HOST_FAIL %s\n", message);
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
    JSValue value = JS_Eval(ctx, text, strlen(text), "character_host.js", flags);
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

static JSValue character_receiver(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSValue value = make_owner(ctx, self, argc, argv);
    if (JS_IsException(value))
        return value;
    const char *code = "(function(s){return s=='a'||s=='b'||s=='c';})";
    JSValue fn = JS_Eval(ctx, code, strlen(code), "character_receiver.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(fn)) {
        JS_FreeValue(ctx, value);
        return fn;
    }
    /* Admit this fresh bytecode through the public C root before its single
     * JS->JS method call. This prepares eligibility, without retaining a new
     * function owner or replacing the native call under observation. */
    JSValue arg = JS_NewString(ctx, "a");
    if (JS_IsException(arg)) {
        JS_FreeValue(ctx, fn);
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    JSValue warm = JS_Call(ctx, fn, JS_UNDEFINED, 1, &arg);
    JS_FreeValue(ctx, arg);
    if (JS_IsException(warm)) {
        JS_FreeValue(ctx, fn);
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    require(JS_IsBool(warm) && JS_ToBool(ctx, warm) == 1, "character method public-root admission");
    JS_FreeValue(ctx, warm);
    if (JS_SetPropertyStr(ctx, value, "m", fn) < 0) {
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    return value;
}
static JSValue character_probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *s = host(ctx);
    require(s->born - s->finalized == 1, "coercion owner alive before reentry");
    size_t moves = s->memory.moves;
    run(ctx,
        "for(let i=0;i<96;i++)characterBuffer.push(i);"
        "if(characterMember('b')!==true)throw Error('character reentry');characterBuffer.length=0;");
    JS_RunGC(JS_GetRuntime(ctx));
    require(s->born - s->finalized == 1, "coercion owner survives reentry and GC");
    if (s->moving)
        require(s->memory.moves > moves, "real fallback backing-buffer relocation");
    ++s->callbacks;
    return JS_UNDEFINED;
}
static void character_admit(JSContext *ctx, JSValueConst fn)
{
    JSValue arg = JS_NewString(ctx, "a");
    require(!JS_IsException(arg), "character admission argument");
    JSValue warm = JS_Call(ctx, fn, JS_UNDEFINED, 1, &arg);
    JS_FreeValue(ctx, arg);
    require(!JS_IsException(warm) && JS_IsBool(warm) && JS_ToBool(ctx, warm) == 1,
            "character public C-root admission");
    JS_FreeValue(ctx, warm);
}
static void character_admit_named(JSContext *ctx, const char *name)
{
    JSValue global = JS_GetGlobalObject(ctx), fn = JS_GetPropertyStr(ctx, global, name);
    require(JS_IsFunction(ctx, fn), "character named admission function");
    character_admit(ctx, fn);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, global);
}
static void character_wire(JSContext *ctx)
{
    JSValue program =
        evaluate(ctx, "globalThis.characterWire=function(s){return s=='a'||s=='b'||s=='c';};",
                 JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    size_t na = 0, nb = 0;
    uint8_t *a = JS_WriteObject(ctx, &na, program, JS_WRITE_OBJ_BYTECODE);
    require(a != NULL, "character serialize before warm");
    JSValue value = JS_EvalFunction(ctx, JS_DupValue(ctx, program));
    require(!JS_IsException(value), "character execute compiled program");
    JS_FreeValue(ctx, value);
    character_admit_named(ctx, "characterWire");
    run(ctx,
        "(function(){for(let i=0;i<64;i++){if(characterWire('a')!==true||characterWire('x')!==false)throw Error('character wire warm');}})();");
    uint8_t *b = JS_WriteObject(ctx, &nb, program, JS_WRITE_OBJ_BYTECODE);
    require(b != NULL && na == nb && memcmp(a, b, na) == 0,
            "character native metadata absent from wire");
    value = JS_ReadObject(ctx, b, nb, JS_READ_OBJ_BYTECODE);
    require(!JS_IsException(value), "character read wire");
    value = JS_EvalFunction(ctx, value);
    require(!JS_IsException(value), "character execute read wire");
    JS_FreeValue(ctx, value);
    character_admit_named(ctx, "characterWire");
    run(ctx,
        "(function(){for(let i=0;i<64;i++)if(characterWire('c')!==true)throw Error('character wire restored');})();characterWire=null;");
    js_free(ctx, a);
    js_free(ctx, b);
    JS_FreeValue(ctx, program);
}
static void character_foreign(JSContext *ctx, JSValue global)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    JSContext *other = JS_NewContext(rt);
    require(other != NULL, "character foreign context");
    JSValue fn =
        evaluate(other, "(function(s){return s=='a'||s=='b'||s=='c';})", JS_EVAL_TYPE_GLOBAL);
    character_admit(other, fn);
    JSValue otherGlobal = JS_GetGlobalObject(other);
    require(JS_SetPropertyStr(other, otherGlobal, "characterTransfer", JS_DupValue(other, fn)) == 1,
            "character other-realm warm function");
    run(other,
        "(function(){for(let i=0;i<32;i++)if(characterTransfer('b')!==true)throw Error('character foreign native warm');})();");
    require(JS_SetPropertyStr(other, otherGlobal, "characterTransfer", JS_UNDEFINED) == 1,
            "character clear other-realm warm function");
    JS_FreeValue(other, otherGlobal);
    require(JS_SetPropertyStr(ctx, global, "characterForeign", fn) == 1,
            "character foreign function");
    run(ctx,
        "(function(){for(let i=0;i<32;i++)if(characterForeign('a')!==true||characterForeign('x')!==false)throw Error('character foreign result');})();");
    JS_FreeContext(other);
    JS_RunGC(rt);
    run(ctx,
        "(function(){if(characterForeign('b')!==true)throw Error('character foreign retained realm');})();characterForeign=null;");
    JS_RunGC(rt);
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
    JS_SetGCThreshold(rt, 4096);
    JS_NewClassID(rt, &s.owner);
    JSClassDef cls = {0};
    cls.class_name = "CharacterOwner";
    cls.finalizer = owner_finalizer;
    require(JS_NewClass(rt, s.owner, &cls) == 0, "character owner class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    install(ctx, global, "makeOwner", make_owner, 1);
    install(ctx, global, "alive", alive, 0);
    install(ctx, global, "makeCharacterReceiver", character_receiver, 1);
    install(ctx, global, "characterProbe", character_probe, 0);
    install(ctx, global, "oomString", oom_string, 0);
    run(ctx,
        "globalThis.characterMember=function(s){return s=='a'||s=='b'||s=='c';};"
        "globalThis.characterBuffer=[];"
        "for(let i=0;i<64;i++)if(characterMember('a')!==true||characterMember('x')!==false)throw Error('character warm');"
        "(function(){"
        "for(let i=0;i<128;i++){"
        "if(characterMember('a',makeOwner('extra'))!==true||alive()!==0)throw Error('character last extra owner');"
        "if(makeCharacterReceiver('receiver').m('b')!==true||alive()!==0)throw Error('character last receiver and function');"
        "}"
        "for(let i=0;i<16;i++){"
        "const makeCoerce=()=>Object.assign(makeOwner('coerce'),{[Symbol.toPrimitive](){characterProbe();return 'a';}});"
        "if(characterMember(makeCoerce())!==true||alive()!==0)throw Error('character fallback coercion');"
        "}"
        "let failed=false;try{characterMember(Object.assign(makeOwner('oom'),{[Symbol.toPrimitive]:oomString}));}catch(e){failed=true;}"
        "if(!failed||alive()!==0)throw Error('character OOM cleanup');"
        "if(characterMember('b')!==true)throw Error('character OOM recovery');})();");
    require(s.callbacks == 16 && s.oom == 1 && s.born == s.finalized,
            "character semantic owner balance");
    character_wire(ctx);
    character_foreign(ctx, global);
    JS_SetInterruptHandler(rt, interrupt, &s);
    const char *loop = "(function(){for(;;)characterMember('a',makeOwner('interrupt'));})()";
    JSValue value = JS_Eval(ctx, loop, strlen(loop), "character_interrupt.js", JS_EVAL_TYPE_GLOBAL);
    JS_SetInterruptHandler(rt, NULL, NULL);
    require(JS_IsException(value) && s.interrupts == 3, "character third interrupt with GC");
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_RunGC(rt);
    require(s.born == s.finalized, "character interrupted owners released");
    run(ctx,
        "if(characterMember('a')!==true||alive()!==0)throw Error('character interrupt recovery');");
    JS_SetMaxStackSize(rt, 64 * 1024);
    run(ctx,
        "(function(){let good=0,bad=0;function depth(n){if(n<=0)return characterMember('a');return depth(n-1)+0;}"
        "for(const n of[1,8,32,128,512,2048]){try{if(!depth(n))throw Error('character depth result');good++;}"
        "catch(e){if(!String(e).includes('stack'))throw e;bad++;}}"
        "if(good===0||bad===0)throw Error('character quota coverage');})();");
    JS_SetMaxStackSize(rt, 1024 * 1024);
    run(ctx, "if(characterMember('c')!==true)throw Error('character quota recovery');");
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == s.finalized && s.callbacks == 16 && s.oom == 1,
            "character final owner balance");
    if (moving) {
        require(s.memory.live == 0 && s.memory.moves > 0 && s.memory.failed > 0,
                "character moving/OOM balance");
        while (s.memory.old) {
            Allocation *next = s.memory.old->h.next;
            free(s.memory.old);
            s.memory.old = next;
        }
    }
    printf(
        "CHARACTER_HOST_OK moving=%d born=%u finalized=%u callbacks=%u oom=%u interrupts=%u moves=%zu failed=%zu wire=1 realm=1 quota=1\n",
        moving, s.born, s.finalized, s.callbacks, s.oom, s.interrupts, s.memory.moves,
        s.memory.failed);
}
int main(void)
{
    exercise(0);
    exercise(1);
    return 0;
}
