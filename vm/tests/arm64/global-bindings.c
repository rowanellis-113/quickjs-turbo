/* Natural BC/activation layers and resolved-cell Symbol branches. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
static JSContext *context;
extern size_t qjs_aarch64_vm_function_code(JSValueConst, const uint8_t **);
static const uint8_t opcode_size[] = {
#define DEF(id, size, n_pop, n_push, format) size,
#define def(id, size, n_pop, n_push, format)
#include "quickjs-opcode.h"
};
static int symbol_pattern(JSValue f, JSAtom atom)
{
    const uint8_t *code = NULL;
    size_t size = qjs_aarch64_vm_function_code(f, &code);
    assert(size && code);
    int found = -1;
    for (size_t pc = 0; pc < size;) {
        unsigned op = code[pc];
        assert(op < sizeof(opcode_size) && opcode_size[op] && pc + opcode_size[op] <= size);
        if (op == ARM_OP_get_var && pc + 11 <= size) {
            uint32_t name;
            memcpy(&name, code + pc + 1, 4);
            if (name == atom && code[pc + 5] == ARM_OP_strict_eq) {
                unsigned branch = code[pc + 6];
                if (branch == ARM_OP_if_true8)
                    found = 0;
                else if (branch == ARM_OP_if_false8)
                    found = 1;
                else if (branch == ARM_OP_if_true)
                    found = 2;
                else if (branch == ARM_OP_if_false)
                    found = 3;
            }
        }
        pc += opcode_size[op];
    }
    return found;
}
static JSValue checked(JSValue v)
{
    if (JS_IsException(v)) {
        JSValue error = JS_GetException(context);
        const char *s = JS_ToCString(context, error);
        fprintf(stderr, "ARM_GLOBAL_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static JSValue eval(const char *text)
{
    return checked(JS_Eval(context, text, strlen(text), "arm-global-paths", JS_EVAL_TYPE_GLOBAL));
}
static void number(JSValue f, int argc, JSValue *argv, int expected)
{
    JSValue v = checked(JS_Call(context, f, JS_UNDEFINED, argc, argv));
    int32_t n = 0;
    if (JS_ToInt32(context, &n, v) || n != expected)
        fprintf(stderr, "ARM_GLOBAL_NUMBER got=%d expected=%d\n", n, expected);
    assert(!JS_ToInt32(context, &n, v) && n == expected);
    JS_FreeValue(context, v);
}
static void counts(uint64_t out[16])
{
    qjs_aarch64_vm_global_counts(out);
}
__attribute__((noipa)) static void global_native_ready(uintptr_t function)
{
    __asm__ volatile("" ::"r"(function) : "memory");
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    context = JS_NewContext(rt);
    assert(context);
    int native = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    int compiled = native && ARM_HAS_GLOBAL_BINDING;
    int cache = compiled && !getenv("QJS_DISABLE_FRAME_GLOBAL_BINDING");
    int cells = compiled && ARM_HAS_PROPERTY_IC && !getenv("QJS_DISABLE_PROPERTY_IC") &&
                !getenv("QJS_DISABLE_FRAME_BINDING_CELL");
    int symbol = cache && cells && !getenv("QJS_DISABLE_SYMBOL_CASE") &&
                 !getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") &&
                 !getenv("QJS_DISABLE_AARCH64_PROPERTY_HINTS");
    JSAtom lexical = 0, own = 0, kept[256];
    unsigned kept_count = 0;
    char name[64], lexname[64], declaration[128];
    for (unsigned i = 0; i < 128; i++) {
        snprintf(lexname, sizeof(lexname), "armGlobalLex%u", i);
        lexical = JS_NewAtom(context, lexname);
        if ((lexical & 1) != (ARM_CONST_JS_ATOM_undefined & 1))
            break;
        kept[kept_count++] = lexical;
        lexical = 0;
    }
    assert(lexical);
    snprintf(declaration, sizeof(declaration), "let %s=23;0", lexname);
    JS_FreeValue(context, eval(declaration));
    // A public atom ID chooses an ordinary global in a different LOWEST
    // bucket bit from the sole lexical name. This holds for every actual
    // constructor-proven nonzero hash mask;no private memory is written.
    for (unsigned i = 0; i < 128; i++) {
        snprintf(name, sizeof(name), "armGlobalOwn%u", i);
        own = JS_NewAtom(context, name);
        if ((own & 1) != (lexical & 1))
            break;
        kept[kept_count++] = own;
        own = 0;
    }
    assert(own);
    JSValue global = JS_GetGlobalObject(context);
    assert(JS_SetProperty(context, global, own, JS_NewInt32(context, 17)) >= 0);
    JSValue object = JS_NewObject(context);
    assert(JS_SetPropertyStr(context, object, "x", JS_NewInt32(context, 1)) >= 0);
    char body[2048];
    snprintf(body, sizeof(body),
             "(function(o,n){let total=0;for(let i=0;i<n;i++)total+=%s+%s+o.x;return total})", name,
             lexname);
    JSValue loop = eval(body), args[] = {object, JS_NewInt32(context, 64)};
    JSValue zero_args[] = {object, JS_NewInt32(context, 0)};
    number(loop, 2, zero_args, 0);
    JSValue driver = eval("(function globalDriver(f,o,n){return f(o,n)+0})");
    JSValue driver_args[] = {loop, object, JS_NewInt32(context, 64)};
    global_native_ready((uintptr_t)JS_VALUE_GET_PTR(loop));
    uint64_t cold_before[16], cold_after[16];
    counts(cold_before);
    number(driver, 3, driver_args, 41 * 64);
    counts(cold_after);
    assert(cold_after[13] - cold_before[13] == (compiled ? 1u : 0u));
    JS_FreeValue(context, driver);
    for (unsigned i = 0; i < 4; i++)
        number(loop, 2, args, 41 * 64);
    uint64_t a[16], b[16], op_a[256], op_b[256];
    counts(a);
    qjs_aarch64_vm_opcode_counts(op_a);
    number(loop, 2, args, 41 * 64);
    counts(b);
    qjs_aarch64_vm_opcode_counts(op_b);
    fprintf(
        stderr,
        "ARM_GLOBAL_LAYERS compiled=%d cache=%d cells=%d cell=%llu own=%llu lex=%llu ownfill=%llu lexfill=%llu base=%llu\n",
        compiled, cache, cells, (unsigned long long)(b[0] - a[0]),
        (unsigned long long)(b[2] - a[2]), (unsigned long long)(b[3] - a[3]),
        (unsigned long long)(b[4] - a[4]), (unsigned long long)(b[5] - a[5]),
        (unsigned long long)(b[11] - a[11]));
    if (cells)
        assert(b[0] - a[0] == 128);
    else if (cache)
        assert(b[2] - a[2] == 63 && b[3] - a[3] == 63 && b[4] - a[4] == 1 && b[5] - a[5] == 1);
    else
        assert(b[2] == a[2] && b[3] == a[3]);
    if (compiled)
        assert(op_b[ARM_OP_get_var] == op_a[ARM_OP_get_var]);
    // Four natural compiler patterns:strict equality followed by short/long
    // true/false branches. Both matching and distinct Symbol owners survive.
    JSValue shared = eval("Symbol('shared')"), different = eval("Symbol('different')");
    assert(JS_SetPropertyStr(context, global, "armGlobalSymbol", JS_DupValue(context, shared)) >=
           0);
    JSAtom symbol_atom = JS_NewAtom(context, "armGlobalSymbol");
    unsigned patterns = 0;
    uint64_t symbol_hits = 0;
    for (unsigned kind = 0; kind < 4; kind++) {
        char source[8192];
        size_t used = (size_t)snprintf(
            source, sizeof(source),
            kind & 1
                ? "(function(s,o,n){let hit=0,i=0;do{hit+=1;"
                : "(function(s,o,n){let hit=0;for(let i=0;i<n;i++){if(s===armGlobalSymbol){hit+=1;");
        if (kind & 2)
            for (unsigned j = 0; j < 100; j++)
                used += (size_t)snprintf(source + used, sizeof(source) - used, "hit+=0;");
        used += (size_t)snprintf(source + used, sizeof(source) - used,
                                 kind & 1 ? "i++;}while(i<n&&s===armGlobalSymbol);return hit+o.x})"
                                          : "}else{hit+=2;}}return hit+o.x})");
        assert(used < sizeof(source));
        JSValue f = eval(source);
        JSValue values[] = {shared, object, JS_NewInt32(context, 32)};
        int pattern = symbol_pattern(f, symbol_atom);
        fprintf(stderr, "ARM_GLOBAL_COMPILER kind=%u pattern=%d\n", kind, pattern);
        const int expected_pattern[] = {1, 0, 3, 2};
        assert(pattern == expected_pattern[kind]);
        patterns |= 1u << pattern;
        number(f, 3, values, 33);
        counts(a);
        number(f, 3, values, 33);
        counts(b);
        fprintf(stderr, "ARM_GLOBAL_SYMBOL kind=%u enabled=%d fused=%llu\n", kind, symbol,
                (unsigned long long)(b[12] - a[12]));
        assert(b[12] - a[12] == (symbol ? (kind & 1 ? 31u : 32u) : 0u));
        symbol_hits += b[12] - a[12];
        values[0] = different;
        counts(a);
        number(f, 3, values, kind & 1 ? 2 : 65);
        counts(b);
        assert(b[12] - a[12] == (symbol ? (kind & 1 ? 1u : 32u) : 0u));
        symbol_hits += b[12] - a[12];
        JS_FreeValue(context, f);
    }
    // A fresh Symbol on the operand stack owns its last reference. It must
    // retain the original duplicate/compare/release and branch poll owners.
    JSValue last = eval(
        "(function(o,n){let hit=0;for(let i=0;i<n;i++){if(Symbol('last')===armGlobalSymbol)hit++;else hit+=2;}return hit+o.x})");
    number(last, 2, args, 129);
    counts(a);
    number(last, 2, args, 129);
    counts(b);
    assert(b[12] == a[12]);
    JS_FreeValue(context, last);
    // Warmed immutable rows still follow live value replacement and GC.
    assert(JS_SetProperty(context, global, own, JS_NewInt32(context, 31)) >= 0);
    snprintf(declaration, sizeof(declaration), "%s=41;0", lexname);
    JS_FreeValue(context, eval(declaration));
    JS_RunGC(rt);
    number(loop, 2, args, 73 * 64);
    JSValue undef =
        eval("(function(n){let value;for(let i=0;i<n;i++)value=undefined;return value})");
    JSValue n = JS_NewInt32(context, 32);
    counts(a);
    JSValue uv = checked(JS_Call(context, undef, JS_UNDEFINED, 1, &n));
    assert(JS_IsUndefined(uv));
    JS_FreeValue(context, uv);
    counts(b);
    if (cache && !getenv("QJS_DISABLE_FRAME_GLOBAL_UNDEFINED"))
        assert(b[7] > a[7]);
    JS_FreeValue(context, undef);
    JS_FreeValue(context, loop);
    JS_FreeValue(context, object);
    JS_FreeValue(context, shared);
    JS_FreeValue(context, different);
    JS_FreeValue(context, global);
    assert(patterns == 15);
    JS_FreeAtom(context, symbol_atom);
    for (unsigned i = 0; i < kept_count; i++)
        JS_FreeAtom(context, kept[i]);
    JS_FreeAtom(context, lexical);
    JS_FreeAtom(context, own);
    JS_FreeContext(context);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
    printf("AARCH64_GLOBAL_BINDINGS_OK compiled=%d cells=%d cache=%d symbols=%llu zero_ledgers\n",
           compiled, cells, cache, (unsigned long long)symbol_hits);
    return 0;
}
