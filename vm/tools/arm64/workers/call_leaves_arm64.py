"""Noncalling call-leaf specialization helpers for ARM64 Fast VM."""

from arm64.vm.specialize import _replace_exact


def _specialize_call_leaves(text):
    islands = []
    for p in ("", "pub_"):
        old_have = f"""    cmn x4, #1
    b.ne .L{p}slow
    ldrh w12, [x3, #ARM_OFF_JSObject_class_id]"""
        new_have = f"""    cmn x4, #1
    b.ne .L{p}slow
.L{p}call_have_callee:
    ldrh w12, [x3, #ARM_OFF_JSObject_class_id]"""
        text = _replace_exact(text, old_have, new_have, 1, f"{p}call_have_callee")

        old_cf = f"""    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .L{p}call_host_original
    mov w28, w0
    orr w28, w28, w17, lsl #16"""
        if not p:
            new_cf = """    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .Lcall_host_original
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b .Lrel_fast_call_forward_leaf
.Lcall_forward_probe_orig:
#endif
    mov w28, w0
    orr w28, w28, w17, lsl #16"""
        else:
            new_cf = """    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .Lpub_call_host_original
#ifndef QJS_AARCH64_VM_INSTRUMENT
    orr w17, w17, #4
    b .Lrel_fast_call_forward_leaf
.Lpub_call_forward_probe_orig:
#endif
    mov w28, w0
    orr w28, w28, w17, lsl #16"""
        text = _replace_exact(text, old_cf, new_cf, 1, f"{p}call_forward_guard")

        old_arity = f""".L{p}call_arity_ready:
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x9, x13, x14
    add x9, x9, x16
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
// The actual C builder places an align16 local pointer table after the
// declared operand area. Reserve it before any quota/capacity commitment.
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    mov x15, #ARM_VAR_REF_POINTER_BYTES
    mul x12, x12, x15
    add x12, x12, #15
    and x12, x12, #-16
    add x9, x9, x12"""
        new_arity = f""".L{p}call_arity_ready:
#ifndef QJS_AARCH64_VM_INSTRUMENT
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbnz w12, .L{p}call_bytes_slow
    ldrh w9, [x7, #ARM_FRAME_CALL_META_OFFSET]
    cbnz w9, .L{p}call_add_owned
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x9, x13, x14
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
    cmp x9, #65536
    b.hs .L{p}call_add_owned
    ldrb w15, [x7, #ARM_FRAME_KIND_OFFSET]
    and w14, w15, #0x0f
    bic w14, w14, #0x02
    cmp w14, #1
    b.ne .L{p}call_add_owned
    cmp w13, #255
    b.hi .L{p}call_add_owned
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w14, #255
    b.hi .L{p}call_add_owned
    strb w13, [x7, #ARM_FRAME_CALL_LOCALS_OFFSET]
    strb w14, [x7, #ARM_FRAME_CALL_FORMALS_OFFSET]
    strh w9, [x7, #ARM_FRAME_CALL_META_OFFSET]
.L{p}call_add_owned:
    add x9, x9, w16, uxtw #4
    b .L{p}call_bytes_ready
.L{p}call_bytes_slow:
#endif
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x9, x13, x14
    add x9, x9, x16
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
// The actual C builder places an align16 local pointer table after the
// declared operand area. Reserve it before any quota/capacity commitment.
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    mov x15, #ARM_VAR_REF_POINTER_BYTES
    mul x12, x12, x15
    add x12, x12, #15
    and x12, x12, #-16
    add x9, x9, x12
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}call_bytes_ready:
#endif"""
        text = _replace_exact(text, old_arity, new_arity, 1, f"{p}call_arity_ready")

        old_vars = f""".L{p}call_owned_ready:
    mov x12, x23
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .L{p}call_locals_ready
.L{p}call_init_locals:"""
        new_vars = f""".L{p}call_owned_ready:
    mov x12, x23
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .L{p}call_locals_ready
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w13, #1
    b.ne .L{p}call_chk_var2
    stp xzr, x14, [x12], #16
    b .L{p}call_locals_ready
.L{p}call_chk_var2:
    cmp w13, #2
    b.ne .L{p}call_init_locals
    stp xzr, x14, [x12], #16
    stp xzr, x14, [x12], #16
    b .L{p}call_locals_ready
#endif
.L{p}call_init_locals:"""
        text = _replace_exact(text, old_vars, new_vars, 1, f"{p}call_owned_ready")

        old_prep = f"""    ldr x7, [x3, #ARM_OFF_JSObject_u_func_function_bytecode]
#if ARM_HAS_ARGUMENTS
    b .L{p}arguments_guard
#endif
.L{p}call_original_kind:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]"""
        fast_ready_tgt = ".Lrel_fast_call_ready" if not p else ".Lpub_fast_call_ready_tramp"
        rel_leaf_tgt = ".Lrel_fast_call_leaf_probe" if not p else ".Lpub_fast_call_leaf_tramp"
        new_prep = f"""    ldr x7, [x3, #ARM_OFF_JSObject_u_func_function_bytecode]
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
#ifndef QJS_AARCH64_VM_INSTRUMENT
    bic w14, w12, #0x30
    bic w14, w14, #0x02
    cmp w14, #0xc1
    b.eq {fast_ready_tgt}
    tbz x28, #62, .L{p}call_prep_not_dec
    tbz w12, #4, .L{p}call_prep_not_dec
    orr w12, w12, #192
    strb w12, [x7, #ARM_FRAME_KIND_OFFSET]
.L{p}call_prep_not_dec:
#endif
    tst w12, #1
#if ARM_HAS_ARGUMENTS
    b.eq .L{p}arguments_guard
#else
    b.eq .L{p}slow
#endif
#ifdef QJS_AARCH64_CALL_LEAVES
    tst w12, #64
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b.eq .L{p}fast_call_leaf_probe
#else
    b.eq {rel_leaf_tgt}
#endif
#endif
    b .L{p}call_admitted_kind
.L{p}call_original_kind:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
.L{p}call_admitted_kind:"""
        text = _replace_exact(text, old_prep, new_prep, 1, f"{p}call_prepare")

        old_quota = f""".L{p}call_quota_ready:
#ifdef QJS_AARCH64_CALL_LEAVES
    // x28 is the existing VM scratch register,not a data-frame field.
    // A decline restarts ordinary admission with original PC/SP/arguments.
    tbnz x28, #62, .L{p}call_leaf_original"""
        new_quota = f""".L{p}call_quota_ready:
#ifdef QJS_AARCH64_CALL_LEAVES
    // x28 is the existing VM scratch register,not a data-frame field.
    // A decline restarts ordinary admission with original PC/SP/arguments.
    tbnz x28, #62, .L{p}call_leaf_original
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    tst w12, #128
    b.ne .L{p}call_leaf_original"""
        text = _replace_exact(text, old_quota, new_quota, 1, f"{p}call_quota_ready")
        text = _replace_exact(
            text,
            f".L{p}call_leaf_original:\n\n#endif\n",
            f".L{p}call_leaf_original:\n"
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    bic x28, x28, #0x4000000000000000\n"
            "#endif\n"
            "#endif\n",
            1,
            f"{p}call_leaf_original clear x28 bit 62",
        )

        islands.append(
            f"""#ifdef QJS_AARCH64_VM_INSTRUMENT
#ifdef QJS_AARCH64_CALL_LEAVES
.L{p}fast_leaf_decline:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    b .L{p}call_admitted_kind
.L{p}fast_leaf_mark_inline_only:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    orr w14, w12, #64
    strb w14, [x7, #ARM_FRAME_KIND_OFFSET]
    b .L{p}call_admitted_kind
.L{p}fast_leaf_mark_nonleaf:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    orr w14, w12, #192
    strb w14, [x7, #ARM_FRAME_KIND_OFFSET]
    b .L{p}call_admitted_kind
.L{p}fast_call_leaf_probe:
    tst w12, #12
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldr w13, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w13, #30
    b.hi .L{p}fast_leaf_mark_nonleaf
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbnz w14, .L{p}fast_leaf_mark_nonleaf
    tbnz x28, #62, .L{p}fast_leaf_decline
    tbnz w17, #1, .L{p}fast_leaf_decline
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_module_loader_has_attr + 1)]
    cmp w15, #2
    b.eq .L{p}fast_leaf_decline
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 1)]
    cmp w15, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 3)]
    cmp w15, #2
    b.eq .L{p}fast_leaf_decline
    ldrb w15, [x14, #ARM_BIT_JSRuntime_dump_flags_BYTE]
    tst w15, #ARM_BIT_JSRuntime_dump_flags_MASK
    b.ne .L{p}fast_leaf_decline
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x16, [x7, #ARM_OFF_JSFunctionBytecode_realm]
    cmp x16, x15
    b.ne .L{p}fast_leaf_decline
    ldrh w16, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w0, w16
    b.lo .L{p}fast_leaf_decline
    ldr w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #1
    b.le .L{p}fast_leaf_decline
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x11, .L{p}fast_leaf_quota_ok
    ldr x10, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x11, x11, x10
    b.cs .L{p}fast_leaf_decline
    mov x10, #5280
    adds x11, x11, x10
    b.cs .L{p}fast_leaf_decline
    mov x10, sp
    cmp x10, x11
    b.lo .L{p}fast_leaf_decline
.L{p}fast_leaf_quota_ok:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    ldr x8, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldrh w9, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    cbnz w9, .L{p}fast_leaf_has_vars
    cmp w13, #2
    b.eq .L{p}fast_leaf_len2
    cmp w13, #4
    b.eq .L{p}fast_leaf_len4
    cmp w13, #1
    b.ne .L{p}fast_leaf_var0_other
    ldrb w10, [x8]
    cmp w10, #ARM_OP_return_undef
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #24, .L{p}fast_leaf_decline
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2:
    ldrb w11, [x8, #1]
    cmp w11, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #24, .L{p}fast_leaf_decline
    ldrb w10, [x8]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .L{p}fast_leaf_len2_nonint
    sub w5, w10, #ARM_OP_push_0
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2_nonint:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .L{p}fast_leaf_len2_nonarg
    cmp w11, w0
    b.hs .L{p}fast_leaf_decline
    add x11, x2, x11, lsl #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .L{p}fast_leaf_decline
    mov w13, #5
    tbz x6, #63, .L{p}fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2_nonarg:
    cmp w10, #ARM_OP_undefined
    b.ne .L{p}fast_leaf_len2_not_undef
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2_not_undef:
    cmp w10, #ARM_OP_null
    b.ne .L{p}fast_leaf_len2_not_null
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_NULL
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2_not_null:
    sub w11, w10, #ARM_OP_push_false
    cmp w11, #1
    b.hi .L{p}fast_leaf_len2_not_bool
    mov w5, w11
    mov x6, #ARM_CONST_JS_TAG_BOOL
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len2_not_bool:
    sub w11, w10, #ARM_OP_get_var_ref0
    cmp w11, #3
    b.hi .L{p}fast_leaf_mark_nonleaf
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cmp w11, w14
    b.hs .L{p}fast_leaf_mark_nonleaf
    ldr x14, [x3, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x14, [x14, x11, lsl #3]
    ldr x14, [x14, #ARM_OFF_JSVarRef_pvalue]
    ldp x5, x6, [x14]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .L{p}fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .L{p}fast_leaf_decline
    mov w13, #5
    tbz x6, #63, .L{p}fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4:
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_return_undef
    b.eq .L{p}fast_leaf_len4_closure
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.ne .L{p}fast_leaf_len4_ext
#else
    b.ne .L{p}fast_leaf_mark_inline_only
#endif
    ldrb w10, [x8]
    sub w10, w10, #ARM_OP_get_arg0
    cmp w10, #3
    b.hi .L{p}fast_leaf_mark_inline_only
    tbz w14, #24, .L{p}fast_leaf_decline
    cmp w10, w0
    b.hs .L{p}fast_leaf_decline
    add x10, x2, x10, lsl #4
    ldp x9, x11, [x10]
    cbnz x11, .L{p}fast_leaf_decline
    ldrb w10, [x8, #1]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .L{p}fast_leaf_len4_add_arg
    sub w11, w10, #ARM_OP_push_0
    b .L{p}fast_leaf_len4_add_do
.L{p}fast_leaf_len4_add_arg:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .L{p}fast_leaf_mark_inline_only
    cmp w11, w0
    b.hs .L{p}fast_leaf_decline
    add x11, x2, x11, lsl #4
    ldr x14, [x11, #8]
    cbnz x14, .L{p}fast_leaf_decline
    ldr w11, [x11]
.L{p}fast_leaf_len4_add_do:
    adds w5, w9, w11
    b.vs .L{p}fast_leaf_decline
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_closure:
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_var_ref0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_put_var_ref0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_inc
    b.eq .L{p}fast_leaf_closure_step
    cmp w10, #ARM_OP_dec
    b.ne .L{p}fast_leaf_mark_nonleaf
.L{p}fast_leaf_closure_step:
    tbz w14, #24, .L{p}fast_leaf_decline
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbz w14, .L{p}fast_leaf_mark_nonleaf
    ldr x14, [x3, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x14, [x14]
    ldrb w11, [x14, #ARM_OFF_JSVarRef_is_const]
    cbnz w11, .L{p}fast_leaf_decline
    ldr x14, [x14, #ARM_OFF_JSVarRef_pvalue]
    ldp x9, x11, [x14]
    cbnz x11, .L{p}fast_leaf_decline
    cmp w10, #ARM_OP_inc
    b.ne .L{p}fast_leaf_closure_dec
    adds w9, w9, #1
    b.vs .L{p}fast_leaf_decline
    b .L{p}fast_leaf_closure_store
.L{p}fast_leaf_closure_dec:
    subs w9, w9, #1
    b.vs .L{p}fast_leaf_decline
.L{p}fast_leaf_closure_store:
    sxtw x9, w9
    str x9, [x14]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    mov w13, #5
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_var0_other:
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w13, #6
    b.eq .L{p}fast_leaf_len6
    cmp w13, #8
    b.eq .L{p}fast_leaf_len8
    cmp w13, #30
    b.eq .L{p}fast_leaf_len30
#endif
    cmp w13, #14
    b.eq .L{p}fast_leaf_check_14
    cmp w13, #22
    b.eq .L{p}fast_leaf_check_ret_end
    cmp w13, #30
    b.eq .L{p}fast_leaf_check_ret_end
    cmp w13, #16
    b.hi .L{p}fast_leaf_mark_nonleaf
.L{p}fast_leaf_check_ret_end:
    sub w10, w13, #1
    ldrb w10, [x8, x10]
    cmp w10, #ARM_OP_return
    b.eq .L{p}fast_leaf_mark_inline_only
    b .L{p}fast_leaf_mark_nonleaf
.L{p}fast_leaf_check_14:
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_return
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.eq .L{p}fast_leaf_cmp14
#else
    b.eq .L{p}fast_leaf_mark_inline_only
#endif
    cmp w10, #ARM_OP_return_undef
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cmp w10, #1
    b.eq .L{p}fast_leaf_mark_inline_only
    b .L{p}fast_leaf_mark_nonleaf
.L{p}fast_leaf_has_vars:
    cmp w9, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    cmp w13, #9
    b.eq .L{p}fast_leaf_getter9
    cmp w13, #10
    b.eq .L{p}fast_leaf_setter10
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w13, #11
    b.eq .L{p}fast_leaf_at11
    cmp w13, #18
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cmp w10, #1
    b.eq .L{p}fast_leaf_mark_inline_only
    b .L{p}fast_leaf_mark_nonleaf
#else
    cmp w13, #18
    b.eq .L{p}fast_leaf_mark_inline_only
    b .L{p}fast_leaf_mark_nonleaf
#endif
.L{p}fast_leaf_getter9:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    orr w10, w10, w11
    cbnz w10, .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #25, .L{p}fast_leaf_decline
    tbz w14, #26, .L{p}fast_leaf_decline
    tbz w17, #0, .L{p}fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_getter9_loop:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .L{p}fast_leaf_getter9_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_getter9_loop
.L{p}fast_leaf_getter9_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .L{p}fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .L{p}fast_leaf_decline
    mov w13, #3
    tbz x6, #63, .L{p}fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_setter10:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cbz w10, .L{p}fast_leaf_size10
#endif
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #4]
    cmp w10, #ARM_OP_put_field
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_return_undef
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #25, .L{p}fast_leaf_decline
    tbz w14, #26, .L{p}fast_leaf_decline
    tbz w17, #0, .L{p}fast_leaf_decline
    cbz w0, .L{p}fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldur w10, [x8, #5]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_setter10_loop:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .L{p}fast_leaf_setter10_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_setter10_loop
.L{p}fast_leaf_setter10_found:
    ldr w5, [x13]
    mov w6, #ARM_PROPERTY_DESC_WRITE_MASK
    and w5, w5, w6
    mov w6, #ARM_PROPERTY_DESC_WRITABLE
    cmp w5, w6
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x13, x14, [x11]
    tbz x14, #63, .L{p}fast_leaf_setter10_old_ok
    ldr w5, [x13, #ARM_REF_COUNT_OFFSET]
    cmp w5, #1
    b.le .L{p}fast_leaf_decline
    cmp x13, x9
    b.ne .L{p}fast_leaf_setter10_old_ok
    cmp w5, #2
    b.le .L{p}fast_leaf_decline
.L{p}fast_leaf_setter10_old_ok:
    ldp x5, x6, [x2]
    tbz x6, #63, .L{p}fast_leaf_setter10_new_ok
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_setter10_new_ok:
    tbz x14, #63, .L{p}fast_leaf_setter10_write
    ldr w10, [x13, #ARM_REF_COUNT_OFFSET]
    sub w10, w10, #1
    str w10, [x13, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_setter10_write:
    stp x5, x6, [x11]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    mov w13, #3
    b .L{p}fast_leaf_commit
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_leaf_len4_ext:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_inline_only
    cmp w10, #ARM_OP_sub
    b.eq .L{p}fast_leaf_len4_ops_ok
    cmp w10, #ARM_OP_mul
    b.eq .L{p}fast_leaf_len4_ops_ok
    sub w11, w10, #ARM_OP_shl
    cmp w11, #(ARM_OP_or - ARM_OP_shl)
    b.ls .L{p}fast_leaf_len4_ops_ok
    sub w11, w10, #ARM_OP_lt
    cmp w11, #(ARM_OP_strict_neq - ARM_OP_lt)
    b.hi .L{p}fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_gte + 1)
    b.eq .L{p}fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_eq - 1)
    b.eq .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len4_ops_ok:
    ldrb w11, [x8]
    sub w12, w11, #ARM_OP_get_arg0
    cmp w12, #3
    b.ls .L{p}fast_leaf_len4_op0_ok
    sub w12, w11, #ARM_OP_push_minus1
    cmp w12, #8
    b.hi .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len4_op0_ok:
    ldrb w12, [x8, #1]
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.ls .L{p}fast_leaf_len4_op1_ok
    sub w13, w12, #ARM_OP_push_minus1
    cmp w13, #8
    b.hi .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len4_op1_ok:
    tbz w14, #24, .L{p}fast_leaf_decline
    sub w13, w11, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .L{p}fast_leaf_len4_p0_lit
    cmp w13, w0
    b.hs .L{p}fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x9, x14, [x13]
    cbnz x14, .L{p}fast_leaf_decline
    b .L{p}fast_leaf_len4_load1
.L{p}fast_leaf_len4_p0_lit:
    sub w9, w11, #ARM_OP_push_0
.L{p}fast_leaf_len4_load1:
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .L{p}fast_leaf_len4_p1_lit
    cmp w13, w0
    b.hs .L{p}fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x11, x14, [x13]
    cbnz x14, .L{p}fast_leaf_decline
    b .L{p}fast_leaf_len4_eval
.L{p}fast_leaf_len4_p1_lit:
    sub w11, w12, #ARM_OP_push_0
.L{p}fast_leaf_len4_eval:
    mov w13, #6
    cmp w10, #ARM_OP_sub
    b.ne .L{p}fast_leaf_len4_not_sub
    subs w5, w9, w11
    b.vs .L{p}fast_leaf_decline
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_sub:
    cmp w10, #ARM_OP_mul
    b.ne .L{p}fast_leaf_len4_not_mul
    smull x5, w9, w11
    cmp x5, w5, sxtw
    b.ne .L{p}fast_leaf_decline
    cbnz x5, .L{p}fast_leaf_len4_mul_ok
    orr w12, w9, w11
    tbnz w12, #31, .L{p}fast_leaf_decline
.L{p}fast_leaf_len4_mul_ok:
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_mul:
    cmp w10, #ARM_OP_shl
    b.ne .L{p}fast_leaf_len4_not_shl
    and w11, w11, #31
    lsl w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_shl:
    cmp w10, #ARM_OP_sar
    b.ne .L{p}fast_leaf_len4_not_sar
    and w11, w11, #31
    asr w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_sar:
    cmp w10, #ARM_OP_shr
    b.ne .L{p}fast_leaf_len4_not_shr
    and w11, w11, #31
    lsr w5, w9, w11
    tbnz w5, #31, .L{p}fast_leaf_decline
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_shr:
    cmp w10, #ARM_OP_and
    b.ne .L{p}fast_leaf_len4_not_and
    and w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_and:
    cmp w10, #ARM_OP_xor
    b.ne .L{p}fast_leaf_len4_not_xor
    eor w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_not_xor:
    cmp w10, #ARM_OP_or
    b.ne .L{p}fast_leaf_len4_cmp
    orr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len4_cmp:
    cmp w10, #ARM_OP_lt
    b.eq .L{p}fast_leaf_cmp_lt
    cmp w10, #ARM_OP_lte
    b.eq .L{p}fast_leaf_cmp_le
    cmp w10, #ARM_OP_gt
    b.eq .L{p}fast_leaf_cmp_gt
    cmp w10, #ARM_OP_gte
    b.eq .L{p}fast_leaf_cmp_ge
    cmp w10, #ARM_OP_eq
    b.eq .L{p}fast_leaf_cmp_eq
    cmp w10, #ARM_OP_strict_eq
    b.eq .L{p}fast_leaf_cmp_eq
    b .L{p}fast_leaf_cmp_ne
.L{p}fast_leaf_cmp_lt:
    cmp w9, w11
    cset w5, lt
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_cmp_le:
    cmp w9, w11
    cset w5, le
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_cmp_gt:
    cmp w9, w11
    cset w5, gt
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_cmp_ge:
    cmp w9, w11
    cset w5, ge
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_cmp_eq:
    cmp w9, w11
    cset w5, eq
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_cmp_ne:
    cmp w9, w11
    cset w5, ne
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .L{p}fast_leaf_commit

.L{p}fast_leaf_size10:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_length
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #13, .L{p}fast_leaf_decline
    tbz w14, #25, .L{p}fast_leaf_decline
    tbz w14, #26, .L{p}fast_leaf_decline
    tbz w17, #0, .L{p}fast_leaf_decline
#ifdef QJS_AARCH64_VM_INSTRUMENT
    adrp x10, JS_FrameLengthData
    add x10, x10, :lo12:JS_FrameLengthData
    ldarb w10, [x10]
    cmp w10, #1
    b.ne .L{p}fast_leaf_decline
#else
    tbz w14, #29, .L{p}fast_leaf_decline
#endif
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_size10_loop:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .L{p}fast_leaf_size10_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_size10_loop
.L{p}fast_leaf_size10_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x11, x12, [x11]
    cmn x12, #1
    b.ne .L{p}fast_leaf_decline
    ldrh w13, [x11, #ARM_OFF_JSObject_class_id]
    cmp w13, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .L{p}fast_leaf_decline
    ldrb w13, [x11, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w13, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .L{p}fast_leaf_decline
    ldr x12, [x11, #ARM_OFF_JSObject_prop]
    ldp x5, x6, [x12, #ARM_OFF_JSProperty_u_value]
    cmp x6, #ARM_CONST_JS_TAG_INT
    b.eq .L{p}fast_leaf_size10_ok
    cmp x6, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}fast_leaf_decline
.L{p}fast_leaf_size10_ok:
    mov w13, #3
    b .L{p}fast_leaf_commit

.L{p}fast_leaf_at11:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_get_array_el
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #10]
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    tbz w14, #25, .L{p}fast_leaf_decline
    tbz w14, #26, .L{p}fast_leaf_decline
    tbz w17, #0, .L{p}fast_leaf_decline
    cbz w0, .L{p}fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_at11_loop:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .L{p}fast_leaf_at11_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_at11_loop
.L{p}fast_leaf_at11_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x11, x12, [x11]
    cmn x12, #1
    b.ne .L{p}fast_leaf_decline
    ldrh w13, [x11, #ARM_OFF_JSObject_class_id]
    cmp w13, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .L{p}fast_leaf_decline
    ldrb w13, [x11, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w13, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .L{p}fast_leaf_decline
    ldp x5, x6, [x2]
    cbnz x6, .L{p}fast_leaf_decline
    tbnz w5, #31, .L{p}fast_leaf_decline
    ldr w13, [x11, #ARM_OFF_JSObject_u_array_count]
    cmp w5, w13
    b.hs .L{p}fast_leaf_decline
    ldr x13, [x11, #ARM_OFF_JSObject_u_array_u_values]
    add x13, x13, w5, uxtw #4
    ldp x5, x6, [x13]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .L{p}fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .L{p}fast_leaf_decline
    tbz x6, #63, .L{p}fast_leaf_at11_ok
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_at11_ok:
    mov w13, #3
    b .L{p}fast_leaf_commit

.L{p}fast_leaf_cmp14:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #2
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_field
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #6]
    cmp w10, #ARM_OP_get_arg1
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #7]
    cmp w10, #ARM_OP_get_field
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #12]
    sub w11, w10, #ARM_OP_lt
    cmp w11, #(ARM_OP_strict_neq - ARM_OP_lt)
    b.hi .L{p}fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_gte + 1)
    b.eq .L{p}fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_eq - 1)
    b.eq .L{p}fast_leaf_mark_inline_only
    tbz w14, #24, .L{p}fast_leaf_decline
    tbz w14, #25, .L{p}fast_leaf_decline
    cmp w0, #2
    b.lo .L{p}fast_leaf_decline
    ldp x9, x11, [x2]
    cmn x11, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w12, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w12, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldp x5, x6, [x2, #16]
    cmn x6, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w12, [x5, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w12, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}fast_leaf_decline
    ldur w10, [x8, #2]
    ldr x12, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x12, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x12, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x12, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_cmp14_loop0:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w6, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w6, w10
    b.eq .L{p}fast_leaf_cmp14_found0
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_cmp14_loop0
.L{p}fast_leaf_cmp14_found0:
    ldr w6, [x13]
    tst w6, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x6, x13, [x11]
    cbnz x13, .L{p}fast_leaf_decline
    ldur w11, [x8, #8]
    ldr x9, [x5, #ARM_OFF_JSObject_shape]
    cmp x9, x12
    b.ne .L{p}fast_leaf_cmp14_slow1
    cmp w11, w10
    b.eq .L{p}fast_leaf_cmp14_got1
.L{p}fast_leaf_cmp14_slow1:
    ldr w14, [x9, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w11, w14
    neg x14, x14
    add x14, x9, x14, lsl #2
    ldur w14, [x14, #-4]
    add x12, x9, #ARM_OFF_JSShape_prop
.L{p}fast_leaf_cmp14_loop1:
    cbz w14, .L{p}fast_leaf_decline
    sub w13, w14, #1
    add x13, x12, x13, lsl #3
    ldr w10, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w10, w11
    b.eq .L{p}fast_leaf_cmp14_found1
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_leaf_cmp14_loop1
.L{p}fast_leaf_cmp14_found1:
    ldr w10, [x13]
    tst w10, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_leaf_decline
    sub w14, w14, #1
.L{p}fast_leaf_cmp14_got1:
    ldr x10, [x5, #ARM_OFF_JSObject_prop]
    add x10, x10, x14, lsl #4
    ldp x10, x11, [x10]
    cbnz x11, .L{p}fast_leaf_decline
    mov w9, w6
    mov w11, w10
    ldrb w10, [x8, #12]
    mov w13, #6
    b .L{p}fast_leaf_len4_cmp
#endif
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_call_ready:
    ldrh w9, [x7, #ARM_FRAME_CALL_META_OFFSET]
    cbz w9, .L{p}call_admitted_kind
    ldrb w14, [x7, #ARM_FRAME_CALL_FORMALS_OFFSET]
    cmp w0, w14
    b.lo .L{p}call_admitted_kind
    ldrb w13, [x7, #ARM_FRAME_CALL_LOCALS_OFFSET]
    ldr x8, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x10, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_capacity]
    subs x12, x12, x10
    b.lo .L{p}slow
    cmp x12, x9
    b.lo .L{p}slow
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .L{p}fcr_quota_ok
    ldr x15, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x15, x15, x9
    b.cs .L{p}slow
    adds x12, x12, x15
    b.cs .L{p}slow
    adds x12, x12, #4096
    b.cs .L{p}slow
    mov x15, sp
    cmp x15, x12
    b.lo .L{p}slow
.L{p}fcr_quota_ok:
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    subs w12, w12, #1
    b.le .L{p}slow
    str w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    and w12, w17, #1
    add w12, w12, w0
    add w12, w12, #1
    tbz w17, #1, .L{p}fcr_pending
    orr w12, w12, #0x8000
.L{p}fcr_pending:
    strh w12, [x22, #ARM_OFF_JSFrame_pending]
    add x14, x10, x9
    str x14, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_data]
    add x10, x10, x12
    add x23, x10, #ARM_FRAME_HEADER_BYTES
    mov x24, x2
    stp x22, x3, [x10]
    stp x4, x24, [x10, #16]
    stp x23, xzr, [x10, #32]
    str xzr, [x10, #48]
    strh wzr, [x10, #56]
    strh w0, [x10, #58]
    ldrb w12, [x7, #ARM_STRICT_BYTE]
    and w12, w12, #ARM_STRICT_MASK
    lsr w12, w12, #ARM_STRICT_SHIFT
    str w12, [x10, #60]
    str xzr, [x10, #64]
    str x7, [x10, #80]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    tbz w17, #0, .L{p}fcr_this
    ldp x5, x6, [x2, #-32]
.L{p}fcr_this:
    stp x5, x6, [x10, #88]
    stp xzr, x8, [x10, #104]
    str x9, [x10, #120]
    mov x12, x23
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .L{p}fcr_locals_done
    cmp w13, #1
    b.ne .L{p}fcr_chk_v2
    stp xzr, x14, [x12], #16
    b .L{p}fcr_locals_done
.L{p}fcr_chk_v2:
    cmp w13, #2
    b.ne .L{p}fcr_vloop
    stp xzr, x14, [x12], #16
    stp xzr, x14, [x12], #16
    b .L{p}fcr_locals_done
.L{p}fcr_vloop:
    stp xzr, x14, [x12], #16
    subs w13, w13, #1
    b.ne .L{p}fcr_vloop
.L{p}fcr_locals_done:
    mov x21, x12
    ldr x20, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x12, x12, x9
    str x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    str x10, [x19, #ARM_OFF_JSFrameRegisterState_frame]
"""
            + (
                """    adrp x25, .Lfast_dirty_ptrs
    add x25, x25, :lo12:.Lfast_dirty_ptrs
"""
                if p == "pub_"
                else """    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x10, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
"""
            )
            + f"""    mov x22, x10
    mov x26, x7
    mov x27, #0
    ARM_DISPATCH_NEXT 1

.L{p}fast_leaf_len6:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_push_0
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #4]
    cmp w10, #ARM_OP_or
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #5]
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
    b.eq .L{p}fast_leaf_len6_op_ok
    cmp w10, #ARM_OP_sub
    b.eq .L{p}fast_leaf_len6_op_ok
    cmp w10, #ARM_OP_mul
    b.eq .L{p}fast_leaf_len6_op_ok
    sub w11, w10, #ARM_OP_shl
    cmp w11, #(ARM_OP_or - ARM_OP_shl)
    b.hi .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len6_op_ok:
    ldrb w11, [x8]
    sub w12, w11, #ARM_OP_get_arg0
    cmp w12, #3
    b.ls .L{p}fast_leaf_len6_p0_ok
    sub w12, w11, #ARM_OP_push_minus1
    cmp w12, #8
    b.hi .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len6_p0_ok:
    ldrb w12, [x8, #1]
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.ls .L{p}fast_leaf_len6_p1_ok
    sub w13, w12, #ARM_OP_push_minus1
    cmp w13, #8
    b.hi .L{p}fast_leaf_mark_inline_only
.L{p}fast_leaf_len6_p1_ok:
    tbz w14, #24, .L{p}fast_leaf_decline
    tbz w14, #21, .L{p}fast_leaf_decline
    sub w13, w11, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .L{p}fast_leaf_len6_p0_lit
    cmp w13, w0
    b.hs .L{p}fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x9, x14, [x13]
    cbnz x14, .L{p}fast_leaf_decline
    b .L{p}fast_leaf_len6_load1
.L{p}fast_leaf_len6_p0_lit:
    sub w9, w11, #ARM_OP_push_0
.L{p}fast_leaf_len6_load1:
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .L{p}fast_leaf_len6_p1_lit
    cmp w13, w0
    b.hs .L{p}fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x11, x14, [x13]
    cbnz x14, .L{p}fast_leaf_decline
    b .L{p}fast_leaf_len6_eval
.L{p}fast_leaf_len6_p1_lit:
    sub w11, w12, #ARM_OP_push_0
.L{p}fast_leaf_len6_eval:
    mov w13, #6
    cmp w10, #ARM_OP_add
    b.ne .L{p}fast_leaf_len6_not_add
    add w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_add:
    cmp w10, #ARM_OP_sub
    b.ne .L{p}fast_leaf_len6_not_sub
    sub w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_sub:
    cmp w10, #ARM_OP_mul
    b.ne .L{p}fast_leaf_len6_bitop
    smull x5, w9, w11
    cmp x5, w5, sxtw
    b.ne .L{p}fast_leaf_decline
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_bitop:
    cmp w10, #ARM_OP_shl
    b.ne .L{p}fast_leaf_len6_not_shl
    and w11, w11, #31
    lsl w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_shl:
    cmp w10, #ARM_OP_sar
    b.ne .L{p}fast_leaf_len6_not_sar
    and w11, w11, #31
    asr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_sar:
    cmp w10, #ARM_OP_shr
    b.ne .L{p}fast_leaf_len6_not_shr
    and w11, w11, #31
    lsr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_shr:
    cmp w10, #ARM_OP_and
    b.ne .L{p}fast_leaf_len6_not_and
    and w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_not_and:
    cmp w10, #ARM_OP_xor
    b.ne .L{p}fast_leaf_len6_or
    eor w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len6_or:
    orr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .L{p}fast_leaf_commit

.L{p}fast_leaf_len8:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_arg1
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w10, [x8, #3]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .L{p}fast_leaf_mark_inline_only
    ldrb w11, [x8, #4]
    cmp w11, #ARM_OP_add
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w11, [x8, #5]
    cmp w11, #ARM_OP_push_0
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w11, [x8, #6]
    cmp w11, #ARM_OP_or
    b.ne .L{p}fast_leaf_mark_inline_only
    ldrb w11, [x8, #7]
    cmp w11, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_inline_only
    tbz w14, #24, .L{p}fast_leaf_decline
    tbz w14, #25, .L{p}fast_leaf_decline
    cmp w0, #2
    b.lo .L{p}fast_leaf_decline
    ldp x9, x12, [x2]
    cbnz x12, .L{p}fast_leaf_decline
    ldp x11, x12, [x2, #16]
    cbnz x12, .L{p}fast_leaf_decline
    add w5, w9, w11
    sub w10, w10, #ARM_OP_push_0
    add w5, w5, w10
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    mov w13, #1
    b .L{p}fast_leaf_commit

.L{p}fast_leaf_len30:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .L{p}fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    cmp w10, #2
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldr w10, [x7, #ARM_OFF_JSFunctionBytecode_cpool_count]
    cbnz w10, .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #6]
    cmp w10, #ARM_OP_eq
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #7]
    cmp w10, #ARM_OP_dup
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_if_true8
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #20
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #10]
    cmp w10, #ARM_OP_drop
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #11]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #12]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #17]
    cmp w10, #ARM_OP_eq
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #18]
    cmp w10, #ARM_OP_dup
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #19]
    cmp w10, #ARM_OP_if_true8
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #20]
    cmp w10, #9
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #21]
    cmp w10, #ARM_OP_drop
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #22]
    cmp w10, #ARM_OP_get_arg0
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #23]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #28]
    cmp w10, #ARM_OP_eq
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x8, #29]
    cmp w10, #ARM_OP_return
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x11, #ARM_OFF_JSRuntime_atom_array]
    ldur w10, [x8, #2]
    tbnz w10, #31, .L{p}fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w5, [x9, #ARM_SIZE_JSString]
    ldur w10, [x8, #13]
    tbnz w10, #31, .L{p}fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w6, [x9, #ARM_SIZE_JSString]
    ldur w10, [x8, #24]
    tbnz w10, #31, .L{p}fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .L{p}fast_leaf_mark_nonleaf
    ldrb w13, [x9, #ARM_SIZE_JSString]
    tbz w14, #24, .L{p}fast_leaf_decline
    tbz w14, #22, .L{p}fast_leaf_decline
    cbz w0, .L{p}fast_leaf_decline
    cmp w16, #3
    b.le .L{p}fast_leaf_decline
    ldp x9, x10, [x2]
    cmp x10, #ARM_CONST_JS_TAG_STRING
    b.ne .L{p}fast_leaf_decline
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .L{p}fast_leaf_decline
    ldrb w10, [x9, #11]
    tst w10, #0x30
    b.ne .L{p}fast_leaf_decline
    ldrb w14, [x9, #ARM_SIZE_JSString]
    cmp w14, w5
    b.ne .L{p}fast_leaf_len30_c12
    sub w16, w16, #1
    mov x5, #1
    mov x6, #ARM_CONST_JS_TAG_BOOL
    mov w13, #7
    b .L{p}fast_leaf_commit
.L{p}fast_leaf_len30_c12:
    sub w16, w16, #2
    cmp w14, w6
    cset w5, eq
    cmp w14, w13
    cset w9, eq
    orr w5, w5, w9
    mov x6, #ARM_CONST_JS_TAG_BOOL
    mov w13, #7
    b .L{p}fast_leaf_commit
#endif

.L{p}fast_leaf_commit:
    sub w16, w16, #1
    str w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x10, tpidr_el0
    add x10, x10, :tprel_hi12:qjs_aarch64_call_leaf_counters
    add x10, x10, :tprel_lo12_nc:qjs_aarch64_call_leaf_counters
    ldr x11, [x10, x13, lsl #3]
    add x11, x11, #1
    str x11, [x10, x13, lsl #3]
    ldr x11, [x10, #80]
    add x11, x11, #1
    str x11, [x10, #80]
#endif
    and w9, w17, #1
    add w9, w9, w0
    add w9, w9, #1
.L{p}fast_leaf_pop_entry:
#ifndef QJS_AARCH64_VM_INSTRUMENT
    tbnz w17, #1, .L{p}fast_leaf_tail_ret
    cmp w9, #1
    b.eq .L{p}fast_leaf_pop1
    cmp w9, #2
    b.eq .L{p}fast_leaf_pop2
#endif
    cmp w9, #8
    b.hi .L{p}fast_leaf_host_return
    sub x12, x21, x9, lsl #4
    mov x13, x12
.L{p}fast_leaf_guard_loop:
    cmp x13, x21
    b.eq .L{p}fast_leaf_release_start
    ldp x10, x11, [x13], #16
    tbz x11, #63, .L{p}fast_leaf_guard_loop
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, w9
    b.le .L{p}fast_leaf_host_return
    b .L{p}fast_leaf_guard_loop
.L{p}fast_leaf_release_start:
    mov x13, x12
.L{p}fast_leaf_release_loop:
    cmp x13, x21
    b.eq .L{p}fast_leaf_popped
    ldp x10, x11, [x13], #16
    tbz x11, #63, .L{p}fast_leaf_release_loop
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    sub w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
    b .L{p}fast_leaf_release_loop
.L{p}fast_leaf_popped:
    stp x5, x6, [x12]
    add x21, x12, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_leaf_pop1:
    sub x12, x21, #16
    ldp x10, x11, [x12]
    tbz x11, #63, .L{p}fast_leaf_pop1_done
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .L{p}fast_leaf_host_return
    sub w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_pop1_done:
    stp x5, x6, [x12]
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.L{p}fast_leaf_pop2:
    sub x12, x21, #32
    ldp x10, x11, [x12]
    ldp x13, x14, [x12, #16]
    tbz x11, #63, .L{p}fast_leaf_pop2_chk1
    ldr w8, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w8, #2
    b.le .L{p}fast_leaf_host_return
.L{p}fast_leaf_pop2_chk1:
    tbz x14, #63, .L{p}fast_leaf_pop2_rel0
    ldr w15, [x13, #ARM_REF_COUNT_OFFSET]
    cmp w15, #2
    b.le .L{p}fast_leaf_host_return
.L{p}fast_leaf_pop2_rel0:
    tbz x11, #63, .L{p}fast_leaf_pop2_rel1
    sub w8, w8, #1
    str w8, [x10, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_pop2_rel1:
    tbz x14, #63, .L{p}fast_leaf_pop2_done
    ldr w15, [x13, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    str w15, [x13, #ARM_REF_COUNT_OFFSET]
.L{p}fast_leaf_pop2_done:
    stp x5, x6, [x12]
    add x21, x12, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.L{p}fast_leaf_tail_ret:
    orr w9, w9, #0x8000
#endif
.L{p}fast_leaf_host_return:
    mov x20, x1
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    strh w9, [x22, #ARM_OFF_JSFrame_pending]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #128]
    add x14, x14, #1
    str x14, [sp, #128]
#endif
    mov x0, x5
    mov x1, x6
    b .L{p}host_return
#endif
#endif
"""
        )

    islands.append("""#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lpub_fast_call_ready_tramp:
    orr w17, w17, #4
    b .Lrel_fast_call_ready
.Lpub_fast_call_leaf_tramp:
    orr w17, w17, #4
    b .Lrel_fast_call_leaf_probe
.Lrel_fcf_fallback:
    tst w17, #4
    b.eq .Lcall_forward_probe_orig
    bic w17, w17, #4
    b .Lpub_call_forward_probe_orig
.Lrel_call_admitted_back:
    tst w17, #4
    b.eq .Lcall_admitted_kind
    bic w17, w17, #4
    b .Lpub_call_admitted_kind
.Lrel_call_slow_back:
    tst w17, #4
    b.eq .Lslow
    bic w17, w17, #4
    b .Lpub_slow

.Lrel_fast_call_forward_leaf:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #19, .Lrel_fcf_fallback
    ldrb w10, [x26, #ARM_FORWARD_MODE_OFFSET]
    cmp w10, #1
    b.hi .Lrel_fcf_fallback
    tbz w17, #0, .Lrel_fcf_fallback
    mov w15, #32765
    cmp w0, w15
    b.hi .Lrel_fcf_fallback
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x11, #(ARM_OFF_JSRuntime_module_loader_has_attr + 1)]
    cmp w15, #2
    b.eq .Lrel_fcf_fallback
    ldrb w15, [x11, #(ARM_OFF_JSRuntime_current_stack_frame - 1)]
    cmp w15, #1
    b.ne .Lrel_fcf_fallback
    ldrb w15, [x11, #(ARM_OFF_JSRuntime_current_stack_frame - 3)]
    cmp w15, #2
    b.eq .Lrel_fcf_fallback
    ldrb w15, [x11, #ARM_BIT_JSRuntime_dump_flags_BYTE]
    tst w15, #ARM_BIT_JSRuntime_dump_flags_MASK
    b.ne .Lrel_fcf_fallback
    ldp x7, x10, [x2, #-32]
    cmn x10, #1
    b.ne .Lrel_fcf_fallback
    ldrh w10, [x7, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION
    b.ne .Lrel_fcf_fallback
    ldr x7, [x7, #ARM_OFF_JSObject_u_func_function_bytecode]
    ldrb w10, [x7, #ARM_FRAME_KIND_OFFSET]
    tbz w10, #0, .Lrel_fcf_fallback
    tst w10, #12
    b.ne .Lrel_fcf_fallback
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbnz w10, .Lrel_fcf_fallback
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .Lrel_fcf_fallback
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x10, [x3, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x10, x15
    b.ne .Lrel_fcf_fallback
    ldr x10, [x7, #ARM_OFF_JSFunctionBytecode_realm]
    cmp x10, x15
    b.ne .Lrel_fcf_fallback
    ldr w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #2
    b.le .Lrel_fcf_fallback
    ldr x10, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x12, [x10, #ARM_OFF_JSFrameSegment_capacity]
    ldr x10, [x10, #ARM_OFF_JSFrameSegment_used]
    sub x12, x12, x10
    cmp x12, #512
    b.lo .Lrel_fcf_fallback
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .Lrel_fcf_quota_ok
    ldr x10, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x12, x12, x10
    b.cs .Lrel_fcf_fallback
    mov x10, #5600
    adds x12, x12, x10
    b.cs .Lrel_fcf_fallback
    mov x10, sp
    cmp x10, x12
    b.lo .Lrel_fcf_fallback
.Lrel_fcf_quota_ok:
    subs w4, w0, #1
    csel w4, w4, wzr, hs
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w4, w10
    b.lo .Lrel_fcf_fallback
    ldr x8, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr w13, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    ldrh w9, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    cbnz w9, .Lrel_fcf_var1
    tbz w14, #24, .Lrel_fcf_fallback
    cmp w13, #1
    b.ne .Lrel_fcf_v0_n1
    ldrb w10, [x8]
    cmp w10, #ARM_OP_return_undef
    b.ne .Lrel_fcf_fallback
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fcf_commit
.Lrel_fcf_v0_n1:
    cmp w13, #2
    b.ne .Lrel_fcf_v0_len4
    ldrb w11, [x8, #1]
    cmp w11, #ARM_OP_return
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .Lrel_fcf_len2_nonint
    sub w5, w10, #ARM_OP_push_0
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fcf_commit
.Lrel_fcf_len2_nonint:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .Lrel_fcf_len2_nonarg
    cmp w11, w4
    b.hs .Lrel_fcf_fallback
    add x11, x2, x11, lsl #4
    ldp x5, x6, [x11, #16]
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fcf_fallback
    tbz x6, #63, .Lrel_fcf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fcf_commit
.Lrel_fcf_len2_nonarg:
    cmp w10, #ARM_OP_undefined
    b.ne .Lrel_fcf_len2_null
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fcf_commit
.Lrel_fcf_len2_null:
    cmp w10, #ARM_OP_null
    b.ne .Lrel_fcf_len2_bool
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_NULL
    b .Lrel_fcf_commit
.Lrel_fcf_len2_bool:
    sub w11, w10, #ARM_OP_push_false
    cmp w11, #1
    b.hi .Lrel_fcf_fallback
    mov w5, w11
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fcf_commit
.Lrel_fcf_v0_len4:
    cmp w13, #4
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fcf_fallback
    ldrb w12, [x8, #2]
    cmp w12, #ARM_OP_add
    b.eq .Lrel_fcf_len4_opok
    cmp w12, #ARM_OP_sub
    b.ne .Lrel_fcf_fallback
.Lrel_fcf_len4_opok:
    ldrb w10, [x8]
    sub w10, w10, #ARM_OP_get_arg0
    cmp w10, #3
    b.hi .Lrel_fcf_fallback
    cmp w10, w4
    b.hs .Lrel_fcf_fallback
    add x10, x2, x10, lsl #4
    ldp x9, x11, [x10, #16]
    cbnz x11, .Lrel_fcf_fallback
    ldrb w10, [x8, #1]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .Lrel_fcf_len4_arg1
    sub w11, w10, #ARM_OP_push_0
    b .Lrel_fcf_len4_calc
.Lrel_fcf_len4_arg1:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .Lrel_fcf_fallback
    cmp w11, w4
    b.hs .Lrel_fcf_fallback
    add x11, x2, x11, lsl #4
    ldp x11, x13, [x11, #16]
    cbnz x13, .Lrel_fcf_fallback
.Lrel_fcf_len4_calc:
    cmp w12, #ARM_OP_add
    b.ne .Lrel_fcf_len4_sub
    adds w5, w9, w11
    b.vs .Lrel_fcf_fallback
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fcf_commit
.Lrel_fcf_len4_sub:
    subs w5, w9, w11
    b.vs .Lrel_fcf_fallback
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fcf_commit
.Lrel_fcf_var1:
    cmp w9, #1
    b.ne .Lrel_fcf_fallback
    tbz w14, #25, .Lrel_fcf_fallback
    tbz w14, #26, .Lrel_fcf_fallback
    cbz w0, .Lrel_fcf_fallback
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fcf_fallback
    cmp w13, #9
    b.ne .Lrel_fcf_var1_chk10
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fcf_fallback
    mov w4, #0
    b .Lrel_fcf_var1_lookup
.Lrel_fcf_var1_chk10:
    cmp w13, #10
    b.ne .Lrel_fcf_fallback
    tbz w14, #29, .Lrel_fcf_fallback
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_length
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fcf_fallback
    mov w4, #1
.Lrel_fcf_var1_lookup:
    ldp x9, x10, [x2]
    cmn x10, #1
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w10, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fcf_fallback
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w12, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w12, w10, w12
    neg x12, x12
    add x12, x11, x12, lsl #2
    ldur w12, [x12, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fcf_prop_loop:
    cbz w12, .Lrel_fcf_fallback
    sub w13, w12, #1
    add x13, x11, x13, lsl #3
    ldr w14, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w14, w10
    b.eq .Lrel_fcf_prop_found
    ldr w12, [x13]
    and w12, w12, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fcf_prop_loop
.Lrel_fcf_prop_found:
    ldr w14, [x13]
    tst w14, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fcf_fallback
    sub w12, w12, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x12, lsl #4
    ldp x5, x6, [x11]
    cbnz w4, .Lrel_fcf_len10_arr
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fcf_fallback
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fcf_fallback
    tbz x6, #63, .Lrel_fcf_commit
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fcf_commit
.Lrel_fcf_len10_arr:
    cmn x6, #1
    b.ne .Lrel_fcf_fallback
    ldrh w10, [x5, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fcf_fallback
    ldrb w10, [x5, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w10, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fcf_fallback
    ldr x10, [x5, #ARM_OFF_JSObject_prop]
    ldp x5, x6, [x10, #ARM_OFF_JSProperty_u_value]
    cmp x6, #ARM_CONST_JS_TAG_INT
    b.eq .Lrel_fcf_commit
    cmp x6, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lrel_fcf_fallback
.Lrel_fcf_commit:
    sub w16, w16, #2
    str w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    add w9, w0, #2
    b .Lrel_fast_leaf_pop_entry

.Lrel_fast_call_ready:
    ldrh w9, [x7, #ARM_FRAME_CALL_META_OFFSET]
    cbz w9, .Lrel_call_admitted_back
    ldrb w14, [x7, #ARM_FRAME_CALL_FORMALS_OFFSET]
    cmp w0, w14
    b.lo .Lrel_call_admitted_back
    mov w16, #0
    tbnz w12, #1, .Lrel_fcr_kind_ok
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #4, .Lrel_call_admitted_back
    mov w16, w14
    add x9, x9, w16, uxtw #4
.Lrel_fcr_kind_ok:
    ldrb w13, [x7, #ARM_FRAME_CALL_LOCALS_OFFSET]
    ldr x8, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x10, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_capacity]
    subs x12, x12, x10
    b.lo .Lrel_call_slow_back
    cmp x12, x9
    b.lo .Lrel_call_slow_back
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .Lrel_fcr_quota_ok
    ldr x15, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x15, x15, x9
    b.cs .Lrel_call_slow_back
    adds x12, x12, x15
    b.cs .Lrel_call_slow_back
    adds x12, x12, #4096
    b.cs .Lrel_call_slow_back
    mov x15, sp
    cmp x15, x12
    b.lo .Lrel_call_slow_back
.Lrel_fcr_quota_ok:
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    subs w12, w12, #1
    b.le .Lrel_call_slow_back
    str w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    and w12, w17, #1
    add w12, w12, w0
    add w12, w12, #1
    tbz w17, #1, .Lrel_fcr_pending
    orr w12, w12, #0x8000
.Lrel_fcr_pending:
    strh w12, [x22, #ARM_OFF_JSFrame_pending]
    add x14, x10, x9
    str x14, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_data]
    add x10, x10, x12
    add x23, x10, #ARM_FRAME_HEADER_BYTES
    mov x24, x2
    mov w15, w0
    cbz w16, .Lrel_fcr_args_hdr_ready
    mov x24, x23
    add x23, x23, w16, uxtw #4
    mov w15, w16
.Lrel_fcr_args_hdr_ready:
    stp x22, x3, [x10]
    stp x4, x24, [x10, #16]
    stp x23, xzr, [x10, #32]
    str xzr, [x10, #48]
    strh wzr, [x10, #56]
    strh w15, [x10, #58]
    ldrb w12, [x7, #ARM_STRICT_BYTE]
    and w12, w12, #ARM_STRICT_MASK
    lsr w12, w12, #ARM_STRICT_SHIFT
    str w12, [x10, #60]
    str xzr, [x10, #64]
    str x7, [x10, #80]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    tbz w17, #0, .Lrel_fcr_this
    ldp x5, x6, [x2, #-32]
.Lrel_fcr_this:
    stp x5, x6, [x10, #88]
    stp xzr, x8, [x10, #104]
    str x9, [x10, #120]
    cbz w16, .Lrel_fcr_owned_ready
    strh w16, [x10, #ARM_OFF_JSFrame_owned_args]
    mov x12, x24
    mov x14, x2
.Lrel_fcr_copy_owned:
    ldp x5, x6, [x14], #16
    tbz x6, #63, .Lrel_fcr_copy_store
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
.Lrel_fcr_copy_store:
    stp x5, x6, [x12], #16
    subs w16, w16, #1
    b.ne .Lrel_fcr_copy_owned
.Lrel_fcr_owned_ready:
    mov x12, x23
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .Lrel_fcr_locals_done
    cmp w13, #1
    b.ne .Lrel_fcr_chk_v2
    stp xzr, x14, [x12], #16
    b .Lrel_fcr_locals_done
.Lrel_fcr_chk_v2:
    cmp w13, #2
    b.ne .Lrel_fcr_vloop
    stp xzr, x14, [x12], #16
    stp xzr, x14, [x12], #16
    b .Lrel_fcr_locals_done
.Lrel_fcr_vloop:
    stp xzr, x14, [x12], #16
    subs w13, w13, #1
    b.ne .Lrel_fcr_vloop
.Lrel_fcr_locals_done:
    mov x21, x12
    ldr x20, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x12, x12, x9
    str x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    str x10, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    tbnz w17, #2, .Lrel_fcr_pub
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x10, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    b .Lrel_fcr_frame_set
.Lrel_fcr_pub:
    adrp x25, qjs_aarch64_publish_dirty
    add x25, x25, :lo12:qjs_aarch64_publish_dirty
.Lrel_fcr_frame_set:
    mov x22, x10
    mov x26, x7
    mov x27, #0
    ldr x3, [x7, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x3, #1
    b.ls .Lrel_fcr_ic_done
    ldr x4, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    add x3, x3, #ARM_OFF_JSPropertyIC_map
    lsr x9, x4, #2
    sub x27, x3, x9, lsl #3
.Lrel_fcr_ic_done:
    ARM_DISPATCH_NEXT 1

#ifdef QJS_AARCH64_CALL_LEAVES
.Lrel_fast_leaf_decline:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    b .Lrel_call_admitted_back
.Lrel_fast_leaf_mark_inline_only:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    orr w14, w12, #64
    strb w14, [x7, #ARM_FRAME_KIND_OFFSET]
    b .Lrel_call_admitted_back
.Lrel_fast_leaf_mark_nonleaf:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    orr w14, w12, #192
    strb w14, [x7, #ARM_FRAME_KIND_OFFSET]
    b .Lrel_call_admitted_back

.Lrel_fast_call_leaf_probe:
    tst w12, #12
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldr w13, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w13, #36
    b.hi .Lrel_fast_leaf_mark_nonleaf
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbnz w14, .Lrel_fast_leaf_mark_nonleaf
    tbnz x28, #62, .Lrel_fast_leaf_decline
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_module_loader_has_attr + 1)]
    cmp w15, #2
    b.eq .Lrel_fast_leaf_decline
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 1)]
    cmp w15, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w15, [x14, #(ARM_OFF_JSRuntime_current_stack_frame - 3)]
    cmp w15, #2
    b.eq .Lrel_fast_leaf_decline
    ldrb w15, [x14, #ARM_BIT_JSRuntime_dump_flags_BYTE]
    tst w15, #ARM_BIT_JSRuntime_dump_flags_MASK
    b.ne .Lrel_fast_leaf_decline
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x16, [x7, #ARM_OFF_JSFunctionBytecode_realm]
    cmp x16, x15
    b.ne .Lrel_fast_leaf_decline
    ldrh w16, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w0, w16
    b.lo .Lrel_fast_leaf_decline
    ldr w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    cmp w16, #1
    b.le .Lrel_call_slow_back
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x11, .Lrel_fast_leaf_quota_ok
    ldr x10, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x11, x11, x10
    b.cs .Lrel_call_slow_back
    mov x10, #5280
    adds x11, x11, x10
    b.cs .Lrel_call_slow_back
    mov x10, sp
    cmp x10, x11
    b.lo .Lrel_call_slow_back
.Lrel_fast_leaf_quota_ok:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    ldr x8, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldrh w9, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    sub w10, w13, #8
    cmp w10, #27
    b.hi .Lrel_leaf_ic_skip
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    ldp x10, x12, [x11]
    cmp x10, x7
    b.ne .Lrel_leaf_ic_skip
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .Lrel_leaf_ic_skip
    ldp x10, x5, [x11, #16]
    ldr x6, [x8]
    cmp x6, x10
    b.ne .Lrel_leaf_ic_skip
    sub x6, x13, #8
    ldr x6, [x8, x6]
    cmp x6, x5
    b.ne .Lrel_leaf_ic_skip
    br x12
.Lrel_leaf_ic_skip:
    cbnz w9, .Lrel_fast_leaf_has_vars
    cmp w13, #2
    b.eq .Lrel_fast_leaf_len2
    cmp w13, #4
    b.eq .Lrel_fast_leaf_len4
    cmp w13, #1
    b.ne .Lrel_fast_leaf_var0_other
    ldrb w10, [x8]
    cmp w10, #ARM_OP_return_undef
    b.ne .Lrel_fast_leaf_mark_nonleaf
    tbz w14, #24, .Lrel_fast_leaf_decline
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2:
    ldrb w11, [x8, #1]
    cmp w11, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    tbz w14, #24, .Lrel_fast_leaf_decline
    ldrb w10, [x8]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .Lrel_fast_leaf_len2_nonint
    sub w5, w10, #ARM_OP_push_0
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2_nonint:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .Lrel_fast_leaf_len2_nonarg
    cmp w11, w0
    b.hs .Lrel_fast_leaf_decline
    add x11, x2, x11, lsl #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2_nonarg:
    cmp w10, #ARM_OP_undefined
    b.ne .Lrel_fast_leaf_len2_not_undef
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2_not_undef:
    cmp w10, #ARM_OP_null
    b.ne .Lrel_fast_leaf_len2_not_null
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_NULL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2_not_null:
    sub w11, w10, #ARM_OP_push_false
    cmp w11, #1
    b.hi .Lrel_fast_leaf_len2_not_bool
    mov w5, w11
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len2_not_bool:
    sub w11, w10, #ARM_OP_get_var_ref0
    cmp w11, #3
    b.hi .Lrel_fast_leaf_mark_nonleaf
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cmp w11, w14
    b.hs .Lrel_fast_leaf_mark_nonleaf
    ldr x14, [x3, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x14, [x14, x11, lsl #3]
    ldr x14, [x14, #ARM_OFF_JSVarRef_pvalue]
    ldp x5, x6, [x14]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_len4:
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_return_undef
    b.eq .Lrel_fast_leaf_len4_closure
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
    b.ne .Lrel_fast_leaf_len4_ext
    ldrb w10, [x8]
    sub w10, w10, #ARM_OP_get_arg0
    cmp w10, #3
    b.hi .Lrel_fast_leaf_mark_inline_only
    tbz w14, #24, .Lrel_fast_leaf_decline
    cmp w10, w0
    b.hs .Lrel_fast_leaf_decline
    add x10, x2, x10, lsl #4
    ldp x9, x11, [x10]
    cbnz x11, .Lrel_fast_leaf_decline
    ldrb w10, [x8, #1]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .Lrel_fast_leaf_len4_add_arg
    sub w11, w10, #ARM_OP_push_0
    b .Lrel_fast_leaf_len4_add_do
.Lrel_fast_leaf_len4_add_arg:
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .Lrel_fast_leaf_mark_inline_only
    cmp w11, w0
    b.hs .Lrel_fast_leaf_decline
    add x11, x2, x11, lsl #4
    ldr x14, [x11, #8]
    cbnz x14, .Lrel_fast_leaf_decline
    ldr w11, [x11]
.Lrel_fast_leaf_len4_add_do:
    adds w5, w9, w11
    b.vs .Lrel_fast_leaf_decline
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_closure:
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_var_ref0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_put_var_ref0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_inc
    b.eq .Lrel_fast_leaf_closure_step
    cmp w10, #ARM_OP_dec
    b.ne .Lrel_fast_leaf_mark_nonleaf
.Lrel_fast_leaf_closure_step:
    tbz w14, #24, .Lrel_fast_leaf_decline
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbz w14, .Lrel_fast_leaf_mark_nonleaf
    ldr x14, [x3, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x14, [x14]
    ldrb w11, [x14, #ARM_OFF_JSVarRef_is_const]
    cbnz w11, .Lrel_fast_leaf_decline
    ldr x14, [x14, #ARM_OFF_JSVarRef_pvalue]
    ldp x9, x11, [x14]
    cbnz x11, .Lrel_fast_leaf_decline
    cmp w10, #ARM_OP_inc
    b.ne .Lrel_fast_leaf_closure_dec
    adds w9, w9, #1
    b.vs .Lrel_fast_leaf_decline
    b .Lrel_fast_leaf_closure_store
.Lrel_fast_leaf_closure_dec:
    subs w9, w9, #1
    b.vs .Lrel_fast_leaf_decline
.Lrel_fast_leaf_closure_store:
    sxtw x9, w9
    str x9, [x14]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_var0_other:
    cmp w13, #6
    b.eq .Lrel_fast_leaf_len6
    cmp w13, #7
    b.eq .Lrel_fast_leaf_len7
    cmp w13, #8
    b.eq .Lrel_fast_leaf_len8
    cmp w13, #9
    b.eq .Lrel_fast_leaf_len9
    cmp w13, #30
    b.eq .Lrel_fast_leaf_len30
    cmp w13, #14
    b.eq .Lrel_fast_leaf_check_14
    cmp w13, #22
    b.eq .Lrel_fast_leaf_check_ret_end
    cmp w13, #30
    b.eq .Lrel_fast_leaf_check_ret_end
    cmp w13, #16
    b.hi .Lrel_fast_leaf_mark_nonleaf
.Lrel_fast_leaf_check_ret_end:
    sub w10, w13, #1
    ldrb w10, [x8, x10]
    cmp w10, #ARM_OP_return
    b.eq .Lrel_fast_leaf_mark_inline_only
    b .Lrel_fast_leaf_mark_nonleaf
.Lrel_fast_leaf_len9:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_typeof
    b.eq .Lrel_probe_c_leaf
    b .Lrel_fast_leaf_check_ret_end
.Lrel_fast_leaf_len7:
    ldrb w10, [x8, #6]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8]
    sub w11, w10, #ARM_OP_get_arg0
    cmp w11, #3
    b.hi .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_inline_only
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    cmp w11, w0
    b.hs .Lrel_fast_leaf_decline
    add x9, x2, w11, uxtw #4
    ldp x9, x12, [x9]
    cmn x12, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w12, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #2]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_len7_loop:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_fast_leaf_len7_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_len7_loop
.Lrel_fast_leaf_len7_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_check_14:
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_return
    b.eq .Lrel_fast_leaf_cmp14
    cmp w10, #ARM_OP_return_undef
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cmp w10, #1
    b.eq .Lrel_fast_leaf_mark_inline_only
    b .Lrel_fast_leaf_mark_nonleaf

.Lrel_fast_leaf_has_vars:
    cmp w9, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    cmp w13, #9
    b.eq .Lrel_fast_leaf_getter9
    cmp w13, #10
    b.eq .Lrel_fast_leaf_setter10
    cmp w13, #11
    b.eq .Lrel_fast_leaf_at11
    cmp w13, #16
    b.eq .Lrel_fast_leaf_rem16
    cmp w13, #18
    b.eq .Lrel_fast_leaf_chk18
    cmp w13, #19
    b.eq .Lrel_probe_c_leaf
    cmp w13, #20
    b.eq .Lrel_probe_c_leaf
    cmp w13, #21
    b.eq .Lrel_probe_c_leaf
    cmp w13, #22
    b.eq .Lrel_fast_leaf_compound22
    cmp w13, #33
    b.eq .Lrel_probe_c_leaf
    cmp w13, #35
    b.eq .Lrel_probe_c_leaf
    b .Lrel_fast_leaf_mark_nonleaf
.Lrel_fast_leaf_chk18:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbz w10, .Lrel_fast_leaf_add18
    cmp w10, #1
    b.eq .Lrel_fast_leaf_mark_inline_only
    b .Lrel_fast_leaf_mark_nonleaf

.Lrel_fast_leaf_getter9:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    orr w10, w10, w11
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_getter9
    add x12, x12, :lo12:.Lrel_exec_getter9
    ldr x5, [x8]
    ldr x6, [x8, #1]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_getter9:
    cmp w13, #9
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cbnz w10, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_getter9_loop:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_fast_leaf_getter9_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_getter9_loop
.Lrel_fast_leaf_getter9_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_fast_leaf_commit
    ldr w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    str w11, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_setter10:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cbz w10, .Lrel_fast_leaf_size10
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #4]
    cmp w10, #ARM_OP_put_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_return_undef
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_setter10
    add x12, x12, :lo12:.Lrel_exec_setter10
    ldr x5, [x8]
    ldr x6, [x8, #2]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_setter10:
    cmp w13, #10
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    cbz w0, .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #5]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_setter10_loop:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_fast_leaf_setter10_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_setter10_loop
.Lrel_fast_leaf_setter10_found:
    ldr w5, [x13]
    mov w6, #ARM_PROPERTY_DESC_WRITE_MASK
    and w5, w5, w6
    mov w6, #ARM_PROPERTY_DESC_WRITABLE
    cmp w5, w6
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x13, x14, [x11]
    tbz x14, #63, .Lrel_fast_leaf_setter10_old_ok
    ldr w5, [x13, #ARM_REF_COUNT_OFFSET]
    cmp w5, #1
    b.le .Lrel_fast_leaf_decline
    cmp x13, x9
    b.ne .Lrel_fast_leaf_setter10_old_ok
    cmp w5, #2
    b.le .Lrel_fast_leaf_decline
.Lrel_fast_leaf_setter10_old_ok:
    ldp x5, x6, [x2]
    tbz x6, #63, .Lrel_fast_leaf_setter10_new_ok
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
.Lrel_fast_leaf_setter10_new_ok:
    tbz x14, #63, .Lrel_fast_leaf_setter10_write
    ldr w10, [x13, #ARM_REF_COUNT_OFFSET]
    sub w10, w10, #1
    str w10, [x13, #ARM_REF_COUNT_OFFSET]
.Lrel_fast_leaf_setter10_write:
    stp x5, x6, [x11]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_len4_ext:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_inline_only
    cmp w10, #ARM_OP_sub
    b.eq .Lrel_fast_leaf_len4_ops_ok
    cmp w10, #ARM_OP_mul
    b.eq .Lrel_fast_leaf_len4_ops_ok
    sub w11, w10, #ARM_OP_shl
    cmp w11, #(ARM_OP_or - ARM_OP_shl)
    b.ls .Lrel_fast_leaf_len4_ops_ok
    sub w11, w10, #ARM_OP_lt
    cmp w11, #(ARM_OP_strict_neq - ARM_OP_lt)
    b.hi .Lrel_fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_gte + 1)
    b.eq .Lrel_fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_eq - 1)
    b.eq .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len4_ops_ok:
    ldrb w11, [x8]
    sub w12, w11, #ARM_OP_get_arg0
    cmp w12, #3
    b.ls .Lrel_fast_leaf_len4_op0_ok
    sub w12, w11, #ARM_OP_push_minus1
    cmp w12, #8
    b.hi .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len4_op0_ok:
    ldrb w12, [x8, #1]
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.ls .Lrel_fast_leaf_len4_op1_ok
    sub w13, w12, #ARM_OP_push_minus1
    cmp w13, #8
    b.hi .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len4_op1_ok:
    tbz w14, #24, .Lrel_fast_leaf_decline
    sub w13, w11, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .Lrel_fast_leaf_len4_p0_lit
    cmp w13, w0
    b.hs .Lrel_fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x9, x14, [x13]
    cbnz x14, .Lrel_fast_leaf_decline
    b .Lrel_fast_leaf_len4_load1
.Lrel_fast_leaf_len4_p0_lit:
    sub w9, w11, #ARM_OP_push_0
.Lrel_fast_leaf_len4_load1:
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .Lrel_fast_leaf_len4_p1_lit
    cmp w13, w0
    b.hs .Lrel_fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x11, x14, [x13]
    cbnz x14, .Lrel_fast_leaf_decline
    b .Lrel_fast_leaf_len4_eval
.Lrel_fast_leaf_len4_p1_lit:
    sub w11, w12, #ARM_OP_push_0
.Lrel_fast_leaf_len4_eval:
    cmp w10, #ARM_OP_sub
    b.ne .Lrel_fast_leaf_len4_not_sub
    subs w5, w9, w11
    b.vs .Lrel_fast_leaf_decline
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_sub:
    cmp w10, #ARM_OP_mul
    b.ne .Lrel_fast_leaf_len4_not_mul
    smull x5, w9, w11
    cmp x5, w5, sxtw
    b.ne .Lrel_fast_leaf_decline
    cbnz x5, .Lrel_fast_leaf_len4_mul_ok
    orr w12, w9, w11
    tbnz w12, #31, .Lrel_fast_leaf_decline
.Lrel_fast_leaf_len4_mul_ok:
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_mul:
    cmp w10, #ARM_OP_shl
    b.ne .Lrel_fast_leaf_len4_not_shl
    and w11, w11, #31
    lsl w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_shl:
    cmp w10, #ARM_OP_sar
    b.ne .Lrel_fast_leaf_len4_not_sar
    and w11, w11, #31
    asr w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_sar:
    cmp w10, #ARM_OP_shr
    b.ne .Lrel_fast_leaf_len4_not_shr
    and w11, w11, #31
    lsr w5, w9, w11
    tbnz w5, #31, .Lrel_fast_leaf_decline
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_shr:
    cmp w10, #ARM_OP_and
    b.ne .Lrel_fast_leaf_len4_not_and
    and w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_and:
    cmp w10, #ARM_OP_xor
    b.ne .Lrel_fast_leaf_len4_not_xor
    eor w5, w9, w11
    mov w5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_not_xor:
    cmp w10, #ARM_OP_or
    b.ne .Lrel_fast_leaf_len4_cmp
    orr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len4_cmp:
    cmp w10, #ARM_OP_lt
    b.eq .Lrel_fast_leaf_cmp_lt
    cmp w10, #ARM_OP_lte
    b.eq .Lrel_fast_leaf_cmp_le
    cmp w10, #ARM_OP_gt
    b.eq .Lrel_fast_leaf_cmp_gt
    cmp w10, #ARM_OP_gte
    b.eq .Lrel_fast_leaf_cmp_ge
    cmp w10, #ARM_OP_eq
    b.eq .Lrel_fast_leaf_cmp_eq
    cmp w10, #ARM_OP_strict_eq
    b.eq .Lrel_fast_leaf_cmp_eq
    b .Lrel_fast_leaf_cmp_ne
.Lrel_fast_leaf_cmp_lt:
    cmp w9, w11
    cset w5, lt
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_cmp_le:
    cmp w9, w11
    cset w5, le
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_cmp_gt:
    cmp w9, w11
    cset w5, gt
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_cmp_ge:
    cmp w9, w11
    cset w5, ge
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_cmp_eq:
    cmp w9, w11
    cset w5, eq
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_cmp_ne:
    cmp w9, w11
    cset w5, ne
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_size10:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_length
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_size10
    add x12, x12, :lo12:.Lrel_exec_size10
    ldr x5, [x8]
    ldr x6, [x8, #2]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_size10:
    cmp w13, #10
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cbnz w10, .Lrel_fast_leaf_decline
    tbz w14, #13, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w14, #29, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_size10_loop:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_fast_leaf_size10_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_size10_loop
.Lrel_fast_leaf_size10_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x11, x12, [x11]
    cmn x12, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w13, [x11, #ARM_OFF_JSObject_class_id]
    cmp w13, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_leaf_decline
    ldrb w13, [x11, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w13, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_leaf_decline
    ldr x12, [x11, #ARM_OFF_JSObject_prop]
    ldp x5, x6, [x12, #ARM_OFF_JSProperty_u_value]
    cmp x6, #ARM_CONST_JS_TAG_INT
    b.eq .Lrel_fast_leaf_commit
    cmp x6, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lrel_fast_leaf_commit
    b .Lrel_fast_leaf_decline

.Lrel_fast_leaf_at11:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #ARM_OP_get_array_el
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #10]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_at11
    add x12, x12, :lo12:.Lrel_exec_at11
    ldr x5, [x8]
    ldr x6, [x8, #3]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_at11:
    cmp w13, #11
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    cbz w0, .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_at11_loop:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_fast_leaf_at11_found
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_at11_loop
.Lrel_fast_leaf_at11_found:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x11, x12, [x11]
    cmn x12, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w13, [x11, #ARM_OFF_JSObject_class_id]
    cmp w13, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_leaf_decline
    ldrb w13, [x11, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w13, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_leaf_decline
    ldp x5, x6, [x2]
    cbnz x6, .Lrel_fast_leaf_decline
    tbnz w5, #31, .Lrel_fast_leaf_decline
    ldr w13, [x11, #ARM_OFF_JSObject_u_array_count]
    cmp w5, w13
    b.hs .Lrel_fast_leaf_decline
    ldr x13, [x11, #ARM_OFF_JSObject_u_array_u_values]
    add x13, x13, w5, uxtw #4
    ldp x5, x6, [x13]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_fast_leaf_commit
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_cmp14:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #2
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #6]
    cmp w10, #ARM_OP_get_arg1
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #7]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #12]
    sub w11, w10, #ARM_OP_lt
    cmp w11, #(ARM_OP_strict_neq - ARM_OP_lt)
    b.hi .Lrel_fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_gte + 1)
    b.eq .Lrel_fast_leaf_mark_inline_only
    cmp w10, #(ARM_OP_eq - 1)
    b.eq .Lrel_fast_leaf_mark_inline_only
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_cmp14
    add x12, x12, :lo12:.Lrel_exec_cmp14
    ldr x5, [x8]
    ldr x6, [x8, #6]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_cmp14:
    cmp w13, #14
    b.ne .Lrel_fast_leaf_decline
    cbnz w9, .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #2
    b.ne .Lrel_fast_leaf_decline
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    cmp w0, #2
    b.lo .Lrel_fast_leaf_decline
    ldp x9, x11, [x2]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w12, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldp x5, x6, [x2, #16]
    cmn x6, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x5, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w12, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #2]
    ldr x12, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x12, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x12, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x12, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_cmp14_loop0:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w6, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w6, w10
    b.eq .Lrel_fast_leaf_cmp14_found0
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_cmp14_loop0
.Lrel_fast_leaf_cmp14_found0:
    ldr w6, [x13]
    tst w6, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x6, x13, [x11]
    cbnz x13, .Lrel_fast_leaf_decline
    ldur w11, [x8, #8]
    ldr x9, [x5, #ARM_OFF_JSObject_shape]
    cmp x9, x12
    b.ne .Lrel_fast_leaf_cmp14_slow1
    cmp w11, w10
    b.eq .Lrel_fast_leaf_cmp14_got1
.Lrel_fast_leaf_cmp14_slow1:
    ldr w14, [x9, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w11, w14
    neg x14, x14
    add x14, x9, x14, lsl #2
    ldur w14, [x14, #-4]
    add x12, x9, #ARM_OFF_JSShape_prop
.Lrel_fast_leaf_cmp14_loop1:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x12, x13, lsl #3
    ldr w10, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w10, w11
    b.eq .Lrel_fast_leaf_cmp14_found1
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_fast_leaf_cmp14_loop1
.Lrel_fast_leaf_cmp14_found1:
    ldr w10, [x13]
    tst w10, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
.Lrel_fast_leaf_cmp14_got1:
    ldr x10, [x5, #ARM_OFF_JSObject_prop]
    add x10, x10, x14, lsl #4
    ldp x10, x11, [x10]
    cbnz x11, .Lrel_fast_leaf_decline
    mov w9, w6
    mov w11, w10
    ldrb w10, [x8, #12]
    b .Lrel_fast_leaf_len4_cmp

.Lrel_fast_leaf_len6:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_push_0
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #4]
    cmp w10, #ARM_OP_or
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #5]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
    b.eq .Lrel_fast_leaf_len6_op_ok
    cmp w10, #ARM_OP_sub
    b.eq .Lrel_fast_leaf_len6_op_ok
    cmp w10, #ARM_OP_mul
    b.eq .Lrel_fast_leaf_len6_op_ok
    sub w11, w10, #ARM_OP_shl
    cmp w11, #(ARM_OP_or - ARM_OP_shl)
    b.hi .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len6_op_ok:
    ldrb w11, [x8]
    sub w12, w11, #ARM_OP_get_arg0
    cmp w12, #3
    b.ls .Lrel_fast_leaf_len6_p0_ok
    sub w12, w11, #ARM_OP_push_minus1
    cmp w12, #8
    b.hi .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len6_p0_ok:
    ldrb w12, [x8, #1]
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.ls .Lrel_fast_leaf_len6_p1_ok
    sub w13, w12, #ARM_OP_push_minus1
    cmp w13, #8
    b.hi .Lrel_fast_leaf_mark_inline_only
.Lrel_fast_leaf_len6_p1_ok:
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #21, .Lrel_fast_leaf_decline
    sub w13, w11, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .Lrel_fast_leaf_len6_p0_lit
    cmp w13, w0
    b.hs .Lrel_fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x9, x14, [x13]
    cbnz x14, .Lrel_fast_leaf_decline
    b .Lrel_fast_leaf_len6_load1
.Lrel_fast_leaf_len6_p0_lit:
    sub w9, w11, #ARM_OP_push_0
.Lrel_fast_leaf_len6_load1:
    sub w13, w12, #ARM_OP_get_arg0
    cmp w13, #3
    b.hi .Lrel_fast_leaf_len6_p1_lit
    cmp w13, w0
    b.hs .Lrel_fast_leaf_decline
    add x13, x2, x13, lsl #4
    ldp x11, x14, [x13]
    cbnz x14, .Lrel_fast_leaf_decline
    b .Lrel_fast_leaf_len6_eval
.Lrel_fast_leaf_len6_p1_lit:
    sub w11, w12, #ARM_OP_push_0
.Lrel_fast_leaf_len6_eval:
    cmp w10, #ARM_OP_add
    b.ne .Lrel_fast_leaf_len6_not_add
    add w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_add:
    cmp w10, #ARM_OP_sub
    b.ne .Lrel_fast_leaf_len6_not_sub
    sub w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_sub:
    cmp w10, #ARM_OP_mul
    b.ne .Lrel_fast_leaf_len6_bitop
    smull x5, w9, w11
    cmp x5, w5, sxtw
    b.ne .Lrel_fast_leaf_decline
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_bitop:
    cmp w10, #ARM_OP_shl
    b.ne .Lrel_fast_leaf_len6_not_shl
    and w11, w11, #31
    lsl w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_shl:
    cmp w10, #ARM_OP_sar
    b.ne .Lrel_fast_leaf_len6_not_sar
    and w11, w11, #31
    asr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_sar:
    cmp w10, #ARM_OP_shr
    b.ne .Lrel_fast_leaf_len6_not_shr
    and w11, w11, #31
    lsr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_shr:
    cmp w10, #ARM_OP_and
    b.ne .Lrel_fast_leaf_len6_not_and
    and w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_not_and:
    cmp w10, #ARM_OP_xor
    b.ne .Lrel_fast_leaf_len6_or
    eor w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len6_or:
    orr w5, w9, w11
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_len8:
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_var
    b.eq .Lrel_probe_c_leaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_get_arg1
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_add
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w10, [x8, #3]
    sub w11, w10, #ARM_OP_push_minus1
    cmp w11, #8
    b.hi .Lrel_fast_leaf_mark_inline_only
    ldrb w11, [x8, #4]
    cmp w11, #ARM_OP_add
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w11, [x8, #5]
    cmp w11, #ARM_OP_push_0
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w11, [x8, #6]
    cmp w11, #ARM_OP_or
    b.ne .Lrel_fast_leaf_mark_inline_only
    ldrb w11, [x8, #7]
    cmp w11, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_inline_only
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_len8
    add x12, x12, :lo12:.Lrel_exec_len8
    ldr x5, [x8]
    stp x7, x12, [x11]
    stp x5, x5, [x11, #16]
.Lrel_exec_len8:
    cmp w13, #8
    b.ne .Lrel_fast_leaf_decline
    cbnz w9, .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #2
    b.hi .Lrel_fast_leaf_decline
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    cmp w0, #2
    b.lo .Lrel_fast_leaf_decline
    ldp x9, x12, [x2]
    cbnz x12, .Lrel_fast_leaf_decline
    ldp x11, x12, [x2, #16]
    cbnz x12, .Lrel_fast_leaf_decline
    ldrb w10, [x8, #3]
    add w5, w9, w11
    sub w10, w10, #ARM_OP_push_0
    add w5, w5, w10
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lrel_fast_leaf_commit

.Lrel_probe_c_leaf:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    mov w10, #1
    b .Lrel_exec_c_leaf_common
.Lrel_exec_c_leaf:
    mov w10, #0
.Lrel_exec_c_leaf_common:
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    adrp x11, .Lfast_vm_ext_env
    ldr w11, [x11, :lo12:.Lfast_vm_ext_env]
    tbz w11, #1, .Lrel_fast_leaf_decline
    cmp w16, #2
    b.le .Lrel_call_slow_back
    sub sp, sp, #96
.cfi_adjust_cfa_offset 96
    stp x0, x1, [sp]
    stp x2, x3, [sp, #16]
    stp x4, x7, [sp, #32]
    stp x17, x28, [sp, #48]
    str w10, [sp, #80]
    mov x3, x0
    mov x0, x19
    mov x1, x7
    mov w4, w17
    add x5, sp, #64
    bl JS_FastCompoundLeaf
    mov w9, w0
    ldr w10, [sp, #80]
    ldp x5, x6, [sp, #64]
    ldp x0, x1, [sp]
    ldp x2, x3, [sp, #16]
    ldp x4, x7, [sp, #32]
    ldp x17, x28, [sp, #48]
    add sp, sp, #96
.cfi_adjust_cfa_offset -96
    cmp w9, #0
    b.lt .Lrel_fast_leaf_mark_nonleaf
    b.eq .Lrel_fast_leaf_decline
    ldr x15, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    sub w16, w16, w9
    add w16, w16, #1
    cbz w10, .Lrel_fast_leaf_commit
    ldr x8, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr w13, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_c_leaf
    add x12, x12, :lo12:.Lrel_exec_c_leaf
    ldr x14, [x8]
    sub x9, x13, #8
    ldr x9, [x8, x9]
    stp x7, x12, [x11]
    stp x14, x9, [x11, #16]
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_rem16:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_field2
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_tail_call_method
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldurh w10, [x8, #14]
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_rem16
    add x12, x12, :lo12:.Lrel_exec_rem16
    ldr x5, [x8]
    ldr x6, [x8, #8]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_rem16:
    cmp w13, #16
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cbnz w10, .Lrel_fast_leaf_decline
    tbz w14, #20, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    cmp w16, #2
    b.le .Lrel_fast_leaf_decline
    adrp x10, JS_LinuxCInvokeControl
    add x10, x10, :lo12:JS_LinuxCInvokeControl
    ldarb w10, [x10]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    adrp x10, JS_LinuxDensePopControl
    add x10, x10, :lo12:JS_LinuxDensePopControl
    ldarb w10, [x10]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    adrp x10, JS_LinuxDensePopLeafControl
    add x10, x10, :lo12:JS_LinuxDensePopLeafControl
    ldarb w10, [x10]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_rem16_l0:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_rem16_f0
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_rem16_l0
.Lrel_rem16_f0:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x4, x6, [x11]
    cmn x6, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x4, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x4, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w10, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_leaf_decline
    ldrb w10, [x4, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lrel_fast_leaf_decline
    ldr x11, [x4, #ARM_OFF_JSObject_shape]
    ldr w10, [x11, #ARM_OFF_JSShape_prop_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x11, #(ARM_OFF_JSShape_prop + ARM_OFF_JSShapeProperty_atom)]
    cmp w10, #ARM_CONST_JS_ATOM_length
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x11, #ARM_OFF_JSShape_prop]
    lsr w10, w10, #26
    cmp w10, #10
    b.ne .Lrel_fast_leaf_decline
    ldr x9, [x11, #ARM_OFF_JSShape_proto]
    cbz x9, .Lrel_fast_leaf_decline
    ldrb w10, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w10, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #9]
    tbnz w10, #31, .Lrel_fast_leaf_decline
    cmp w10, #ARM_CONST_JS_ATOM_length
    b.eq .Lrel_fast_leaf_decline
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_rem16_l1:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_rem16_f1
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_rem16_l1
.Lrel_rem16_f1:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x10, x11, [x11]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w12, [x10, #ARM_OFF_JSObject_class_id]
    cmp w12, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.ne .Lrel_fast_leaf_decline
    ldrh w12, [x10, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w12, .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_length]
    cbnz w12, .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x12, x15
    b.ne .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x13, JS_FrameDenseArrayPop
    add x13, x13, :lo12:JS_FrameDenseArrayPop
    cmp x12, x13
    b.ne .Lrel_fast_leaf_decline
    ldr x10, [x4, #ARM_OFF_JSObject_prop]
    ldr x11, [x10, #8]
    cbnz x11, .Lrel_fast_leaf_decline
    ldr w11, [x10]
    ldr w12, [x4, #ARM_OFF_JSObject_u_array_count]
    cmp w11, w12
    b.ne .Lrel_fast_leaf_decline
    cmp w12, #0
    b.lt .Lrel_fast_leaf_decline
    cbz w12, .Lrel_rem16_empty
    sub w12, w12, #1
    ldr x11, [x4, #ARM_OFF_JSObject_u_array_u_values]
    add x11, x11, w12, uxtw #4
    ldp x5, x6, [x11]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lrel_fast_leaf_decline
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    str w12, [x4, #ARM_OFF_JSObject_u_array_count]
    str x12, [x10]
    sub w16, w16, #1
    b .Lrel_fast_leaf_commit
.Lrel_rem16_empty:
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    sub w16, w16, #1
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_add18:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_field2
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #14]
    cmp w10, #ARM_OP_call_method
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldurh w10, [x8, #15]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #17]
    cmp w10, #ARM_OP_return_undef
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_add18
    add x12, x12, :lo12:.Lrel_exec_add18
    ldr x5, [x8]
    ldr x6, [x8, #10]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_add18:
    cmp w13, #18
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_field2
    b.ne .Lrel_fast_leaf_decline
    tbz w14, #20, .Lrel_fast_leaf_decline
    tbz w14, #25, .Lrel_fast_leaf_decline
    tbz w14, #26, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    cbz w0, .Lrel_fast_leaf_decline
    cmp w16, #2
    b.le .Lrel_fast_leaf_decline
    ldrb w10, [x15, #ARM_BIT_JSContext_std_array_prototype_BYTE]
    tst w10, #ARM_BIT_JSContext_std_array_prototype_MASK
    b.eq .Lrel_fast_leaf_decline
    ldp x9, x11, [x2, #-32]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w11, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w11, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_add18_l0:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_add18_f0
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_add18_l0
.Lrel_add18_f0:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x4, x6, [x11]
    cmn x6, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x4, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x4, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w10, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lrel_fast_leaf_decline
    ldrb w10, [x4, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lrel_fast_leaf_decline
    ldr x11, [x4, #ARM_OFF_JSObject_shape]
    ldr x9, [x11, #ARM_OFF_JSShape_proto]
    ldr x12, [x15, #ARM_OFF_JSContext_class_proto]
    ldp x12, x13, [x12, #(ARM_CONST_JS_CLASS_ARRAY * 16)]
    cmn x13, #1
    b.ne .Lrel_fast_leaf_decline
    cmp x9, x12
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w10, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x11, #ARM_OFF_JSShape_prop_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x11, #(ARM_OFF_JSShape_prop + ARM_OFF_JSShapeProperty_atom)]
    cmp w10, #ARM_CONST_JS_ATOM_length
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x11, #ARM_OFF_JSShape_prop]
    tst w10, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    tst w10, #ARM_PROPERTY_DESC_WRITABLE
    b.eq .Lrel_fast_leaf_decline
    ldur w10, [x8, #9]
    tbnz w10, #31, .Lrel_fast_leaf_decline
    cmp w10, #ARM_CONST_JS_ATOM_length
    b.eq .Lrel_fast_leaf_decline
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_add18_l1:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_add18_f1
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_add18_l1
.Lrel_add18_f1:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x10, x11, [x11]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w12, [x10, #ARM_OFF_JSObject_class_id]
    cmp w12, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.ne .Lrel_fast_leaf_decline
    ldrh w12, [x10, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w12, .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w12, #1
    b.ne .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x12, x15
    b.ne .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x13, qjs_fast_core_js_array_push
    ldr x13, [x13, :lo12:qjs_fast_core_js_array_push]
    cmp x12, x13
    b.ne .Lrel_fast_leaf_decline
    ldr x10, [x4, #ARM_OFF_JSObject_prop]
    ldr x11, [x10, #8]
    cbnz x11, .Lrel_fast_leaf_decline
    ldr w12, [x10]
    ldr w13, [x4, #ARM_OFF_JSObject_u_array_count]
    cmp w12, w13
    b.ne .Lrel_fast_leaf_decline
    ldr w13, [x4, #ARM_OFF_JSObject_u_array_u1_size]
    cmp w12, w13
    b.hs .Lrel_fast_leaf_decline
    adds w13, w12, #1
    b.vs .Lrel_fast_leaf_decline
    ldp x5, x6, [x2]
    cmp x6, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lrel_fast_leaf_decline
    tbz x6, #63, .Lrel_add18_store
    ldr w9, [x5, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x5, #ARM_REF_COUNT_OFFSET]
.Lrel_add18_store:
    ldr x11, [x4, #ARM_OFF_JSObject_u_array_u_values]
    add x11, x11, w12, uxtw #4
    stp x5, x6, [x11]
    mov w13, w13
    str w13, [x4, #ARM_OFF_JSObject_u_array_count]
    str x13, [x10]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    sub w16, w16, #1
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_compound22:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w11, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_push_this
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_put_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #2]
    cmp w10, #ARM_OP_get_loc0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #3]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_field2
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #14]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #19]
    cmp w10, #ARM_OP_tail_call_method
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldurh w10, [x8, #20]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    lsr x10, x7, #4
    and x10, x10, #63
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_leaf_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_leaf_ic
    add x11, x11, x10, lsl #5
    adrp x12, .Lrel_exec_compound22
    add x12, x12, :lo12:.Lrel_exec_compound22
    ldr x5, [x8]
    ldr x6, [x8, #14]
    stp x7, x12, [x11]
    stp x5, x6, [x11, #16]
.Lrel_exec_compound22:
    cmp w13, #22
    b.ne .Lrel_fast_leaf_decline
    cmp w9, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_get_field2
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x8, #13]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x8, #14]
    cmp w10, #ARM_OP_get_field
    b.ne .Lrel_fast_leaf_decline
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w17, #0, .Lrel_fast_leaf_decline
    cbz w0, .Lrel_fast_leaf_decline
    cmp w16, #2
    b.le .Lrel_fast_leaf_decline
    adrp x10, .Lfast_vm_ext_env
    ldr w10, [x10, :lo12:.Lfast_vm_ext_env]
    and w10, w10, #3
    cmp w10, #3
    b.ne .Lrel_fast_leaf_decline
    ldr x10, [x15, #ARM_OFF_JSContext_rt]
    ldr w10, [x10, #ARM_OFF_JSRuntime_property_ic_mode]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldr x9, [x15, #ARM_OFF_JSContext_class_proto]
    ldp x9, x10, [x9, #(ARM_CONST_JS_CLASS_STRING * 16)]
    cmn x10, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w10, [x9, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_STRING
    b.eq .Lrel_c22_proto_ok
    cmp w10, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x9, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w10, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
.Lrel_c22_proto_ok:
    ldur w10, [x8, #9]
    tbnz w10, #31, .Lrel_fast_leaf_decline
    cmp w10, #ARM_CONST_JS_ATOM_length
    b.eq .Lrel_fast_leaf_decline
    ldr x11, [x9, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_c22_lm:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_c22_fm
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_c22_lm
.Lrel_c22_fm:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x9, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x10, x11, [x11]
    cmn x11, #1
    b.ne .Lrel_fast_leaf_decline
    ldrh w12, [x10, #ARM_OFF_JSObject_class_id]
    cmp w12, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic
    b.ne .Lrel_fast_leaf_decline
    ldrb w12, [x10, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w12, #1
    b.ne .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_realm]
    cmp x12, x15
    b.ne .Lrel_fast_leaf_decline
    ldr x12, [x10, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x13, JS_FrameLocaleCompare
    add x13, x13, :lo12:JS_FrameLocaleCompare
    cmp x12, x13
    b.ne .Lrel_fast_leaf_decline
    ldp x4, x6, [x2, #-32]
    cmn x6, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w6, [x4, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w6, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #4]
    ldr x11, [x4, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_c22_la:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w5, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w5, w10
    b.eq .Lrel_c22_fa
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_c22_la
.Lrel_c22_fa:
    ldr w5, [x13]
    tst w5, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x4, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x9, x10, [x11]
    cmn x10, #7
    b.ne .Lrel_fast_leaf_decline
    ldr w4, [x9, #ARM_BIT_JSString_len_BYTE]
    tbnz w4, #31, .Lrel_fast_leaf_decline
    ldp x5, x6, [x2]
    cmn x6, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w6, [x5, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w6, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lrel_fast_leaf_decline
    ldur w10, [x8, #15]
    ldr x11, [x5, #ARM_OFF_JSObject_shape]
    ldr w14, [x11, #ARM_OFF_JSShape_prop_hash_mask]
    and w14, w10, w14
    neg x14, x14
    add x14, x11, x14, lsl #2
    ldur w14, [x14, #-4]
    add x11, x11, #ARM_OFF_JSShape_prop
.Lrel_c22_lb:
    cbz w14, .Lrel_fast_leaf_decline
    sub w13, w14, #1
    add x13, x11, x13, lsl #3
    ldr w6, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w6, w10
    b.eq .Lrel_c22_fb
    ldr w14, [x13]
    and w14, w14, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lrel_c22_lb
.Lrel_c22_fb:
    ldr w6, [x13]
    tst w6, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lrel_fast_leaf_decline
    sub w14, w14, #1
    ldr x11, [x5, #ARM_OFF_JSObject_prop]
    add x11, x11, x14, lsl #4
    ldp x12, x13, [x11]
    cmn x13, #7
    b.ne .Lrel_fast_leaf_decline
    ldr w5, [x12, #ARM_BIT_JSString_len_BYTE]
    tbnz w5, #31, .Lrel_fast_leaf_decline
    cmp x9, x12
    b.eq .Lrel_c22_eq
    ldr w6, [x9, #ARM_BIT_JSString_hash_BYTE]
    ubfx w6, w6, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbz w6, .Lrel_c22_a0
    cmp w6, #1
    b.eq .Lrel_c22_a1
    cmp w6, #2
    b.ne .Lrel_fast_leaf_decline
    ldr x10, [x9, #ARM_SIZE_JSString]
    b .Lrel_c22_chk_b
.Lrel_c22_a0:
    add x10, x9, #ARM_SIZE_JSString
    b .Lrel_c22_chk_b
.Lrel_c22_a1:
    ldr x13, [x9, #ARM_SIZE_JSString]
    ldr w10, [x9, #(ARM_SIZE_JSString + 8)]
    add x10, x13, x10
    add x10, x10, #ARM_SIZE_JSString
.Lrel_c22_chk_b:
    ldr w6, [x12, #ARM_BIT_JSString_hash_BYTE]
    ubfx w6, w6, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbz w6, .Lrel_c22_b0
    cmp w6, #1
    b.eq .Lrel_c22_b1
    cmp w6, #2
    b.ne .Lrel_fast_leaf_decline
    ldr x11, [x12, #ARM_SIZE_JSString]
    b .Lrel_c22_cmp
.Lrel_c22_b0:
    add x11, x12, #ARM_SIZE_JSString
    b .Lrel_c22_cmp
.Lrel_c22_b1:
    ldr x13, [x12, #ARM_SIZE_JSString]
    ldr w11, [x12, #(ARM_SIZE_JSString + 8)]
    add x11, x13, x11
    add x11, x11, #ARM_SIZE_JSString
.Lrel_c22_cmp:
    cmp w4, w5
    csel w6, w4, w5, lo
.Lrel_c22_loop:
    cbz w6, .Lrel_c22_len
    ldrb w13, [x10], #1
    ldrb w14, [x11], #1
    cmp w13, w14
    b.ne .Lrel_c22_diff
    sub w6, w6, #1
    b .Lrel_c22_loop
.Lrel_c22_len:
    cmp w4, w5
    b.eq .Lrel_c22_eq
.Lrel_c22_diff:
    mov w5, #-1
    mov w6, #1
    csel w5, w5, w6, lo
    sxtw x5, w5
    mov x6, #0
    sub w16, w16, #1
    b .Lrel_fast_leaf_commit
.Lrel_c22_eq:
    mov x5, #0
    mov x6, #0
    sub w16, w16, #1
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_len30:
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    ldrh w10, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    cmp w10, #2
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldr w10, [x7, #ARM_OFF_JSFunctionBytecode_cpool_count]
    cbnz w10, .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #1]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #6]
    cmp w10, #ARM_OP_eq
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #7]
    cmp w10, #ARM_OP_dup
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #8]
    cmp w10, #ARM_OP_if_true8
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #9]
    cmp w10, #20
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #10]
    cmp w10, #ARM_OP_drop
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #11]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #12]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #17]
    cmp w10, #ARM_OP_eq
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #18]
    cmp w10, #ARM_OP_dup
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #19]
    cmp w10, #ARM_OP_if_true8
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #20]
    cmp w10, #9
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #21]
    cmp w10, #ARM_OP_drop
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #22]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #23]
    cmp w10, #ARM_OP_push_atom_value
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #28]
    cmp w10, #ARM_OP_eq
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x8, #29]
    cmp w10, #ARM_OP_return
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x11, #ARM_OFF_JSRuntime_atom_array]
    ldur w10, [x8, #2]
    tbnz w10, #31, .Lrel_fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w5, [x9, #ARM_SIZE_JSString]
    ldur w10, [x8, #13]
    tbnz w10, #31, .Lrel_fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w6, [x9, #ARM_SIZE_JSString]
    ldur w10, [x8, #24]
    tbnz w10, #31, .Lrel_fast_leaf_mark_nonleaf
    ldr x9, [x11, w10, uxtw #3]
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w10, [x9, #11]
    and w10, w10, #0xf0
    cmp w10, #0x40
    b.ne .Lrel_fast_leaf_mark_nonleaf
    ldrb w13, [x9, #ARM_SIZE_JSString]
    tbz w14, #24, .Lrel_fast_leaf_decline
    tbz w14, #22, .Lrel_fast_leaf_decline
    cbz w0, .Lrel_fast_leaf_decline
    cmp w16, #3
    b.le .Lrel_fast_leaf_decline
    ldp x9, x10, [x2]
    cmp x10, #ARM_CONST_JS_TAG_STRING
    b.ne .Lrel_fast_leaf_decline
    ldr w10, [x9, #4]
    cmp w10, #1
    b.ne .Lrel_fast_leaf_decline
    ldrb w10, [x9, #11]
    tst w10, #0x30
    b.ne .Lrel_fast_leaf_decline
    ldrb w14, [x9, #ARM_SIZE_JSString]
    cmp w14, w5
    b.ne .Lrel_fast_leaf_len30_c12
    sub w16, w16, #1
    mov x5, #1
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit
.Lrel_fast_leaf_len30_c12:
    sub w16, w16, #2
    cmp w14, w6
    cset w5, eq
    cmp w14, w13
    cset w9, eq
    orr w5, w5, w9
    mov x6, #ARM_CONST_JS_TAG_BOOL
    b .Lrel_fast_leaf_commit

.Lrel_fast_leaf_commit:
    sub w16, w16, #1
    str w16, [x15, #ARM_OFF_JSContext_interrupt_counter]
    and w9, w17, #1
    add w9, w9, w0
    add w9, w9, #1
#endif
.Lrel_fast_leaf_pop_entry:
    tbnz w17, #1, .Lrel_fast_leaf_tail_ret
    cmp w9, #1
    b.eq .Lrel_fast_leaf_pop1
    cmp w9, #2
    b.eq .Lrel_fast_leaf_pop2
    cmp w9, #8
    b.hi .Lrel_fast_leaf_host_return
    sub x12, x21, x9, lsl #4
    mov x13, x12
.Lrel_fast_leaf_guard_loop:
    cmp x13, x21
    b.eq .Lrel_fast_leaf_release_start
    ldp x10, x11, [x13], #16
    tbz x11, #63, .Lrel_fast_leaf_guard_loop
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, w9
    b.le .Lrel_fast_leaf_host_return
    b .Lrel_fast_leaf_guard_loop
.Lrel_fast_leaf_release_start:
    mov x13, x12
.Lrel_fast_leaf_release_loop:
    cmp x13, x21
    b.eq .Lrel_fast_leaf_popped
    ldp x10, x11, [x13], #16
    tbz x11, #63, .Lrel_fast_leaf_release_loop
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    sub w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
    b .Lrel_fast_leaf_release_loop
.Lrel_fast_leaf_popped:
    stp x5, x6, [x12]
    add x21, x12, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.Lrel_fast_leaf_pop1:
    sub x12, x21, #16
    ldp x10, x11, [x12]
    tbz x11, #63, .Lrel_fast_leaf_pop1_done
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .Lrel_fast_leaf_host_return
    sub w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
.Lrel_fast_leaf_pop1_done:
    stp x5, x6, [x12]
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.Lrel_fast_leaf_pop2:
    sub x12, x21, #32
    ldp x10, x11, [x12]
    ldp x13, x14, [x12, #16]
    tbz x11, #63, .Lrel_fast_leaf_pop2_chk1
    ldr w8, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w8, #2
    b.le .Lrel_fast_leaf_host_return
.Lrel_fast_leaf_pop2_chk1:
    tbz x14, #63, .Lrel_fast_leaf_pop2_rel0
    ldr w15, [x13, #ARM_REF_COUNT_OFFSET]
    cmp w15, #2
    b.le .Lrel_fast_leaf_host_return
.Lrel_fast_leaf_pop2_rel0:
    tbz x11, #63, .Lrel_fast_leaf_pop2_rel1
    sub w8, w8, #1
    str w8, [x10, #ARM_REF_COUNT_OFFSET]
.Lrel_fast_leaf_pop2_rel1:
    tbz x14, #63, .Lrel_fast_leaf_pop2_done
    ldr w15, [x13, #ARM_REF_COUNT_OFFSET]
    sub w15, w15, #1
    str w15, [x13, #ARM_REF_COUNT_OFFSET]
.Lrel_fast_leaf_pop2_done:
    stp x5, x6, [x12]
    add x21, x12, #16
    mov x20, x1
    ARM_DISPATCH_NEXT 1
.Lrel_fast_leaf_tail_ret:
    orr w9, w9, #0x8000
.Lrel_fast_leaf_host_return:
    mov x20, x1
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    strh w9, [x22, #ARM_OFF_JSFrame_pending]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x5
    mov x1, x6
    tst w17, #4
    b.ne .Lpub_host_return
    b .Lhost_return
#endif
""")

    return text, "\n".join(islands)
