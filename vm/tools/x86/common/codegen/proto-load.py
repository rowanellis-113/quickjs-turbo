"""Guarded ProtoLoad at the own-miss branch, with two weak holder hints."""

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


def _properties(base, destination, abi):
    fields = abi["offsets"]
    if abi["reference_count_model"] == "inline-header":
        return [f"lea {destination}, [{base}+{fields['JSShape.prop']}]"]
    return [
        f"mov eax, DWORD PTR [{base}+{fields['JSShape.prop_hash_mask']}]",
        f"lea {destination}, [{base}+rax*4+{fields['JSShape.hash_table'] + 4}]",
    ]


def append(g, diagnostics, length_atom):
    abi = current_abi()
    fields = abi["offsets"]
    ((exotic_byte, exotic_mask),) = abi["bits"]["JSObject.is_exotic"]
    begin = g.index("interp_get_field2:")
    end = g.index("interp_get_field2_noref:", begin)
    patch = g.index("jz interp_property_slow_get_field2", begin, end)
    assert g[patch - 1] == "test ecx, ecx"
    # The pinned native handler has just walked the live receiver hash chain
    # and proved absence. Keep the six-byte conditional branch width and all
    # subsequent PCs. Getter/VARREF/AUTOINIT/type misses keep the old cold route.
    g[patch] = "jz JS_FrameProtoObjectEntry"
    at = g.index("jmp JS_FrameNumberPropertyEntry", g.index("interp_property_slow_get_field2:"))
    g[at] = "jmp JS_FrameProtoLoadEntry"
    sites = 2280 if diagnostics else 144
    g += [
        '.section .qjscall$zzzzprotoload,"xr"',
        ".p2align 2",
        ".globl JS_FrameProtoLoadEntry, JS_FrameProtoLoadEntry_end, JS_FrameProtoObjectEntry",
        ".globl JS_FrameProtoLoadHit, JS_FrameProtoLoadMiss, JS_FrameProtoLoadFallback",
        ".def JS_FrameProtoLoadEntry; .scl 2; .type 32; .endef",
        "JS_FrameProtoLoadEntry:",
        # The original cold stub has already published VM registers here.
        # Number and object found-descriptor misses retain the exact parent.
        "cmp DWORD PTR [r13-8], -7",
        "jne JS_FrameNumberPropertyEntry",
        "mov r9d, DWORD PTR [r12+1]",
        "test r9d, r9d",
        "js JS_FrameProtoLoadFallback",
        "cmp r9d, " + str(length_atom),
        "je JS_FrameProtoLoadFallback",
        "cmp BYTE PTR [rip+JS_FrameProtoLoadControl], 0",
        "je JS_FrameProtoLoadMiss",
        "cmp BYTE PTR [rip+JS_FrameProtoLoadControl], 1",
        "jne JS_FrameProtoLoadFallback",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.class_proto']}]",
        "cmp DWORD PTR [r8+88], -1",
        "jne JS_FrameProtoLoadFallback",
        "mov r8, QWORD PTR [r8+80]",
        "jmp proto_load_holder",
        "JS_FrameProtoObjectEntry:",
        "mov r9d, DWORD PTR [r12+1]",
        "test r9d, r9d",
        "js JS_FrameProtoLoadFallback",
        "cmp BYTE PTR [rip+JS_FrameProtoLoadControl], 0",
        "je JS_FrameProtoLoadMiss",
        "cmp BYTE PTR [rip+JS_FrameProtoLoadControl], 1",
        "jne JS_FrameProtoLoadFallback",
        "mov r8, QWORD PTR [r13-16]",
        f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
        "jz proto_load_object",
        f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 2",
        "jne JS_FrameProtoLoadFallback",
        "proto_load_object:",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov r8, QWORD PTR [r10+{fields['JSShape.proto']}]",
        "test r8, r8",
        "jz JS_FrameProtoLoadFallback",
        "proto_load_holder:",
        "mov r11, QWORD PTR [rbx+" + str(sites) + "]",
        "test r11, r11",
        "jz JS_FrameProtoLoadFallback",
        "mov rcx, r12",
        "shr rcx, 6",
        "mov rax, r12",
        "shr rax, 12",
        "xor rcx, r12",
        "xor rcx, rax",
        "and ecx, 7",
        "shl ecx, 6",
        "add r11, rcx",
        "cmp QWORD PTR [r11], r12",
        "jne proto_load_second",
        "cmp DWORD PTR [r11+24], -1",
        "jne proto_load_second",
        "cmp QWORD PTR [r11+8], r8",
        "jne proto_load_second",
        "cmp DWORD PTR [r11+20], r9d",
        "je proto_load_guard",
        "proto_load_second:",
        "add r11, 32",
        "cmp QWORD PTR [r11], r12",
        "jne JS_FrameProtoLoadMiss",
        "cmp DWORD PTR [r11+24], -1",
        "jne JS_FrameProtoLoadMiss",
        "cmp QWORD PTR [r11+8], r8",
        "jne JS_FrameProtoLoadMiss",
        "cmp DWORD PTR [r11+20], r9d",
        "jne JS_FrameProtoLoadMiss",
        "proto_load_guard:",
        "mov ecx, DWORD PTR [r11+16]",
        "cmp ecx, -1",
        "je JS_FrameProtoLoadFallback",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"cmp ecx, DWORD PTR [r10+{fields['JSShape.prop_count']}]",
        "jae JS_FrameProtoLoadMiss",
        *_properties("r10", "r11", abi),
        "lea r11, [r11+rcx*8]",
        "cmp DWORD PTR [r11+4], r9d",
        "jne JS_FrameProtoLoadMiss",
        "test DWORD PTR [r11], 3221225472",
        "jnz JS_FrameProtoLoadFallback",
        "shl rcx, 4",
        f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rcx+8]",
        "test edx, edx",
        "jns JS_FrameProtoLoadHit",
        f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "JS_FrameProtoLoadHit:",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "JS_FrameProtoLoadMiss:",
        # Object entry skipped the old C boundary on hits. Fill is pure with
        # respect to JS: publishing these fields is sufficient for its reads;
        # it allocates/calls no JS and preserves the just-proven own absence.
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameProtoPersistentTry",
        "test eax, eax",
        "jz JS_FrameProtoLoadFallback",
        "cmp DWORD PTR [r13-8], -1",
        "je JS_FrameProtoObjectEntry",
        "jmp JS_FrameProtoLoadEntry",
        "JS_FrameProtoLoadFallback:",
        "cmp DWORD PTR [r13-8], -1",
        "je proto_load_object_fallback",
        "jmp JS_FrameNumberPropertyEntry",
        "proto_load_object_fallback:",
        "jmp interp_property_slow_get_field2",
        "JS_FrameProtoLoadEntry_end:",
        ".p2align 2",
        "proto_load_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .pdata$zzzzzzzzzzprotoload,"dr"',
        ".p2align 2",
        ".rva JS_FrameProtoLoadEntry, JS_FrameProtoLoadEntry_end, proto_load_unwind",
    ]
    if not diagnostics and abi["reference_count_model"] == "inline-header":
        append_live_chain(g, abi)
    append_persistent(g, diagnostics)


def append_live_chain(g, abi):
    """Resolve live inherited data after the direct-prototype hint fails.

    Entry retains the original owned receiver on the VM stack; the existing
    object lane has proved its own absence. No cached holder is dereferenced.
    All misses return to the complete original opcode before any mutation.
    The enclosing entry's chained unwind record covers this no-C/RSP leaf,
    and the existing publication generator clones every label for Dirty.
    """
    slow = "interp_property_slow_get_field2"
    name = "JS_FrameProtoChainLive"
    at = g.index("proto_load_object_fallback:")
    assert g[at + 1] == "jmp " + slow
    g[at + 1] = "jmp " + name
    end = g.index("JS_FrameProtoLoadEntry_end:")
    g[end:end] = live_chain_body(name, slow, abi)
    # A failed activation hint otherwise enters C to fill a direct-prototype
    # slot even when the actual method is deeper and cannot use that hint.
    # Probe only deeper live data first. Direct-prototype hits and every miss
    # retain the original fill/learning policy; no negative hint is invented.
    at = g.index("JS_FrameProtoLoadMiss:")
    g[at + 1 : at + 1] = [
        "cmp DWORD PTR [r13-8], -1",
        "je JS_FrameProtoChainProbe",
        "proto_load_original_fill:",
    ]
    end = g.index("JS_FrameProtoLoadEntry_end:")
    g[end:end] = live_chain_body(
        "JS_FrameProtoChainProbe", "proto_load_original_fill", abi, deep_only=True
    )


def live_chain_body(name, slow, abi, deep_only=False):
    fields = abi["offsets"]
    ((exotic_byte, exotic_mask),) = abi["bits"]["JSObject.is_exotic"]
    body = [
        ".globl " + name,
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
        "mov r8, QWORD PTR [r13-16]",
        # The direct-object entry proved absence, but exotic receivers still
        # require the generic operation. In particular, do not infer ordinary
        # Array/typed-array behavior from a non-index-looking bytecode operand.
        f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
        "jnz " + slow,
        "mov r9d, DWORD PTR [r12+1]",
        "test r9d, r9d",
        "js " + slow,
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov r8, QWORD PTR [r10+{fields['JSShape.proto']}]",
        "test r8, r8",
        "jz " + slow,
        "mov eax, 32",
        name + "_object:",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
        "mov edx, r9d",
        "and edx, ecx",
        "neg rdx",
        "mov ecx, DWORD PTR [r10+rdx*4-4]",
        f"lea r11, [r10+{fields['JSShape.prop']}]",
        name + "_probe:",
        "test ecx, ecx",
        "jz " + name + "_absent",
        "cmp DWORD PTR [r11+rcx*8-4], r9d",
        "je " + name + "_found",
        "mov ecx, DWORD PTR [r11+rcx*8-8]",
        "and ecx, 67108863",
        "jmp " + name + "_probe",
        name + "_absent:",
        # Match the opcode's order: a current own data descriptor may be read
        # on an exotic prototype; an exotic absence must invoke its hooks.
        f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
        "jnz " + slow,
        "dec eax",
        "jz " + slow,
        f"mov r8, QWORD PTR [r10+{fields['JSShape.proto']}]",
        "test r8, r8",
        "jnz " + name + "_object",
        "jmp " + slow,
        name + "_found:",
        "test DWORD PTR [r11+rcx*8-8], 3221225472",
        "jnz " + slow,
        "dec ecx",
        "shl rcx, 4",
        f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rcx+8]",
        "test edx, edx",
        "jns " + name + "_ready",
        f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        name + "_ready:",
        # The receiver is retained by get_field2. Duplicate exactly one live
        # result and keep the current Clean/Dirty dispatch table unchanged.
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    if deep_only:
        at = body.index(name + "_found:") + 1
        body[at:at] = ["cmp eax, 32", "je " + slow]
    return body


def append_masm(masm, gas, abi):
    """Same live data lookup for the Win64 C-invoke backend, without hints.

    The caller branches here only at the proven object own-absence edge.
    Descriptor/type misses still use their original opcode boundary. Other
    reference layouts/foundation/diagnostic builds do not select this entry.
    """
    assert abi["reference_count_model"] == "inline-header"
    name = "JS_FrameProtoChainLive"
    slow = "interp_property_slow_get_field2"
    body = live_chain_body(name, slow, abi)
    # C-invoke has already saved the original template for its String/Object
    # holder probes. Retarget ONLY the primary object own-absence branch.
    for stream, suffix in ((masm, "::"), (gas, ":")):
        begin = stream.index("interp_get_field2" + suffix)
        end = stream.index("interp_get_field2_noref" + suffix, begin)
        fields = [
            i for i in range(begin, end) if stream[i] in ("jz " + slow, "jz NEAR PTR " + slow)
        ]
        assert len(fields) == 1, fields
        stream[fields[0]] = "jz " + ("NEAR PTR " if stream is masm else "") + name
    assert masm.pop() == "END"
    masm += [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC " + name,
        "PUBLIC " + name + "_end",
        name + " PROC",
    ]
    for line in body[3:]:
        if line.endswith(":"):
            masm.append(line[:-1] + "::")
        elif line.endswith(" " + slow):
            masm.append(line.replace(" " + slow, " NEAR PTR " + slow))
        else:
            masm.append(line)
    masm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        '.section .qjscold,"xr"',
        *body,
        name + "_end:",
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]


def append_persistent(g, diagnostics):
    abi = current_abi()
    fields = abi["offsets"]
    ((exotic_byte, exotic_mask),) = abi["bits"]["JSObject.is_exotic"]
    sites = 2280 if diagnostics else 144
    nexts = 2288 if diagnostics else 152
    g += [
        '.section .qjscall$zzzzzzpersisttry,"xr"',
        ".p2align 2",
        ".globl JS_FrameProtoPersistentTry, JS_FrameProtoPersistentTry_end",
        ".globl JS_FrameProtoPersistentPromote, JS_FrameProtoPersistentSnapshot",
        ".def JS_FrameProtoPersistentTry; .scl 2; .type 32; .endef",
        "JS_FrameProtoPersistentTry:",
        "cmp BYTE PTR [rip+JS_FrameProtoLoadControl], 1",
        "jne proto_persist_slow",
        "cmp BYTE PTR [rip+JS_FrameProtoPersistControl], 1",
        "jne proto_persist_slow",
        "mov r9d, DWORD PTR [r12+1]",
        # Always derive the CURRENT live holder, including during concurrent
        # first-time control initialization; never trust an incoming scratch.
        "cmp DWORD PTR [r13-8], -1",
        "je proto_persist_object",
        "cmp DWORD PTR [r13-8], -7",
        "jne proto_persist_slow",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.class_proto']}]",
        "cmp DWORD PTR [r8+88], -1",
        "jne proto_persist_slow",
        "mov r8, QWORD PTR [r8+80]",
        "jmp proto_persist_holder",
        "proto_persist_object:",
        "mov r8, QWORD PTR [r13-16]",
        f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
        "jz proto_persist_ordinary",
        f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 2",
        "jne proto_persist_slow",
        "proto_persist_ordinary:",
        f"mov r8, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov r8, QWORD PTR [r8+{fields['JSShape.proto']}]",
        "proto_persist_holder:",
        "test r8, r8",
        "jz proto_persist_slow",
        "mov rcx, r12",
        "shr rcx, 6",
        "mov rax, r12",
        "shr rax, 12",
        "xor rcx, r12",
        "xor rcx, rax",
        "and ecx, 63",
        "shl ecx, 6",
        "lea r11, [rip+JS_FrameProtoPersistentHints]",
        "add r11, rcx",
        "cmp QWORD PTR [r11], r12",
        "jne proto_persist_second",
        "cmp DWORD PTR [r11+24], -1",
        "jne proto_persist_second",
        "cmp QWORD PTR [r11+8], r8",
        "jne proto_persist_second",
        "cmp DWORD PTR [r11+20], r9d",
        "je proto_persist_snapshot",
        "proto_persist_second:",
        "add r11, 32",
        "cmp QWORD PTR [r11], r12",
        "jne proto_persist_slow",
        "cmp DWORD PTR [r11+24], -1",
        "jne proto_persist_slow",
        "cmp QWORD PTR [r11+8], r8",
        "jne proto_persist_slow",
        "cmp DWORD PTR [r11+20], r9d",
        "jne proto_persist_slow",
        "proto_persist_snapshot:",
        "JS_FrameProtoPersistentSnapshot:",
        # Capture packed slot+atom ONCE, then validate that same snapshot.
        "mov r10, QWORD PTR [r11+16]",
        "mov rax, r10",
        "shr rax, 32",
        "cmp eax, r9d",
        "jne proto_persist_slow",
        "mov ecx, r10d",
        f"mov r11, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"cmp ecx, DWORD PTR [r11+{fields['JSShape.prop_count']}]",
        "jae proto_persist_slow",
        *_properties("r11", "r11", abi),
        "lea r11, [r11+rcx*8]",
        "cmp DWORD PTR [r11+4], r9d",
        "jne proto_persist_slow",
        "test DWORD PTR [r11], 3221225472",
        "jnz proto_persist_slow",
        "mov r11, QWORD PTR [rbx+" + str(sites) + "]",
        "test r11, r11",
        "jz proto_persist_slow",
        "mov rcx, r12",
        "shr rcx, 6",
        "mov rax, r12",
        "shr rax, 12",
        "xor rcx, r12",
        "xor rcx, rax",
        "and ecx, 7",
        "mov rdx, QWORD PTR [rbx+" + str(nexts) + "]",
        "test rdx, rdx",
        "jz proto_persist_slow",
        # Calculate the 64B bucket before selecting a vacant way. Full buckets
        # keep CD replacement policy in the retained C fill.
        "mov rax, rcx",
        "shl rax, 6",
        "add r11, rax",
        "cmp QWORD PTR [r11], 0",
        "jne proto_persist_activation_second",
        "mov BYTE PTR [rdx+rcx], 1",
        "jmp JS_FrameProtoPersistentPromote",
        "proto_persist_activation_second:",
        "add r11, 32",
        "cmp QWORD PTR [r11], 0",
        "jne proto_persist_slow",
        "mov BYTE PTR [rdx+rcx], 0",
        "JS_FrameProtoPersistentPromote:",
        # Do not reread racing global fields after validation. Current live
        # identities and the validated packed snapshot form the promoted cell.
        "mov QWORD PTR [r11], r12",
        "mov QWORD PTR [r11+8], r8",
        "mov QWORD PTR [r11+16], r10",
        "mov eax, 4294967295",
        "mov QWORD PTR [r11+24], rax",
        "mov eax, 1",
        "ret",
        "proto_persist_slow:",
        "mov rcx, rbx",
        "jmp JS_FrameProtoPersistentFill",
        "JS_FrameProtoPersistentTry_end:",
        ".p2align 2",
        "proto_persistent_try_unwind:",
        ".byte 1,0,0,0",
        '.section .pdata$zzzzzzzzzzzpersisttry,"dr"',
        ".p2align 2",
        ".rva JS_FrameProtoPersistentTry, JS_FrameProtoPersistentTry_end, proto_persistent_try_unwind",
    ]
