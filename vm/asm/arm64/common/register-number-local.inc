/* Number-only add_loc; original owners handle every non-number. MIT.
* Inputs are the original local address x12, lhs x10/x11 and rhs x14/x15.
* No owner/PC/SP is changed before both number guards succeed. */
@STEM@_overflow:
    ldr x10, [x12]
@STEM@_number:
    cbz x11, @STEM@_lhs_int
    cmp x11, #ARM_CONST_JS_TAG_FLOAT64
    b.ne @STEM@_fallback
    fmov d0, x10
    b @STEM@_lhs_ready
@STEM@_lhs_int:
    scvtf d0, w10
@STEM@_lhs_ready:
    cbz x15, @STEM@_rhs_int
    cmp x15, #ARM_CONST_JS_TAG_FLOAT64
    b.ne @STEM@_fallback
    fmov d1, x14
    b @STEM@_rhs_ready
@STEM@_rhs_int:
    scvtf d1, w14
@STEM@_rhs_ready:
    fadd d0, d0, d1
    fmov x10, d0
    mov x11, #ARM_CONST_JS_TAG_FLOAT64
    stp x10, x11, [x12]
    sub x21, x21, #16
    add x20, x20, #2
    ARM_DISPATCH_NEXT 1
@STEM@_fallback:
    @FALLBACK@
