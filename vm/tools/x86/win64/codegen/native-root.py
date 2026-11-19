"""One exact-width root dispatch JMP; new leaf/config and C entry late."""

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
    old = "jmp JS_FrameRootLeafSelect"
    start = gas.index("JS_FrameCallEntryDispatch:")
    end = gas.index("JS_FrameCallEntryDispatch_end:")
    assert gas[start:end].count(old) == 1
    gas[gas.index(old, start, end)] = "jmp JS_FrameNativeRootSelect"
    base = len(gas)
    name = "JS_FrameNativeRootSelect"
    fallback = "JS_FrameRootLeafSelect"
    code = [
        "test DWORD PTR [rsp+64], -3",
        "jnz " + fallback,
        "cmp DWORD PTR [r8+8], -1",
        "jne " + fallback,
        "mov r11, QWORD PTR [r8]",
        f"cmp WORD PTR [r11+{abi_fields['JSObject.class_id']}], 13",
        "jne " + fallback,
        f"mov r11, QWORD PTR [r11+{abi_fields['JSObject.u.func.function_bytecode']}]",
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
        "jz " + fallback,
        # Preserve established primitive no-frame leaves, including fallbacks.
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe " + fallback,
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        "cmp DWORD PTR [rsp+48], 65535",
        "ja " + fallback,
        # Recompute from live bytecode; no weak metadata/address dereference.
        "mov QWORD PTR [rsp+24], r11",
        f"movzx r10d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}]",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "add r10d, eax",
        "test DWORD PTR [rsp+64], 2",
        "jnz native_root_owned",
        f"test BYTE PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 4",
        "jnz native_root_owned",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp DWORD PTR [rsp+48], eax",
        "jge native_root_size",
        "native_root_owned:",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "add r10d, eax",
        "native_root_size:",
        "shl r10d, 4",
        "add r10d, 128",
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}]",
        "lea eax, [rax*8+15]",
        "and eax, -16",
        "add r10d, eax",
        "cmp r10d, 4096",
        "ja " + fallback,
        # Same original root physical admission margin, no quota relaxation.
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "lea r10, [rsp-8192]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        "cmp BYTE PTR [rip+JS_FrameNativeRootControl], 0",
        "je JS_FrameNativeRootConfig",
        "cmp BYTE PTR [rip+JS_FrameNativeRootControl], 1",
        "jne " + fallback,
        "jmp JS_FrameNativeRootRun",
    ]
    gas += [
        '.section .qjsroot$a,"xr"',
        ".p2align 4",
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
        *code,
        name + "_end:",
        "JS_FrameNativeRootConfig:",
        "sub rsp, 88",
        "native_root_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "lea rcx, [rip+JS_FrameNativeRootDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FrameNativeRootControl], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp " + name,
        "JS_FrameNativeRootConfig_end:",
        ".globl JS_FrameNativeRootConfig, JS_FrameNativeRootConfig_end",
        ".p2align 2",
        "JS_FrameNativeRootSelect_unwind:",
        ".byte 1,0,0,0",
        "JS_FrameNativeRootConfig_unwind:",
        ".byte 1,native_root_config_alloc - JS_FrameNativeRootConfig,1,0",
        ".byte native_root_config_alloc - JS_FrameNativeRootConfig,0xa2",
        ".short 0",
        "JS_FrameNativeRootDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ROOT_ENTRY"',
        '.section .pdata$zzzzzzzzrootasm,"dr"',
        ".p2align 2",
        ".rva JS_FrameNativeRootSelect, JS_FrameNativeRootSelect_end, JS_FrameNativeRootSelect_unwind",
        ".rva JS_FrameNativeRootConfig, JS_FrameNativeRootConfig_end, JS_FrameNativeRootConfig_unwind",
    ]

    output = out / "quickjs-interpreter-native-root-select-win64.S"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(".intel_syntax noprefix\n" + "\n".join(gas[base:]) + "\n", encoding="utf-8")
    del gas[base:]
