"""Function-owned leaf entries; original call/return kernels retained.

The ABI-checked padding byte holds scalar classification bits4..6, separate
from the iterator metadata byte.
The core owns bits0..3 and CallLink OOM backoff owns bit7; both are preserved.
True/false share one class and read the live immutable literal opcode.
Rejected bodies acquire the ordinary descriptor's ready bit, with no leaf cache.
No object/code/context address or decoded literal is cached. Every entry reads
the live callee, current bytecode and operands. Failing guards precede the call
commit. Primitive bodies cannot allocate, invoke C/JS, or throw. Win64 builds
with property IC also recognize one complete ordinary-data/pure-builtin wrapper.
That entry uses a nonobserving C proof, consumes its two original call polls,
and retains all precommit fallbacks. GNU additionally has an exact three-literal character
predicate reads only borrowed flat one-character strings/owned bytecode atoms,
consumes its original path-dependent call/conditional polls,and uses the same
precommit fallbacks. Cleanup uses the inherited pending-value/
finalizer protocol, including the owned XMM0
return. This is an interpreter entry specialization, not generated machine code.
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
from native_abi import current as current_abi, source_abi
from abi_layout import constants as layout_constants
import hashlib, json, re


def checked_opcodes(source):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header = core[
        core.index("typedef struct JSFunctionBytecode {") : core.index("} JSFunctionBytecode;")
    ]
    # Reject a changed private layout rather than claim a newly-used byte is
    # padding. The C adapter independently asserts sizeof/header offsets.
    flags = re.findall(r"uint8_t\s+(\w+)\s*:\s*(\d+)\s*;", header)
    assert flags == [
        ("is_strict_mode", "1"),
        ("has_prototype", "1"),
        ("has_simple_parameter_list", "1"),
        ("is_derived_class_constructor", "1"),
        ("need_home_object", "1"),
        ("func_kind", "2"),
        ("new_target_allowed", "1"),
        ("super_call_allowed", "1"),
        ("super_allowed", "1"),
        ("arguments_allowed", "1"),
        ("backtrace_barrier", "1"),
    ]

    prefix = header[: header.index("uint8_t *byte_code_buf;")]
    prefix = re.sub(r"/\*.*?\*/", "", prefix, flags=re.S)
    expected = "typedef struct JSFunctionBytecode { JSGCObjectHeader header; " + "".join(
        "uint8_t " + n + " : " + w + "; " for n, w in flags
    )
    assert "".join(prefix.split()) == "".join(expected.split()), (
        "Header padding is occupied or rearranged"
    )
    assert "/* XXX: 5 bits available */\n    uint8_t *byte_code_buf;" in header
    assert header.count("uint8_t") == 13 and "JSGCObjectHeader header;" in header
    assert core.count("b = js_mallocz(ctx, function_size);") == 2
    assert "memset(&bc, 0, sizeof(bc));" in core and "memcpy(b, &bc, sizeof(*b));" in core
    assert "FRAME_KIND(b)" in _frame_source_text(source, "quickjs-interpreter-loop.h")
    ids = {
        m[1]: i
        for i, m in enumerate(
            re.finditer(
                r"^DEF\(\s*(\w+)\s*,",
                _frame_source_file(source, "quickjs-opcode.h").read_text(),
                re.M,
            )
        )
    }
    assert ids["get_arg3"] - ids["get_arg0"] == 3
    assert ids["push_7"] - ids["push_minus1"] == 8
    return ids


def leaf_kernel(ids, diagnostics, original_unready):
    abi_rc = layout_constants(current_abi())["QJS_ABI_REF_COUNT_OFFSET"]
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    g = [
        "JS_FrameLeafGuard:",
        # The inherited live tag/class/bytecode prefix has already run. The
        # single near JNE selects this entry only while descriptor bit16 is
        # clear. Rejected bodies acquire ordinary descriptor bit16 once and
        # therefore incur no new warm-call checks or dispatch-table wrappers.
        "cmp BYTE PTR [rip+JS_FrameLeafControl], 1",
        "jne " + original_unready,
        f"test BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
        "jz " + original_unready,
        f"movzx eax, BYTE PTR [r9+{abi_bits['JSFunctionBytecode.is_strict_mode'][0][0] + 1}]",
        "shr eax, 4",
        "and eax, 7",
        "test eax, eax",
        "jz JS_FrameLeafInitialize",
        "jmp JS_FrameLeafHit",
        "JS_FrameLeafInitialize:",
        # Captured arguments require the retained owned-call protocol. Local
        # and var-ref declarations are not elided even if apparently unused.
        f"test BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 4",
        "jnz leaf_classify_reject",
        f"cmp WORD PTR [r9+{abi_fields['JSFunctionBytecode.var_count']}], 0",
        "jne leaf_classify_reject",
        f"cmp WORD PTR [r9+{abi_fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne leaf_classify_reject",
        f"mov r10, QWORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"mov eax, DWORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_len']}]",
        "cmp eax, 1",
        "je leaf_classify_undef",
        "cmp eax, 2",
        "je leaf_classify_single",
        "cmp eax, 4",
        "je leaf_classify_add",
        "jmp leaf_classify_reject",
        "leaf_classify_undef:",
        f"cmp BYTE PTR [r10], {ids['return_undef']}",
        "jne leaf_classify_reject",
        "mov eax, 2",
        "jmp leaf_classify_store",
        "leaf_classify_single:",
        f"cmp BYTE PTR [r10+1], {ids['return']}",
        "jne leaf_classify_reject",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "jbe leaf_classify_int",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "jbe leaf_classify_arg",
        f"cmp BYTE PTR [r10], {ids['undefined']}",
        "je leaf_classify_undef_value",
        f"cmp BYTE PTR [r10], {ids['null']}",
        "je leaf_classify_null",
        f"cmp BYTE PTR [r10], {ids['push_false']}",
        "je leaf_classify_false",
        f"cmp BYTE PTR [r10], {ids['push_true']}",
        "je leaf_classify_true",
        "jmp leaf_classify_reject",
        "leaf_classify_int:",
        "mov eax, 1",
        "jmp leaf_classify_store",
        "leaf_classify_undef_value:",
        "mov eax, 2",
        "jmp leaf_classify_store",
        "leaf_classify_arg:",
        "mov eax, 3",
        "jmp leaf_classify_store",
        "leaf_classify_null:",
        "mov eax, 6",
        "jmp leaf_classify_store",
        "leaf_classify_false:",
        "mov eax, 7",
        "jmp leaf_classify_store",
        "leaf_classify_true:",
        "mov eax, 7",
        "jmp leaf_classify_store",
        "leaf_classify_add:",
        f"cmp BYTE PTR [r10+2], {ids['add']}",
        "jne leaf_classify_reject",
        f"cmp BYTE PTR [r10+3], {ids['return']}",
        "jne leaf_classify_reject",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "ja leaf_classify_reject",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "jbe leaf_classify_add_const",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "ja leaf_classify_reject",
        "mov eax, 5",
        "jmp leaf_classify_store",
        "leaf_classify_add_const:",
        "mov eax, 4",
        "jmp leaf_classify_store",
        "leaf_classify_reject:",
        "jmp JS_FrameLeafUnready",
        "leaf_classify_store:",
        # Publish the same full-frame scalar descriptor before its isolated
        # three-bit leaf kind. Bit16 deliberately remains clear for a linked leaf;
        # all type/quota/poll failures can enter original_ready without
        # disabling future int32 calls or exposing partial metadata.
        "mov r11d, eax",
        f"movzx eax, WORD PTR [r9+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "shl eax, 4",
        "add eax, 160",
        f"mov WORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 6}], ax",
        f"mov BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 4}], 0",
        f"movzx eax, WORD PTR [r9+{abi_fields['JSFunctionBytecode.arg_count']}]",
        f"mov BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 3}], al",
        "mov eax, r11d",
        "shl al, 4",
        f"and BYTE PTR [r9+{abi_bits['JSFunctionBytecode.is_strict_mode'][0][0] + 1}], 143",
        f"or BYTE PTR [r9+{abi_bits['JSFunctionBytecode.is_strict_mode'][0][0] + 1}], al",
        "mov eax, r11d",
        "jmp JS_FrameLeafHit",
        "JS_FrameLeafHit:",
        # Admit the same arity, arena capacity, conservative VM quota, and
        # poll conditions as the original prepared call. This primitive leaf
        # does not acquire storage or change used/committed/SF/depth fields.
        f"movzx edx, WORD PTR [r9+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp ecx, edx",
        "jb JS_FrameLeafReject",
        f"movzx edx, WORD PTR [r9+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "shl rdx, 4",
        "add rdx, 128",
        "mov r11, QWORD PTR [rbx+8]",
        "mov r10, QWORD PTR [r11+16]",
        "add r10, rdx",
        "cmp r10, QWORD PTR [r11+8]",
        "ja JS_FrameLeafReject",
        "add rdx, QWORD PTR [rbx+32]",
        "mov r10, rsp",
        "sub r10, rdx",
        f"cmp r10, QWORD PTR [rbx+{2312 if diagnostics else 72}]",
        "jb JS_FrameLeafReject",
        f"cmp DWORD PTR [rsi+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle JS_FrameLeafReject",
        f"mov r10, QWORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "cmp eax, 1",
        "je leaf_value_int",
        "cmp eax, 2",
        "je leaf_value_undef",
        "cmp eax, 6",
        "je leaf_value_null",
        "cmp eax, 7",
        "je leaf_value_boolean_literal",
        "mov edx, eax",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, ecx",
        "jae JS_FrameLeafReject",
        "shl rax, 4",
        "add rax, r8",
        "cmp edx, 3",
        "je leaf_value_arg",
        "cmp DWORD PTR [rax+8], 0",
        "jne JS_FrameLeafReject",
        "mov r11d, DWORD PTR [rax]",
        "cmp edx, 4",
        "je leaf_value_add_const",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, ecx",
        "jae JS_FrameLeafReject",
        "shl rax, 4",
        "add rax, r8",
        "cmp DWORD PTR [rax+8], 0",
        "jne JS_FrameLeafReject",
        "add r11d, DWORD PTR [rax]",
        "jo JS_FrameLeafReject",
        "mov eax, r11d",
        "jmp leaf_value_integer",
        "leaf_value_add_const:",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['push_minus1'] + 1}",
        "add eax, r11d",
        "jo JS_FrameLeafReject",
        "jmp leaf_value_integer",
        "leaf_value_int:",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['push_minus1'] + 1}",
        "leaf_value_integer:",
        "movq xmm0, rax",
        "jmp JS_FrameLeafCommit",
        "leaf_value_undef:",
        "movdqu xmm0, XMMWORD PTR [rdi+2048]",
        "jmp JS_FrameLeafCommit",
        "leaf_value_null:",
        "xor eax, eax",
        "movq xmm0, rax",
        "mov eax, 2",
        "movq xmm1, rax",
        "punpcklqdq xmm0, xmm1",
        "jmp JS_FrameLeafCommit",
        "leaf_value_boolean_literal:",
        "xor eax, eax",
        f"cmp BYTE PTR [r10], {ids['push_true']}",
        "sete al",
        "leaf_value_boolean:",
        "movq xmm0, rax",
        "mov eax, 1",
        "movq xmm1, rax",
        "punpcklqdq xmm0, xmm1",
        "jmp JS_FrameLeafCommit",
        "leaf_value_arg:",
        "movdqu xmm0, XMMWORD PTR [rax]",
        "cmp DWORD PTR [rax+8], 0",
        "jge JS_FrameLeafCommit",
        "mov rax, QWORD PTR [rax]",
        f"inc DWORD PTR [rax{abi_rc:+d}]",
        "JS_FrameLeafCommit:",
        # Exactly one original call poll, then the original caller-owned
        # argument/function/receiver consumer. There is no C call before all
        # pending/PC/SP fields describe the committed return.
        f"dec DWORD PTR [rsi+{abi_fields['JSContext.interrupt_counter']}]",
        "mov eax, DWORD PTR [rsp+56]",
        "add r12, rax",
        "mov QWORD PTR [rbp+48], r12",
        "mov QWORD PTR [rbp+104], r13",
        "mov eax, DWORD PTR [rsp+48]",
        "lea eax, [rax+rcx+1]",
        "or eax, DWORD PTR [rsp+52]",
        "mov WORD PTR [rbp+126], ax",
        "mov r11, r13",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
    ]
    return g


def compound_kernel(ids, stream):
    f = current_abi()["offsets"]
    g = list(stream)
    at = g.index(f"cmp WORD PTR [r9+{f['JSFunctionBytecode.var_count']}], 0")
    g[at:at] = [
        "cmp BYTE PTR [rip+JS_FrameCompoundControl], 1",
        "jne compound_classify_skip",
        f"cmp DWORD PTR [r9+{f['JSFunctionBytecode.byte_code_len']}], 22",
        "je compound_classify",
        "compound_classify_skip:",
    ]
    at = g.index(f"mov WORD PTR [r9+{f['JSFunctionBytecode.byte_code_buf'] - 6}], ax")
    g[at : at + 2] = [
        f"movzx edx, WORD PTR [r9+{f['JSFunctionBytecode.var_count']}]",
        "shl edx, 4",
        "add eax, edx",
        f"mov WORD PTR [r9+{f['JSFunctionBytecode.byte_code_buf'] - 6}], ax",
        f"movzx eax, WORD PTR [r9+{f['JSFunctionBytecode.var_count']}]",
        f"mov BYTE PTR [r9+{f['JSFunctionBytecode.byte_code_buf'] - 4}], al",
    ]
    at = g.index("je leaf_value_null")
    g[at] = "je leaf_value_null_or_compound"
    # Previous add-constant path ends with an unconditional jump;no ordinary
    # leaf can fall through into these cold/body-specialized islands.
    at = g.index("leaf_value_int:")
    assert g[at - 1] == "jmp leaf_value_integer"
    save = ["mov QWORD PTR [rsp+32], r8", "mov DWORD PTR [rsp+40], ecx"]
    restore = [
        "mov r8, QWORD PTR [rsp+32]",
        "mov ecx, DWORD PTR [rsp+40]",
        "mov rdx, QWORD PTR [r8-16]",
        f"mov r9, QWORD PTR [rdx+{f['JSObject.u.func.function_bytecode']}]",
    ]

    def quota(fail):
        # Conservatively cover both original192BJSframe charge and original
        # native formal1+256Bcheck. No used/committed/limit field is modified.
        return [
            "mov rax, QWORD PTR [rbx+32]",
            "add rax, 464",
            "mov r11, rsp",
            "sub r11, rax",
            "cmp r11, QWORD PTR [rbx+72]",
            "jb " + fail,
            "mov rax, QWORD PTR [rbx+56]",
            "lea r11, [rsp-272]",
            f"cmp r11, QWORD PTR [rax+{f['JSRuntime.stack_limit']}]",
            "jb " + fail,
        ]

    code = [
        "compound_classify:",
        f"mov r10, QWORD PTR [r9+{f['JSFunctionBytecode.byte_code_buf']}]",
    ]
    for name, n in (
        ("arg_count", 1),
        ("var_count", 1),
        ("stack_size", 3),
        ("var_ref_count", 0),
        ("closure_var_count", 0),
    ):
        code += [
            f"cmp WORD PTR [r9+{f['JSFunctionBytecode.' + name]}], {n}",
            "jne leaf_classify_reject",
        ]
    code += [
        f"cmp DWORD PTR [r9+{f['JSFunctionBytecode.cpool_count']}], 0",
        "jne leaf_classify_reject",
    ]
    for off, name in (
        (0, "push_this"),
        (1, "put_loc0"),
        (2, "get_loc0"),
        (3, "get_field"),
        (8, "get_field2"),
        (13, "get_arg0"),
        (14, "get_field"),
        (19, "tail_call_method"),
    ):
        code += [f"cmp BYTE PTR [r10+{off}], {ids[name]}", "jne leaf_classify_reject"]
    code += [
        "cmp WORD PTR [r10+20], 1",
        "jne leaf_classify_reject",
        *quota("leaf_classify_reject"),
        *save,
        "mov rdx, r9",
        f"mov rcx, QWORD PTR [r9+{f['JSFunctionBytecode.realm']}]",
        "xor r8d, r8d",
        "xor r9d, r9d",
        "call JS_FrameLocaleCompareCompound",
        *restore,
        "bt rax, 33",
        "jnc leaf_classify_reject",
        "mov eax, 6",
        "jmp leaf_classify_store",
        "leaf_value_null_or_compound:",
        f"cmp BYTE PTR [r10], {ids['null']}",
        "je leaf_value_null",
        "JS_FrameCompoundEntry:",
        "cmp BYTE PTR [rip+JS_FrameCompoundControl], 1",
        "jne JS_FrameLeafReject",
        "cmp DWORD PTR [rsp+48], 1",
        "jne JS_FrameLeafReject",
        "mov rax, QWORD PTR [rbx+8]",
        "mov r11, QWORD PTR [rax+16]",
        "add r11, 192",
        "cmp r11, QWORD PTR [rax+8]",
        "ja JS_FrameLeafReject",
        *quota("JS_FrameLeafReject"),
        f"cmp DWORD PTR [rsi+{f['JSContext.interrupt_counter']}], 2",
        "jle JS_FrameLeafReject",
        *save,
        "mov rcx, rsi",
        "mov rdx, r9",
        "lea r9, [r8-32]",
        "call JS_FrameLocaleCompareCompound",
        *restore,
        "bt rax, 32",
        "jnc JS_FrameLeafReject",
        "JS_FrameCompoundSuccess:",
        "mov eax, eax",
        "movq xmm0, rax",
        f"dec DWORD PTR [rsi+{f['JSContext.interrupt_counter']}]",
        "jmp JS_FrameLeafCommit",
    ]
    g[at:at] = code
    return g


def character_set_kernel(ids, stream):
    """Exact three literal string equalities joined by ordinary short-circuit OR.

    Kind6 is disjoint: null starts with null,the complete builtin wrapper
    with push_this,and this body with get_arg0. Retained kind7 is unchanged. No cached pointer/decoded value/new VM field. Bytecode
    owns all atoms; admitted one-character flat Latin1 atom storage is immutable.
    Actual argument,realm,arity,arena,quota and poll remain guarded on every hit.
    """
    a = current_abi()
    f = a["offsets"]
    g = list(stream)
    size = a["sizes"]["JSString"]
    len_byte = a["bits"]["JSString.len"][0][0]
    kind_byte = len_byte + 7
    assert len_byte in (0, 4) and a["bits"]["JSString.len"] == [[len_byte, 1]]
    assert a["bits"]["JSString.is_wide_char"] == [[len_byte + 3, 128]]
    assert a["bits"]["JSString.kind"] == [[kind_byte, 16]] and a["bits"]["JSString.atom_type"] == [
        [kind_byte, 64]
    ]
    at = g.index("cmp eax, 1", g.index("JS_FrameLeafInitialize:"))
    g[at:at] = ["cmp eax, 30", "je character_set_classify"]
    at = g.index("JS_FrameCompoundEntry:")
    g[at:at] = [f"cmp BYTE PTR [r10], {ids['get_arg0']}", "je JS_FrameCharacterSetEntry"]
    at = g.index("leaf_value_int:")
    assert g[at - 1] == "jmp JS_FrameLeafCommit"
    code = [
        "character_set_classify:",
        "cmp BYTE PTR [rip+JS_FrameCharacterSetControl], 1",
        "jne leaf_classify_reject",
        f"cmp QWORD PTR [r9+{f['JSFunctionBytecode.realm']}], rsi",
        "jne leaf_classify_reject",
    ]
    for name, n in (
        ("arg_count", 1),
        ("var_count", 0),
        ("var_ref_count", 0),
        ("closure_var_count", 0),
        ("stack_size", 2),
    ):
        code += [
            f"cmp WORD PTR [r9+{f['JSFunctionBytecode.' + name]}], {n}",
            "jne leaf_classify_reject",
        ]
    code += [
        f"cmp DWORD PTR [r9+{f['JSFunctionBytecode.cpool_count']}], 0",
        "jne leaf_classify_reject",
        f"mov r10, QWORD PTR [r9+{f['JSFunctionBytecode.byte_code_buf']}]",
    ]
    for offset, name in (
        (0, "get_arg0"),
        (1, "push_atom_value"),
        (6, "eq"),
        (7, "dup"),
        (8, "if_true8"),
        (10, "drop"),
        (11, "get_arg0"),
        (12, "push_atom_value"),
        (17, "eq"),
        (18, "dup"),
        (19, "if_true8"),
        (21, "drop"),
        (22, "get_arg0"),
        (23, "push_atom_value"),
        (28, "eq"),
        (29, "return"),
    ):
        code += [f"cmp BYTE PTR [r10+{offset}], {ids[name]}", "jne leaf_classify_reject"]
    code += [
        "cmp BYTE PTR [r10+9], 20",
        "jne leaf_classify_reject",
        "cmp BYTE PTR [r10+20], 9",
        "jne leaf_classify_reject",
        f"mov r11, QWORD PTR [rsi+{f['JSContext.rt']}]",
        f"mov r11, QWORD PTR [r11+{f['JSRuntime.atom_array']}]",
    ]
    # Never clobber RDX/argv/argc before a cold reject: original_unready owns them.
    for offset in (2, 13, 24):
        code += [
            f"mov eax, DWORD PTR [r10+{offset}]",
            "test eax, 2147483648",
            "jnz leaf_classify_reject",
            "mov rax, QWORD PTR [r11+rax*8]",
            f"cmp DWORD PTR [rax+{len_byte}], 1",
            "jne leaf_classify_reject",
            f"test BYTE PTR [rax+{kind_byte}], 48",
            "jnz leaf_classify_reject",
            f"test BYTE PTR [rax+{kind_byte}], 128",
            "jnz leaf_classify_reject",
            f"test BYTE PTR [rax+{kind_byte}], 64",
            "jz leaf_classify_reject",
        ]
    code += [
        "mov eax, 6",
        "jmp leaf_classify_store",
        "JS_FrameCharacterSetEntry:",
        "cmp BYTE PTR [rip+JS_FrameCharacterSetControl], 1",
        "jne JS_FrameLeafReject",
        f"cmp DWORD PTR [rsi+{f['JSContext.interrupt_counter']}], 3",
        "jle JS_FrameLeafReject",
        f"cmp QWORD PTR [r9+{f['JSFunctionBytecode.realm']}], rsi",
        "jne JS_FrameLeafReject",
        "cmp DWORD PTR [r8+8], -7",
        "jne JS_FrameLeafReject",
        "mov rax, QWORD PTR [r8]",
        f"cmp DWORD PTR [rax+{len_byte}], 1",
        "jne JS_FrameLeafReject",
        f"test BYTE PTR [rax+{kind_byte}], 48",
        "jnz JS_FrameLeafReject",
        f"movzx edx, BYTE PTR [rax+{size}]",
        f"mov rax, QWORD PTR [rsi+{f['JSContext.rt']}]",
        f"mov r11, QWORD PTR [rax+{f['JSRuntime.atom_array']}]",
    ]
    for offset in (2, 13, 24):
        code += [
            f"mov eax, DWORD PTR [r10+{offset}]",
            "mov rax, QWORD PTR [r11+rax*8]",
            f"cmp dl, BYTE PTR [rax+{size}]",
            "je " + ("character_set_first_true" if offset == 2 else "character_set_later_true"),
        ]
    # Exact path-dependent poll ledger:call+first conditional=2 when first
    # literal matches;call+both conditionals=3 for every later result. Counter
    # >3 guard precedes all borrowed reads;potential callbacks use original VM.
    code += [
        "xor eax, eax",
        "jmp character_set_later_result",
        "character_set_first_true:",
        "mov eax, 1",
        f"dec DWORD PTR [rsi+{f['JSContext.interrupt_counter']}]",
        "jmp JS_FrameCharacterSetSuccess",
        "character_set_later_true:",
        "mov eax, 1",
        "character_set_later_result:",
        f"sub DWORD PTR [rsi+{f['JSContext.interrupt_counter']}], 2",
        "JS_FrameCharacterSetSuccess:",
        "jmp leaf_value_boolean",
    ]
    g[at:at] = code
    return g


@source_abi
def append(source, build, g, diagnostics):
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    # Property-IC-OFF retains the original primitive island and has no compound
    # C helper, entry, mode storage or configuration lookup.
    compound = not diagnostics and "QJS_PROPERTY_IC:BOOL=ON" in (
        build / "CMakeCache.txt"
    ).read_text(encoding="utf-8")
    ids = checked_opcodes(source)
    names = (
        "call0",
        "call1",
        "call2",
        "call3",
        "call",
        "tail_call",
        "call_method",
        "tail_call_method",
    )
    slots = {n: 8 * ids[n] for n in names}
    lo = g.index("JS_FrameGlobalBindingSelect:") + 1
    hi = g.index("JS_FrameGlobalBindingSelect_end:")
    selector = g[lo:hi]
    local = {s[:-1]: "leaf_select_" + s[:-1] for s in selector if s.endswith(":")}
    local["JS_FrameGlobalBindingSelect"] = "JS_FrameLeafSelect"
    rx = re.compile(r"\b(?:" + "|".join(map(re.escape, local)) + r")\b")
    selector = [rx.sub(lambda m: local[m[0]], s) for s in selector]
    configure = [
        "lea rcx, [rip+JS_FrameLeafDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne al",
        "inc al",
        "mov BYTE PTR [rip+JS_FrameLeafControl], al",
    ]
    if compound:
        configure += [
            "lea rcx, [rip+JS_FrameCompoundDisable]",
            "call QWORD PTR [rip+__imp_getenv]",
            "test rax, rax",
            "jne compound_select_disabled",
            "lea rcx, [rip+JS_FrameCompoundLocaleDisable]",
            "call QWORD PTR [rip+__imp_getenv]",
            "test rax, rax",
            "setne al",
            "inc al",
            "mov BYTE PTR [rip+JS_FrameCompoundControl], al",
            "jmp compound_select_done",
            "compound_select_disabled:",
            "mov BYTE PTR [rip+JS_FrameCompoundControl], 2",
            "compound_select_done:",
        ]
    if compound:
        configure += [
            "lea rcx, [rip+JS_FrameCharacterSetDisable]",
            "call QWORD PTR [rip+__imp_getenv]",
            "test rax, rax",
            "setne al",
            "inc al",
            "mov BYTE PTR [rip+JS_FrameCharacterSetControl], al",
        ]
    if not diagnostics:
        at = selector.index("mov BYTE PTR [rip+JS_FramePublishControl], 1")
        selector[at:at] = configure
    else:
        at = selector.index("lea rcx, [rip+JS_FrameGlobalBindingDisable]")
        selector[at:at] = configure
        entry = _frame_generated_file(build, "quickjs-interpreter-native-slice-win64.S")
        text = entry.read_text()
        before = "jmp JS_FrameGlobalBindingSelect\nnop\nnop"
        assert text.count(before) == 1
        entry.write_text(text.replace(before, "jmp JS_FrameLeafSelect\nnop\nnop"), encoding="utf-8")
    prepared_path = _frame_build_file(
        build,
        "quickjs-interpreter-register-win64.S"
        if diagnostics
        else "quickjs-interpreter-publish-win64.S",
    )
    prepared = prepared_path.read_text(encoding="utf-8")
    lo = prepared.index("JS_FrameInterpCallMeta:" if diagnostics else "JS_FramePublishCallMeta:")
    hi = prepared.index(
        "JS_FrameInterpCallMeta_end:" if diagnostics else "JS_FramePublishCallMeta_end:", lo
    )
    stream = prepared[lo:hi]
    original_unready = "interp_meta_unready" if diagnostics else "publish_interp_meta_unready"
    original_ready = "interp_meta_ready" if diagnostics else "publish_interp_meta_ready"
    before = "jne " + original_unready
    assert stream.count(before) == 1
    stream = stream.replace(before, "jne JS_FrameLeafGuard")
    prepared_path.write_text(prepared[:lo] + stream + prepared[hi:], encoding="utf-8")
    g += [
        '.section .qjslcal,"xr"',
        ".p2align 4",
        ".globl JS_FrameLeafSelect, JS_FrameLeafSelect_end",
        ".def JS_FrameLeafSelect; .scl 2; .type 32; .endef",
        "JS_FrameLeafSelect:",
        *selector,
        "JS_FrameLeafSelect_end:",
        ".p2align 4",
        ".globl JS_FrameLeafCalls, JS_FrameLeafCalls_end",
        ".def JS_FrameLeafCalls; .scl 2; .type 32; .endef",
        "JS_FrameLeafCalls:",
    ]
    g += [
        ".globl JS_FrameLeafGuard, JS_FrameLeafInitialize, JS_FrameLeafHit, JS_FrameLeafReject, JS_FrameLeafCommit"
    ]
    kernel = leaf_kernel(ids, diagnostics, original_unready)
    if compound:
        kernel = character_set_kernel(ids, compound_kernel(ids, kernel))
    g += kernel
    if compound:
        g += [".globl JS_FrameCompoundEntry, JS_FrameCompoundSuccess"]
    if compound:
        g += [".globl JS_FrameCharacterSetEntry, JS_FrameCharacterSetSuccess"]
    if not diagnostics:
        g += [
            "lea rax, [rip+JS_FramePublishTable]",
            "cmp rdi, rax",
            "je interp_release_values",
            "jmp publish_interp_release_values",
        ]
    else:
        g += ["jmp interp_release_values"]
    g += [
        "JS_FrameLeafReject:",
        "mov rdx, QWORD PTR [r8-16]",
        "jmp " + original_ready,
        ".globl JS_FrameLeafUnready",
        "JS_FrameLeafUnready:",
        f"movzx eax, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}]",
        "and eax, 21",
        "jmp " + original_unready,
        "JS_FrameLeafCalls_end:",
        ".p2align 2",
        "leaf_entry_unwind:",
        ".byte 33,0,0,0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .qjslefn$0,"dr"',
        ".p2align 2",
        ".rva JS_FrameLeafSelect, JS_FrameLeafSelect_end, leaf_entry_unwind",
        ".rva JS_FrameLeafCalls, JS_FrameLeafCalls_end, leaf_entry_unwind",
        '.section .qjslcm,"dw"',
        ".globl JS_FrameLeafControl",
        "JS_FrameLeafControl:",
        ".byte 0",
        "JS_FrameLeafDisable:",
        '.asciz "QJS_DISABLE_FRAME_LEAF_ENTRY"',
    ]

    if compound:
        g += [
            '.section .qjslcm,"dw"',
            ".globl JS_FrameCompoundControl",
            "JS_FrameCompoundControl:",
            ".byte 0",
            "JS_FrameCompoundDisable:",
            '.asciz "QJS_DISABLE_FRAME_COMPOUND_LEAF"',
            "JS_FrameCompoundLocaleDisable:",
            '.asciz "QJS_DISABLE_LOCALE_COMPARE_LATIN1"',
        ]
    if compound:
        g += [
            '.section .qjslcm,"dw"',
            ".globl JS_FrameCharacterSetControl",
            "JS_FrameCharacterSetControl:",
            ".byte 0",
            "JS_FrameCharacterSetDisable:",
            '.asciz "QJS_DISABLE_FRAME_CHARACTER_SET_LEAF"',
        ]
    proof = dict(
        status="passed",
        diagnostics=diagnostics,
        compound_entry=compound,
        character_set_entry=compound,
        character_set_contract="kind6null/22Bwrapper or exact30B3atom-loose-equality OR body;one formal/no locals or refs/cpool/stack2;three immutable1byte flat string atoms;same realm;live flat Latin1 argument length1;original192Bdescriptor/160Bframe quota/path-dependent2or3originalpolls/caller cleanup;no pointer/decoded value cache,C call,allocation,GC or ownership change before commit;independent presence-OFF",
        compound_contract="kind6null or exact22BJSbody;livepurebuiltinadmission;correct224Bdescriptor/192Bquota+272Bnativecheck;2originalpolls;borrowedreadonlyvalues;originalcaller-owned cleanup;mode0/2oranyproofmissoriginalready",
        header_classification_byte=current_abi()["bits"]["JSFunctionBytecode.is_strict_mode"][0][0]
        + 1,
        classification_mask=112,
        preserved_mask=143,
        kinds={
            "unknown": 0,
            "small-int": 1,
            "undefined": 2,
            "argument": 3,
            "argument+small-int": 4,
            "argument+argument": 5,
            "null": 6,
            "boolean-literal": 7,
        },
        compound_kind=(
            dict(
                kind=6,
                distinguishing_opcode="OP_null selects literal;OP_push_this exact22Bwrapper;OP_get_arg0 exact30Bcharacterpredicate",
            )
            if compound
            else None
        ),
        ordinary_warm_call_instructions_unchanged=True,
        positive_leaf_descriptor_bit16_clear=True,
        near_jcc_patch="single original CallMeta ready-guard JNE displacement",
        no_weak_address_cache=True,
        no_dynamic_code=True,
        extra_gc_roots=0,
        extra_activation_bytes=0,
        physical_frame_bytes=128,
        eligibility="live supported bytecode class13;exact primitive body/no locals,or Win64+PropertyIC exact22Bcompound/one this-local;GNU also has exact30Bcharacterpredicate/no locals. Arity,arena,quota,poll and realm proofs remain live",
        fallback="original descriptor unready/ready continuations; rejected functions acquire bit16 and bypass this island on subsequent warm calls; no PC/SP/pending/ownership/poll change before rejection",
        commit="primitive one call poll;compound two original call polls;characterpredicate one call+one/two original conditional polls. Original caller pending/PC/SP,owned XMM0,finalizer-safe value consumer and tail-call return",
        limits=[
            "Primitive addition accepts int32 without overflow; other values/coercion/overflow use the original call.",
            "No new C-to-JS root entry and no generic frameless interpreter; classification is bytecode-owned and body remains immutable.",
            "Diagnostic and PropertyIC-OFF retain primitive leaf handling;MSVC shares the22Bkernel viaappend_masm without the30Bentry.",
        ],
        source_sha256=hashlib.sha256(
            _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8").encode()
        ).hexdigest(),
        dispatch_slots=slots,
    )
    (_frame_build_file(build, "leaf-entry-generation.json")).write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )


@source_abi
def append_masm(source, build, masm, diagnostics):
    """Enter from the original cold CallMeta branch, inside its existing ABI.

    Scratch32 saves argv and scratch60 saves argc only during one-time getenv.
    Method/tail/opcode-width at48/52/56 and the Win64 shadow area remain intact.
    Callee and bytecode are reloaded from the live argv after the C call.
    The positive path allocates no frame and uses the original value consumer.
    """
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    ids = checked_opcodes(source)
    # This caller passes generated, unlike the GNU composition caller.
    cache = build.parent / "CMakeCache.txt"
    compound = not diagnostics and "QJS_PROPERTY_IC:BOOL=ON" in cache.read_text(encoding="utf-8")
    unready = "interp_meta_unready"
    ready = "interp_meta_ready"
    lo = masm.index("JS_FrameInterpCallMeta PROC")
    hi = masm.index("JS_FrameInterpCallMeta ENDP", lo)
    before = "jne " + unready
    assert masm[lo:hi].count(before) == 1
    at = masm.index(before, lo, hi)
    masm[at] = "jne NEAR PTR JS_FrameLeafGuard"
    stream = leaf_kernel(ids, diagnostics, unready)
    if compound:
        stream = compound_kernel(ids, stream)
    assert stream[:3] == [
        "JS_FrameLeafGuard:",
        "cmp BYTE PTR [rip+JS_FrameLeafControl], 1",
        "jne " + unready,
    ]
    configure = [
        "JS_FrameLeafGuard:",
        "cmp BYTE PTR [JS_FrameLeafControl], 1",
        "je leaf_masm_control_ready",
        "cmp BYTE PTR [JS_FrameLeafControl], 2",
        "je " + unready,
        "xor eax, eax",
        "mov r10b, 3",
        "lock cmpxchg BYTE PTR [JS_FrameLeafControl], r10b",
        "jne leaf_masm_control_wait",
        "mov QWORD PTR [rsp+32], r8",
        "mov DWORD PTR [rsp+60], ecx",
        "lea rcx, JS_FrameLeafDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne al",
        "inc al",
        "mov BYTE PTR [JS_FrameLeafControl], al",
        "mov r8, QWORD PTR [rsp+32]",
        "mov ecx, DWORD PTR [rsp+60]",
        "mov rdx, QWORD PTR [r8-16]",
        f"mov r9, QWORD PTR [rdx+{abi_fields['JSObject.u.func.function_bytecode']}]",
        "jmp JS_FrameLeafGuard",
        "leaf_masm_control_wait:",
        "pause",
        "jmp JS_FrameLeafGuard",
        "leaf_masm_control_ready:",
    ]
    if compound:
        # Keep LeafControl in its locked state until every subsidiary mode is
        # published. Scratch40 is free during configuration;argc remains at60.
        at = configure.index("mov BYTE PTR [JS_FrameLeafControl], al")
        configure[at : at + 1] = [
            "mov BYTE PTR [rsp+40], al",
            "lea rcx, JS_FrameCompoundDisable",
            "call QWORD PTR [__imp_getenv]",
            "test rax, rax",
            "jne compound_masm_disabled",
            "lea rcx, JS_FrameCompoundLocaleDisable",
            "call QWORD PTR [__imp_getenv]",
            "test rax, rax",
            "setne al",
            "inc al",
            "mov BYTE PTR [JS_FrameCompoundControl], al",
            "jmp compound_masm_ready",
            "compound_masm_disabled:",
            "mov BYTE PTR [JS_FrameCompoundControl], 2",
            "compound_masm_ready:",
            "movzx eax, BYTE PTR [rsp+40]",
            "mov BYTE PTR [JS_FrameLeafControl], al",
        ]
    # CMPXCHG/getenv may overwrite EAX. A rejected unvalidated bytecode
    # must reload the kind expected by the retained unready continuation.
    assert stream[3:5] == [
        f"test BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}], 1",
        "jz " + unready,
    ]
    stream[4] = "jz JS_FrameLeafUnready"
    stream = (
        configure
        + stream[3:]
        + [
            "jmp interp_release_values",
            "JS_FrameLeafReject:",
            "mov rdx, QWORD PTR [r8-16]",
            "jmp " + ready,
            "JS_FrameLeafUnready:",
            f"movzx eax, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}]",
            "and eax, 21",
            "jmp " + unready,
        ]
    )
    # The disabled path must supply the masked kind expected by unready.
    stream[stream.index("je " + unready)] = "je leaf_masm_disabled"
    stream += [
        "leaf_masm_disabled:",
        f"movzx eax, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}]",
        "and eax, 21",
        "jmp " + unready,
    ]
    stream = [re.sub(r"\[rip\+([^]]+)\]", r"[\1]", row) for row in stream]
    cross = {unready, ready, "interp_release_values"}
    translated = [
        row[:-1] + "::"
        if row.endswith(":")
        else re.sub(
            r"^(j\w+) (\w+)$", lambda m: m[1] + " NEAR PTR " + m[2] if m[2] in cross else m[0], row
        )
        for row in stream
    ]
    assert masm[-1] == "END"
    masm.pop()
    masm[3:3] = ["EXTERN __imp_getenv:QWORD"]
    if compound:
        masm[3:3] = ["EXTERN JS_FrameLocaleCompareCompound:PROC"]
    masm += [
        ".qjszlf SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC JS_FrameLeafCalls, JS_FrameLeafCalls_end",
        "PUBLIC JS_FrameLeafGuard, JS_FrameLeafInitialize, JS_FrameLeafHit, JS_FrameLeafReject, JS_FrameLeafCommit",
        "JS_FrameLeafCalls PROC",
        *translated,
        "JS_FrameLeafCalls_end LABEL BYTE",
        "JS_FrameLeafCalls ENDP",
        ".qjszlf ENDS",
        ".xdata SEGMENT ALIGN(4) READONLY 'DATA'",
        "leaf_entry_unwind LABEL BYTE",
        "DB 021h,0,0,0",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        ".xdata ENDS",
        ".pdata$zzqjsleaf SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL JS_FrameLeafCalls, IMAGEREL JS_FrameLeafCalls_end, IMAGEREL leaf_entry_unwind",
        ".pdata$zzqjsleaf ENDS",
        ".qjszlm SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC JS_FrameLeafControl",
        "JS_FrameLeafControl DB 0",
        'JS_FrameLeafDisable DB "QJS_DISABLE_FRAME_LEAF_ENTRY",0',
        ".qjszlm ENDS",
    ]
    if compound:
        # The established .qjszlm prefix is exact-sized by later control
        # adapters. Share the builtin's existing RW section for the new mode.
        masm += [
            ".qjslfm SEGMENT ALIGN(1) 'DATA'",
            "PUBLIC JS_FrameCompoundControl, JS_FrameCompoundEntry, JS_FrameCompoundSuccess",
            "JS_FrameCompoundControl DB 0",
            'JS_FrameCompoundDisable DB "QJS_DISABLE_FRAME_COMPOUND_LEAF",0',
            'JS_FrameCompoundLocaleDisable DB "QJS_DISABLE_LOCALE_COMPARE_LATIN1",0',
            ".qjslfm ENDS",
        ]
    masm += ["END"]
    proof = dict(
        status="passed",
        toolchain="msvc",
        diagnostics=diagnostics,
        header_classification_byte=current_abi()["bits"]["JSFunctionBytecode.is_strict_mode"][0][0]
        + 1,
        classification_mask=112,
        preserved_mask=143,
        shared_primitive_kernel=True,
        compound_entry=compound,
        character_set_entry=False,
        compound_contract="Exact shared22Bbody/liveordinarydata/purebuiltin;kind6disjointnull;224Bdescriptor/192Barena/464Bsoftcharge/272Bnativeguard;2originalpolls;borrowedreadonly;originalcaller cleanup;allmissprecommit",
        kinds={
            "unknown": 0,
            "small-int": 1,
            "undefined": 2,
            "argument": 3,
            "argument+small-int": 4,
            "argument+argument": 5,
            "null": 6,
            "boolean-literal": 7,
        },
        patch="same-width original CallMeta cold JNE displacement",
        extra_gc_roots=0,
        extra_activation_bytes=0,
        physical_frame_bytes=128,
        ordinary_warm_call_instructions_unchanged=True,
        commit="one poll, PC/SP/pending, owned XMM0, original finalizer-safe value consumer",
        configuration="process-level atomic once;compoundmode published beforeLeafControl;existing shadow;scratch32/40/60;live callee/bytecode reloaded",
        fallback="all arity, arena, quota, interrupt, type and overflow exits precede commit; rejected bodies use ordinary prepared frames",
        limits=[
            "Exact existing primitive forms plus release+PIC whole22Bpurewrapper;no30Bcharacterpredicate,generic frameless interpreter ornewpublicroot."
        ],
        source_sha256=hashlib.sha256(
            _frame_source_file(source, "quickjs.c").read_bytes()
        ).hexdigest(),
    )
    (_frame_build_file(build, "leaf-entry-generation.json")).write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
