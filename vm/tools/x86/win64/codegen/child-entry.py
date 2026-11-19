"""Win64 native-to-JS child entry over an already paused arena. MIT.

The only old-code edit redirects the active-entry leaf's JCC operand. Hot,
validated noncapturing callees borrow argv. Every guard failure tails the
retained C entry with the original hidden-result and argument ABI intact.
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
    abi_fields, abi_bits = layout["offsets"], layout["bits"]
    size = 2448 if diagnostics else 168
    extra = size - 168
    alloc = (248 + extra + 7) // 16 * 16 + 8
    assert alloc % 16 == 8 and alloc >= 248 + extra
    fixed = alloc
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    caller = 2272 if diagnostics else 136
    sites = 2280 if diagnostics else 144
    cache = 2288 if diagnostics else 152
    direct = 2297 if diagnostics else 161
    fallback = "JS_FrameCallEntryShared"
    fast = "JS_FrameChildFast"
    body_name = "JS_FrameChildTrampoline"
    config = "JS_FrameChildConfig"
    guard = [
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], 0",
        "je " + config,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], 1",
        "jne " + fallback,
        "mov r11d, DWORD PTR [rsp+64]",
        "test r11d, 4294967293",
        "jnz " + fallback,
        "mov r11d, DWORD PTR [rsp+48]",
        "test r11d, r11d",
        "js " + fallback,
        "cmp r11d, 65535",
        "ja " + fallback,
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 3",
        "cmp r10d, 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        # MS-compatible Win64 bitfield allocation puts dump_flags at1436.
        # Release leaves it zero; this also preserves dynamic debug stepping.
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        "mov QWORD PTR [rsp+8], rax",
        "CHILD_GUARD_TLS",
        "mov r10, QWORD PTR [r10]",
        "test r10, r10",
        "jz " + fallback,
        "cmp DWORD PTR [r10+16], 0",
        "jne " + fallback,
        "mov r10, QWORD PTR [r10+8]",
        "cmp QWORD PTR [r10+56], rax",
        "jne " + fallback,
        "mov r11, QWORD PTR [r10+32]",
        f"cmp r11, QWORD PTR [r10+{committed}]",
        "jne " + fallback,
        "mov QWORD PTR [rsp+16], r10",
        "cmp DWORD PTR [r8+8], -1",
        "jne " + fallback,
        "mov r11, QWORD PTR [r8]",
        f"cmp WORD PTR [r11+{abi_fields['JSObject.class_id']}], 13",
        "jne " + fallback,
        f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
        "jz " + fallback,
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 4",
        "jnz " + fallback,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + fallback,
        "test DWORD PTR [rsp+64], 2",
        "jz child_borrow_allowed",
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 2",
        "jz " + fallback,
        "child_borrow_allowed:",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp DWORD PTR [rsp+48], r10d",
        "jl " + fallback,
        "mov QWORD PTR [rsp+24], r11",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}]",
        f"movzx r11d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "add r11d, r10d",
        "shl r11d, 4",
        "add r11d, 128",
        "mov QWORD PTR [rsp+32], r11",
        "mov r10, QWORD PTR [rsp+16]",
        "mov r10, QWORD PTR [r10+8]",
        "mov rax, QWORD PTR [r10+8]",
        "sub rax, QWORD PTR [r10+16]",
        "jb " + fallback,
        "cmp rax, r11",
        "jb " + fallback,
        "mov r10, rsp",
        f"sub r10, {fixed + 4096}",
        "sub r10, r11",
        "mov rax, QWORD PTR [rsp+8]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "jmp JS_FrameChildLeafFast",
    ]
    # B=current RSP. Shadow B0; state B32; barrier B32+size;
    # hidden-result/TLS B224/B232 (+diagnostic delta), alignment tail8.
    # Only volatile GPRs/XMM0..2 are used. The VM preserves nonvolatiles once.
    body = [
        f"sub rsp, {alloc}",
        "child_alloc:",
        f"mov QWORD PTR [rsp+{224 + extra}], rcx",
        "movdqu xmm1, XMMWORD PTR [r8]",
        "movdqu xmm2, XMMWORD PTR [r9]",
        "lea r9, [rsp+32]",
    ]
    if diagnostics:
        body += [
            "pxor xmm0, xmm0",
            "mov rax, r9",
            f"mov ecx, {size // 16}",
            "child_zero_state:",
            "movdqu XMMWORD PTR [rax], xmm0",
            "add rax, 16",
            "dec ecx",
            "jnz child_zero_state",
        ]
        if size % 16:
            body += ["mov QWORD PTR [rax], 0"]
    else:
        # All live control fields are assigned. Release slots88..127 are reused by the native C-window cache.
        # The enabled MinGW native-view island repoints result.u zeroing to
        # cache-owner96. Result.tag starts undefined; every root exit writes
        # its complete result before the caller reads it.
        body += ["mov QWORD PTR [r9+40], 0", "mov QWORD PTR [r9+160], 0"]
    body += [
        f"mov QWORD PTR [r9+{caller}], rdx",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        f"mov rax, QWORD PTR [rsp+{fixed + 16}]",
        f"mov r8, QWORD PTR [rax+{sites}]",
        f"mov QWORD PTR [r9+{sites}], r8",
        f"mov r8, QWORD PTR [rax+{cache}]",
        f"mov QWORD PTR [r9+{cache}], r8",
        f"mov r8b, BYTE PTR [rax+{direct}]",
        f"mov BYTE PTR [r9+{direct}], r8b",
        "mov rdx, QWORD PTR [rax+8]",
        "mov r8, QWORD PTR [rdx+24]",
        # RDX is now a private JSFrameSegment, not the callee context.
        "add r8, QWORD PTR [rdx+16]",
        f"mov r10, QWORD PTR [rsp+{fixed + 32}]",
        "add QWORD PTR [rdx+16], r10",
        "mov QWORD PTR [r9+8], rdx",
        "mov QWORD PTR [r8+112], rdx",
        "mov QWORD PTR [r9], r8",
        "mov QWORD PTR [r9+32], r10",
        f"mov QWORD PTR [r9+{committed}], r10",
        f"mov rcx, QWORD PTR [rsp+{fixed + 8}]",
        "mov QWORD PTR [r9+56], rcx",
        "mov DWORD PTR [r8+120], r10d",
        "mov DWORD PTR [r8+124], 0",
        f"mov rax, QWORD PTR [rcx+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r8], rax",
        "movdqu XMMWORD PTR [r8+8], xmm1",
        "movdqu XMMWORD PTR [r8+88], xmm2",
        f"mov r11, QWORD PTR [rsp+{fixed + 24}]",
        "mov QWORD PTR [r8+80], r11",
        "mov QWORD PTR [r8+104], 0",
        f"mov rax, QWORD PTR [rsp+{fixed + 56}]",
        "mov QWORD PTR [r8+24], rax",
        "lea rax, [r8+128]",
        "mov QWORD PTR [r8+32], rax",
        "mov QWORD PTR [r8+40], 0",
        "mov QWORD PTR [r8+48], 0",
        "mov WORD PTR [r8+56], 0",
        f"mov dx, WORD PTR [rsp+{fixed + 48}]",
        "mov WORD PTR [r8+58], dx",
        f"mov dl, BYTE PTR [r11+{abi_bits['JSFunctionBytecode.is_strict_mode'][0][0]}]",
        "and dl, 1",
        "mov BYTE PTR [r8+60], dl",
        "mov BYTE PTR [r8+61], 0",
        "mov WORD PTR [r8+62], 1",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        f"movzx ecx, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}]",
        "test ecx, ecx",
        "jz child_vars_ready",
        "child_init_vars:",
        "mov QWORD PTR [rax], 0",
        "mov QWORD PTR [rax+8], 3",
        "add rax, 16",
        "dec ecx",
        "jnz child_init_vars",
        "child_vars_ready:",
        "mov QWORD PTR [r9+24], rax",
        f"mov rax, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [r9+16], rax",
        "mov QWORD PTR [r9+48], 3",
    ]
    if diagnostics:
        body += [
            "mov QWORD PTR [r9+88], 1",
            "mov DWORD PTR [r9+128], 1",
            "mov DWORD PTR [r9+132], 1",
            "mov QWORD PTR [r9+120], r10",
        ]
    body += [
        "mov rdx, QWORD PTR [r9+56]",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r10",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}]",
        "test rax, rax",
        "jz child_unlimited",
        "add rax, r10",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], rax",
        "child_unlimited:",
        f"mov QWORD PTR [r9+{shared_limit}], rax",
        "test rax, rax",
        "jz child_limit_ready",
        "sub rax, r10",
        "child_limit_ready:",
        f"mov QWORD PTR [r9+{native_limit}], rax",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.current_stack_frame']}], r8",
        "CHILD_BODY_TLS",
        f"mov QWORD PTR [rsp+{232 + extra}], r10",
        "mov rax, QWORD PTR [r10]",
        f"mov QWORD PTR [r9+{size}], rax",
        f"mov QWORD PTR [r9+{size + 8}], r9",
        f"mov DWORD PTR [r9+{size + 16}], 2",
        f"lea rax, [r9+{size}]",
        "mov QWORD PTR [r10], rax",
        "mov rcx, r9",
        "call JS_FrameInterp",
        "lea r9, [rsp+32]",
        "mov rdx, QWORD PTR [r9+56]",
        "mov r10, QWORD PTR [r9+32]",
        f"sub r10, QWORD PTR [r9+{committed}]",
        "jz child_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r10",
        f"cmp QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je child_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], r10",
        "child_charged:",
        f"mov rax, QWORD PTR [rsp+{232 + extra}]",
        f"mov r10, QWORD PTR [r9+{size}]",
        "mov QWORD PTR [rax], r10",
        f"mov rax, QWORD PTR [rsp+{224 + extra}]",
        "movdqu xmm0, XMMWORD PTR [r9+40]",
        "movdqu XMMWORD PTR [rax], xmm0",
        "child_epilogue:",
        f"add rsp, {alloc}",
        "ret",
    ]
    cold = [
        "sub rsp, 72",
        "child_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "CHILD_ENV",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], r11b",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 72",
        "jmp " + fallback,
    ]

    def tls(which, target, restore_rt=False):
        if which == "masm":
            return [
                "mov " + target + ", QWORD PTR gs:[88]",
                "mov r11d, DWORD PTR [_tls_index]",
                "mov " + target + ", QWORD PTR [" + target + "+r11*8]",
                "mov r11d, SECTIONREL js_frame_shared_top",
                "add " + target + ", r11",
            ]
        return [
            "mov " + target + ", QWORD PTR gs:[88]",
            "mov r11d, DWORD PTR [rip+_tls_index]",
            "mov " + target + ", QWORD PTR [" + target + "+r11*8]",
            "lea r11, [rip+JS_FrameSharedTop]",
            "lea rax, [rip+_tls_start]",
            "sub r11, rax",
            "add " + target + ", r11",
            # Guard keeps RAX=rt; body no longer needs its prior value.
            *(["mov rax, QWORD PTR [rsp+8]"] if restore_rt else []),
        ]

    assert masm[-1] == "END"
    masm.pop()
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjscold,"xr"', ".fill (-(. - JS_FrameInterpPropertyCold)) & 15, 1, 0x90"]
    for name, stream in ((fast, guard), (body_name, body), (config, cold)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in stream:
            if line.endswith(":"):
                masm += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                gas += [".globl " + line[:-1], line]
            elif line.startswith("CHILD_"):
                if line == "CHILD_ENV":
                    masm += ["lea rcx, JS_FrameChildDisable", "call QWORD PTR [__imp_getenv]"]
                    gas += ["lea rcx, [rip+JS_FrameChildDisable]", "call getenv"]
                else:
                    target = "r10"
                    masm += tls("masm", target)
                    gas += tls("gas", target, restore_rt=line == "CHILD_GUARD_TLS")
            else:
                masm += [
                    line.replace(" " + fallback, " NEAR PTR " + fallback)
                    .replace(" " + config, " NEAR PTR " + config)
                    .replace(" JS_FrameChildLeafCaptured", " NEAR PTR JS_FrameChildLeafCaptured")
                    .replace(" JS_FrameChildLeafFast", " NEAR PTR JS_FrameChildLeafFast")
                ]
                gas += [line]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        body_name + "_unwind LABEL BYTE",
        "DB 1, child_alloc - " + body_name + ", 2, 0",
        "DB child_alloc - " + body_name + ", 1",
        "DW " + str(alloc // 8),
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        body_name + "_unwind:",
        ".byte 1, child_alloc - " + body_name + ", 2, 0",
        ".byte child_alloc - " + body_name + ", 1",
        ".short " + str(alloc // 8),
    ]
    masm += [
        config + "_unwind LABEL BYTE",
        "DB 1, child_config_alloc - " + config + ", 1, 0",
        "DB child_config_alloc - " + config + ", 082h",
        "DB 0, 0",
        "PUBLIC JS_FrameChildDisable",
        "JS_FrameChildDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_CHILD", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        config + "_unwind:",
        ".byte 1, child_config_alloc - " + config + ", 1, 0",
        ".byte child_config_alloc - " + config + ", 0x82",
        ".short 0",
        ".globl JS_FrameChildDisable",
        "JS_FrameChildDisable:",
        '.asciz "QJS_DISABLE_NATIVE_CHILD"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (fast, body_name, config):
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]
