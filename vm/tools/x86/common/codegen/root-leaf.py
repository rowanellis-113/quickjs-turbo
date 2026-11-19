"""No-anchor call leaves, sharing the normal native leaf mode.

Two independent tails preserve either the original C interpreter or the
existing root-frame entry. Exact primitive or own-data getter bytecode, same
realm, noncaptured arguments and conservative physical/quota guards only.
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


def append(masm, gas, ids):
    layout = current_abi()
    abi_fields, abi_bits = layout["offsets"], layout["bits"]
    assert ids["push_7"] - ids["push_minus1"] == 8
    cfg = "JS_FrameRootLeafConfig"
    names = ("JS_FrameRootLeafSelect", "JS_FrameLegacyChildLeaf")
    origins = ("JS_FrameCallEntryLegacy", "qjs_frame_core_JS_CallInternal")
    assert masm.pop() == "END"
    masm += [
        "EXTERN qjs_internal_interp_register_current_disabled:PROC",
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
    ]
    gas += ['.section .qjsleaf,"xr"']
    for name, origin in zip(names, origins):
        label = "root_leaf_" + ("root" if name == names[0] else "legacy")
        # Preserve RCX/RDX/R8/R9 and every stack argument until an accepted
        # leaf commits. Incoming home words are ABI scratch storage.
        code = [
            "test DWORD PTR [rsp+64], -3",
            "jnz " + origin,
            "cmp DWORD PTR [r8+8], -1",
            "jne " + origin,
            "mov r11, QWORD PTR [r8]",
            f"cmp WORD PTR [r11+{abi_fields['JSObject.class_id']}], 13",
            "jne " + origin,
            f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
            f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
            "jz " + origin,
            f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 4",
            "jnz " + origin,
            f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 0",
            "jne " + origin,
            f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
            "jne " + origin,
            f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 2",
            "ja " + origin,
            f"cmp QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}], rdx",
            "jne " + origin,
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 2",
            "je " + label + "_shape",
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
            "jne " + origin,
            label + "_shape:",
            f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
            f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
            "jne " + origin,
            f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 2",
            "je " + origin,
            f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
            "jnz " + origin,
            "cmp DWORD PTR [rsp+48], 65535",
            "ja " + origin,
            f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
            "cmp DWORD PTR [rsp+48], r10d",
            "jl " + origin,
            # Include the actual argument span conservatively, even though
            # these leaves neither copy nor retain any argument references.
            "mov r10d, DWORD PTR [rsp+48]",
            "shl r10, 4",
            "add r10, 5280",
            "neg r10",
            "add r10, rsp",
            f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
            "jb " + origin,
            f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
            "jle " + origin,
            "mov QWORD PTR [rsp+8], rax",
            "mov QWORD PTR [rsp+24], r11",
            f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 0",
            "je " + label + "_config",
            f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], 0",
            "je " + label + "_config",
            f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], 1",
            "jne " + origin,
            f"mov r10, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 2",
            "je " + label + "_constant",
            "mov eax, DWORD PTR [r10]",
            "and eax, 4294902015",
            "cmp eax, " + str(ids["get_arg0"] | ids["add"] << 16 | ids["return"] << 24),
            "jne " + origin,
            "cmp DWORD PTR [rsp+48], 1",
            "jl " + origin,
            "movzx r11d, BYTE PTR [r10+1]",
            f"sub r11d, {ids['push_minus1']}",
            "cmp r11d, 8",
            "ja " + origin,
            "dec r11d",
            "mov r10, QWORD PTR [rsp+56]",
            "cmp DWORD PTR [r10+8], 0",
            "jne " + origin,
            "mov eax, DWORD PTR [r10]",
            "add eax, r11d",
            "jo " + origin,
            "jmp " + label + "_result",
            label + "_constant:",
            f"cmp BYTE PTR [r10+1], {ids['return']}",
            "jne " + origin,
            "movzx eax, BYTE PTR [r10]",
            f"sub eax, {ids['push_minus1']}",
            "cmp eax, 8",
            "ja " + origin,
            "dec eax",
            label + "_result:",
            f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
            "mov QWORD PTR [rcx], rax",
            "mov QWORD PTR [rcx+8], 0",
            "mov rax, rcx",
            "ret",
            label + "_config:",
            "lea r10, " + name,
            "jmp " + cfg,
        ]
        # Keep the established zero-local prefix for the independent MinGW
        # 1..3-argument root adapter. A getter branches away BEFORE that
        # prefix; it must never acquire the adapter's no-local assumption.
        gate = code.index(f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 0")
        code[gate + 1] = "jne " + label + "_this_field"
        runtime = code[
            code.index(label + "_shape:") + 1 : code.index(
                f"mov r10, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]"
            )
        ]
        getter = [
            label + "_this_field:",
            f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 1",
            "jne " + origin,
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 9",
            "je " + label + "_getter_shape",
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 18",
            "jne " + origin,
            label + "_getter_shape:",
            f"cmp QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}], rdx",
            "jne " + origin,
            *runtime,
            "mov r10d, " + str(0 if name == names[0] else 1),
            f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 9",
            "jne JS_FrameSymbolFieldLeaf",
            "jmp JS_FrameThisFieldLeaf",
        ]
        at = code.index(label + "_config:")
        code[at:at] = getter
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in code:
            masm += [
                line[:-1] + "::"
                if line.endswith(":")
                else line.replace(" " + origin, " NEAR PTR " + origin)
                .replace("jmp " + cfg, "jmp NEAR PTR " + cfg)
                .replace(" JS_FrameSymbolFieldLeaf", " NEAR PTR JS_FrameSymbolFieldLeaf")
            ]
            gas += [line.replace("lea r10, " + name, "lea r10, [rip+" + name + "]")]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    code = [
        "sub rsp, 88",
        "root_leaf_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "mov QWORD PTR [rsp+72], r10",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 0",
        "jne root_leaf_register_ready",
        "lea rcx, JS_FrameRootRegisterLegacyDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "jnz root_leaf_register_checked",
        "call qjs_internal_interp_register_current_disabled",
        "test eax, eax",
        "root_leaf_register_checked:",
        "setne r11b",
        "inc r11b",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], r11b",
        "root_leaf_register_ready:",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], 0",
        "jne root_leaf_modes_ready",
        "lea rcx, JS_FrameChildLeafDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], r11b",
        "root_leaf_modes_ready:",
        "cmp BYTE PTR [JS_FrameGetterLeafControl], 0",
        "jne root_leaf_getter_configured",
        "lea rcx, JS_FrameGetterLeafDisable",
        "call QWORD PTR [__imp_getenv]",
        "mov r11b, 1",
        "test rax, rax",
        "jz root_leaf_getter_publish",
        "cmp BYTE PTR [rax], 48",
        "je root_leaf_getter_publish",
        "inc r11b",
        "root_leaf_getter_publish:",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [JS_FrameGetterLeafControl], r11b",
        "root_leaf_getter_configured:",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "mov r11, QWORD PTR [rsp+72]",
        # RtlVirtualUnwind does not recognize a register-indirect tail as
        # an epilog. Choose the retry before restoring RSP, then use one
        # of two direct tails so every instruction PC unwinds correctly.
        "lea r10, JS_FrameRootLeafSelect",
        "cmp r11, r10",
        "jne root_leaf_config_legacy",
        "add rsp, 88",
        "jmp JS_FrameRootLeafSelect",
        "root_leaf_config_legacy:",
        "add rsp, 88",
        "jmp JS_FrameLegacyChildLeaf",
    ]
    masm += ["ALIGN 16", "PUBLIC " + cfg + ", " + cfg + "_end", cfg + " PROC"]
    gas += [
        ".p2align 4",
        ".globl " + cfg + ", " + cfg + "_end",
        ".def " + cfg + "; .scl 2; .type 32; .endef",
        cfg + ":",
    ]
    for line in code:
        masm += [
            line[:-1] + "::"
            if line.endswith(":")
            else line.replace(
                "jmp JS_FrameRootLeafSelect", "jmp NEAR PTR JS_FrameRootLeafSelect"
            ).replace("jmp JS_FrameLegacyChildLeaf", "jmp NEAR PTR JS_FrameLegacyChildLeaf")
        ]
        gas += [
            line.replace(
                "lea rcx, JS_FrameRootRegisterLegacyDisable",
                "lea rcx, [rip+JS_FrameRootRegisterLegacyDisable]",
            )
            .replace("lea rcx, JS_FrameChildLeafDisable", "lea rcx, [rip+JS_FrameChildLeafDisable]")
            .replace(
                "lea rcx, JS_FrameGetterLeafDisable", "lea rcx, [rip+JS_FrameGetterLeafDisable]"
            )
            .replace("[JS_FrameGetterLeafControl]", "[rip+JS_FrameGetterLeafControl]")
            .replace("lea r10, JS_FrameRootLeafSelect", "lea r10, [rip+JS_FrameRootLeafSelect]")
            .replace("[__imp_getenv]", "[rip+__imp_getenv]")
        ]
    # The retired register-control spelling is kept as separate bytes, as in
    # interpreter-env.h, for applications that still supply the old option.
    masm += [
        cfg + "_end LABEL BYTE",
        cfg + " ENDP",
        "ALIGN 4",
        cfg + "_unwind LABEL BYTE",
        "DB 1, root_leaf_config_alloc - " + cfg + ", 1, 0",
        "DB root_leaf_config_alloc - " + cfg + ", 0a2h",
        "DB 0, 0",
        "JS_FrameRootRegisterLegacyDisable LABEL BYTE",
        'DB "QJS_DISABLE_REGISTER_", 76, 76, 73, 78, 84, 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        cfg + "_end:",
        ".p2align 2",
        cfg + "_unwind:",
        ".byte 1, root_leaf_config_alloc - " + cfg + ", 1, 0",
        ".byte root_leaf_config_alloc - " + cfg + ", 0xa2",
        ".short 0",
        "JS_FrameRootRegisterLegacyDisable:",
        '.ascii "QJS_DISABLE_REGISTER_"',
        ".byte 76,76,73,78,84,0",
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (*names, cfg):
        unwind = cfg + "_unwind" if name == cfg else "JS_FrameChildLeafFast_unwind"
        masm += ["DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + unwind]
        gas += [".rva " + name + ", " + name + "_end, " + unwind]
    masm += [".pdata$zzqjscold ENDS", "END"]
