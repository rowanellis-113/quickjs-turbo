"""Release-only argc0 root: volatile assembly setup, real VM CALL/RET."""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
from native_abi import current as current_abi


def append(gas, diagnostics, out):
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    output = out / "quickjs-interpreter-native-root-zero-win64.S"
    output.parent.mkdir(parents=True, exist_ok=True)
    if diagnostics:
        output.write_text(".intel_syntax noprefix\n.text\n", encoding="utf-8")
        return
    start = gas.index("JS_FrameCallEntryDispatch:")
    end = gas.index("JS_FrameCallEntryDispatch_end:")
    old = "jmp JS_FrameNativeRootSelect"
    assert gas[start:end].count(old) == 1
    gas[gas.index(old, start, end)] = "jmp JS_FrameNativeRootZeroSelect"
    base = len(gas)
    fallback = "JS_FrameRootLeafSelect"
    entry = "JS_FrameNativeRootZero"
    guard = [
        "cmp DWORD PTR [rsp+48], 0",
        "jne " + fallback,
        "test DWORD PTR [rsp+64], -3",
        "jnz " + fallback,
        "cmp DWORD PTR [r8+8], -1",
        "jne " + fallback,
        "mov r11, QWORD PTR [r8]",
        f"cmp WORD PTR [r11+{abi_fields['JSObject.class_id']}], 13",
        "jne " + fallback,
        f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe " + fallback,
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
        "jz " + fallback,
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}], 0",
        "jne " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 240",
        "ja " + fallback,
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        "cmp BYTE PTR [rip+JS_FrameNativeRootControl], 0",
        "je JS_FrameNativeRootConfig",
        "cmp BYTE PTR [rip+JS_FrameNativeRootControl], 1",
        "jne " + fallback,
        "lea r10, [rsp-8192]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        "cmp BYTE PTR [rip+JS_FrameNativeRootZeroControl], 0",
        "je JS_FrameNativeRootZeroConfig",
        "cmp BYTE PTR [rip+JS_FrameNativeRootZeroControl], 1",
        "jne " + fallback,
        "jmp " + entry,
    ]
    config = [
        "sub rsp, 88",
        "root_zero_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "lea rcx, [rip+JS_FrameNativeRootZeroDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FrameNativeRootZeroControl], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp JS_FrameNativeRootZeroSelect",
    ]
    # Fixed locations above Win64 shadow32. No nonvolatile GPR/XMM changes.
    # state112..279, segment288..319, sites320..831, next832, arena848..4943.
    run = [
        "mov eax, 4952",
        "call ___chkstk_ms",
        "sub rsp, rax",
        "root_zero_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "mov QWORD PTR [rsp+48], rax",
        "movdqu xmm1, XMMWORD PTR [r8]",
        "movdqu XMMWORD PTR [rsp+64], xmm1",
        "movdqu xmm1, XMMWORD PTR [r9]",
        "movdqu XMMWORD PTR [rsp+80], xmm1",
        "mov r11, QWORD PTR [r8]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
        "mov QWORD PTR [rsp+96], r11",
        # Same caller-realm poll, before charge/publication.
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        "jg root_zero_polled",
        "mov rcx, rdx",
        "call qjs_frame_core___js_poll_interrupts",
        "test eax, eax",
        "jnz root_zero_exception",
        "root_zero_polled:",
        "mov rax, QWORD PTR [rsp+48]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], 0",
        "jne root_zero_host_ready",
        "lea rcx, [rip+JS_FrameNativeRootHostDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "mov rax, QWORD PTR [rsp+48]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], cl",
        "root_zero_host_ready:",
        "mov r11, QWORD PTR [rsp+96]",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "shl r10d, 4",
        "add r10d, 128",
        "mov QWORD PTR [rsp+56], r10",
        # Exact logical check after physical entry, before quota/publication.
        "mov rax, rsp",
        "sub rax, r10",
        "mov r9, QWORD PTR [rsp+48]",
        f"cmp rax, QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}]",
        "jb root_zero_overflow",
        "pxor xmm0, xmm0",
    ]
    for q in range(112, 272, 16):
        run += ["movdqu XMMWORD PTR [rsp+" + str(q) + "], xmm0"]
    run += ["mov QWORD PTR [rsp+272], 0", "mov QWORD PTR [rsp+832], 0", "xor eax, eax"]
    for q in range(320, 832, 32):
        run += ["mov QWORD PTR [rsp+" + str(q) + "], rax"]
    # SF initialization: zero fields48..79, vars/ref table, then named fields.
    run += [
        "movdqu XMMWORD PTR [rsp+880], xmm0",
        "movdqu XMMWORD PTR [rsp+896], xmm0",
        "movdqu XMMWORD PTR [rsp+912], xmm0",
        "mov QWORD PTR [rsp+952], 0",
        f"mov rax, QWORD PTR [r9+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+848], rax",
        "movdqu xmm1, XMMWORD PTR [rsp+64]",
        "movdqu XMMWORD PTR [rsp+856], xmm1",
        # Preserve even a non-NULL argv with actual argc0.
        "mov rax, QWORD PTR [rsp+5008]",
        "mov QWORD PTR [rsp+872], rax",
        "lea r8, [rsp+976]",
        "mov QWORD PTR [rsp+880], r8",
        f"mov al, BYTE PTR [r11+{abi_bits['JSFunctionBytecode.is_strict_mode'][0][0]}]",
        "and al, 1",
        "mov BYTE PTR [rsp+908], al",
        "mov BYTE PTR [rsp+910], 1",  # sf root marker62; cache marker63 remains0
        "mov QWORD PTR [rsp+928], r11",
        "movdqu xmm1, XMMWORD PTR [rsp+80]",
        "movdqu XMMWORD PTR [rsp+936], xmm1",
        "lea rdx, [rsp+288]",
        "mov QWORD PTR [rsp+960], rdx",
        "mov DWORD PTR [rsp+968], r10d",
        "mov DWORD PTR [rsp+972], 0",
        "mov QWORD PTR [rdx], 0",
        "mov QWORD PTR [rdx+8], 4096",
        "mov QWORD PTR [rdx+16], r10",
        "lea rax, [rsp+848]",
        "mov QWORD PTR [rdx+24], rax",
        # Existing state ABI and exact committed/native/shared budget.
        "mov QWORD PTR [rsp+112], rax",
        "mov QWORD PTR [rsp+120], rdx",
        f"mov rdx, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [rsp+128], rdx",
        "mov QWORD PTR [rsp+136], r8",
        "mov QWORD PTR [rsp+144], r10",
        "mov QWORD PTR [rsp+160], 3",
        "mov QWORD PTR [rsp+168], r9",
        "mov QWORD PTR [rsp+176], r10",
        f"add QWORD PTR [r9+{abi_fields['JSRuntime.stack_top']}], r10",
        f"mov rdx, QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}]",
        "mov QWORD PTR [rsp+184], rdx",
        "test rdx, rdx",
        "jz root_zero_unlimited",
        "add rdx, r10",
        f"mov QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], rdx",
        "root_zero_unlimited:",
        "mov QWORD PTR [rsp+192], rdx",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov QWORD PTR [rsp+248], rdx",
        "lea rdx, [rsp+320]",
        "mov QWORD PTR [rsp+256], rdx",
        "lea rdx, [rsp+832]",
        "mov QWORD PTR [rsp+264], rdx",
        f"cmp BYTE PTR [r9+{abi_fields['JSRuntime.current_stack_frame'] - 4}], 1",
        "sete BYTE PTR [rsp+273]",
        f"mov QWORD PTR [r9+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        # A real CALL: original VM prologue is the sole callee-save set.
        "lea rcx, [rsp+112]",
        "call JS_FrameInterp",
        "mov r9, QWORD PTR [rsp+48]",
        "mov r8, QWORD PTR [rsp+144]",
        "sub r8, QWORD PTR [rsp+176]",
        f"add QWORD PTR [r9+{abi_fields['JSRuntime.stack_top']}], r8",
        f"cmp QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je root_zero_budget_done",
        f"add QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], r8",
        "root_zero_budget_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [rsp+152]",
        "movdqu XMMWORD PTR [rax], xmm0",
        # Existing activation cleanup; no fake returns or shared-cursor owners.
        "mov rdx, QWORD PTR [rsp+288]",
        "test rdx, rdx",
        "jz root_zero_done",
        "root_zero_free:",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [rsp+104], rax",
        "mov rcx, QWORD PTR [rsp+40]",
        "call js_free",
        "mov rdx, QWORD PTR [rsp+104]",
        "test rdx, rdx",
        "jnz root_zero_free",
        "root_zero_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "add rsp, 4952",
        "ret",
        "root_zero_overflow:",
        "lea rcx, [rsp+152]",
        "mov rdx, QWORD PTR [rsp+40]",
        "call JS_FrameNativeRootThrowOverflow",
        "jmp root_zero_exception",
        "root_zero_exception:",
        "mov rax, QWORD PTR [rsp+32]",
        "mov QWORD PTR [rax], 0",
        "mov QWORD PTR [rax+8], 6",
        "add rsp, 4952",
        "ret",
    ]
    # ThrowStackOverflow's original inline body is JS_ThrowRangeError(ctx,
    # "Maximum call stack size exceeded"). Use original error semantics.
    throw = [
        "sub rsp, 40",
        "root_zero_throw_alloc:",
        "lea r8, [rip+JS_FrameNativeRootOverflowMessage]",
        "call JS_ThrowRangeError",
        "add rsp, 40",
        "ret",
    ]
    gas += ['.section .qjszero$a,"xr"', ".p2align 4"]
    for name, code in (
        ("JS_FrameNativeRootZeroSelect", guard),
        ("JS_FrameNativeRootZeroConfig", config),
        (entry, run),
        ("JS_FrameNativeRootThrowOverflow", throw),
    ):
        gas += [
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
            *code,
            name + "_end:",
            ".p2align 4",
        ]
    gas += [
        "JS_FrameNativeRootZeroSelect_unwind:",
        ".byte 1,0,0,0",
        "JS_FrameNativeRootZeroConfig_unwind:",
        ".byte 1,root_zero_config_alloc - JS_FrameNativeRootZeroConfig,1,0",
        ".byte root_zero_config_alloc - JS_FrameNativeRootZeroConfig,0xa2",
        ".short 0",
        entry + "_unwind:",
        ".byte 1,root_zero_alloc - " + entry + ",2,0",
        ".byte root_zero_alloc - " + entry + ",1",
        ".short 619",
        "JS_FrameNativeRootThrowOverflow_unwind:",
        ".byte 1,root_zero_throw_alloc - JS_FrameNativeRootThrowOverflow,1,0",
        ".byte root_zero_throw_alloc - JS_FrameNativeRootThrowOverflow,0x42",
        ".short 0",
        "JS_FrameNativeRootZeroDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ROOT_ZERO"',
        "JS_FrameNativeRootHostDisable:",
        '.asciz "QJS_DISABLE_DIRECT_HOST_CALL"',
        "JS_FrameNativeRootOverflowMessage:",
        '.asciz "Maximum call stack size exceeded"',
        '.section .pdata$zzzzzzzzzero,"dr"',
        ".p2align 2",
    ]
    for name in (
        "JS_FrameNativeRootZeroSelect",
        "JS_FrameNativeRootZeroConfig",
        entry,
        "JS_FrameNativeRootThrowOverflow",
    ):
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    gas += [
        '.section .qjszmet$control,"dw"',
        ".globl JS_FrameNativeRootZeroControl",
        "JS_FrameNativeRootZeroControl:",
        ".byte 0",
    ]

    # Old generated ASM retains its original debug geometry. New symbols and
    # OS unwind remain in this independently compiled -g0 assembly object.
    output.write_text(".intel_syntax noprefix\n" + "\n".join(gas[base:]) + "\n", encoding="utf-8")
    del gas[base:]
