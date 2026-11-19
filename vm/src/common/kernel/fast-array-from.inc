/* Direct array literal fast path for OP_array_from. */
extern JSValue JS_NewArrayFrom(JSContext *ctx, int count, const JSValue *values);

__attribute__((visibility("hidden"), noipa)) int JS_FastArrayFrom(JSFrameRegisterState *state)
{
    uint8_t *pc = state->pc;
    uint16_t argc = (uint16_t)pc[1] | ((uint16_t)pc[2] << 8);
    JSValue *tab = state->sp - argc;
    JSFrame *frame = state->frame;
    JSContext *ctx = frame->bytecode->realm;
    JSValue arr = JS_NewArrayFrom(ctx, argc, tab);
    uint8_t *next_pc = pc + 3;
    state->pc = next_pc;
    frame->sf.cur_pc = next_pc;
    if (JS_IsException(arr)) {
        state->sp = tab;
        frame->saved_sp = tab;
        frame->sf.cur_sp = tab;
        state->exception_pending = true;
        return 1;
    }
    tab[0] = arr;
    state->sp = tab + 1;
    frame->saved_sp = tab + 1;
    frame->sf.cur_sp = tab + 1;
    return 0;
}
