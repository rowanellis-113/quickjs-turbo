"""Release-only equal-arity 1..3 root; exact COPY_ARGV JSValue ownership."""

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
from abi_layout import constants as layout_constants


def append(gas, diagnostics, out):
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    abi_rc = layout_constants(abi_layout)["QJS_ABI_REF_COUNT_OFFSET"]
    output = out / "quickjs-interpreter-native-root-args-win64.S"
    output.parent.mkdir(parents=True, exist_ok=True)
    if diagnostics:
        output.write_text(".intel_syntax noprefix\n.text\n", encoding="utf-8")
        return
    # These three pre-existing six-byte Jcc instructions all have the same
    # proven prefix: flags0/2, object/class13, live validated b in r11,
    # no captured arguments, no locals/local var_refs. No runtime mode or
    # realm is assumed. Nonmatching callees tail CallEntryLegacy, not this
    # classifier, so an off/ineligible root cannot loop.
    start = gas.index("JS_FrameRootLeafSelect:")
    end = gas.index("JS_FrameRootLeafSelect_end:")
    for compare, branch in (
        (f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 2", "ja"),
        (f"cmp QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}], rdx", "jne"),
        (f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4", "jne"),
    ):
        at = gas.index(compare, start, end)
        assert gas[at + 1] == branch + " JS_FrameCallEntryLegacy"
        gas[at + 1] = branch + " JS_FrameNativeRootArgsSelect"
    base = len(gas)
    fallback = "JS_FrameCallEntryLegacy"
    entry = "JS_FrameNativeRootArgs"
    guard = [
        "mov eax, DWORD PTR [rsp+48]",
        "dec eax",
        "cmp eax, 2",
        "ja " + fallback,
        # r11 and eligibility above are proved by every incoming old Jcc.
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe " + fallback,
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, DWORD PTR [rsp+48]",
        "jne " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 237",
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
        "cmp BYTE PTR [rip+JS_FrameNativeRootArgsControl], 0",
        "je JS_FrameNativeRootArgsConfig",
        "cmp BYTE PTR [rip+JS_FrameNativeRootArgsControl], 1",
        "jne " + fallback,
        "jmp " + entry,
    ]
    config = [
        "sub rsp, 88",
        "root_args_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "lea rcx, [rip+JS_FrameNativeRootArgsDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FrameNativeRootArgsControl], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp JS_FrameRootLeafSelect",
    ]
    # Fixed locations above Win64 shadow32. No nonvolatile GPR/XMM changes.
    # state112..279, segment288..319, sites320..831, next832, arena848..4943.
    run = [
        "mov eax, 4952",
        "call ___chkstk_ms",
        "sub rsp, rax",
        "root_args_alloc:",
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
        "jg root_args_polled",
        "mov rcx, rdx",
        "call qjs_frame_core___js_poll_interrupts",
        "test eax, eax",
        "jnz root_args_exception",
        "root_args_polled:",
        "mov rax, QWORD PTR [rsp+48]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], 0",
        "jne root_args_host_ready",
        "lea rcx, [rip+JS_FrameNativeRootArgsHostDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "mov rax, QWORD PTR [rsp+48]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], cl",
        "root_args_host_ready:",
        "mov r11, QWORD PTR [rsp+96]",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "test DWORD PTR [rsp+5016], 2",
        "jz root_args_bytes_ready",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "add r10d, eax",
        "root_args_bytes_ready:",
        "shl r10d, 4",
        "add r10d, 128",
        "mov QWORD PTR [rsp+56], r10",
        # Exact logical check after physical entry, before quota/publication.
        "mov rax, rsp",
        "sub rax, r10",
        "mov r9, QWORD PTR [rsp+48]",
        f"cmp rax, QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}]",
        "jb root_args_overflow",
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
        # Borrow flags0 argv; COPY_ARGV owns exactly formal_count JSValues.
        "mov rdx, QWORD PTR [rsp+5008]",
        "mov QWORD PTR [rsp+872], rdx",
        "lea r8, [rsp+976]",
        f"movzx ecx, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "mov WORD PTR [rsp+906], cx",
        "mov DWORD PTR [rsp+972], 0",
        "test DWORD PTR [rsp+5016], 2",
        "jz root_args_values_ready",
        "mov WORD PTR [rsp+972], cx",
        "mov QWORD PTR [rsp+872], r8",
        "root_args_copy:",
        "movdqu xmm1, XMMWORD PTR [rdx]",
        "movdqu XMMWORD PTR [r8], xmm1",
        # Exact unsigned tag>=unsigned(-9); JS_REF_COUNT is allocation payload-4. No allocation.
        "cmp DWORD PTR [rdx+8], -9",
        "jb root_args_copy_immediate",
        "mov rax, QWORD PTR [rdx]",
        f"add DWORD PTR [rax{abi_rc:+d}], 1",
        "root_args_copy_immediate:",
        "add rdx, 16",
        "add r8, 16",
        "dec ecx",
        "jnz root_args_copy",
        "root_args_values_ready:",
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
        "jz root_args_unlimited",
        "add rdx, r10",
        f"mov QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], rdx",
        "root_args_unlimited:",
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
        "je root_args_budget_done",
        f"add QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], r8",
        "root_args_budget_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [rsp+152]",
        "movdqu XMMWORD PTR [rax], xmm0",
        # Existing activation cleanup; no fake returns or shared-cursor owners.
        "mov rdx, QWORD PTR [rsp+288]",
        "test rdx, rdx",
        "jz root_args_done",
        "root_args_free:",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [rsp+104], rax",
        "mov rcx, QWORD PTR [rsp+40]",
        "call js_free",
        "mov rdx, QWORD PTR [rsp+104]",
        "test rdx, rdx",
        "jnz root_args_free",
        "root_args_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "add rsp, 4952",
        "ret",
        "root_args_overflow:",
        "lea rcx, [rsp+152]",
        "mov rdx, QWORD PTR [rsp+40]",
        "call JS_FrameNativeRootArgsThrowOverflow",
        "jmp root_args_exception",
        "root_args_exception:",
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
        "root_args_throw_alloc:",
        "lea r8, [rip+JS_FrameNativeRootArgsOverflowMessage]",
        "call JS_ThrowRangeError",
        "add rsp, 40",
        "ret",
    ]
    gas += ['.section .qjsargs$a,"xr"', ".p2align 4"]
    for name, code in (
        ("JS_FrameNativeRootArgsSelect", guard),
        ("JS_FrameNativeRootArgsConfig", config),
        (entry, run),
        ("JS_FrameNativeRootArgsThrowOverflow", throw),
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
        "JS_FrameNativeRootArgsSelect_unwind:",
        ".byte 1,0,0,0",
        "JS_FrameNativeRootArgsConfig_unwind:",
        ".byte 1,root_args_config_alloc - JS_FrameNativeRootArgsConfig,1,0",
        ".byte root_args_config_alloc - JS_FrameNativeRootArgsConfig,0xa2",
        ".short 0",
        entry + "_unwind:",
        ".byte 1,root_args_alloc - " + entry + ",2,0",
        ".byte root_args_alloc - " + entry + ",1",
        ".short 619",
        "JS_FrameNativeRootArgsThrowOverflow_unwind:",
        ".byte 1,root_args_throw_alloc - JS_FrameNativeRootArgsThrowOverflow,1,0",
        ".byte root_args_throw_alloc - JS_FrameNativeRootArgsThrowOverflow,0x42",
        ".short 0",
        "JS_FrameNativeRootArgsDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ROOT_ARGS"',
        "JS_FrameNativeRootArgsHostDisable:",
        '.asciz "QJS_DISABLE_DIRECT_HOST_CALL"',
        "JS_FrameNativeRootArgsOverflowMessage:",
        '.asciz "Maximum call stack size exceeded"',
        '.section .pdata$zzzzzzzzzargs,"dr"',
        ".p2align 2",
    ]
    for name in (
        "JS_FrameNativeRootArgsSelect",
        "JS_FrameNativeRootArgsConfig",
        entry,
        "JS_FrameNativeRootArgsThrowOverflow",
    ):
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    gas += [
        '.section .qjsamet$control,"dw"',
        ".globl JS_FrameNativeRootArgsControl",
        "JS_FrameNativeRootArgsControl:",
        ".byte 0",
    ]

    # Old generated ASM retains its original debug geometry. New symbols and
    # OS unwind remain in this independently compiled -g0 assembly object.
    output.write_text(".intel_syntax noprefix\n" + "\n".join(gas[base:]) + "\n", encoding="utf-8")
    del gas[base:]
