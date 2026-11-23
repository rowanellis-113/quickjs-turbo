"""SysV primitive numeric and dense-pop bodies over the real C SF contract."""


def render(source, layout, ordinary):
    # Reuse the actual ordinary boundary's finish protocol, not a second copy
    # of quota/SF/publication semantics. Both frames use the same96-byte type.
    start = ordinary.index(
        "mov r10, QWORD PTR [rbx+56]", ordinary.index("linux_c_invoke_result_ready:")
    )
    end = ordinary.index("mov rdi, QWORD PTR [rbp+80]", start)
    finish = ordinary[start:end].replace("[rbp+", "[rsp+")
    setup = """
sub rsp, 120
.cfi_adjust_cfa_offset 120
mov QWORD PTR [rsp+80], rdi
mov QWORD PTR [rsp+88], rsi
mov DWORD PTR [rsp+96], r8d
mov WORD PTR [rsp+102], cx
dec DWORD PTR [rsi+@CTX_INTERRUPT@]
mov r10, QWORD PTR [rbx+56]
mov rax, QWORD PTR [r10+@RT_SF@]
mov QWORD PTR [rsp+@SF_PREV@], rax
movdqu xmm0, XMMWORD PTR [rdx-16]
movdqu XMMWORD PTR [rsp+@SF_FUNC@], xmm0
mov QWORD PTR [rsp+@SF_ARGV@], rdx
pxor xmm0, xmm0
movdqu XMMWORD PTR [rsp+32], xmm0
movdqu XMMWORD PTR [rsp+48], xmm0
mov QWORD PTR [rsp+72], 0
mov WORD PTR [rsp+@SF_ARGC@], r8w
mov al, BYTE PTR [r10+@RT_SHARED@]
and al, 4
mov BYTE PTR [rsp+100], al
mov BYTE PTR [rsp+101], 0
mov QWORD PTR [r10+@RT_SF@], rsp
or BYTE PTR [r10+@RT_SHARED@], 4
mov DWORD PTR [rsp+144], 0
""".strip().splitlines()
    # Exact accepted bitwise double_is_int32 boxing, including -0,NaN and
    # INT32_MIN. Only labels differ from numeric-invoke.py's shared algorithm.
    numeric = """
test BYTE PTR [rip+JS_LinuxNumericControl], 1
jz scalar_numeric_trampoline
mov rax, QWORD PTR [rsp+@SF_FUNC@]
mov r11, QWORD PTR [rax+@OBJ_FUNCTION@]
movsd xmm0, xmm4
movsd xmm1, xmm5
scalar_numeric_call:
call r11
movq rax, xmm0
mov rdx, rax
shr rdx, 52
and edx, 2047
sub edx, 1023
cmp edx, 30
ja scalar_numeric_special
mov ecx, edx
mov rdx, rax
shl rdx, 12
shl rdx, cl
test rdx, rdx
jne scalar_numeric_float
jmp scalar_numeric_int
scalar_numeric_special:
test rax, rax
jz scalar_numeric_int
mov rdx, 0xc1e0000000000000
cmp rax, rdx
je scalar_numeric_int
scalar_numeric_float:
mov edx, @TAG_FLOAT@
jmp scalar_numeric_boxed
scalar_numeric_int:
cvttsd2si eax, xmm0
xor edx, edx
jmp scalar_numeric_boxed
scalar_numeric_trampoline:
mov rdi, rsp
call JS_LinuxNumericTrampoline
scalar_numeric_boxed:
""".strip().splitlines()
    pop = """
movq r9, xmm4
mov ecx, DWORD PTR [r9+@ARRAY_COUNT@]
test ecx, ecx
jz scalar_pop_empty
dec ecx
mov r10, QWORD PTR [r9+@ARRAY_VALUES@]
mov r11, rcx
shl r11, 4
mov rax, QWORD PTR [r10+r11]
mov rdx, QWORD PTR [r10+r11+8]
scalar_pop_commit:
mov DWORD PTR [r9+@ARRAY_COUNT@], ecx
mov r10, QWORD PTR [r9+@OBJ_PROPERTIES@]
mov QWORD PTR [r10], rcx
jmp scalar_pop_value
scalar_pop_empty:
xor eax, eax
mov edx, @TAG_UNDEFINED@
scalar_pop_value:
""".strip().splitlines()
    packed = [
        "movq xmm0, rax",
        "movq xmm1, rdx",
        "punpcklqdq xmm0, xmm1",
        "mov BYTE PTR [rbx+160], 0",
    ]
    lines = [
        ".hidden JS_LinuxNumericControl, JS_LinuxNumericTrampoline",
        ".hidden JS_LinuxDensePopControl, JS_LinuxDensePopLeafControl, JS_FrameDenseArrayPop",
    ]
    for name, body in [
        ("qjs_linux_numeric_invoke_private", numeric),
        ("qjs_linux_dense_pop_private", pop),
    ]:
        lines += [
            '.section .text.qjs_linux_c_special,"ax",@progbits',
            ".p2align 4",
            ".globl " + name,
            ".hidden " + name,
            ".type " + name + ",@function",
            name + ":",
            ".cfi_startproc",
            "endbr64",
            *setup,
            *body,
            *packed,
            *finish.replace("linux_c_invoke_", name + "_").splitlines(),
            "mov rdi, QWORD PTR [rsp+80]",
            "mov rsi, QWORD PTR [rsp+88]",
            "xor eax, eax",
            "add rsp, 120",
            ".cfi_adjust_cfa_offset -120",
            "ret",
            ".cfi_endproc",
            ".size " + name + ", .-" + name,
        ]
    return lines
