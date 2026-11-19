"""Append a chained VM leaf; change only the old Number type-miss branch."""

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


def append(g):
    fields = current_abi()["offsets"]
    a = g.index("interp_get_field2:")
    at = g.index("jne interp_property_slow_get_field2", a)
    assert at == a + 2
    b = g.index("mov r9d, DWORD PTR [r12+1]", at)
    e = g.index("interp_get_field2_noref:", b)
    # Identical own shape hash/probe/TMASK/slot/dup semantics to the object lane.
    body = [
        x.replace("interp_get_field2_obj_", "number_property_obj_")
        .replace("interp_get_field2_noref", "JS_FrameNumberPropertyHit")
        .replace("interp_property_slow_get_field2", "JS_FrameNumberPropertyFallback")
        for x in g[b:e]
    ]
    g[at] = "jne interp_property_slow_get_field2"
    slow = g.index("interp_property_slow_get_field2:")
    call = g.index("call JS_FrameInterpProperty_get_field2", slow)
    assert g[call - 4 : call] == [
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
    ]
    prefix = g[slow + 1 : call - 4]
    assert prefix in ([], ["inc QWORD PTR [rbx+80]", "inc QWORD PTR [rbx+664]"])
    # Preserve the original object type/hash/slot/dup path byte for byte.
    # The old slow stub has already published its VM registers into RBX.
    # Replace its 5-byte CALL by a same-width JMP; the new leaf owns no return PC.
    g[call] = "jmp JS_FrameNumberPropertyEntry"
    g.insert(call + 1, "interp_number_property_return:")
    g += [
        '.section .qjscall$zzznumberproperty,"xr"',
        ".p2align 2",
        ".globl JS_FrameNumberPropertyEntry, JS_FrameNumberPropertyEntry_end",
        ".globl JS_FrameNumberPropertyHit, JS_FrameNumberPropertyFallback, JS_FrameNumberPropertyCold",
        ".def JS_FrameNumberPropertyEntry; .scl 2; .type 32; .endef",
        "JS_FrameNumberPropertyEntry:",
        "mov eax, DWORD PTR [r13-8]",
        "test eax, eax",
        "jz number_property_tag",
        "cmp eax, 8",
        "jne JS_FrameNumberPropertyFallback",
        "number_property_tag:",
        "cmp BYTE PTR [rip+JS_FrameNumberPropertyControl], 0",
        "je JS_FrameNumberPropertyCold",
        "cmp BYTE PTR [rip+JS_FrameNumberPropertyControl], 1",
        "jne JS_FrameNumberPropertyFallback",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.class_proto']}]",
        "cmp DWORD PTR [r8+72], -1",
        "jne JS_FrameNumberPropertyFallback",
        "mov r8, QWORD PTR [r8+64]",
        f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 4",
        "je number_property_class",
        f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 1",
        "jne JS_FrameNumberPropertyFallback",
        "number_property_class:",
        *body,
        "JS_FrameNumberPropertyHit:",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "JS_FrameNumberPropertyFallback:",
        "mov rcx, rbx",
        "call JS_FrameInterpProperty_get_field2",
        "jmp interp_number_property_return",
        "JS_FrameNumberPropertyCold:",
        # VM already owns 72 bytes of stack including Win64 shadow space.
        # All persistent VM registers are nonvolatile. getenv has no JS hooks.
        "call JS_FrameNumberPropertyConfigure",
        "jmp JS_FrameNumberPropertyEntry",
        "JS_FrameNumberPropertyEntry_end:",
        ".p2align 2",
        "number_property_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .pdata$zzzzzzzzzznumberproperty,"dr"',
        ".p2align 2",
        ".rva JS_FrameNumberPropertyEntry, JS_FrameNumberPropertyEntry_end, number_property_unwind",
    ]
