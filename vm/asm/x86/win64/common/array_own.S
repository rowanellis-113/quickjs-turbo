.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix

/* Win64 C ABI: (ctx=rcx, object=rdx, uint32 index=r8d, result=r9).
* Borrow the receiver and duplicate an existing ordinary numeric data value.
* Misses preserve every argument and the original fast-array helper contract.
*/
.section .qjsleaf$arrayown,"xr"
.p2align 4
.globl JS_FrameFastArrayOwnGet, JS_FrameFastArrayOwnGet_end
.def JS_FrameFastArrayOwnGet; .scl 2; .type 32; .endef
JS_FrameFastArrayOwnGet:
.if QJS_ABI_HAS_PREFIX_RC == 0
.if QJS_ABI_SIZE_JSValue != 16 || QJS_ABI_SIZE_JSShapeProperty != 8 || QJS_ABI_OFF_JSShapeProperty_atom != 4
.error "array own leaf requires the reviewed value/shape descriptor ABI"
.endif
    cmp WORD PTR [rdx+QJS_ABI_OFF_JSObject_class_id], QJS_ABI_CONST_JS_CLASS_ARRAY
    jne JS_FrameFastArrayOwnGet_fallback
    test BYTE PTR [rdx+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jnz JS_FrameFastArrayOwnGet_fallback
/* A negative int32 key and uint32 >= 2^31 require their original atom path. */
    test r8d, r8d
    js JS_FrameFastArrayOwnGet_fallback
    mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSObject_shape]
    mov eax, r8d
    and eax, DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_hash_mask]
    neg rax
    mov eax, DWORD PTR [r10+rax*4-4]
    add r10, QJS_ABI_OFF_JSShape_prop
    mov r11d, r8d
    or r11d, 0x80000000
JS_FrameFastArrayOwnGet_probe:
    test eax, eax
    jz JS_FrameFastArrayOwnGet_fallback
    cmp DWORD PTR [r10+rax*8-4], r11d
    je JS_FrameFastArrayOwnGet_found
    mov eax, DWORD PTR [r10+rax*8-8]
    and eax, 0x03ffffff
    jmp JS_FrameFastArrayOwnGet_probe
JS_FrameFastArrayOwnGet_found:
/* Pinned JSShapeProperty: 26 hash-next bits, then six property flag bits. */
    test DWORD PTR [r10+rax*8-8], 0xc0000000
    jnz JS_FrameFastArrayOwnGet_fallback
    dec eax
    shl rax, 4
    mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSObject_prop]
    mov r11, QWORD PTR [r10+rax]
    mov rax, QWORD PTR [r10+rax+8]
    test eax, eax
    jns JS_FrameFastArrayOwnGet_value
    inc DWORD PTR [r11+QJS_ABI_REF_COUNT_OFFSET]
JS_FrameFastArrayOwnGet_value:
    mov QWORD PTR [r9], r11
    mov QWORD PTR [r9+8], rax
    mov eax, 1
    ret
.endif
JS_FrameFastArrayOwnGet_fallback:
    jmp qjs_frame_core_js_get_fast_array_element
JS_FrameFastArrayOwnGet_end:
.section .xdata$qjsarrayown,"dr"
.p2align 2
JS_FrameFastArrayOwnGet_unwind:
.byte 1, 0, 0, 0
.section .pdata$qjsarrayown,"dr"
.p2align 2
.rva JS_FrameFastArrayOwnGet, JS_FrameFastArrayOwnGet_end, JS_FrameFastArrayOwnGet_unwind
