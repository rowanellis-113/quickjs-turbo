/* Native slot writes. set_* duplicates its input,put_* consumes it.
* Nonlast releases stay here;last release commits through the source-owned
* continuation and original typed C Free owner before any reentrant callback. */
.macro ARM_SLOT_STORE name, base, first, keep, width
.L\name:
.if \width == 0
    sub w10, w9, #\first
    mov x13, #1
.elseif \width == 1
    ldrb w10, [x20, #1]
    mov x13, #2
.else
    ldurh w10, [x20, #1]
    mov x13, #3
.endif
    add x12, \base, x10, lsl #4
    mov w17, #\keep
    b .Lslot_store
.endm
    ARM_SLOT_STORE put_loc_short, x23, ARM_OP_put_loc0, 0, 0
    ARM_SLOT_STORE set_loc_short, x23, ARM_OP_set_loc0, 1, 0
    ARM_SLOT_STORE put_arg_short, x24, ARM_OP_put_arg0, 0, 0
    ARM_SLOT_STORE set_arg_short, x24, ARM_OP_set_arg0, 1, 0
    ARM_SLOT_STORE put_loc8, x23, 0, 0, 1
    ARM_SLOT_STORE set_loc8, x23, 0, 1, 1
    ARM_SLOT_STORE put_loc, x23, 0, 0, 2
    ARM_SLOT_STORE set_loc, x23, 0, 1, 2
    ARM_SLOT_STORE put_arg, x24, 0, 0, 2
    ARM_SLOT_STORE set_arg, x24, 0, 1, 2
.purgem ARM_SLOT_STORE
.Lslot_store:
    ldp x10, x11, [x21, #-16]
.Lslot_store_value:
    ldp x14, x15, [x12]
    orr x16, x11, x15
    tbz x16, #63, .Lslot_policy_ready
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tbz w16, #0, .Lslow
.Lslot_policy_ready:
    tbz x15, #63, .Lslot_old_ready
    ldur w16, [x14, #ARM_REF_COUNT_OFFSET]
    cmp w16, #1
    b.le .Lslot_last
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x4, tpidr_el0
    add x4, x4, :tprel_hi12:qjs_aarch64_store_counters
    add x4, x4, :tprel_lo12_nc:qjs_aarch64_store_counters
    ldr x5, [x4]
    add x5, x5, #1
    str x5, [x4]
#endif
.Lslot_old_ready:
    cbz w17, .Lslot_new_ready
    tbz x11, #63, .Lslot_new_ready
    ldur w16, [x10, #ARM_REF_COUNT_OFFSET]
    add w16, w16, #1
    stur w16, [x10, #ARM_REF_COUNT_OFFSET]
.Lslot_new_ready:
    tbz x15, #63, .Lslot_release_ready
// Reload after Dup: old/new may be the same heap object.
    ldur w16, [x14, #ARM_REF_COUNT_OFFSET]
    sub w16, w16, #1
    stur w16, [x14, #ARM_REF_COUNT_OFFSET]
.Lslot_release_ready:
    stp x10, x11, [x12]
    cbnz w17, .Lslot_keep
    sub x21, x21, #16
.Lslot_keep:
    add x20, x20, x13
    ARM_DISPATCH_NEXT 1

.Linc_loc:
    mov w17, #1
    b .Lupdate_local
.Ldec_loc:
    mov w17, #-1
.Lupdate_local:
    ldrb w12, [x20, #1]
    add x12, x23, x12, lsl #4
    ldp x10, x11, [x12]
    cbnz x11, .Lslow
    adds w10, w10, w17
    b.vs .Lslow
    stp x10, x11, [x12]
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
.Ladd_loc:
    ldrb w12, [x20, #1]
    add x12, x23, x12, lsl #4
    ldp x10, x11, [x12]
    ldp x14, x15, [x21, #-16]
    orr x16, x11, x15
#if ARM_HAS_NUMERIC_WORKERS
    cbnz x16, .Lnumeric_add_local
#elif ARM_HAS_STRING_WORKERS
    cbnz x16, .Lstring_add_local
#else
    cbnz x16, .Lslow
#endif
    adds w10, w10, w14
    b.vs .Lslow
    stp x10, x11, [x12]
    sub x21, x21, #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
