"""Numeric comparison, equality, bitwise, and negation fast paths for ARM64 Fast VM."""

from arm64.vm.specialize import _replace_exact


def _specialize_compare_branch_and_loops(text):
    # 1. Compare + branch fusion
    old_macro = """.macro ARM_INT_COMPARE name, condition
.L\\name:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lfloat_\\name
    cmp w10, w12
    cset w10, \\condition
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.endm"""
    new_macro = """.macro ARM_INT_COMPARE name, condition
.L\\name:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lfloat_\\name
    cmp w10, w12
    cset w10, \\condition
    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_if_false8
    cmp w16, #1
    b.ls .Lfast_cmp_branch
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.endm"""
    text = _replace_exact(text, old_macro, new_macro, 1, "ARM_INT_COMPARE macro")

    for name, cond in (
        ("lt", "lt"),
        ("lte", "le"),
        ("gt", "gt"),
        ("gte", "ge"),
        ("eq", "eq"),
        ("neq", "ne"),
    ):
        old_pub = f""".Lpub_{name}:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lpub_float_{name}
    cmp w10, w12
    cset w10, {cond}
    mov x11, #ARM_CONST_JS_TAG_BOOL"""
        new_pub = f""".Lpub_{name}:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lpub_float_{name}
    cmp w10, w12
    cset w10, {cond}
    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_if_false8
    cmp w16, #1
    b.ls .Lfast_cmp_branch
    mov x11, #ARM_CONST_JS_TAG_BOOL"""
        text = _replace_exact(text, old_pub, new_pub, 1, f"pub_{name} compare")

    # 2. Universal for-loop backedge fusion: inc_loc / dec_loc + goto8 -> get_loc + bound + lt/lte/gt/gte + if_false8/if_true8
    for p in ("", "pub_"):
        old_inc = f""".L{p}inc_loc:
    mov w17, #1
    b .L{p}update_local
.L{p}dec_loc:
    mov w17, #-1
.L{p}update_local:
    ldrb w12, [x20, #1]
    add x12, x23, x12, lsl #4
    ldp x10, x11, [x12]
    cbnz x11, .L{p}slow
    adds w10, w10, w17
    b.vs .L{p}slow
    stp x10, x11, [x12]
    add x20, x20, #2"""
        new_inc = f""".L{p}inc_loc:
    ldrb w14, [x20, #1]
    add x12, x23, w14, uxtw #4
    ldp x10, x11, [x12]
    cbnz x11, .L{p}slow
    adds w10, w10, #1
    b.vs .L{p}slow
    str x10, [x12]
    ldrb w15, [x20, #2]
    cmp w15, #ARM_OP_goto8
    b.eq .Lfast_inc_loop_goto8
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
.L{p}dec_loc:
    mov w17, #-1
.L{p}update_local:
    ldrb w14, [x20, #1]
    add x12, x23, w14, uxtw #4
    ldp x10, x11, [x12]
    cbnz x11, .L{p}slow
    adds w10, w10, w17
    b.vs .L{p}slow
    str x10, [x12]
    ldrb w15, [x20, #2]
    cmp w15, #ARM_OP_goto8
    b.eq .Lfast_inc_loop_goto8
    add x20, x20, #2"""
        text = _replace_exact(text, old_inc, new_inc, 1, f"{p}inc_loc/dec_loc")

    # 2b. Backward goto8 -> while (--n >= 0) 7-opcode loop superinstruction (Crypto am3 & bnCompareTo)
    old_goto = """    add x10, x10, #1
    add x10, x20, x10
    mov w17, #0
    b .Lbranch_poll"""
    new_goto = """    add x10, x10, #1
    add x10, x20, x10
#ifndef QJS_AARCH64_VM_INSTRUMENT
.if \\width == 1
    ldrb w14, [x10]
    cmp w14, #ARM_OP_get_arg
    b.eq .Lfast_goto8_back
    ldrb w15, [x10, #1]
    cmp w15, #ARM_OP_dec
    b.eq .Lfast_goto8_back
.Lgoto8_poll:
.endif
#endif
    mov w17, #0
    b .Lbranch_poll"""
    text = _replace_exact(text, old_goto, new_goto, 1, "ARM_GOTO goto8 backedge")

    old_pub_goto8 = """.Lpub_goto8:
.if 1 == 1
    ldrsb x10, [x20, #1]
.elseif 1 == 2
    ldursh x10, [x20, #1]
.else
    ldursw x10, [x20, #1]
.endif
    add x10, x10, #1
    add x10, x20, x10
    mov w17, #0
    b .Lpub_branch_poll"""
    new_pub_goto8 = """.Lpub_goto8:
    ldrsb x10, [x20, #1]
    add x10, x10, #1
    add x10, x20, x10
#ifndef QJS_AARCH64_VM_INSTRUMENT
    ldrb w14, [x10]
    cmp w14, #ARM_OP_get_arg
    b.eq .Lpub_fast_goto8_back
    ldrb w15, [x10, #1]
    cmp w15, #ARM_OP_dec
    b.eq .Lpub_fast_goto8_back
.Lpub_goto8_poll:
#endif
    mov w17, #0
    b .Lpub_branch_poll"""
    text = _replace_exact(text, old_pub_goto8, new_pub_goto8, 1, "pub_goto8 backedge")

    old_cmp_commit = """.Lcomparison_commit:
    eor w10, w10, w17
    mov x11, #ARM_CONST_JS_TAG_BOOL"""
    new_cmp_commit = """.Lcomparison_commit:
    eor w10, w10, w17
#ifndef QJS_AARCH64_VM_INSTRUMENT
    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_if_false8
    cmp w16, #1
    b.ls .Lfast_cmp_branch
#endif
    mov x11, #ARM_CONST_JS_TAG_BOOL"""
    text = _replace_exact(
        text, old_cmp_commit, new_cmp_commit, 1, "comparison_commit branch fusion"
    )

    # 3. Float compare + short branch fusion + ASCII/Latin1 String relational comparisons (<, <=, >, >=) + Release per-opcode C step
    old_f_end = """    mov x11, #ARM_CONST_JS_TAG_BOOL
    b .Lnumber_store
.endm"""
    new_f_end = """    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_if_false8
    cmp w16, #1
    b.ls .Lfast_cmp_branch
    mov x11, #ARM_CONST_JS_TAG_BOOL
    b .Lnumber_store
.endm"""
    text = _replace_exact(text, old_f_end, new_f_end, 1, "ARM_FLOAT_COMPARE branch fusion")

    old_pub_f_end = """    mov x11, #ARM_CONST_JS_TAG_BOOL
    b .Lpub_number_store"""
    new_pub_f_end = """    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_if_false8
    cmp w16, #1
    b.ls .Lfast_cmp_branch
    mov x11, #ARM_CONST_JS_TAG_BOOL
    b .Lpub_number_store"""
    if text.count(old_pub_f_end) != 8:
        raise ValueError(f"Expected 8 .Lpub_float_* stores, got {text.count(old_pub_f_end)}")
    text = text.replace(old_pub_f_end, new_pub_f_end)

    old_f_lt = """    ARM_FLOAT_COMPARE lt, lt, 1, .Lslow
    ARM_FLOAT_COMPARE lte, le, 1, .Lslow
    ARM_FLOAT_COMPARE gt, gt, 1, .Lslow
    ARM_FLOAT_COMPARE gte, ge, 1, .Lslow"""
    new_f_lt = """    ARM_FLOAT_COMPARE lt, lt, 1, .Lfast_rel_str_lt
    ARM_FLOAT_COMPARE lte, le, 1, .Lfast_rel_str_lte
    ARM_FLOAT_COMPARE gt, gt, 1, .Lfast_rel_str_gt
    ARM_FLOAT_COMPARE gte, ge, 1, .Lfast_rel_str_gte"""
    text = _replace_exact(text, old_f_lt, new_f_lt, 1, "ARM_FLOAT_COMPARE rel")

    for op in ("lt", "lte", "gt", "gte"):
        # In .Lpub_ stream, each .Lpub_float_{op} has exactly two b.ne .Lpub_slow before fcmp
        idx = text.index(f".Lpub_float_{op}:\n")
        end_idx = text.index("    fcmpe d0, d1\n", idx)
        seg = text[idx:end_idx]
        if seg.count("    b.ne .Lpub_slow\n") != 2:
            raise ValueError(f"Unexpected b.ne .Lpub_slow count in .Lpub_float_{op}")
        seg_new = seg.replace("    b.ne .Lpub_slow\n", f"    b.ne .Lpub_fast_rel_str_{op}\n")
        text = text[:idx] + seg_new + text[end_idx:]

    rel_islands = []
    for p in ("", "pub_"):
        pub_sync = ""
        if p == "pub_":
            pub_sync = """    adrp x10, qjs_aarch64_publish_clean
    add x10, x10, :lo12:qjs_aarch64_publish_clean
    cmp x25, x10
    b.eq 1f
    mov x25, x10
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
1:
"""
        rel_islands.append(f"""#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_goto8_back:
    cmp x10, x20
    b.hs .L{p}goto8_poll
    cmp w14, #ARM_OP_get_arg
    b.eq .L{p}fast_predec_arg
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .L{p}goto8_poll
    ldrb w16, [x10, #1]
    cmp w16, #ARM_OP_dec
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #2]
    add w13, w15, #ARM_OP_set_loc0
    cmp w16, w13
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #3]
    cmp w16, #ARM_OP_push_0
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #4]
    cmp w16, #ARM_OP_gte
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #5]
    cmp w16, #ARM_OP_if_false8
    b.ne .L{p}goto8_poll
    add x12, x23, w15, uxtw #4
    add x16, x10, #5
    b .L{p}fast_predec_exec
.L{p}fast_predec_arg:
    ldrb w16, [x10, #3]
    cmp w16, #ARM_OP_dec
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #4]
    cmp w16, #ARM_OP_set_arg
    b.ne .L{p}goto8_poll
    ldurh w15, [x10, #1]
    ldurh w13, [x10, #5]
    cmp w15, w13
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #7]
    cmp w16, #ARM_OP_push_0
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #8]
    cmp w16, #ARM_OP_gte
    b.ne .L{p}goto8_poll
    ldrb w16, [x10, #9]
    cmp w16, #ARM_OP_if_false8
    b.ne .L{p}goto8_poll
    add x12, x24, w15, uxtw #4
    add x16, x10, #9
.L{p}fast_predec_exec:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    mov w15, #3
    movk w15, #1, lsl #16
    and w14, w14, w15
    cmp w14, w15
    b.ne .L{p}goto8_poll
    ldp x13, x14, [x12]
    cbnz x14, .L{p}goto8_poll
    subs w13, w13, #1
    b.vs .L{p}goto8_poll
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w14, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w14, w14, #2
    b.le .L{p}goto8_poll
    str w14, [x11, #ARM_OFF_JSContext_interrupt_counter]
    sxtw x13, w13
    str x13, [x12]
    tbnz w13, #31, .L{p}fast_predec_exit
    add x20, x16, #2
    ARM_DISPATCH_NEXT 7
.L{p}fast_predec_exit:
    ldrsb x14, [x16, #1]
    add x20, x16, #1
    add x20, x20, x14
    ARM_DISPATCH_NEXT 7
#endif

.L{p}fast_rel_str_lt:
    mov w8, #0
    b .L{p}fast_rel_str_common
.L{p}fast_rel_str_lte:
    mov w8, #1
    b .L{p}fast_rel_str_common
.L{p}fast_rel_str_gt:
    mov w8, #2
    b .L{p}fast_rel_str_common
.L{p}fast_rel_str_gte:
    mov w8, #3
.L{p}fast_rel_str_common:
    cmn x11, #7
    b.ne .L{p}fast_rel_c_fallback
    cmn x13, #7
    b.ne .L{p}fast_rel_c_fallback
    ldur w0, [x10, #ARM_REF_COUNT_OFFSET]
    cmp x10, x12
    b.ne .L{p}fast_rel_distinct
    cmp w0, #2
    b.le .L{p}fast_rel_c_fallback
    and w6, w8, #1
    b .L{p}fast_rel_commit
.L{p}fast_rel_distinct:
    cmp w0, #1
    b.le .L{p}fast_rel_c_fallback
    ldur w1, [x12, #ARM_REF_COUNT_OFFSET]
    cmp w1, #1
    b.le .L{p}fast_rel_c_fallback
    ldr w2, [x10, #ARM_BIT_JSString_len_BYTE]
    tbnz w2, #31, .L{p}fast_rel_c_fallback
    ldr w3, [x12, #ARM_BIT_JSString_len_BYTE]
    tbnz w3, #31, .L{p}fast_rel_c_fallback
    ldr w4, [x10, #ARM_BIT_JSString_hash_BYTE]
    ubfx w4, w4, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbnz w4, .L{p}fast_rel_c_fallback
    ldr w4, [x12, #ARM_BIT_JSString_hash_BYTE]
    ubfx w4, w4, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cbnz w4, .L{p}fast_rel_c_fallback
    add x4, x10, #ARM_SIZE_JSString
    add x5, x12, #ARM_SIZE_JSString
    cmp w2, w3
    csel w7, w2, w3, lo
    cbz w7, .L{p}fast_rel_len_cmp
.L{p}fast_rel_byte_loop:
    ldrb w14, [x4], #1
    ldrb w15, [x5], #1
    cmp w14, w15
    b.ne .L{p}fast_rel_decided
    subs w7, w7, #1
    b.ne .L{p}fast_rel_byte_loop
.L{p}fast_rel_len_cmp:
    cmp w2, w3
.L{p}fast_rel_decided:
    cset w6, lo
    cset w7, ls
    cset w14, hi
    cset w15, hs
    cmp w8, #1
    csel w6, w6, w7, lo
    cmp w8, #2
    csel w14, w14, w15, eq
    csel w6, w6, w14, lo
.L{p}fast_rel_commit:
    ldur w0, [x10, #ARM_REF_COUNT_OFFSET]
    sub w0, w0, #1
    stur w0, [x10, #ARM_REF_COUNT_OFFSET]
    ldur w1, [x12, #ARM_REF_COUNT_OFFSET]
    sub w1, w1, #1
    stur w1, [x12, #ARM_REF_COUNT_OFFSET]
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x6, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.L{p}fast_rel_c_fallback:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b .L{p}slow
#else
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
{pub_sync}    mov x0, x19
    cbz w8, .L{p}fast_rel_c_lt
    cmp w8, #1
    b.eq .L{p}fast_rel_c_lte
    cmp w8, #2
    b.eq .L{p}fast_rel_c_gt
    bl JS_FrameInterpOp_gte
    cbz w0, .Lreload
    b .Ldone
.L{p}fast_rel_c_lt:
    bl JS_FrameInterpOp_lt
    cbz w0, .Lreload
    b .Ldone
.L{p}fast_rel_c_lte:
    bl JS_FrameInterpOp_lte
    cbz w0, .Lreload
    b .Ldone
.L{p}fast_rel_c_gt:
    bl JS_FrameInterpOp_gt
    cbz w0, .Lreload
    b .Ldone
#endif
""")
        if p:
            rel_islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{rel_islands[-1]}\n#endif"

    shared_island = """.Lfast_cmp_branch:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #1, .Lfast_cmp_unfused
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w14, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w14, w14, #1
    b.le .Lfast_cmp_unfused
    str w14, [x11, #ARM_OFF_JSContext_interrupt_counter]
    sub x21, x21, #32
    cmp w10, w16
    b.eq .Lfast_cmp_taken
    add x20, x20, #3
    ARM_DISPATCH_NEXT 2
.Lfast_cmp_taken:
    ldrsb x14, [x20, #2]
    add x20, x20, #2
    add x20, x20, x14
    ARM_DISPATCH_NEXT 2
.Lfast_cmp_unfused:
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.Lfast_inc_loop_goto8:
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    ldrsb x15, [x20, #3]
    add x15, x15, #3
    add x15, x20, x15
    ldrb w16, [x15]
    // A non-short index must clear Z even if the opcode arithmetic matches.
    add w17, w14, #ARM_OP_get_loc0
    cmp w14, #3
    ccmp w16, w17, #0, ls
    b.ne .Lfast_loop_chk_loc8
    add x16, x15, #1
.Lfast_loop_read_bound:
    ldrb w12, [x16]
    sub w17, w12, #ARM_OP_get_arg0
    cmp w17, #3
    b.hi .Lfast_loop_bnd_loc
    add x14, x24, w17, uxtw #4
    ldp x13, x14, [x14]
    add x17, x16, #1
    cbz x14, .Lfast_loop_int_cmp
    b .Lfast_loop_chk_nonint_tag
.Lfast_loop_chk_loc8:
    cmp w16, #ARM_OP_get_loc8
    b.ne .Lfast_inc_loop_goto_only
    ldrb w17, [x15, #1]
    cmp w17, w14
    b.ne .Lfast_inc_loop_goto_only
    add x16, x15, #2
    b .Lfast_loop_read_bound
.Lfast_loop_bnd_loc:
    sub w17, w12, #ARM_OP_get_loc0
    cmp w17, #3
    b.hi .Lfast_loop_bnd_vref
    add x14, x23, w17, uxtw #4
    ldp x13, x14, [x14]
    add x17, x16, #1
    b .Lfast_loop_chk_tag
.Lfast_loop_bnd_vref:
    sub w17, w12, #ARM_OP_get_var_ref0
    cmp w17, #3
    b.hi .Lfast_loop_bnd_i16
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #3, .Lfast_inc_loop_goto_only
    ldr x14, [x22, #ARM_OFF_JSStackFrame_cur_func]
    ldr x14, [x14, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x14, [x14, w17, uxtw #3]
    ldr x14, [x14, #ARM_OFF_JSVarRef_pvalue]
    ldp x13, x14, [x14]
    add x17, x16, #1
    b .Lfast_loop_chk_tag
.Lfast_loop_bnd_i16:
    cmp w12, #ARM_OP_push_i16
    b.ne .Lfast_loop_bnd_i8
    ldursh w13, [x16, #1]
    add x17, x16, #3
    b .Lfast_loop_int_cmp
.Lfast_loop_bnd_i8:
    cmp w12, #ARM_OP_push_i8
    b.ne .Lfast_loop_bnd_loc8
    ldrsb w13, [x16, #1]
    add x17, x16, #2
    b .Lfast_loop_int_cmp
.Lfast_loop_bnd_loc8:
    cmp w12, #ARM_OP_get_loc8
    b.ne .Lfast_loop_bnd_small
    ldrb w17, [x16, #1]
    add x14, x23, w17, uxtw #4
    ldp x13, x14, [x14]
    add x17, x16, #2
    b .Lfast_loop_chk_tag
.Lfast_loop_bnd_small:
    sub w17, w12, #ARM_OP_push_minus1
    cmp w17, #8
    b.hi .Lfast_inc_loop_goto_only
    sub w13, w12, #ARM_OP_push_0
    add x17, x16, #1
    b .Lfast_loop_int_cmp
.Lfast_loop_chk_tag:
    cbz x14, .Lfast_loop_int_cmp
.Lfast_loop_chk_nonint_tag:
    cmp x14, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_inc_loop_goto_only
    ldrb w14, [x17]
    sub w12, w14, #ARM_OP_lt
    cmp w12, #3
    b.hi .Lfast_inc_loop_goto_only
    scvtf d0, w10
    fmov d1, x13
    fcmpe d0, d1
    cset w14, mi
    cset w10, ls
    cset w13, gt
    cset w16, ge
    cmp w12, #1
    csel w14, w14, w10, lo
    cmp w12, #2
    csel w13, w13, w16, eq
    csel w14, w14, w13, lo
    b .Lfast_loop_chk_br
.Lfast_loop_int_cmp:
    ldrb w14, [x17]
    cmp w14, #ARM_OP_lt
    b.eq .Lfast_loop_cc_lt
    cmp w14, #ARM_OP_lte
    b.eq .Lfast_loop_cc_le
    cmp w14, #ARM_OP_gte
    b.eq .Lfast_loop_cc_ge
    cmp w14, #ARM_OP_gt
    b.ne .Lfast_inc_loop_goto_only
    cmp w10, w13
    cset w14, gt
    b .Lfast_loop_chk_br
.Lfast_loop_cc_lt:
    cmp w10, w13
    cset w14, lt
    b .Lfast_loop_chk_br
.Lfast_loop_cc_le:
    cmp w10, w13
    cset w14, le
    b .Lfast_loop_chk_br
.Lfast_loop_cc_ge:
    cmp w10, w13
    cset w14, ge
.Lfast_loop_chk_br:
    ldrb w12, [x17, #1]
    sub w16, w12, #ARM_OP_if_false8
    cmp w16, #1
    b.hi .Lfast_inc_loop_goto_only
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #1, .Lfast_inc_loop_goto_only
    subs w12, w9, #2
    b.le .Lfast_inc_loop_unfused
    str w12, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cmp w14, w16
    b.eq .Lfast_loop_taken
    add x20, x17, #3
    ARM_DISPATCH_NEXT 5
.Lfast_loop_taken:
    ldrsb x14, [x17, #2]
    add x20, x17, #2
    add x20, x20, x14
    ARM_DISPATCH_NEXT 5
.Lfast_inc_loop_goto_only:
    subs w12, w9, #1
    b.le .Lfast_inc_loop_unfused
    str w12, [x11, #ARM_OFF_JSContext_interrupt_counter]
    mov x20, x15
    ARM_DISPATCH_NEXT 2
.Lfast_inc_loop_unfused:
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
"""
    return text, shared_island + "\n" + "\n".join(rel_islands)


def _specialize_equality_comparisons(text):
    # Early diff-tag bypass right at .L{p}comparison_strict_miss (skips ldar on JS_FrameReferenceMode when x11 != x13!)
    islands = []
    for p in ("", "pub_"):
        old_sm = f""".L{p}comparison_strict_miss:
    adrp x9, JS_FrameReferenceMode"""
        new_sm = f""".L{p}comparison_strict_miss:
    cmp x11, x13
    b.ne .L{p}fast_strict_diff_tag
    adrp x9, JS_FrameReferenceMode"""
        text = _replace_exact(text, old_sm, new_sm, 1, f"{p}comparison_strict_miss")

        label_strict = f".L{p}comparison_strict_reference_miss:\n"
        new_strict = f""".L{p}comparison_strict_reference_miss:
    b .L{p}fast_strict_eq_ext
.L{p}comparison_strict_ref_orig:
"""
        text = _replace_exact(
            text, label_strict, new_strict, 1, f"{p}comparison_strict_reference_miss"
        )

        label_loose = f".L{p}comparison_loose_miss:\n"
        new_loose = f""".L{p}comparison_loose_miss:
    b .L{p}fast_loose_eq_ext
.L{p}comparison_loose_miss_orig:
"""
        text = _replace_exact(text, label_loose, new_loose, 1, f"{p}comparison_loose_miss")

        islands.append(f"""#if ARM_HAS_COMPARISONS
.L{p}fast_strict_eq_ext:
    cmp x11, x13
    b.ne .L{p}fast_strict_diff_tag
    cmp x11, #ARM_CONST_JS_TAG_BOOL
    b.ne .L{p}fast_strict_same_null
    cmp w10, w12
    cset w10, eq
    b .L{p}comparison_commit
.L{p}fast_strict_same_null:
    sub x9, x11, #ARM_CONST_JS_TAG_NULL
    cmp x9, #1
    b.hi .L{p}comparison_strict_ref_orig
    mov w10, #1
    b .L{p}comparison_commit
.L{p}fast_strict_diff_tag:
    tbz x11, #63, .L{p}fast_strict_l_imm
    cmn x11, #1
    b.eq .L{p}fast_strict_l_rc
    cmn x11, #7
    b.eq .L{p}fast_strict_l_rc
    cmn x11, #8
    b.ne .L{p}comparison_strict_ref_orig
.L{p}fast_strict_l_rc:
    ldur w0, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w0, #1
    b.le .L{p}comparison_strict_ref_orig
    b .L{p}fast_strict_chk_r
.L{p}fast_strict_l_imm:
    cmp x11, #ARM_CONST_JS_TAG_UNDEFINED
    b.hi .L{p}comparison_strict_ref_orig
.L{p}fast_strict_chk_r:
    tbz x13, #63, .L{p}fast_strict_r_imm
    cmn x13, #1
    b.eq .L{p}fast_strict_r_rc
    cmn x13, #7
    b.eq .L{p}fast_strict_r_rc
    cmn x13, #8
    b.ne .L{p}comparison_strict_ref_orig
.L{p}fast_strict_r_rc:
    ldur w1, [x12, #ARM_REF_COUNT_OFFSET]
    cmp w1, #1
    b.le .L{p}comparison_strict_ref_orig
    b .L{p}fast_strict_diff_commit
.L{p}fast_strict_r_imm:
    cmp x13, #ARM_CONST_JS_TAG_UNDEFINED
    b.hi .L{p}comparison_strict_ref_orig
.L{p}fast_strict_diff_commit:
    tbz x11, #63, .L{p}fast_strict_rel_r
    sub w0, w0, #1
    stur w0, [x10, #ARM_REF_COUNT_OFFSET]
.L{p}fast_strict_rel_r:
    tbz x13, #63, .L{p}fast_strict_false
    sub w1, w1, #1
    stur w1, [x12, #ARM_REF_COUNT_OFFSET]
.L{p}fast_strict_false:
    mov w10, #0
    b .L{p}comparison_commit

.L{p}fast_loose_eq_ext:
    cmp x11, x13
    b.ne .L{p}comparison_loose_miss_orig
    cmp x11, #ARM_CONST_JS_TAG_BOOL
    b.ne .L{p}fast_loose_ref_chk
    cmp w10, w12
    cset w10, eq
    b .L{p}comparison_commit
.L{p}fast_loose_ref_chk:
    cmn x11, #1
    b.eq .L{p}fast_loose_ref_mode
    cmn x11, #8
    b.ne .L{p}comparison_loose_miss_orig
.L{p}fast_loose_ref_mode:
    adrp x9, JS_FrameReferenceMode
    add x9, x9, :lo12:JS_FrameReferenceMode
    ldar w9, [x9]
    cmp w9, #1
    b.eq .L{p}comparison_reference_tag
    b .L{p}comparison_loose_miss_orig
#endif
""")
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"
    return text, "\n".join(islands)


def _specialize_float_bitwise_and_neg(text):
    islands = [
        """#if ARM_HAS_SCALAR_OPS
.Lfast_shr_uint32:
    ucvtf d0, w0
    fmov x0, d0
    mov x1, #ARM_CONST_JS_TAG_FLOAT64
    stp x0, x1, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
#endif
"""
    ]
    for p in ("", "pub_"):
        if not p:
            text = _replace_exact(
                text,
                ".Lnumeric_binary_tags:\n"
                "    ldp x10, x11, [x21, #-32]\n"
                "    ldp x12, x13, [x21, #-16]\n"
                "    cmp x11, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "    b.eq .Lnumeric_binary_rhs\n",
                ".Lnumeric_binary_tags:\n"
                "    ldp x10, x11, [x21, #-32]\n"
                "    ldp x12, x13, [x21, #-16]\n"
                "    cmp x11, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
                "    b.eq .Lfast_sbigint_lhs\n"
                "#else\n"
                "    b.eq .Lnumeric_binary_rhs\n"
                "#endif\n",
                1,
                "numeric_binary_tags sbigint",
            )
            text = _replace_exact(
                text,
                ".Lnumeric_binary_rhs:\n"
                "    cmp x13, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "    b.eq .Lnumeric_binary_call\n"
                "    mov x14, #ARM_CONST_JS_TAG_BIG_INT\n",
                ".Lnumeric_binary_rhs:\n"
                "    cmp x13, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "    b.eq .Lnumeric_binary_call\n"
                ".Lnumeric_binary_rhs_not_short:\n"
                "    mov x14, #ARM_CONST_JS_TAG_BIG_INT\n",
                1,
                "numeric_binary_rhs label",
            )
            text = _replace_exact(
                text,
                ".Lnumeric_binary_done:\n    cbz w0, .Lreload\n    b .Ldone\n",
                ".Lnumeric_binary_done:\n"
                "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
                "    cbz w0, .Lfast_numeric_c_resume\n"
                "#else\n"
                "    cbz w0, .Lreload\n"
                "#endif\n"
                "    b .Ldone\n",
                1,
                "numeric_binary_done light resume",
            )
            text = _replace_exact(
                text,
                ".Lnumeric_local_mode:\n"
                "    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]\n"
                "    ldrb w10, [x9, #ARM_NUMERIC_LOCAL_MODE_OFFSET]\n"
                "    cmp w10, #2\n"
                "    b.eq .Lslow\n"
                "    cbz w10, .Lnumeric_local_c\n"
                "    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "    b.ne .Lnumeric_local_c\n",
                ".Lnumeric_local_mode:\n"
                "    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]\n"
                "    ldrb w10, [x9, #ARM_NUMERIC_LOCAL_MODE_OFFSET]\n"
                "    cmp w10, #2\n"
                "    b.eq .Lslow\n"
                "    cbz w10, .Lnumeric_local_c\n"
                "    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT\n"
                "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
                "    b.ne .Lfast_local_bigint_chk\n"
                "#else\n"
                "    b.ne .Lnumeric_local_c\n"
                "#endif\n",
                1,
                "numeric_local_mode bigint inplace",
            )
            text = _replace_exact(
                text,
                "    bl JS_FrameAddLocalBig\n"
                "    cmp w0, #2\n"
                "    b.eq .Lreload\n"
                "    cbz w0, .Lreload\n"
                "    b .Ldone\n",
                "    bl JS_FrameAddLocalBig\n"
                "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
                "    cmp w0, #2\n"
                "    b.eq .Lfast_numeric_c_resume\n"
                "    cbz w0, .Lfast_numeric_c_resume\n"
                "#else\n"
                "    cmp w0, #2\n"
                "    b.eq .Lreload\n"
                "    cbz w0, .Lreload\n"
                "#endif\n"
                "    b .Ldone\n",
                1,
                "numeric_local_c light resume",
            )
            islands.append("""#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_sbigint_lhs:
    cmp x13, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lnumeric_binary_rhs_not_short
    cbnz w17, .Lfast_sbigint_mul
    adds w14, w10, w12
    b.vs .Lnumeric_binary_call
    mov w14, w14
    mov x15, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    stp x14, x15, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lfast_sbigint_mul:
    smull x14, w10, w12
    ldrb w15, [x20, #1]
    cmp w15, #ARM_OP_add
    b.eq .Lfast_sbigint_mul_addput
    cmp w15, #ARM_OP_add_loc
    b.ne .Lfast_sbigint_mul_only
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x9, #ARM_NUMERIC_LOCAL_MODE_OFFSET]
    cmp w15, #1
    b.ne .Lfast_sbigint_mul_only
    ldrb w4, [x20, #2]
    add x4, x23, x4, lsl #4
    ldp x5, x6, [x4]
    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lfast_sbigint_mul_acc_big
    sxtw x15, w5
    adds x16, x15, x14
    b.vs .Lnumeric_binary_call
    cmp x16, w16, sxtw
    b.ne .Lnumeric_binary_call
    mov w16, w16
    str x16, [x4]
    sub x21, x21, #32
    add x20, x20, #3
    ARM_DISPATCH_NEXT 2
.Lfast_sbigint_mul_acc_big:
    cmn x6, #9
    b.ne .Lnumeric_binary_call
    ldur w15, [x5, #ARM_OFF_JSBigInt_header_ref_count]
    cmp w15, #1
    b.ne .Lnumeric_binary_call
    mov x9, #3
    mov w8, #32
    b .Lfast_sbigint_mul_big_limbs
.Lfast_sbigint_mul_addput:
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w15, [x9, #ARM_NUMERIC_LOCAL_MODE_OFFSET]
    cmp w15, #1
    b.ne .Lfast_sbigint_mul_only
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #0, .Lfast_sbigint_mul_only
    ldrb w16, [x20, #2]
    sub w4, w16, #ARM_OP_put_loc0
    cmp w4, #3
    mov x9, #3
    b.ls .Lfast_sbm_ap_slot
    cmp w16, #ARM_OP_put_loc8
    b.ne .Lfast_sbigint_mul_only
    ldrb w4, [x20, #3]
    mov x9, #4
.Lfast_sbm_ap_slot:
    add x4, x23, w4, uxtw #4
    ldp x5, x6, [x21, #-48]
    ldp x7, x8, [x4]
    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lfast_sbm_ap_big
    tbnz x8, #63, .Lfast_sbigint_mul_only
    sxtw x15, w5
    adds x16, x15, x14
    b.vs .Lnumeric_binary_call
    cmp x16, w16, sxtw
    b.ne .Lnumeric_binary_call
    mov w16, w16
    mov x15, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    stp x16, x15, [x4]
    sub x21, x21, #48
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3
.Lfast_sbm_ap_big:
    cmn x6, #9
    b.ne .Lfast_sbigint_mul_only
    cmp x5, x7
    b.ne .Lfast_sbigint_mul_only
    cmp x6, x8
    b.ne .Lfast_sbigint_mul_only
    ldur w15, [x5, #ARM_OFF_JSBigInt_header_ref_count]
    cmp w15, #2
    b.ne .Lfast_sbigint_mul_only
    mov w8, #48
.Lfast_sbigint_mul_big_limbs:
    ldr w15, [x5, #ARM_OFF_JSBigInt_len]
    cmp w15, #2
    b.ne .Lfast_sbigint_mul_chk3
    ldur x16, [x5, #ARM_OFF_JSBigInt_tab]
    adds x16, x16, x14
    b.vs .Lnumeric_binary_call
    cmp x16, w16, sxtw
    b.eq .Lnumeric_binary_call
    mov w15, #1
    stur w15, [x5, #ARM_OFF_JSBigInt_header_ref_count]
    stur x16, [x5, #ARM_OFF_JSBigInt_tab]
    sub x21, x21, x8
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3
.Lfast_sbigint_mul_chk3:
    cmp w15, #3
    b.ne .Lnumeric_binary_call
    cmp x14, #0
    b.lt .Lnumeric_binary_call
    ldr w7, [x5, #(ARM_OFF_JSBigInt_tab + 8)]
    cmp w7, #0
    b.lt .Lnumeric_binary_call
    ldur x16, [x5, #ARM_OFF_JSBigInt_tab]
    adds x16, x16, x14
    adc w7, w7, wzr
    cmp w7, #0
    b.lt .Lnumeric_binary_call
    mov w15, #1
    stur w15, [x5, #ARM_OFF_JSBigInt_header_ref_count]
    stur x16, [x5, #ARM_OFF_JSBigInt_tab]
    str w7, [x5, #(ARM_OFF_JSBigInt_tab + 8)]
    sub x21, x21, x8
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3
.Lfast_sbigint_mul_only:
    cmp x14, w14, sxtw
    b.ne .Lnumeric_binary_call
    mov w14, w14
    mov x15, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    stp x14, x15, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.Lfast_local_bigint_chk:
    cmn x6, #9
    b.ne .Lnumeric_local_c
    cmp x8, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lnumeric_local_c
    ldur w15, [x5, #ARM_OFF_JSBigInt_header_ref_count]
    cmp w15, #1
    b.ne .Lnumeric_local_c
    sxtw x14, w7
    ldr w15, [x5, #ARM_OFF_JSBigInt_len]
    cmp w15, #2
    b.ne .Lfast_local_bigint_chk3
    ldur x16, [x5, #ARM_OFF_JSBigInt_tab]
    adds x16, x16, x14
    b.vs .Lnumeric_local_c
    cmp x16, w16, sxtw
    b.eq .Lnumeric_local_c
    stur x16, [x5, #ARM_OFF_JSBigInt_tab]
    sub x21, x21, #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
.Lfast_local_bigint_chk3:
    cmp x14, #0
    b.lt .Lnumeric_local_c
    cmp w15, #3
    b.hi .Lfast_local_bigint_chk_ge4
    b.lo .Lnumeric_local_c
    ldr w12, [x5, #(ARM_OFF_JSBigInt_tab + 8)]
    cmp w12, #0
    b.lt .Lnumeric_local_c
    ldur x16, [x5, #ARM_OFF_JSBigInt_tab]
    adds x16, x16, x14
    adc w12, w12, wzr
    cmp w12, #0
    b.lt .Lnumeric_local_c
    stur x16, [x5, #ARM_OFF_JSBigInt_tab]
    str w12, [x5, #(ARM_OFF_JSBigInt_tab + 8)]
    sub x21, x21, #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
.Lfast_local_bigint_chk_ge4:
    sub w12, w15, #1
    add x16, x5, #ARM_OFF_JSBigInt_tab
    ldr w12, [x16, w12, uxtw #2]
    cmp w12, #0
    b.lt .Lnumeric_local_c
    ldur x16, [x5, #ARM_OFF_JSBigInt_tab]
    adds x16, x16, x14
    b.cs .Lnumeric_local_c
    stur x16, [x5, #ARM_OFF_JSBigInt_tab]
    sub x21, x21, #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1

.Lfast_numeric_c_resume:
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    cmp x9, x22
    b.ne .Lreload
    mov x27, #0
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 1
#endif
""")

        # Direct sub/div C step in Release when non-number misses numeric_binary (e.g. string_to_float r -= s)
        old_nb = f""".L{p}numeric_binary:
    cmp w17, #0
    b.eq .L{p}numeric_binary_tags
    cmp w17, #2
    b.ne .L{p}slow"""
        new_nb = f""".L{p}numeric_binary:
    cmp w17, #0
    b.eq .L{p}numeric_binary_tags
    cmp w17, #2
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b.ne .L{p}slow
#else
    b.ne .L{p}fast_c_sub_div
#endif"""
        text = _replace_exact(text, old_nb, new_nb, 1, f"{p}numeric_binary")

        old_neg = f""".L{p}scalar_neg:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .L{p}slow"""
        new_neg = f""".L{p}scalar_neg:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .L{p}fast_neg_f64"""
        text = _replace_exact(text, old_neg, new_neg, 1, f"{p}scalar_neg")

        for op_name in ("or", "xor", "shl", "sar"):
            old_bw = f""".L{p}scalar_{op_name}:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .L{p}slow"""
            new_bw = f""".L{p}scalar_{op_name}:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .L{p}fast_f64_{op_name}"""
            text = _replace_exact(text, old_bw, new_bw, 1, f"{p}scalar_{op_name}")

        old_shr = f""".L{p}scalar_shr:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .L{p}slow
    lsr w0, w0, w2
    tbnz w0, #31, .L{p}slow"""
        new_shr = f""".L{p}scalar_shr:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .L{p}fast_f64_shr
    lsr w0, w0, w2
    tst w0, #0x80000000
    b.ne .Lfast_shr_uint32"""
        text = _replace_exact(text, old_shr, new_shr, 1, f"{p}scalar_shr")

        old_and = f""".L{p}bitand:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .L{p}slow"""
        new_and = f""".L{p}bitand:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .L{p}fast_f64_and"""
        text = _replace_exact(text, old_and, new_and, 1, f"{p}bitand")

        old_mod = f""".L{p}scalar_mod:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .L{p}slow"""
        new_mod = f""".L{p}scalar_mod:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
#ifdef QJS_AARCH64_VM_INSTRUMENT
    cbnz x4, .L{p}slow
#else
    cbnz x4, .L{p}fast_c_mod
#endif"""
        text = _replace_exact(text, old_mod, new_mod, 1, f"{p}scalar_mod")

        pub_sync = ""
        if p == "pub_":
            pub_sync = """    adrp x10, qjs_aarch64_publish_clean
    add x10, x10, :lo12:qjs_aarch64_publish_clean
    cmp x25, x10
    b.eq 1f
    mov x25, x10
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
1:
"""

        lhs_big_br = (
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    b.hs .Lfast_f64_big_lhs\n"
            "#else\n"
            "    b.hs .Lslow\n"
            "#endif"
            if not p
            else "    b.hs .Lpub_slow"
        )
        rhs_big_br = (
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    b.hs .Lfast_f64_big_rhs\n"
            "#else\n"
            "    b.hs .Lslow\n"
            "#endif"
            if not p
            else "    b.hs .Lpub_slow"
        )
        big_f64_ext = (
            """#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_f64_big_lhs:
    cmp w9, #1107
    b.hs .Lfast_f64_zero_lhs
    sub w14, w9, #1075
    lsl w14, w0, w14
    tbz x0, #63, .Lfast_f64_set_lhs
    neg w14, w14
.Lfast_f64_set_lhs:
    mov w0, w14
    b .Lfast_f64_rhs
.Lfast_f64_zero_lhs:
    mov x0, #0
    b .Lfast_f64_rhs
.Lfast_f64_big_rhs:
    cmp w9, #1107
    b.hs .Lfast_f64_zero_rhs
    sub w14, w9, #1075
    lsl w14, w2, w14
    tbz x2, #63, .Lfast_f64_set_rhs
    neg w14, w14
.Lfast_f64_set_rhs:
    mov w2, w14
    b .Lfast_f64_exec
.Lfast_f64_zero_rhs:
    mov x2, #0
    b .Lfast_f64_exec
#endif
"""
            if not p
            else ""
        )

        resume_lbl = ".Lfast_numeric_c_resume" if not p else ".Lpub_reload"
        islands.append(f"""#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_c_sub_div:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
{pub_sync}    mov x0, x19
    cmp w17, #1
    b.ne .L{p}fast_c_div
    bl JS_FrameInterpOp_sub
    cbz w0, {resume_lbl}
    b .Ldone
.L{p}fast_c_div:
    bl JS_FrameInterpOp_div
    cbz w0, {resume_lbl}
    b .Ldone
.L{p}fast_c_mod:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
{pub_sync}    mov x0, x19
    bl JS_FrameInterpOp_mod
    cbz w0, {resume_lbl}
    b .Ldone
#endif

#if ARM_HAS_SCALAR_OPS
.L{p}fast_neg_f64:
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}slow
    eor x0, x0, #0x8000000000000000
    str x0, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.L{p}fast_f64_or:
    mov w8, #0
    b .L{p}fast_f64_bitwise
.L{p}fast_f64_xor:
    mov w8, #1
    b .L{p}fast_f64_bitwise
.L{p}fast_f64_shl:
    mov w8, #2
    b .L{p}fast_f64_bitwise
.L{p}fast_f64_sar:
    mov w8, #3
    b .L{p}fast_f64_bitwise
.L{p}fast_f64_shr:
    mov w8, #4
    b .L{p}fast_f64_bitwise
.L{p}fast_f64_and:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tst w9, #0x10000
    b.eq .L{p}slow
    mov x0, x10
    mov x1, x11
    mov x2, x12
    mov x3, x13
    mov w8, #5
.L{p}fast_f64_bitwise:
    cbz x1, .L{p}fast_f64_rhs
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}slow
    lsr x9, x0, #52
    and w9, w9, #0x7ff
    cmp w9, #1075
{lhs_big_br}
    fmov d0, x0
    fcvtzs x0, d0
.L{p}fast_f64_rhs:
    cbz x3, .L{p}fast_f64_exec
    cmp x3, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}slow
    lsr x9, x2, #52
    and w9, w9, #0x7ff
    cmp w9, #1075
{rhs_big_br}
    fmov d0, x2
    fcvtzs x2, d0
.L{p}fast_f64_exec:
    cbz w8, .L{p}fast_f64_do_or
    cmp w8, #5
    b.eq .L{p}fast_f64_do_and
    cmp w8, #1
    b.eq .L{p}fast_f64_do_xor
    cmp w8, #2
    b.eq .L{p}fast_f64_do_shl
    cmp w8, #3
    b.eq .L{p}fast_f64_do_sar
    lsr w0, w0, w2
    tbnz w0, #31, .Lfast_shr_uint32
    b .L{p}fast_f64_commit
.L{p}fast_f64_do_or:
    orr w0, w0, w2
    b .L{p}fast_f64_commit
.L{p}fast_f64_do_and:
    and w0, w0, w2
    b .L{p}fast_f64_commit
.L{p}fast_f64_do_xor:
    eor w0, w0, w2
    b .L{p}fast_f64_commit
.L{p}fast_f64_do_shl:
    lsl w0, w0, w2
    b .L{p}fast_f64_commit
.L{p}fast_f64_do_sar:
    asr w0, w0, w2
.L{p}fast_f64_commit:
    stp x0, xzr, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
{big_f64_ext}#endif
""")
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"
    return text, "\n".join(islands)
