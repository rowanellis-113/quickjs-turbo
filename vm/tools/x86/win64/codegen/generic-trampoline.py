"""Win64 generic/magic native call with aligned JSValue ABI temporaries. MIT.

RCX/RDX/R8/R9 initially retain the existing host bridge ABI. Eligibility is
side-effect free. Every failure tail-transfers to the retained C shared bridge.
The successful body publishes the original SF/TLS/GC boundary and invokes the
live target using the compiler-proved hidden-result, by-value-this convention.
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


def append(masm, gas, diagnostics):
    layout = current_abi()
    abi_fields = layout["offsets"]
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    # Append to the existing final group. A new MSVC COFF group creates a
    # 24-byte POGO debug record, which can shift .data across a PE page edge.
    # The old cold-island bytes/labels/relocations precede this append unchanged.
    # This section also follows the original numeric C bridge, preserving its RVA.
    section = ".qjscold"
    fallback = "JS_FrameInterpHostDirectShared"
    config = "JS_FrameInterpGenericConfig"
    fast = "JS_FrameInterpGenericFast"
    trampoline = "JS_FrameInterpGenericTrampoline"
    guard = [
        "mov rax, QWORD PTR [rcx+56]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 1}], 0",
        "je " + config,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 1}], 1",
        "jne " + fallback,
        f"movzx r11d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r11d, 11",
        "cmp r11d, 1",
        "jne " + fallback,
        "mov r10, QWORD PTR [rdx-16]",
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "cmp r8d, r11d",
        "jl JS_FrameInterpGenericMissingFast",
        "mov r11, QWORD PTR [rcx+32]",
        f"cmp r11, QWORD PTR [rcx+{committed}]",
        "jne " + fallback,
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "shl r11, 4",
        "add r11, 248",
        "mov r10, rsp",
        "sub r10, r11",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        "mov r11, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r11+80]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "jmp " + trampoline,
    ]
    body = [
        "push rbx",
        "gen_tramp_push_rbx:",
        "push rbp",
        "gen_tramp_push_rbp:",
        "push rsi",
        "gen_tramp_push_rsi:",
        "sub rsp, 208",
        "gen_tramp_alloc:",
        "mov rbx, rcx",
        "mov rbp, rax",
        f"dec DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}]",
        # Native call shadow/stack arguments 0..47; original SF 48..127.
        f"mov rax, QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+48], rax",
        "movdqu xmm2, XMMWORD PTR [rdx-16]",
        "movdqu XMMWORD PTR [rsp+56], xmm2",
        "mov QWORD PTR [rsp+72], rdx",
        "mov WORD PTR [rsp+106], r8w",
        "mov WORD PTR [rsp+108], 0",
        "mov DWORD PTR [rsp+168], r8d",
        # By-value JSValue temporary is independently 16-byte aligned.
        "test r9b, r9b",
        "jz gen_tramp_undefined",
        "movdqu xmm2, XMMWORD PTR [rdx-32]",
        "movdqa XMMWORD PTR [rsp+176], xmm2",
        "jmp gen_tramp_this_ready",
        "gen_tramp_undefined:",
        "mov QWORD PTR [rsp+176], 0",
        "mov QWORD PTR [rsp+184], 3",
        "gen_tramp_this_ready:",
        "mov rax, QWORD PTR [rdx-16]",
        f"mov r10, QWORD PTR [rax+{abi_fields['JSObject.u.cfunc.c_function']}]",
        "mov QWORD PTR [rsp+160], r10",
        f"movsx r10d, WORD PTR [rax+{abi_fields['JSObject.u.cfunc.magic']}]",
        "mov DWORD PTR [rsp+40], r10d",
        "mov QWORD PTR [rsp+32], rdx",
        "GENERIC_TLS",
        "mov rax, QWORD PTR [rsi]",
        "mov QWORD PTR [rsp+128], rax",
        "mov QWORD PTR [rsp+136], rbx",
        "mov DWORD PTR [rsp+144], 0",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 4",
        "mov BYTE PTR [rsp+152], al",
        "lea rax, [rsp+48]",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "lea rax, [rsp+128]",
        f"or BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rsi], rax",
        # Hidden sret RCX, callee realm RDX, this-temp R8, argc R9,
        # argv [RSP+32], signed magic [RSP+40] (unused by generic).
        "mov rax, QWORD PTR [rsp+56]",
        f"mov rdx, QWORD PTR [rax+{abi_fields['JSObject.u.cfunc.realm']}]",
        "lea rcx, [rsp+192]",
        "lea r8, [rsp+176]",
        "mov r9d, DWORD PTR [rsp+168]",
    ]
    if diagnostics:
        body += [
            "inc QWORD PTR [rbx+2208]",
            f"cmp BYTE PTR [rax+{abi_fields['JSObject.u.cfunc.cproto']}], 0",
            "jne gen_tramp_magic_count",
            "inc QWORD PTR [rbx+2392]",
            "jmp gen_tramp_counted",
            "gen_tramp_magic_count:",
            "inc QWORD PTR [rbx+2400]",
            "gen_tramp_counted:",
        ]
    body += [
        "call QWORD PTR [rsp+160]",
        "movdqu xmm0, XMMWORD PTR [rsp+192]",
        "movdqu XMMWORD PTR [rbx+40], xmm0",
        "cmp QWORD PTR [rbx+48], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "mov rax, QWORD PTR [rsp+128]",
        "mov QWORD PTR [rsi], rax",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsp+152]",
        f"mov BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsp+48]",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne gen_tramp_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je gen_tramp_done",
        "gen_tramp_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz gen_tramp_limit",
        "sub rdx, rax",
        "gen_tramp_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2336]"]
    body += [
        "gen_tramp_done:",
        f"movzx eax, BYTE PTR [rbx+{exception}]",
        "gen_tramp_epilogue:",
        "add rsp, 208",
        "pop rsi",
        "pop rbp",
        "pop rbx",
        "ret",
    ]
    cold = [
        "sub rsp, 72",
        "gen_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "GENERIC_ENV",
        "mov r10, QWORD PTR [rsp+64]",
        "test rax, rax",
        "mov eax, 1",
        "jz gen_config_store",
        "mov eax, 2",
        "gen_config_store:",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.module_normalize_has_attr'] + 1}], al",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "gen_config_epilogue:",
        "add rsp, 72",
        "jmp " + fallback,
    ]
    tls_m = [
        "mov rax, QWORD PTR gs:[88]",
        "mov ecx, DWORD PTR [_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "mov ecx, SECTIONREL js_frame_shared_top",
        "lea rsi, [rax+rcx]",
    ]
    tls_g = [
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "lea rcx, [rip+JS_FrameSharedTop]",
        "lea r11, [rip+_tls_start]",
        "sub rcx, r11",
        "lea rsi, [rax+rcx]",
    ]
    assert masm[-1] == "END"
    masm.pop()
    masm[3:3] = ["EXTERN __imp_getenv:QWORD"]
    masm += [section + " SEGMENT ALIGN(16) 'CODE'"]
    gas += [
        ".section " + section + ',"xr"',
        # GAS's automatic end-of-section fill was single-byte NOPs.
        # Explicitly retain it instead of replacing it with a long NOP.
        ".fill (-(. - JS_FrameInterpPropertyCold)) & 15, 1, 0x90",
    ]
    for name, stream in ((fast, guard), (trampoline, body), (config, cold)):
        labels = [line[:-1] for line in stream if line.endswith(":")]
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end"]
        gas += [".p2align 4", ".globl " + name + ", " + name + "_end"]
        for label in labels:
            masm += ["PUBLIC " + label]
            gas += [".globl " + label]
        masm += [name + " PROC"]
        gas += [".def " + name + "; .scl 2; .type 32; .endef", name + ":"]
        for line in stream:
            if line == "GENERIC_TLS":
                masm += tls_m
                gas += tls_g
            elif line == "GENERIC_ENV":
                masm += ["lea rcx, JS_FrameGenericFastDisable", "call QWORD PTR [__imp_getenv]"]
                gas += ["lea rcx, [rip+JS_FrameGenericFastDisable]", "call getenv"]
            else:
                masm += [
                    line[:-1] + "::"
                    if line.endswith(":")
                    else line.replace(" " + fallback, " NEAR PTR " + fallback).replace(
                        " " + config, " NEAR PTR " + config
                    )
                ]
                gas += [line]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        trampoline + "_unwind LABEL BYTE",
        "DB 1, gen_tramp_alloc - " + trampoline + ", 5, 0",
        "DB gen_tramp_alloc - " + trampoline + ", 1",
        "DW 26",
        "DB gen_tramp_push_rsi - " + trampoline + ", 060h",
        "DB gen_tramp_push_rbp - " + trampoline + ", 050h",
        "DB gen_tramp_push_rbx - " + trampoline + ", 030h",
        "DB 0, 0",
        config + "_unwind LABEL BYTE",
        "DB 1, gen_config_alloc - " + config + ", 1, 0",
        "DB gen_config_alloc - " + config + ", 082h",
        "DB 0, 0",
        "PUBLIC JS_FrameGenericFastDisable",
        "JS_FrameGenericFastDisable LABEL BYTE",
        'DB "QJS_DISABLE_GENERIC_TRAMPOLINE", 0',
        section + " ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        trampoline + "_unwind:",
        ".byte 1, gen_tramp_alloc - " + trampoline + ", 5, 0",
        ".byte gen_tramp_alloc - " + trampoline + ", 1",
        ".short 26",
        ".byte gen_tramp_push_rsi - " + trampoline + ", 0x60",
        ".byte gen_tramp_push_rbp - " + trampoline + ", 0x50",
        ".byte gen_tramp_push_rbx - " + trampoline + ", 0x30",
        ".short 0",
        config + "_unwind:",
        ".byte 1, gen_config_alloc - " + config + ", 1, 0",
        ".byte gen_config_alloc - " + config + ", 0x82",
        ".short 0",
        ".globl JS_FrameGenericFastDisable",
        "JS_FrameGenericFastDisable:",
        '.asciz "QJS_DISABLE_GENERIC_TRAMPOLINE"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    # Reuse the cold-code pdata group so MS LINK preserves global RVA order.
    for name in (fast, trampoline, config):
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]
