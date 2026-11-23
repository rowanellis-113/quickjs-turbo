"""Primitive string addition directly to the unmodified core concat helper.

An ordinary Win64 C call, no nonvolatile save, owned argument copies aligned
to 16 bytes. Object coercion and non-string addition retain the old boundary.
The caller changes only its existing CALL relocation operand.
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
from abi_layout import constants as abi_constants


def append(masm, gas, diagnostics, opcodes):
    layout = current_abi()
    abi_fields = layout["offsets"]
    abi_rc = abi_constants(layout)["QJS_ABI_REF_COUNT_OFFSET"]
    len_disp = layout["bits"]["JSString.len"][0][0]
    committed = 2304 if diagnostics else 64
    native = 2312 if diagnostics else 72
    shared = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    fast = "JS_FrameInterpAddDirect"
    tramp = "JS_FrameInterpAddTrampoline"
    select = "JS_FrameSharedConcatSelect"
    fallback = "JS_FrameInterpBig_add"
    gate = [
        "mov r10, QWORD PTR [rcx+24]",
        "mov eax, DWORD PTR [r10-24]",
        "sub eax, -7",
        "cmp eax, 1",
        "jbe add_direct_string",
        "mov eax, DWORD PTR [r10-8]",
        "sub eax, -7",
        "cmp eax, 1",
        "ja " + fallback,
        "add_direct_string:",
        "cmp DWORD PTR [r10-24], -1",
        "je " + fallback,
        "cmp DWORD PTR [r10-8], -1",
        "je " + fallback,
        "mov r11, QWORD PTR [rcx+56]",
        f"cmp BYTE PTR [r11+{abi_fields['JSRuntime.module_normalize_has_attr'] + 6}], 2",
        "je " + fallback,
        "cmp BYTE PTR [r11+" + str(abi_fields["JSRuntime.module_normalize_has_attr"] + 6) + "], 1",
        "jne " + tramp,
        "cmp DWORD PTR [r10-24], -6",
        "jne " + tramp,
        "cmp DWORD PTR [r10-8], -7",
        "jne " + tramp,
        "mov rdx, QWORD PTR [r10-32]",
        f"cmp DWORD PTR [rdx{abi_rc:+d}], 2",
        "jne " + tramp,
        "cmp BYTE PTR [JS_FrameLocalRopeMode], 2",
        "je " + tramp,
        "mov r11, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r11+80]",
        f"mov r8, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"movsxd r9, DWORD PTR [r11+{abi_fields['JSFunctionBytecode.byte_code_len']}]",
        "add r9, r8",
        "mov rax, QWORD PTR [rcx+16]",
        "inc rax",
        "cmp rax, r8",
        "jb " + tramp,
        "cmp rax, r9",
        "jae " + tramp,
        "mov r8, rax",
        "movzx eax, BYTE PTR [r8]",
        f"cmp eax, {opcodes['put_loc8']}",
        "je local_rope_index8",
        f"cmp eax, {opcodes['set_loc8']}",
        "je local_rope_index8",
        f"cmp eax, {opcodes['put_loc']}",
        "je local_rope_index16",
        f"cmp eax, {opcodes['set_loc']}",
        "je local_rope_index16",
        f"sub eax, {opcodes['put_loc0']}",
        "cmp eax, 3",
        "jbe local_rope_index_ready",
        "movzx eax, BYTE PTR [r8]",
        f"sub eax, {opcodes['set_loc0']}",
        "cmp eax, 3",
        "jbe local_rope_index_ready",
        "jmp " + tramp,
        "local_rope_index8:",
        "lea r11, [r8+2]",
        "cmp r11, r9",
        "ja " + tramp,
        "movzx eax, BYTE PTR [r8+1]",
        "jmp local_rope_index_ready",
        "local_rope_index16:",
        "lea r11, [r8+3]",
        "cmp r11, r9",
        "ja " + tramp,
        "movzx eax, WORD PTR [r8+1]",
        "local_rope_index_ready:",
        "mov r11, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r11+80]",
        f"cmp ax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}]",
        "jae " + tramp,
        "shl eax, 4",
        "mov r11, QWORD PTR [rcx]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSStackFrame.var_buf']}]",
        "test r11, r11",
        "jz " + tramp,
        "cmp QWORD PTR [r11+rax+8], -6",
        "jne " + tramp,
        "cmp QWORD PTR [r11+rax], rdx",
        "jne " + tramp,
        "jmp JS_FrameLocalRopeAppendEnter",
    ]
    body = [
        "sub rsp, 104",
        "add_direct_alloc:",
        "mov QWORD PTR [rsp+64], rcx",
        "mov r10, QWORD PTR [rcx+56]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_normalize_has_attr'] + 6}], 0",
        "je add_direct_config",
        # Exact begin_c: no publication of committed until after C returns.
        "mov r11, QWORD PTR [rcx+32]",
        f"sub r11, QWORD PTR [rcx+{committed}]",
        "jz add_direct_begin_done",
        f"add QWORD PTR [r10+{abi_fields['JSRuntime.stack_top']}], r11",
    ]
    if diagnostics:
        # Same counters as C begin/finish (not opcode exits, already counted).
        body += ["inc QWORD PTR [rcx+2328]"]
    body += [
        f"cmp QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je add_direct_begin_done",
        f"add QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}], r11",
        "add_direct_begin_done:",
        "mov rax, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [rcx+16]",
        "inc r11",
        "mov QWORD PTR [rax+48], r11",
        "mov rdx, QWORD PTR [rax+80]",
        f"mov rdx, QWORD PTR [rdx+{abi_fields['JSFunctionBytecode.realm']}]",
        "mov r10, QWORD PTR [rcx+24]",
        "movdqu xmm0, XMMWORD PTR [r10-32]",
        "movdqa XMMWORD PTR [rsp+32], xmm0",
        "movdqu xmm0, XMMWORD PTR [r10-16]",
        "movdqa XMMWORD PTR [rsp+48], xmm0",
        "lea rcx, [rsp+80]",
        "lea r8, [rsp+32]",
        "lea r9, [rsp+48]",
        "call " + select,
        "mov rcx, QWORD PTR [rsp+64]",
        # Exact finish_c, including host changes to the runtime stack limit.
        "mov r10, QWORD PTR [rcx+56]",
        "mov rax, QWORD PTR [rcx+32]",
        f"mov rdx, QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rcx+{committed}]",
        "jne add_direct_refresh",
        f"cmp rdx, QWORD PTR [rcx+{shared}]",
        "je add_direct_finish_done",
        "add_direct_refresh:",
        f"mov QWORD PTR [rcx+{committed}], rax",
        f"mov QWORD PTR [rcx+{shared}], rdx",
        "test rdx, rdx",
        "jz add_direct_unlimited",
        "sub rdx, rax",
        "add_direct_unlimited:",
        f"mov QWORD PTR [rcx+{native}], rdx",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rcx+2336]"]
    body += [
        "add_direct_finish_done:",
        "inc QWORD PTR [rcx+16]",
        "mov r10, QWORD PTR [rcx+24]",
        "cmp QWORD PTR [rsp+88], 6",
        "je add_direct_exception",
        "movdqa xmm0, XMMWORD PTR [rsp+80]",
        "movdqu XMMWORD PTR [r10-32], xmm0",
        "sub r10, 16",
        "mov QWORD PTR [rcx+24], r10",
        "xor eax, eax",
        "add rsp, 104",
        "ret",
        "add_direct_exception:",
        # Concat consumes both inputs even on allocation/conversion failure.
        "mov QWORD PTR [r10-32], 0",
        "mov QWORD PTR [r10-24], 3",
        "mov QWORD PTR [r10-16], 0",
        "mov QWORD PTR [r10-8], 3",
        f"mov BYTE PTR [rcx+{exception}], 1",
        "add rsp, 104",
        "jmp JS_FrameInterpSlow",
        "add_direct_config:",
        "lea rcx, JS_FrameAddDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov rcx, QWORD PTR [rsp+64]",
        "mov r10, QWORD PTR [rcx+56]",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.module_normalize_has_attr'] + 6}], r11b",
        "add rsp, 104",
        "jmp " + fast,
    ]
    assert masm.pop() == "END"
    # A leaf selector preserves the exact hidden-result/context/value-pointer
    # Win64 ABI. Rejected cases tail-jump to the original helper with no extra
    # C activation. Only already-shared long flat prefixes use a new rope.
    selector = [
        "cmp DWORD PTR [r8+8], -7",
        "jne shared_concat_fallback",
        "mov r10, QWORD PTR [r8]",
        f"mov r11d, DWORD PTR [r10{f'+{len_disp}' if len_disp else ''}]",
        "and r11d, 7fffffffh",
        "cmp r11d, 512",
        "jbe shared_concat_fallback",
        "cmp r11d, 8192",
        "ja shared_concat_fallback",
        f"cmp DWORD PTR [r10{abi_rc:+d}], 1",
        "jle shared_concat_fallback",
        "cmp DWORD PTR [r9+8], -7",
        "jne shared_concat_fallback",
        "mov r10, QWORD PTR [r9]",
        f"mov r11d, DWORD PTR [r10{f'+{len_disp}' if len_disp else ''}]",
        "and r11d, 7fffffffh",
        "test r11d, r11d",
        "jz shared_concat_fallback",
        "cmp r11d, 512",
        "ja shared_concat_fallback",
        "cmp BYTE PTR [JS_FrameConcatMode], 2",
        "je shared_concat_fallback",
        "jmp JS_FrameSharedConcatRope",
        "shared_concat_fallback:",
        "jmp qjs_frame_core_JS_ConcatString",
    ]
    masm[3:3] = [
        "EXTERN qjs_frame_core_JS_ConcatString:PROC",
        "EXTERN JS_FrameSharedConcatRope:PROC",
        "EXTERN JS_FrameConcatMode:BYTE",
        "EXTERN JS_FrameLocalRopeMode:BYTE",
        "EXTERN JS_FrameLocalRopeAppendStep:PROC",
    ]
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsleaf,"xr"']
    local_enter = "JS_FrameLocalRopeAppendEnter"
    local_body = [
        "sub rsp, 40",
        "local_rope_alloc:",
        "call JS_FrameLocalRopeAppendStep",
        "add rsp, 40",
        "ret",
    ]
    for name, lines in ((fast, gate), (tramp, body), (select, selector), (local_enter, local_body)):
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
                else line.replace(" " + fallback, " NEAR PTR " + fallback)
                .replace(" " + tramp, " NEAR PTR " + tramp)
                .replace(" " + local_enter, " NEAR PTR " + local_enter)
                .replace("jmp JS_FrameInterpSlow", "jmp NEAR PTR JS_FrameInterpSlow")
            ]
            gas += [
                line.replace("lea rcx, JS_FrameAddDisable", "lea rcx, [rip+JS_FrameAddDisable]")
                .replace("[__imp_getenv]", "[rip+__imp_getenv]")
                .replace("[JS_FrameConcatMode]", "[rip+JS_FrameConcatMode]")
                .replace("[JS_FrameLocalRopeMode]", "[rip+JS_FrameLocalRopeMode]")
                .replace("7fffffffh", "0x7fffffff")
            ]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        fast + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        tramp + "_unwind LABEL BYTE",
        "DB 1, add_direct_alloc - " + tramp + ", 1, 0",
        "DB add_direct_alloc - " + tramp + ", 0c2h",
        "DB 0, 0",
        local_enter + "_unwind LABEL BYTE",
        "DB 1, local_rope_alloc - " + local_enter + ", 1, 0",
        "DB local_rope_alloc - " + local_enter + ", 042h",
        "DB 0, 0",
        "JS_FrameAddDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_ADD_BOUNDARY", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        fast + "_unwind:",
        ".byte 1, 0, 0, 0",
        tramp + "_unwind:",
        ".byte 1, add_direct_alloc - " + tramp + ", 1, 0",
        ".byte add_direct_alloc - " + tramp + ", 0xc2",
        ".short 0",
        local_enter + "_unwind:",
        ".byte 1, local_rope_alloc - " + local_enter + ", 1, 0",
        ".byte local_rope_alloc - " + local_enter + ", 0x42",
        ".short 0",
        "JS_FrameAddDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ADD_BOUNDARY"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
    ]
    for name in (fast, tramp, select, local_enter):
        unwind = fast if name == select else name
        masm += [
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + unwind + "_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, " + unwind + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]


def native_append_body(layout, opcodes, name, miss, *, add_mode=None):
    fields = layout["offsets"]
    p = name + "_"
    rows = [
        "cmp DWORD PTR [r13-24], -6",
        "jne " + miss,
        "cmp DWORD PTR [r13-8], -7",
        "jne " + miss,
        "cmp BYTE PTR [JS_FrameLocalRopeMode], 17",
        "jne " + miss,
        "mov rax, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [rax+{fields['JSRuntime.module_normalize_has_attr'] + 6}], 1",
        "jne " + miss,
        "lea rcx, [FramePoolFunctions]",
        "mov rax, QWORD PTR [rax+32]",
        "cmp rax, QWORD PTR [rcx+32]",
        "jne " + miss,
        "mov r8, QWORD PTR [r13-32]",
        "cmp DWORD PTR [r8], 2",
        "jne " + miss,
        "mov r9, QWORD PTR [r13-16]",
        "cmp DWORD PTR [r9+4], 1",
        "jne " + miss,
        "test DWORD PTR [r9+8], 805306368",
        "jnz " + miss,
        "cmp DWORD PTR [r9], 1",
        "jle " + miss,
        "cmp DWORD PTR [r8+40], -7",
        "jne " + miss,
        "mov r10, QWORD PTR [r8+32]",
        "cmp DWORD PTR [r10], 1",
        "jne " + miss,
        "test DWORD PTR [r10+8], 4026531840",
        "jnz " + miss,
        "mov eax, DWORD PTR [r10+4]",
        "cmp eax, 512",
        "ja " + miss,
        "add eax, 26",
        "cmp QWORD PTR [r10-8], rax",
        "jb " + miss,
        # Decode only a complete following local store. A native VM PC
        # already denotes a validated opcode, but the lookahead is bounded.
        "mov r11, QWORD PTR [rbp+80]",
        f"mov rcx, QWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_buf']}]",
        f"movsxd rax, DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}]",
        "add rcx, rax",
        "lea rax, [r12+1]",
        "cmp rax, rcx",
        "jae " + miss,
        "movzx eax, BYTE PTR [r12+1]",
        f"cmp eax, {opcodes['put_loc8']}",
        "je " + p + "put8",
        f"cmp eax, {opcodes['set_loc8']}",
        "je " + p + "set8",
        f"cmp eax, {opcodes['put_loc']}",
        "je " + p + "put16",
        f"cmp eax, {opcodes['set_loc']}",
        "je " + p + "set16",
        "mov edx, 2",
        f"sub eax, {opcodes['put_loc0']}",
        "cmp eax, 3",
        "jbe " + p + "index",
        f"add eax, {opcodes['put_loc0'] - opcodes['set_loc0']}",
        "cmp eax, 3",
        "ja " + miss,
        "mov edx, 258",
        "jmp " + p + "index",
        p + "put8:",
        "mov edx, 3",
        "jmp " + p + "index8",
        p + "set8:",
        "mov edx, 259",
        p + "index8:",
        "lea rax, [r12+2]",
        "cmp rax, rcx",
        "jae " + miss,
        "movzx eax, BYTE PTR [r12+2]",
        "jmp " + p + "index",
        p + "put16:",
        "mov edx, 4",
        "jmp " + p + "index16",
        p + "set16:",
        "mov edx, 260",
        p + "index16:",
        "lea rax, [r12+3]",
        "cmp rax, rcx",
        "jae " + miss,
        "movzx eax, WORD PTR [r12+2]",
        p + "index:",
        f"movzx ecx, WORD PTR [r11+{fields['JSFunctionBytecode.var_count']}]",
        "cmp eax, ecx",
        "jae " + miss,
        f"mov rcx, QWORD PTR [rbp+{fields['JSStackFrame.var_buf']}]",
        "test rcx, rcx",
        "jz " + miss,
        "shl rax, 4",
        "add rcx, rax",
        "cmp DWORD PTR [rcx+8], -6",
        "jne " + miss,
        "cmp QWORD PTR [rcx], r8",
        "jne " + miss,
        "mov r11d, edx",
        "mov edx, 1",
        "cmp DWORD PTR [r8+24], -6",
        "jne " + p + "depth",
        "mov rax, QWORD PTR [r8+16]",
        "movzx edx, BYTE PTR [rax+9]",
        "inc edx",
        p + "depth:",
        "cmp edx, 60",
        "ja " + miss,
        "cmp DWORD PTR [r8+4], 1073741823",
        "jae " + miss,
        # Commit: the RHS has another reference and the root has exactly
        # the operand/local pair. No fallible or observable work remains.
        "mov eax, DWORD PTR [r10+4]",
        "movzx ecx, BYTE PTR [r9+24]",
        "mov BYTE PTR [r10+rax+24], cl",
        "mov BYTE PTR [r10+rax+25], 0",
        "inc DWORD PTR [r10+4]",
        "inc DWORD PTR [r8+4]",
        "mov BYTE PTR [r8+9], dl",
        "dec DWORD PTR [r9]",
        "mov QWORD PTR [r13-16], 0",
        "mov QWORD PTR [r13-8], 3",
        "test r11d, 256",
        "jnz " + p + "keep",
        "dec DWORD PTR [r8]",
        "mov QWORD PTR [r13-32], 0",
        "mov QWORD PTR [r13-24], 3",
        "sub r13, 16",
        p + "keep:",
        "sub r13, 16",
        "and r11d, 255",
        "add r12, r11",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    if add_mode is not None:
        original = [
            "mov rax, QWORD PTR [rbx+56]",
            f"cmp BYTE PTR [rax+{fields['JSRuntime.module_normalize_has_attr'] + 6}], 1",
        ]
        positions = [i for i in range(len(rows) - 1) if rows[i : i + 2] == original]
        assert len(positions) == 1
        at = positions[0]
        rows[at : at + 2] = [
            "mov rax, QWORD PTR [rbx+56]",
            "cmp BYTE PTR [rip+" + add_mode + "], 1",
        ]
    return rows


def route_native_append(masm, gas, diagnostics, opcodes, out):
    """Jump-only single-byte append before SF publication or a C activation.

    Both families retain their own exact miss edge and dispatch table. Every
    guard precedes mutation; the hit cannot allocate, collect or release a last
    reference. Unmeasured additional offsets/limits are asserted by the engine
    compiler in quickjs-string-control.inc; the pool header is asserted at its
    definition. These are private, pinned Win64 contracts, not public ABI.
    """
    assert not diagnostics
    layout = current_abi()
    fields = layout["offsets"]
    assert layout["reference_count_model"] == "inline-header"
    assert layout["sizes"]["JSString"] == 24
    for field, expected in [
        ("JSString.len", [[4, 1]]),
        ("JSString.is_wide_char", [[7, 128]]),
        ("JSString.kind", [[11, 16]]),
        ("JSString.atom_type", [[11, 64]]),
    ]:
        assert layout["bits"][field] == expected, (field, layout["bits"][field])

    def body(name, miss):
        return native_append_body(layout, opcodes, name, miss)

    def route(lines, prefix, target):
        start = next(
            i
            for i, line in enumerate(lines)
            if line in (prefix + "interp_short_big_add:", prefix + "interp_short_big_add::")
        )
        end = next(
            i
            for i in range(start + 1, len(lines))
            if lines[i] in (prefix + "interp_short_big_mul:", prefix + "interp_short_big_mul::")
        )
        old = prefix + "interp_op_slow_add"
        count = 0
        for i in range(start, end):
            if lines[i] in ("jne " + old, "jo " + old, "jne NEAR PTR " + old, "jo NEAR PTR " + old):
                branch = lines[i].split()[0]
                lines[i] = branch + " " + target
                count += 1
        assert count == 3, (prefix, count)

    clean = "JS_FrameNativeRopeAppendClean"
    dirty = "JS_FrameNativeRopeAppendDirty"
    route(gas, "", clean)
    route(masm, "", "NEAR PTR " + clean)
    assert masm.pop() == "END"
    masm[:0] = ["EXTERN FramePoolFunctions:QWORD"]
    masm += [
        ".qjscold$zzzznative_rope SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC " + clean + ", " + clean + "_end",
        clean + " PROC",
    ]
    for line in body(clean, "interp_op_slow_add"):
        masm.append(
            line[:-1] + "::"
            if line.endswith(":")
            else line.replace(" interp_op_slow_add", " NEAR PTR interp_op_slow_add")
        )
    masm += [
        clean + "_end LABEL BYTE",
        clean + " ENDP",
        ".qjscold$zzzznative_rope ENDS",
        ".pdata$zznativerope SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + clean
        + ", IMAGEREL "
        + clean
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zznativerope ENDS",
        "END",
    ]

    def emit_gas(lines, name, miss):
        lines += [
            '.section .qjsex$zzzznative_rope,"xr"',
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        lines += [
            line.replace("[JS_FrameLocalRopeMode]", "[rip+JS_FrameLocalRopeMode]").replace(
                "[FramePoolFunctions]", "[rip+FramePoolFunctions]"
            )
            for line in body(name, miss)
        ]
        lines += [
            name + "_end:",
            '.section .pdata$zznativerope,"dr"',
            ".p2align 2",
            ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
        ]

    emit_gas(gas, clean, "interp_op_slow_add")
    path = out / "quickjs-interpreter-publish-win64.S"
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        route(lines, "dirty_", dirty)
        emit_gas(lines, dirty, "dirty_interp_op_slow_add")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
