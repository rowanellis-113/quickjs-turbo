/* Dedicated compiler-owned AAPCS64 C invocation,not the legacy bridge.
 * The inherited generic/numeric/builtin owners supply actual private types,
 * algorithms and controls. C owns aggregate/FP ABI,stack layout and full CFI.
 * All rejected profiles retain their original complete typed bridge. MIT. */
#define ARM_C_ENTRY __attribute__((visibility("hidden"), section(".text.qjs_arm_c_entry"), noipa))
typedef struct JSAArch64CInvokeScope {
    JSLinuxCInvokeFrame frame;
    JSFrameSharedAnchor anchor;
    JSFrameSharedAnchor **slot;
} JSAArch64CInvokeScope;
__attribute__((visibility("hidden"), used))
const uintptr_t qjs_aarch64_c_entry_geometry[] = {sizeof(JSLinuxCInvokeFrame),
                                                  _Alignof(JSLinuxCInvokeFrame),
                                                  sizeof(JSAArch64CInvokeScope),
                                                  _Alignof(JSAArch64CInvokeScope),
                                                  offsetof(JSAArch64CInvokeScope, anchor),
                                                  offsetof(JSAArch64CInvokeScope, slot),
                                                  sizeof(JSLinuxBuiltinView),
                                                  _Alignof(JSLinuxBuiltinView),
                                                  offsetof(JSLinuxBuiltinView, anchor),
                                                  offsetof(JSLinuxBuiltinView, slot),
                                                  offsetof(JSLinuxBuiltinView, active),
                                                  offsetof(JSLinuxBuiltinView, transient_segment),
                                                  sizeof(JSFrameRegisterState),
                                                  sizeof(JSFrame)};

static inline void js_arm_c_publish(JSFrameRegisterState *state, JSAArch64CInvokeScope *scope,
                                    JSValue *argv, int argc, int visible)
{
    JSRuntime *rt = state->rt;
    memset(scope, 0, sizeof(*scope));
    scope->frame.sf.prev_frame = rt->current_stack_frame;
    scope->frame.sf.cur_func = argv[-1];
    scope->frame.sf.arg_buf = argv;
    scope->frame.sf.arg_count = visible;
    scope->frame.argc = argc;
    scope->frame.active = FRAME_SHARED_ACTIVE(rt);
    scope->slot = js_frame_shared_slot();
    scope->anchor.prev = *scope->slot;
    scope->anchor.state = state;
    scope->anchor.kind = 0;
    rt->current_stack_frame = &scope->frame.sf;
    FRAME_SHARED_BITS(rt) |= 4;
    *scope->slot = &scope->anchor;
}
static inline JSValue js_arm_c_restore(JSFrameRegisterState *state, JSAArch64CInvokeScope *scope,
                                       JSValue result)
{
    JSRuntime *rt = state->rt;
    state->exception_pending = JS_IsException(result);
    if (state->exception_pending)
        state->result = result;
    *scope->slot = scope->anchor.prev;
    FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | scope->frame.active;
    rt->current_stack_frame = scope->frame.sf.prev_frame;
    js_frame_finish_c(state);
    return result;
}
static inline void js_arm_c_observe(unsigned kind, unsigned proto)
{
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_c_entry(kind);
    qjs_aarch64_vm_direct_host(proto == JS_CFUNC_generic         ? 0
                               : proto == JS_CFUNC_generic_magic ? 1
                                                                 : 2);
#else
    (void)kind;
    (void)proto;
#endif
}
/* Same checked native leaf as the SysV owner. All misses enter the complete
 * source-owned dense-pop C function,including its original core fallback. */
static inline bool js_arm_dense_pop(JSObject *function, JSValue receiver, int argc, bool method,
                                    JSValue *out)
{
    JSObject *p;
    JSShapeProperty *length;
    uint32_t n;
    if (argc || !method || function->u.cfunc.cproto != JS_CFUNC_generic_magic ||
        function->u.cfunc.length || function->u.cfunc.magic ||
        function->u.cfunc.c_function.generic_magic != JS_FrameDenseArrayPop ||
        atomic_load_explicit(&JS_LinuxDensePopControl, memory_order_relaxed) != 1 ||
        atomic_load_explicit(&JS_LinuxDensePopLeafControl, memory_order_relaxed) != 1 ||
        JS_VALUE_GET_TAG(receiver) != JS_TAG_OBJECT)
        return false;
    p = JS_VALUE_GET_OBJ(receiver);
    if (p->class_id != JS_CLASS_ARRAY || !p->fast_array || !p->extensible)
        return false;
    length = &get_shape_prop(p->shape)[0];
    n = p->u.array.count;
    if (length->atom != JS_ATOM_length || length->flags != (JS_PROP_WRITABLE | JS_PROP_LENGTH) ||
        JS_VALUE_GET_TAG(p->prop[0].u.value) != JS_TAG_INT || n > INT32_MAX ||
        (uint32_t)JS_VALUE_GET_INT(p->prop[0].u.value) != n)
        return false;
    if (!n)
        *out = JS_UNDEFINED;
    else {
        *out = p->u.array.u.values[--n];
        p->u.array.count = n;
        p->prop[0].u.value = js_int32(n);
    }
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_c_entry(5);
#endif
    return true;
}
ARM_C_ENTRY JSValue JS_FrameAArch64GenericInvoke(JSFrameRegisterState *state, JSValue *argv,
                                                 int argc, bool method)
{
    JSObject *function = JS_VALUE_GET_OBJ(argv[-1]);
    JSContext *caller = state->frame->bytecode->realm;
    JSValue receiver = method ? argv[-2] : JS_UNDEFINED;
    JSAArch64CInvokeScope scope;
    JSValue result;
    unsigned formal = function->u.cfunc.length;
    JSValue *args = argv;
    if ((unsigned)argc < formal) {
        args = alloca(sizeof(JSValue) * formal);
        for (unsigned i = 0; i < (unsigned)argc; i++)
            args[i] = argv[i];
        for (unsigned i = (unsigned)argc; i < formal; i++)
            args[i] = JS_UNDEFINED;
    }
    --caller->interrupt_counter;
    js_arm_c_publish(state, &scope, argv, argc, (unsigned)argc < formal ? formal : (unsigned)argc);
    scope.frame.sf.arg_buf = args;
    js_arm_c_observe(0, function->u.cfunc.cproto);
    if (!js_arm_dense_pop(function, receiver, argc, method, &result)) {
        if (function->u.cfunc.cproto == JS_CFUNC_generic)
            result = function->u.cfunc.c_function.generic(function->u.cfunc.realm, receiver, argc,
                                                          vc(args));
        else
            result = function->u.cfunc.c_function.generic_magic(
                function->u.cfunc.realm, receiver, argc, vc(args), function->u.cfunc.magic);
    }
    return js_arm_c_restore(state, &scope, result);
}
ARM_C_ENTRY JSValue JS_FrameAArch64NumericInvoke(JSFrameRegisterState *state, JSValue *argv,
                                                 int argc, bool method)
{
    (void)method;
    JSObject *function = JS_VALUE_GET_OBJ(argv[-1]);
    JSAArch64CInvokeScope scope;
    JSValue result;
    --state->frame->bytecode->realm->interrupt_counter;
    js_arm_c_publish(state, &scope, argv, argc, argc);
    unsigned control = atomic_load_explicit(&JS_LinuxNumericControl, memory_order_relaxed);
    js_arm_c_observe(control & 1 ? 1 : 2, function->u.cfunc.cproto);
    if (control & 1) {
        double a = JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT ? JS_VALUE_GET_INT(argv[0])
                                                           : JS_VALUE_GET_FLOAT64(argv[0]);
        if (function->u.cfunc.cproto == JS_CFUNC_f_f)
            result = js_number(function->u.cfunc.c_function.f_f(a));
        else {
            double b = JS_VALUE_GET_TAG(argv[1]) == JS_TAG_INT ? JS_VALUE_GET_INT(argv[1])
                                                               : JS_VALUE_GET_FLOAT64(argv[1]);
            result = js_number(function->u.cfunc.c_function.f_f_f(a, b));
        }
    } else
        result = JS_LinuxNumericTrampoline(&scope.frame.sf);
    return js_arm_c_restore(state, &scope, result);
}
ARM_C_ENTRY JSValue JS_FrameAArch64BuiltinInvoke(JSFrameRegisterState *state, JSValue *argv,
                                                 int argc, bool method)
{
    JSRuntime *rt = state->rt;
    JSLinuxBuiltinView stack, *view = NULL;
    JSValue receiver = method ? argv[-2] : JS_UNDEFINED;
    JSValue result;
    unsigned mode = atomic_load_explicit(&JS_LinuxBuiltinControl, memory_order_relaxed) & 7;
    if (mode != 3) {
        if (mode == 1 && state->arities == (uintptr_t)state->frame &&
            (FRAME_FLAGS(state->frame) & FRAME_FLAG_C_WINDOW)) {
            view = (JSLinuxBuiltinView *)(uintptr_t)state->pushes;
            view->transient_segment = NULL;
#ifdef QJS_AARCH64_VM_INSTRUMENT
            qjs_aarch64_vm_c_entry(6);
#endif
        } else
            view = JS_LinuxBuiltinPrepare(state);
    }
    if (!view) {
        view = &stack;
        view->transient_segment = NULL;
    }
    --state->frame->bytecode->realm->interrupt_counter;
    memset(&view->sf, 0, sizeof(view->sf));
    view->sf.prev_frame = rt->current_stack_frame;
    view->sf.cur_func = argv[-1];
    view->sf.arg_buf = argv;
    view->sf.arg_count = argc;
    view->sf.var_buf = &receiver;
    view->slot = js_frame_shared_slot();
    view->anchor.prev = *view->slot;
    view->anchor.state = state;
    view->anchor.kind = 0;
    view->active = FRAME_SHARED_ACTIVE(rt);
    js_frame_finish_c(state);
    rt->current_stack_frame = &view->sf;
    FRAME_SHARED_BITS(rt) |= 4;
    *view->slot = &view->anchor;
    js_arm_c_observe(view->transient_segment ? 4
                     : view == &stack        ? 3
                                             : 7,
                     JS_VALUE_GET_OBJ(argv[-1])->u.cfunc.cproto);
    JS_LinuxBuiltinRun(&view->sf, &result);
    state->exception_pending = JS_IsException(result);
    if (state->exception_pending)
        state->result = result;
    *view->slot = view->anchor.prev;
    FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | view->active;
    rt->current_stack_frame = view->sf.prev_frame;
    if (view->transient_segment) {
        view->transient_segment->used -= sizeof(*view);
        js_frame_charge_stack(rt, (size_t)0 - sizeof(*view));
    }
    js_frame_finish_c(state);
    return result;
}
ARM_C_ENTRY JSValue JS_FrameAArch64CInvoke(JSFrameRegisterState *state, JSValue *argv, int argc,
                                           bool method, bool class_route)
{
    JSRuntime *rt = state->rt;
    JSObject *function;
    unsigned proto, formal, control;
    JSContext *caller = state->frame->bytecode->realm;
    if (FRAME_REGISTER_STATE(rt) != 1 || !state->direct_host_calls || argc < 0 || argc > 65535 ||
        rt->current_stack_frame != &state->frame->sf || caller->interrupt_counter <= 1)
        goto original;
    /* ARM native children deliberately defer their data-frame quota. Commit
     * the exact original delta once before this C boundary;then cache it before
     * publishing kind0. Both native and retained owners see one coherent count.
     * Shallow/deep calls consequently use the same physical native C owner. */
    js_frame_begin_c(state);
    js_frame_finish_c(state);
    if (!atomic_load_explicit(&JS_LinuxCInvokeControl, memory_order_relaxed) ||
        !atomic_load_explicit(&JS_LinuxNumericControl, memory_order_relaxed) ||
        !atomic_load_explicit(&JS_LinuxBuiltinControl, memory_order_relaxed)) {
        if (!JS_LinuxCInvokeInit(state))
            goto original;
    } else if (atomic_load_explicit(&JS_LinuxCInvokeControl, memory_order_relaxed) != 1 ||
               !js_frame_shared_enabled(rt) || (FRAME_SHARED_BITS(rt) & 8))
        goto original;
    if (JS_VALUE_GET_TAG(argv[-1]) != JS_TAG_OBJECT)
        goto original;
    function = JS_VALUE_GET_OBJ(argv[-1]);
    if (function->class_id != JS_CLASS_C_FUNCTION || function->u.cfunc.realm->rt != rt)
        goto original;
    proto = function->u.cfunc.cproto;
    formal = function->u.cfunc.length;
    /* Actual C header/view plus a target C reserve,not copied SysV scratch.
     * Every stack rejection precedes the poll/publication and keeps core errors. */
    size_t padding = (unsigned)argc < formal ? sizeof(JSValue) * formal : 0;
    if (js_check_stack_overflow(rt, sizeof(JSAArch64CInvokeScope) + sizeof(JSLinuxBuiltinView) +
                                        512 + padding))
        goto original;
    if (proto == JS_CFUNC_generic || proto == JS_CFUNC_generic_magic) {
        control = atomic_load_explicit(&JS_LinuxBuiltinControl, memory_order_relaxed);
        bool slice = proto == JS_CFUNC_generic && formal == 2 &&
                     function->u.cfunc.c_function.generic == JS_LinuxBuiltinTargets[0].generic;
        bool number =
            proto == JS_CFUNC_generic_magic && formal == 1 && !argc && !function->u.cfunc.magic &&
            !(control & 32) &&
            function->u.cfunc.c_function.generic_magic == JS_LinuxBuiltinTargets[1].generic_magic;
        if ((slice || number) && (control & 7) != 2)
            return JS_FrameAArch64BuiltinInvoke(state, argv, argc, method);
        return JS_FrameAArch64GenericInvoke(state, argv, argc, method);
    }
    if (proto != JS_CFUNC_f_f && proto != JS_CFUNC_f_f_f)
        goto original;
    if ((unsigned)argc < formal || argc < (proto == JS_CFUNC_f_f ? 1 : 2) ||
        !(atomic_load_explicit(&JS_LinuxNumericControl, memory_order_relaxed) & 3))
        goto original;
    for (unsigned i = 0; i < (proto == JS_CFUNC_f_f ? 1u : 2u); i++) {
        int tag = JS_VALUE_GET_TAG(argv[i]);
        if (tag != JS_TAG_INT && tag != JS_TAG_FLOAT64)
            goto original;
    }
    return JS_FrameAArch64NumericInvoke(state, argv, argc, method);
original:
    if (class_route)
        JS_FrameInterpHostSharedOriginal(state, argv, argc, method);
    else
        JS_FrameInterpHostDirectSharedOriginal(state, argv, argc, method);
    return state->result;
}
/* VM-only entry uses the STANDARD target JSValue aggregate return in x0/x1.
 * Compatibility int entry points retain result/event for source C callers. */
ARM_C_ENTRY JSValue JS_FrameAArch64HostDirectValue(JSFrameRegisterState *state, JSValue *argv,
                                                   int argc, bool method)
{
    return JS_FrameAArch64CInvoke(state, argv, argc, method, false);
}
ARM_C_ENTRY JSValue JS_FrameAArch64HostValue(JSFrameRegisterState *state, JSValue *argv, int argc,
                                             bool method)
{
    return JS_FrameAArch64CInvoke(state, argv, argc, method, true);
}
ARM_C_ENTRY int JS_FrameInterpHostDirectShared(JSFrameRegisterState *state, JSValue *argv, int argc,
                                               bool method)
{
    state->result = JS_FrameAArch64CInvoke(state, argv, argc, method, false);
    return state->exception_pending;
}
ARM_C_ENTRY int JS_FrameInterpHostShared(JSFrameRegisterState *state, JSValue *argv, int argc,
                                         bool method)
{
    state->result = JS_FrameAArch64CInvoke(state, argv, argc, method, true);
    return state->exception_pending;
}
#undef ARM_C_ENTRY
