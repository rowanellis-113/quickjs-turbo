"""Zero-actual/formal generic calls without taxing every generic arity guard."""

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


def append(masm, gas):
    layout = current_abi()
    abi_fields = layout["offsets"]
    fast = "JS_FrameInterpZeroHost"
    config = "JS_FrameInterpZeroConfig"
    old = "JS_FrameInterpGenericFast"
    retained = "JS_FrameInterpHostDirectShared"
    gate = [
        "mov r10, QWORD PTR [rdx-16]",
        f"cmp WORD PTR [r10+{abi_fields['JSObject.u.cfunc.length']}], 0",
        "jne " + old,
        "mov rax, QWORD PTR [rcx+56]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 7}], 0",
        "je " + config,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 7}], 1",
        "jne " + old,
        "jmp " + retained,
    ]
    body = [
        "sub rsp, 72",
        "zero_host_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "lea rcx, JS_FrameZeroDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 7}], r11b",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 72",
        "jmp " + fast,
    ]
    assert masm.pop() == "END"
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsleaf,"xr"']
    for name, lines in ((fast, gate), (config, body)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in lines:
            masm += [
                line[:-1] + "::"
                if line.endswith(":")
                else line.replace(" " + old, " NEAR PTR " + old).replace(
                    " " + retained, " NEAR PTR " + retained
                )
            ]
            gas += [
                line.replace(
                    "lea rcx, JS_FrameZeroDisable", "lea rcx, [rip+JS_FrameZeroDisable]"
                ).replace("[__imp_getenv]", "[rip+__imp_getenv]")
            ]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        config + "_unwind LABEL BYTE",
        "DB 1, zero_host_alloc - " + config + ", 1, 0",
        "DB zero_host_alloc - " + config + ", 082h",
        "DB 0, 0",
        "JS_FrameZeroDisable LABEL BYTE",
        'DB "QJS_DISABLE_ZERO_HOST_GUARD", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        config + "_unwind:",
        ".byte 1, zero_host_alloc - " + config + ", 1, 0",
        ".byte zero_host_alloc - " + config + ", 0x82",
        ".short 0",
        "JS_FrameZeroDisable:",
        '.asciz "QJS_DISABLE_ZERO_HOST_GUARD"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (fast, config):
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]
