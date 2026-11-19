"""Win64 primitive numeric bridge with a native SF and coherent TLS boundary.

One instruction stream, distinct TLS-address and unwind encodings. No stack,
quota, interrupt or publication side effect occurs before the tail guard ends.
Unwind/config data live in the existing late RX numeric island, outside core
readonly data. A standard .pdata entry may refer to this readonly image data.
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
import re


def append(masm, gas, diagnostics):
    layout = current_abi()
    abi_fields = layout["offsets"]
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    section = ".qjsvm$zzznumA"
    fallback = "JS_FrameInterpHostNumeric"
    fast = "JS_FrameInterpNumericFast"
    tramp = "JS_FrameInterpNumericTrampoline"
    guard = [
        "mov rax, QWORD PTR [rcx+56]",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 64",
        "jz " + fallback,
        f"movzx r11d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r11d, 3",
        "cmp r11d, 1",
        "jne " + fallback,
        "mov r10, QWORD PTR [rdx-16]",
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "cmp r8d, r11d",
        "jl " + fallback,
        "cmp r8d, 1",
        "jl " + fallback,
        "cmp QWORD PTR [rdx+8], 8",
        "je num_fast_double0",
        "cmp QWORD PTR [rdx+8], 0",
        "jne " + fallback,
        "cvtsi2sd xmm0, DWORD PTR [rdx]",
        "jmp num_fast_arg0",
        "num_fast_double0:",
        "movsd xmm0, QWORD PTR [rdx]",
        "num_fast_arg0:",
        f"cmp BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.cproto']}], 6",
        "je num_fast_args_ready",
        "cmp r8d, 2",
        "jl " + fallback,
        "cmp QWORD PTR [rdx+24], 8",
        "je num_fast_double1",
        "cmp QWORD PTR [rdx+24], 0",
        "jne " + fallback,
        "cvtsi2sd xmm1, DWORD PTR [rdx+16]",
        "jmp num_fast_args_ready",
        "num_fast_double1:",
        "movsd xmm1, QWORD PTR [rdx+16]",
        "num_fast_args_ready:",
        "mov r11, QWORD PTR [rcx+32]",
        f"cmp r11, QWORD PTR [rcx+{committed}]",
        "jne " + fallback,
        # Conservative physical guard, retaining the old formal*16 contract.
        f"movzx r11d, BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.length']}]",
        "shl r11, 4",
        "add r11, 200",
        "mov r10, rsp",
        "sub r10, r11",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        "mov r11, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r11+80]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "jmp " + tramp,
    ]
    body = [
        "push rbx",
        "num_tramp_push_rbx:",
        "push rbp",
        "num_tramp_push_rbp:",
        "push rsi",
        "num_tramp_push_rsi:",
        "sub rsp, 160",
        "num_tramp_alloc:",
        "mov rbx, rcx",
        "mov rbp, rax",
        f"dec DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}]",
        f"mov rax, QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+32], rax",
        "movdqu xmm2, XMMWORD PTR [rdx-16]",
        "movdqu XMMWORD PTR [rsp+40], xmm2",
        "mov QWORD PTR [rsp+56], rdx",
        "mov WORD PTR [rsp+90], r8w",
        "mov WORD PTR [rsp+92], 0",
        "mov rax, QWORD PTR [rdx-16]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSObject.u.cfunc.c_function']}]",
        "mov QWORD PTR [rsp+144], rax",
        "NUMERIC_TLS",
        "mov rax, QWORD PTR [rsi]",
        "mov QWORD PTR [rsp+112], rax",
        "mov QWORD PTR [rsp+120], rbx",
        "mov DWORD PTR [rsp+128], 0",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 4",
        "mov BYTE PTR [rsp+136], al",
        "lea rax, [rsp+32]",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "lea rax, [rsp+112]",
        f"or BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rsi], rax",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2208]"]
    body += [
        # Both exact C prototypes take XMM0; the binary prototype also XMM1.
        "call QWORD PTR [rsp+144]",
        # Exactly the bitwise double_is_int32 decision, preserving -0/NaNs.
        "movq rax, xmm0",
        "mov rdx, rax",
        "shr rdx, 52",
        "and edx, 2047",
        "sub edx, 1023",
        "cmp edx, 30",
        "ja num_tramp_special",
        "mov ecx, edx",
        "mov rdx, rax",
        "shl rdx, 12",
        "shl rdx, cl",
        "test rdx, rdx",
        "jne num_tramp_float",
        "jmp num_tramp_int",
        "num_tramp_special:",
        "test rax, rax",
        "jz num_tramp_int",
        "mov rdx, 0c1e0000000000000h",
        "cmp rax, rdx",
        "je num_tramp_int",
        "num_tramp_float:",
        "mov edx, 8",
        "jmp num_tramp_boxed",
        "num_tramp_int:",
        "cvttsd2si eax, xmm0",
        "xor edx, edx",
        "num_tramp_boxed:",
        "mov QWORD PTR [rbx+40], rax",
        "mov QWORD PTR [rbx+48], rdx",
        f"mov BYTE PTR [rbx+{exception}], 0",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [rsi], rax",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsp+136]",
        f"mov BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsp+32]",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        # Same finish_c refresh after arbitrary GC, child execution or limits.
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne num_tramp_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je num_tramp_done",
        "num_tramp_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz num_tramp_limit",
        "sub rdx, rax",
        "num_tramp_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2336]"]
    body += [
        "num_tramp_done:",
        "xor eax, eax",
        "num_tramp_epilogue:",
        "add rsp, 160",
        "pop rsi",
        "pop rbp",
        "pop rbx",
        "ret",
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
    masm[3:3] = ["EXTERN js_frame_shared_top:BYTE", "EXTERN _tls_index:DWORD"]

    def rows(stream, tls, is_masm):
        output = []
        for line in stream:
            if line == "NUMERIC_TLS":
                output += tls
                continue
            if is_masm:
                if line.endswith(":"):
                    line = line[:-1] + "::"
                elif line.endswith(" " + fallback):
                    line = line.replace(" " + fallback, " NEAR PTR " + fallback)
            else:
                line = line.replace("0c1e0000000000000h", "0xc1e0000000000000")
            output.append(line)
        return output

    masm += [section + " SEGMENT ALIGN(16) 'CODE'"]
    gas += [".section " + section + ',"xr"']
    for name, stream in ((fast, guard), (tramp, body)):
        labels = [line[:-1] for line in stream if line.endswith(":")]
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end"]
        gas += [".p2align 4", ".globl " + name + ", " + name + "_end"]
        for label in labels:
            masm += ["PUBLIC " + label]
            gas += [".globl " + label]
        masm += (
            [name + " PROC"]
            + rows(stream, tls_m, True)
            + [name + "_end LABEL BYTE", name + " ENDP"]
        )
        gas += (
            [".def " + name + "; .scl 2; .type 32; .endef", name + ":"]
            + rows(stream, tls_g, False)
            + [name + "_end:"]
        )
    # Referenced data is readonly, late and within the existing numeric island.
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        tramp + "_unwind LABEL BYTE",
        "DB 1, num_tramp_alloc - " + tramp + ", 5, 0",
        "DB num_tramp_alloc - " + tramp + ", 1",
        "DW 20",
        "DB num_tramp_push_rsi - " + tramp + ", 060h",
        "DB num_tramp_push_rbp - " + tramp + ", 050h",
        "DB num_tramp_push_rbx - " + tramp + ", 030h",
        "DB 0, 0",
        "PUBLIC JS_FrameNumericFastDisable",
        "JS_FrameNumericFastDisable LABEL BYTE",
        'DB "QJS_DISABLE_NUMERIC_TRAMPOLINE", 0',
        section + " ENDS",
        ".pdata$zzqjsshared SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        tramp + "_unwind:",
        ".byte 1, num_tramp_alloc - " + tramp + ", 5, 0",
        ".byte num_tramp_alloc - " + tramp + ", 1",
        ".short 20",
        ".byte num_tramp_push_rsi - " + tramp + ", 0x60",
        ".byte num_tramp_push_rbp - " + tramp + ", 0x50",
        ".byte num_tramp_push_rbx - " + tramp + ", 0x30",
        ".short 0",
        ".globl JS_FrameNumericFastDisable",
        "JS_FrameNumericFastDisable:",
        '.asciz "QJS_DISABLE_NUMERIC_TRAMPOLINE"',
        '.section .pdata$zzqjsshared,"dr"',
        ".p2align 2",
    ]
    for name in (fast, tramp):
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    masm += [".pdata$zzqjsshared ENDS", "END"]
