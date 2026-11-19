"""Indexed, borrow, stack, global, and iterator fast paths for ARM64 Fast VM."""

import re

from arm64.vm.specialize import _replace_exact


def _specialize_indexed_and_borrows(text, f32_id, f64_id):
    islands = []
    for p in ("", "pub_"):
        text = _replace_exact(
            text,
            f".L{p}indexed_instanceof:\n"
            "    ldr x0, [x26, #ARM_OFF_JSFunctionBytecode_realm]\n"
            "    mov x1, x21\n"
            "    bl JS_FrameSlowDirectTryInstanceOfLeaf\n",
            f".L{p}indexed_instanceof:\n"
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    mov x0, x19\n"
            "    mov x1, x21\n"
            "    bl JS_FastInstanceOf\n"
            "#else\n"
            "    ldr x0, [x26, #ARM_OFF_JSFunctionBytecode_realm]\n"
            "    mov x1, x21\n"
            "    bl JS_FrameSlowDirectTryInstanceOfLeaf\n"
            "#endif\n",
            1,
            f"{p}indexed_instanceof IC",
        )
        if not p:
            text = _replace_exact(
                text,
                ".Lindexed_get_array_el_own:\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_get_array_el_fallback\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_get_array_el_fallback\n"
                "    tbnz w2, #31, .Lindexed_get_array_el_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                ".Lindexed_get_array_el_own:\n"
                "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_get_array_el_fallback\n"
                "#else\n"
                "    ldr w16, [sp, #ARM_VM_POLICY_OFF]\n"
                "    tbz w16, #28, .Lindexed_get_array_el_fallback\n"
                "#endif\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_get_array_el_fallback\n"
                ".Lindexed_get_array_el_own_hash:\n"
                "    tbnz w2, #31, .Lindexed_get_array_el_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                1,
                "indexed_get_array_el_own hash & direct probe",
            )
            text = _replace_exact(
                text,
                ".Lindexed_get_array_el2_own:\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_get_array_el2_fallback\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_get_array_el2_fallback\n"
                "    tbnz w2, #31, .Lindexed_get_array_el2_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                ".Lindexed_get_array_el2_own:\n"
                "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_get_array_el2_fallback\n"
                "#else\n"
                "    ldr w16, [sp, #ARM_VM_POLICY_OFF]\n"
                "    tbz w16, #28, .Lindexed_get_array_el2_fallback\n"
                "#endif\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_get_array_el2_fallback\n"
                "    tbnz w2, #31, .Lindexed_get_array_el2_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                1,
                "indexed_get_array_el2_own direct probe",
            )
            text = _replace_exact(
                text,
                ".Lindexed_put_array_el_own:\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_put_array_el_fallback\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_put_array_el_fallback\n"
                "    tbnz w2, #31, .Lindexed_put_array_el_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                ".Lindexed_put_array_el_own:\n"
                "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
                "    adrp x12, JS_FrameSlowDirectData\n"
                "    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]\n"
                "    tbnz w16, #4, .Lindexed_put_array_el_fallback\n"
                "#else\n"
                "    ldr w16, [sp, #ARM_VM_POLICY_OFF]\n"
                "    tbz w16, #28, .Lindexed_put_array_el_fallback\n"
                "#endif\n"
                "    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]\n"
                "    tst w5, #ARM_BIT_JSObject_fast_array_MASK\n"
                "    b.ne .Lindexed_put_array_el_fallback\n"
                ".Lindexed_put_array_el_own_hash:\n"
                "    tbnz w2, #31, .Lindexed_put_array_el_fallback\n"
                "    ldr x5, [x0, #ARM_OFF_JSObject_shape]\n",
                1,
                "indexed_put_array_el_own hash & direct probe",
            )

        old_get = f"""    cmp w4, #ARM_CONST_JS_CLASS_UINT8C_ARRAY
    b.eq .L{p}indexed_get_array_el_u8
    b .L{p}indexed_get_array_el_fallback"""
        new_get = f"""    cmp w4, #ARM_CONST_JS_CLASS_UINT8C_ARRAY
    b.eq .L{p}indexed_get_array_el_u8
    cmp w4, #{f64_id}
    b.eq .L{p}indexed_get_array_el_f64
    cmp w4, #{f32_id}
    b.eq .L{p}indexed_get_array_el_f32"""
        if not p:
            new_get += """
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.eq .Lfast_obj_get_el_own
#endif"""
        new_get += f"""
    b .L{p}indexed_get_array_el_fallback"""
        text = _replace_exact(text, old_get, new_get, 1, f"{p}indexed_get_array_el_typed")

        old_put = f"""    cmp w4, #ARM_CONST_JS_CLASS_UINT16_ARRAY
    b.eq .L{p}indexed_put_array_el_u16
    b .L{p}indexed_put_array_el_fallback"""
        new_put = f"""    cmp w4, #ARM_CONST_JS_CLASS_UINT16_ARRAY
    b.eq .L{p}indexed_put_array_el_u16
    cmp w4, #{f64_id}
    b.eq .L{p}indexed_put_array_el_f64
    cmp w4, #{f32_id}
    b.eq .L{p}indexed_put_array_el_f32"""
        if not p:
            new_put += """
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.eq .Lfast_obj_put_el_own
#endif"""
        new_put += f"""
    b .L{p}indexed_put_array_el_fallback"""
        text = _replace_exact(text, old_put, new_put, 1, f"{p}indexed_put_array_el_typed")

        islands.append(f"""#if ARM_HAS_INDEXED
.L{p}indexed_get_array_el_f64:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .L{p}indexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr d0, [x5, w2, uxtw #3]
    b .L{p}indexed_get_array_el_fp_box
.L{p}indexed_get_array_el_f32:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .L{p}indexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr s0, [x5, w2, uxtw #2]
    fcvt d0, s0
.L{p}indexed_get_array_el_fp_box:
    fmov x6, d0
    mov x7, #ARM_CONST_JS_TAG_FLOAT64
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldr w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    str w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.L{p}indexed_put_array_el_f64:
    ldp x6, x7, [x21, #-16]
    cbz x7, .L{p}indexed_put_f64_int
    cmp x7, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}indexed_put_array_el_fallback
    fmov d0, x6
    b .L{p}indexed_put_f64_check
.L{p}indexed_put_f64_int:
    scvtf d0, w6
.L{p}indexed_put_f64_check:
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .L{p}indexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .L{p}indexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    str d0, [x5, w2, uxtw #3]
    b .L{p}indexed_put_fp_done

.L{p}indexed_put_array_el_f32:
    ldp x6, x7, [x21, #-16]
    cbz x7, .L{p}indexed_put_f32_int
    cmp x7, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .L{p}indexed_put_array_el_fallback
    fmov d0, x6
    b .L{p}indexed_put_f32_check
.L{p}indexed_put_f32_int:
    scvtf d0, w6
.L{p}indexed_put_f32_check:
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .L{p}indexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .L{p}indexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    fcvt s0, d0
    str s0, [x5, w2, uxtw #2]
.L{p}indexed_put_fp_done:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldr w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    str w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
#endif
""")
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"

        # Zero-miss-penalty inline filter for borrowed get_field, get_array_el (1B & 2B idx), and put_array_el (1B & 2B idx)!
        for name, width in (("get_loc_short", 1), ("get_arg_short", 1), ("get_loc8", 2)):
            stem = f".L{p}valueflow_reference_{name}"
            old_ref = f"""    ldrb w14, [x20, #{width}]
    cmp w14, #ARM_OP_get_field
    b.ne {stem}_dup"""
            new_ref = f"""    ldrb w14, [x20, #{width}]
    cmp w14, #ARM_OP_get_field
    b.eq {stem}_field
"""
            if not p:
                lit_pf = (
                    "    sub w15, w14, #ARM_OP_undefined\n"
                    "    cmp w15, #4\n"
                    "    b.ls .Lfast_ref_lit_pf_chk\n"
                    if width == 1
                    else ""
                )
                new_ref += f"""#ifndef QJS_AARCH64_VM_INSTRUMENT
#if ARM_HAS_PROPERTY_IC
    cmp w14, #ARM_OP_get_field2
    b.eq .Lfast_ref_gf2_w{width}
{lit_pf}#endif
#endif
"""
            pf_chk1 = (
                """#ifndef QJS_AARCH64_VM_INSTRUMENT
#if ARM_HAS_PROPERTY_IC
    cmp w15, #ARM_OP_put_field
    b.eq .Lfast_ref_put_field
#endif
#endif
"""
                if not p and width == 1
                else ""
            )
            pf_chk2 = (
                """#ifndef QJS_AARCH64_VM_INSTRUMENT
#if ARM_HAS_PROPERTY_IC
    cmp w16, #ARM_OP_put_field
    b.eq .Lfast_ref_put_field2
#endif
#endif
"""
                if not p and width == 1
                else ""
            )
            if not p and width == 1:
                hi_br = (
                    f"#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
                    f"    b.hi {stem}_chk_null\n"
                    f"#else\n"
                    f"    b.hi {stem}_dup\n"
                    f"#endif"
                )
            else:
                hi_br = f"    b.hi {stem}_dup"
            tail_chk = (
                f"""#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w14, w9
    b.eq .Lfast_ref_same_reg_gf
    b {stem}_dup
{stem}_chk_null:
    sub w15, w14, #ARM_OP_is_undefined
    cmp w15, #1
    b.ls .Lfast_ref_is_null_w1
#endif
"""
                if not p and width == 1
                else ""
            )
            new_ref += f"""#if ARM_HAS_INDEXED
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #33
{hi_br}
    ldrb w15, [x20, #{width + 1}]
    cmp w15, #ARM_OP_get_array_el
    b.eq .Lfast_borrow_arr_get_w{width}
{pf_chk1}    ldrb w16, [x20, #{width + 2}]
    cmp w16, #ARM_OP_get_array_el
    b.eq .Lfast_borrow_arr_get2_w{width}
    cmp w16, #ARM_OP_put_array_el
    b.eq .Lfast_borrow_arr_put1_w{width}
{pf_chk2}#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w15, #ARM_OP_post_inc
    b.eq .Lfast_borrow_arr_postinc_w{width}
#endif
    ldrb w17, [x20, #{width + 3}]
    cmp w17, #ARM_OP_put_array_el
    b.eq .Lfast_borrow_arr_put2_w{width}
{tail_chk}#endif
    b {stem}_dup
{stem}_field:"""
            text = _replace_exact(text, old_ref, new_ref, 1, f"{p}{name} zero-miss borrow hook")

    # Shared Clean/Dirty borrow array-get & array-put islands (never call C, preserve x25 automatically!)
    for width in (1, 2):
        ref_put_field_asm = (
            """
.Lfast_ref_same_reg_gf:
    cmp w15, #ARM_OP_get_field
    b.ne .Lfast_borrow_miss_w1
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x21], #16
    mov x0, x10
    mov x1, x11
    add x20, x20, #2
    b .Lproperty_borrow_entry

.Lfast_ref_is_null_w1:
    ldrb w15, [x10, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tbnz w15, #7, .Lfast_borrow_miss_w1
    ldrb w15, [x20, #2]
    cmp w15, #ARM_OP_if_false8
    b.eq .Lfast_ref_is_null_f8
    cmp w15, #ARM_OP_if_true8
    b.eq .Lfast_ref_is_null_t8
    mov x12, #ARM_CONST_JS_TAG_BOOL
    stp xzr, x12, [x21], #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 2
.Lfast_ref_is_null_f8:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #1, .Lfast_borrow_miss_w1
    ldrsb x14, [x20, #3]
    tbz x14, #63, .Lfast_ref_is_null_f8_jmp
    ldr x12, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w15, [x12, #ARM_OFF_JSContext_interrupt_counter]
    subs w15, w15, #1
    b.le .Lfast_borrow_miss_w1
    str w15, [x12, #ARM_OFF_JSContext_interrupt_counter]
.Lfast_ref_is_null_f8_jmp:
    add x20, x20, #3
    add x20, x20, x14
    ARM_DISPATCH_NEXT 3
.Lfast_ref_is_null_t8:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #1, .Lfast_borrow_miss_w1
    add x20, x20, #4
    ARM_DISPATCH_NEXT 3

.Lfast_ref_lit_pf_chk:
    cmp w14, #ARM_OP_push_this
    b.eq .Lfast_borrow_miss_w1
    ldrb w15, [x20, #2]
    cmp w15, #ARM_OP_put_field
    b.ne .Lfast_borrow_miss_w1
.Lfast_ref_put_field:
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_rpf_chk_arg
    add x15, x23, w15, uxtw #4
    ldp x2, x3, [x15]
    cmp x3, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_borrow_miss_w1
    b .Lfast_rpf_val_ok
.Lfast_rpf_chk_arg:
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_rpf_chk_pint
    ldrh w9, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w15, w9
    b.hs .Lfast_borrow_miss_w1
    add x15, x24, w15, uxtw #4
    ldp x2, x3, [x15]
    b .Lfast_rpf_val_ok
.Lfast_rpf_chk_pint:
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_rpf_chk_undef
    sub w2, w14, #ARM_OP_push_0
    sxtw x2, w2
    mov x3, #0
    b .Lfast_rpf_val_ok
.Lfast_rpf_chk_undef:
    cmp w14, #ARM_OP_undefined
    b.ne .Lfast_rpf_chk_null
    mov x2, #0
    mov x3, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lfast_rpf_val_ok
.Lfast_rpf_chk_null:
    cmp w14, #ARM_OP_null
    b.ne .Lfast_rpf_chk_bool
    mov x2, #0
    mov x3, #ARM_CONST_JS_TAG_NULL
    b .Lfast_rpf_val_ok
.Lfast_rpf_chk_bool:
    sub w15, w14, #ARM_OP_push_false
    cmp w15, #1
    b.ls .Lfast_rpf_bool_ok
    ldrb w16, [x20, #3]
    cmp w16, #ARM_OP_put_field
    b.eq .Lfast_ref_put_field2
    b .Lfast_borrow_miss_w1
.Lfast_rpf_bool_ok:
    mov w2, w15
    mov x3, #ARM_CONST_JS_TAG_BOOL
.Lfast_rpf_val_ok:
    add x4, x20, #2
    mov x13, #7
    b .Lfast_rpf_site_check
.Lfast_ref_put_field2:
    cmp w14, #ARM_OP_get_loc8
    b.ne .Lfast_rpf2_chk_i8
    ldrb w15, [x20, #2]
    add x15, x23, w15, uxtw #4
    ldp x2, x3, [x15]
    cmp x3, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_borrow_miss_w1
    add x4, x20, #3
    mov x13, #8
    b .Lfast_rpf_site_check
.Lfast_rpf2_chk_i8:
    cmp w14, #ARM_OP_push_i8
    b.ne .Lfast_borrow_miss_w1
    ldrsb w2, [x20, #2]
    mov w2, w2
    mov x3, #0
    add x4, x20, #3
    mov x13, #8
.Lfast_rpf_site_check:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #2048
    b.eq .Lfast_borrow_miss_w1
    cbnz x27, .Lfast_rpf_x27_ok
    ldr x5, [x26, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x5, #1
    b.ls .Lfast_borrow_miss_w1
    ldr x6, [x26, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    add x5, x5, #ARM_OFF_JSPropertyIC_map
    lsr x9, x6, #2
    sub x27, x5, x9, lsl #3
.Lfast_rpf_x27_ok:
    cmp x27, #1
    b.ls .Lfast_borrow_miss_w1
    cmn x11, #1
    b.ne .Lfast_borrow_miss_w1
    ldrb w9, [x10, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lfast_borrow_miss_w1
    lsr x4, x4, #2
    ldr x5, [x27, x4, lsl #3]
    cbz x5, .Lfast_borrow_miss_w1
    ldr x6, [x10, #ARM_OFF_JSObject_shape]
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    cmp x7, x6
    b.ne .Lfast_borrow_miss_w1
    ldr w12, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w12, #ARM_CONST_JS_IC_REPLACE
    b.ne .Lfast_borrow_miss_w1
    ldr w12, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x10, #ARM_OFF_JSObject_prop]
    add x7, x7, x12, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x16, #63, .Lfast_rpf_new_inc
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lfast_borrow_miss_w1
.Lfast_rpf_new_inc:
    tbz x3, #63, .Lfast_rpf_old_dec
    ldr w9, [x2, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x2, #ARM_REF_COUNT_OFFSET]
.Lfast_rpf_old_dec:
    tbz x16, #63, .Lfast_rpf_store
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
.Lfast_rpf_store:
    stp x2, x3, [x7, #ARM_OFF_JSProperty_u_value]
    add x20, x20, x13
    ARM_DISPATCH_NEXT 3"""
            if width == 1
            else ""
        )
        islands.append(f"""#if ARM_HAS_PROPERTY_IC
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_ref_gf2_w{width}:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #0x800
    b.eq .Lfast_borrow_miss_w{width}
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x21], #16
    mov x0, x10
    mov x1, x11
    mov w17, #2
    add x20, x20, #{width}
    b .Lproperty_receiver_ready{ref_put_field_asm}
#endif
#endif
#if ARM_HAS_INDEXED
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_borrow_arr_postinc_w{width}:
    ldrb w17, [x20, #{width + 3}]
    cmp w17, #ARM_OP_get_array_el
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w16, [x20, #{width + 2}]
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_borrow_pinc_loc_w{width}
    add w17, w15, #ARM_OP_put_arg0
    cmp w16, w17
    b.ne .Lfast_borrow_miss_w{width}
    add x15, x24, w15, uxtw #4
    b .Lfast_borrow_pinc_exec_w{width}
.Lfast_borrow_pinc_loc_w{width}:
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_borrow_miss_w{width}
    add w17, w15, #ARM_OP_put_loc0
    cmp w16, w17
    b.ne .Lfast_borrow_miss_w{width}
    add x15, x23, w15, uxtw #4
.Lfast_borrow_pinc_exec_w{width}:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #0, .Lfast_borrow_miss_w{width}
    tbz w12, #16, .Lfast_borrow_miss_w{width}
    ldp x2, x3, [x15]
    cbnz x3, .Lfast_borrow_miss_w{width}
    adds w8, w2, #1
    b.vs .Lfast_borrow_miss_w{width}
    ldrh w4, [x10, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lfast_borrow_pinc_chk_obj_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lfast_borrow_own_pinc_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    sxtw x8, w8
    str x8, [x15]
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lfast_borrow_pinc_ok_w{width}
    ldr w12, [x6, #ARM_REF_COUNT_OFFSET]
    add w12, w12, #1
    str w12, [x6, #ARM_REF_COUNT_OFFSET]
.Lfast_borrow_pinc_ok_w{width}:
    stp x6, x7, [x21], #16
    add x20, x20, #{width + 4}
    ARM_DISPATCH_NEXT 5
#endif

.Lfast_borrow_arr_get2_w{width}:
    cmp w14, #ARM_OP_push_i8
    b.ne .Lfast_borrow_get2_loc8_w{width}
    ldrsb w2, [x20, #{width + 1}]
    mov x3, #0
    mov x9, #{width + 3}
    b .Lfast_borrow_idx_ready_dyn_w{width}
.Lfast_borrow_get2_loc8_w{width}:
    cmp w14, #ARM_OP_get_loc8
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w15, [x20, #{width + 1}]
    add x15, x23, w15, uxtw #4
    ldp x2, x3, [x15]
    mov x9, #{width + 3}
    b .Lfast_borrow_idx_ready_dyn_w{width}

.Lfast_borrow_arr_get_w{width}:
    mov x9, #{width + 2}
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_borrow_idx_arg_w{width}
    add x15, x23, x15, lsl #4
    ldp x2, x3, [x15]
    b .Lfast_borrow_idx_ready_dyn_w{width}
.Lfast_borrow_idx_arg_w{width}:
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_borrow_idx_const_w{width}
    add x15, x24, x15, lsl #4
    ldp x2, x3, [x15]
    b .Lfast_borrow_idx_ready_dyn_w{width}
.Lfast_borrow_idx_const_w{width}:
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_borrow_miss_w{width}
    sub w2, w14, #ARM_OP_push_0
    sxtw x2, w2
    mov x3, #0
.Lfast_borrow_idx_ready_dyn_w{width}:
    cbnz x3, .Lfast_borrow_miss_w{width}
    ldrh w4, [x10, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lfast_borrow_get_ta_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.eq .Lfast_borrow_own_get_w{width}
#else
    b.eq .Lfast_borrow_miss_w{width}
#endif
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lfast_borrow_arr_get_ok_w{width}
    ldr w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    str w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lfast_borrow_arr_get_ok_w{width}:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    stp x6, x7, [x21], #16
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3
.Lfast_borrow_get_ta_w{width}:
    cmp w4, #ARM_CONST_JS_CLASS_INT32_ARRAY
    b.ne .Lfast_borrow_get_f64_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x5, w2, uxtw #2]
    mov x7, #ARM_CONST_JS_TAG_INT
    b .Lfast_borrow_get_ta_done_w{width}
.Lfast_borrow_get_f64_w{width}:
    cmp w4, #{f64_id}
    b.ne .Lfast_borrow_get_f32_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    ldr d0, [x5, w2, uxtw #3]
    fmov x6, d0
    mov x7, #ARM_CONST_JS_TAG_FLOAT64
    b .Lfast_borrow_get_ta_done_w{width}
.Lfast_borrow_get_f32_w{width}:
    cmp w4, #{f32_id}
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.ne .Lfast_borrow_get_chk_obj_w{width}
#else
    b.ne .Lfast_borrow_miss_w{width}
#endif
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    ldr s0, [x5, w2, uxtw #2]
    fcvt d0, s0
    fmov x6, d0
    mov x7, #ARM_CONST_JS_TAG_FLOAT64
.Lfast_borrow_get_ta_done_w{width}:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21], #16
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3

.Lfast_borrow_arr_put2_w{width}:
    cmp w14, #ARM_OP_push_i8
    b.ne .Lfast_borrow_put2_loc8_w{width}
    ldrsb w2, [x20, #{width + 1}]
    mov x3, #0
    ldrb w16, [x20, #{width + 2}]
    mov x9, #{width + 4}
    b .Lfast_borrow_put_val_w{width}
.Lfast_borrow_put2_loc8_w{width}:
    cmp w14, #ARM_OP_get_loc8
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w15, [x20, #{width + 1}]
    add x15, x23, w15, uxtw #4
    ldp x2, x3, [x15]
    ldrb w16, [x20, #{width + 2}]
    mov x9, #{width + 4}
    b .Lfast_borrow_put_val_w{width}

.Lfast_borrow_arr_put1_w{width}:
    mov x9, #{width + 3}
    ldrb w16, [x20, #{width + 1}]
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_borrow_put1_arg_w{width}
    add x15, x23, x15, lsl #4
    ldp x2, x3, [x15]
    b .Lfast_borrow_put_val_w{width}
.Lfast_borrow_put1_arg_w{width}:
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_borrow_put1_const_w{width}
    add x15, x24, x15, lsl #4
    ldp x2, x3, [x15]
    b .Lfast_borrow_put_val_w{width}
.Lfast_borrow_put1_const_w{width}:
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_borrow_miss_w{width}
    sub w2, w14, #ARM_OP_push_0
    mov x3, #0
.Lfast_borrow_put_val_w{width}:
    cbnz x3, .Lfast_borrow_miss_w{width}
    sub w15, w16, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_borrow_putv_arg_w{width}
    add x15, x23, x15, lsl #4
    ldp x6, x7, [x15]
    b .Lfast_borrow_put_exec_w{width}
.Lfast_borrow_putv_arg_w{width}:
    sub w15, w16, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_borrow_putv_const_w{width}
    add x15, x24, x15, lsl #4
    ldp x6, x7, [x15]
    b .Lfast_borrow_put_exec_w{width}
.Lfast_borrow_putv_const_w{width}:
    sub w15, w16, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_borrow_miss_w{width}
    sub w6, w16, #ARM_OP_push_0
    mov x7, #0
.Lfast_borrow_put_exec_w{width}:
    tbnz x7, #63, .Lfast_borrow_miss_w{width}
    ldrh w4, [x10, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lfast_borrow_put_ta_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.eq .Lfast_borrow_own_put_w{width}
#else
    b.eq .Lfast_borrow_miss_w{width}
#endif
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldr x8, [x5, #8]
    tbnz x8, #63, .Lfast_borrow_miss_w{width}
    stp x6, x7, [x5]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #16]
    add x13, x13, #1
    str x13, [x12, #16]
#endif
    add x20, x20, x9
    ARM_DISPATCH_NEXT 4
.Lfast_borrow_put_ta_w{width}:
    cmp w4, #ARM_CONST_JS_CLASS_INT32_ARRAY
    b.ne .Lfast_borrow_put_f64_w{width}
    cbnz x7, .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lfast_borrow_miss_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    str w6, [x5, w2, uxtw #2]
    b .Lfast_borrow_put_ta_done_w{width}
.Lfast_borrow_put_f64_w{width}:
    cmp w4, #{f64_id}
    b.ne .Lfast_borrow_put_f32_w{width}
    cbz x7, .Lfast_borrow_put_f64_i_w{width}
    cmp x7, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_borrow_miss_w{width}
    fmov d0, x6
    b .Lfast_borrow_put_f64_chk_w{width}
.Lfast_borrow_put_f64_i_w{width}:
    scvtf d0, w6
.Lfast_borrow_put_f64_chk_w{width}:
    ldr x5, [x10, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lfast_borrow_miss_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    str d0, [x5, w2, uxtw #3]
    b .Lfast_borrow_put_ta_done_w{width}
.Lfast_borrow_put_f32_w{width}:
    cmp w4, #{f32_id}
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.ne .Lfast_borrow_put_chk_obj_w{width}
#else
    b.ne .Lfast_borrow_miss_w{width}
#endif
    cbz x7, .Lfast_borrow_put_f32_i_w{width}
    cmp x7, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_borrow_miss_w{width}
    fmov d0, x6
    b .Lfast_borrow_put_f32_chk_w{width}
.Lfast_borrow_put_f32_i_w{width}:
    scvtf d0, w6
.Lfast_borrow_put_f32_chk_w{width}:
    ldr x5, [x10, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lfast_borrow_miss_w{width}
    ldr w5, [x10, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_u_array_u_values]
    fcvt s0, d0
    str s0, [x5, w2, uxtw #2]
.Lfast_borrow_put_ta_done_w{width}:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    add x20, x20, x9
    ARM_DISPATCH_NEXT 4

.Lfast_borrow_miss_w{width}:
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x21], #16
    add x20, x20, #{width}
    ARM_DISPATCH_NEXT 1
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_borrow_pinc_chk_obj_w{width}:
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w5, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lfast_borrow_miss_w{width}
.Lfast_borrow_own_pinc_w{width}:
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tbz w16, #28, .Lfast_borrow_miss_w{width}
    tbnz w2, #31, .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_shape]
    ldr w12, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    and w12, w2, w12
    neg x12, x12
    sub x9, x5, #4
    ldr w12, [x9, x12, lsl #2]
    add x5, x5, #ARM_OFF_JSShape_prop
    orr w9, w2, #0x80000000
.Lfast_borrow_own_pinc_probe_w{width}:
    cbz w12, .Lfast_borrow_miss_w{width}
    add x13, x5, w12, uxtw #3
    ldur w14, [x13, #-4]
    cmp w14, w9
    b.eq .Lfast_borrow_own_pinc_found_w{width}
    ldur w12, [x13, #-8]
    and w12, w12, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lfast_borrow_own_pinc_probe_w{width}
.Lfast_borrow_own_pinc_found_w{width}:
    ldur w14, [x13, #-8]
    tst w14, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lfast_borrow_miss_w{width}
    sub w12, w12, #1
    ldr x5, [x10, #ARM_OFF_JSObject_prop]
    add x5, x5, w12, uxtw #4
    ldp x6, x7, [x5]
    sxtw x8, w8
    str x8, [x15]
    tbz x7, #63, .Lfast_borrow_own_pinc_ok_w{width}
    ldr w12, [x6, #ARM_REF_COUNT_OFFSET]
    add w12, w12, #1
    str w12, [x6, #ARM_REF_COUNT_OFFSET]
.Lfast_borrow_own_pinc_ok_w{width}:
    stp x6, x7, [x21], #16
    add x20, x20, #{width + 4}
    ARM_DISPATCH_NEXT 5

.Lfast_borrow_get_chk_obj_w{width}:
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w5, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lfast_borrow_miss_w{width}
.Lfast_borrow_own_get_w{width}:
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tbz w16, #28, .Lfast_borrow_miss_w{width}
    tbnz w2, #31, .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_shape]
    ldr w12, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    and w12, w2, w12
    neg x12, x12
    sub x14, x5, #4
    ldr w12, [x14, x12, lsl #2]
    add x5, x5, #ARM_OFF_JSShape_prop
    orr w13, w2, #0x80000000
.Lfast_borrow_own_get_probe_w{width}:
    cbz w12, .Lfast_borrow_miss_w{width}
    add x15, x5, w12, uxtw #3
    ldur w16, [x15, #-4]
    cmp w16, w13
    b.eq .Lfast_borrow_own_get_found_w{width}
    ldur w12, [x15, #-8]
    and w12, w12, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lfast_borrow_own_get_probe_w{width}
.Lfast_borrow_own_get_found_w{width}:
    ldur w16, [x15, #-8]
    tst w16, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lfast_borrow_miss_w{width}
    sub w12, w12, #1
    ldr x5, [x10, #ARM_OFF_JSObject_prop]
    add x5, x5, w12, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lfast_borrow_own_get_ok_w{width}
    ldr w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    str w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lfast_borrow_own_get_ok_w{width}:
    stp x6, x7, [x21], #16
    add x20, x20, x9
    ARM_DISPATCH_NEXT 3

.Lfast_borrow_put_chk_obj_w{width}:
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lfast_borrow_miss_w{width}
    ldrb w5, [x10, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w5, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lfast_borrow_miss_w{width}
.Lfast_borrow_own_put_w{width}:
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tbz w16, #28, .Lfast_borrow_miss_w{width}
    tbnz w2, #31, .Lfast_borrow_miss_w{width}
    ldr x5, [x10, #ARM_OFF_JSObject_shape]
    ldr w12, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    and w12, w2, w12
    neg x12, x12
    sub x14, x5, #4
    ldr w12, [x14, x12, lsl #2]
    add x5, x5, #ARM_OFF_JSShape_prop
    orr w13, w2, #0x80000000
.Lfast_borrow_own_put_probe_w{width}:
    cbz w12, .Lfast_borrow_miss_w{width}
    add x15, x5, w12, uxtw #3
    ldur w16, [x15, #-4]
    cmp w16, w13
    b.eq .Lfast_borrow_own_put_found_w{width}
    ldur w12, [x15, #-8]
    and w12, w12, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lfast_borrow_own_put_probe_w{width}
.Lfast_borrow_own_put_found_w{width}:
    ldur w16, [x15, #-8]
    mov w14, #ARM_PROPERTY_DESC_WRITE_MASK
    and w16, w16, w14
    mov w14, #ARM_PROPERTY_DESC_WRITABLE
    cmp w16, w14
    b.ne .Lfast_borrow_miss_w{width}
    sub w12, w12, #1
    ldr x5, [x10, #ARM_OFF_JSObject_prop]
    add x5, x5, w12, uxtw #4
    ldr x8, [x5, #8]
    tbnz x8, #63, .Lfast_borrow_miss_w{width}
    stp x6, x7, [x5]
    add x20, x20, x9
    ARM_DISPATCH_NEXT 4
#endif
#endif
""")

    islands.append("""#if ARM_HAS_INDEXED
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_obj_get_el_own:
    ldrb w5, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w5, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lindexed_get_array_el_fallback
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tst w16, #0x10000000
    b.eq .Lindexed_get_array_el_fallback
    b .Lindexed_get_array_el_own_hash

.Lfast_obj_put_el_own:
    ldrb w5, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w5, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lindexed_put_array_el_fallback
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tst w16, #0x10000000
    b.eq .Lindexed_put_array_el_fallback
    b .Lindexed_put_array_el_own_hash
#endif
#endif
""")

    return text, "\n".join(islands)


def _specialize_stack_and_globals(text, output, op_ids):
    old_check = """    ldr x15, [x12, #8]
    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lslow
    ldp x10, x11, [x21, #-16]
    ldr x15, [x12, #8]"""
    text = text.replace(
        old_check,
        "    ldr x15, [x12, #8]\n"
        "    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED\n"
        "    b.eq .Lslow\n"
        "    ldp x10, x11, [x21, #-16]",
    )
    old_check_pub = old_check.replace(".Lslow", ".Lpub_slow")
    text = text.replace(
        old_check_pub,
        "    ldr x15, [x12, #8]\n"
        "    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED\n"
        "    b.eq .Lpub_slow\n"
        "    ldp x10, x11, [x21, #-16]",
    )

    # Last-ref drop via JS_FrameInterpFree (RegExp 130k, string_slice1..3 600k)
    for p in ("", "pub_"):
        old_drop = f""".L{p}drop:
    ldp x10, x11, [x21, #-16]
    tbz x11, #63, .L{p}drop_commit
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .L{p}slow"""
        new_drop = f""".L{p}drop:
    ldp x10, x11, [x21, #-16]
    tbz x11, #63, .L{p}drop_commit
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .L{p}fast_drop_last"""
        text = _replace_exact(text, old_drop, new_drop, 1, f"{p}drop")

    disp_path = output / "interpreter-aarch64-dispatch.inc"
    disp_lines = disp_path.read_text().splitlines()
    if len(disp_lines) != 256:
        raise ValueError("Unexpected line count in interpreter-aarch64-dispatch.inc")

    pub_path = output / "interpreter-aarch64-publication-tables.inc"
    pub_lines = pub_path.read_text().splitlines()
    clean_idx = pub_lines.index("qjs_aarch64_publish_clean:")
    dirty_idx = pub_lines.index("qjs_aarch64_publish_dirty:")

    def bind_shared(op_name, label):
        slot = op_ids[op_name]
        disp_lines[slot] = f".word {label} - .Ldispatch_table"
        pub_lines[clean_idx + 1 + slot] = f"    .word {label} - qjs_aarch64_publish_clean"
        pub_lines[dirty_idx + 1 + slot] = f"    .word {label} - qjs_aarch64_publish_dirty"

    def bind_dual(op_name, base_label):
        slot = op_ids[op_name]
        disp_lines[slot] = f".word .L{base_label} - .Ldispatch_table"
        pub_lines[clean_idx + 1 + slot] = f"    .word .L{base_label} - qjs_aarch64_publish_clean"
        pub_lines[dirty_idx + 1 + slot] = (
            f"    .word .Lpub_{base_label} - qjs_aarch64_publish_dirty"
        )

    # 1. Pure non-calling shared handlers that were .Lslow in R76 (Original == Clean == Dirty)
    for op_name, label in (
        ("dup1", ".Lfast_dup1"),
        ("dup2", ".Lfast_dup2"),
        ("perm3", ".Lfast_perm3"),
        ("rot3r", ".Lfast_rot3r"),
    ):
        bind_shared(op_name, label)

    # 2. Dedicated Clean/Dirty handlers that were .Lslow in R76 (Original == Clean == .L*, Dirty == .Lpub_*)
    for op_name, base_label in (
        ("nip", "fast_nip"),
        ("put_var", "fast_put_var"),
        ("to_object", "fast_to_object"),
        ("typeof", "fast_typeof"),
    ):
        bind_dual(op_name, base_label)

    disp_path.write_text("\n".join(disp_lines) + "\n")
    pub_path.write_text("\n".join(pub_lines) + "\n")

    # Wait-free Release hooks: OP_array_from & OP_get_field in .Lslow, virtual arguments, get_var x27+borrow, ALU+store, push_int ALU, lnot+br, post_inc+store
    text = _replace_exact(
        text,
        ".Lslow:\n"
        "    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]\n"
        "    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]\n"
        "    mov x0, x19\n",
        ".Lslow:\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldrb w9, [x20]\n"
        f"    cmp w9, #{op_ids['array_from']}\n"
        "    b.eq .Lfast_array_from\n"
        "    cmp w9, #ARM_OP_get_field\n"
        "    b.eq .Lfast_c_get_field\n"
        ".Lslow_no_arr:\n"
        "#endif\n"
        "    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]\n"
        "    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]\n"
        ".Lslow_call_c:\n"
        "    mov x0, x19\n",
        1,
        "slow array_from & get_field hook",
    )
    text = _replace_exact(
        text,
        "    cmp x1, #ARM_CONST_JS_TAG_OBJECT\n"
        "    b.ne .Lslow\n"
        "    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]\n"
        "    cmp w9, #ARM_CONST_JS_CLASS_ARRAY\n"
        "    b.ne .Lslow\n",
        "    cmp x1, #ARM_CONST_JS_TAG_OBJECT\n"
        "    b.ne .Lslow\n"
        "    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]\n"
        "    cmp w9, #ARM_CONST_JS_CLASS_ARRAY\n"
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    b.ne .Lslow\n"
        "#else\n"
        "    b.ne .Lfast_ta_get_length\n"
        "#endif\n",
        1,
        "get_length typed_array hook",
    )
    text = _replace_exact(
        text,
        ".Larguments_object:\n"
        "    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]\n"
        "    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]\n"
        "    mov x0, x19\n"
        "    bl JS_FrameArgumentsStep\n",
        ".Larguments_object:\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldrb w9, [x22, #ARM_FRAME_ROOT_OFFSET]\n"
        "    cmp w9, #3\n"
        "    b.eq .Lfast_virt_args_entry\n"
        ".Lfast_virt_args_orig:\n"
        "#endif\n"
        "    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]\n"
        "    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]\n"
        "    mov x0, x19\n"
        "    bl JS_FrameArgumentsStep\n",
        1,
        "arguments_object virtual_arguments fast entry",
    )
    text = _replace_exact(
        text,
        ".Lget_arg:\n"
        "    ldurh w10, [x20, #1]\n"
        "    add x12, x24, x10, lsl #4\n"
        "    ldp x10, x11, [x12]\n"
        "    tbnz x11, #63, .Lvalueflow_reference_get_arg\n",
        ".Lget_arg:\n"
        "    ldurh w16, [x20, #1]\n"
        "    add x12, x24, x16, lsl #4\n"
        "    ldp x10, x11, [x12]\n"
        "    tbnz x11, #63, .Lvalueflow_reference_get_arg\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldrb w14, [x20, #3]\n"
        "    cmp w14, #ARM_OP_dec\n"
        "    b.eq .Lfast_get_arg_dec\n"
        "#endif\n",
        1,
        "get_arg + dec loop hook",
    )
    text = _replace_exact(
        text,
        ".Lglobal_cell_probe:\n"
        "    mov x11, x26\n"
        "    ldr x0, [x11, #ARM_OFF_JSFunctionBytecode_realm]\n"
        "#if ARM_HAS_PROPERTY_IC\n"
        "    ldr x2, [x11, #ARM_OFF_JSFunctionBytecode_property_ic]\n",
        ".Lglobal_cell_probe:\n"
        "    mov x11, x26\n"
        "    ldr x0, [x11, #ARM_OFF_JSFunctionBytecode_realm]\n"
        "#if ARM_HAS_PROPERTY_IC\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    cmp x27, #1\n"
        "    b.ls .Lfast_glob_ic_slow\n"
        "    lsr x3, x20, #2\n"
        "    ldr x3, [x27, x3, lsl #3]\n"
        "    tbnz x3, #0, .Lglobal_cell_hit\n"
        "    cbz x3, .Lglobal_cell_relink\n"
        "    b .Lglobal_after_cell\n"
        ".Lfast_glob_ic_slow:\n"
        "#endif\n"
        "    ldr x2, [x11, #ARM_OFF_JSFunctionBytecode_property_ic]\n",
        1,
        "global_cell_probe x27 reuse",
    )
    text = _replace_exact(
        text,
        "    ldr x2, [x11, #ARM_OFF_JSFunctionBytecode_property_ic]\n"
        "    cmp x2, #1\n"
        "    b.hi .Lglobal_cell_metadata\n"
        "    b.eq .Lglobal_after_cell\n",
        "    ldr x2, [x11, #ARM_OFF_JSFunctionBytecode_property_ic]\n"
        "    cmp x2, #1\n"
        "    b.hi .Lglobal_cell_metadata\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    b.ne .Lfast_glob_ic_mode\n"
        "    mov x27, #1\n"
        "    b .Lglobal_after_cell\n"
        ".Lfast_glob_ic_mode:\n"
        "#else\n"
        "    b.eq .Lglobal_after_cell\n"
        "#endif\n",
        1,
        "global_cell_probe mark x27=1",
    )
    text = _replace_exact(
        text,
        ".Lglobal_cell_metadata:\n"
        "    ldr x3, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_buf]\n"
        "    sub x3, x20, x3\n"
        "    lsr x3, x3, #2\n"
        "    add x2, x2, #ARM_OFF_JSPropertyIC_map\n"
        "    ldr x3, [x2, x3, lsl #3]\n",
        ".Lglobal_cell_metadata:\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldr x4, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_buf]\n"
        "    add x3, x2, #ARM_OFF_JSPropertyIC_map\n"
        "    lsr x9, x4, #2\n"
        "    sub x27, x3, x9, lsl #3\n"
        "    lsr x3, x20, #2\n"
        "    ldr x3, [x27, x3, lsl #3]\n"
        "#else\n"
        "    ldr x3, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_buf]\n"
        "    sub x3, x20, x3\n"
        "    lsr x3, x3, #2\n"
        "    add x2, x2, #ARM_OFF_JSPropertyIC_map\n"
        "    ldr x3, [x2, x3, lsl #3]\n"
        "#endif\n",
        1,
        "global_cell_metadata populate x27",
    )
    text = _replace_exact(
        text,
        ".Lglobal_cell_ready:\n    ARM_GLOBAL_EVENT 0\n    cbnz w16, .Lglobal_symbol_condition\n",
        ".Lglobal_cell_ready:\n"
        "    ARM_GLOBAL_EVENT 0\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    cmn x13, #1\n"
        "    b.eq .Lfast_global_borrow_gf\n"
        "#endif\n"
        "    cbnz w16, .Lglobal_symbol_condition\n",
        1,
        "global_cell_ready get_field borrow",
    )
    text = _replace_exact(
        text,
        ".Lstack_insert3:\n"
        "    adrp x9, JS_FrameSlowDirectData\n"
        "    add x9, x9, :lo12:JS_FrameSlowDirectData\n"
        "    ldrb w9, [x9, #ARM_OFF_JSFrameSlowDirectData_mode]\n"
        "    tbnz w9, #5, .Lslow\n",
        ".Lstack_insert3:\n"
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    adrp x9, JS_FrameSlowDirectData\n"
        "    add x9, x9, :lo12:JS_FrameSlowDirectData\n"
        "    ldrb w9, [x9, #ARM_OFF_JSFrameSlowDirectData_mode]\n"
        "    tbnz w9, #5, .Lslow\n"
        "#else\n"
        "    ldr w9, [sp, #ARM_VM_POLICY_OFF]\n"
        "    tbz w9, #23, .Lslow\n"
        "#endif\n",
        1,
        "stack_insert3 policy bit 23",
    )
    text = _replace_exact(
        text,
        ".Lget_length_original:\n"
        "#endif\n"
        "    ldr w9, [sp, #ARM_VM_POLICY_OFF]\n"
        "    tbz w9, #13, .Lslow\n"
        "    adrp x9, JS_FrameLengthData\n"
        "    add x9, x9, :lo12:JS_FrameLengthData\n"
        "    ldarb w9, [x9]\n"
        "    cmp w9, #1\n"
        "    b.ne .Lslow\n",
        ".Lget_length_original:\n"
        "#endif\n"
        "    ldr w9, [sp, #ARM_VM_POLICY_OFF]\n"
        "    tbz w9, #13, .Lslow\n"
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    adrp x9, JS_FrameLengthData\n"
        "    add x9, x9, :lo12:JS_FrameLengthData\n"
        "    ldarb w9, [x9]\n"
        "    cmp w9, #1\n"
        "    b.ne .Lslow\n"
        "#else\n"
        "    tbz w9, #29, .Lslow\n"
        "#endif\n",
        1,
        "get_length_original policy bit 29",
    )
    text = _replace_exact(
        text,
        ".Lliteral_truth_lnot_primitive:\n    eor w6, w6, #1\n    mov x7, #ARM_CONST_JS_TAG_BOOL\n",
        ".Lliteral_truth_lnot_primitive:\n"
        "    eor w6, w6, #1\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldrb w15, [x20, #1]\n"
        "    sub w16, w15, #ARM_OP_if_false8\n"
        "    cmp w16, #1\n"
        "    b.ls .Lfast_lnot_branch\n"
        ".Lfast_lnot_unfused:\n"
        "#endif\n"
        "    mov x7, #ARM_CONST_JS_TAG_BOOL\n",
        1,
        "lnot branch fuse",
    )
    text = _replace_exact(
        text,
        ".Lscalar_post_commit:\n    stp x0, x1, [x21], #16\n",
        ".Lscalar_post_commit:\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    tst w12, #1\n"
        "    b.ne .Lfast_post_store_fuse\n"
        ".Lfast_post_unfused:\n"
        "#endif\n"
        "    stp x0, x1, [x21], #16\n",
        1,
        "post_inc/dec store fuse",
    )
    for k, disp in (("known_", ".Lpub_dispatch"), ("", ".Ldispatch"), ("pub_", ".Lpub_dispatch")):
        text = _replace_exact(
            text,
            f".L{k}linear_return_caller_done:\n"
            "    and w9, w28, #0x7fff\n"
            "    sub x21, x24, x9, lsl #4\n"
            "    strh wzr, [x22, #ARM_OFF_JSFrame_pending]\n"
            "    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]\n"
            "    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]\n"
            f"    tbnz w28, #15, .L{k}linear_return_tail_parent\n"
            "    stp x0, x1, [x21], #16\n"
            f"    b {disp}\n",
            f".L{k}linear_return_caller_done:\n"
            "    and w9, w28, #0x7fff\n"
            "    sub x21, x24, x9, lsl #4\n"
            "    strh wzr, [x22, #ARM_OFF_JSFrame_pending]\n"
            "    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]\n"
            "    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]\n"
            f"    tbnz w28, #15, .L{k}linear_return_tail_parent\n"
            "    stp x0, x1, [x21], #16\n"
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    ldr x3, [x26, #ARM_OFF_JSFunctionBytecode_property_ic]\n"
            "    cmp x3, #1\n"
            f"    b.ls .L{k}linear_ret_ic_done\n"
            "    ldr x4, [x26, #ARM_OFF_JSFunctionBytecode_byte_code_buf]\n"
            "    add x3, x3, #ARM_OFF_JSPropertyIC_map\n"
            "    lsr x9, x4, #2\n"
            "    sub x27, x3, x9, lsl #3\n"
            f".L{k}linear_ret_ic_done:\n"
            "#endif\n"
            f"    b {disp}\n",
            1,
            f"{k}linear_return caller x27 preload",
        )
    for k in ("", "pub_", "known_"):
        for role in ("callee", "caller"):
            lbl = f".L{k}linear_return_{role}"
            text = _replace_exact(
                text,
                f"{lbl}:\n"
                "    cmp x23, x24\n"
                f"    b.eq {lbl}_done\n"
                "    ldp x10, x11, [x23]\n"
                "    mov x12, #ARM_CONST_JS_TAG_UNDEFINED\n"
                "    stp xzr, x12, [x23], #16\n"
                f"    tbz x11, #63, {lbl}\n",
                f"{lbl}:\n"
                "    cmp x23, x24\n"
                f"    b.eq {lbl}_done\n"
                "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
                "    ldp x10, x11, [x23]\n"
                "    mov x12, #ARM_CONST_JS_TAG_UNDEFINED\n"
                "    stp xzr, x12, [x23], #16\n"
                f"    tbz x11, #63, {lbl}\n"
                "#else\n"
                "    ldr x11, [x23, #8]\n"
                "    add x23, x23, #16\n"
                f"    tbz x11, #63, {lbl}\n"
                "    ldr x10, [x23, #-16]\n"
                "    mov x12, #ARM_CONST_JS_TAG_UNDEFINED\n"
                "    stp xzr, x12, [x23, #-16]\n"
                "#endif\n",
                1,
                f"{k}linear_return_{role} primitive skip",
            )

    shared_pushes = [
        """.Lfast_dup1:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    tbz x11, #63, .Lfast_dup1_commit
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
.Lfast_dup1_commit:
    stp x10, x11, [x21, #-16]
    stp x12, x13, [x21], #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.Lfast_dup2:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    tbz x11, #63, .Lfast_dup2_second
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
.Lfast_dup2_second:
    tbz x13, #63, .Lfast_dup2_commit
    ldr w14, [x12, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x12, #ARM_REF_COUNT_OFFSET]
.Lfast_dup2_commit:
    stp x10, x11, [x21]
    stp x12, x13, [x21, #16]
    add x21, x21, #32
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.Lfast_perm3:
    ldp x10, x11, [x21, #-48]
    ldp x12, x13, [x21, #-32]
    stp x12, x13, [x21, #-48]
    stp x10, x11, [x21, #-32]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.Lfast_rot3r:
    ldp x10, x11, [x21, #-16]
    ldp x12, x13, [x21, #-32]
    ldp x14, x15, [x21, #-48]
    stp x12, x13, [x21, #-16]
    stp x14, x15, [x21, #-32]
    stp x10, x11, [x21, #-48]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_ta_get_length:
    sub w10, w9, #22
    cmp w10, #11
    b.hi .Lslow
    ldr w10, [sp, #ARM_VM_POLICY_OFF]
    tst w10, #0x2000
    b.eq .Lslow
    tst w10, #0x20000000
    b.eq .Lslow
    ldr w11, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w11, #1
    b.le .Lslow
    ldr x12, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w13, [x12, #ARM_OFF_JSContext_interrupt_counter]
    cmp w13, #1
    b.le .Lslow
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x15, [x14, #ARM_OFF_JSRuntime_property_ic_epoch]
    cbz x15, .Lslow
    ldr x4, [x0, #ARM_OFF_JSObject_shape]
    lsr x5, x4, #6
    and x5, x5, #3
    adrp x6, .Lfast_ta_len_ic
    add x6, x6, :lo12:.Lfast_ta_len_ic
    add x6, x6, x5, lsl #5
    ldp x7, x8, [x6]
    cmp x7, x4
    b.ne .Lfast_ta_len_miss
    cmp x8, x15
    b.ne .Lfast_ta_len_miss
    ldr x7, [x6, #16]
    cmp x7, x12
    b.ne .Lfast_ta_len_miss
.Lfast_ta_len_hit:
    sub w13, w13, #1
    str w13, [x12, #ARM_OFF_JSContext_interrupt_counter]
    sub w11, w11, #1
    str w11, [x0, #ARM_REF_COUNT_OFFSET]
    ldr w2, [x0, #ARM_OFF_JSObject_u_array_count]
    sxtw x2, w2
    stp x2, xzr, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lfast_ta_len_miss:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x1, x0
    mov x0, x12
    bl JS_FastTypedArrayLenProve
    cbz w0, .Lslow
    ldr x0, [x21, #-16]
    ldr w11, [x0, #ARM_REF_COUNT_OFFSET]
    ldr x4, [x0, #ARM_OFF_JSObject_shape]
    ldr x12, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w13, [x12, #ARM_OFF_JSContext_interrupt_counter]
    ldr x14, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x15, [x14, #ARM_OFF_JSRuntime_property_ic_epoch]
    lsr x5, x4, #6
    and x5, x5, #3
    adrp x6, .Lfast_ta_len_ic
    add x6, x6, :lo12:.Lfast_ta_len_ic
    add x6, x6, x5, lsl #5
    stp x4, x15, [x6]
    str x12, [x6, #16]
    b .Lfast_ta_len_hit

.Lfast_array_from:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    adrp x10, qjs_aarch64_publish_clean
    add x10, x10, :lo12:qjs_aarch64_publish_clean
    cmp x25, x10
    b.eq 1f
    adrp x11, qjs_aarch64_publish_dirty
    add x11, x11, :lo12:qjs_aarch64_publish_dirty
    cmp x25, x11
    b.ne 1f
    mov x25, x10
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
1:
    mov x0, x19
    bl JS_FastArrayFrom
    cbnz w0, .Lslow_call_c
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 1

.Lfast_virt_args_entry:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    adrp x10, qjs_aarch64_publish_clean
    add x10, x10, :lo12:qjs_aarch64_publish_clean
    cmp x25, x10
    b.eq 1f
    adrp x11, qjs_aarch64_publish_dirty
    add x11, x11, :lo12:qjs_aarch64_publish_dirty
    cmp x25, x11
    b.ne 1f
    mov x25, x10
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
1:
    mov x0, x19
    bl JS_LinuxVirtualArgumentsStep
    cmp w0, #0
    b.gt .Lreload
    b.lt .Lslow_no_arr
    mov x0, x19
    bl JS_FrameArgumentsStep
    cbz w0, .Lreload
    b .Ldone

.Lfast_global_borrow_gf:
    ldrb w9, [x20, #5]
    cmp w9, #ARM_OP_get_field
    b.ne .Lfast_global_borrow_gf2
    mov x0, x12
    mov x1, x13
    add x20, x20, #5
    b .Lproperty_borrow_entry
.Lfast_global_borrow_gf2:
    cmp w9, #ARM_OP_get_field2
    b.ne .Lglobal_ready
    ldr w10, [sp, #ARM_VM_POLICY_OFF]
    tst w10, #0x800
    b.eq .Lglobal_ready
    ldr w9, [x12, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x12, #ARM_REF_COUNT_OFFSET]
    stp x12, x13, [x21], #16
    mov x0, x12
    mov x1, x13
    mov w17, #2
    add x20, x20, #5
    b .Lproperty_receiver_ready

.Lfast_lnot_branch:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tst w14, #2
    b.eq .Lfast_lnot_unfused
    ldrsb x14, [x20, #2]
    tbnz x14, #63, .Lfast_lnot_bwd
.Lfast_lnot_do:
    sub x21, x21, #16
    cmp w6, w16
    b.eq .Lfast_lnot_taken
    add x20, x20, #3
    ARM_DISPATCH_NEXT 2
.Lfast_lnot_taken:
    add x20, x20, #2
    add x20, x20, x14
    ARM_DISPATCH_NEXT 2
.Lfast_lnot_bwd:
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w9, w9, #1
    b.le .Lfast_lnot_unfused
    str w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    b .Lfast_lnot_do

.Lfast_post_store_fuse:
    ldrb w15, [x20, #1]
    sub w16, w15, #ARM_OP_put_arg0
    cmp w16, #3
    b.hi .Lfast_post_chk_loc0
    ldrh w17, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w16, w17
    b.hs .Lfast_post_unfused
    add x12, x24, w16, uxtw #4
    mov x14, #2
    b .Lfast_post_chk_slot
.Lfast_post_chk_loc0:
    sub w16, w15, #ARM_OP_put_loc0
    cmp w16, #3
    b.hi .Lfast_post_chk_loc8
    add x12, x23, w16, uxtw #4
    mov x14, #2
    b .Lfast_post_chk_slot
.Lfast_post_chk_loc8:
    cmp w15, #ARM_OP_put_loc8
    b.ne .Lfast_post_chk_arg16
    ldrb w16, [x20, #2]
    add x12, x23, w16, uxtw #4
    mov x14, #3
    b .Lfast_post_chk_slot
.Lfast_post_chk_arg16:
    cmp w15, #ARM_OP_put_arg
    b.ne .Lfast_post_unfused
    ldurh w16, [x20, #2]
    ldrh w17, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w16, w17
    b.hs .Lfast_post_unfused
    add x12, x24, w16, uxtw #4
    mov x14, #4
.Lfast_post_chk_slot:
    ldr x13, [x12, #8]
    cmp x13, #3
    b.ls 4f
    cmp x13, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_post_unfused
4:
    stp x0, x1, [x12]
    add x20, x20, x14
    ARM_DISPATCH_NEXT 2
#endif
""",
        """#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_get_arg_dec:
    cbnz x11, .Lfast_gad_orig
    ldur x14, [x20, #3]
    ubfx x14, x14, #0, #56
    movz x15, #0x5c8d
    bfi x15, x16, #16, #16
    movk x15, #0xa8ba, lsl #32
    movk x15, #0x00f0, lsl #48
    cmp x14, x15
    b.ne .Lfast_gad_orig
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    movz w15, #0x0002
    movk w15, #0x0001, lsl #16
    and w14, w14, w15
    cmp w14, w15
    b.ne .Lfast_gad_orig
    subs w14, w10, #1
    b.vs .Lfast_gad_orig
    b.lt .Lfast_get_arg_dec_exit
    sxtw x14, w14
    str x14, [x12]
    add x20, x20, #11
    ARM_DISPATCH_NEXT 2
.Lfast_gad_orig:
    b .Lvalueflow_commit_get_arg
.Lfast_get_arg_dec_exit:
    ldrsb x15, [x20, #10]
    cmp x15, #0
    b.gt .Lfast_get_arg_dec_branch_commit
    ldr x16, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w17, [x16, #ARM_OFF_JSContext_interrupt_counter]
    subs w17, w17, #1
    b.le .Lfast_gad_orig
    str w17, [x16, #ARM_OFF_JSContext_interrupt_counter]
.Lfast_get_arg_dec_branch_commit:
    sxtw x14, w14
    str x14, [x12]
    add x20, x20, #10
    add x20, x20, x15
    ARM_DISPATCH_NEXT 2
#endif
""",
    ]

    islands = ["\n".join(shared_pushes)]

    for p in ("", "pub_"):
        free_target = (
            "JS_FrameInterpFree" if not p else "qjs_aarch64_publish_before_FrameInterpFree"
        )
        islands.append(f"""
.L{p}fast_to_object:
    ldr x11, [x21, #-8]
    cmn x11, #1
    b.ne .L{p}slow
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.L{p}fast_drop_last:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tst w14, #1
    b.eq .L{p}slow
    mov x2, x10
    mov x3, x11
    sub x21, x21, #16
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x14, [x21]
    add x20, x20, #1
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
#endif
    ldr x1, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    bl {free_target}
    ARM_DISPATCH_NEXT 1

.L{p}fast_nip:
    ldp x10, x11, [x21, #-32]
    tbz x11, #63, .L{p}fast_nip_commit
    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .L{p}fast_nip_last
    sub w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
.L{p}fast_nip_commit:
    ldp x12, x13, [x21, #-16]
    stp x12, x13, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.L{p}fast_nip_last:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tst w14, #1
    b.eq .L{p}slow
    mov x2, x10
    mov x3, x11
    ldp x12, x13, [x21, #-16]
    stp x12, x13, [x21, #-32]
    sub x21, x21, #16
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x14, [x21]
    add x20, x20, #1
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
#endif
    ldr x1, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    bl {free_target}
    ARM_DISPATCH_NEXT 1

.L{p}fast_put_var:
    ldr x0, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldur w8, [x20, #1]
    add x1, x0, #ARM_OFF_JSContext_global_var_obj
    ldp x1, x2, [x1]
    cmn x2, #1
    b.ne .L{p}slow
    ldrh w3, [x1, #ARM_OFF_JSObject_class_id]
    cmp w3, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .L{p}slow
    ldrb w3, [x1, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w3, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}slow
    ldr x3, [x1, #ARM_OFF_JSObject_shape]
    ldr w4, [x3, #ARM_OFF_JSShape_prop_hash_mask]
    and w4, w8, w4
    neg x4, x4
    add x4, x3, x4, lsl #2
    ldur w4, [x4, #-4]
    add x5, x3, #ARM_OFF_JSShape_prop
.L{p}fast_put_var_lex_loop:
    cbz w4, .L{p}fast_put_var_global
    sub w6, w4, #1
    add x6, x5, x6, lsl #3
    ldr w7, [x6, #ARM_OFF_JSShapeProperty_atom]
    cmp w7, w8
    b.eq .L{p}fast_put_var_lex_found
    ldr w4, [x6]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_put_var_lex_loop
.L{p}fast_put_var_lex_found:
    ldr w7, [x6]
    mov w9, #ARM_PROPERTY_DESC_WRITE_MASK
    and w7, w7, w9
    mov w9, #ARM_PROPERTY_DESC_WRITABLE
    cmp w7, w9
    b.ne .L{p}slow
    sub w4, w4, #1
    ldr x2, [x1, #ARM_OFF_JSObject_prop]
    add x2, x2, x4, lsl #4
    ldp x14, x15, [x2]
    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .L{p}slow
    b .L{p}fast_put_var_store
.L{p}fast_put_var_global:
    add x1, x0, #ARM_OFF_JSContext_global_obj
    ldp x1, x2, [x1]
    cmn x2, #1
    b.ne .L{p}slow
    ldrh w3, [x1, #ARM_OFF_JSObject_class_id]
    cmp w3, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .L{p}slow
    ldrb w3, [x1, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w3, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}slow
    ldr x3, [x1, #ARM_OFF_JSObject_shape]
    ldr w4, [x3, #ARM_OFF_JSShape_prop_hash_mask]
    and w4, w8, w4
    neg x4, x4
    add x4, x3, x4, lsl #2
    ldur w4, [x4, #-4]
    add x5, x3, #ARM_OFF_JSShape_prop
.L{p}fast_put_var_glob_loop:
    cbz w4, .L{p}slow
    sub w6, w4, #1
    add x6, x5, x6, lsl #3
    ldr w7, [x6, #ARM_OFF_JSShapeProperty_atom]
    cmp w7, w8
    b.eq .L{p}fast_put_var_glob_found
    ldr w4, [x6]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .L{p}fast_put_var_glob_loop
.L{p}fast_put_var_glob_found:
    ldr w7, [x6]
    mov w9, #ARM_PROPERTY_DESC_WRITE_MASK
    and w7, w7, w9
    mov w9, #ARM_PROPERTY_DESC_WRITABLE
    cmp w7, w9
    b.ne .L{p}slow
    sub w4, w4, #1
    ldr x2, [x1, #ARM_OFF_JSObject_prop]
    add x2, x2, x4, lsl #4
    ldp x14, x15, [x2]
.L{p}fast_put_var_store:
    tbz x15, #63, .L{p}fast_put_var_commit
    ldr w9, [x14, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .L{p}fast_put_var_last
    sub w9, w9, #1
    str w9, [x14, #ARM_REF_COUNT_OFFSET]
.L{p}fast_put_var_commit:
    ldp x10, x11, [x21, #-16]
    sub x21, x21, #16
    stp x10, x11, [x2]
    add x20, x20, #5
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ARM_DISPATCH_NEXT 1
.L{p}fast_put_var_last:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tst w9, #1
    b.eq .L{p}slow
    ldp x10, x11, [x21, #-16]
    stp x10, x11, [x2]
    sub x21, x21, #16
    mov x12, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x12, [x21]
    add x20, x20, #5
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x9, [sp, #136]
    add x9, x9, #1
    str x9, [sp, #136]
#endif
    mov x1, x0
    mov x2, x14
    mov x3, x15
    mov x0, x19
    bl {free_target}
    ARM_DISPATCH_NEXT 1

.L{p}fast_typeof:
    ldp x0, x1, [x21, #-16]
    cbz x1, .L{p}ft_num
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .L{p}ft_num
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.eq .L{p}ft_undef
    cmp x1, #ARM_CONST_JS_TAG_BOOL
    b.eq .L{p}ft_bool
    cmp x1, #ARM_CONST_JS_TAG_NULL
    b.eq .L{p}ft_obj_atom
    cmp x1, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .L{p}ft_bigint
    cmp x1, #0
    b.ge .L{p}slow
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .L{p}slow
    cmn x1, #1
    b.eq .L{p}ft_obj
    cmn x1, #7
    b.eq .L{p}ft_str
    cmn x1, #6
    b.eq .L{p}ft_str
    cmn x1, #8
    b.eq .L{p}ft_sym
    cmn x1, #9
    b.eq .L{p}ft_bigint
    b .L{p}slow
.L{p}ft_obj:
    ldrb w3, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tbnz w3, #7, .L{p}ft_undef
    ldrh w3, [x0, #ARM_OFF_JSObject_class_id]
    cbz w3, .L{p}slow
    sub w4, w3, #1
    cmp w4, #10
    b.ls .L{p}ft_obj_atom
    cmp w3, #17
    b.ls .L{p}ft_func
    cmp w3, #50
    b.ls .L{p}ft_obj_atom
    b .L{p}slow
.L{p}ft_func:
    mov w2, #27
    b .L{p}ft_commit
.L{p}ft_undef:
    mov w2, #73
    b .L{p}ft_commit
.L{p}ft_num:
    mov w2, #74
    b .L{p}ft_commit
.L{p}ft_bool:
    mov w2, #75
    b .L{p}ft_commit
.L{p}ft_str:
    mov w2, #76
    b .L{p}ft_commit
.L{p}ft_obj_atom:
    mov w2, #77
    b .L{p}ft_commit
.L{p}ft_sym:
    mov w2, #78
    b .L{p}ft_commit
.L{p}ft_bigint:
    mov w2, #150
.L{p}ft_commit:
    tbz x1, #63, .L{p}ft_push
    sub w9, w9, #1
    str w9, [x0, #ARM_REF_COUNT_OFFSET]
.L{p}ft_push:
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x3, [x3, #ARM_OFF_JSRuntime_atom_array]
    ldr x3, [x3, w2, uxtw #3]
    ldr w4, [x3, #ARM_REF_COUNT_OFFSET]
    add w4, w4, #1
    str w4, [x3, #ARM_REF_COUNT_OFFSET]
    mov x5, #ARM_CONST_JS_TAG_STRING
    stp x3, x5, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
""")
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"

    return text, "\n".join(islands)


def _specialize_iterators(text, arr_iter_id, cfunc_iter_next):
    islands = []
    for p in ("", "pub_"):
        helper = (
            "JS_LinuxIterator_for_of_next"
            if not p
            else "qjs_aarch64_publish_before_LinuxIterator_for_of_next"
        )
        old_it = f""".L{p}iterator_for_of_next:
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
    bl {helper}
    cbz w0, .L{p}reload
    b .Ldone"""
        new_it = f""".L{p}iterator_for_of_next:
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b .L{p}fast_for_of_next
#else
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    ldr x14, [sp, #128]
    add x14, x14, #1
    str x14, [sp, #128]
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
    bl {helper}
    cbz w0, .L{p}reload
    b .Ldone
#endif"""
        text = _replace_exact(text, old_it, new_it, 1, f"{p}iterator_for_of_next")

        cfunc_island = (
            ""
            if p
            else """
.Lfast_cfunc_for_of_next:
    adrp x10, qjs_aarch64_publish_dirty
    add x10, x10, :lo12:qjs_aarch64_publish_dirty
    cmp x25, x10
    b.ne .Lfast_cfunc_for_of_clean
    adrp x25, qjs_aarch64_publish_clean
    add x25, x25, :lo12:qjs_aarch64_publish_clean
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
.Lfast_cfunc_for_of_clean:
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    bl JS_FastCfuncForOfNext
    cmp w0, #2
    b.ne .Lfast_cfunc_for_of_slow
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 2
.Lfast_cfunc_for_of_slow:
    cbz w0, .Lreload
    b .Ldone
"""
        )
        if p:
            fast_head = f"""#if ARM_HAS_ITERATORS
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_for_of_next:
    ldrb w2, [x22, #ARM_FRAME_FLAGS_OFFSET]
    tbnz w2, #1, .L{p}iterator_for_of_next_c
    ldrb w1, [x26, #116]
    tbz w1, #2, .L{p}iterator_for_of_next_c
    adrp x14, .Lfast_array_iter_fn
    ldr x14, [x14, :lo12:.Lfast_array_iter_fn]
    cbz x14, .L{p}iterator_for_of_next_c
    ldrb w5, [x20, #1]
    mov w1, #-3
    sub w1, w1, w5
    sbfiz x1, x1, #4, #32
    add x1, x21, x1
    ldp x2, x3, [x1]
    cmn x3, #1
    b.ne .L{p}iterator_for_of_next_c
    ldp x4, x5, [x1, #16]
    cmn x5, #1
    b.ne .L{p}iterator_for_of_next_c
    ldrh w6, [x2, #ARM_OFF_JSObject_class_id]
    cmp w6, #{arr_iter_id}
    b.ne .L{p}iterator_for_of_next_c
    ldrh w6, [x4, #ARM_OFF_JSObject_class_id]
    cmp w6, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .L{p}iterator_for_of_next_c
    ldrb w6, [x4, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w6, #{cfunc_iter_next}
    b.ne .L{p}iterator_for_of_next_c
    ldr x6, [x4, #ARM_OFF_JSObject_u_cfunc_c_function]
    cmp x6, x14
    b.ne .L{p}iterator_for_of_next_c"""
        else:
            fast_head = f"""#if ARM_HAS_ITERATORS
#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_for_of_next:
    ldrb w2, [x22, #ARM_FRAME_FLAGS_OFFSET]
    tbnz w2, #1, .L{p}iterator_for_of_next_c
    ldrb w5, [x20, #1]
    mov w1, #-3
    sub w1, w1, w5
    sbfiz x1, x1, #4, #32
    add x1, x21, x1
    ldp x2, x3, [x1]
    cmn x3, #1
    b.ne .L{p}iterator_for_of_next_c
    ldp x4, x5, [x1, #16]
    cmn x5, #1
    b.ne .L{p}iterator_for_of_next_c
    ldrh w6, [x4, #ARM_OFF_JSObject_class_id]
    cmp w6, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .L{p}iterator_for_of_next_c
    ldrb w6, [x4, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w6, #{cfunc_iter_next}
    b.ne .L{p}iterator_for_of_next_c
    ldrh w6, [x2, #ARM_OFF_JSObject_class_id]
    cmp w6, #{arr_iter_id}
    b.ne .Lfast_cfunc_for_of_next
    ldrb w1, [x26, #116]
    tbz w1, #2, .L{p}iterator_for_of_next_c
    adrp x14, .Lfast_array_iter_fn
    ldr x14, [x14, :lo12:.Lfast_array_iter_fn]
    cbz x14, .L{p}iterator_for_of_next_c
    ldr x6, [x4, #ARM_OFF_JSObject_u_cfunc_c_function]
    cmp x6, x14
    b.ne .Lfast_cfunc_for_of_next"""
        islands.append(
            fast_head
            + f"""
    ldr x3, [x2, #48]
    cbz x3, .L{p}iterator_for_of_next_c
    ldr w6, [x3, #16]
    cmp w6, #1
    b.ne .L{p}iterator_for_of_next_c
    ldp x7, x8, [x3]
    cmn x8, #1
    b.ne .L{p}iterator_for_of_next_c
    ldrh w6, [x7, #ARM_OFF_JSObject_class_id]
    cmp w6, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .L{p}iterator_for_of_next_c
    ldrb w6, [x7, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w6, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .L{p}iterator_for_of_next_c
    ldr x5, [x7, #ARM_OFF_JSObject_shape]
    ldr w6, [x5, #ARM_OFF_JSShape_prop_count]
    cmp w6, #0
    b.le .L{p}iterator_for_of_next_c
    ldr w6, [x5, #(ARM_OFF_JSShape_prop + ARM_OFF_JSShapeProperty_atom)]
    cmp w6, #ARM_CONST_JS_ATOM_length
    b.ne .L{p}iterator_for_of_next_c
    ldr w6, [x5, #ARM_OFF_JSShape_prop]
    lsr w6, w6, #26
    and w6, w6, #0x38
    cmp w6, #8
    b.ne .L{p}iterator_for_of_next_c
    ldr x5, [x7, #ARM_OFF_JSObject_prop]
    ldp x8, x9, [x5]
    cbnz x9, .L{p}iterator_for_of_next_c
    tbnz w8, #31, .L{p}iterator_for_of_next_c
    ldr w6, [x3, #20]
    cmp w6, w8
    b.hs .L{p}iterator_for_of_next_c
    ldr w8, [x7, #ARM_OFF_JSObject_u_array_count]
    cmp w6, w8
    b.hs .L{p}iterator_for_of_next_c
    add w9, w6, #1
    str w9, [x3, #20]
    ldr x8, [x7, #ARM_OFF_JSObject_u_array_u_values]
    add x8, x8, w6, uxtw #4
    ldp x10, x11, [x8]
    tbz x11, #63, .L{p}fast_for_of_val_ok
    ldr w12, [x10, #ARM_REF_COUNT_OFFSET]
    add w12, w12, #1
    str w12, [x10, #ARM_REF_COUNT_OFFSET]
.L{p}fast_for_of_val_ok:
    ldrb w12, [x20, #2]
    cmp w12, #ARM_OP_if_false8
    b.ne .L{p}fast_for_of_push2
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #1, .L{p}fast_for_of_push2
    ldr x13, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w14, [x13, #ARM_OFF_JSContext_interrupt_counter]
    subs w14, w14, #1
    b.le .L{p}fast_for_of_push2
    str w14, [x13, #ARM_OFF_JSContext_interrupt_counter]
    stp x10, x11, [x21], #16
    ldrsb x15, [x20, #3]
    add x20, x20, #3
    add x20, x20, x15
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ARM_DISPATCH_NEXT 2
.L{p}fast_for_of_push2:
    stp x10, x11, [x21]
    mov x12, #ARM_CONST_JS_TAG_BOOL
    stp xzr, x12, [x21, #16]
    add x21, x21, #32
    add x20, x20, #2
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ARM_DISPATCH_NEXT 1

.L{p}iterator_for_of_next_c:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    bl {helper}
    cbnz w0, .Ldone
    adrp x14, .Lfast_array_iter_fn
    ldr x15, [x14, :lo12:.Lfast_array_iter_fn]
    cbnz x15, .L{p}fast_for_of_reload
    ldr x1, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    cmp x1, x22
    b.ne .L{p}fast_for_of_reload
    ldr x2, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    sub x3, x2, x21
    cmp x3, #32
    b.ne .L{p}fast_for_of_reload
    ldrb w3, [x26, #116]
    tbz w3, #2, .L{p}fast_for_of_reload
    ldrb w5, [x20, #1]
    mov w1, #-3
    sub w1, w1, w5
    sbfiz x1, x1, #4, #32
    add x1, x21, x1
    ldp x2, x3, [x1]
    cmn x3, #1
    b.ne .L{p}fast_for_of_reload
    ldrh w6, [x2, #ARM_OFF_JSObject_class_id]
    cmp w6, #{arr_iter_id}
    b.ne .L{p}fast_for_of_reload
    ldp x4, x5, [x1, #16]
    cmn x5, #1
    b.ne .L{p}fast_for_of_reload
    ldrh w6, [x4, #ARM_OFF_JSObject_class_id]
    cmp w6, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .L{p}fast_for_of_reload
    ldrb w6, [x4, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w6, #{cfunc_iter_next}
    b.ne .L{p}fast_for_of_reload
    ldrh w6, [x4, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w6, .L{p}fast_for_of_reload
    ldr x6, [x4, #ARM_OFF_JSObject_u_cfunc_c_function]
    str x6, [x14, :lo12:.Lfast_array_iter_fn]
.L{p}fast_for_of_reload:
    b .L{p}reload{cfunc_island}
#endif
#endif
"""
        )
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"

    return text, "\n".join(islands)
