/* Reuse strict_identity.inc's nonlast proof inside the register VM.
* Every guard precedes decrements;misses preserve both operands. */
.section .data$qjsrefmode,"dw"
.p2align 2
.globl JS_FrameReferenceMode
JS_FrameReferenceMode:
.long 0
.globl JS_FrameLargeGlobalMode
JS_FrameLargeGlobalMode:
.long 0
.macro FRAME_STRICT_REFERENCE prefix
    cmp DWORD PTR [rip+JS_FrameReferenceMode], 1
    jne \prefix\()_reference_miss
    mov eax, DWORD PTR [r13-24]
    cmp eax, DWORD PTR [r13-8]
    jne \prefix\()_reference_miss
    cmp eax, -8
    je \prefix\()_reference_tag
    cmp eax, QJS_ABI_CONST_JS_TAG_OBJECT
    jne \prefix\()_reference_miss
\prefix\()_reference_tag:
    mov r8, QWORD PTR [r13-32]
    mov r9, QWORD PTR [r13-16]
    cmp r8, r9
    jne \prefix\()_reference_distinct
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 2
    jle \prefix\()_reference_miss
    mov eax, 1
    jmp \prefix\()_reference_release
\prefix\()_reference_distinct:
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle \prefix\()_reference_miss
    cmp DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    jle \prefix\()_reference_miss
    xor eax, eax
\prefix\()_reference_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    sub DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp \prefix\()_commit
\prefix\()_reference_miss:
.endm
