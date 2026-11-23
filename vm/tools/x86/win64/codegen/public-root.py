"""Release-only public ABI root; called only after original ResolveCall.

The original selector proves object/class13/live supported bytecode. Public
argc/argv are at entry RSP+40/+48. COPY_ARGV is always required. The old C
bridge consumed 120 native bytes plus one 8-byte CALL return slot: subtract
128 in the conservative physical/logical checks to retain its admission.
No nonvolatile registers or ownership/capacity changes.
"""

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
    output = out / "quickjs-interpreter-public-root-win64.S"
    output.parent.mkdir(parents=True, exist_ok=True)
    if diagnostics:
        output.write_text(".intel_syntax noprefix\n.text\n", encoding="utf-8")
        return
    base = len(gas)
    fallback = "JS_FrameRunCall"
    entry = "JS_FramePublicRoot"
    guard = [
        # Primitive short leaves retain their established entries; larger zero roots fuse.
        "cmp DWORD PTR [rsp+40], 3",
        "ja " + fallback,
        # Proven by the original ResolveCall before its read-only tail pointer.
        "mov r11, QWORD PTR [r8]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 0",
        "jne " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + fallback,
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 4",
        "jnz " + fallback,
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, DWORD PTR [rsp+40]",
        "jne " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 237",
        "ja " + fallback,
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"cmp QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}], 0",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "jnz " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        # Cold/disabled inherited controls must use their original configuration.
        "cmp BYTE PTR [rip+JS_FrameNativeRootControl], 1",
        "jne " + fallback,
        "cmp DWORD PTR [rsp+40], 0",
        "jne root_public_nonzero_control",
        "cmp BYTE PTR [rip+JS_FrameNativeRootZeroControl], 1",
        "jne " + fallback,
        "jmp root_public_arity_control_ready",
        "root_public_nonzero_control:",
        "cmp BYTE PTR [rip+JS_FrameNativeRootArgsControl], 1",
        "jne " + fallback,
        "root_public_arity_control_ready:",
        "lea r10, [rsp-8320]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        "cmp BYTE PTR [rip+JS_FramePublicRootControl], 0",
        "je JS_FramePublicRootConfig",
        "cmp BYTE PTR [rip+JS_FramePublicRootControl], 1",
        "jne " + fallback,
        "jmp " + entry,
    ]
    config = [
        "sub rsp, 88",
        "root_public_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "lea rcx, [rip+JS_FramePublicRootDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FramePublicRootControl], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp JS_FramePublicRootSelect",
    ]
    # Fixed locations above Win64 shadow32. No nonvolatile GPR/XMM changes.
    # state112..279, segment288..319, sites320..831, next832, arena848..4943.
    run = [
        "mov eax, 4952",
        "call ___chkstk_ms",
        "sub rsp, rax",
        "root_public_alloc:",
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
        "jg root_public_polled",
        "mov rcx, rdx",
        "call qjs_frame_core___js_poll_interrupts",
        "test eax, eax",
        "jnz root_public_exception",
        "root_public_polled:",
        "mov rax, QWORD PTR [rsp+48]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], 0",
        "jne root_public_host_ready",
        "lea rcx, [rip+JS_FramePublicRootHostDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "mov rax, QWORD PTR [rsp+48]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 4}], cl",
        "root_public_host_ready:",
        "mov r11, QWORD PTR [rsp+96]",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "add r10d, eax",
        "root_public_bytes_ready:",
        "shl r10d, 4",
        "add r10d, 128",
        "mov QWORD PTR [rsp+56], r10",
        # Exact logical check after physical entry, before quota/publication.
        "mov rax, rsp",
        "sub rax, 128",
        "sub rax, r10",
        "mov r9, QWORD PTR [rsp+48]",
        f"cmp rax, QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}]",
        "jb root_public_overflow",
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
        # Public COPY_ARGV always owns exactly formal_count JSValues.
        "mov rdx, QWORD PTR [rsp+5000]",
        "mov QWORD PTR [rsp+872], rdx",
        "lea r8, [rsp+976]",
        f"movzx ecx, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "mov WORD PTR [rsp+906], cx",
        "mov DWORD PTR [rsp+972], 0",
        # For formal0, keep the original incoming argv (including non-NULL).
        "test ecx, ecx",
        "jz root_public_values_ready",
        "mov WORD PTR [rsp+972], cx",
        "mov QWORD PTR [rsp+872], r8",
        "root_public_copy:",
        "movdqu xmm1, XMMWORD PTR [rdx]",
        "movdqu XMMWORD PTR [r8], xmm1",
        # Exact unsigned tag>=unsigned(-9); JS_REF_COUNT is allocation payload-4. No allocation.
        "cmp DWORD PTR [rdx+8], -9",
        "jb root_public_copy_immediate",
        "mov rax, QWORD PTR [rdx]",
        f"add DWORD PTR [rax{abi_rc:+d}], 1",
        "root_public_copy_immediate:",
        "add rdx, 16",
        "add r8, 16",
        "dec ecx",
        "jnz root_public_copy",
        "root_public_values_ready:",
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
        "jz root_public_unlimited",
        "add rdx, r10",
        f"mov QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], rdx",
        "root_public_unlimited:",
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
        "je root_public_budget_done",
        f"add QWORD PTR [r9+{abi_fields['JSRuntime.stack_limit']}], r8",
        "root_public_budget_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [rsp+152]",
        "movdqu XMMWORD PTR [rax], xmm0",
        # Existing activation cleanup; no fake returns or shared-cursor owners.
        "mov rdx, QWORD PTR [rsp+288]",
        "test rdx, rdx",
        "jz root_public_done",
        "root_public_free:",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [rsp+104], rax",
        "mov rcx, QWORD PTR [rsp+40]",
        "call js_free",
        "mov rdx, QWORD PTR [rsp+104]",
        "test rdx, rdx",
        "jnz root_public_free",
        "root_public_done:",
        "mov rax, QWORD PTR [rsp+32]",
        "add rsp, 4952",
        "ret",
        "root_public_overflow:",
        "lea rcx, [rsp+152]",
        "mov rdx, QWORD PTR [rsp+40]",
        "call JS_FramePublicRootThrowOverflow",
        "jmp root_public_exception",
        "root_public_exception:",
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
        "root_public_throw_alloc:",
        "lea r8, [rip+JS_FramePublicRootOverflowMessage]",
        "call JS_ThrowRangeError",
        "add rsp, 40",
        "ret",
    ]
    gas += ['.section .qjspub$a,"xr"', ".p2align 4"]
    for name, code in (
        ("JS_FramePublicRootSelect", guard),
        ("JS_FramePublicRootConfig", config),
        (entry, run),
        ("JS_FramePublicRootThrowOverflow", throw),
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
        "JS_FramePublicRootSelect_unwind:",
        ".byte 1,0,0,0",
        "JS_FramePublicRootConfig_unwind:",
        ".byte 1,root_public_config_alloc - JS_FramePublicRootConfig,1,0",
        ".byte root_public_config_alloc - JS_FramePublicRootConfig,0xa2",
        ".short 0",
        entry + "_unwind:",
        ".byte 1,root_public_alloc - " + entry + ",2,0",
        ".byte root_public_alloc - " + entry + ",1",
        ".short 619",
        "JS_FramePublicRootThrowOverflow_unwind:",
        ".byte 1,root_public_throw_alloc - JS_FramePublicRootThrowOverflow,1,0",
        ".byte root_public_throw_alloc - JS_FramePublicRootThrowOverflow,0x42",
        ".short 0",
        "JS_FramePublicRootDisable:",
        '.asciz "QJS_DISABLE_PUBLIC_ROOT"',
        "JS_FramePublicRootHostDisable:",
        '.asciz "QJS_DISABLE_DIRECT_HOST_CALL"',
        "JS_FramePublicRootOverflowMessage:",
        '.asciz "Maximum call stack size exceeded"',
        '.section .pdata$zzzzzzzzzzpublic,"dr"',
        ".p2align 2",
    ]
    for name in (
        "JS_FramePublicRootSelect",
        "JS_FramePublicRootConfig",
        entry,
        "JS_FramePublicRootThrowOverflow",
    ):
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    gas += [
        '.section .qjspumt$control,"dw"',
        ".globl JS_FramePublicRootControl",
        "JS_FramePublicRootControl:",
        ".byte 0",
    ]

    # Old generated ASM retains its original debug geometry. New symbols and
    # OS unwind remain in this independently compiled -g0 assembly object.
    output.write_text(".intel_syntax noprefix\n" + "\n".join(gas[base:]) + "\n", encoding="utf-8")
    del gas[base:]
