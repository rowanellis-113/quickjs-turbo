    mov r11d, DWORD PTR [rip+JS_FrameStrictEqMode]
    shl ecx, 31
    or r11d, ecx
    mov eax, DWORD PTR [r13-24]
    mov edx, DWORD PTR [r13-8]
    cmp eax, -7
    jne JS_FrameStrictEqClean_number
    cmp edx, -7
    jne JS_FrameStrictEqClean_number
    test r11d, 1
    jz JS_FrameStrictEqClean_fallback
    mov r8, QWORD PTR [r13-32]
    mov r9, QWORD PTR [r13-16]
    cmp r8, r9
    jne JS_FrameStrictEqClean_different_owners
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 2
    jle JS_FrameStrictEqClean_last_owner
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_0_1
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+0]
JS_FrameStrictEqClean_observed_0_1:
    mov eax, 1
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_different_owners:
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameStrictEqClean_last_owner
    cmp DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameStrictEqClean_last_owner
    mov r10d, DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE]
    mov ecx, DWORD PTR [r9+QJS_ABI_BIT_JSString_len_BYTE]
    test r10d, r10d
    jns JS_FrameStrictEqClean_left_narrow
    or r11d, 65536
JS_FrameStrictEqClean_left_narrow:
    test ecx, ecx
    jns JS_FrameStrictEqClean_right_narrow
    or r11d, 131072
JS_FrameStrictEqClean_right_narrow:
    and r10d, 2147483647
    and ecx, 2147483647
    cmp r10d, ecx
    jne JS_FrameStrictEqClean_length_different
    cmp r10d, 8
    ja JS_FrameStrictEqClean_fallback
    test r10d, r10d
    jz JS_FrameStrictEqClean_short_equal
    mov eax, DWORD PTR [r8+QJS_ABI_BIT_JSString_hash_BYTE]
    shr eax, 28
    and eax, 3
    cmp eax, 1
    je JS_FrameStrictEqClean_left_slice
    cmp eax, 2
    je JS_FrameStrictEqClean_left_indirect
    test eax, eax
    jnz JS_FrameStrictEqClean_fallback
    lea rax, [r8+24]
    jmp JS_FrameStrictEqClean_left_data
JS_FrameStrictEqClean_left_slice:
    mov rax, QWORD PTR [r8+24]
    mov ecx, DWORD PTR [r8+32]
    lea rax, [rax+rcx+24]
    jmp JS_FrameStrictEqClean_left_data
JS_FrameStrictEqClean_left_indirect:
    mov rax, QWORD PTR [r8+24]
JS_FrameStrictEqClean_left_data:
    mov edx, DWORD PTR [r9+QJS_ABI_BIT_JSString_hash_BYTE]
    shr edx, 28
    and edx, 3
    cmp edx, 1
    je JS_FrameStrictEqClean_right_slice
    cmp edx, 2
    je JS_FrameStrictEqClean_right_indirect
    test edx, edx
    jnz JS_FrameStrictEqClean_fallback
    lea rdx, [r9+24]
    jmp JS_FrameStrictEqClean_right_data
JS_FrameStrictEqClean_right_slice:
    mov rdx, QWORD PTR [r9+24]
    mov ecx, DWORD PTR [r9+32]
    lea rdx, [rdx+rcx+24]
    jmp JS_FrameStrictEqClean_right_data
JS_FrameStrictEqClean_right_indirect:
    mov rdx, QWORD PTR [r9+24]
JS_FrameStrictEqClean_right_data:
    mov ecx, r11d
    and ecx, 196608
    test ecx, ecx
    jz JS_FrameStrictEqClean_same_width
    cmp ecx, 196608
    jne JS_FrameStrictEqClean_mixed_width
    shl r10d, 1
JS_FrameStrictEqClean_same_width:
    cmp r10d, 8
    jb JS_FrameStrictEqClean_four_bytes
    mov rcx, QWORD PTR [rax]
    cmp rcx, QWORD PTR [rdx]
    jne JS_FrameStrictEqClean_short_different
    mov rcx, QWORD PTR [rax+r10-8]
    cmp rcx, QWORD PTR [rdx+r10-8]
    jne JS_FrameStrictEqClean_short_different
    jmp JS_FrameStrictEqClean_short_equal
JS_FrameStrictEqClean_four_bytes:
    cmp r10d, 4
    jb JS_FrameStrictEqClean_two_bytes
    mov ecx, DWORD PTR [rax]
    cmp ecx, DWORD PTR [rdx]
    jne JS_FrameStrictEqClean_short_different
    mov ecx, DWORD PTR [rax+r10-4]
    cmp ecx, DWORD PTR [rdx+r10-4]
    jne JS_FrameStrictEqClean_short_different
    jmp JS_FrameStrictEqClean_short_equal
JS_FrameStrictEqClean_two_bytes:
    cmp r10d, 2
    jb JS_FrameStrictEqClean_one_byte
    movzx ecx, WORD PTR [rax]
    cmp cx, WORD PTR [rdx]
    jne JS_FrameStrictEqClean_short_different
    movzx ecx, WORD PTR [rax+r10-2]
    cmp cx, WORD PTR [rdx+r10-2]
    jne JS_FrameStrictEqClean_short_different
    jmp JS_FrameStrictEqClean_short_equal
JS_FrameStrictEqClean_one_byte:
    movzx ecx, BYTE PTR [rax]
    cmp cl, BYTE PTR [rdx]
    jne JS_FrameStrictEqClean_short_different
    jmp JS_FrameStrictEqClean_short_equal
JS_FrameStrictEqClean_mixed_width:
    test r11d, 65536
    jz JS_FrameStrictEqClean_right_wide
JS_FrameStrictEqClean_left_wide:
    movzx ecx, WORD PTR [rax]
    cmp ecx, 255
    ja JS_FrameStrictEqClean_mixed_different
    cmp cl, BYTE PTR [rdx]
    jne JS_FrameStrictEqClean_mixed_different
    add rax, 2
    inc rdx
    dec r10d
    jnz JS_FrameStrictEqClean_left_wide
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_3_2
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+24]
JS_FrameStrictEqClean_observed_3_2:
    mov eax, 1
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_right_wide:
    movzx ecx, WORD PTR [rdx]
    cmp ecx, 255
    ja JS_FrameStrictEqClean_mixed_different
    cmp cl, BYTE PTR [rax]
    jne JS_FrameStrictEqClean_mixed_different
    inc rax
    add rdx, 2
    dec r10d
    jnz JS_FrameStrictEqClean_right_wide
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_3_3
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+24]
JS_FrameStrictEqClean_observed_3_3:
    mov eax, 1
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_mixed_different:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_3_4
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+24]
JS_FrameStrictEqClean_observed_3_4:
    xor eax, eax
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_short_equal:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_2_5
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+16]
JS_FrameStrictEqClean_observed_2_5:
    mov eax, 1
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_short_different:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_2_6
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+16]
JS_FrameStrictEqClean_observed_2_6:
    xor eax, eax
    jmp JS_FrameStrictEqClean_string_release
JS_FrameStrictEqClean_length_different:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_1_7
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+8]
JS_FrameStrictEqClean_observed_1_7:
    xor eax, eax
JS_FrameStrictEqClean_string_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    sub DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameStrictEqClean_commit
JS_FrameStrictEqClean_number:
    test r11d, 2
    jz JS_FrameStrictEqClean_fallback
    cmp eax, 8
    je JS_FrameStrictEqClean_left_float
    cmp edx, 8
    jne JS_FrameStrictEqClean_fallback
    test eax, eax
    jz JS_FrameStrictEqClean_left_int
    cmp eax, 3
    jbe JS_FrameStrictEqClean_mixed_false
    cmp eax, 7
    je JS_FrameStrictEqClean_mixed_false
    jmp JS_FrameStrictEqClean_fallback
JS_FrameStrictEqClean_left_int:
    cvtsi2sd xmm0, DWORD PTR [r13-32]
    movsd xmm1, QWORD PTR [r13-16]
    jmp JS_FrameStrictEqClean_compare_numbers
JS_FrameStrictEqClean_left_float:
    movsd xmm0, QWORD PTR [r13-32]
    cmp edx, 8
    je JS_FrameStrictEqClean_right_float
    test edx, edx
    jz JS_FrameStrictEqClean_right_int
    cmp edx, 3
    jbe JS_FrameStrictEqClean_mixed_false
    cmp edx, 7
    je JS_FrameStrictEqClean_mixed_false
    jmp JS_FrameStrictEqClean_fallback
JS_FrameStrictEqClean_right_float:
    movsd xmm1, QWORD PTR [r13-16]
    jmp JS_FrameStrictEqClean_compare_numbers
JS_FrameStrictEqClean_right_int:
    cvtsi2sd xmm1, DWORD PTR [r13-16]
JS_FrameStrictEqClean_compare_numbers:
    ucomisd xmm0, xmm1
    setnp dl
    sete al
    and al, dl
    movzx eax, al
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_4_8
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+32]
JS_FrameStrictEqClean_observed_4_8:
    jmp JS_FrameStrictEqClean_commit
JS_FrameStrictEqClean_mixed_false:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_5_9
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+40]
JS_FrameStrictEqClean_observed_5_9:
    xor eax, eax
JS_FrameStrictEqClean_commit:
    shr r11d, 31
    xor eax, r11d
    mov QWORD PTR [r13-32], rax
    mov QWORD PTR [r13-24], 1
    sub r13, 16
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameStrictEqClean_last_owner:
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_7_10
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+56]
JS_FrameStrictEqClean_observed_7_10:
JS_FrameStrictEqClean_fallback:
    FRAME_STRICT_REFERENCE JS_FrameStrictEqClean
    test r11d, 8
    jz JS_FrameStrictEqClean_observed_6_11
    lock inc QWORD PTR [rip+JS_FrameStrictEqStats+48]
JS_FrameStrictEqClean_observed_6_11:
    test r11d, 2147483648
    jnz JS_FrameStrictEqOldCleanNeq
    jmp JS_FrameStrictEqOldCleanEq
