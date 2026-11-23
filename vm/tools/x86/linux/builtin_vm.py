"""Real SysV builtin window/transient/stack entries with fixed ELF CFI."""


def render(ordinary):
    start = ordinary.index(
        "mov rax, QWORD PTR [rbx+32]", ordinary.index("linux_c_invoke_result_ready:")
    )
    end = ordinary.index("mov rdi, QWORD PTR [rbp+80]", start)
    quota = ordinary[start:end]
    lines = [
        ".hidden JS_LinuxBuiltinControl, JS_LinuxBuiltinTargets",
        ".hidden JS_LinuxBuiltinPrepare, JS_LinuxBuiltinRun",
    ]
    name = "qjs_linux_builtin_prepare_private"
    lines += [
        '.section .text.qjs_linux_builtin_entry,"ax",@progbits',
        ".p2align 4",
        ".globl " + name,
        ".hidden " + name,
        ".type " + name + ",@function",
        name + ":",
        ".cfi_startproc",
        "endbr64",
        "sub rsp, 40",
        ".cfi_adjust_cfa_offset 40",
        "mov QWORD PTR [rsp], rdx",
        "mov DWORD PTR [rsp+8], r8d",
        "mov DWORD PTR [rsp+12], r9d",
        "mov QWORD PTR [rsp+16], rsi",
        "mov QWORD PTR [rsp+24], rdi",
        "mov rdi, rbx",
        "call JS_LinuxBuiltinPrepare",
        "mov rdx, QWORD PTR [rsp]",
        "mov r8d, DWORD PTR [rsp+8]",
        "mov r9d, DWORD PTR [rsp+12]",
        "mov rsi, QWORD PTR [rsp+16]",
        "mov rdi, QWORD PTR [rsp+24]",
        "mov r11, rax",
        "add rsp, 40",
        ".cfi_adjust_cfa_offset -40",
        "test r11, r11",
        "jnz qjs_linux_builtin_window_private",
        "jmp qjs_linux_builtin_stack_private",
        ".cfi_endproc",
        ".size " + name + ",.-" + name,
    ]
    for kind, allocation in [("window", 40), ("stack", 168)]:
        name = "qjs_linux_builtin_" + kind + "_private"
        prefix = "builtin_" + kind + "_"
        body = [
            "sub rsp, " + str(allocation),
            ".cfi_adjust_cfa_offset " + str(allocation),
            "mov QWORD PTR [rsp], rdi",
            "mov QWORD PTR [rsp+8], rsi",
        ]
        if kind == "stack":
            body += ["lea r11, [rsp+40]", "mov QWORD PTR [r11+120], 0"]
        body += [
            "mov QWORD PTR [rsp+16], r11",
            "dec DWORD PTR [rsi+@CTX_INTERRUPT@]",
            "mov r10, QWORD PTR [rbx+56]",
            "mov rax, QWORD PTR [r10+@RT_SF@]",
            "mov QWORD PTR [r11+@SF_PREV@], rax",
            "movdqu xmm0, XMMWORD PTR [rdx-16]",
            "movdqu XMMWORD PTR [r11+@SF_FUNC@], xmm0",
            "mov QWORD PTR [r11+@SF_ARGV@], rdx",
            "pxor xmm0, xmm0",
            "movdqu XMMWORD PTR [r11+40], xmm0",
            "movdqu XMMWORD PTR [r11+56], xmm0",
            "mov QWORD PTR [r11+72], 0",
            "mov WORD PTR [r11+@SF_ARGC@], r8w",
            "lea rax, [rip+interp_table+2048]",
            "test r9d, r9d",
            "jz " + prefix + "this",
            "lea rax, [rdx-32]",
            prefix + "this:",
            "mov QWORD PTR [r11+32], rax",
            "mov rax, QWORD PTR [rsp+" + str(allocation + 72) + "]",
            "mov QWORD PTR [r11+104], rax",
            "mov rdx, QWORD PTR [rax]",
            "mov QWORD PTR [r11+80], rdx",
            "mov QWORD PTR [r11+88], rbx",
            "mov QWORD PTR [r11+96], 0",
            "lea rdx, [r11+80]",
            "mov QWORD PTR [rax], rdx",
            "mov al, BYTE PTR [r10+@RT_SHARED@]",
            "and al, 4",
            "mov BYTE PTR [r11+112], al",
            "mov QWORD PTR [r10+@RT_SF@], r11",
            "or BYTE PTR [r10+@RT_SHARED@], 4",
            "mov rdi, r11",
            "lea rsi, [rbx+40]",
            prefix + "call:",
            "call JS_LinuxBuiltinRun",
            "mov r11, QWORD PTR [rsp+16]",
            "mov r10, QWORD PTR [rbx+56]",
            "cmp QWORD PTR [rbx+48], @TAG_EXCEPTION@",
            "sete BYTE PTR [rbx+160]",
            "mov rax, QWORD PTR [r11+104]",
            "mov rdx, QWORD PTR [r11+80]",
            "mov QWORD PTR [rax], rdx",
            "mov al, BYTE PTR [r10+@RT_SHARED@]",
            "and al, 251",
            "or al, BYTE PTR [r11+112]",
            "mov BYTE PTR [r10+@RT_SHARED@], al",
            "mov rax, QWORD PTR [r11+@SF_PREV@]",
            "mov QWORD PTR [r10+@RT_SF@], rax",
            "mov rax, QWORD PTR [r11+120]",
            "test rax, rax",
            "jz " + prefix + "released",
            "sub QWORD PTR [rax+16], 128",
            "sub QWORD PTR [r10+@RT_TOP@], 128",
            "cmp QWORD PTR [r10+@RT_LIMIT@], 0",
            "je " + prefix + "released",
            "sub QWORD PTR [r10+@RT_LIMIT@], 128",
            prefix + "released:",
        ]
        body += quota.replace("linux_c_invoke_", prefix).splitlines()
        body += [
            "movdqu xmm0, XMMWORD PTR [rbx+40]",
            "mov rdi, QWORD PTR [rsp]",
            "mov rsi, QWORD PTR [rsp+8]",
            "movzx eax, BYTE PTR [rbx+160]",
            "add rsp, " + str(allocation),
            ".cfi_adjust_cfa_offset -" + str(allocation),
            "ret",
        ]
        lines += [
            '.section .text.qjs_linux_builtin_entry,"ax",@progbits',
            ".p2align 4",
            ".globl " + name,
            ".hidden " + name,
            ".type " + name + ",@function",
            name + ":",
            ".cfi_startproc",
            "endbr64",
            *body,
            ".cfi_endproc",
            ".size " + name + ",.-" + name,
        ]
    return lines
