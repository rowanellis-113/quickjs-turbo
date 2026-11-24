"""Constructor and host-call specialization helpers for ARM64 Fast VM."""

from arm64.vm.specialize import _replace_exact


def _specialize_constructors_and_host(text):
    # 1. Constructor return 64-bit uniqueness hash mask across all 3 streams (.L, .Lpub_, .Lknown_)
    for p in ("", "pub_", "known_"):
        old_cg = f"""    mov x9, x3
.L{p}construct_guard:
    cmp x9, x2
    b.eq .L{p}construct_release_begin
    ldp x10, x11, [x9], #16
    tbz x11, #63, .L{p}construct_guard
    ldur w12, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w12, w8
    b.le .L{p}return_fallback
    b .L{p}construct_guard"""
        new_cg = f"""    mov x13, #0
    mov x9, x3
.L{p}construct_guard:
    cmp x9, x2
    b.eq .L{p}construct_release_begin
    ldp x10, x11, [x9], #16
    tbz x11, #63, .L{p}construct_guard
    ldur w12, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w12, w8
    b.gt .L{p}construct_guard
    cmp w12, #1
    b.le .L{p}return_fallback
    eor x15, x10, x10, lsr #6
    lsr x15, x15, #4
    mov x14, #1
    lsl x14, x14, x15
    tst x13, x14
    b.ne .L{p}return_fallback
    orr x13, x13, x14
    b .L{p}construct_guard"""
        text = _replace_exact(text, old_cg, new_cg, 1, f"{p}construct_guard")

    # 1b. Hook .Lconstruct_call / .Lpub_construct_call / .Lknown_construct_call for JS_FastConstructCall Tier 1 fast continuation
    old_ctor_call_0 = """    bl JS_FrameInterpProperty_call_constructor
    cbz w0, .Lreload
    b .Ldone"""
    new_ctor_call_0 = """    bl JS_FrameInterpProperty_call_constructor
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w0, #2
    b.ne .Lconstruct_not_t1
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 1
.Lconstruct_not_t1:
#endif
    cbz w0, .Lreload
    b .Ldone"""
    text = _replace_exact(text, old_ctor_call_0, new_ctor_call_0, 1, "construct_call fast Tier 1")

    for p in ("pub_", "known_"):
        old_ctor_call_p = f""".L{p}construct_call:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #128]
    add x14, x14, #1
    str x14, [sp, #128]
#endif
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
#endif
    bl qjs_aarch64_publish_before_FrameInterpProperty_call_constructor
    cbz w0, .Lpub_reload
    b .Ldone"""
        new_ctor_call_p = f""".L{p}construct_call:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #128]
    add x14, x14, #1
    str x14, [sp, #128]
#endif
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
#endif
    bl qjs_aarch64_publish_before_FrameInterpProperty_call_constructor
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w0, #2
    b.ne .L{p}construct_not_t1
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 1
.L{p}construct_not_t1:
#endif
    cbz w0, .Lpub_reload
    b .Ldone"""
        text = _replace_exact(
            text, old_ctor_call_p, new_ctor_call_p, 1, f"{p}construct_call fast Tier 1"
        )

    # 2. Deduplicated Release host routes (generic: charCodeAt/codePointAt/localeCompare, magic: pop/push, f_f/f_f_f Math.*)
    for p in ("", "pub_"):
        old_host = f"""    ldrb w12, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic
    b.eq .L{p}call_host_ready
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .L{p}call_host_ready"""
        if not p:
            new_host = """    ldrb w12, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b.eq .Lcall_host_ready
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .Lcall_host_ready
#else
    b.eq .Lrel_fast_host_generic_chk
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .Lrel_fast_host_magic_chk
    cmp w12, #ARM_CONST_JS_CFUNC_f_f
    b.eq .Lrel_fast_math_chk
    cmp w12, #ARM_CONST_JS_CFUNC_f_f_f
    b.eq .Lrel_fast_math_chk
#endif"""
        else:
            new_host = """    ldrb w12, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b.eq .Lpub_call_host_ready
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .Lpub_call_host_ready
#else
    b.eq .Lpub_host_generic_tramp
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .Lpub_host_magic_tramp
    cmp w12, #ARM_CONST_JS_CFUNC_f_f
    b.eq .Lpub_math_tramp
    cmp w12, #ARM_CONST_JS_CFUNC_f_f_f
    b.eq .Lpub_math_tramp
#endif"""
        text = _replace_exact(text, old_host, new_host, 1, f"{p}call_host_original")

    islands = [
        """#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lpub_host_generic_tramp:
    orr w17, w17, #4
    b .Lrel_fast_host_generic_chk
.Lpub_host_magic_tramp:
    orr w17, w17, #4
    b .Lrel_fast_host_magic_chk
.Lpub_math_tramp:
    orr w17, w17, #4
    b .Lrel_fast_math_chk

.Lrel_fast_math_fallback:
    mov w16, #0
    tbz w17, #2, .Lcall_class_host
    bic w17, w17, #4
    b .Lpub_call_class_host
.Lrel_fast_math_chk:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #20, .Lrel_fast_math_fallback
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 1)]
    cmp w15, #1
    b.ne .Lrel_fast_math_fallback
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 3)]
    cmp w15, #1
    b.ne .Lrel_fast_math_fallback
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 5)]
    tbnz w15, #1, .Lrel_fast_math_fallback
    tbnz w15, #3, .Lrel_fast_math_fallback
    tbnz w17, #2, .Lrel_fast_math_rt_ok
    ldr x15, [x14, #ARM_OFF_JSRuntime_current_stack_frame]
    cmp x15, x22
    b.ne .Lrel_fast_math_fallback
.Lrel_fast_math_rt_ok:
    ldr x15, [x3, #ARM_OFF_JSObject_u_cfunc_realm]
    ldr x15, [x15, #ARM_OFF_JSContext_rt]
    cmp x15, x14
    b.ne .Lrel_fast_math_fallback
    ldrb w15, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w0, w15
    b.lo .Lrel_fast_math_fallback
    mov w15, #65535
    cmp w0, w15
    b.hi .Lrel_fast_math_fallback
    ldr x15, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x15, .Lrel_fast_math_stk_ok
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x15, x15, x14
    b.cs .Lrel_fast_math_fallback
    adds x15, x15, #1024
    b.cs .Lrel_fast_math_fallback
    mov x14, sp
    cmp x14, x15
    b.lo .Lrel_fast_math_fallback
.Lrel_fast_math_stk_ok:
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #1
    b.le .Lrel_fast_math_fallback
    cbz w0, .Lrel_fast_math_fallback
    ldp x9, x10, [x2]
    cbz x10, .Lrel_fast_math_a0_i32
    cmp x10, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lrel_fast_math_fallback
    fmov d0, x9
    b .Lrel_fast_math_a0_done
.Lrel_fast_math_a0_i32:
    scvtf d0, w9
.Lrel_fast_math_a0_done:
    cmp w12, #ARM_CONST_JS_CFUNC_f_f_f
    b.ne .Lrel_fast_math_go
    cmp w0, #2
    b.lo .Lrel_fast_math_fallback
    ldp x9, x10, [x2, #16]
    cbz x10, .Lrel_fast_math_a1_i32
    cmp x10, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lrel_fast_math_fallback
    fmov d1, x9
    b .Lrel_fast_math_go
.Lrel_fast_math_a1_i32:
    scvtf d1, w9
.Lrel_fast_math_go:
    sub w16, w16, #1
    str w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    mov w28, w0
    orr w28, w28, w17, lsl #16
    sub x14, x1, x20
    orr w28, w28, w14, lsl #24
    ldr x14, [x3, #ARM_OFF_JSObject_u_cfunc_c_function]
    blr x14
    uxth w0, w28
    ubfx w17, w28, #16, #3
    lsr w14, w28, #24
    mov x28, #0
    add x1, x20, x14
    strb wzr, [x19, #ARM_OFF_JSFrameRegisterState_exception_pending]
    fmov x5, d0
    fcvtzs w11, d0
    scvtf d1, w11
    fcmp d0, d1
    b.ne .Lrel_fast_math_ret_f64
    cbnz w11, .Lrel_fast_math_ret_i32
    tbnz x5, #63, .Lrel_fast_math_ret_f64
.Lrel_fast_math_ret_i32:
    sxtw x5, w11
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_math_pop
.Lrel_fast_math_ret_f64:
    mov x6, #ARM_CONST_JS_TAG_FLOAT64
.Lrel_fast_math_pop:
    and w9, w17, #1
    add w9, w9, w0
    add w9, w9, #1
    b .Lrel_fast_leaf_pop_entry

.Lrel_fast_host_fallback:
    mov w16, #0
    tbz w17, #2, .Lcall_host_ready
    bic w17, w17, #4
    b .Lpub_call_host_ready

.Lrel_fast_host_magic_chk:
    and w14, w17, #3
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    ldrh w14, [x3, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w14, .Lrel_fast_host_fallback
    cmp w0, #1
    b.eq .Lrel_fast_array_push_chk
    cbnz w0, .Lrel_fast_host_fallback
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cbnz w14, .Lrel_fast_host_fallback
    ldr x14, [x3, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x15, JS_FrameDenseArrayPop
    add x15, x15, :lo12:JS_FrameDenseArrayPop
    cmp x14, x15
    b.ne .Lrel_fast_host_fallback
    adrp x14, JS_LinuxCInvokeControl
    add x14, x14, :lo12:JS_LinuxCInvokeControl
    ldarb w14, [x14]
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    adrp x14, JS_LinuxDensePopControl
    add x14, x14, :lo12:JS_LinuxDensePopControl
    ldarb w14, [x14]
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    adrp x14, JS_LinuxDensePopLeafControl
    add x14, x14, :lo12:JS_LinuxDensePopLeafControl
    ldarb w14, [x14]
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    ldur w14, [x3, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .Lrel_fast_host_fallback
    ldp x9, x10, [x2, #-32]
    cmn x10, #1
    b.ne .Lrel_fast_host_fallback
    ldur w15, [x9, #ARM_REF_COUNT_OFFSET]
    cmp w15, #1
    b.le .Lrel_fast_host_fallback
    ldrh w10, [x9, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_host_fallback
    ldrb w10, [x9, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w10, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_host_fallback
    ldrb w10, [x9, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lrel_fast_host_fallback
    ldr x10, [x9, #ARM_OFF_JSObject_shape]
    ldr w11, [x10, #ARM_OFF_JSShape_prop_hash_mask]
    add x10, x10, w11, uxtw #2
    add x10, x10, #(ARM_OFF_JSShape_hash_table + 4)
    ldr w11, [x10, #ARM_OFF_JSShapeProperty_atom]
    cmp w11, #ARM_CONST_JS_ATOM_length
    b.ne .Lrel_fast_host_fallback
    ldr w11, [x10]
    lsr w11, w11, #26
    cmp w11, #10
    b.ne .Lrel_fast_host_fallback
    ldr x10, [x9, #ARM_OFF_JSObject_prop]
    ldr x11, [x10, #8]
    cbnz x11, .Lrel_fast_host_fallback
    ldr w11, [x10]
    ldr w12, [x9, #ARM_OFF_JSObject_u_array_count]
    cmp w11, w12
    b.ne .Lrel_fast_host_fallback
    cmp w12, #0
    b.lt .Lrel_fast_host_fallback
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w13, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w13, w13, #1
    b.le .Lrel_fast_host_fallback
    str w13, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cbz w12, .Lrel_fast_pop_empty
    sub w12, w12, #1
    ldr x11, [x9, #ARM_OFF_JSObject_u_array_u_values]
    add x11, x11, w12, uxtw #4
    ldp x5, x6, [x11]
    str w12, [x9, #ARM_OFF_JSObject_u_array_count]
    str x12, [x10]
    b .Lrel_fast_pop_commit
.Lrel_fast_pop_empty:
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
.Lrel_fast_pop_commit:
    sub w14, w14, #1
    stur w14, [x3, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    stur w15, [x9, #ARM_REF_COUNT_OFFSET]
    stp x5, x6, [x2, #-32]
    sub x21, x2, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1

.Lrel_fast_array_push_chk:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #20, .Lrel_fast_host_fallback
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    ldr x14, [x3, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x15, qjs_fast_core_js_array_push
    ldr x15, [x15, :lo12:qjs_fast_core_js_array_push]
    cmp x14, x15
    b.ne .Lrel_fast_host_fallback
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x12, [x3, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x12, x11
    b.ne .Lrel_fast_host_fallback
    ldur w14, [x3, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .Lrel_fast_host_fallback
    ldp x9, x10, [x2, #-32]
    cmn x10, #1
    b.ne .Lrel_fast_host_fallback
    ldur w15, [x9, #ARM_REF_COUNT_OFFSET]
    cmp w15, #1
    b.le .Lrel_fast_host_fallback
    ldrh w10, [x9, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_host_fallback
    ldrb w10, [x9, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w10, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_host_fallback
    ldrb w10, [x9, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lrel_fast_host_fallback
    ldrb w10, [x11, #ARM_BIT_JSContext_std_array_prototype_BYTE]
    tst w10, #ARM_BIT_JSContext_std_array_prototype_MASK
    b.eq .Lrel_fast_host_fallback
    ldr x10, [x9, #ARM_OFF_JSObject_shape]
    ldr x12, [x10, #ARM_OFF_JSShape_proto]
    ldr x13, [x11, #ARM_OFF_JSContext_class_proto]
    ldp x13, x8, [x13, #(ARM_CONST_JS_CLASS_ARRAY * 16)]
    cmn x8, #1
    b.ne .Lrel_fast_host_fallback
    cmp x12, x13
    b.ne .Lrel_fast_host_fallback
    ldr w12, [x10, #ARM_OFF_JSShape_prop_hash_mask]
    add x10, x10, w12, uxtw #2
    add x10, x10, #(ARM_OFF_JSShape_hash_table + 4)
    ldr w12, [x10, #ARM_OFF_JSShapeProperty_atom]
    cmp w12, #ARM_CONST_JS_ATOM_length
    b.ne .Lrel_fast_host_fallback
    ldr w12, [x10]
    tst w12, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_host_fallback
    tst w12, #ARM_PROPERTY_DESC_WRITABLE
    b.eq .Lrel_fast_host_fallback
    ldr x10, [x9, #ARM_OFF_JSObject_prop]
    ldr x12, [x10, #8]
    cbnz x12, .Lrel_fast_host_fallback
    ldr w12, [x10]
    ldr w13, [x9, #ARM_OFF_JSObject_u_array_count]
    cmp w12, w13
    b.ne .Lrel_fast_host_fallback
    ldr w13, [x9, #ARM_OFF_JSObject_u_array_u1_size]
    cmp w12, w13
    b.hs .Lrel_fast_host_fallback
    adds w8, w12, #1
    b.vs .Lrel_fast_host_fallback
    ldr w13, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w13, w13, #1
    b.le .Lrel_fast_host_fallback
    str w13, [x11, #ARM_OFF_JSContext_interrupt_counter]
    ldr x13, [x9, #ARM_OFF_JSObject_u_array_u_values]
    add x13, x13, w12, uxtw #4
    ldp x5, x6, [x2]
    stp x5, x6, [x13]
    mov w8, w8
    str w8, [x9, #ARM_OFF_JSObject_u_array_count]
    str x8, [x10]
    sub w14, w14, #1
    stur w14, [x3, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    stur w15, [x9, #ARM_REF_COUNT_OFFSET]
    stp x8, xzr, [x2, #-32]
    sub x21, x2, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1

.Lrel_fast_host_generic_chk:
    cmp w0, #1
    b.ne .Lrel_fast_host_fallback
    and w14, w17, #3
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #20, .Lrel_fast_host_fallback
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .Lrel_fast_host_fallback
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x12, [x3, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x12, x11
    b.ne .Lrel_fast_host_fallback
    ldur w14, [x3, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .Lrel_fast_host_fallback
    ldp x9, x10, [x2, #-32]
    cmn x10, #7
    b.ne .Lrel_fast_host_fallback
    ldur w15, [x9, #ARM_REF_COUNT_OFFSET]
    cmp w15, #1
    b.le .Lrel_fast_host_fallback
    ldr x12, [x3, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x13, JS_FrameLocaleCompare
    add x13, x13, :lo12:JS_FrameLocaleCompare
    cmp x12, x13
    b.eq .Lrel_fast_locale_compare
    mov w8, #0
    adrp x13, qjs_fast_core_js_string_charCodeAt
    ldr x13, [x13, :lo12:qjs_fast_core_js_string_charCodeAt]
    cmp x12, x13
    b.eq .Lrel_fast_str_char
    mov w8, #1
    adrp x13, qjs_fast_core_js_string_codePointAt
    ldr x13, [x13, :lo12:qjs_fast_core_js_string_codePointAt]
    cmp x12, x13
    b.ne .Lrel_fast_host_fallback
.Lrel_fast_str_char:
    ldp x12, x13, [x2]
    cbnz x13, .Lrel_fast_host_fallback
    ldr w16, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #1
    b.le .Lrel_fast_host_fallback
    ldr w7, [x9, #ARM_BIT_JSString_len_BYTE]
    and w6, w7, #0x7fffffff
    cmp w12, w6
    b.hs .Lrel_fast_str_char_oob
    ldr w13, [x9, #ARM_BIT_JSString_hash_BYTE]
    ubfx w13, w13, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbz w13, .Lrel_fast_str_k0
    cmp w13, #1
    b.eq .Lrel_fast_str_k1
    cmp w13, #2
    b.ne .Lrel_fast_host_fallback
    ldr x13, [x9, #ARM_SIZE_JSString]
    b .Lrel_fast_str_ptr
.Lrel_fast_str_k0:
    add x13, x9, #ARM_SIZE_JSString
    b .Lrel_fast_str_ptr
.Lrel_fast_str_k1:
    ldr x4, [x9, #ARM_SIZE_JSString]
    ldr w13, [x9, #(ARM_SIZE_JSString + 8)]
    add x13, x4, x13
    add x13, x13, #ARM_SIZE_JSString
.Lrel_fast_str_ptr:
    tbnz w7, #31, .Lrel_fast_str_wide
    ldrb w5, [x13, w12, uxtw]
    mov x6, #0
    b .Lrel_fast_str_commit
.Lrel_fast_str_wide:
    ldrh w5, [x13, w12, uxtw #1]
    cbz w8, .Lrel_fast_str_wide_done
    lsr w10, w5, #10
    cmp w10, #0x36
    b.eq .Lrel_fast_host_fallback
.Lrel_fast_str_wide_done:
    mov x6, #0
    b .Lrel_fast_str_commit
.Lrel_fast_str_char_oob:
    cbnz w8, .Lrel_fast_str_cp_oob
    movz x5, #0x7ff8, lsl #48
    mov x6, #ARM_CONST_JS_TAG_FLOAT64
    b .Lrel_fast_str_commit
.Lrel_fast_str_cp_oob:
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
.Lrel_fast_str_commit:
    sub w16, w16, #1
    str w16, [x11, #ARM_OFF_JSContext_interrupt_counter]
    sub w14, w14, #1
    stur w14, [x3, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    stur w15, [x9, #ARM_REF_COUNT_OFFSET]
    stp x5, x6, [x2, #-32]
    sub x21, x2, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1

.Lrel_fast_locale_compare:
    adrp x13, .Lfast_vm_ext_env
    ldr w13, [x13, :lo12:.Lfast_vm_ext_env]
    tbz w13, #0, .Lrel_fast_host_fallback
    ldp x12, x13, [x2]
    cmn x13, #7
    b.ne .Lrel_fast_host_fallback
    ldr w4, [x9, #ARM_BIT_JSString_len_BYTE]
    tbnz w4, #31, .Lrel_fast_host_fallback
    ldr w5, [x12, #ARM_BIT_JSString_len_BYTE]
    tbnz w5, #31, .Lrel_fast_host_fallback
    ldr w16, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #1
    b.le .Lrel_fast_host_fallback
    cmp x9, x12
    b.ne .Lrel_fast_lc_distinct
    cmp w15, #2
    b.le .Lrel_fast_host_fallback
    sub w16, w16, #1
    str w16, [x11, #ARM_OFF_JSContext_interrupt_counter]
    sub w14, w14, #1
    stur w14, [x3, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #2
    stur w15, [x9, #ARM_REF_COUNT_OFFSET]
    stp xzr, xzr, [x2, #-32]
    sub x21, x2, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.Lrel_fast_lc_distinct:
    ldur w6, [x12, #ARM_REF_COUNT_OFFSET]
    cmp w6, #1
    b.le .Lrel_fast_host_fallback
    ldr w7, [x9, #ARM_BIT_JSString_hash_BYTE]
    ubfx w7, w7, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbz w7, .Lrel_fast_lc_a0
    cmp w7, #1
    b.eq .Lrel_fast_lc_a1
    cmp w7, #2
    b.ne .Lrel_fast_host_fallback
    ldr x8, [x9, #ARM_SIZE_JSString]
    b .Lrel_fast_lc_chk_b
.Lrel_fast_lc_a0:
    add x8, x9, #ARM_SIZE_JSString
    b .Lrel_fast_lc_chk_b
.Lrel_fast_lc_a1:
    ldr x13, [x9, #ARM_SIZE_JSString]
    ldr w8, [x9, #(ARM_SIZE_JSString + 8)]
    add x8, x13, x8
    add x8, x8, #ARM_SIZE_JSString
.Lrel_fast_lc_chk_b:
    ldr w7, [x12, #ARM_BIT_JSString_hash_BYTE]
    ubfx w7, w7, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbz w7, .Lrel_fast_lc_b0
    cmp w7, #1
    b.eq .Lrel_fast_lc_b1
    cmp w7, #2
    b.ne .Lrel_fast_host_fallback
    ldr x10, [x12, #ARM_SIZE_JSString]
    b .Lrel_fast_lc_cmp
.Lrel_fast_lc_b0:
    add x10, x12, #ARM_SIZE_JSString
    b .Lrel_fast_lc_cmp
.Lrel_fast_lc_b1:
    ldr x13, [x12, #ARM_SIZE_JSString]
    ldr w10, [x12, #(ARM_SIZE_JSString + 8)]
    add x10, x13, x10
    add x10, x10, #ARM_SIZE_JSString
.Lrel_fast_lc_cmp:
    cmp w4, w5
    csel w7, w4, w5, lo
.Lrel_fast_lc_loop:
    cbz w7, .Lrel_fast_lc_len
    ldrb w0, [x8], #1
    ldrb w13, [x10], #1
    cmp w0, w13
    b.ne .Lrel_fast_lc_diff
    sub w7, w7, #1
    b .Lrel_fast_lc_loop
.Lrel_fast_lc_len:
    cmp w4, w5
    b.eq .Lrel_fast_lc_eq
.Lrel_fast_lc_diff:
    mov w0, #-1
    mov w13, #1
    csel w0, w0, w13, lo
    b .Lrel_fast_lc_commit
.Lrel_fast_lc_eq:
    mov w0, #0
.Lrel_fast_lc_commit:
    sxtw x0, w0
    sub w16, w16, #1
    str w16, [x11, #ARM_OFF_JSContext_interrupt_counter]
    sub w14, w14, #1
    stur w14, [x3, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    stur w15, [x9, #ARM_REF_COUNT_OFFSET]
    sub w6, w6, #1
    stur w6, [x12, #ARM_REF_COUNT_OFFSET]
    stp x0, xzr, [x2, #-32]
    sub x21, x2, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
#endif
"""
    ]
    return text, "\n".join(islands)
