/* Typed double native calls at a coherent Interp boundary. MIT. */
#if defined(_MSC_VER)
#define NUMERIC_CODE __declspec(code_seg(".qjsvm$zzznumC")) no_inline
#pragma section(".rdata$zzznum", read)
__declspec(allocate(".rdata$zzznum")) static const char numeric_disable_name[] =
    "QJS_DISABLE_NUMERIC_HOST";
#else
#define NUMERIC_CODE __attribute__((section(".qjsvm$zzznumC"), noipa))
static const char numeric_disable_name[] __attribute__((section(".qjsro$zzznum"))) =
    "QJS_DISABLE_NUMERIC_HOST";
#endif
_Static_assert(JS_CFUNC_f_f == 6 && JS_CFUNC_f_f_f == 7, "numeric native leaf selector signatures");
extern int JS_FrameInterpHostGate(JSFrameRegisterState *, JSValue *, int, bool);
extern const char JS_FrameNumericFastDisable[];
#if defined(_MSC_VER)
#define NUMERIC_FAST_DISABLE_NAME JS_FrameNumericFastDisable
#else
/* A direct RIP-relative reference avoids MinGW's extra .refptr slot in the
 * original readonly tables. The linked symbol still determines the address. */
static inline const char *numeric_fast_disable_name(void)
{
    const char *name;
    __asm__("leaq JS_FrameNumericFastDisable(%%rip), %0" : "=r"(name));
    return name;
}
#define NUMERIC_FAST_DISABLE_NAME numeric_fast_disable_name()
#endif
_Static_assert(offsetof(JSObject, u.cfunc.realm) == QJS_ABI_OFF_JSObject_u_cfunc_realm &&
                   offsetof(JSObject, u.cfunc.c_function) ==
                       QJS_ABI_OFF_JSObject_u_cfunc_c_function &&
                   offsetof(JSObject, u.cfunc.length) == QJS_ABI_OFF_JSObject_u_cfunc_length &&
                   sizeof(JSFrameSharedAnchor) == 24 && offsetof(JSFrameSharedAnchor, state) == 8 &&
                   offsetof(JSFrameSharedAnchor, kind) == 16,
               "numeric trampoline live target and TLS anchor ABI");

NUMERIC_CODE int JS_FrameInterpHostNumeric(JSFrameRegisterState *state, JSValue *argv, int argc,
                                           bool method)
{
    JSRuntime *rt = state->rt;
    JSContext *ctx;
    JSObject *object;
    JSStackFrame host_frame;
    JSFrameSharedAnchor **slot = NULL, anchor;
    JSValueConst *arg_buf;
    JSCFunctionType func;
    double d1, d2;
    unsigned char active = 0, cproto;
    int formal, i;

    /* Only this new bridge consumes these previously unused padding bits. */
    if (unlikely(!(FRAME_SHARED_BITS(rt) & 48)))
        FRAME_SHARED_BITS(rt) |= getenv(numeric_disable_name) ? 32 : 16;
    if (FRAME_SHARED_BITS(rt) & 32)
        return JS_FrameInterpHostGate(state, argv, argc, method);
    if (unlikely(!(FRAME_SHARED_BITS(rt) & 192)))
        FRAME_SHARED_BITS(rt) |= getenv(NUMERIC_FAST_DISABLE_NAME) ? 128 : 64;

    ctx = state->frame->bytecode->realm;
    object = JS_VALUE_GET_OBJ(argv[-1]);
    js_frame_begin_c(state);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state->bridges++;
#endif
    /* Exactly the caller-realm poll that precedes js_call_c_function. */
    if (unlikely(js_poll_interrupts(ctx))) {
        state->result = JS_EXCEPTION;
        goto done;
    }
    formal = object->u.cfunc.length;
    if (unlikely(js_check_stack_overflow(rt, sizeof(JSValue) * formal))) {
        state->result = JS_ThrowStackOverflow(ctx);
        goto done;
    }
    arg_buf = vc(argv);
    if (unlikely(argc < formal)) {
        arg_buf = alloca(sizeof(JSValue) * formal);
        for (i = 0; i < argc; i++)
            arg_buf[i] = argv[i];
        for (; i < formal; i++)
            arg_buf[i] = JS_UNDEFINED;
    }
    host_frame.prev_frame = rt->current_stack_frame;
    host_frame.cur_func = argv[-1];
    host_frame.arg_buf = (JSValue *)arg_buf;
    host_frame.arg_count = argc < formal ? formal : argc;
    host_frame.is_strict_mode = false;
    FRAME_CLEAR_STACK_AUX(&host_frame);
    rt->current_stack_frame = &host_frame;
    ctx = object->u.cfunc.realm;
    cproto = object->u.cfunc.cproto;
    func = object->u.cfunc.c_function;

    /* Coercion is an arbitrary JS/GC boundary too. The native prototype
     * has no context argument, but an embedder can still reenter JS. */
    if (js_frame_shared_enabled(rt)) {
        slot = js_frame_shared_slot();
        anchor.prev = *slot;
        anchor.state = state;
        anchor.kind = 0;
        active = FRAME_SHARED_ACTIVE(rt);
        FRAME_SHARED_BITS(rt) |= 4;
        *slot = &anchor;
    }
    if (JS_ToFloat64(ctx, &d1, arg_buf[0])) {
        state->result = JS_EXCEPTION;
    } else if (cproto == JS_CFUNC_f_f) {
        state->result = js_number(func.f_f(d1));
    } else if (JS_ToFloat64(ctx, &d2, arg_buf[1])) {
        state->result = JS_EXCEPTION;
    } else {
        state->result = js_number(func.f_f_f(d1, d2));
    }
    if (slot) {
        *slot = anchor.prev;
        FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | active;
    }
    rt->current_stack_frame = host_frame.prev_frame;
done:
    state->exception_pending = JS_IsException(state->result);
    js_frame_finish_c(state);
    return state->exception_pending;
}
#undef NUMERIC_CODE
#undef NUMERIC_FAST_DISABLE_NAME
