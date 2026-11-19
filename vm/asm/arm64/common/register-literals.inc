/* Source-owned literal/transition/scalar continuations; measured AAPCS64. MIT. */
#if ARM_HAS_LITERALS
.Lliteral_object:
.Lliteral_define_field:
    ldrb w4, [x19, #ARM_LITERAL_ACTIVE_OFFSET]
    cmp w4, #4
    b.eq .Lliteral_active
    ldrb w4, [x19, #ARM_LITERAL_LAZY_OFFSET]
    cmp w4, #1
    b.ne .Lslow
    ldr w4, [x19, #ARM_OFF_JSFrameRegisterState_iterator_checkpoint_depth]
    cbnz w4, .Lslow
    ldrb w4, [x20]
    cmp w4, #ARM_OP_define_field
    b.ne .Lliteral_cold
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    tbz w16, #10, .Lslow
    b .Lliteral_cold
.Lliteral_active:
    ldr w4, [x19, #ARM_OFF_JSFrameRegisterState_iterator_checkpoint_depth]
    cbnz w4, .Lslow
    ldrb w4, [x20]
    cmp w4, #ARM_OP_define_field
    b.ne .Lliteral_cold
    ldrb w4, [x19, #ARM_OFF_JSFrameRegisterState_exception_pending]
    cbnz w4, .Lliteral_cold
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    tbz w16, #0, .Lliteral_cold
    tst w16, #2
    b.ne .Lliteral_cold
    tbnz w16, #3, .Lliteral_cold
    tbnz w16, #7, .Lliteral_cold
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lliteral_cold
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lliteral_cold
    ldrb w4, [x0, #ARM_BIT_JSObject_is_prototype_BYTE]
    tst w4, #ARM_BIT_JSObject_is_prototype_MASK
    b.ne .Lliteral_cold
    ldrb w4, [x0, #ARM_BIT_JSObject_extensible_BYTE]
    tst w4, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lliteral_cold
    tst w4, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lliteral_cold
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldrb w4, [x2, #ARM_OFF_JSShape_is_hashed]
    cbz w4, .Lliteral_cold
    ldr w4, [x2, #ARM_OFF_JSShape_deleted_prop_count]
    cbnz w4, .Lliteral_cold
    ldr w4, [x2, #ARM_OFF_JSShape_prop_count]
    ldr w5, [x2, #ARM_OFF_JSShape_prop_size]
    cmp w4, w5
    b.hs .Lliteral_cold
    tbz w16, #11, .Lliteral_spare
    cmp w5, #ARM_CONST_JS_PROP_INITIAL_SIZE
    b.ne .Lliteral_cold
.Lliteral_spare:
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_cache_next]
    cbz x3, .Lliteral_cold
    eor x4, x20, x20, lsr #5
    eor x4, x4, x20, lsr #11
    and x4, x4, #63
    add x3, x3, #ARM_OFF_OrdScope_bucket
    ldr x3, [x3, x4, lsl #3]
    ldr x4, [x22, #ARM_OFF_JSFrame_bytecode]
.Lliteral_record:
    cbz x3, .Lliteral_cold
    ldr x5, [x3, #ARM_OFF_JSFrameLiteralSite_site]
    cmp x5, x20
    b.ne .Lliteral_next
    ldr x5, [x3, #ARM_OFF_JSFrameLiteralSite_bytecode]
    cmp x5, x4
    b.eq .Lliteral_found
.Lliteral_next:
    ldr x3, [x3, #ARM_OFF_OrdRecord_next]
    b .Lliteral_record
.Lliteral_found:
    ldr x5, [x3, #ARM_OFF_JSFrameLiteralSite_old_shape]
    cmp x5, x2
    b.ne .Lliteral_cold
    ldur w5, [x20, #1]
    ldr w6, [x3, #ARM_OFF_JSFrameLiteralSite_atom]
    cmp w5, w6
    b.ne .Lliteral_cold
    ldr x5, [x3, #ARM_OFF_JSFrameLiteralSite_new_shape]
    cbz x5, .Lliteral_cold
    ldrb w6, [x5, #ARM_OFF_JSShape_is_hashed]
    cbz w6, .Lliteral_cold
    ldr w6, [x2, #ARM_OFF_JSShape_prop_count]
    ldr w7, [x3, #ARM_OFF_JSFrameLiteralSite_slot]
    cmp w6, w7
    b.ne .Lliteral_cold
    add w7, w6, #1
    ldr w8, [x5, #ARM_OFF_JSShape_prop_count]
    cmp w7, w8
    b.ne .Lliteral_cold
    ldr w7, [x2, #ARM_OFF_JSShape_prop_size]
    ldr w8, [x5, #ARM_OFF_JSShape_prop_size]
    cmp w7, w8
    b.ne .Lliteral_cold
// Both shapes are pinned by the actual activation owner. Retain the
// successor before weakening the old shape;no observer follows commit.
    ldr w8, [x5, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    str w8, [x5, #ARM_REF_COUNT_OFFSET]
    str x5, [x0, #ARM_OFF_JSObject_shape]
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    add x5, x5, w6, uxtw #4
    ldp x10, x11, [x21, #-16]
    stp x10, x11, [x5]
    ldr w8, [x2, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    str w8, [x2, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #16
    mov x8, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x8, [x21]
    add x20, x20, #5
    tbz w16, #2, .Lliteral_transition_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #40
.Lliteral_transition_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_transition_count
.Lliteral_transition_counted:
    tbz w16, #2, .Lliteral_vm_hit_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #128
.Lliteral_vm_hit_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_vm_hit_count
.Lliteral_vm_hit_counted:
    ldr w7, [x2, #ARM_OFF_JSShape_prop_size]
    cmp w7, #ARM_CONST_JS_PROP_INITIAL_SIZE
    b.ls .Lliteral_transition_done
    tbz w16, #2, .Lliteral_spare_hit_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #184
.Lliteral_spare_hit_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_spare_hit_count
.Lliteral_spare_hit_counted:
.Lliteral_transition_done:
    ARM_DISPATCH_NEXT 1
.Lliteral_cold:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameOrdinaryLiteralStep
    cbz w0, .Lreload
    b .Ldone

.Lliteral_insert2:
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #12, .Lslow
    ldp x0, x1, [x21, #-16]
    ldp x2, x3, [x21, #-32]
    tbz x1, #63, .Lliteral_insert2_value
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    add w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_insert2_value:
    stp x0, x1, [x21]
    stp x2, x3, [x21, #-16]
    stp x0, x1, [x21, #-32]
    add x21, x21, #16
    add x20, x20, #1
    tbz w16, #2, .Lliteral_insert2_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #192
.Lliteral_insert2_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_insert2_count
.Lliteral_insert2_counted:
    ARM_DISPATCH_NEXT 1
.Lliteral_typeof:
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #13, .Lslow
    ldp x0, x1, [x21, #-16]
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.gt .Lliteral_typeof_immediate
    mov x4, #ARM_CONST_JS_TAG_BIG_INT
    cmp x1, x4
    b.lt .Lslow
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
    b .Lliteral_typeof_classified
.Lliteral_typeof_immediate:
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lliteral_typeof_classified
    cmp x1, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lliteral_typeof_classified
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
.Lliteral_typeof_classified:
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_typeof_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_typeof_string
    mov x4, #ARM_CONST_JS_TAG_BIG_INT
    cmp x1, x4
    b.eq .Lliteral_typeof_bigint
    mov x4, #ARM_CONST_JS_TAG_SYMBOL
    cmp x1, x4
    b.eq .Lliteral_typeof_symbol
    mov x4, #ARM_CONST_JS_TAG_INT
    cmp x1, x4
    b.eq .Lliteral_typeof_number
    mov x4, #ARM_CONST_JS_TAG_FLOAT64
    cmp x1, x4
    b.eq .Lliteral_typeof_number
    mov x4, #ARM_CONST_JS_TAG_BOOL
    cmp x1, x4
    b.eq .Lliteral_typeof_boolean
    mov x4, #ARM_CONST_JS_TAG_NULL
    cmp x1, x4
    b.eq .Lliteral_typeof_object
    mov x4, #ARM_CONST_JS_TAG_UNDEFINED
    cmp x1, x4
    b.eq .Lliteral_typeof_undefined
    mov x4, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    cmp x1, x4
    b.eq .Lliteral_typeof_bigint
    brk #0
.Lliteral_typeof_string:
    mov w5, #ARM_CONST_JS_ATOM_string
    b .Lliteral_typeof_result
.Lliteral_typeof_bigint:
    mov w5, #ARM_CONST_JS_ATOM_bigint
    b .Lliteral_typeof_result
.Lliteral_typeof_symbol:
    mov w5, #ARM_CONST_JS_ATOM_symbol
    b .Lliteral_typeof_result
.Lliteral_typeof_number:
    mov w5, #ARM_CONST_JS_ATOM_number
    b .Lliteral_typeof_result
.Lliteral_typeof_boolean:
    mov w5, #ARM_CONST_JS_ATOM_boolean
    b .Lliteral_typeof_result
.Lliteral_typeof_object:
    mov w5, #ARM_CONST_JS_ATOM_object
    b .Lliteral_typeof_result
.Lliteral_typeof_undefined:
    mov w5, #ARM_CONST_JS_ATOM_undefined
    b .Lliteral_typeof_result
.Lliteral_typeof_result:
    ldr x4, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x4, [x4, #ARM_OFF_JSRuntime_atom_array]
    ldr x0, [x4, w5, uxtw #3]
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    add w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
    mov x1, #ARM_CONST_JS_TAG_STRING
    stp x0, x1, [x21, #-16]
    add x20, x20, #1
    tbz w16, #2, .Lliteral_typeof_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #200
.Lliteral_typeof_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_typeof_count
.Lliteral_typeof_counted:
    ARM_DISPATCH_NEXT 1
.Lliteral_typeof_is_function:
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #13, .Lslow
    ldp x0, x1, [x21, #-16]
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.gt .Lliteral_typeof_is_function_immediate
    mov x4, #ARM_CONST_JS_TAG_BIG_INT
    cmp x1, x4
    b.lt .Lslow
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
    b .Lliteral_typeof_is_function_classified
.Lliteral_typeof_is_function_immediate:
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lliteral_typeof_is_function_classified
    cmp x1, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lliteral_typeof_is_function_classified
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
.Lliteral_typeof_is_function_classified:
    mov x0, #0
    mov x1, #ARM_CONST_JS_TAG_BOOL
    stp x0, x1, [x21, #-16]
    add x20, x20, #1
    tbz w16, #2, .Lliteral_typeof_is_function_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #208
.Lliteral_typeof_is_function_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_typeof_is_function_count
.Lliteral_typeof_is_function_counted:
    ARM_DISPATCH_NEXT 1
.Lliteral_typeof_is_undefined:
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #13, .Lslow
    ldp x0, x1, [x21, #-16]
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.gt .Lliteral_typeof_is_undefined_immediate
    mov x4, #ARM_CONST_JS_TAG_BIG_INT
    cmp x1, x4
    b.lt .Lslow
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
    b .Lliteral_typeof_is_undefined_classified
.Lliteral_typeof_is_undefined_immediate:
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lliteral_typeof_is_undefined_classified
    cmp x1, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lliteral_typeof_is_undefined_classified
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
.Lliteral_typeof_is_undefined_classified:
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    cset w0, eq
    mov x1, #ARM_CONST_JS_TAG_BOOL
    stp x0, x1, [x21, #-16]
    add x20, x20, #1
    tbz w16, #2, .Lliteral_typeof_is_undefined_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #216
.Lliteral_typeof_is_undefined_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_typeof_is_undefined_count
.Lliteral_typeof_is_undefined_counted:
    ARM_DISPATCH_NEXT 1
.Lliteral_lnot:
.Lliteral_truth_lnot:
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #1, .Lslow
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.hi .Lliteral_truth_lnot_extended
    cmp w0, #0
    cset w6, ne
    b .Lliteral_truth_lnot_primitive
.Lliteral_truth_lnot_extended:
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #15, .Lslow
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lliteral_truth_lnot_object
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_truth_lnot_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_truth_lnot_rope
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbnz w16, #16, .Lslow
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #2, .Lslow
    fmov d0, x0
    fcmp d0, #0.0
    cset w6, ne
    csel w6, wzr, w6, vs
    b .Lliteral_truth_lnot_commit
.Lliteral_truth_lnot_string:
    ldr w4, [x0, #ARM_BIT_JSString_len_BYTE]
    tst w4, #0x7fffffff
    cset w6, ne
    b .Lliteral_truth_lnot_release
.Lliteral_truth_lnot_rope:
    ldr w4, [x0, #ARM_OFF_JSStringRope_len]
    cmp w4, #0
    cset w6, ne
    b .Lliteral_truth_lnot_release
.Lliteral_truth_lnot_object:
    ldrb w4, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    cset w6, eq
.Lliteral_truth_lnot_release:
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_truth_lnot_commit:
    tbz w16, #2, .Lliteral_truth_lnot_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #232
.Lliteral_truth_lnot_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_truth_lnot_count
.Lliteral_truth_lnot_counted:
.Lliteral_truth_lnot_primitive:
    eor w6, w6, #1
    mov x7, #ARM_CONST_JS_TAG_BOOL
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lliteral_truth_if_true:
    ldp x0, x1, [x21, #-16]
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #15, .Lslow
    ldr x8, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x8, [x8, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    cmp w9, #1
    b.le .Lslow
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lliteral_truth_if_true_object
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_truth_if_true_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_truth_if_true_rope
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbnz w16, #16, .Lslow
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #2, .Lslow
    fmov d0, x0
    fcmp d0, #0.0
    cset w6, ne
    csel w6, wzr, w6, vs
    b .Lliteral_truth_if_true_commit
.Lliteral_truth_if_true_string:
    ldr w4, [x0, #ARM_BIT_JSString_len_BYTE]
    tst w4, #0x7fffffff
    cset w6, ne
    b .Lliteral_truth_if_true_release
.Lliteral_truth_if_true_rope:
    ldr w4, [x0, #ARM_OFF_JSStringRope_len]
    cmp w4, #0
    cset w6, ne
    b .Lliteral_truth_if_true_release
.Lliteral_truth_if_true_object:
    ldrb w4, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    cset w6, eq
.Lliteral_truth_if_true_release:
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_truth_if_true_commit:
    tbz w16, #2, .Lliteral_truth_if_true_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #240
.Lliteral_truth_if_true_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_truth_if_true_count
.Lliteral_truth_if_true_counted:
    sub w9, w9, #1
    str w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    sub x21, x21, #16
    cmp w6, #1
    ldursw x10, [x20, #1]
    add x10, x10, #1
    mov x11, #5
    csel x10, x10, x11, eq
    add x20, x20, x10
    ARM_DISPATCH_NEXT 1
.Lliteral_truth_if_false:
    ldp x0, x1, [x21, #-16]
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #15, .Lslow
    ldr x8, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x8, [x8, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    cmp w9, #1
    b.le .Lslow
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lliteral_truth_if_false_object
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_truth_if_false_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_truth_if_false_rope
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbnz w16, #16, .Lslow
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #2, .Lslow
    fmov d0, x0
    fcmp d0, #0.0
    cset w6, ne
    csel w6, wzr, w6, vs
    b .Lliteral_truth_if_false_commit
.Lliteral_truth_if_false_string:
    ldr w4, [x0, #ARM_BIT_JSString_len_BYTE]
    tst w4, #0x7fffffff
    cset w6, ne
    b .Lliteral_truth_if_false_release
.Lliteral_truth_if_false_rope:
    ldr w4, [x0, #ARM_OFF_JSStringRope_len]
    cmp w4, #0
    cset w6, ne
    b .Lliteral_truth_if_false_release
.Lliteral_truth_if_false_object:
    ldrb w4, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    cset w6, eq
.Lliteral_truth_if_false_release:
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_truth_if_false_commit:
    tbz w16, #2, .Lliteral_truth_if_false_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #248
.Lliteral_truth_if_false_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_truth_if_false_count
.Lliteral_truth_if_false_counted:
    sub w9, w9, #1
    str w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    sub x21, x21, #16
    cmp w6, #0
    ldursw x10, [x20, #1]
    add x10, x10, #1
    mov x11, #5
    csel x10, x10, x11, eq
    add x20, x20, x10
    ARM_DISPATCH_NEXT 1
.Lliteral_truth_if_true8:
    ldp x0, x1, [x21, #-16]
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #15, .Lslow
    ldr x8, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x8, [x8, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    cmp w9, #1
    b.le .Lslow
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lliteral_truth_if_true8_object
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_truth_if_true8_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_truth_if_true8_rope
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbnz w16, #16, .Lslow
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #2, .Lslow
    fmov d0, x0
    fcmp d0, #0.0
    cset w6, ne
    csel w6, wzr, w6, vs
    b .Lliteral_truth_if_true8_commit
.Lliteral_truth_if_true8_string:
    ldr w4, [x0, #ARM_BIT_JSString_len_BYTE]
    tst w4, #0x7fffffff
    cset w6, ne
    b .Lliteral_truth_if_true8_release
.Lliteral_truth_if_true8_rope:
    ldr w4, [x0, #ARM_OFF_JSStringRope_len]
    cmp w4, #0
    cset w6, ne
    b .Lliteral_truth_if_true8_release
.Lliteral_truth_if_true8_object:
    ldrb w4, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    cset w6, eq
.Lliteral_truth_if_true8_release:
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_truth_if_true8_commit:
    tbz w16, #2, .Lliteral_truth_if_true8_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #256
.Lliteral_truth_if_true8_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_truth_if_true8_count
.Lliteral_truth_if_true8_counted:
    sub w9, w9, #1
    str w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    sub x21, x21, #16
    cmp w6, #1
    ldrsb x10, [x20, #1]
    add x10, x10, #1
    mov x11, #2
    csel x10, x10, x11, eq
    add x20, x20, x10
    ARM_DISPATCH_NEXT 1
.Lliteral_truth_if_false8:
    ldp x0, x1, [x21, #-16]
    adrp x12, JS_FrameOrdinaryLiteralMode
    ldr w16, [x12, :lo12:JS_FrameOrdinaryLiteralMode]
    cbz w16, .Lslow
    tbnz w16, #15, .Lslow
    ldr x8, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x8, [x8, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    cmp w9, #1
    b.le .Lslow
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lliteral_truth_if_false8_object
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.eq .Lliteral_truth_if_false8_string
    mov x4, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x1, x4
    b.eq .Lliteral_truth_if_false8_rope
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbnz w16, #16, .Lslow
    ldr w15, [sp, #ARM_VM_POLICY_OFF]
    tbz w15, #2, .Lslow
    fmov d0, x0
    fcmp d0, #0.0
    cset w6, ne
    csel w6, wzr, w6, vs
    b .Lliteral_truth_if_false8_commit
.Lliteral_truth_if_false8_string:
    ldr w4, [x0, #ARM_BIT_JSString_len_BYTE]
    tst w4, #0x7fffffff
    cset w6, ne
    b .Lliteral_truth_if_false8_release
.Lliteral_truth_if_false8_rope:
    ldr w4, [x0, #ARM_OFF_JSStringRope_len]
    cmp w4, #0
    cset w6, ne
    b .Lliteral_truth_if_false8_release
.Lliteral_truth_if_false8_object:
    ldrb w4, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    cset w6, eq
.Lliteral_truth_if_false8_release:
    ldr w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    sub w4, w4, #1
    str w4, [x0, #ARM_REF_COUNT_OFFSET]
.Lliteral_truth_if_false8_commit:
    tbz w16, #2, .Lliteral_truth_if_false8_counted
    adrp x12, JS_FrameOrdinaryLiteralStats
    add x12, x12, :lo12:JS_FrameOrdinaryLiteralStats
    add x12, x12, #264
.Lliteral_truth_if_false8_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lliteral_truth_if_false8_count
.Lliteral_truth_if_false8_counted:
    sub w9, w9, #1
    str w9, [x8, #ARM_OFF_JSContext_interrupt_counter]
    sub x21, x21, #16
    cmp w6, #0
    ldrsb x10, [x20, #1]
    add x10, x10, #1
    mov x11, #2
    csel x10, x10, x11, eq
    add x20, x20, x10
    ARM_DISPATCH_NEXT 1
#endif
