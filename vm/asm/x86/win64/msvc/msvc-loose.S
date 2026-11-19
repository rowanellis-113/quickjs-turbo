.include "interpreter-private-abi-gas.inc"
/* R8266: same VM registers/stack; no engine C call on the null lane. */
.intel_syntax noprefix
.section .qzzem$looseeq,"dw"
.p2align 3
.globl JS_FrameLooseEqStats
JS_FrameLooseEqStats:
.zero 64
.section .qzzec$looseeq,"xr"
.p2align 4
.globl JS_FrameLooseEqEq, JS_FrameLooseEqEq_end
.def JS_FrameLooseEqEq; .scl 2; .type 32; .endef
JS_FrameLooseEqEq:
    mov r11d, DWORD PTR [rip+JS_FrameLooseEqMode]
    test r11d, r11d
    jz JS_FrameLooseEqEq_configure
    test r11d, 32
    jz .Lloose_observed_1
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+0]
.Lloose_observed_1:
    mov ecx, 0
    jmp JS_FrameLooseEqCommon
JS_FrameLooseEqEq_configure:
    call JS_FrameLooseEqConfigure
    jmp JS_FrameLooseEqEq
JS_FrameLooseEqEq_end:
.p2align 4
.globl JS_FrameLooseEqNeq, JS_FrameLooseEqNeq_end
.def JS_FrameLooseEqNeq; .scl 2; .type 32; .endef
JS_FrameLooseEqNeq:
    mov r11d, DWORD PTR [rip+JS_FrameLooseEqMode]
    test r11d, r11d
    jz JS_FrameLooseEqNeq_configure
    test r11d, 32
    jz .Lloose_observed_2
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+8]
.Lloose_observed_2:
    mov ecx, 1
    jmp JS_FrameLooseEqCommon
JS_FrameLooseEqNeq_configure:
    call JS_FrameLooseEqConfigure
    jmp JS_FrameLooseEqNeq
JS_FrameLooseEqNeq_end:
.globl JS_FrameLooseEqCommon, JS_FrameLooseEqCommon_end
.def JS_FrameLooseEqCommon; .scl 2; .type 32; .endef
JS_FrameLooseEqCommon:
    shl ecx, 31
    or r11d, ecx
    mov eax, DWORD PTR [r13-24]
    mov edx, DWORD PTR [r13-8]
    test r11d, 1
    jz .Lloose_null
    cmp eax, -7
    jne .Lloose_null
    cmp edx, -7
    jne .Lloose_null
    test r11d, 32
    jz .Lloose_observed_3
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+16]
.Lloose_observed_3:
    mov ecx, r11d
    shr ecx, 31
    jmp JS_FrameStrictEqClean
.Lloose_null:
    test r11d, 2
    jz .Lloose_fallback
    cmp eax, 2
    je .Lloose_left_null
    cmp eax, 3
    je .Lloose_left_null
    cmp edx, 2
    je .Lloose_right_null
    cmp edx, 3
    jne .Lloose_fallback
.Lloose_right_null:
    mov r8, QWORD PTR [r13-32]
    jmp .Lloose_other_tag
.Lloose_left_null:
    mov eax, edx
    mov r8, QWORD PTR [r13-16]
.Lloose_other_tag:
    cmp eax, 3
    jbe .Lloose_immediate
    cmp eax, 7
    je .Lloose_immediate
    cmp eax, 8
    je .Lloose_immediate
    cmp eax, -1
    je .Lloose_object
    cmp eax, -9
    jl .Lloose_fallback
    cmp eax, -6
    jg .Lloose_fallback
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle .Lloose_last_owner
.Lloose_nonlast:
    test r11d, 32
    jz .Lloose_observed_4
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+32]
.Lloose_observed_4:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    xor eax, eax
    jmp .Lloose_commit
.Lloose_object:
    test r11d, 4
    jz .Lloose_fallback
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    jnz .Lloose_fallback
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle .Lloose_last_owner
    test r11d, 32
    jz .Lloose_object_hit
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+56]
.Lloose_object_hit:
    jmp .Lloose_nonlast
.Lloose_immediate:
    test r11d, 32
    jz .Lloose_observed_5
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+24]
.Lloose_observed_5:
    sub eax, 2
    cmp eax, 1
    setbe al
    movzx eax, al
    jmp .Lloose_commit
.Lloose_last_owner:
    test r11d, 32
    jz .Lloose_observed_6
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+48]
.Lloose_observed_6:
.Lloose_fallback:
    test r11d, 32
    jz .Lloose_observed_7
    lock inc QWORD PTR [rip+JS_FrameLooseEqStats+40]
.Lloose_observed_7:
    test r11d, 2147483648
    jnz JS_FrameLooseEqOldNeq
    jmp JS_FrameLooseEqOldEq
.Lloose_commit:
    shr r11d, 31
    xor eax, r11d
    mov QWORD PTR [r13-32], rax
    mov QWORD PTR [r13-24], 1
    sub r13, 16
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameLooseEqCommon_end:
.section .pdata$zzzzlooseeq,"dr"
.p2align 2
.rva JS_FrameLooseEqEq, JS_FrameLooseEqEq_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameLooseEqNeq, JS_FrameLooseEqNeq_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameLooseEqCommon, JS_FrameLooseEqCommon_end, JS_FrameInterpPropertyCold_unwind
