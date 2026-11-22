"""Property IC and array/typed-array specialization helpers for ARM64 Fast VM."""

from arm64.vm.specialize import _replace_exact


def _specialize_property_ic(text):
    islands = []
    for p in ("", "pub_"):
        free_target = (
            "JS_FrameInterpFree" if not p else "qjs_aarch64_publish_before_FrameInterpFree"
        )
        if not p:
            old_put = """.Lproperty_put:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_REPLACE
    b.eq .Lproperty_replace
    cmp w10, #ARM_CONST_JS_IC_TRANSITION
    b.ne .Lproperty_pic_slow
    ldrb w10, [x0, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lproperty_pic_slow
    ldrb w10, [x0, #ARM_BIT_JSObject_is_prototype_BYTE]
    tst w10, #ARM_BIT_JSObject_is_prototype_MASK
    b.ne .Lproperty_pic_slow
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x9, #ARM_OFF_JSRuntime_property_ic_epoch]
    cbz x11, .Lproperty_pic_slow
    ldr x12, [x5, #ARM_OFF_JSPropertyICWay_epoch]
    cmp x11, x12
    b.ne .Lproperty_pic_slow
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_transition]"""
            new_put = """.Lproperty_put:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_REPLACE
    b.eq .Lproperty_replace
    cmp w10, #ARM_CONST_JS_IC_TRANSITION
#ifndef QJS_AARCH64_VM_INSTRUMENT
    b.eq .Lproperty_transition_chk
    cmp w10, #6
#endif
    b.ne .Lproperty_pic_slow
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lproperty_transition_chk:
#endif
    ldrb w13, [x0, #ARM_BIT_JSObject_extensible_BYTE]
    tst w13, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lproperty_pic_slow
    ldrb w13, [x0, #ARM_BIT_JSObject_is_prototype_BYTE]
    tst w13, #ARM_BIT_JSObject_is_prototype_MASK
    b.ne .Lproperty_pic_slow
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x9, #ARM_OFF_JSRuntime_property_ic_epoch]
    cbz x11, .Lproperty_pic_slow
    ldr x12, [x5, #ARM_OFF_JSPropertyICWay_epoch]
    cmp x11, x12
    b.ne .Lproperty_pic_slow
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w10, #6
    b.eq .Lfast_prop_transition_resize
.Lproperty_transition_apply:
#endif
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_transition]"""
            text = _replace_exact(text, old_put, new_put, 1, "property_put transition_resize")

            old_mc = """.Lproperty_method_commit:
    stp x8, x16, [x21], #16
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #8]
    add x15, x15, #1
    str x15, [x14, #8]
#endif
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1"""
            new_mc = """.Lproperty_method_commit:
    stp x8, x16, [x21], #16
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #8]
    add x15, x15, #1
    str x15, [x14, #8]
#else
    cmn x16, #1
    b.eq .Lfast_method_call_fuse
.Lfast_method_commit_next:
#endif
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1"""
            text = _replace_exact(text, old_mc, new_mc, 1, "property_method_commit call fuse")

            old_pt = """.Lpush_this:
    add x12, x22, #ARM_OFF_JSFrame_this_value
    ldp x10, x11, [x12]"""
            new_pt = """.Lpush_this:
    add x12, x22, #ARM_OFF_JSFrame_this_value
    ldp x10, x11, [x12]
#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmn x11, #1
    b.eq .Lfast_push_this_gf_chk
.Lfast_push_this_orig:
#endif"""
            text = _replace_exact(text, old_pt, new_pt, 1, "push_this prologue gf fuse")
        old_ready_folded = f""".L{p}property_receiver_ready:
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}property_method_legacy
    mov x2, x26
    ldr x3, [x2, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x3, #4095
    b.ls .L{p}property_ic_cold
    ldr x4, [x2, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    sub x4, x20, x4
    lsr x4, x4, #2
    add x3, x3, #ARM_OFF_JSPropertyIC_map
    ldr x5, [x3, x4, lsl #3]
    cbz x5, .L{p}property_method_legacy
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    mov w2, #0
    cmp x7, x6
    b.eq .L{p}property_matched"""
        exotic_branch = (
            "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
            "    b.ne .Lfast_exotic_prop_chk\n"
            "#else\n"
            "    b.ne .Lproperty_method_legacy\n"
            "#endif"
            if not p
            else "    b.ne .Lpub_property_method_legacy"
        )
        new_ready = f""".L{p}property_receiver_ready:
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
{exotic_branch}
    cmp x27, #1
    b.ls .L{p}property_ic_unready
.L{p}property_ic_map_ready:
    lsr x4, x20, #2
    ldr x5, [x27, x4, lsl #3]
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
.L{p}property_ic_site_loaded:
    cbz x5, .L{p}property_method_legacy
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    mov w2, #0
    cmp x7, x6
    b.eq .L{p}property_matched"""
        text = _replace_exact(text, old_ready_folded, new_ready, 1, f"{p}property_receiver_ready")

        if not p:
            old_get_commit = """.Lproperty_get_commit:
    cbz w2, .Lproperty_get_primary"""
            new_get_commit = """.Lproperty_get_commit:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    cbz w2, .Lproperty_get_primary
#endif"""
            text = _replace_exact(
                text, old_get_commit, new_get_commit, 1, "property_get_commit dead cbz w2"
            )

        # Last-ref property_replace via JS_FrameInterpFree (eliminates 50k slow put_field in Splay)
        old_rep = f"""    ldr w12, [x8, #ARM_REF_COUNT_OFFSET]
    cmp w12, #1
    b.le .L{p}property_pic_slow"""
        new_rep = f"""    ldr w12, [x8, #ARM_REF_COUNT_OFFSET]
    cmp w12, #1
    b.le .L{p}fast_prop_replace_last"""
        text = _replace_exact(text, old_rep, new_rep, 1, f"{p}property_replace last")

        # Direct per-opcode C property step in Release (eliminates 6 noipa wrapper calls on JS_IC_TRANSITION_RESIZE)
        old_pic_slow = f""".L{p}property_pic_slow:
    cmp w17, #4
    b.ne .L{p}slow"""
        new_pic_slow = f""".L{p}property_pic_slow:
    cmp w17, #4
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b.ne .L{p}slow
#else
    b.ne .L{p}fast_c_prop_step
#endif"""
        text = _replace_exact(text, old_pic_slow, new_pic_slow, 1, f"{p}property_pic_slow")

        # Fast Array.length = int32 update/truncation + Release put_field C fallback in property_own_put
        old_own_put = f""".L{p}property_own_put:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #15, .L{p}slow
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .L{p}slow
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .L{p}slow
    ldur w8, [x20, #1]
    ldr x2, [x0, #ARM_OFF_JSObject_shape]"""
        new_own_put = f""".L{p}property_own_put:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #15, .L{p}slow
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .L{p}slow
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .L{p}slow
    ldur w8, [x20, #1]
    cmp w8, #ARM_CONST_JS_ATOM_length
    b.eq .L{p}fast_set_array_len
.L{p}property_own_put_shape:
    ldr x2, [x0, #ARM_OFF_JSObject_shape]"""
        text = _replace_exact(text, old_own_put, new_own_put, 1, f"{p}property_own_put")

        # get_loc0_loc1 + put_field fusion ONLY when loc0 is a heap reference (zero overhead on scalar loc0/loc1!)
        old_pair = f""".L{p}scalar_get_loc0_loc1:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x23]
    tbz x1, #63, .L{p}scalar_pair_first_ready"""
        new_pair = f""".L{p}scalar_get_loc0_loc1:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .L{p}slow
    ldp x0, x1, [x23]
    tbz x1, #63, .L{p}scalar_pair_first_ready
    ldrb w14, [x20, #1]
    cmp w14, #ARM_OP_put_field
    b.eq .L{p}fast_pair_put_field
.L{p}scalar_get_loc0_loc1_orig:"""
        text = _replace_exact(text, old_pair, new_pair, 1, f"{p}scalar_get_loc0_loc1")

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

        islands.append(f""".L{p}property_ic_unready:
    b.eq .L{p}property_method_legacy
    ldr x3, [x26, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x3, #4095
    b.hi .L{p}property_ic_set_bias
    cmp x3, #1
    b.ne .L{p}property_no_cache
    mov x27, #1
    b .L{p}property_method_legacy
.L{p}property_ic_set_bias:
    ldr x4, [x26, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    add x3, x3, #ARM_OFF_JSPropertyIC_map
    lsr x9, x4, #2
    sub x27, x3, x9, lsl #3
    cbnz x27, .L{p}property_ic_map_ready
    sub x4, x20, x4
    lsr x4, x4, #2
    ldr x5, [x3, x4, lsl #3]
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    b .L{p}property_ic_site_loaded

.L{p}fast_prop_replace_last:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tst w14, #1
    b.eq .L{p}property_pic_slow
    ldp x10, x11, [x21, #-16]
    stp x10, x11, [x7, #ARM_OFF_JSProperty_u_value]
    ldr w12, [x0, #ARM_REF_COUNT_OFFSET]
    sub w12, w12, #1
    str w12, [x0, #ARM_REF_COUNT_OFFSET]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #16]
    add x15, x15, #1
    str x15, [x14, #16]
    cbz w2, .L{p}fast_prop_rep_prim
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
.L{p}fast_prop_rep_prim:
    ldr x14, [sp, #136]
    add x14, x14, #1
    str x14, [sp, #136]
#endif
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x14, [x21, #-32]
    stp xzr, x14, [x21, #-16]
    sub x21, x21, #32
    add x20, x20, #5
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    mov x2, x8
    mov x3, x16
    ldr x1, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    bl {free_target}
    ARM_DISPATCH_NEXT 1

#ifndef QJS_AARCH64_VM_INSTRUMENT
.L{p}fast_c_prop_step:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
{pub_sync}    mov x0, x19
    cmp w17, #3
    b.eq .L{p}fast_c_prop_put
    cmp w17, #2
    b.eq .L{p}fast_c_prop_get2
    b .Lfast_c_get_field_sync
.L{p}fast_c_prop_get2:
    bl JS_FrameInterpProperty_get_field2
    cbz w0, .Lreload
    b .Ldone
.L{p}fast_c_prop_put:
    bl JS_FrameInterpProperty_put_field
    cbz w0, .Lreload
    b .Ldone
#endif

.L{p}fast_set_array_len:
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .L{p}property_own_put_shape
    ldrb w4, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w4, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .L{p}fast_set_array_len_slow
    ldp x10, x11, [x21, #-16]
    cbnz x11, .L{p}fast_set_array_len_slow
    tbnz w10, #31, .L{p}fast_set_array_len_slow
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr w4, [x2, #(ARM_OFF_JSShape_prop + ARM_OFF_JSShapeProperty_atom)]
    cmp w4, #ARM_CONST_JS_ATOM_length
    b.ne .L{p}fast_set_array_len_slow
    ldr w4, [x2, #ARM_OFF_JSShape_prop]
    tst w4, #ARM_PROPERTY_DESC_WRITABLE
    b.eq .L{p}fast_set_array_len_slow
    tst w4, #ARM_PROPERTY_DESC_TMASK
    b.ne .L{p}fast_set_array_len_slow
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w10, w5
    b.hs .L{p}fast_set_array_len_store
    sub w6, w5, w10
    cmp w6, #16
    b.hi .L{p}fast_set_array_len_slow
    ldr x7, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x12, x7, w10, uxtw #4
    add x13, x7, w5, uxtw #4
    mov x14, x12
.L{p}fast_set_array_len_chk:
    ldr x15, [x14, #8]
    tbnz x15, #63, .L{p}fast_set_array_len_slow
    add x14, x14, #16
    cmp x14, x13
    b.lo .L{p}fast_set_array_len_chk
    mov x15, #ARM_CONST_JS_TAG_UNDEFINED
.L{p}fast_set_array_len_clr:
    stp xzr, x15, [x12], #16
    cmp x12, x13
    b.lo .L{p}fast_set_array_len_clr
    str w10, [x0, #ARM_OFF_JSObject_u_array_count]
.L{p}fast_set_array_len_store:
    ldr x7, [x0, #ARM_OFF_JSObject_prop]
    mov w10, w10
    stp x10, xzr, [x7]
    sub w9, w9, #1
    str w9, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #32
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.L{p}fast_set_array_len_slow:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    b .L{p}slow
#else
    mov w17, #3
    b .L{p}fast_c_prop_step
#endif

.L{p}fast_pair_put_field:
    tst w12, #2048
    b.eq .L{p}scalar_get_loc0_loc1_orig
    cmp x27, #1
    b.ls .L{p}scalar_get_loc0_loc1_orig
    cmn x1, #1
    b.ne .L{p}scalar_get_loc0_loc1_orig
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .L{p}scalar_get_loc0_loc1_orig
    add x4, x20, #1
    lsr x4, x4, #2
    ldr x5, [x27, x4, lsl #3]
    cbz x5, .L{p}scalar_get_loc0_loc1_orig
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    cmp x7, x6
    b.ne .L{p}scalar_get_loc0_loc1_orig
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_REPLACE
    b.ne .L{p}scalar_get_loc0_loc1_orig
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x0, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldr x16, [x7, #(ARM_OFF_JSProperty_u_value + 8)]
    cmp x16, #0
    b.lt .L{p}scalar_get_loc0_loc1_orig
    ldp x8, x9, [x23, #16]
    tbz x9, #63, .L{p}fast_pair_put_store
    ldr w10, [x8, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x8, #ARM_REF_COUNT_OFFSET]
.L{p}fast_pair_put_store:
    stp x8, x9, [x7, #ARM_OFF_JSProperty_u_value]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_scalar_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_scalar_counters
    ldr x13, [x12, #(8*13)]
    add x13, x13, #1
    str x13, [x12, #(8*13)]
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #16]
    add x15, x15, #1
    str x15, [x14, #16]
#endif
    add x20, x20, #6
    ARM_DISPATCH_NEXT 2
""")
        if p:
            islands[-1] = f"#ifdef QJS_AARCH64_VM_INSTRUMENT\n{islands[-1]}\n#endif"

        old_borrow = f""".L{p}property_borrow_entry:
#if ARM_HAS_PROPERTY_IC
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w9, #1
    b.ne .L{p}property_borrow_fallback
    mov w17, #4
    b .L{p}property_probe"""
        if not p:
            new_borrow = """.Lproperty_borrow_entry:
#if ARM_HAS_PROPERTY_IC
#ifndef QJS_AARCH64_VM_INSTRUMENT
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #0x08000000
    b.eq .Lfast_borrow_gf_chk_lf
    tst w12, #0x800
    b.eq .Lproperty_borrow_fallback
    b .Lfast_borrow_gf_enter
#else
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w9, #1
    b.ne .Lproperty_borrow_fallback
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    mov w17, #4
    tbz w9, #11, .Lproperty_borrow_fallback
    b .Lproperty_receiver_ready
#endif"""
        else:
            new_borrow = f""".L{p}property_borrow_entry:
#if ARM_HAS_PROPERTY_IC
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w9, #1
    b.ne .L{p}property_borrow_fallback
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    mov w17, #4
    tbz w9, #11, .L{p}property_borrow_fallback
    b .L{p}property_receiver_ready"""
        text = _replace_exact(text, old_borrow, new_borrow, 1, f"{p}property_borrow_entry")

        old_load = f""".L{p}property_load:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x7, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x16, #63, .L{p}property_get_commit
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]"""
        new_load = (
            f""".L{p}property_load:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x7, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x16, #63, .L{p}property_get_commit
    cmp w17, #4
    b.ne .L{p}property_load_dup
    cmn x16, #1
    b.ne .L{p}property_load_dup
    ldrb w9, [x20, #5]
    cmp w9, #ARM_OP_get_field
    b.eq .L{p}property_load_chain_gf
"""
            + (
                """#ifndef QJS_AARCH64_VM_INSTRUMENT
    cmp w9, #ARM_OP_get_field2
    b.ne .Lproperty_load_dup
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
    stp x8, x16, [x21], #16
    add x20, x20, #5
    mov x0, x8
    mov x1, x16
    mov w17, #2
    b .Lproperty_receiver_ready
#else
    b .Lproperty_load_dup
#endif
"""
                if not p
                else f"    b .L{p}property_load_dup\n"
            )
            + f""".L{p}property_load_chain_gf:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    cbz w2, .L{p}property_chain_prim
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
.L{p}property_chain_prim:
    ldr x15, [x14]
    add x15, x15, #1
    str x15, [x14]
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_hint_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_hint_counters
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
    ldr x14, [sp, #128]
    add x14, x14, #1
    str x14, [sp, #128]
#endif
    add x20, x20, #5
    mov x0, x8
    mov x1, x16
    b .L{p}property_receiver_ready
.L{p}property_load_dup:
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]"""
        )
        text = _replace_exact(text, old_load, new_load, 1, f"{p}property_load")

    islands.append("""#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_prop_transition_resize:
    mov x2, x5
    mov x1, x0
    mov x0, x9
    bl JS_FastTransitionResize
    cbz x0, .Lproperty_pic_slow
    mov x5, x0
    ldr x0, [x21, #-32]
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    mov w2, #0
    b .Lproperty_transition_apply

.Lfast_borrow_gf_chk_lf:
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w9, #1
    b.ne .Lproperty_borrow_fallback
    tst w12, #0x800
    b.eq .Lproperty_borrow_fallback
.Lfast_borrow_gf_enter:
    mov w17, #4
.Lfast_borrow_gf_loop:
    cmp x27, #1
    b.ls .Lproperty_receiver_ready
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lproperty_method_legacy
    lsr x4, x20, #2
    ldr x5, [x27, x4, lsl #3]
    cbz x5, .Lproperty_method_legacy
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    mov w2, #0
    cmp x7, x6
    b.ne .Lproperty_ic_site_loaded
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_OWN
    b.ne .Lproperty_matched
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x0, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    ldrb w13, [x20, #5]
    cmn x16, #1
    b.ne .Lfast_borrow_gf_chk_null
    cmp w13, #ARM_OP_get_field
    b.eq .Lfast_borrow_gf_chain
    cmp w13, #ARM_OP_get_field2
    b.ne .Lfast_borrow_gf_chk_br
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
    stp x8, x16, [x21], #16
    mov x0, x8
    mov x1, x16
    mov w17, #2
    add x20, x20, #5
    b .Lproperty_receiver_ready
.Lfast_borrow_gf_chain:
    mov x0, x8
    add x20, x20, #5
    b .Lfast_borrow_gf_loop
.Lfast_borrow_gf_chk_null:
    cmp w13, #ARM_OP_null
    b.ne .Lfast_borrow_gf_chk_br
    tst w12, #2
    b.eq .Lfast_borrow_gf_commit
    ldrb w14, [x20, #6]
    sub w14, w14, #ARM_OP_eq
    cmp w14, #3
    b.hi .Lfast_borrow_gf_commit
    ldrb w15, [x20, #7]
    sub w11, w15, #ARM_OP_if_false8
    cmp w11, #1
    b.hi .Lfast_borrow_gf_commit
    cmp x16, #ARM_CONST_JS_TAG_NULL
    b.eq .Lfast_borrow_gf_null_true
    cmp x16, #ARM_CONST_JS_TAG_UNDEFINED
    b.eq .Lfast_borrow_gf_null_undef
    cbz x16, .Lfast_borrow_gf_null_false
    cmp x16, #1
    b.eq .Lfast_borrow_gf_null_false
    cmp x16, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lfast_borrow_gf_null_false
    tbnz x16, #63, .Lfast_borrow_gf_null_false
    b .Lfast_borrow_gf_commit
.Lfast_borrow_gf_null_undef:
    tst w14, #2
    cset w9, eq
    b .Lfast_borrow_gf_null_apply
.Lfast_borrow_gf_null_true:
    mov w9, #1
    b .Lfast_borrow_gf_null_apply
.Lfast_borrow_gf_null_false:
    mov w9, #0
.Lfast_borrow_gf_null_apply:
    and w13, w14, #1
    eor w9, w9, w13
    cmp w9, w11
    b.eq .Lfast_borrow_gf_null_taken
    add x20, x20, #9
    ARM_DISPATCH_NEXT 4
.Lfast_borrow_gf_null_taken:
    ldrsb x15, [x20, #8]
    tbnz x15, #63, .Lfast_borrow_gf_null_bwd
.Lfast_borrow_gf_null_jump:
    add x20, x20, #8
    add x20, x20, x15
    ARM_DISPATCH_NEXT 4
.Lfast_borrow_gf_null_bwd:
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w9, w9, #1
    b.le .Lfast_borrow_gf_commit
    str w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    b .Lfast_borrow_gf_null_jump
.Lfast_borrow_gf_chk_br:
    sub w14, w13, #ARM_OP_if_false8
    cmp w14, #1
    b.hi .Lfast_borrow_gf_chk_null_obj
    tst w12, #2
    b.eq .Lfast_borrow_gf_commit
    cmn x16, #1
    b.eq .Lfast_borrow_gf_br_obj
    cmp x16, #1
    b.ls .Lfast_borrow_gf_br_ib
    cmp x16, #ARM_CONST_JS_TAG_UNDEFINED
    b.hi .Lfast_borrow_gf_commit
    mov w15, #0
    b .Lfast_borrow_gf_br_eval
.Lfast_borrow_gf_br_obj:
    ldrb w9, [x8, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tbnz w9, #7, .Lfast_borrow_gf_commit
    mov w15, #1
    b .Lfast_borrow_gf_br_eval
.Lfast_borrow_gf_br_ib:
    cmp w8, #0
    cset w15, ne
.Lfast_borrow_gf_br_eval:
    cmp w15, w14
    b.eq .Lfast_borrow_gf_br_taken
    add x20, x20, #7
    ARM_DISPATCH_NEXT 2
.Lfast_borrow_gf_br_taken:
    ldrsb x15, [x20, #6]
    tbnz x15, #63, .Lfast_borrow_gf_br_bwd
.Lfast_borrow_gf_br_jump:
    add x20, x20, #6
    add x20, x20, x15
    ARM_DISPATCH_NEXT 2
.Lfast_borrow_gf_br_bwd:
    ldr x11, [x26, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w9, w9, #1
    b.le .Lfast_borrow_gf_commit
    str w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    b .Lfast_borrow_gf_br_jump
.Lfast_borrow_gf_chk_null_obj:
    cmp w13, #ARM_OP_null
    b.ne .Lfast_borrow_gf_chk_pf
    tst w12, #2
    b.eq .Lfast_borrow_gf_commit
    ldrb w14, [x20, #6]
    sub w14, w14, #ARM_OP_eq
    cmp w14, #3
    b.hi .Lfast_borrow_gf_commit
    ldrb w15, [x20, #7]
    sub w11, w15, #ARM_OP_if_false8
    cmp w11, #1
    b.hi .Lfast_borrow_gf_commit
    ldrb w9, [x8, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tbnz w9, #7, .Lfast_borrow_gf_commit
    b .Lfast_borrow_gf_null_false
.Lfast_borrow_gf_chk_pf:
    cmp w13, #ARM_OP_put_field
    b.eq .Lfast_borrow_gf_put_field
.Lfast_borrow_gf_commit:
    tbz x16, #63, .Lfast_borrow_gf_push
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
.Lfast_borrow_gf_push:
    stp x8, x16, [x21], #16
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1

.Lfast_borrow_gf_put_field:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #0x800
    b.eq .Lfast_borrow_gf_commit
    cmp x27, #1
    b.ls .Lfast_borrow_gf_commit
    cmp x16, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_borrow_gf_commit
    cmp x16, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lfast_borrow_gf_commit
    ldp x2, x3, [x21, #-16]
    cmn x3, #1
    b.ne .Lfast_borrow_gf_commit
    ldr w9, [x2, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lfast_borrow_gf_commit
    ldrb w9, [x2, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lfast_borrow_gf_commit
    add x4, x20, #5
    lsr x4, x4, #2
    ldr x5, [x27, x4, lsl #3]
    cbz x5, .Lfast_borrow_gf_commit
    ldr x6, [x2, #ARM_OFF_JSObject_shape]
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    cmp x7, x6
    b.ne .Lfast_borrow_gf_commit
    ldr w12, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w12, #ARM_CONST_JS_IC_REPLACE
    b.ne .Lfast_borrow_gf_commit
    ldr w12, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x2, #ARM_OFF_JSObject_prop]
    add x7, x7, x12, lsl #4
    ldp x14, x15, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x15, #63, .Lfast_bgfpf_old_ok
    ldr w11, [x14, #ARM_REF_COUNT_OFFSET]
    cmp w11, #1
    b.le .Lfast_borrow_gf_commit
    cmp x14, x2
    b.ne .Lfast_bgfpf_old_ok
    cmp w11, #2
    b.le .Lfast_borrow_gf_commit
.Lfast_bgfpf_old_ok:
    tbz x16, #63, .Lfast_bgfpf_dec_old
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
.Lfast_bgfpf_dec_old:
    tbz x15, #63, .Lfast_bgfpf_dec_recv
    ldr w9, [x14, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    str w9, [x14, #ARM_REF_COUNT_OFFSET]
.Lfast_bgfpf_dec_recv:
    ldr w9, [x2, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    str w9, [x2, #ARM_REF_COUNT_OFFSET]
    stp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    sub x21, x21, #16
    add x20, x20, #10
    ARM_DISPATCH_NEXT 3

.Lfast_c_get_field:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
.Lfast_c_get_field_sync:
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    mov x0, x19
    bl JS_FastGetField
    cmp w0, #2
    b.ne .Lfast_c_gf_fallback_ret
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ARM_DISPATCH_NEXT 1
.Lfast_c_gf_fallback_ret:
    adrp x10, qjs_aarch64_publish_dirty
    add x10, x10, :lo12:qjs_aarch64_publish_dirty
    cmp x25, x10
    b.ne 1f
    adrp x25, qjs_aarch64_publish_clean
    add x25, x25, :lo12:qjs_aarch64_publish_clean
1:
    cbz w0, .Lreload
    b .Ldone

.Lfast_exotic_prop_chk:
    cmp w17, #2
    b.ne .Lproperty_method_legacy
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lproperty_method_legacy
    ldr x4, [x0, #ARM_OFF_JSObject_shape]
    ldr w9, [x4, #ARM_OFF_JSShape_prop_count]
    cmp w9, #1
    b.ne .Lproperty_method_legacy
    ldr w9, [x4, #(ARM_OFF_JSShape_prop + ARM_OFF_JSShapeProperty_atom)]
    cmp w9, #ARM_CONST_JS_ATOM_length
    b.ne .Lproperty_method_legacy
    ldur w8, [x20, #1]
    tbnz w8, #31, .Lproperty_method_legacy
    cmp w8, #ARM_CONST_JS_ATOM_length
    b.eq .Lproperty_method_legacy
    ldr x3, [x4, #ARM_OFF_JSShape_proto]
    cbz x3, .Lproperty_method_legacy
    ldrb w9, [x3, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lproperty_method_legacy
    ldr x4, [x3, #ARM_OFF_JSObject_shape]
    eor w10, w8, w8, lsr #2
    and w10, w10, #3
    mrs x11, tpidr_el0
    add x11, x11, :tprel_hi12:.Lfast_arr_proto_ic
    add x11, x11, :tprel_lo12_nc:.Lfast_arr_proto_ic
    add x11, x11, x10, lsl #4
    ldr x12, [x11]
    cmp x12, x4
    b.ne .Lfast_arr_proto_miss
    ldr w13, [x11, #8]
    cmp w13, w8
    b.ne .Lfast_arr_proto_miss
    ldr w10, [x11, #12]
    ldr w12, [x4, #ARM_OFF_JSShape_prop_count]
    cmp w10, w12
    b.hs .Lfast_arr_proto_miss
    add x13, x4, #ARM_OFF_JSShape_prop
    add x13, x13, x10, lsl #3
    ldr w14, [x13, #ARM_OFF_JSShapeProperty_atom]
    cmp w14, w8
    b.ne .Lfast_arr_proto_miss
    ldr w14, [x13]
    tst w14, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lfast_arr_proto_miss
    b .Lfast_arr_proto_load
.Lfast_arr_proto_miss:
    ldr w12, [x4, #ARM_OFF_JSShape_prop_hash_mask]
    and w12, w8, w12
    neg x12, x12
    add x12, x4, x12, lsl #2
    ldur w12, [x12, #-4]
    add x13, x4, #ARM_OFF_JSShape_prop
.Lfast_arr_proto_loop:
    cbz w12, .Lproperty_method_legacy
    sub w10, w12, #1
    add x14, x13, x10, lsl #3
    ldr w15, [x14, #ARM_OFF_JSShapeProperty_atom]
    cmp w15, w8
    b.eq .Lfast_arr_proto_found
    ldr w12, [x14]
    and w12, w12, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lfast_arr_proto_loop
.Lfast_arr_proto_found:
    ldr w15, [x14]
    tst w15, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_method_legacy
    str x4, [x11]
    str w8, [x11, #8]
    str w10, [x11, #12]
.Lfast_arr_proto_load:
    ldr x12, [x3, #ARM_OFF_JSObject_prop]
    add x12, x12, x10, lsl #4
    ldp x8, x16, [x12, #ARM_OFF_JSProperty_u_value]
    cmp x16, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lproperty_method_legacy
    cmp x16, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lproperty_method_legacy
    tbz x16, #63, .Lproperty_method_commit
    ldr w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x8, #ARM_REF_COUNT_OFFSET]
    b .Lproperty_method_commit

.Lfast_push_this_gf_chk:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #1
    b.eq .Lfast_push_this_orig
    ldrb w13, [x20, #1]
    sub w15, w13, #ARM_OP_put_loc0
    cmp w15, #3
    b.hi .Lfast_push_this_chk8
    add x16, x23, w15, uxtw #4
    ldr x14, [x16, #8]
    cmp x14, #3
    b.ls .Lfast_push_this_short_loc_ok
    cmp x14, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_push_this_orig
.Lfast_push_this_short_loc_ok:
    ldrb w14, [x20, #2]
    add w9, w15, #ARM_OP_get_loc0
    cmp w14, w9
    b.eq .Lfast_push_this_short_op
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x16]
    add x20, x20, #2
    ARM_DISPATCH_NEXT 2
.Lfast_push_this_short_op:
    ldrb w14, [x20, #3]
    add x13, x20, #3
    b .Lfast_push_this_dispatch
.Lfast_push_this_chk8:
    cmp w13, #ARM_OP_put_loc8
    b.ne .Lfast_push_this_orig
    ldrb w14, [x20, #2]
    add x16, x23, w14, uxtw #4
    ldr x15, [x16, #8]
    cmp x15, #3
    b.ls .Lfast_push_this_loc8_ok
    cmp x15, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lfast_push_this_orig
.Lfast_push_this_loc8_ok:
    ldrb w15, [x20, #3]
    cmp w15, #ARM_OP_get_loc8
    b.ne .Lfast_push_this_loc8_only
    ldrb w15, [x20, #4]
    cmp w14, w15
    b.ne .Lfast_push_this_loc8_only
    ldrb w14, [x20, #5]
    add x13, x20, #5
    b .Lfast_push_this_dispatch
.Lfast_push_this_loc8_only:
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x16]
    add x20, x20, #3
    ARM_DISPATCH_NEXT 2
.Lfast_push_this_dispatch:
    cmp w14, #ARM_OP_get_field
    b.eq .Lfast_push_this_gf1
    cmp w14, #ARM_OP_get_field2
    b.eq .Lfast_push_this_gf2
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #2
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x16]
    stp x10, x11, [x21], #16
    mov x20, x13
    ARM_DISPATCH_NEXT 3
.Lfast_push_this_gf2:
    tst w12, #0x800
    b.eq .Lfast_push_this_orig
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #2
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x16]
    stp x10, x11, [x21], #16
    mov x0, x10
    mov x1, x11
    mov w17, #2
    mov x20, x13
    b .Lproperty_receiver_ready
.Lfast_push_this_gf1:
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x16]
    mov x0, x10
    mov x1, x11
    mov x20, x13
    b .Lproperty_borrow_entry

.Lfast_method_call_fuse:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tst w12, #512
    b.eq .Lfast_method_commit_next
    ldrb w13, [x20, #5]
    cmp w13, #ARM_OP_call_method
    b.eq .Lfast_mcf_arg0_chk
    cmp w13, #ARM_OP_tail_call_method
    b.ne .Lfast_method_call_arg1
.Lfast_mcf_arg0_chk:
    ldurh w14, [x20, #6]
    cbnz w14, .Lfast_method_commit_next
    mov w0, #0
    add x20, x20, #5
    add x1, x20, #3
    mov x2, x21
    mov x3, x8
    mov x4, x16
    mov x28, #0
    cmp w13, #ARM_OP_call_method
    mov w17, #1
    mov w14, #3
    csel w17, w17, w14, eq
    b .Lpub_call_have_callee
.Lfast_method_call_arg1:
    mov w9, #1
    sub w14, w13, #ARM_OP_get_loc0
    cmp w14, #3
    b.ls .Lfast_mcf_chk_call1
    sub w14, w13, #ARM_OP_get_arg0
    cmp w14, #3
    b.ls .Lfast_mcf_chk_call1
    sub w14, w13, #ARM_OP_push_minus1
    cmp w14, #8
    b.ls .Lfast_mcf_chk_call1
    cmp w13, #ARM_OP_undefined
    b.eq .Lfast_mcf_chk_call1
    cmp w13, #ARM_OP_null
    b.eq .Lfast_mcf_chk_call1
    cmp w13, #ARM_OP_push_false
    b.eq .Lfast_mcf_chk_call1
    cmp w13, #ARM_OP_push_true
    b.eq .Lfast_mcf_chk_call1
    mov w9, #2
    cmp w13, #ARM_OP_get_loc8
    b.eq .Lfast_mcf_chk_call1
    cmp w13, #ARM_OP_push_i8
    b.ne .Lfast_method_commit_next
.Lfast_mcf_chk_call1:
    add x12, x20, #5
    add x12, x12, x9
    ldrb w14, [x12]
    cmp w14, #ARM_OP_call_method
    b.eq .Lfast_mcf_chk_argc1
    cmp w14, #ARM_OP_tail_call_method
    b.eq .Lfast_mcf_chk_argc1
    mov w11, #1
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.ls .Lfast_mcf_chk_call2
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.ls .Lfast_mcf_chk_call2
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #8
    b.ls .Lfast_mcf_chk_call2
    cmp w14, #ARM_OP_undefined
    b.eq .Lfast_mcf_chk_call2
    cmp w14, #ARM_OP_null
    b.eq .Lfast_mcf_chk_call2
    cmp w14, #ARM_OP_push_false
    b.eq .Lfast_mcf_chk_call2
    cmp w14, #ARM_OP_push_true
    b.eq .Lfast_mcf_chk_call2
    mov w11, #2
    cmp w14, #ARM_OP_get_loc8
    b.eq .Lfast_mcf_chk_call2
    cmp w14, #ARM_OP_push_i8
    b.ne .Lfast_method_commit_next
.Lfast_mcf_chk_call2:
    add x7, x12, x11
    ldrb w10, [x7]
    cmp w10, #ARM_OP_call_method
    b.eq .Lfast_mcf_chk_argc2
    cmp w10, #ARM_OP_tail_call_method
    b.ne .Lfast_method_commit_next
.Lfast_mcf_chk_argc2:
    ldurh w15, [x7, #1]
    cmp w15, #2
    b.ne .Lfast_method_commit_next
    // Decode arg0 from w13 at [x20, #6] into (x0, x1)
    sub w15, w13, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_mcf2_a0_not_loc0
    add x15, x23, w15, uxtw #4
    ldp x0, x1, [x15]
    cmp x1, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_not_loc0:
    sub w15, w13, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_mcf2_a0_not_arg0
    ldrh w9, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w15, w9
    b.hs .Lfast_method_commit_next
    add x15, x24, w15, uxtw #4
    ldp x0, x1, [x15]
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_not_arg0:
    sub w15, w13, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_mcf2_a0_not_pint
    sub w0, w13, #ARM_OP_push_0
    sxtw x0, w0
    mov x1, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_not_pint:
    cmp w13, #ARM_OP_get_loc8
    b.ne .Lfast_mcf2_a0_not_loc8
    ldrb w15, [x20, #6]
    add x15, x23, w15, uxtw #4
    ldp x0, x1, [x15]
    cmp x1, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_not_loc8:
    cmp w13, #ARM_OP_push_i8
    b.ne .Lfast_mcf2_a0_lit
    ldrsb w0, [x20, #6]
    sxtw x0, w0
    mov x1, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_lit:
    cmp w13, #ARM_OP_undefined
    b.ne .Lfast_mcf2_a0_not_undef
    mov x0, #0
    mov x1, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_not_undef:
    cmp w13, #ARM_OP_null
    b.ne .Lfast_mcf2_a0_bool
    mov x0, #0
    mov x1, #ARM_CONST_JS_TAG_NULL
    b .Lfast_mcf2_dec_a1
.Lfast_mcf2_a0_bool:
    cmp w13, #ARM_OP_push_true
    cset w0, eq
    mov x1, #ARM_CONST_JS_TAG_BOOL
.Lfast_mcf2_dec_a1:
    // Decode arg1 from w14 at [x12, #1] into (x4, x5)
    sub w15, w14, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_mcf2_a1_not_loc0
    add x15, x23, w15, uxtw #4
    ldp x4, x5, [x15]
    cmp x5, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_not_loc0:
    sub w15, w14, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_mcf2_a1_not_arg0
    ldrh w9, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w15, w9
    b.hs .Lfast_method_commit_next
    add x15, x24, w15, uxtw #4
    ldp x4, x5, [x15]
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_not_arg0:
    sub w15, w14, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_mcf2_a1_not_pint
    sub w4, w14, #ARM_OP_push_0
    sxtw x4, w4
    mov x5, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_not_pint:
    cmp w14, #ARM_OP_get_loc8
    b.ne .Lfast_mcf2_a1_not_loc8
    ldrb w15, [x12, #1]
    add x15, x23, w15, uxtw #4
    ldp x4, x5, [x15]
    cmp x5, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_not_loc8:
    cmp w14, #ARM_OP_push_i8
    b.ne .Lfast_mcf2_a1_lit
    ldrsb w4, [x12, #1]
    sxtw x4, w4
    mov x5, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_lit:
    cmp w14, #ARM_OP_undefined
    b.ne .Lfast_mcf2_a1_not_undef
    mov x4, #0
    mov x5, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_not_undef:
    cmp w14, #ARM_OP_null
    b.ne .Lfast_mcf2_a1_bool
    mov x4, #0
    mov x5, #ARM_CONST_JS_TAG_NULL
    b .Lfast_mcf2_commit
.Lfast_mcf2_a1_bool:
    cmp w14, #ARM_OP_push_true
    cset w4, eq
    mov x5, #ARM_CONST_JS_TAG_BOOL
.Lfast_mcf2_commit:
    tbz x1, #63, .Lfast_mcf2_inc1
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x0, #ARM_REF_COUNT_OFFSET]
.Lfast_mcf2_inc1:
    tbz x5, #63, .Lfast_mcf2_store
    ldr w9, [x4, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x4, #ARM_REF_COUNT_OFFSET]
.Lfast_mcf2_store:
    stp x0, x1, [x21]
    stp x4, x5, [x21, #16]
    add x21, x21, #32
    mov x20, x7
    add x1, x20, #3
    mov w0, #2
    sub x2, x21, #32
    mov x3, x8
    mov x4, x16
    mov x28, #0
    cmp w10, #ARM_OP_call_method
    mov w17, #1
    mov w15, #3
    csel w17, w17, w15, eq
    b .Lpub_call_have_callee
.Lfast_mcf_chk_argc1:
    ldurh w15, [x12, #1]
    cmp w15, #1
    b.ne .Lfast_method_commit_next
    b .Lfast_mcf_arg1_decode
.Lfast_mcf_arg1_decode:
    sub w15, w13, #ARM_OP_get_loc0
    cmp w15, #3
    b.hi .Lfast_mcf_arg1_not_loc0
    add x15, x23, w15, uxtw #4
    ldp x5, x6, [x15]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_not_loc0:
    sub w15, w13, #ARM_OP_get_arg0
    cmp w15, #3
    b.hi .Lfast_mcf_arg1_not_arg0
    ldrh w10, [x22, #ARM_OFF_JSStackFrame_arg_count]
    cmp w15, w10
    b.hs .Lfast_method_commit_next
    add x15, x24, w15, uxtw #4
    ldp x5, x6, [x15]
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_not_arg0:
    sub w15, w13, #ARM_OP_push_minus1
    cmp w15, #8
    b.hi .Lfast_mcf_arg1_not_pint
    sub w5, w13, #ARM_OP_push_0
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_not_pint:
    cmp w13, #ARM_OP_get_loc8
    b.ne .Lfast_mcf_arg1_not_loc8
    ldrb w15, [x20, #6]
    add x15, x23, w15, uxtw #4
    ldp x5, x6, [x15]
    cmp x6, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lfast_method_commit_next
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_not_loc8:
    cmp w13, #ARM_OP_push_i8
    b.ne .Lfast_mcf_arg1_lit
    ldrsb w5, [x20, #6]
    sxtw x5, w5
    mov x6, #ARM_CONST_JS_TAG_INT
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_lit:
    cmp w13, #ARM_OP_undefined
    b.ne .Lfast_mcf_arg1_not_undef
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_not_undef:
    cmp w13, #ARM_OP_null
    b.ne .Lfast_mcf_arg1_bool
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_NULL
    b .Lfast_mcf_arg1_push
.Lfast_mcf_arg1_bool:
    cmp w13, #ARM_OP_push_true
    cset w5, eq
    mov x6, #ARM_CONST_JS_TAG_BOOL
.Lfast_mcf_arg1_push:
    tbz x6, #63, .Lfast_mcf_arg1_store
    ldr w10, [x5, #ARM_REF_COUNT_OFFSET]
    add w10, w10, #1
    str w10, [x5, #ARM_REF_COUNT_OFFSET]
.Lfast_mcf_arg1_store:
    stp x5, x6, [x21], #16
    mov x20, x12
    add x1, x20, #3
    mov w0, #1
    sub x2, x21, #16
    mov x3, x8
    mov x4, x16
    mov x28, #0
    cmp w14, #ARM_OP_call_method
    mov w17, #1
    mov w15, #3
    csel w17, w17, w15, eq
    b .Lpub_call_have_callee
#endif
""")

    return text, "\n".join(islands)
