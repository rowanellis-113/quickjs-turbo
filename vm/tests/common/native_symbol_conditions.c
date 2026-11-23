#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    unsigned polls, limit;
} State;
static int interrupt(JSContext *ctx, void *opaque)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    State *s = opaque;
    ++s->polls;
    if (s->polls == 2)
        JS_RunGC(rt);
    return s->limit && s->polls == s->limit;
}
static void string_hex(JSContext *ctx, JSValueConst value)
{
    const char *text = JS_ToCString(ctx, value);
    if (!text) {
        fputs("CONVERSION_FAILED", stdout);
        exit(3);
    }
    for (const unsigned char *p = (const unsigned char *)text; *p; p++)
        printf("%02x", *p);
    JS_FreeCString(ctx, text);
}
enum { SYMBOL_PROGRAMS = 4, SYMBOL_PROGRAM_CAP = 16384 };
static void append_program(char *program, size_t *length, const char *part)
{
    size_t n = strlen(part);
    if (n >= SYMBOL_PROGRAM_CAP - *length)
        exit(8);
    memcpy(program + *length, part, n + 1);
    *length += n;
}
static void make_program(unsigned test, char program[SYMBOL_PROGRAM_CAP])
{
    size_t length = 0;
    program[0] = 0;
    append_program(
        program, &length,
        "globalThis.progress=-1;globalThis.total=0;globalThis.SA=Symbol('a');globalThis.SB=Symbol('b');globalThis.SC=Symbol('c');\nfunction compareBody(seed){let acc=0;for(let i=0;i<30000;i++){progress=i;let hint={x:i};let force=hint.x;let v=(i&3)===0?SA:(i&3)===1?SB:(i&3)===2?SC:Symbol.for('none');\n");
    if (test & 1)
        append_program(program, &length,
                       "if((i&7)===0)v=String(i);else if((i&7)===1)v=BigInt(i);\n");
    append_program(program, &length, "switch(v){case SA:acc+=3;");
    if (test & 2)
        for (unsigned n = 0; n < 100; n++)
            append_program(program, &length, "acc+=(i&1);");
    append_program(
        program, &length,
        "break;case SB:acc+=7;break;case SC:acc+=11;break;default:acc-=1;}\ntotal=acc;}return acc;}\ncompareBody(117);\n");
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--dump-programs")) {
        for (unsigned test = 0; test < SYMBOL_PROGRAMS; test++) {
            char program[SYMBOL_PROGRAM_CAP];
            make_program(test, program);
            for (const unsigned char *p = (const unsigned char *)program; *p; p++)
                printf("%02x", *p);
            puts("");
        }
        return 0;
    }
    const unsigned limits[] = {0, 1, 2, 5};
    for (unsigned test = 0; test < SYMBOL_PROGRAMS; test++) {
        char program[SYMBOL_PROGRAM_CAP];
        make_program(test, program);
        for (unsigned k = 0; k < sizeof(limits) / sizeof(limits[0]); k++) {
            JSRuntime *rt = JS_NewRuntime();
            if (!rt)
                return 4;
            JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
            JSContext *ctx = JS_NewContext(rt);
            if (!ctx)
                return 5;
            State state = {0, limits[k]};
            JS_SetInterruptHandler(rt, interrupt, &state);
            JSValue value = JS_Eval(ctx, program, strlen(program), "symbol-conditions-interrupt.js",
                                    JS_EVAL_TYPE_GLOBAL);
            JS_SetInterruptHandler(rt, NULL, NULL);
            int failed = JS_IsException(value);
            printf("CASE %u LIMIT %u POLLS %u EXCEPTION %d RESULT ", test, state.limit, state.polls,
                   failed);
            if (failed) {
                JSValue error = JS_GetException(ctx);
                string_hex(ctx, error);
                JSValue stack = JS_GetPropertyStr(ctx, error, "stack");
                fputs(" STACK ", stdout);
                string_hex(ctx, stack);
                JS_FreeValue(ctx, stack);
                JS_FreeValue(ctx, error);
            } else
                string_hex(ctx, value);
            JS_FreeValue(ctx, value);
            JSValue global = JS_GetGlobalObject(ctx);
            for (unsigned n = 0; n < 2; n++) {
                JSValue field = JS_GetPropertyStr(ctx, global, n ? "total" : "progress");
                fputs(n ? " TOTAL " : " PROGRESS ", stdout);
                string_hex(ctx, field);
                JS_FreeValue(ctx, field);
            }
            JS_FreeValue(ctx, global);
            JS_RunGC(rt);
            JSMemoryUsage memory;
            JS_ComputeMemoryUsage(rt, &memory);
            printf(" MEMORY %lld %lld\n", (long long)memory.memory_used_count,
                   (long long)memory.memory_used_size);
            if (state.limit && state.polls >= state.limit && !failed)
                return 6;
            if (!state.limit && failed)
                return 7;
            JS_FreeContext(ctx);
            JS_FreeRuntime(rt);
        }
    }
    puts("SYMBOL_CONDITIONS_INTERRUPT_OK");
    return 0;
}
