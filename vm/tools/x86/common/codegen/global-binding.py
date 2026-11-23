"""Interp-style global binding hints with a live lexical empty-bucket proof.

No cached shape/object/value is dereferenced. 32-byte cells borrow the existing
activation table with argc=-2 for global own data and -3 for lexical data. A hit checks current lexical hash geometry and
an empty current bucket, then current global slot atom/type and value.
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
from abi_layout import constants as abi_constants
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, sys

sys.dont_write_bytecode = True


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "binding_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@source_abi
def generate(source, build, diagnostics=False, leaf_entry=False):
    abi = current_abi()
    fields = abi["offsets"]
    values = abi_constants(abi)
    inline = abi["reference_count_model"] == "inline-header"
    # JS_NewContextRaw always constructs both ordinary global objects before
    # returning a usable context. Those two fields and object class/exotic
    # identities are immutable thereafter. Guard the source invariants during
    # generation so an upstream change requires review rather than silently
    # removing checks. Shape, slots, descriptors and JSValues remain mutable.
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    if inline:
        assert "h = (uintptr_t)atom & sh->prop_hash_mask;" in core
        assert "return prop_hash_end(sh) - ((intptr_t)sh->prop_hash_mask + 1);" in core
    else:
        assert "h = hash_atom(atom, sh->prop_hash_mask);" in core
        assert "return sh->hash_table + sh->prop_hash_mask + 1;" in core
    shape_property = core[
        core.index("typedef struct JSShapeProperty {") : core.index("} JSShapeProperty;")
    ]
    assert re.search(r"uint32_t\s+hash_next\s*:\s*26\s*;", shape_property)
    assert re.search(r"uint32_t\s+flags\s*:\s*6\s*;", shape_property)
    constructors = re.findall(r"->(global_obj|global_var_obj)\s*=(?!=)\s*(.*?);", core, re.S)
    expected = {
        "global_obj": "JS_NewObjectProtoClassAlloc(ctx, ctx->class_proto[JS_CLASS_OBJECT], JS_CLASS_OBJECT, 64)",
        "global_var_obj": "JS_NewObjectProtoClassAlloc(ctx, JS_NULL, JS_CLASS_OBJECT, 16)",
    }
    assert len(constructors) == 2
    assert {name: " ".join(value.split()) for name, value in constructors} == expected
    assert not re.search(r"&\s*\w+->global_(?:var_)?obj\b", core)
    context = core[
        core.index("JSContext *JS_NewContextRaw(JSRuntime *rt)") : core.index(
            "JSContext *JS_NewContext(JSRuntime *rt)"
        )
    ]
    required = "if (JS_AddIntrinsicBasicObjects(ctx)) {\n        JS_FreeContext(ctx);\n        return NULL;\n    }\n    return ctx;"
    assert required in context
    allocation = core[
        core.index("    p->class_id = class_id;") : core.index(
            "static JSValue JS_NewObjectProtoClassAlloc("
        )
    ]
    assert "p->is_exotic = 0;" in allocation
    assert "case JS_CLASS_OBJECT:\n        break;" in allocation
    exotic_writes = re.findall(r"\w+->is_exotic\s*=(?!=)", core)
    assert len(exotic_writes) == 4 and len(re.findall(r"\w+->is_exotic\s*=(?!=)", allocation)) == 4
    object_invariants = dict(
        status="passed",
        source_sha256=hashlib.sha256(core.encode("utf-8")).hexdigest(),
        constructors=expected,
        assignments=len(constructors),
        exotic_write_sites=len(exotic_writes),
        context_raw_constructs_basic_objects=True,
        global_fields_never_passed_by_mutable_address=True,
        scope="Public engine contexts, including raw contexts; all object/exotic writes belong to allocation. No cached context/object/shape pointer is introduced.",
    )
    opcodes = [
        m[1]
        for m in re.finditer(
            r"^DEF\(\s*(\w+)\s*,", _frame_source_file(source, "quickjs-opcode.h").read_text(), re.M
        )
    ]
    slots = [opcodes.index(n) for n in ("get_var", "get_var_undef")]
    atoms = re.findall(
        r"^DEF\(\s*(\w+)", _frame_source_file(source, "quickjs-atom.h").read_text(), re.M
    )
    undefined_atom = atoms.index("undefined") + 1
    undefined_hash = (undefined_atom * 7046029254386353131) & ((1 << 64) - 1)
    selector_source = _frame_build_file(
        build,
        "quickjs-interpreter-register-win64.S"
        if diagnostics
        else "quickjs-interpreter-publish-win64.S",
    )
    original = selector_source.read_text(encoding="utf-8").splitlines()
    if diagnostics:
        begin = original.index("interp_table:") + 1
        table_values = []
        line = begin
        while original[line].startswith(".quad "):
            table_values.extend(x.strip() for x in original[line][6:].split(","))
            line += 1
        table_count = len(table_values)
        assert table_count == 258 and table_values[-2:] == ["0", "3"]
        assert len(opcodes) <= 256 and all(
            table_values[slot] == "interp_" + opcodes[slot] for slot in slots
        )
        selector = [
            "cmp BYTE PTR [rip+JS_FrameGlobalBindingControl], 1",
            "je global_binding_diagnostic_table",
            "cmp BYTE PTR [rip+JS_FrameGlobalBindingControl], 2",
            "je global_binding_original_table",
            "xor eax, eax",
            "mov cl, 3",
            "lock cmpxchg BYTE PTR [rip+JS_FrameGlobalBindingControl], cl",
            "jne global_binding_config_wait",
            "lea rcx, [rip+JS_FrameGlobalBindingDisable]",
            "call QWORD PTR [rip+__imp_getenv]",
            "test rax, rax",
            "jnz global_binding_config_disabled",
            "lea rsi, [rip+interp_table]",
            "lea rdi, [rip+JS_FrameGlobalBindingDiagnosticTable]",
            "mov ecx, " + str(table_count),
            "rep movsq",
            "lea r10, [rip+JS_FrameGlobalBindingGet]",
        ]
        for slot in slots:
            selector.append(
                "mov QWORD PTR [rip+JS_FrameGlobalBindingDiagnosticTable+"
                + str(slot * 8)
                + "], r10"
            )
        selector += [
            "mov BYTE PTR [rip+JS_FrameGlobalBindingControl], 1",
            "jmp JS_FrameGlobalBindingSelect",
            "global_binding_config_disabled:",
            "mov BYTE PTR [rip+JS_FrameGlobalBindingControl], 2",
            "jmp JS_FrameGlobalBindingSelect",
            "global_binding_config_wait:",
            "pause",
            "jmp JS_FrameGlobalBindingSelect",
            "global_binding_diagnostic_table:",
            "lea rdi, [rip+JS_FrameGlobalBindingDiagnosticTable]",
            "jmp interp_reload",
            "global_binding_original_table:",
            "lea rdi, [rip+interp_table]",
            "jmp interp_reload",
        ]
        # This entry's original LEA is seven bytes. Replace it with a five-byte
        # JMP plus two NOPs, retaining the entry size and every following RVA.
        entry = _frame_generated_file(build, "quickjs-interpreter-native-slice-win64.S")
        text = entry.read_text(encoding="utf-8")
        old = "JS_FrameNativeLifetimeEntry:\nmov QWORD PTR [rbx+2416], 0\nlea rdi, [rip+interp_table]\njmp interp_reload"
        new = old.replace(
            "lea rdi, [rip+interp_table]", "jmp JS_FrameGlobalBindingSelect\nnop\nnop"
        )
        assert text.count(old) == 1
        entry.write_text(text.replace(old, new), encoding="utf-8")
    else:
        table_count = None
        begin = original.index("JS_FramePublishSelect:")
        end = original.index("JS_FramePublishSelect_end:", begin)
        selector = original[begin + 1 : end]
        local = {
            m[1]: "global_select_" + m[1] for s in selector if (m := re.fullmatch(r"(\w+):", s))
        }
        local["JS_FramePublishSelect"] = "JS_FrameGlobalBindingSelect"
        pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, local)) + r")\b")
        selector = [pattern.sub(lambda m: local[m[0]], s) for s in selector]
        at = selector.index("mov BYTE PTR [rip+JS_FramePublishControl], 1")
        install = [
            "lea rcx, [rip+JS_FrameGlobalBindingDisable]",
            "call QWORD PTR [rip+__imp_getenv]",
            "test rax, rax",
            "jnz global_binding_config_off",
            "mov BYTE PTR [rip+JS_FrameGlobalBindingControl], 1",
            "lea r10, [rip+JS_FrameGlobalBindingGet]",
        ]
        for table in ("JS_FramePublishTable", "JS_FramePublishDirtyTable"):
            for slot in slots:
                install.append("mov QWORD PTR [rip+" + table + "+" + str(slot * 8) + "], r10")
        install += [
            "jmp global_binding_config_ready",
            "global_binding_config_off:",
            "mov BYTE PTR [rip+JS_FrameGlobalBindingControl], 2",
            "global_binding_config_ready:",
        ]
        selector[at:at] = install
    # Replace a six-byte IAT CALL by a five-byte direct CALL plus one byte.
    # This is a fixed instruction-size replacement, with no placement search.
    at = selector.index("lea rcx, [rip+JS_FrameGlobalBindingDisable]") + 1
    assert selector[at] == "call QWORD PTR [rip+__imp_getenv]"
    selector[at : at + 1] = ["call JS_FrameGlobalBindingControls", "nop"]
    # Keep arithmetic hints, but derive buckets/properties from the selected
    # source. Inline-header shapes have leading buckets and trailing props;
    # the prefix allocator revision uses a multiplied hash and trailing buckets.
    guard_bucket = ["mov edx, DWORD PTR [r11+12]"]
    if not inline:
        guard_bucket += ["lea r10, [r10+rax*4+60]"]
    guard_bucket += ["neg rdx"]
    properties = (
        [f"lea r10, [r10+{fields['JSShape.prop']}]"]
        if inline
        else [
            f"mov eax, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
            "lea r10, [r10+rax*4+60]",
        ]
    )
    if inline:
        lexical_hash = ["mov r11, r10", "mov eax, ecx", "mov edx, r9d", "and edx, eax"]
        object_hash = ["mov r11, r10", "mov edx, r9d", "and edx, ecx"]
        after_bucket = [f"lea r11, [r11+{fields['JSShape.prop']}]"]
        undefined_bucket = ["mov r11, r10", "neg rdx"]
        undefined_arithmetic = [f"mov edx, {undefined_atom}", "and edx, eax"]
    else:
        lexical_hash = [
            "lea r11, [r10+rcx*4+60]",
            "mov eax, ecx",
            "inc ecx",
            "bsr ecx, ecx",
            "mov edx, 64",
            "sub edx, ecx",
            "mov ecx, edx",
            "mov edx, r9d",
            "mov r10, 7046029254386353131",
            "imul rdx, r10",
            "shr rdx, cl",
        ]
        object_hash = [
            "lea r11, [r10+rcx*4+60]",
            "inc ecx",
            "bsr ecx, ecx",
            "mov eax, 64",
            "sub eax, ecx",
            "mov ecx, eax",
            "mov edx, r9d",
            "mov rax, 7046029254386353131",
            "imul rdx, rax",
            "shr rdx, cl",
        ]
        after_bucket = []
        undefined_bucket = ["lea r11, [r10+rax*4+60]", "neg rdx"]
        undefined_arithmetic = [
            "mov ecx, eax",
            "inc ecx",
            "bsr ecx, ecx",
            "mov edx, 64",
            "sub edx, ecx",
            "mov ecx, edx",
            f"mov rdx, {undefined_hash}",
            "shr rdx, cl",
        ]
    g = [
        ".intel_syntax noprefix",
        '.section .qjsglob,"xr"',
        ".p2align 4",
        ".globl JS_FrameGlobalBindingSelect, JS_FrameGlobalBindingSelect_end",
        ".def JS_FrameGlobalBindingSelect; .scl 2; .type 32; .endef",
        "JS_FrameGlobalBindingSelect:",
        *selector,
        "JS_FrameGlobalBindingSelect_end:",
        ".p2align 4",
        ".globl JS_FrameGlobalBindingGet, JS_FrameGlobalBindingGet_end",
        ".globl JS_FrameGlobalBindingHit, JS_FrameGlobalBindingFill, JS_FrameGlobalBindingMiss, JS_FrameGlobalBindingFallback",
        ".def JS_FrameGlobalBindingGet; .scl 2; .type 32; .endef",
        "JS_FrameGlobalBindingGet:",
        *(
            module(source, "property_ic_native").global_cell_probe(
                abi, "activation", "global_binding_ready", "JS_FrameGlobalBindingFallback"
            )
            if (build / "CMakeCache.txt").is_file()
            and "QJS_PROPERTY_IC:BOOL=ON" in (build / "CMakeCache.txt").read_text()
            else []
        ),
        # Only the newly admitted cohort bypasses the activation weak cache.
        # Preserve PC/SP/values and use the inherited native resolver with
        # its exact clean/dirty dispatch. No hint-capacity or frame change.
        "mov r11, QWORD PTR [rbp+80]",
        f"cmp DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}], 4096",
        "jbe global_binding_ordinary_cache",
        "cmp DWORD PTR [rip+JS_FrameLargeGlobalMode], 1",
        "je JS_FrameGlobalBindingFallback",
        "global_binding_ordinary_cache:",
        "mov r9d, DWORD PTR [r12+1]",
        "test r9d, r9d",
        "js JS_FrameGlobalBindingFallback",
        "mov r11, QWORD PTR [rbx+144]",
        "test r11, r11",
        "jz JS_FrameGlobalBindingFallback",
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
        "jne global_binding_second",
        "cmp DWORD PTR [r11+24], -2",
        "jne global_binding_first_lexical",
        "cmp DWORD PTR [r11+20], r9d",
        "je global_binding_guard",
        "global_binding_second:",
        "add r11, 32",
        "cmp QWORD PTR [r11], r12",
        "jne JS_FrameGlobalBindingMiss",
        "cmp DWORD PTR [r11+24], -2",
        "jne global_binding_second_lexical",
        "cmp DWORD PTR [r11+20], r9d",
        "jne JS_FrameGlobalBindingMiss",
        "global_binding_guard:",
        # The saved bucket is only arithmetic, not absence/shape identity.
        # Same mask+atom implies the same bucket; a live zero head proves no
        # lexical shadow even after GC, shape recycling, realm or eval changes.
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_var_obj']}]",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov eax, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
        "cmp eax, DWORD PTR [r11+8]",
        "jne JS_FrameGlobalBindingMiss",
        *guard_bucket,
        "cmp DWORD PTR [r10+rdx*4-4], 0",
        "jne JS_FrameGlobalBindingMiss",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_obj']}]",
        "mov ecx, DWORD PTR [r11+16]",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"cmp ecx, DWORD PTR [r10+{fields['JSShape.prop_count']}]",
        "jae JS_FrameGlobalBindingMiss",
        *properties,
        "lea r10, [r10+rcx*8]",
        "cmp DWORD PTR [r10+4], r9d",
        "jne JS_FrameGlobalBindingMiss",
        "test DWORD PTR [r10], 3221225472",
        "jnz JS_FrameGlobalBindingFallback",
        "jmp global_binding_load",
        "JS_FrameGlobalBindingMiss:",
        # Pure ASM fill uses volatile XMM2/3, no stack frame or C/JS calls.
        # Keep every cache hit unchanged. Only undefined misses bypass the
        # repeated cold hash/probe. Replace the constructor-proven redundant
        # 13-byte tag guard with cmp/near-je + one three-byte NOP.
        f"cmp r9d, {undefined_atom}",
        "je JS_FrameGlobalUndefinedLink",
        ".byte 15,31,0",
        "JS_FrameGlobalUndefinedResume:",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_var_obj']}]",
        f"test BYTE PTR [r8+{values['QJS_ABI_BIT_JSObject_is_exotic_BYTE']}], {values['QJS_ABI_BIT_JSObject_is_exotic_MASK']}",
        "jnz JS_FrameGlobalBindingFallback",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
        "test ecx, ecx",
        "js JS_FrameGlobalBindingFallback",
        *lexical_hash,
        "shl rdx, 32",
        "or rdx, rax",
        "movq xmm2, rdx",
        "shr rdx, 32",
        "neg rdx",
        "mov ecx, DWORD PTR [r11+rdx*4-4]",
        *after_bucket,
        "test ecx, ecx",
        "jnz global_binding_lexical_probe",
        f"cmp DWORD PTR [rsi+{fields['JSContext.global_obj'] + fields['JSValue.tag']}], -1",
        "jne JS_FrameGlobalBindingFallback",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_obj']}]",
        f"test BYTE PTR [r8+{values['QJS_ABI_BIT_JSObject_is_exotic_BYTE']}], {values['QJS_ABI_BIT_JSObject_is_exotic_MASK']}",
        "jnz JS_FrameGlobalBindingFallback",
        # Same pinned own-property formula as the original global handler.
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
        *object_hash,
        "neg rdx",
        "mov ecx, DWORD PTR [r11+rdx*4-4]",
        *after_bucket,
        "global_binding_object_probe:",
        "test ecx, ecx",
        "jz JS_FrameGlobalBindingFallback",
        "lea rax, [r11+rcx*8-8]",
        "cmp DWORD PTR [rax+4], r9d",
        "je global_binding_object_found",
        "mov ecx, DWORD PTR [rax]",
        "and ecx, 67108863",
        "jmp global_binding_object_probe",
        "global_binding_object_found:",
        "test DWORD PTR [rax], 3221225472",
        "jnz JS_FrameGlobalBindingFallback",
        "mov eax, 4294967294",
        "movq xmm4, rax",
        "jmp global_binding_pack",
        "global_binding_lexical_probe:",
        "lea rax, [r11+rcx*8-8]",
        "cmp DWORD PTR [rax+4], r9d",
        "je global_binding_lexical_found",
        "mov ecx, DWORD PTR [rax]",
        "and ecx, 67108863",
        "test ecx, ecx",
        "jnz global_binding_lexical_probe",
        "jmp JS_FrameGlobalBindingFallback",
        "global_binding_lexical_found:",
        "test DWORD PTR [rax], 3221225472",
        "jnz JS_FrameGlobalBindingFallback",
        "mov eax, 4294967293",
        "movq xmm4, rax",
        "global_binding_pack:",
        "dec ecx",
        "mov edx, r9d",
        "shl rdx, 32",
        "or rdx, rcx",
        "movq xmm3, rdx",
        "mov r11, QWORD PTR [rbx+144]",
        "mov rcx, r12",
        "shr rcx, 6",
        "mov rax, r12",
        "shr rax, 12",
        "xor rcx, r12",
        "xor rcx, rax",
        "and ecx, 7",
        "mov rax, rcx",
        "shl rax, 6",
        "add r11, rax",
        "cmp QWORD PTR [r11], r12",
        "je JS_FrameGlobalBindingFill",
        "cmp QWORD PTR [r11+32], r12",
        "je global_binding_fill_second",
        "cmp QWORD PTR [r11], 0",
        "je global_binding_empty_first",
        "cmp QWORD PTR [r11+32], 0",
        "je global_binding_empty_second",
        "mov r10, QWORD PTR [rbx+152]",
        "test r10, r10",
        "jz JS_FrameGlobalBindingFallback",
        "movzx eax, BYTE PTR [r10+rcx]",
        "and eax, 1",
        "xor BYTE PTR [r10+rcx], 1",
        "shl eax, 5",
        "add r11, rax",
        "jmp JS_FrameGlobalBindingFill",
        "global_binding_empty_first:",
        "mov r10, QWORD PTR [rbx+152]",
        "test r10, r10",
        "jz JS_FrameGlobalBindingFallback",
        "mov BYTE PTR [r10+rcx], 1",
        "jmp JS_FrameGlobalBindingFill",
        "global_binding_empty_second:",
        "mov r10, QWORD PTR [rbx+152]",
        "test r10, r10",
        "jz JS_FrameGlobalBindingFallback",
        "mov BYTE PTR [r10+rcx], 0",
        "global_binding_fill_second:",
        "add r11, 32",
        "JS_FrameGlobalBindingFill:",
        "movq r10, xmm2",
        "mov QWORD PTR [r11+8], r10",
        "movq rcx, xmm3",
        "mov QWORD PTR [r11+16], rcx",
        "movq rax, xmm4",
        "mov QWORD PTR [r11+24], rax",
        "mov QWORD PTR [r11], r12",
        "mov ecx, ecx",
        "cmp eax, -3",
        "je global_binding_lexical_load",
        "global_binding_load:",
        "shl rcx, 4",
        f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rcx+8]",
        "global_binding_ready:",
        "add r12, 5",
        "mov QWORD PTR [rbp+48], r12",
        "test edx, edx",
        "jns JS_FrameGlobalBindingHit",
        f"inc DWORD PTR [rax{values['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "JS_FrameGlobalBindingHit:",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "JS_FrameGlobalBindingFallback:",
        "lea r10, [rip+JS_FramePublishDirtyTable]",
        "cmp rdi, r10",
        "je global_binding_dirty_fallback",
        "jmp interp_get_var",
        "global_binding_dirty_fallback:",
        "jmp dirty_interp_get_var",
        "global_binding_first_lexical:",
        "cmp DWORD PTR [r11+24], -3",
        "jne global_binding_second",
        "cmp DWORD PTR [r11+20], r9d",
        "jne global_binding_second",
        "jmp global_binding_lexical_guard",
        "global_binding_second_lexical:",
        "cmp DWORD PTR [r11+24], -3",
        "jne JS_FrameGlobalBindingMiss",
        "cmp DWORD PTR [r11+20], r9d",
        "jne JS_FrameGlobalBindingMiss",
        "global_binding_lexical_guard:",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_var_obj']}]",
        "mov ecx, DWORD PTR [r11+16]",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"cmp ecx, DWORD PTR [r10+{fields['JSShape.prop_count']}]",
        "jae JS_FrameGlobalBindingMiss",
        *properties,
        "lea r10, [r10+rcx*8]",
        "cmp DWORD PTR [r10+4], r9d",
        "jne JS_FrameGlobalBindingMiss",
        "test DWORD PTR [r10], 3221225472",
        "jnz JS_FrameGlobalBindingFallback",
        "jmp global_binding_lexical_load",
        "global_binding_lexical_load:",
        "shl rcx, 4",
        f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rcx+8]",
        "cmp edx, 4",
        "je JS_FrameGlobalBindingFallback",
        "jmp global_binding_ready",
        "JS_FrameGlobalBindingGet_end:",
        # New code/data follow all inherited islands. Existing getter and
        # selectors retain their sizes and RVAs; only typed call/LEA edges change.
        '.section .qjsundf,"xr"',
        ".p2align 4",
        ".globl JS_FrameGlobalBindingControls, JS_FrameGlobalBindingControls_end",
        ".def JS_FrameGlobalBindingControls; .scl 2; .type 32; .endef",
        "JS_FrameGlobalBindingControls:",
        "sub rsp, 40",
        "call QWORD PTR [rip+__imp_getenv]",
        "mov QWORD PTR [rsp+32], rax",
        "lea rcx, [rip+JS_FrameGlobalUndefinedDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "mov eax, 1",
        "jz global_undefined_config_ready",
        "mov eax, 2",
        "global_undefined_config_ready:",
        "mov BYTE PTR [rip+JS_FrameGlobalUndefinedControl], al",
        "mov rax, QWORD PTR [rsp+32]",
        "add rsp, 40",
        "ret",
        "JS_FrameGlobalBindingControls_end:",
        ".p2align 4",
        ".globl JS_FrameGlobalUndefinedLink, JS_FrameGlobalUndefinedLink_end",
        ".def JS_FrameGlobalUndefinedLink; .scl 2; .type 32; .endef",
        "JS_FrameGlobalUndefinedLink:",
        "cmp BYTE PTR [rip+JS_FrameGlobalUndefinedControl], 1",
        "jne JS_FrameGlobalUndefinedResume",
        f"mov r8, QWORD PTR [rsi+{fields['JSContext.global_var_obj']}]",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"mov eax, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
        "test eax, eax",
        "js JS_FrameGlobalBindingFallback",
        "mov rdx, QWORD PTR [rip+JS_FrameGlobalUndefinedArithmetic]",
        "cmp edx, eax",
        "jne global_undefined_init_arithmetic",
        "shr rdx, 32",
        "global_undefined_lexical_bucket:",
        *undefined_bucket,
        "cmp DWORD PTR [r11+rdx*4-4], 0",
        # Empty: original fill creates a PC hint and future accesses hit.
        # Nonempty: retain native resolution; do not repeat its lexical probe.
        "je JS_FrameGlobalUndefinedResume",
        "jmp JS_FrameGlobalBindingFallback",
        "global_undefined_init_arithmetic:",
        *undefined_arithmetic,
        "mov r11, rdx",
        "shl r11, 32",
        "or r11, rax",
        "mov QWORD PTR [rip+JS_FrameGlobalUndefinedArithmetic], r11",
        "jmp global_undefined_lexical_bucket",
        "JS_FrameGlobalUndefinedLink_end:",
        ".p2align 2",
        "global_undefined_controls_unwind:",
        ".byte 1,4,1,0,4,66,0,0",
        '.section .qjsglob,"xr"',
        ".p2align 2",
        "global_binding_unwind:",
        ".byte 33,0,0,0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .qjsgcfn$0,"dr"',
        ".p2align 2",
        ".rva JS_FrameGlobalBindingSelect, JS_FrameGlobalBindingSelect_end, global_binding_unwind",
        ".rva JS_FrameGlobalBindingGet, JS_FrameGlobalBindingGet_end, global_binding_unwind",
        ".rva JS_FrameGlobalBindingControls, JS_FrameGlobalBindingControls_end, global_undefined_controls_unwind",
        ".rva JS_FrameGlobalUndefinedLink, JS_FrameGlobalUndefinedLink_end, global_binding_unwind",
        '.section .qjsgmet,"dw"',
        ".globl JS_FrameGlobalBindingControl",
        "JS_FrameGlobalBindingControl:",
        ".byte 0",
        "JS_FrameGlobalBindingDisable:",
        '.asciz "QJS_DISABLE_FRAME_GLOBAL_BINDING"',
        '.section .qjsundm,"dw"',
        "JS_FrameGlobalUndefinedDisable:",
        '.asciz "QJS_DISABLE_FRAME_GLOBAL_UNDEFINED"',
        ".globl JS_FrameGlobalUndefinedControl",
        "JS_FrameGlobalUndefinedControl:",
        ".byte 0",
        ".p2align 3",
        "JS_FrameGlobalUndefinedArithmetic:",
        ".quad 4294967295",
    ]
    if diagnostics:
        g = [s.replace("[rbx+144]", "[rbx+2280]").replace("[rbx+152]", "[rbx+2288]") for s in g]
        first = g.index("JS_FrameGlobalBindingFallback:")
        end = g.index("global_binding_first_lexical:", first)
        g[first:end] = ["JS_FrameGlobalBindingFallback:", "jmp interp_get_var"]
        g += [
            ".p2align 3",
            ".globl JS_FrameGlobalBindingDiagnosticTable",
            "JS_FrameGlobalBindingDiagnosticTable:",
            ".zero " + str(table_count * 8),
        ]
    # The linker derives the exact directory size from this executable's
    # .pdata and checkpoint/literal/global contributions. No parent PE, spare
    # section header, fixed capacity or placement search is required.
    if leaf_entry:
        module(source, "leaf-entry").append(source, build, g, diagnostics)
    asm = _frame_generated_file(build, "quickjs-interpreter-global-binding-win64.S")
    asm.write_text("\n".join(g) + "\n", encoding="utf-8")
    proof = dict(
        status="passed",
        selector_source=str(selector_source),
        private_abi_sha256=abi["source_sha256"],
        hash_geometry="leading buckets, atom & mask, inline props"
        if inline
        else "trailing buckets, multiplied hash",
        selector_source_sha256=hashlib.sha256(selector_source.read_bytes()).hexdigest(),
        dispatch_slots=slots,
        markers={"global-own": -2, "lexical-data": -3},
        hint_bytes=32,
        extra_activation_bytes=0,
        extra_gc_roots=0,
        undefined_descriptor={
            "atom": undefined_atom,
            "hash": undefined_hash,
            "controls": "QJS_DISABLE_FRAME_GLOBAL_UNDEFINED",
            "cache": "Aligned mask/bucket arithmetic pair only. Cache hits unchanged. Current empty bucket returns to original fill; nonempty bucket retains native resolution without duplicate ASM lexical probing.",
            "island": "New .qjsundf/.qjsundm follow every inherited code/data contribution. Existing getter/leaf/selector spans and RVAs retained. One fixed 13-byte cold tag-guard replacement and six-byte selector call replacement. All original hit bytes unchanged. No extra ordinary-name hop, added header, relocation/alignment/base search or cached absence/value/address.",
        },
        object_invariants=object_invariants,
        lexical_guard="Current mask equals arithmetic profile; current atom bucket is empty.",
        global_guard="Current own slot index bounds, atom and data descriptor; load/duplicate current value.",
        lexical_data_guard="Current lexical slot bounds, current slot atom/data descriptor, current value and TDZ.",
        semantic_paths="Constructor-proven immutable object tag/exotic checks leave cache hits; miss checks, live slot/atom/data, lexical absence and TDZ remain. Generation rejects changes to these constructor invariants. No padding, fixed base, PGO or layout search.",
        diagnostics=diagnostics,
        state_sites_offset=2280 if diagnostics else 144,
        state_cache_next_offset=2288 if diagnostics else 152,
        directory_capacity="Link-time SIZEOF(.pdata) plus actual late unwind contributions.",
        limitations=[
            "Global own data with a live empty lexical bucket, or a current positive lexical data slot, are admitted. Other cases retain the original handler.",
            "Release uses existing clean/dirty publication identities; diagnostics uses a separate copy of its original table. MSVC retains semantic fallback.",
        ],
    )
    (_frame_build_file(build, "global-binding-generation.json")).write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    return asm


def adapt_build(source, build, objdump, diagnostics=False, leaf_entry=False):
    adapter = module(source, "object-adapter")
    new_object = _frame_generated_file(build, "quickjs-interpreter-global-binding.obj")
    new = adapter.Coff(new_object.read_bytes())
    needed = {
        s["name"] for s in new.all_symbols.values() if s["section"] == 0 and s["storage"] == 2
    }
    paths = [_frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")]
    paths += sorted((_frame_build_file(build, "CMakeFiles/qjs.dir")).rglob("*.obj"))
    paths += sorted(
        p
        for p in _frame_generated_file(build, "").glob("*.obj")
        if p.name != "quickjs-core-original.obj" and p != new_object
    )
    promotions = []
    definitions = {}
    entry_objects = []
    for path in dict.fromkeys(paths):
        raw = path.read_bytes()
        coff = adapter.Coff(raw)
        data = bytearray(raw)
        rows = []
        for index, symbol in coff.all_symbols.items():
            if symbol["section"] <= 0:
                continue
            if symbol["name"] == "JS_FrameNativeLifetimeEntry":
                entry_objects.append(path)
            if symbol["name"] not in needed or symbol["storage"] not in (2, 3):
                continue
            definitions.setdefault(symbol["name"], []).append(str(path))
            if symbol["storage"] == 2:
                continue
            at = coff.table + index * coff.stride + coff.class_offset
            assert data[at] == 3
            data[at] = 2
            rows.append(dict(name=symbol["name"], section=symbol["section"], value=symbol["value"]))
        if rows:
            path.write_bytes(data)
            promotions.append(
                dict(
                    path=str(path),
                    before_sha256=hashlib.sha256(raw).hexdigest(),
                    after_sha256=sha(path),
                    symbols=rows,
                )
            )
    assert all(len(v) == 1 for v in definitions.values()), definitions
    assert len(entry_objects) == 1, entry_objects
    if not diagnostics:
        path = entry_objects[0]
        module(source, "iterator").route(
            path,
            source,
            objdump,
            targets={
                "JS_FramePublishSelect": "JS_FrameLeafSelect"
                if leaf_entry
                else "JS_FrameGlobalBindingSelect"
            },
            label="global-binding-" + sha(path)[:16],
            caller="JS_FrameNativeLifetimeEntry",
        )
    state = dict(
        status="passed",
        diagnostics=diagnostics,
        promotions=promotions,
        needed_symbols=sorted(needed),
        library_definitions=definitions,
        entry_object=str(entry_objects[0]),
        runner_sha256=sha(Path(__file__)),
        policy="Promote only referenced local aliases, then redirect the decoded Release entry JMP; no core body, symbol value or section/CFI changes.",
    )
    (_frame_build_file(build, "global-binding-adaptation.json")).write_text(
        json.dumps(state, indent=2) + "\n"
    )
    return state


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--adapt-build", action="store_true")
    ap.add_argument("--objdump", type=Path)
    ap.add_argument("--diagnostics", action="store_true")
    ap.add_argument("--leaf-entry", action="store_true")
    a = ap.parse_args()
    if a.adapt_build:
        assert a.objdump
        print(
            "Global binding adaptation:",
            adapt_build(a.source, a.build, a.objdump, a.diagnostics, a.leaf_entry)["status"],
        )
    else:
        print(generate(a.source, a.build, a.diagnostics, a.leaf_entry))
