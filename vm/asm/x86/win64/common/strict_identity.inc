/* Win64 C ABI: (ctx=rcx, sp=rdx, is_neq=r8b), return status in eax.
* Only consume object/Symbol operands whose references remain positive.
* Every miss preserves all arguments and reaches the original C helper.
*/
.section .qjsleaf$zzzzzzzzidentity,"xr"
.p2align 4
.globl JS_FrameStrictIdentitySlow, JS_FrameStrictIdentitySlow_end
.def JS_FrameStrictIdentitySlow; .scl 2; .type 32; .endef
JS_FrameStrictIdentitySlow:
    mov r9d, DWORD PTR [rdx-24]
    cmp r9d, DWORD PTR [rdx-8]
    jne JS_FrameStrictIdentitySlow_fallback
    cmp r9d, -8
    je JS_FrameStrictIdentitySlow_reference
    cmp r9d, QJS_ABI_CONST_JS_TAG_OBJECT
    jne JS_FrameStrictIdentitySlow_fallback
JS_FrameStrictIdentitySlow_reference:
    mov r9, QWORD PTR [rdx-32]
    mov r10, QWORD PTR [rdx-16]
    cmp r9, r10
    jne JS_FrameStrictIdentitySlow_distinct
    cmp DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 2
    jle JS_FrameStrictIdentitySlow_fallback
    mov eax, 1
    jmp JS_FrameStrictIdentitySlow_release
JS_FrameStrictIdentitySlow_distinct:
    cmp DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameStrictIdentitySlow_fallback
    cmp DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameStrictIdentitySlow_fallback
    xor eax, eax
JS_FrameStrictIdentitySlow_release:
    sub DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    sub DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET], 1
    movzx r11d, r8b
    xor eax, r11d
    mov QWORD PTR [rdx-32], rax
    mov QWORD PTR [rdx-24], 1
    xor eax, eax
    ret
JS_FrameStrictIdentitySlow_fallback:
    jmp qjs_frame_core_js_strict_eq_slow
JS_FrameStrictIdentitySlow_end:
.section .xdata$qjseqid,"dr"
.p2align 2
JS_FrameStrictIdentitySlow_unwind:
.byte 1, 0, 0, 0
.section .pdata$zzqjseqid,"dr"
.p2align 2
.rva JS_FrameStrictIdentitySlow, JS_FrameStrictIdentitySlow_end, JS_FrameStrictIdentitySlow_unwind
