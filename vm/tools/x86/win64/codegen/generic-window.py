"""Win64 generic/magic arity window with a stable FP and ordered page probes. MIT.

Entry inherits generic/shared/signature checks, RAX=rt, RDX=original argv.
Only the arity JCC of the retained generic guard changes. This separate island
borrows actual values, pads undefined slots and publishes the same SF/TLS scope.
The parent keeps owning its values. No shared-arena address or extent changes.
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
    fallback = "JS_FrameInterpHostDirectShared"
    fast = "JS_FrameInterpGenericMissingFast"
    trampoline = "JS_FrameInterpGenericMissingTrampoline"
    config = "JS_FrameInterpGenericMissingConfig"
    guard = [
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], 0",
        "je " + config,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], 1",
        "jne " + fallback,
        "test r8d, r8d",
        "js " + fallback,
        "mov r11, QWORD PTR [rcx+32]",
        f"cmp r11, QWORD PTR [rcx+{committed}]",
        "jne " + fallback,
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "shl r11, 4",
        "add r11, 264",
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
    # S=entry RSP. Four saves +168 fixed bytes =200; B=S-200, FP=B+80.
    # B: SF[0,80), TLS[80,104), active104, target112, actual argc120,
    # aligned this128/result144. Dynamic RSP=B-(formal*16+48): outgoing
    # shadow+argv+magic[0,48), borrowed/padded window[48,48+formal*16).
    body = [
        "push rbx",
        "miss_push_rbx:",
        "push rbp",
        "miss_push_rbp:",
        "push rsi",
        "miss_push_rsi:",
        "push rdi",
        "miss_push_rdi:",
        "sub rsp, 168",
        "miss_alloc:",
        "lea rbp, [rsp+80]",
        "miss_set_fp:",
        "mov rbx, rcx",
        "mov rdi, rax",
        f"dec DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}]",
        f"mov rax, QWORD PTR [rdi+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rbp-80], rax",
        "movdqu xmm2, XMMWORD PTR [rdx-16]",
        "movdqu XMMWORD PTR [rbp-72], xmm2",
        "mov r10, QWORD PTR [rdx-16]",
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "mov WORD PTR [rbp-22], r11w",
        "mov WORD PTR [rbp-20], 0",
        "mov DWORD PTR [rbp+40], r8d",
        "test r9b, r9b",
        "jz miss_undefined",
        "movdqu xmm2, XMMWORD PTR [rdx-32]",
        "movdqa XMMWORD PTR [rbp+48], xmm2",
        "jmp miss_this_ready",
        "miss_undefined:",
        "mov QWORD PTR [rbp+48], 0",
        "mov QWORD PTR [rbp+56], 3",
        "miss_this_ready:",
        f"mov rax, QWORD PTR [r10+{abi_fields['JSObject.u.cfunc.c_function']}]",
        "mov QWORD PTR [rbp+32], rax",
        "shl r11d, 4",
        "add r11d, 48",
        # SF store above has already touched B. Visit every intervening page
        # before the endpoint. Max allocation 4128 needs at most one step.
        "cmp r11d, 4096",
        "jbe miss_last_page",
        "test BYTE PTR [rsp-4096], 0",
        "miss_last_page:",
        "sub rsp, r11",
        "test BYTE PTR [rsp], 0",
        "miss_dynamic_ready:",
        "lea rax, [rsp+48]",
        "mov QWORD PTR [rbp-56], rax",
        "mov QWORD PTR [rsp+32], rax",
        f"movsx r11d, WORD PTR [r10+{abi_fields['JSObject.u.cfunc.magic']}]",
        "mov DWORD PTR [rsp+40], r11d",
        "xor r10d, r10d",
        "mov ecx, r8d",
        "test ecx, ecx",
        "jz miss_fill_start",
        "miss_copy:",
        "movdqu xmm1, XMMWORD PTR [rdx+r10]",
        "movdqu XMMWORD PTR [rax+r10], xmm1",
        "add r10, 16",
        "dec ecx",
        "jnz miss_copy",
        "miss_fill_start:",
        "movzx ecx, WORD PTR [rbp-22]",
        "sub ecx, r8d",
        "miss_fill:",
        "mov QWORD PTR [rax+r10], 0",
        "mov QWORD PTR [rax+r10+8], 3",
        "add r10, 16",
        "dec ecx",
        "jnz miss_fill",
        "MISSING_TLS",
        "mov rax, QWORD PTR [rsi]",
        "mov QWORD PTR [rbp], rax",
        "mov QWORD PTR [rbp+8], rbx",
        "mov DWORD PTR [rbp+16], 0",
        f"mov al, BYTE PTR [rdi+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 4",
        "mov BYTE PTR [rbp+24], al",
        "lea rax, [rbp-80]",
        f"mov QWORD PTR [rdi+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        f"or BYTE PTR [rdi+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rsi], rbp",
        "mov rax, QWORD PTR [rbp-72]",
        f"mov rdx, QWORD PTR [rax+{abi_fields['JSObject.u.cfunc.realm']}]",
        "lea rcx, [rbp+64]",
        "lea r8, [rbp+48]",
        "mov r9d, DWORD PTR [rbp+40]",
    ]
    if diagnostics:
        body += [
            "inc QWORD PTR [rbx+2208]",
            f"cmp BYTE PTR [rax+{abi_fields['JSObject.u.cfunc.cproto']}], 0",
            "jne miss_magic_count",
            "inc QWORD PTR [rbx+2392]",
            "jmp miss_counted",
            "miss_magic_count:",
            "inc QWORD PTR [rbx+2400]",
            "miss_counted:",
        ]
    body += [
        "call QWORD PTR [rbp+32]",
        "movdqu xmm0, XMMWORD PTR [rbp+64]",
        "movdqu XMMWORD PTR [rbx+40], xmm0",
        "cmp QWORD PTR [rbx+48], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "mov rax, QWORD PTR [rbp]",
        "mov QWORD PTR [rsi], rax",
        f"mov al, BYTE PTR [rdi+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rbp+24]",
        f"mov BYTE PTR [rdi+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rbp-80]",
        f"mov QWORD PTR [rdi+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [rdi+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne miss_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je miss_done",
        "miss_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz miss_limit",
        "sub rdx, rax",
        "miss_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2336]"]
    body += [
        "miss_done:",
        f"movzx eax, BYTE PTR [rbx+{exception}]",
        "miss_epilogue:",
        "lea rsp, [rbp+88]",
        "pop rdi",
        "pop rsi",
        "pop rbp",
        "pop rbx",
        "ret",
    ]
    cold = [
        "sub rsp, 72",
        "miss_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "MISSING_ENV",
        "mov r10, QWORD PTR [rsp+64]",
        "test rax, rax",
        "mov eax, 1",
        "jz miss_config_store",
        "mov eax, 2",
        "miss_config_store:",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], al",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "miss_config_epilogue:",
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
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjscold,"xr"', ".fill (-(. - JS_FrameInterpPropertyCold)) & 15, 1, 0x90"]
    for name, stream in ((fast, guard), (trampoline, body), (config, cold)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end"]
        gas += [".p2align 4", ".globl " + name + ", " + name + "_end"]
        for label in (line[:-1] for line in stream if line.endswith(":")):
            masm += ["PUBLIC " + label]
            gas += [".globl " + label]
        masm += [name + " PROC"]
        gas += [".def " + name + "; .scl 2; .type 32; .endef", name + ":"]
        for line in stream:
            if line == "MISSING_TLS":
                masm += tls_m
                gas += tls_g
            elif line == "MISSING_ENV":
                masm += ["lea rcx, JS_FrameGenericWindowDisable", "call QWORD PTR [__imp_getenv]"]
                gas += ["lea rcx, [rip+JS_FrameGenericWindowDisable]", "call getenv"]
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
    # 7 unwind slots: SET_FP + ALLOC_LARGE(two) + four PUSH_NONVOL.
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        trampoline + "_unwind LABEL BYTE",
        "DB 1, miss_set_fp - " + trampoline + ", 7, 055h",
        "DB miss_set_fp - " + trampoline + ", 3",
        "DB miss_alloc - " + trampoline + ", 1",
        "DW 21",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        trampoline + "_unwind:",
        ".byte 1, miss_set_fp - " + trampoline + ", 7, 0x55",
        ".byte miss_set_fp - " + trampoline + ", 3",
        ".byte miss_alloc - " + trampoline + ", 1",
        ".short 21",
    ]
    for reg, opcode in (("rdi", 0x70), ("rsi", 0x60), ("rbp", 0x50), ("rbx", 0x30)):
        masm += ["DB miss_push_" + reg + " - " + trampoline + ", " + str(opcode)]
        gas += [".byte miss_push_" + reg + " - " + trampoline + ", " + str(opcode)]
    masm += [
        "DB 0, 0",
        config + "_unwind LABEL BYTE",
        "DB 1, miss_config_alloc - " + config + ", 1, 0",
        "DB miss_config_alloc - " + config + ", 082h",
        "DB 0, 0",
        "PUBLIC JS_FrameGenericWindowDisable",
        "JS_FrameGenericWindowDisable LABEL BYTE",
        'DB "QJS_DISABLE_GENERIC_WINDOW", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".short 0",
        config + "_unwind:",
        ".byte 1, miss_config_alloc - " + config + ", 1, 0",
        ".byte miss_config_alloc - " + config + ", 0x82",
        ".short 0",
        ".globl JS_FrameGenericWindowDisable",
        "JS_FrameGenericWindowDisable:",
        '.asciz "QJS_DISABLE_GENERIC_WINDOW"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (fast, trampoline, config):
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]
