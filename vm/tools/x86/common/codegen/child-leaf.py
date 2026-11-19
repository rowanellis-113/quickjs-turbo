"""Frame-free leaf calls after the existing native child guards.

Exact compiler bytecode patterns, not function names. Accepted leaves cannot
allocate, call a host/getter, throw or release a last reference. Own-data
getters duplicate their returned value. Misses retain the old call protocol.
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


def append(masm, gas, ids, diagnostics):
    layout = current_abi()
    abi_fields = layout["offsets"]
    fast = "JS_FrameChildLeafFast"
    captured = "JS_FrameChildLeafCaptured"
    config = "JS_FrameChildLeafConfig"
    normal = "JS_FrameChildTrampoline"
    shared = "JS_FrameCallEntryShared"
    field = "JS_FrameThisFieldLeaf"
    symbol_field = "JS_FrameSymbolFieldLeaf"
    extra = 2280 if diagnostics else 0
    fixed = (248 + (2448 - 168 if diagnostics else 0) + 7) // 16 * 16 + 8

    def word(seq):
        return int.from_bytes(bytes(ids[x] if isinstance(x, str) else x for x in seq), "little")

    def hexnum(n):
        return "0" + format(n, "x") + "h"

    # Only the push-small-int byte varies, from push_minus1 through push_7.
    map_mask = 0xFFFF00FF
    reduce_mask = 0xFFFFFFFF00FFFFFF
    capture_mask = 0xFFFF00FFFFFFFFFF
    map_word = word(["get_arg0", 0, "add", "return"])
    reduce_word = word(["get_arg0", "get_arg1", "add", 0, "add", "push_0", "or", "return"])
    capture_word = word(["get_var_ref_check", 0, 0, "get_arg0", "add", 0, "add", "push_0"])
    fast_body = [
        "mov r10, QWORD PTR [rsp+8]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], 0",
        "je " + config,
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], 1",
        "jne " + normal,
        "mov r11, QWORD PTR [rsp+24]",
        f"cmp QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}], rdx",
        "jne " + normal,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 0",
        "jne child_leaf_this_field",
        f"mov r10, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 4",
        "je child_leaf_map",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 8",
        "je child_leaf_reduce",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 14",
        "je " + captured,
        "jmp " + normal,
        "child_leaf_reduce:",
        "mov r11, QWORD PTR [r10]",
        "mov rax, " + hexnum(reduce_mask),
        "and r11, rax",
        "mov rax, " + hexnum(reduce_word),
        "cmp r11, rax",
        "jne " + normal,
        "cmp DWORD PTR [rsp+48], 2",
        "jl " + normal,
        "movzx r11d, BYTE PTR [r10+3]",
        f"sub r11d, {ids['push_minus1']}",
        "cmp r11d, 8",
        "ja " + normal,
        "dec r11d",
        "mov r10, QWORD PTR [rsp+56]",
        "cmp DWORD PTR [r10+8], 0",
        "jne " + normal,
        "cmp DWORD PTR [r10+24], 0",
        "jne " + normal,
        # Both intermediate integer sums are exactly representable as doubles
        # after an overflow; the final |0 therefore permits modular addition.
        "mov eax, DWORD PTR [r10]",
        "add eax, DWORD PTR [r10+16]",
        "add eax, r11d",
        "jmp child_leaf_int_result",
        "child_leaf_map:",
        "mov eax, DWORD PTR [r10]",
        f"and eax, {map_mask}",
        f"cmp eax, {map_word}",
        "jne " + normal,
        "cmp DWORD PTR [rsp+48], 1",
        "jl " + normal,
        "movzx r11d, BYTE PTR [r10+1]",
        f"sub r11d, {ids['push_minus1']}",
        "cmp r11d, 8",
        "ja " + normal,
        "dec r11d",
        "mov r10, QWORD PTR [rsp+56]",
        "cmp DWORD PTR [r10+8], 0",
        "jne " + normal,
        "mov eax, DWORD PTR [r10]",
        "add eax, r11d",
        "jo " + normal,
        "child_leaf_int_result:",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        "mov QWORD PTR [rcx], rax",
        "mov QWORD PTR [rcx+8], 0",
        "mov rax, rcx",
        "ret",
        "child_leaf_this_field:",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 9",
        "je child_leaf_this_data",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 18",
        "jne " + normal,
        "mov r10d, 2",
        "jmp " + symbol_field,
        "child_leaf_this_data:",
        "mov r10d, 2",
        "jmp " + field,
    ]
    # Private tail ABI: standard Win64 call arguments, R11=live bytecode and
    # R10d=failed-origin selector (root=0, C internal=1, native child=2).
    # Volatile XMM words preserve R8 and the selector, with no stack/frame.
    # The bytecode owns its atom, this is borrowed, and no user code can run
    # between the live descriptor read and duplication of its data result.
    values = layout_constants(layout)
    assert values["QJS_ABI_SIZE_JSValue"] == 16
    assert values["QJS_ABI_SIZE_JSShapeProperty"] == 8
    assert values["QJS_ABI_OFF_JSShapeProperty_atom"] == 4
    assert values["QJS_ABI_HAS_PREFIX_RC"] == 0
    assert values["QJS_ABI_CONST_JS_PROP_TMASK"] == 48
    assert layout["bits"]["JSShapeProperty.flags"] == [[3, 4]]

    def own_data_probe(prefix, miss):
        # R10=borrowed receiver, R8d=live bytecode atom. No prototype/exotic
        # hook is called. R10/R11 return the borrowed data payload/tag.
        return [
            f"mov r11, QWORD PTR [r10+{abi_fields['JSObject.shape']}]",
            "mov eax, r8d",
            f"and eax, DWORD PTR [r11+{abi_fields['JSShape.prop_hash_mask']}]",
            "not rax",
            "mov eax, DWORD PTR [r11+rax*4]",
            prefix + "_probe:",
            "test eax, eax",
            "jz " + miss,
            f"cmp DWORD PTR [r11+rax*8+{abi_fields['JSShape.prop'] - 4}], r8d",
            "je " + prefix + "_found",
            f"mov eax, DWORD PTR [r11+rax*8+{abi_fields['JSShape.prop'] - 8}]",
            "and eax, 67108863",
            "jmp " + prefix + "_probe",
            prefix + "_found:",
            f"test DWORD PTR [r11+rax*8+{abi_fields['JSShape.prop'] - 8}], 3221225472",
            "jnz " + miss,
            "dec eax",
            "shl rax, 4",
            f"add rax, QWORD PTR [r10+{abi_fields['JSObject.prop']}]",
            "mov r10, QWORD PTR [rax]",
            "mov r11, QWORD PTR [rax+8]",
        ]

    field_body = [
        "movq xmm1, r8",
        "movd xmm2, r10d",
        "cmp BYTE PTR [JS_FrameGetterLeafControl], 1",
        "jne this_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 1",
        "jne this_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne this_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.closure_var_count']}], 0",
        "jne this_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}], 0",
        "jne this_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 1",
        "jne this_field_miss",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 9",
        "jne this_field_miss",
        f"mov r10, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"cmp DWORD PTR [r10], {word(['push_this', 'put_loc0', 'get_loc0', 'get_field'])}",
        "jne this_field_miss",
        f"cmp BYTE PTR [r10+8], {ids['return']}",
        "jne this_field_miss",
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle this_field_miss",
        "cmp DWORD PTR [r9+8], -1",
        "jne this_field_miss",
        "mov r8d, DWORD PTR [r10+4]",
        "mov r10, QWORD PTR [r9]",
        *own_data_probe("this_field", "this_field_miss"),
        "cmp r11d, 6",
        "je this_field_miss",
        "test r11d, r11d",
        "jns this_field_result",
        f"inc DWORD PTR [r10+{values['QJS_ABI_REF_COUNT_OFFSET']}]",
        "this_field_result:",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        "mov QWORD PTR [rcx], r10",
        "mov QWORD PTR [rcx+8], r11",
        "mov rax, rcx",
        "ret",
        "this_field_miss:",
        "movq r8, xmm1",
        "movd eax, xmm2",
        "cmp eax, 2",
        "je " + normal,
        "test eax, eax",
        "jnz qjs_frame_core_JS_CallInternal",
        "jmp JS_FrameCallEntryLegacy",
    ]
    # Exact this.field ==/=== capture0.field expression. Both live data
    # values must be Symbols. Borrow them through their existing owners;
    # identity needs no conversion, allocation, reference release or frame.
    symbol_body = [
        "movq xmm1, r8",
        "movd xmm2, r10d",
        "cmp BYTE PTR [JS_FrameGetterLeafControl], 1",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}], 1",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.closure_var_count']}], 1",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.arg_count']}], 0",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 2",
        "jne symbol_field_miss",
        f"cmp DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}], 18",
        "jne symbol_field_miss",
        f"mov r10, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"cmp DWORD PTR [r10], {word(['push_this', 'put_loc0', 'get_loc0', 'get_field'])}",
        "jne symbol_field_miss",
        f"cmp DWORD PTR [r10+8], {word(['get_var_ref_check', 0, 0, 'get_field'])}",
        "jne symbol_field_miss",
        f"cmp WORD PTR [r10+16], {word(['eq', 'return'])}",
        "je symbol_field_code_ready",
        f"cmp WORD PTR [r10+16], {word(['strict_eq', 'return'])}",
        "jne symbol_field_miss",
        "symbol_field_code_ready:",
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle symbol_field_miss",
        "cmp DWORD PTR [r9+8], -1",
        "jne symbol_field_miss",
        "mov r8d, DWORD PTR [r10+4]",
        "mov r10, QWORD PTR [r9]",
        *own_data_probe("symbol_field_left", "symbol_field_miss"),
        "cmp r11d, -8",
        "jne symbol_field_miss",
        "movq xmm3, r10",
        "movq r8, xmm1",
        "mov r10, QWORD PTR [r8]",
        f"mov r11, QWORD PTR [r10+{abi_fields['JSObject.u.func.function_bytecode']}]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov r8d, DWORD PTR [r11+12]",
        f"mov r10, QWORD PTR [r10+{abi_fields['JSObject.u.func.var_refs']}]",
        "mov r10, QWORD PTR [r10]",
        f"mov r10, QWORD PTR [r10+{abi_fields['JSVarRef.pvalue']}]",
        "cmp DWORD PTR [r10+8], -1",
        "jne symbol_field_miss",
        "mov r10, QWORD PTR [r10]",
        *own_data_probe("symbol_field_right", "symbol_field_miss"),
        "cmp r11d, -8",
        "jne symbol_field_miss",
        "movq rax, xmm3",
        "cmp r10, rax",
        "sete al",
        "movzx eax, al",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        "mov QWORD PTR [rcx], rax",
        "mov QWORD PTR [rcx+8], 1",
        "mov rax, rcx",
        "ret",
        "symbol_field_miss:",
        "movq r8, xmm1",
        "movd eax, xmm2",
        "cmp eax, 2",
        "je " + normal,
        "test eax, eax",
        "jnz qjs_frame_core_JS_CallInternal",
        "jmp JS_FrameCallEntryLegacy",
    ]
    cap_body = [
        # The already-checked child has no OWN var-ref table. Its closure's
        # external table is counted by closure_var_count, not var_ref_count.
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.closure_var_count']}], 1",
        "jne " + normal,
        f"cmp WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}], 2",
        "jne " + normal,
        f"mov r11, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov r10, QWORD PTR [r11]",
        "mov rax, " + hexnum(capture_mask),
        "and r10, rax",
        "mov rax, " + hexnum(capture_word),
        "cmp r10, rax",
        "jne " + normal,
        f"cmp DWORD PTR [r11+8], {word(['or', 'dup', 'put_var_ref_check', 0])}",
        "jne " + normal,
        f"cmp WORD PTR [r11+12], {word([0, 'return_undef'])}",
        "jne " + normal,
        "movzx r10d, BYTE PTR [r11+5]",
        f"sub r10d, {ids['push_minus1']}",
        "cmp r10d, 8",
        "ja " + normal,
        "dec r10d",
        "mov rax, QWORD PTR [r8]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSObject.u.func.var_refs']}]",
        "mov rax, QWORD PTR [rax]",
        f"cmp BYTE PTR [rax+{abi_fields['JSVarRef.is_const']}], 0",
        "jne " + normal,
        f"mov rax, QWORD PTR [rax+{abi_fields['JSVarRef.pvalue']}]",
        "cmp DWORD PTR [rax+8], 0",
        "jne " + normal,
        "mov r11, QWORD PTR [rsp+56]",
        "cmp DWORD PTR [r11+8], 0",
        "jne " + normal,
        "mov r11d, DWORD PTR [r11]",
        "add r11d, DWORD PTR [rax]",
        "add r11d, r10d",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        "mov QWORD PTR [rax], r11",
        "xor eax, eax",
        "mov QWORD PTR [rcx], rax",
        "mov QWORD PTR [rcx+8], 3",
        "mov rax, rcx",
        "ret",
    ]
    cfg_body = [
        "sub rsp, 72",
        "child_leaf_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "mov QWORD PTR [rsp+64], rax",
        "lea rcx, JS_FrameChildLeafDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 1}], r11b",
        "cmp BYTE PTR [JS_FrameGetterLeafControl], 0",
        "jne child_leaf_getter_configured",
        "lea rcx, JS_FrameGetterLeafDisable",
        "call QWORD PTR [__imp_getenv]",
        "mov r11b, 1",
        "test rax, rax",
        "jz child_leaf_getter_publish",
        "cmp BYTE PTR [rax], 48",
        "je child_leaf_getter_publish",
        "inc r11b",
        "child_leaf_getter_publish:",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [JS_FrameGetterLeafControl], r11b",
        "child_leaf_getter_configured:",
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
    for name, lines in (
        (fast, fast_body),
        (captured, cap_body),
        (config, cfg_body),
        (field, field_body),
        (symbol_field, symbol_body),
    ):
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
                else line.replace(" " + normal, " NEAR PTR " + normal)
                .replace(" " + shared, " NEAR PTR " + shared)
                .replace(
                    " qjs_frame_core_JS_CallInternal", " NEAR PTR qjs_frame_core_JS_CallInternal"
                )
                .replace(" JS_FrameCallEntryLegacy", " NEAR PTR JS_FrameCallEntryLegacy")
            ]
            g = line.replace(
                "lea rcx, JS_FrameChildLeafDisable", "lea rcx, [rip+JS_FrameChildLeafDisable]"
            )
            g = g.replace(
                "lea rcx, JS_FrameGetterLeafDisable", "lea rcx, [rip+JS_FrameGetterLeafDisable]"
            )
            g = g.replace("[JS_FrameGetterLeafControl]", "[rip+JS_FrameGetterLeafControl]")
            g = g.replace("[__imp_getenv]", "[rip+__imp_getenv]")
            import re

            g = re.sub(r"\b0([0-9a-f]+)h\b", r"0x\1", g)
            gas += [g]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        config + "_unwind LABEL BYTE",
        "DB 1, child_leaf_config_alloc - " + config + ", 1, 0",
        "DB child_leaf_config_alloc - " + config + ", 082h",
        "DB 0, 0",
        "JS_FrameChildLeafDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_CHILD_LEAF", 0',
        "JS_FrameGetterLeafDisable LABEL BYTE",
        'DB "QJS_DISABLE_THIS_FIELD_LEAF", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        config + "_unwind:",
        ".byte 1, child_leaf_config_alloc - " + config + ", 1, 0",
        ".byte child_leaf_config_alloc - " + config + ", 0x82",
        ".short 0",
        "JS_FrameChildLeafDisable:",
        '.asciz "QJS_DISABLE_NATIVE_CHILD_LEAF"',
        "JS_FrameGetterLeafDisable:",
        '.asciz "QJS_DISABLE_THIS_FIELD_LEAF"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (fast, captured, config, field, symbol_field):
        unwind = config + "_unwind" if name == config else fast + "_unwind"
        masm += ["DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + unwind]
        gas += [".rva " + name + ", " + name + "_end, " + unwind]
    # MSVC's existing .qjszlm has a sealed payload consumed by the forward
    # control adapter. Give this independent byte its own contribution.
    masm += [
        ".pdata$zzqjscold ENDS",
        ".qjsgetm SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC JS_FrameGetterLeafControl",
        "JS_FrameGetterLeafControl DB 0",
        ".qjsgetm ENDS",
        "END",
    ]
    gas += [
        '.section .qjslcm,"dw"',
        ".globl JS_FrameGetterLeafControl",
        "JS_FrameGetterLeafControl:",
        ".byte 0",
    ]
