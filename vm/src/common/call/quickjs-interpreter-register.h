/* State transferred only at an assembly/C boundary. Normal JS calls stay in
 * JS_FrameInterp, with a fixed PC/SP/frame/argument/local register convention. */
typedef struct JSFrameRegisterState {
    JSFrame *frame;          /* 0 */
    JSFrameSegment *segment; /* 8 */
    uint8_t *pc;             /* 16: opcode address, not operand address */
    JSValue *sp;             /* 24 */
    size_t used_bytes;       /* 32 */
    JSValue result;          /* 40: C result/finalizer return spill */
    JSRuntime *rt;           /* 56 */
#if defined(QJS_INTERP_FRAME_INTERNAL_ENTRY) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
    /* Release images never increment these diagnostic slots. Give them the
     * quota protocol's actual state without growing or moving the record. */
    size_t committed_bytes;       /* 64 */
    uintptr_t native_stack_limit; /* 72: excludes this activation's charge */
    uintptr_t shared_stack_limit; /* 80: last observed runtime limit */
#else
    uint64_t native_calls;   /* 64 */
    uint64_t native_returns; /* 72 */
    uint64_t slow_exits;     /* 80 */
#endif
    uint64_t pushes;           /* 88: diagnostic counters */
    uint64_t arities;          /* 96 */
    uint64_t borrowed_values;  /* 104 */
    uint64_t windows;          /* 112 */
    size_t peak_bytes;         /* 120 */
    unsigned depth, max_depth; /* 128, 132 */
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    uint64_t native_windows;    /* 136 */
    uint64_t slow_opcodes[256]; /* 144 */
    uint64_t cache_hits, cache_misses, bridges, copied_values;
    uint64_t window_fallbacks, window_bytes, shallow_values, cross_windows;
    uint64_t window_helpers;
    uint64_t native_hosts;
#endif
    JSContext *caller_ctx;
    JSFrameCallSite *sites;
    uint8_t *cache_next;
    bool exception_pending;
    bool direct_host_calls;             /* consumes existing boundary-record padding */
    uint32_t iterator_checkpoint_depth; /* remaining boundary padding, ABI size unchanged */
#if defined(QJS_INTERP_FRAME_INTERNAL_ENTRY) && defined(QJS_INTERP_FRAME_DIAGNOSTICS)
    size_t committed_bytes;       /* 2304: retain all diagnostic offsets */
    uintptr_t native_stack_limit; /* 2312 */
    uintptr_t shared_stack_limit; /* 2320 */
    uint64_t budget_syncs, budget_refreshes;
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    uint64_t return_root_stores, return_finalizer_spills, return_host_loads, return_caller_stores;
    uint64_t call_prepare_hits, call_prepare_inits;
    uint64_t direct_host_generic, direct_host_magic;
    /* Appended only in diagnostics. Release uses the otherwise untouched
       pushes/arities/borrowed_values/windows/peak_bytes slots88..127. */
    void *native_c_view, *native_c_owner, *native_c_vars;
    uint64_t native_c_geometry;
    uint64_t native_c_frame_bytes;
#endif
} JSFrameRegisterState;

#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
#define FRAME_REGISTER_STATE_BYTES 2448
#else
#define FRAME_REGISTER_STATE_BYTES 2408
#endif
#define FRAME_REGISTER_STATE_EXCEPTION 2296
#else
#define FRAME_REGISTER_STATE_BYTES 168
#define FRAME_REGISTER_STATE_EXCEPTION 160
#endif
_Static_assert(sizeof(JSFrameRegisterState) == FRAME_REGISTER_STATE_BYTES &&
                   offsetof(JSFrameRegisterState, exception_pending) ==
                       FRAME_REGISTER_STATE_EXCEPTION &&
                   offsetof(JSFrameRegisterState, direct_host_calls) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 1 &&
                   offsetof(JSFrameRegisterState, iterator_checkpoint_depth) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 4,
               "owned state profile and literal flag padding");

/* These assertions intentionally bind the independent assembler to this
 * version's ORIGINAL private types. No core type is changed. */
_Static_assert(JS_TAG_SHORT_BIG_INT == 7 && sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   offsetof(JSValue, tag) == 8 && JS_SHORT_BIG_INT_MIN == INT32_MIN &&
                   JS_SHORT_BIG_INT_MAX == INT32_MAX,
               "native short BigInt tag, slot and signed arithmetic range");
_Static_assert(sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode &&
                   offsetof(JSFunctionBytecode, byte_code_buf) ==
                       QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf &&
                   sizeof(JSFrame) == 128,
               "function-owned call descriptor ABI");
_Static_assert(160 + 16 * (128 + 256) + 8 * (128 + 128) <= UINT16_MAX,
               "validated frame allocation fits descriptor word");
#define FRAME_ABI_OFFSET(type, field, offset)                                                      \
    _Static_assert(offsetof(type, field) == offset, "register ABI: " #type "." #field)
FRAME_ABI_OFFSET(JSFrameRegisterState, rt, 56);
#if defined(QJS_INTERP_FRAME_INTERNAL_ENTRY) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
FRAME_ABI_OFFSET(JSFrameRegisterState, committed_bytes, 64);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_stack_limit, 72);
FRAME_ABI_OFFSET(JSFrameRegisterState, shared_stack_limit, 80);
_Static_assert(sizeof(JSFrameRegisterState) == 168, "release boundary record unchanged");
FRAME_ABI_OFFSET(JSFrameRegisterState, direct_host_calls, 161);
FRAME_ABI_OFFSET(JSFrameRegisterState, iterator_checkpoint_depth, 164);
#else
FRAME_ABI_OFFSET(JSFrameRegisterState, native_calls, 64);
#endif
FRAME_ABI_OFFSET(JSFrameRegisterState, depth, 128);

#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
FRAME_ABI_OFFSET(JSFrameRegisterState, sites, 2280);
FRAME_ABI_OFFSET(JSFrameRegisterState, cache_next, 2288);
#else
FRAME_ABI_OFFSET(JSFrameRegisterState, sites, 144);
FRAME_ABI_OFFSET(JSFrameRegisterState, cache_next, 152);
#endif
_Static_assert(JS_TAG_UNINITIALIZED == 4, "binding fallback preserves lexical TDZ");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
FRAME_ABI_OFFSET(JSFrameRegisterState, native_windows, 136);
FRAME_ABI_OFFSET(JSFrameRegisterState, slow_opcodes, 144);
FRAME_ABI_OFFSET(JSFrameRegisterState, cross_windows, 2248);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_hosts, 2264);
FRAME_ABI_OFFSET(JSFrameRegisterState, direct_host_calls, 2297);
FRAME_ABI_OFFSET(JSFrameRegisterState, iterator_checkpoint_depth, 2300);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
FRAME_ABI_OFFSET(JSFrameRegisterState, committed_bytes, 2304);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_stack_limit, 2312);
FRAME_ABI_OFFSET(JSFrameRegisterState, shared_stack_limit, 2320);
FRAME_ABI_OFFSET(JSFrameRegisterState, return_root_stores, 2344);
FRAME_ABI_OFFSET(JSFrameRegisterState, call_prepare_hits, 2376);
#else
FRAME_ABI_OFFSET(JSFrameRegisterState, return_root_stores, 2304);
FRAME_ABI_OFFSET(JSFrameRegisterState, call_prepare_hits, 2336);
#endif
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
FRAME_ABI_OFFSET(JSFrameRegisterState, native_c_view, 2408);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_c_owner, 2416);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_c_vars, 2424);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_c_geometry, 2432);
FRAME_ABI_OFFSET(JSFrameRegisterState, native_c_frame_bytes, 2440);
#endif
#else
FRAME_ABI_OFFSET(JSFrameRegisterState, pushes, 88);
FRAME_ABI_OFFSET(JSFrameRegisterState, arities, 96);
FRAME_ABI_OFFSET(JSFrameRegisterState, borrowed_values, 104);
FRAME_ABI_OFFSET(JSFrameRegisterState, windows, 112);
FRAME_ABI_OFFSET(JSFrameRegisterState, peak_bytes, 120);
#endif
FRAME_ABI_OFFSET(JSFrame, bytecode, 80);
FRAME_ABI_OFFSET(JSFrame, this_value, 88);
FRAME_ABI_OFFSET(JSFrame, saved_sp, 104);
FRAME_ABI_OFFSET(JSFrame, segment, 112);
FRAME_ABI_OFFSET(JSFrame, frame_bytes, 120);
FRAME_ABI_OFFSET(JSFrame, owned_args, 124);
FRAME_ABI_OFFSET(JSFrame, pending, 126);
FRAME_ABI_OFFSET(JSStackFrame, arg_buf, QJS_ABI_OFF_JSStackFrame_arg_buf);
FRAME_ABI_OFFSET(JSStackFrame, var_buf, QJS_ABI_OFF_JSStackFrame_var_buf);
FRAME_ABI_OFFSET(JSStackFrame, var_refs, QJS_ABI_OFF_JSStackFrame_var_refs);
FRAME_ABI_OFFSET(JSStackFrame, cur_pc, QJS_ABI_OFF_JSStackFrame_cur_pc);
FRAME_ABI_OFFSET(JSStackFrame, var_ref_count, QJS_ABI_OFF_JSStackFrame_var_ref_count);
FRAME_ABI_OFFSET(JSStackFrame, arg_count, QJS_ABI_OFF_JSStackFrame_arg_count);
FRAME_ABI_OFFSET(JSStackFrame, is_strict_mode, QJS_ABI_OFF_JSStackFrame_is_strict_mode);
#if QJS_ABI_HAS_CORO_OWNER
FRAME_ABI_OFFSET(JSStackFrame, is_constructor, 61);
#endif
FRAME_ABI_OFFSET(JSStackFrame, cur_sp, QJS_ABI_OFF_JSStackFrame_cur_sp);
_Static_assert(sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame && sizeof(bool) == 1,
               "root marker uses padding byte 62, never a named core field");
_Static_assert(128 + 16 * (128 + 128 + 256 + 128) + 8 * 256 <= UINT32_MAX,
               "bounded owned args, locals, stack, window and capture bytes fit compact counter");
FRAME_ABI_OFFSET(JSFunctionBytecode, arg_count, QJS_ABI_OFF_JSFunctionBytecode_arg_count);
FRAME_ABI_OFFSET(JSFunctionBytecode, var_count, QJS_ABI_OFF_JSFunctionBytecode_var_count);
FRAME_ABI_OFFSET(JSFunctionBytecode, var_ref_count, QJS_ABI_OFF_JSFunctionBytecode_var_ref_count);
FRAME_ABI_OFFSET(JSFunctionBytecode, stack_size, QJS_ABI_OFF_JSFunctionBytecode_stack_size);
FRAME_ABI_OFFSET(JSFunctionBytecode, realm, QJS_ABI_OFF_JSFunctionBytecode_realm);
FRAME_ABI_OFFSET(JSFunctionBytecode, cpool, QJS_ABI_OFF_JSFunctionBytecode_cpool);
FRAME_ABI_OFFSET(JSObject, class_id, QJS_ABI_OFF_JSObject_class_id);
FRAME_ABI_OFFSET(JSObject, u.func.function_bytecode, QJS_ABI_OFF_JSObject_u_func_function_bytecode);
FRAME_ABI_OFFSET(JSObject, u.func.var_refs, QJS_ABI_OFF_JSObject_u_func_var_refs);
FRAME_ABI_OFFSET(JSObject, u.cfunc.cproto, QJS_ABI_OFF_JSObject_u_cfunc_cproto);
_Static_assert(JS_CLASS_C_FUNCTION == 12 && JS_CFUNC_generic == 0 && JS_CFUNC_generic_magic == 1 &&
                   JS_TAG_OBJECT == -1,
               "native host dispatcher class, signature and full value tag");
FRAME_ABI_OFFSET(JSVarRef, pvalue, QJS_ABI_OFF_JSVarRef_pvalue);
FRAME_ABI_OFFSET(JSContext, interrupt_counter, QJS_ABI_OFF_JSContext_interrupt_counter);
FRAME_ABI_OFFSET(JSContext, global_obj, QJS_ABI_OFF_JSContext_global_obj);
FRAME_ABI_OFFSET(JSContext, global_var_obj, QJS_ABI_OFF_JSContext_global_var_obj);
FRAME_ABI_OFFSET(JSShape, prop_hash_mask, QJS_ABI_OFF_JSShape_prop_hash_mask);
FRAME_ABI_OFFSET(JSShape, prop_count, QJS_ABI_OFF_JSShape_prop_count);
#if QJS_ABI_HAS_PREFIX_RC
FRAME_ABI_OFFSET(JSShape, hash_table, 56);
#else
FRAME_ABI_OFFSET(JSShape, prop, QJS_ABI_OFF_JSShape_prop);
#endif
_Static_assert(sizeof(JSShapeProperty) == 8 &&
                   offsetof(JSShapeProperty, atom) == QJS_ABI_OFF_JSShapeProperty_atom,
               "register ABI shape property");
_Static_assert(sizeof(JSProperty) == QJS_ABI_SIZE_JSProperty && JS_PROP_TMASK == 48,
               "register ABI property");
FRAME_ABI_OFFSET(JSRuntime, stack_limit, QJS_ABI_OFF_JSRuntime_stack_limit);
FRAME_ABI_OFFSET(JSRuntime, stack_top, QJS_ABI_OFF_JSRuntime_stack_top);
FRAME_ABI_OFFSET(JSRuntime, atom_array, QJS_ABI_OFF_JSRuntime_atom_array);
FRAME_ABI_OFFSET(JSObject, u.array.u.values, QJS_ABI_OFF_JSObject_u_array_u_values);
FRAME_ABI_OFFSET(JSObject, u.array.count, QJS_ABI_OFF_JSObject_u_array_count);
FRAME_ABI_OFFSET(JSObject, u.typed_array, QJS_ABI_OFF_JSObject_u_typed_array);
FRAME_ABI_OFFSET(JSObject, u.array_buffer, QJS_ABI_OFF_JSObject_u_array_buffer);
FRAME_ABI_OFFSET(JSObject, u.array.u.int32_ptr, QJS_ABI_OFF_JSObject_u_array_u_int32_ptr);
FRAME_ABI_OFFSET(JSTypedArray, buffer, QJS_ABI_OFF_JSTypedArray_buffer);
FRAME_ABI_OFFSET(JSArrayBuffer, immutable, QJS_ABI_OFF_JSArrayBuffer_immutable);
_Static_assert(JS_CLASS_INT32_ARRAY == 27, "register ABI Int32Array class");
_Static_assert(offsetof(JSString, hash_next) == QJS_ABI_OFF_JSString_hash_next &&
                   JS_ATOM_TYPE_STRING == 1 && JS_ATOM_empty_string == 48,
               "register ABI atom layout");
_Static_assert(JS_CLASS_ARRAY == 2 && JS_PROP_WRITABLE == 2 && JS_PROP_LENGTH == 8 &&
                   JS_PROP_TMASK == 48,
               "register ABI writable data flags");
_Static_assert(JS_TAG_FLOAT64 == 8 && JS_TAG_STRING == -7 && JS_TAG_SYMBOL == -8,
               "register ABI native value tags");
_Static_assert(sizeof(JSFrame) == 128, "register ABI frame size");
_Static_assert(QJS_ABI_REF_COUNT_OFFSET == (QJS_ABI_HAS_PREFIX_RC ? -4 : 0),
               "register ABI refcount");
_Static_assert(JS_CLASS_BYTECODE_FUNCTION == 13, "register ABI function class");
#undef FRAME_ABI_OFFSET

/* The assembly activation remains alive across C slow steps. Return 1 after
 * the root has returned/unwound; result is owned by the caller and every frame
 * has already been released. The C step's own 0 result means resume in assembly. */
extern int JS_FrameInterp(JSFrameRegisterState *state);

/* Private native return ABI: XMM0 owns one complete JSValue through frame
 * pop, ordinary decrefs and tail-return chains. Last-reference releases spill
 * it to result before C and reload afterwards. Host results load it from
 * result; native roots materialize it there before cleanup. C slow exits keep their existing
 * result/event protocol and must not be overwritten by an unrelated XMM0. */
