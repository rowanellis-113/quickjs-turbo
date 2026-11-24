"""Generate identical Win64 VM handlers for MASM and GNU assembler.

The emitter uses one Intel-syntax instruction stream, never compiled C, for
the normal dispatch/call/return protocol. Only entry/SEH/table syntax differs.
QuickJS bytecode IDs come from the checked-in opcode definition, not constants.
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
import argparse
import re
from pathlib import Path
from abi_layout import constants as layout_constants
from native_abi import current_or_load as load_layout, source_abi
from indexed_own_native import append as indexed_own_append
from property_store_native import append as property_store_append


@source_abi
def generate(
    root,
    out,
    diagnostics=False,
    internal_entry=False,
    native_slice=False,
    leaf_entry_masm=False,
    c_invoke_masm=False,
    foundation_only=False,
    numeric_compare=False,
    pool_allocator=False,
    layout_override=None,
    instruction_stream=None,
    linux_borrowed_field=False,
    linux_stack_insert=False,
    linux_reference_stores=False,
    win64_native=False,
    array_append_body=None,
):
    layout = layout_override if layout_override is not None else load_layout(root)
    out.mkdir(parents=True, exist_ok=True)
    fields = layout["offsets"]
    has_prefix = layout["reference_count_model"] == "allocator-prefix"
    indexed_own = (
        internal_entry
        and (native_slice or c_invoke_masm)
        and not foundation_only
        and not diagnostics
        and not has_prefix
    )
    win64_indexed_own = bool(win64_native and internal_entry and not diagnostics)
    emit_indexed_own = bool(indexed_own or win64_indexed_own)
    typed_enum = _frame_source_file(root, "quickjs.c").read_text(encoding="utf-8")
    typed_enum = typed_enum[
        typed_enum.index("    JS_CLASS_OBJECT = 1,") : typed_enum.index("    JS_CLASS_INIT_COUNT,")
    ]
    typed_ids = {
        name: i + 1 for i, name in enumerate(re.findall(r"^\s*(JS_CLASS_\w+)", typed_enum, re.M))
    }
    assert {
        typed_ids[n]
        for n in (
            "JS_CLASS_UINT8C_ARRAY",
            "JS_CLASS_INT8_ARRAY",
            "JS_CLASS_UINT8_ARRAY",
            "JS_CLASS_INT16_ARRAY",
            "JS_CLASS_UINT16_ARRAY",
            "JS_CLASS_INT32_ARRAY",
            "JS_CLASS_UINT32_ARRAY",
        )
    } == set(range(22, 29))
    for n, expected in (
        ("JS_CLASS_UINT8C_ARRAY", 22),
        ("JS_CLASS_INT8_ARRAY", 23),
        ("JS_CLASS_UINT8_ARRAY", 24),
        ("JS_CLASS_INT16_ARRAY", 25),
        ("JS_CLASS_UINT16_ARRAY", 26),
        ("JS_CLASS_INT32_ARRAY", 27),
        ("JS_CLASS_UINT32_ARRAY", 28),
        ("JS_CLASS_FLOAT32_ARRAY", 32),
        ("JS_CLASS_FLOAT64_ARRAY", 33),
    ):
        assert typed_ids[n] == expected, "Review native typed widths after upstream change"
    rc = layout_constants(layout)["QJS_ABI_REF_COUNT_OFFSET"]
    ctx_rt, ctx_global, ctx_lexical, ctx_poll = (
        fields["JSContext." + name]
        for name in ("rt", "global_obj", "global_var_obj", "interrupt_counter")
    )
    rt_atoms, rt_top, rt_limit, rt_frame = (
        fields["JSRuntime." + name]
        for name in ("atom_array", "stack_top", "stack_limit", "current_stack_frame")
    )
    rt_shared = rt_frame - 5
    obj_class, obj_shape, obj_props = (
        fields["JSObject." + name] for name in ("class_id", "shape", "prop")
    )
    obj_refs, obj_bytecode = (
        fields["JSObject.u.func." + name] for name in ("var_refs", "function_bytecode")
    )
    obj_values, obj_count = fields["JSObject.u.array.u.values"], fields["JSObject.u.array.count"]
    obj_typed, obj_buffer, obj_cproto = (
        fields["JSObject." + name] for name in ("u.typed_array", "u.array_buffer", "u.cfunc.cproto")
    )
    obj_fast_byte, obj_fast_mask = layout["bits"]["JSObject.fast_array"][0]
    htmldda_byte, htmldda_mask = layout["bits"]["JSObject.is_HTMLDDA"][0]
    ref_value = fields["JSVarRef.pvalue"]
    string_hash = layout["bits"]["JSString.hash"][0][0]
    string_len_byte = layout["bits"]["JSString.len"][0][0]
    string_size = layout["sizes"]["JSString"]
    bc_code, bc_realm, bc_pool = (
        fields["JSFunctionBytecode." + name] for name in ("byte_code_buf", "realm", "cpool")
    )
    bc_args, bc_vars, bc_stack, bc_refs = (
        fields["JSFunctionBytecode." + name]
        for name in ("arg_count", "var_count", "stack_size", "var_ref_count")
    )
    bc_bits = layout["bits"]["JSFunctionBytecode.is_strict_mode"][0][0]
    bc_meta, bc_cached_vars, bc_cached_args, bc_kind = (
        bc_code - 6,
        bc_code - 4,
        bc_code - 3,
        bc_code - 1,
    )
    if foundation_only and (native_slice or leaf_entry_masm or c_invoke_masm):
        raise ValueError(
            "The development foundation stage cannot claim unported native supplements"
        )
    if linux_stack_insert and not (
        foundation_only
        and internal_entry
        and not diagnostics
        and instruction_stream is not None
        and layout.get("platform") == "linux-x86_64-sysv"
    ):
        raise ValueError("Linux stack insert requires the checked native instruction stream")
    if linux_reference_stores and not (
        foundation_only
        and internal_entry
        and not diagnostics
        and instruction_stream is not None
        and layout.get("platform") == "linux-x86_64-sysv"
    ):
        raise ValueError("Linux reference stores require measured native state")
    ops = re.findall(
        r"^\s*DEF\(\s*(\w+)", _frame_source_file(root, "quickjs-opcode.h").read_text(), re.M
    )
    ids = {name: i for i, name in enumerate(ops)}
    atoms = re.findall(
        r"^DEF\(\s*(\w+)", _frame_source_file(root, "quickjs-atom.h").read_text(), re.M
    )
    empty_atom = atoms.index("empty_string") + 1
    native_limit_offset = 2312 if diagnostics else 72
    return_count_offset = 2344 if internal_entry else 2304
    code, handlers, labels = [], {}, set()
    cold_stage3 = []
    reference_stores = []

    def emit(*lines):
        for line in lines:
            for instruction in (x.strip() for x in line.splitlines() if x.strip()):
                # Handler-local dispatch follows Interp's dispatch macro. The
                # old shared transfers below are generator macros, never actual
                # assembly branches. PC/operands and ownership stay identical.
                if instruction == "jmp interp_dispatch":
                    code.extend(("movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"))
                elif instruction == "jmp interp_push_value":
                    code.extend(
                        (
                            "mov QWORD PTR [r13], rax",
                            "mov QWORD PTR [r13+8], rdx",
                            "add r13, 16",
                            "movzx eax, BYTE PTR [r12]",
                            "jmp QWORD PTR [rdi+rax*8]",
                        )
                    )
                else:
                    code.append(instruction)

    def label(name):
        assert name not in labels, name
        labels.add(name)
        emit(name + ":")

    def op(name):
        handlers[name] = "interp_" + name
        label(handlers[name])

    def next_(size=1):
        emit(f"add r12, {size}", "jmp interp_dispatch")

    binding_cache = out.parent / "CMakeCache.txt"
    if linux_borrowed_field and not (
        foundation_only
        and internal_entry
        and layout.get("platform") == "linux-x86_64-sysv"
        and layout.get("property_ic")
    ):
        raise ValueError("Borrowed Linux field requires the complete actual property profile")
    binding_index = (
        indexed_own
        and binding_cache.is_file()
        and "QJS_PROPERTY_IC:BOOL=ON" in binding_cache.read_text(encoding="utf-8")
    )
    # Linux's measured global-cell emitter is separate from the PE inline
    # metadata probe selected by binding_index. Enable only the shared borrowed
    # load here; its normal output directory is not the PE CMake root.
    borrowed_field_index = binding_index or linux_borrowed_field

    def dup_value(borrow_field=False):
        # RAX/RDX are the payload/tag; the measured ABI supplies the RC address.
        ready = "interp_dup_ready_" + str(len(labels))
        emit("test edx, edx", "jns " + ready)
        if borrow_field and borrowed_field_index and (native_slice or linux_borrowed_field):
            ordinary = ready + "_ordinary"
            emit(
                "cmp edx, -1",
                "jne " + ordinary,
                f"cmp BYTE PTR [r12], {ids['get_field']}",
                "jne " + ordinary,
                "jmp JS_FrameBorrowedField",
            )
            label(ordinary)
        emit(f"inc DWORD PTR [rax{rc:+d}]")
        label(ready)
        emit("jmp interp_push_value")

    label("interp_reload")
    emit(
        "mov rbp, QWORD PTR [rbx]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "mov r14, QWORD PTR [rbp+32]",
        "mov r15, QWORD PTR [rbp+24]",
        "mov rax, QWORD PTR [rbp+80]",
        f"mov rsi, QWORD PTR [rax+{bc_realm}]",
    )
    label("interp_dispatch")
    emit("movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]")

    # Immediate values and constant pool.
    for name, value in [("push_minus1", -1)] + [("push_" + str(i), i) for i in range(8)]:
        op(name)
        emit(f"mov eax, {value}", "xor edx, edx", "inc r12", "jmp interp_push_value")
    for name, tag, payload in [
        ("undefined", 3, 0),
        ("null", 2, 0),
        ("push_false", 1, 0),
        ("push_true", 1, 1),
    ]:
        op(name)
        emit(f"mov eax, {payload}", f"mov edx, {tag}", "inc r12", "jmp interp_push_value")
    for name, load, size in [
        ("push_i8", "movsx eax, BYTE PTR [r12+1]", 2),
        ("push_i16", "movsx eax, WORD PTR [r12+1]", 3),
        ("push_i32", "mov eax, DWORD PTR [r12+1]", 5),
    ]:
        op(name)
        emit(load, "xor edx, edx", f"add r12, {size}", "jmp interp_push_value")
    for name, load, size in [
        ("push_const8", "movzx ecx, BYTE PTR [r12+1]", 2),
        ("push_const", "mov ecx, DWORD PTR [r12+1]", 5),
    ]:
        op(name)
        emit(
            load,
            "shl rcx, 4",
            "mov rax, QWORD PTR [rbp+80]",
            f"mov rax, QWORD PTR [rax+{bc_pool}]",
            "add rax, rcx",
            "mov rdx, QWORD PTR [rax+8]",
            "mov rax, QWORD PTR [rax]",
            f"add r12, {size}",
        )
        dup_value()
    op("push_empty_string")
    emit(
        "mov rax, QWORD PTR [rbx+56]",
        f"mov rax, QWORD PTR [rax+{rt_atoms}]",
        f"mov rax, QWORD PTR [rax+{empty_atom * 8}]",
        "mov rdx, -7",
        "inc r12",
    )
    dup_value()
    op("push_atom_value")
    # Numeric atoms require allocating their decimal string. All other atoms
    # duplicate the live string/symbol, exactly as __JS_AtomToValue does.
    emit(
        "mov ecx, DWORD PTR [r12+1]",
        "test ecx, ecx",
        "js interp_slow",
        "mov rax, QWORD PTR [rbx+56]",
        f"mov rax, QWORD PTR [rax+{rt_atoms}]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        f"mov ecx, DWORD PTR [rax+{string_hash}]",
        "shr ecx, 30",
        "mov rdx, -7",
        "cmp ecx, 1",
        "je interp_atom_ready",
        "mov rdx, -8",
    )
    label("interp_atom_ready")
    emit("add r12, 5")
    dup_value()
    op("push_this")
    emit(
        "mov rax, QWORD PTR [rbp+88]",
        "mov rdx, QWORD PTR [rbp+96]",
        "cmp BYTE PTR [rbp+60], 0",
        "jne interp_this_ready",
        "cmp edx, -1",
        "jne interp_slow",
    )
    label("interp_this_ready")
    emit("inc r12")
    dup_value()

    # Slots retain QuickJS ownership. Stores whose old value is referenced go
    # to the original C opcode before modifying anything (finalizer ordering).
    def slot(name, base, action, index=None, width=0, checked=False):
        op(name)
        if index is None:
            emit(f"movzx ecx, {'WORD' if width == 2 else 'BYTE'} PTR [r12+1]")
            emit("shl rcx, 4", f"lea r8, [{base}+rcx]")
        else:
            emit(f"lea r8, [{base}+{index * 16}]")
        if base == "r11":
            raise AssertionError("closure slots have a separate resolver")
        size = 1 + width
        slot_body(action, size, checked)

    def slot_body(action, size, checked=False):
        if action == "get":
            emit("mov rax, QWORD PTR [r8]", "mov rdx, QWORD PTR [r8+8]")
            if checked:
                emit("cmp edx, 4", "je interp_slow")
            emit(f"add r12, {size}")
            dup_value(borrow_field=True)
        else:
            target = "interp_ref_store_" + str(len(reference_stores))
            reference_stores.append((target, action, size))
            emit(
                "cmp DWORD PTR [r8+8], 0",
                "jl " + target
                if internal_entry
                and (not foundation_only or linux_reference_stores or win64_native)
                else "jl interp_slow",
            )
            emit("mov rax, QWORD PTR [r13-16]", "mov rdx, QWORD PTR [r13-8]")
            if action == "set":
                emit("test edx, edx", f"jns interp_set_noref_{len(code)}")
                done = code[-1].split()[-1]
                emit(f"inc DWORD PTR [rax{rc:+d}]")
                label(done)
            emit("mov QWORD PTR [r8], rax", "mov QWORD PTR [r8+8], rdx")
            if action == "put":
                emit("sub r13, 16")
            next_(size)

    for kind, base in [("loc", "r14"), ("arg", "r15")]:
        for action in ("get", "put", "set"):
            for i in range(4):
                slot(f"{action}_{kind}{i}", base, action, index=i)
            slot(f"{action}_{kind}", base, action, width=2)
            if kind == "loc":
                slot(f"{action}_loc8", base, action, width=1)
    slot("get_loc_check", "r14", "get", width=2, checked=True)
    op("set_loc_uninitialized")
    emit(
        "movzx ecx, WORD PTR [r12+1]",
        "shl rcx, 4",
        "lea r8, [r14+rcx]",
        "cmp DWORD PTR [r8+8], 0",
        "jl interp_slow",
        "mov QWORD PTR [r8], 0",
        "mov QWORD PTR [r8+8], 4",
    )
    next_(3)
    for name, initial in [("put_loc_check", False), ("put_loc_check_init", True)]:
        op(name)
        emit(
            "movzx ecx, WORD PTR [r12+1]",
            "shl rcx, 4",
            "lea r8, [r14+rcx]",
            "cmp DWORD PTR [r8+8], 4",
            ("jne" if initial else "je") + " interp_slow",
        )
        slot_body("put", 3)
    op("get_loc0_loc1")
    for index in (0, 1):
        emit(
            f"mov rax, QWORD PTR [r14+{index * 16}]",
            f"mov rdx, QWORD PTR [r14+{index * 16 + 8}]",
            "test edx, edx",
            f"jns interp_get_loc_pair_{index}",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label(f"interp_get_loc_pair_{index}")
        emit("mov QWORD PTR [r13], rax", "mov QWORD PTR [r13+8], rdx", "add r13, 16")
    next_()
    for action in ("get", "put", "set"):
        for index in [0, 1, 2, 3, None]:
            name = f"{action}_var_ref" + (str(index) if index is not None else "")
            op(name)
            if index is None:
                emit("movzx ecx, WORD PTR [r12+1]")
            else:
                emit(f"mov ecx, {index}")
            emit(
                "mov r8, QWORD PTR [rbp+8]",
                f"mov r8, QWORD PTR [r8+{obj_refs}]",
                "mov r8, QWORD PTR [r8+rcx*8]",
                f"mov r8, QWORD PTR [r8+{ref_value}]",
            )
            slot_body(action, 3 if index is None else 1)
    op("get_var_ref_check")
    emit(
        "movzx ecx, WORD PTR [r12+1]",
        "mov r8, QWORD PTR [rbp+8]",
        f"mov r8, QWORD PTR [r8+{obj_refs}]",
        "mov r8, QWORD PTR [r8+rcx*8]",
        f"mov r8, QWORD PTR [r8+{ref_value}]",
    )
    slot_body("get", 3, checked=True)

    # Read live global/own data properties without entering the C opcode step.
    # No cached object/shape/slot survives a call, mutation or address recycling.
    def own_property(prefix, absent, writable=False, slow="interp_slow"):
        emit(f"mov r10, QWORD PTR [r8+{obj_shape}]")
        if has_prefix:
            # 0.17 stores the hash buckets inside the shape allocation.
            emit(
                "mov ecx, DWORD PTR [r10+24]",
                "lea r11, [r10+rcx*4+60]",
                "inc ecx",
                "mov edx, r9d",
                "mov rax, 7046029254386353131",
                "imul rdx, rax",
                "shr rdx, 32",
                "imul rdx, rcx",
                "shr rdx, 32",
                "neg rdx",
                "mov ecx, DWORD PTR [r11+rdx*4-4]",
            )
        else:
            # Exact 0.15.1 find_own_property1: atom & mask, buckets before sh,
            # followed by the original flexible property array after sh.
            emit(
                f"mov ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
                "mov edx, r9d",
                "and edx, ecx",
                "neg rdx",
                "mov ecx, DWORD PTR [r10+rdx*4-4]",
                f"lea r11, [r10+{fields['JSShape.prop']}]",
            )
        label(prefix + "_probe")
        emit(
            "test ecx, ecx",
            "jz " + absent,
            "lea rax, [r11+rcx*8-8]",
            "cmp DWORD PTR [rax+4], r9d",
            "je " + prefix + "_found",
            "mov ecx, DWORD PTR [rax]",
            "and ecx, 67108863",
            "jmp " + prefix + "_probe",
        )
        label(prefix + "_found")
        if writable:
            # JSShapeProperty packs six flags above its 26-bit hash link.
            emit(
                "mov edx, DWORD PTR [rax]",
                "and edx, 3892314112",
                "cmp edx, 134217728",
                "jne " + slow,
            )
        else:
            emit("test DWORD PTR [rax], 3221225472", "jnz " + slow)
        emit(
            "dec ecx",
            "shl rcx, 4",
            f"mov r10, QWORD PTR [r8+{obj_props}]",
            "add r10, rcx",
            "mov rax, QWORD PTR [r10]",
            "mov rdx, QWORD PTR [r10+8]",
        )

    for name in ("get_var", "get_var_undef"):
        op(name)
        if binding_index:
            from property_ic_native import global_cell_probe

            emit(
                *global_cell_probe(
                    layout, "interp_" + name, "interp_" + name + "_ready", "interp_slow"
                )
            )
        emit("mov r9d, DWORD PTR [r12+1]", f"mov r8, QWORD PTR [rsi+{ctx_lexical}]")
        own_property("interp_" + name + "_lex", "interp_" + name + "_global")
        emit("cmp edx, 4", "je interp_slow", "jmp interp_" + name + "_ready")
        label("interp_" + name + "_global")
        emit(f"mov r8, QWORD PTR [rsi+{ctx_global}]")
        own_property("interp_" + name + "_obj", "interp_slow")
        label("interp_" + name + "_ready")
        emit("add r12, 5", "mov QWORD PTR [rbp+48], r12")
        dup_value()
    for name in ("get_field", "get_field2"):
        op(name)
        slow = "interp_property_slow_" + name
        emit("cmp DWORD PTR [r13-8], -1", "jne " + slow, "mov r8, QWORD PTR [r13-16]")
        if name == "get_field":
            emit(f"cmp DWORD PTR [r8{rc:+d}], 1", "jle " + slow)
        emit("mov r9d, DWORD PTR [r12+1]")
        own_property("interp_" + name + "_obj", slow, slow=slow)
        emit("test edx, edx", "jns interp_" + name + "_noref", f"inc DWORD PTR [rax{rc:+d}]")
        label("interp_" + name + "_noref")
        if name == "get_field":
            emit(
                f"dec DWORD PTR [r8{rc:+d}]",
                "mov QWORD PTR [r13-16], rax",
                "mov QWORD PTR [r13-8], rdx",
            )
            next_(5)
        else:
            emit("add r12, 5", "jmp interp_push_value")
    op("put_field")
    emit(
        "cmp DWORD PTR [r13-24], -1",
        "jne interp_property_slow_put_field",
        "mov r8, QWORD PTR [r13-32]",
        f"cmp DWORD PTR [r8{rc:+d}], 1",
        "jle interp_property_slow_put_field",
        "mov r9d, DWORD PTR [r12+1]",
    )
    own_property(
        "interp_put_field_obj",
        "interp_property_slow_put_field",
        writable=True,
        slow="interp_property_slow_put_field",
    )
    # Referenced old values retain C unless the isolated continuation proves
    # both releases non-final. Unsupported layouts keep the complete C path.
    ref_store = (
        "JS_FramePropertyReferenceStore" if indexed_own else "interp_property_slow_put_field"
    )
    emit(
        "test edx, edx",
        "js " + ref_store,
        "mov rax, QWORD PTR [r13-16]",
        "mov rdx, QWORD PTR [r13-8]",
        "mov QWORD PTR [r10], rax",
        "mov QWORD PTR [r10+8], rdx",
        f"dec DWORD PTR [r8{rc:+d}]",
        "sub r13, 32",
    )
    next_(5)
    # Interp-style indexed loads keep ordinary dense arrays and live Int32Array
    # and integer 8/16/32-bit views in the native activation. Read current count/data:
    # detach/resize updates those fields in the original engine. No conversion,
    # getter, last-reference release or pointer cache is allowed in this path.
    for name in ("get_array_el", "get_array_el2"):
        op(name)
        emit(
            "cmp DWORD PTR [r13-8], 0",
            "jne interp_slow",
            "cmp DWORD PTR [r13-24], -1",
            "jne interp_slow",
            "mov r8, QWORD PTR [r13-32]",
        )
        if name == "get_array_el":
            emit(f"cmp DWORD PTR [r8{rc:+d}], 1", "jle interp_slow")
        indexed_miss = "interp_" + name + "_indexed_own" if emit_indexed_own else "interp_slow"
        emit(
            "mov ecx, DWORD PTR [r13-16]",
            f"cmp ecx, DWORD PTR [r8+{obj_count}]",
            "jae " + indexed_miss,
            f"cmp WORD PTR [r8+{obj_class}], 2",
            "jne interp_" + name + "_typed",
            f"test BYTE PTR [r8+{obj_fast_byte}], {obj_fast_mask}",
            "jz " + indexed_miss,
            "shl rcx, 4",
            f"mov r10, QWORD PTR [r8+{obj_values}]",
            "mov rax, QWORD PTR [r10+rcx]",
            "mov rdx, QWORD PTR [r10+rcx+8]",
            "test edx, edx",
            "jns interp_" + name + "_ready",
            f"inc DWORD PTR [rax{rc:+d}]",
            "jmp interp_" + name + "_ready",
        )
        label("interp_" + name + "_typed")
        emit(f"cmp WORD PTR [r8+{obj_class}], 27", "je interp_" + name + "_typed_int32")
        for class_id, kind in (
            (24, "uint8"),
            (28, "uint32"),
            (23, "int8"),
            (25, "int16"),
            (26, "uint16"),
            (22, "uint8"),
            (33, "float64"),
            (32, "float32"),
        ):
            emit(
                f"cmp WORD PTR [r8+{obj_class}], {class_id}", "je interp_" + name + "_typed_" + kind
            )
        emit("jmp interp_slow")
        label("interp_" + name + "_typed_int32")
        emit(
            f"mov r10, QWORD PTR [r8+{obj_values}]",
            "mov eax, DWORD PTR [r10+rcx*4]",
            "xor edx, edx",
        )
        label("interp_" + name + "_ready")
        if name == "get_array_el":
            emit(
                f"dec DWORD PTR [r8{rc:+d}]",
                "mov QWORD PTR [r13-32], rax",
                "mov QWORD PTR [r13-24], rdx",
                "sub r13, 16",
            )
        else:
            emit("mov QWORD PTR [r13-16], rax", "mov QWORD PTR [r13-8], rdx")
        next_()
        if emit_indexed_own:
            indexed_own_append(name, layout, rc, emit, label, next_)
        # Interp's sign/zero-extending typed loads adapted to NG's owned 16B
        # values. Unlike the retained Interp Uint32 high-half fallback, NG can
        # box its exact uint32 as an inline double without allocation or C.
        for kind, instruction in (
            ("uint8", "movzx eax, BYTE PTR [r10+rcx]"),
            ("int8", "movsx eax, BYTE PTR [r10+rcx]"),
            ("int16", "movsx eax, WORD PTR [r10+rcx*2]"),
            ("uint16", "movzx eax, WORD PTR [r10+rcx*2]"),
        ):
            label("interp_" + name + "_typed_" + kind)
            emit(
                f"mov r10, QWORD PTR [r8+{obj_values}]",
                instruction,
                "xor edx, edx",
                "jmp interp_" + name + "_ready",
            )
        label("interp_" + name + "_typed_uint32")
        emit(
            f"mov r10, QWORD PTR [r8+{obj_values}]",
            "mov eax, DWORD PTR [r10+rcx*4]",
            "test eax, eax",
            "js interp_" + name + "_typed_uint32_double",
            "xor edx, edx",
            "jmp interp_" + name + "_ready",
        )
        label("interp_" + name + "_typed_uint32_double")
        emit("cvtsi2sd xmm0, rax", "movq rax, xmm0", "mov edx, 8", "jmp interp_" + name + "_ready")
        # Append Float32/Float64 typed-array handlers to eq_code (.qjscold) so
        # main_code keeps its compact hot instruction layout.
        saved_code, code = code, cold_stage3
        for float_kind, load_inst in (
            ("float64", "mov rax, QWORD PTR [r10+rcx*8]"),
            ("float32", "cvtss2sd xmm0, DWORD PTR [r10+rcx*4]\nmovq rax, xmm0"),
        ):
            label("interp_" + name + "_typed_" + float_kind)
            emit(f"mov r10, QWORD PTR [r8+{obj_values}]", load_inst, "mov edx, 8")
            if name == "get_array_el":
                emit(
                    f"dec DWORD PTR [r8{rc:+d}]",
                    "mov QWORD PTR [r13-32], rax",
                    "mov QWORD PTR [r13-24], rdx",
                    "sub r13, 16",
                )
            else:
                emit("mov QWORD PTR [r13-16], rax", "mov QWORD PTR [r13-8], rdx")
            next_()
        code = saved_code

    op("put_array_el")
    emit(
        "cmp DWORD PTR [r13-24], 0",
        "jne interp_slow",
        "cmp DWORD PTR [r13-40], -1",
        "jne interp_slow",
        "mov r8, QWORD PTR [r13-48]",
        f"cmp WORD PTR [r8+{obj_class}], 2",
        "jne interp_put_array_el_typed",
        f"test BYTE PTR [r8+{obj_fast_byte}], {obj_fast_mask}",
        "jz " + ("interp_put_array_el_indexed_own" if emit_indexed_own else "interp_slow"),
        f"cmp DWORD PTR [r8{rc:+d}], 1",
        "jle interp_slow",
        "mov ecx, DWORD PTR [r13-32]",
        f"cmp ecx, DWORD PTR [r8+{obj_count}]",
        "jae interp_put_array_append" if array_append_body else "jae interp_slow",
        "shl rcx, 4",
        f"mov r10, QWORD PTR [r8+{obj_values}]",
        "add r10, rcx",
        "cmp DWORD PTR [r10+8], 0",
        "jl interp_slow",
        "mov rax, QWORD PTR [r13-16]",
        "mov rdx, QWORD PTR [r13-8]",
        "mov QWORD PTR [r10], rax",
        "mov QWORD PTR [r10+8], rdx",
        f"dec DWORD PTR [r8{rc:+d}]",
        "sub r13, 48",
    )
    next_()

    if array_append_body:
        saved_code, code = code, cold_stage3
        label("interp_put_array_append")
        emit("cmp ecx, 2147483647", "jae interp_slow")
        emit(
            *array_append_body(
                "interp_put_array_append", "interp_slow", layout=layout, runtime_control=False
            )
        )
        code = saved_code

    label("interp_put_array_el_typed")
    # An int already satisfies ToInt32, so it cannot coerce/reenter/detach.
    # Keep the original immutable-buffer check and read current bounds/data.
    emit(f"cmp WORD PTR [r8+{obj_class}], 27", "je interp_put_array_el_typed_int32")
    for class_id, kind in (
        (24, "8"),
        (28, "int32"),
        (23, "8"),
        (25, "16"),
        (26, "16"),
        (33, "float64"),
        (32, "float32"),
    ):
        emit(f"cmp WORD PTR [r8+{obj_class}], {class_id}", "je interp_put_array_el_typed_" + kind)
    emit("jmp interp_slow")

    def typed_store_body():
        # Non-final receiver, mutable backing storage and fresh in-bounds data.
        emit(
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle interp_slow",
            f"mov r10, QWORD PTR [r8+{obj_typed}]",
            "mov r10, QWORD PTR [r10+24]",
            f"mov r10, QWORD PTR [r10+{obj_buffer}]",
            "cmp BYTE PTR [r10+9], 0",
            "jne interp_slow",
            "mov ecx, DWORD PTR [r13-32]",
            f"cmp ecx, DWORD PTR [r8+{obj_count}]",
            "jae interp_slow",
            f"mov r10, QWORD PTR [r8+{obj_values}]",
        )

    def typed_store_guards():
        # Only pre-converted int RHS for integer views. Every other case retains C.
        emit("cmp DWORD PTR [r13-8], 0", "jne interp_slow")
        typed_store_body()
        emit("mov eax, DWORD PTR [r13-16]")

    label("interp_put_array_el_typed_int32")
    typed_store_guards()
    emit("mov DWORD PTR [r10+rcx*4], eax", f"dec DWORD PTR [r8{rc:+d}]", "sub r13, 48")
    next_()

    if emit_indexed_own:
        indexed_own_append("put_array_el", layout, rc, emit, label, next_)
    for width, store in ((8, "mov BYTE PTR [r10+rcx], al"), (16, "mov WORD PTR [r10+rcx*2], ax")):
        label("interp_put_array_el_typed_" + str(width))
        typed_store_guards()
        emit(store, f"dec DWORD PTR [r8{rc:+d}]", "sub r13, 48")
        next_()
    saved_code, code = code, cold_stage3
    for kind, store_inst in (
        ("float64", "movq QWORD PTR [r10+rcx*8], xmm0"),
        ("float32", "cvtsd2ss xmm0, xmm0\nmovss DWORD PTR [r10+rcx*4], xmm0"),
    ):
        lbl_int = "interp_put_array_el_typed_" + kind + "_int"
        lbl_chk = "interp_put_array_el_typed_" + kind + "_chk"
        label("interp_put_array_el_typed_" + kind)
        emit(
            "cmp DWORD PTR [r13-8], 0",
            "je " + lbl_int,
            "cmp DWORD PTR [r13-8], 8",
            "jne interp_slow",
            "movq xmm0, QWORD PTR [r13-16]",
            "jmp " + lbl_chk,
        )
        label(lbl_int)
        emit("cvtsi2sd xmm0, DWORD PTR [r13-16]")
        label(lbl_chk)
        typed_store_body()
        emit(store_inst, f"dec DWORD PTR [r8{rc:+d}]", "sub r13, 48")
        next_()
    code = saved_code

    # Stack movement. More complex permutations retain the C semantics.
    op("dup")
    emit("mov rax, QWORD PTR [r13-16]", "mov rdx, QWORD PTR [r13-8]", "inc r12")
    dup_value()
    op("drop")
    emit("cmp DWORD PTR [r13-8], 0", "jl interp_property_slow_drop", "sub r13, 16")
    next_()
    op("swap")
    emit(
        "movdqu xmm0, XMMWORD PTR [r13-32]",
        "movdqu xmm1, XMMWORD PTR [r13-16]",
        "movdqu XMMWORD PTR [r13-16], xmm0",
        "movdqu XMMWORD PTR [r13-32], xmm1",
    )
    next_()

    # Interp-style numeric cases: int/int stays compact; doubles and mixed
    # int/double run in SSE2. Coercion exits before operand/PC mutation.
    def number_to_xmm(prefix, payload, tag, xmm, slow="interp_slow"):
        emit(
            f"cmp DWORD PTR [{tag}], 0",
            "je " + prefix + "_int",
            f"cmp DWORD PTR [{tag}], 8",
            "jne " + slow,
            f"movq {xmm}, QWORD PTR [{payload}]",
            "jmp " + prefix + "_ready",
        )
        label(prefix + "_int")
        emit(f"cvtsi2sd {xmm}, DWORD PTR [{payload}]")
        label(prefix + "_ready")

    for name, inst in [
        ("add", "add"),
        ("sub", "sub"),
        ("mul", "imul"),
        ("and", "and"),
        ("or", "or"),
        ("xor", "xor"),
    ]:
        op(name)
        numeric = name in ("add", "sub", "mul")
        fallback = "interp_" + name + "_number" if numeric else "interp_slow"
        emit(
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz " + fallback,
            "mov eax, DWORD PTR [r13-32]",
            f"{inst} eax, DWORD PTR [r13-16]",
        )
        if numeric:
            emit("jo " + fallback)
        if name == "mul":
            # A negative operand multiplied by zero produces IEEE -0.
            emit(
                "test eax, eax",
                "jnz interp_mul_store",
                "mov ecx, DWORD PTR [r13-32]",
                "or ecx, DWORD PTR [r13-16]",
                "js " + fallback,
            )
            label("interp_mul_store")
        emit("mov QWORD PTR [r13-32], rax", "sub r13, 16")
        next_()
        if numeric:
            label(fallback)
            # Preserve this established instruction stream. Only the two
            # existing non-number branch targets change for add/mul.
            slow = (
                "interp_short_big_" + name if name in ("add", "mul") else "interp_op_slow_" + name
            )
            number_to_xmm("interp_" + name + "_lhs", "r13-32", "r13-24", "xmm0", slow)
            number_to_xmm("interp_" + name + "_rhs", "r13-16", "r13-8", "xmm1", slow)
            emit(
                name + "sd xmm0, xmm1",
                "movq QWORD PTR [r13-32], xmm0",
                "mov QWORD PTR [r13-24], 8",
                "sub r13, 16",
            )
            next_()
    op("add_loc")
    emit(
        "movzx ecx, BYTE PTR [r12+1]",
        "shl rcx, 4",
        "lea r8, [r14+rcx]",
        "mov eax, DWORD PTR [r8+8]",
        "or eax, DWORD PTR [r13-8]",
        "jnz interp_add_loc_number",
        "mov eax, DWORD PTR [r8]",
        "add eax, DWORD PTR [r13-16]",
        "jo interp_add_loc_number",
        "mov QWORD PTR [r8], rax",
        "sub r13, 16",
    )
    next_(2)
    label("interp_add_loc_number")
    add_local_slow = (
        "JS_FrameAddLocalBigCold" if internal_entry and not foundation_only else "interp_slow"
    )
    number_to_xmm("interp_add_loc_lhs", "r8", "r8+8", "xmm0", add_local_slow)
    number_to_xmm("interp_add_loc_rhs", "r13-16", "r13-8", "xmm1", add_local_slow)
    emit("addsd xmm0, xmm1", "movq QWORD PTR [r8], xmm0", "mov QWORD PTR [r8+8], 8", "sub r13, 16")
    next_(2)
    op("mod")
    emit(
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz interp_op_slow_mod",
        "mov ecx, DWORD PTR [r13-16]",
        "test ecx, ecx",
        "jz interp_op_slow_mod",
        "mov eax, DWORD PTR [r13-32]",
        "cmp eax, -2147483648",
        "je interp_op_slow_mod",
        "mov r8d, eax",
        "cdq",
        "idiv ecx",
        "test edx, edx",
        "jnz interp_mod_store",
        "test r8d, r8d",
        "js interp_op_slow_mod",
    )
    label("interp_mod_store")
    emit("mov eax, edx", "mov QWORD PTR [r13-32], rax", "sub r13, 16")
    next_()

    def emit_rel_xmm_compare(name):
        emit("xor eax, eax", "ucomisd xmm0, xmm1")
        if name in ("lt", "lte"):
            emit(("setb" if name == "lt" else "setbe") + " al", "setnp dl", "and al, dl")
        else:
            emit(("seta" if name == "gt" else "setae") + " al")
        emit("mov QWORD PTR [r13-32], rax", "mov QWORD PTR [r13-24], 1", "sub r13, 16")
        next_()

    number_compare_paths = []
    for name, cc in [
        ("lt", "l"),
        ("lte", "le"),
        ("gt", "g"),
        ("gte", "ge"),
        ("eq", "e"),
        ("neq", "ne"),
        ("strict_eq", "e"),
        ("strict_neq", "ne"),
    ]:
        op(name)
        is_rel = name in ("lt", "lte", "gt", "gte")
        miss = (
            "interp_primitive_" + name
            if name in ("strict_eq", "strict_neq")
            else "interp_op_slow_" + name
        )
        number_compare_paths.append((name, miss))
        if numeric_compare and name not in ("strict_eq", "strict_neq"):
            target = "interp_number_compare_" + name
        elif is_rel:
            target = "interp_rel_compare_" + name
        else:
            target = miss
        emit(
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz " + target,
            "mov ecx, DWORD PTR [r13-32]",
            "xor eax, eax",
            "cmp ecx, DWORD PTR [r13-16]",
            f"set{cc} al",
            "mov QWORD PTR [r13-32], rax",
            "mov QWORD PTR [r13-24], 1",
            "sub r13, 16",
        )
        next_()

    saved_code, code = code, cold_stage3
    if not numeric_compare:
        for name in ("lt", "lte", "gt", "gte"):
            prefix = "interp_rel_compare_" + name
            rel_str = "interp_rel_str_" + name
            label(prefix)
            number_to_xmm(prefix + "_lhs", "r13-32", "r13-24", "xmm0", rel_str)
            number_to_xmm(prefix + "_rhs", "r13-16", "r13-8", "xmm1", rel_str)
            emit_rel_xmm_compare(name)

    for rel_idx, name in enumerate(("lt", "lte", "gt", "gte")):
        label("interp_rel_str_" + name)
        emit(f"mov r11d, {rel_idx}", "jmp interp_rel_str_common")

    label("interp_rel_str_common")
    emit(
        "cmp DWORD PTR [r13-24], -7",
        "jne interp_rel_str_slow",
        "cmp DWORD PTR [r13-8], -7",
        "jne interp_rel_str_slow",
        "mov r8, QWORD PTR [r13-32]",
        "mov r9, QWORD PTR [r13-16]",
        "cmp r8, r9",
        "jne interp_rel_str_distinct",
        f"cmp DWORD PTR [r8{rc:+d}], 2",
        "jle interp_rel_str_slow",
        "mov eax, r11d",
        "and eax, 1",
        "jmp interp_rel_str_commit",
    )
    label("interp_rel_str_distinct")
    emit(
        f"cmp DWORD PTR [r8{rc:+d}], 1",
        "jle interp_rel_str_slow",
        f"cmp DWORD PTR [r9{rc:+d}], 1",
        "jle interp_rel_str_slow",
        f"mov ecx, DWORD PTR [r8+{string_len_byte}]",
        "test ecx, ecx",
        "js interp_rel_str_slow",
        f"mov edx, DWORD PTR [r9+{string_len_byte}]",
        "test edx, edx",
        "js interp_rel_str_slow",
        f"mov eax, DWORD PTR [r8+{string_hash}]",
        "shr eax, 28",
        "and eax, 3",
        "jnz interp_rel_str_slow",
        f"mov eax, DWORD PTR [r9+{string_hash}]",
        "shr eax, 28",
        "and eax, 3",
        "jnz interp_rel_str_slow",
        "cmp ecx, edx",
        "ja interp_rel_str_len_gt",
        "jb interp_rel_str_len_lt",
        "mov eax, r11d",
        "and eax, 1",
        "jmp interp_rel_str_tie_ready",
    )
    label("interp_rel_str_len_gt")
    emit("mov eax, r11d", "shr eax, 1", "and eax, 1", "jmp interp_rel_str_tie_ready")
    label("interp_rel_str_len_lt")
    emit("mov eax, r11d", "shr eax, 1", "and eax, 1", "xor eax, 1")
    label("interp_rel_str_tie_ready")
    emit(
        "shl eax, 8",
        "or r11d, eax",
        "mov eax, ecx",
        "cmp eax, edx",
        "cmova eax, edx",
        "xor r10d, r10d",
        "test eax, eax",
        "jz interp_rel_str_prefix_eq",
    )
    label("interp_rel_str_byte_loop")
    emit(
        f"mov cl, BYTE PTR [r8+r10+{string_size}]",
        f"mov dl, BYTE PTR [r9+r10+{string_size}]",
        "cmp cl, dl",
        "jne interp_rel_str_diff",
        "inc r10",
        "cmp r10d, eax",
        "jb interp_rel_str_byte_loop",
    )
    label("interp_rel_str_prefix_eq")
    emit("mov eax, r11d", "shr eax, 8", "jmp interp_rel_str_commit")
    label("interp_rel_str_diff")
    emit(
        "setb al",
        "movzx eax, al",
        "shr r11d, 1",
        "and r11d, 1",
        "xor eax, r11d",
    )
    label("interp_rel_str_commit")
    emit(
        f"dec DWORD PTR [r8{rc:+d}]",
        f"dec DWORD PTR [r9{rc:+d}]",
        "mov QWORD PTR [r13-32], rax",
        "mov QWORD PTR [r13-24], 1",
        "sub r13, 16",
    )
    next_()
    label("interp_rel_str_slow")
    emit(
        "cmp r11d, 0",
        "je interp_op_slow_lt",
        "cmp r11d, 1",
        "je interp_op_slow_lte",
        "cmp r11d, 2",
        "je interp_op_slow_gt",
        "jmp interp_op_slow_gte",
    )
    code = saved_code

    for name, instruction in [("shl", "shl"), ("shr", "shr"), ("sar", "sar")]:
        op(name)
        emit(
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz interp_slow",
            "mov eax, DWORD PTR [r13-32]",
            "mov ecx, DWORD PTR [r13-16]",
            f"{instruction} eax, cl",
        )
        if name == "shr":
            emit("test eax, eax", "js interp_slow")
        emit("mov QWORD PTR [r13-32], rax", "sub r13, 16")
        next_()
    for name, inst in [("inc_loc", "add"), ("dec_loc", "sub")]:
        op(name)
        emit(
            "movzx ecx, BYTE PTR [r12+1]",
            "shl rcx, 4",
            "lea r8, [r14+rcx]",
            "cmp DWORD PTR [r8+8], 0",
            "jne interp_slow",
            "mov eax, DWORD PTR [r8]",
            f"{inst} eax, 1",
            "jo interp_slow",
            "mov QWORD PTR [r8], rax",
        )
        next_(2)
    for name in ("inc", "dec", "not", "neg"):
        op(name)
        emit("cmp DWORD PTR [r13-8], 0", "jne interp_slow", "mov eax, DWORD PTR [r13-16]")
        if name == "not":
            emit("not eax")
        elif name == "neg":
            emit("test eax, eax", "jz interp_slow", "neg eax", "jo interp_slow")
        else:
            emit(("add" if name == "inc" else "sub") + " eax, 1", "jo interp_slow")
        emit("mov QWORD PTR [r13-16], rax")
        next_()
    for name, inst in [("post_inc", "add"), ("post_dec", "sub")]:
        op(name)
        emit(
            "cmp DWORD PTR [r13-8], 0",
            "jne interp_slow",
            "mov eax, DWORD PTR [r13-16]",
            f"{inst} eax, 1",
            "jo interp_slow",
            "xor edx, edx",
            "inc r12",
            "jmp interp_push_value",
        )
    for name, tag in [("is_undefined", 3), ("is_null", 2), ("is_undefined_or_null", None)]:
        op(name)
        emit(
            "cmp DWORD PTR [r13-8], 0",
            "jge interp_" + name + "_primitive",
            "mov rax, QWORD PTR [r13-16]",
            f"cmp DWORD PTR [rax{rc:+d}], 1",
            "jle interp_slow",
            f"dec DWORD PTR [rax{rc:+d}]",
        )
        label("interp_" + name + "_primitive")
        emit("xor eax, eax")
        if tag is None:
            emit("mov ecx, DWORD PTR [r13-8]", "sub ecx, 2", "cmp ecx, 1", "setbe al")
        else:
            emit(f"cmp DWORD PTR [r13-8], {tag}", "sete al")
        emit("mov QWORD PTR [r13-16], rax", "mov QWORD PTR [r13-8], 1")
        next_()
    for name in ("to_propkey", "to_propkey2"):
        op(name)
        if name == "to_propkey2":
            emit("mov eax, DWORD PTR [r13-24]", "sub eax, 2", "cmp eax, 1", "jbe interp_slow")
        emit(
            "mov eax, DWORD PTR [r13-8]",
            "test eax, eax",
            "jz interp_" + name + "_ready",
            "cmp eax, -7",
            "je interp_" + name + "_ready",
            "cmp eax, -8",
            "jne interp_slow",
        )
        label("interp_" + name + "_ready")
        next_()
    op("lnot")
    emit(
        "cmp DWORD PTR [r13-8], 3",
        "ja interp_lnot_cold" if win64_native else "ja interp_slow",
        "xor eax, eax",
        "cmp DWORD PTR [r13-16], 0",
        "sete al",
        "mov QWORD PTR [r13-16], rax",
        "mov QWORD PTR [r13-8], 1",
    )
    next_()

    # Match the original interrupt polling frequency; an expired counter exits
    # before modifying the instruction so C performs precisely one poll.
    for name, width in [
        ("goto", 4),
        ("goto16", 2),
        ("goto8", 1),
        ("if_true", 4),
        ("if_false", 4),
        ("if_true8", 1),
        ("if_false8", 1),
    ]:
        op(name)
        emit(f"cmp DWORD PTR [rsi+{ctx_poll}], 1", "jle interp_slow")
        if name.startswith("if"):
            emit(
                "cmp DWORD PTR [r13-8], 3",
                ("ja interp_" + name + "_cold") if win64_native else "ja interp_slow",
                "mov eax, DWORD PTR [r13-16]",
                "sub r13, 16",
            )
        emit(f"dec DWORD PTR [rsi+{ctx_poll}]")
        if name.startswith("if"):
            emit(
                "test eax, eax",
                ("jz" if "true" in name else "jnz") + " interp_" + name + "_untaken",
            )
        if width == 4:
            emit("movsxd rax, DWORD PTR [r12+1]")
        else:
            emit(f"movsx rax, {'WORD' if width == 2 else 'BYTE'} PTR [r12+1]")
        emit("lea r12, [r12+rax+1]", "jmp interp_dispatch")
        if name.startswith("if"):
            label("interp_" + name + "_untaken")
            next_(1 + width)

    # Internal ABI: RBX state, RBP frame, R12 PC, R13 operand top,
    # R14 locals, R15 arguments, RSI realm, RDI dispatch. No native call stack
    # growth per JS call; common frames are allocated directly in the arena.
    call_start = len(code)
    for name in (
        "call0",
        "call1",
        "call2",
        "call3",
        "call",
        "tail_call",
        "call_method",
        "tail_call_method",
    ):
        op(name)
        method = name.endswith("method")
        tail = name.startswith("tail")
        size = 1 if name[-1].isdigit() else 3
        if size == 1:
            emit(f"mov ecx, {int(name[-1])}")
        else:
            emit("movzx ecx, WORD PTR [r12+1]")
        emit(
            f"mov DWORD PTR [rsp+48], {int(method)}",
            f"mov DWORD PTR [rsp+52], {0x8000 if tail else 0}",
            f"mov DWORD PTR [rsp+56], {size}",
            "jmp interp_prepare_call",
        )
    label("interp_prepare_call")
    emit(
        "mov r8, rcx",
        "shl r8, 4",
        "neg r8",
        "add r8, r13",
        "cmp DWORD PTR [r8-8], -1",
        "jne interp_slow",
        "mov rdx, QWORD PTR [r8-16]",
        f"cmp WORD PTR [rdx+{obj_class}], 13",
        "jne interp_host_call",
        f"mov r9, QWORD PTR [rdx+{obj_bytecode}]",
        f"test BYTE PTR [r9+{bc_kind}], 1",
        "jz interp_slow",
        # Captured arguments own copies; their indirect writes/lifetime are
        # handled by the C push, while captured locals can use a native frame.
        f"test BYTE PTR [r9+{bc_kind}], 4",
        "jnz interp_slow",
        f"movzx eax, WORD PTR [r9+{bc_args}]",
        "cmp ecx, eax",
        "jae interp_call_arity_ok",
        "cmp WORD PTR [rbp+56], 0",
        "jne interp_slow",
        f"test BYTE PTR [r9+{bc_kind}], 2",
        "jz interp_slow",
        "shl rax, 4",
        "add rax, r8",
        "mov r10d, DWORD PTR [rbp+120]",
        "add r10, rbp",
        "cmp rax, r10",
        "ja interp_slow",
    )
    label("interp_call_arity_ok")
    emit(
        f"movzx eax, WORD PTR [r9+{bc_vars}]",
        f"movzx r10d, WORD PTR [r9+{bc_stack}]",
        "add eax, r10d",
        "shl rax, 4",
        "add rax, 128",
        f"test BYTE PTR [r9+{bc_kind}], 8",
        "jnz interp_call_capture_size",
    )
    label("interp_call_size_ready")
    emit(
        "mov r11, QWORD PTR [rbx+8]",
        "mov r10, QWORD PTR [r11+16]",
        "add r10, rax",
        "cmp r10, QWORD PTR [r11+8]",
        "ja interp_slow",
        "mov r10, QWORD PTR [rbx+32]",
        "add r10, rax",
        "mov QWORD PTR [rsp+32], rax",
        "mov rax, rsp",
        "sub rax, r10",
        (
            f"mov r10, QWORD PTR [rbx+{native_limit_offset}]"
            if internal_entry
            else "mov r10, QWORD PTR [rbx+56]"
        ),
        ("cmp rax, r10" if internal_entry else f"cmp rax, QWORD PTR [r10+{rt_limit}]"),
        "jb interp_slow",
        f"cmp DWORD PTR [rsi+{ctx_poll}], 1",
        "jle interp_slow",
        f"dec DWORD PTR [rsi+{ctx_poll}]",
        # Commit only after every slow guard; no cache hint is dereferenced.
        "mov eax, DWORD PTR [rsp+56]",
        "add r12, rax",
        "mov QWORD PTR [rbp+48], r12",
        "mov QWORD PTR [rbp+104], r13",
        "mov eax, DWORD PTR [rsp+48]",
        "lea eax, [rax+rcx+1]",
        "or eax, DWORD PTR [rsp+52]",
        "mov WORD PTR [rbp+126], ax",
        "mov r10, QWORD PTR [r11+16]",
        "mov rax, QWORD PTR [r11+24]",
        "add rax, r10",
        "mov r10, QWORD PTR [rsp+32]",
        "mov DWORD PTR [rax+120], r10d",
        "add QWORD PTR [r11+16], r10",
        "add QWORD PTR [rbx+32], r10",
        "mov QWORD PTR [rax+112], r11",
        "mov QWORD PTR [rax], rbp",
        "mov QWORD PTR [rax+8], rdx",
        "mov QWORD PTR [rax+16], -1",
        "mov QWORD PTR [rax+80], r9",
        "mov QWORD PTR [rax+24], r8",
        "lea r14, [rax+128]",
        "mov QWORD PTR [rax+32], r14",
        "mov QWORD PTR [rax+40], 0",
        "mov QWORD PTR [rax+48], 0",
        "mov QWORD PTR [rax+56], 0",
        "mov QWORD PTR [rax+64], 0",
        "mov QWORD PTR [rax+72], 0",
        "mov DWORD PTR [rax+124], 0",
        f"movzx edx, WORD PTR [r9+{bc_args}]",
        "cmp edx, ecx",
        "cmovb edx, ecx",
        "mov WORD PTR [rax+58], dx",
        f"movzx edx, BYTE PTR [r9+{bc_bits}]",
        "and edx, 1",
        "mov BYTE PTR [rax+60], dl",
        "xor edx, edx",
        "mov QWORD PTR [rax+88], rdx",
        "mov QWORD PTR [rax+96], 3",
        "cmp DWORD PTR [rsp+48], 0",
        "je interp_call_this_done",
        "movdqu xmm0, XMMWORD PTR [r8-32]",
        "movdqu XMMWORD PTR [rax+88], xmm0",
    )
    label("interp_call_this_done")
    if diagnostics:
        emit(
            "inc QWORD PTR [rbx+64]",
            "inc QWORD PTR [rbx+88]",
            "inc DWORD PTR [rbx+128]",
            "mov edx, DWORD PTR [rbx+128]",
            "cmp edx, DWORD PTR [rbx+132]",
            "jbe interp_call_depth_ok",
            "mov DWORD PTR [rbx+132], edx",
        )
        label("interp_call_depth_ok")
        emit(
            "mov rdx, QWORD PTR [rbx+32]",
            "cmp rdx, QWORD PTR [rbx+120]",
            "jbe interp_call_peak_ok",
            "mov QWORD PTR [rbx+120], rdx",
        )
        label("interp_call_peak_ok")
    emit(
        "mov rbp, rax",
        "mov r15, r8",
        "mov r10, QWORD PTR [rbx+56]",
        f"mov QWORD PTR [r10+{rt_frame}], rbp",
    )
    emit(f"movzx edx, WORD PTR [r9+{bc_args}]", "cmp ecx, edx", "jae interp_call_pad_done")
    if diagnostics:
        emit(
            "inc QWORD PTR [rbx+96]",
            "inc QWORD PTR [rbx+112]",
            "inc QWORD PTR [rbx+136]",
            "add QWORD PTR [rbx+104], rcx",
        )
        emit(
            "mov rax, QWORD PTR [rbp]",
            "mov rax, QWORD PTR [rax+112]",
            "cmp rax, QWORD PTR [rbx+8]",
            "je interp_call_window_owner_ok",
            "inc QWORD PTR [rbx+2248]",
        )
        label("interp_call_window_owner_ok")
    emit("shl rcx, 4", "lea r8, [r15+rcx]", "shl rdx, 4", "add rdx, r15")
    label("interp_call_pad_loop")
    emit(
        "mov QWORD PTR [r8], 0",
        "mov QWORD PTR [r8+8], 3",
        "add r8, 16",
        "cmp r8, rdx",
        "jb interp_call_pad_loop",
    )
    label("interp_call_pad_done")
    emit(
        f"movzx ecx, WORD PTR [r9+{bc_vars}]",
        "mov r13, r14",
        "test ecx, ecx",
        "jz interp_call_locals_done",
    )
    label("interp_call_locals_loop")
    emit(
        "mov QWORD PTR [r13], 0",
        "mov QWORD PTR [r13+8], 3",
        "add r13, 16",
        "dec ecx",
        "jnz interp_call_locals_loop",
    )
    label("interp_call_locals_done")
    # Keep the original var-ref table in this stable data frame, beyond the
    # declared operand stack. Only capturing frames reserve/initialize it.
    emit(
        f"test BYTE PTR [r9+{bc_kind}], 8",
        "jz interp_call_refs_done",
        f"movzx ecx, WORD PTR [r9+{bc_refs}]",
        "mov WORD PTR [rbp+56], cx",
        f"movzx edx, WORD PTR [r9+{bc_stack}]",
        "shl rdx, 4",
        "lea r8, [r13+rdx]",
        "mov QWORD PTR [rbp+40], r8",
    )
    label("interp_call_refs_loop")
    emit("mov QWORD PTR [r8], 0", "add r8, 8", "dec ecx", "jnz interp_call_refs_loop")
    label("interp_call_refs_done")
    emit(
        f"mov r12, QWORD PTR [r9+{bc_code}]",
        f"mov rsi, QWORD PTR [r9+{bc_realm}]",
        "jmp interp_dispatch",
    )
    call_end = len(code)

    label("interp_host_call")
    emit(
        "mov eax, DWORD PTR [rsp+56]",
        "add r12, rax",
        "mov QWORD PTR [rbp+48], r12",
        "mov QWORD PTR [rbp+104], r13",
        "mov eax, DWORD PTR [rsp+48]",
        "lea eax, [rax+rcx+1]",
        "or eax, DWORD PTR [rsp+52]",
        "mov WORD PTR [rbp+126], ax",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rdx, r8",
        "mov r8d, ecx",
        "mov r9d, DWORD PTR [rsp+48]",
        "mov rcx, rbx",
    )
    if diagnostics:
        emit("inc QWORD PTR [rbx+2264]")
    emit(
        "call JS_FrameInterpHostDispatch",
        "test eax, eax",
        "jnz interp_host_exception",
        "movdqu xmm0, XMMWORD PTR [rbx+40]",
    )
    if diagnostics:
        emit(f"inc QWORD PTR [rbx+{return_count_offset + 16}]")
    emit(
        "mov r11, QWORD PTR [rbp+104]",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
        "jmp interp_release_values",
    )
    label("interp_host_exception")
    # A tail call's continuation can be one-past-bytecode. Do not read its
    # opcode when the C bridge has already supplied an exception to unwind.
    if diagnostics:
        emit("inc QWORD PTR [rbx+80]")
    emit(
        "mov rcx, rbx",
        "call JS_FrameInterpSlow",
        "mov rbp, QWORD PTR [rbx]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "jmp interp_exit",
    )

    # Interp-style private return ABI: XMM0 owns the full payload/tag until
    # the caller consumes it. Only a C boundary or root return spills it.
    op("return")
    emit("sub r13, 16", "movdqu xmm0, XMMWORD PTR [r13]", "jmp interp_return_frame")
    op("return_undef")
    # The pinned dispatch-table base also addresses the immutable JS_UNDEFINED
    # value after its 256 entries; no temporary result record is needed.
    emit("movdqu xmm0, XMMWORD PTR [rdi+2048]")
    label("interp_return_frame")
    # A root returns to the C boundary, not a JS operand window. Materialize
    # its result before cleanup, retaining f33's overlap with owned-root
    # decrefs/pop. Ordinary JS returns continue to carry only XMM0.
    emit("cmp BYTE PTR [rbp+62], 0", "je interp_return_value_ready")
    if diagnostics:
        emit(f"inc QWORD PTR [rbx+{return_count_offset}]")
    emit("movdqu XMMWORD PTR [rbx+40], xmm0")
    label("interp_return_value_ready")
    emit(
        "cmp WORD PTR [rbp+56], 0",
        "je interp_return_refs_done",
        "movdqu XMMWORD PTR [rbx+40], xmm0",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameInterpClose",
        "movdqu xmm0, XMMWORD PTR [rbx+40]",
    )
    label("interp_return_refs_done")
    emit(
        "movzx r10d, WORD PTR [rbp+124]",
        "shl r10, 4",
        "neg r10",
        "add r10, QWORD PTR [rbp+32]",
        "mov r11, r13",
        "mov DWORD PTR [rsp+60], 0",
        "jmp interp_release_values",
    )
    label("interp_pop_frame")
    if diagnostics:
        emit("inc QWORD PTR [rbx+72]", "dec DWORD PTR [rbx+128]")
    emit(
        "mov rax, QWORD PTR [rbp+112]",
        "mov rdx, rbp",
        "sub rdx, QWORD PTR [rax+24]",
        "mov QWORD PTR [rax+16], rdx",
        "mov QWORD PTR [rbx+8], rax",
        "mov edx, DWORD PTR [rbp+120]",
        "sub QWORD PTR [rbx+32], rdx",
        "mov r10, QWORD PTR [rbx+56]",
    )
    emit(
        "mov rax, QWORD PTR [rbp]",
        "mov rdx, r10",
        f"mov QWORD PTR [rdx+{rt_frame}], rax",
        "cmp BYTE PTR [rbp+62], 0",
        "jne interp_root_return",
        "mov rbp, rax",
        "mov rax, QWORD PTR [rbp+80]",
        f"mov rsi, QWORD PTR [rax+{bc_realm}]",
        "mov r14, QWORD PTR [rbp+32]",
        "mov r15, QWORD PTR [rbp+24]",
        "mov r12, QWORD PTR [rbp+48]",
        "mov r11, QWORD PTR [rbp+104]",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
        "jmp interp_release_values",
    )
    label("interp_finish_call")
    emit("test WORD PTR [rbp+126], 32768", "jne interp_return_frame")
    if diagnostics:
        emit(f"inc QWORD PTR [rbx+{return_count_offset + 24}]")
    emit(
        "movdqu XMMWORD PTR [r13], xmm0",
        "add r13, 16",
        "mov WORD PTR [rbp+126], 0",
        "jmp interp_dispatch",
    )
    label("interp_release_values")
    emit("cmp r10, r11", "jae interp_release_done")
    label("interp_release_loop")
    emit(
        "cmp DWORD PTR [r10+8], 0",
        "jge interp_release_next",
        "mov rax, QWORD PTR [r10]",
        f"cmp DWORD PTR [rax{rc:+d}], 1",
        "jle interp_release_finalizer",
        f"dec DWORD PTR [rax{rc:+d}]",
        "jmp interp_release_next",
    )
    label("interp_release_finalizer")
    # Win64 XMM0 is volatile. A finalizer may reenter JavaScript, so retain the
    # owned return in this activation's boundary record until C has returned.
    if diagnostics:
        emit(f"inc QWORD PTR [rbx+{return_count_offset + 8}]")
    emit(
        "movdqu XMMWORD PTR [rbx+40], xmm0",
        "mov QWORD PTR [rsp+32], r10",
        "mov QWORD PTR [rsp+40], r11",
    )
    if internal_entry:
        emit("mov rcx, rbx", "mov rdx, rsi", "mov r8, r10", "call JS_FrameInterpFree")
    else:
        emit("mov rcx, rsi", "mov rdx, r10", "call JS_FreeValue")
    emit(
        "movdqu xmm0, XMMWORD PTR [rbx+40]",
        "mov r10, QWORD PTR [rsp+32]",
        "mov r11, QWORD PTR [rsp+40]",
    )
    label("interp_release_next")
    emit("add r10, 16", "cmp r10, r11", "jb interp_release_loop")
    label("interp_release_done")
    emit("cmp DWORD PTR [rsp+60], 0", "je interp_pop_frame", "jmp interp_finish_call")

    # Validated metadata keeps the zero-capture call path linear. This cold
    # continuation preserves the existing table alignment and every slow guard.
    label("interp_call_capture_size")
    emit(
        f"movzx r10d, WORD PTR [r9+{bc_refs}]",
        "shl r10, 3",
        "add r10, 15",
        "and r10, -16",
        "add rax, r10",
        "jmp interp_call_size_ready",
    )

    op("nop")
    next_()
    numeric_ops = (
        "add",
        "sub",
        "mul",
        "div",
        "mod",
        "lt",
        "lte",
        "gt",
        "gte",
        "eq",
        "neq",
        "strict_eq",
        "strict_neq",
    )
    # Division already used a C operation; give it the same explicit boundary.
    op("div")
    emit("jmp interp_op_slow_div")
    for name in numeric_ops:
        label("interp_op_slow_" + name)
        if diagnostics:
            emit("inc QWORD PTR [rbx+80]", f"inc QWORD PTR [rbx+{ids[name] * 8 + 144}]")
        emit(
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov rcx, rbx",
            "call "
            + (
                "JS_FrameInterpAddDirect"
                if name == "add" and internal_entry and not foundation_only
                else ("JS_FrameInterpBig_" if name in ("add", "mul") else "JS_FrameInterpOp_")
                + name
            ),
            "test eax, eax",
            "jz interp_reload",
            "mov rbp, QWORD PTR [rbx]",
            "mov r12, QWORD PTR [rbx+16]",
            "mov r13, QWORD PTR [rbx+24]",
            "jmp interp_exit",
        )
    label("interp_slow")
    if diagnostics:
        emit("inc QWORD PTR [rbx+80]", "movzx eax, BYTE PTR [r12]", "inc QWORD PTR [rbx+rax*8+144]")
    emit(
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameInterpSlow",
        "test eax, eax",
        "jz interp_reload",
        "mov rbp, QWORD PTR [rbx]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "jmp interp_exit",
    )
    property_ops = ("get_field", "get_field2", "put_field", "drop", "call_constructor")
    # New slow entries form a noncontiguous part of this native activation.
    # They must not extend the established main dispatch/return code section.
    main_code, code = code, []
    op("call_constructor")
    emit("jmp interp_property_slow_call_constructor")
    op("check_ctor")
    emit("cmp BYTE PTR [rbp+62], 3", "jne interp_slow")
    next_()
    for name in property_ops:
        label("interp_property_slow_" + name)
        if name == "drop" and win64_native:
            emit(
                "mov rax, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [rax{rc:+d}], 1",
                "jle interp_property_slow_drop_c",
                f"dec DWORD PTR [rax{rc:+d}]",
                "sub r13, 16",
            )
            next_()
            label("interp_property_slow_drop_c")
        if diagnostics:
            emit("inc QWORD PTR [rbx+80]", f"inc QWORD PTR [rbx+{ids[name] * 8 + 144}]")
        emit(
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov rcx, rbx",
            "call JS_FrameInterpProperty_" + name,
            "test eax, eax",
            "jz interp_reload",
            "mov rbp, QWORD PTR [rbx]",
            "mov r12, QWORD PTR [rbx+16]",
            "mov r13, QWORD PTR [rbx+24]",
            "jmp interp_exit",
        )
    cold_code, code = code, []
    # A noncontiguous part of the same VM activation, entered BEFORE spilling
    # state or publishing/refreshing the C boundary. Short values own no heap
    # references. Overflow/type exits leave both operand slots and PC/SP intact.
    for name, instruction in (("add", "add"), ("mul", "imul")):
        label("interp_short_big_" + name)
        slow = "interp_op_slow_" + name
        emit(
            "cmp DWORD PTR [r13-24], 7",
            "jne " + slow,
            "cmp DWORD PTR [r13-8], 7",
            "jne " + slow,
            "mov eax, DWORD PTR [r13-32]",
            instruction + " eax, DWORD PTR [r13-16]",
            "jo " + slow,
            "mov QWORD PTR [r13-32], rax",
            "sub r13, 16",
        )
        next_()
    short_code, code = code, main_code

    # Native equivalent of the pinned insert3 opcode (obj key value ->
    # value obj key value). No user code, allocation or final release is
    # possible; only the duplicated value gains one original JS owner.
    # Keep the established dispatch kernel outside this new cold body.
    stack_insert = (
        internal_entry
        and native_slice
        and not foundation_only
        and not diagnostics
        and not has_prefix
    ) or linux_stack_insert
    if stack_insert:
        code, main_code = [], code
        op("insert3")
        emit(
            "test BYTE PTR [rip+JS_FrameSlowDirectData], 32",
            "jnz interp_slow",
            "cmp DWORD PTR [r13-8], 0",
            "jns interp_insert3_copy",
            "mov rax, QWORD PTR [r13-16]",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label("interp_insert3_copy")
        emit(
            "movdqu xmm0, XMMWORD PTR [r13-16]",
            "movdqu XMMWORD PTR [r13], xmm0",
            "movdqu xmm1, XMMWORD PTR [r13-32]",
            "movdqu XMMWORD PTR [r13-16], xmm1",
            "movdqu xmm1, XMMWORD PTR [r13-48]",
            "movdqu XMMWORD PTR [r13-32], xmm1",
            "movdqu XMMWORD PTR [r13-48], xmm0",
            "add r13, 16",
        )
        next_()
        short_code += code
        code = main_code

    # A separate call kernel uses immutable, function-owned preparation data.
    # Both kernels share the compact frame ABI. Only eight dispatch-table
    # destinations select descriptor preparation; ordinary opcode handlers
    # remain in the isolated native VM section outside the original C core.
    call_code = list(code[call_start:call_end])
    call_labels = {
        row[:-1]: "interp_meta_" + row[:-1].removeprefix("interp_")
        for row in call_code
        if row.endswith(":")
    }
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, call_labels)) + r")\b")
    call_code = [pattern.sub(lambda m: call_labels[m[0]], row) for row in call_code]
    old_size = [
        f"movzx eax, WORD PTR [r9+{bc_vars}]",
        f"movzx r10d, WORD PTR [r9+{bc_stack}]",
        "add eax, r10d",
        "shl rax, 4",
        "add rax, 128",
        f"test BYTE PTR [r9+{bc_kind}], 8",
        "jnz interp_call_capture_size",
    ]
    text = "\n".join(call_code)
    assert text.count("\n".join(old_size)) == 1
    # Cached scalar metadata retains its neutral 160-byte-header definition.
    # The native allocation removes 32; no stale descriptor can change ABI.
    text = text.replace("\n".join(old_size), f"movzx eax, WORD PTR [r9+{bc_meta}]\nsub eax, 32")
    assert text.count(f"WORD PTR [r9+{bc_args}]") == 3
    assert text.count(f"WORD PTR [r9+{bc_vars}]") == 1
    text = text.replace(f"WORD PTR [r9+{bc_args}]", f"BYTE PTR [r9+{bc_cached_args}]")
    text = text.replace(f"WORD PTR [r9+{bc_vars}]", f"BYTE PTR [r9+{bc_cached_vars}]")
    guard = (
        f"test BYTE PTR [r9+{bc_kind}], 1\njz interp_slow\n"
        f"test BYTE PTR [r9+{bc_kind}], 4\njnz interp_slow"
    )
    assert text.count(guard) == 1
    hit_offset = 2376 if internal_entry else 2336
    # One hot comparison describes a supported, uncaptured-argument function
    # with prepared scalar metadata. Cold cases retain the original C guards.
    ready = [
        f"movzx eax, BYTE PTR [r9+{bc_kind}]",
        "and eax, 21",
        "cmp eax, 17",
        "jne interp_meta_unready",
    ]
    if diagnostics:
        ready += [f"inc QWORD PTR [rbx+{hit_offset}]"]
    ready += ["interp_meta_ready:"]
    text = text.replace(guard, "\n".join(ready))
    # Preserve every initialized field and its offset while combining adjacent
    # writes. XMM1 is volatile and no C call occurs in committed preparation.
    replacements = [
        (
            "\n".join(
                [
                    "mov QWORD PTR [rax+40], 0",
                    "mov QWORD PTR [rax+48], 0",
                    "mov QWORD PTR [rax+56], 0",
                    "mov QWORD PTR [rax+64], 0",
                    "mov QWORD PTR [rax+72], 0",
                    "mov DWORD PTR [rax+124], 0",
                ]
            ),
            "\n".join(
                [
                    "pxor xmm1, xmm1",
                    "movq QWORD PTR [rax+40], xmm1",
                    "movdqu XMMWORD PTR [rax+48], xmm1",
                    "movdqu XMMWORD PTR [rax+64], xmm1",
                    "mov DWORD PTR [rax+124], 0",
                ]
            ),
        ),
        (
            "xor edx, edx\nmov QWORD PTR [rax+88], rdx\nmov QWORD PTR [rax+96], 3",
            "movdqu xmm1, XMMWORD PTR [rdi+2048]\nmovdqu XMMWORD PTR [rax+88], xmm1",
        ),
        ("mov QWORD PTR [r8], 0\nmov QWORD PTR [r8+8], 3", "movdqu XMMWORD PTR [r8], xmm1"),
        ("mov QWORD PTR [r13], 0\nmov QWORD PTR [r13+8], 3", "movdqu XMMWORD PTR [r13], xmm1"),
    ]
    for before, after in replacements:
        assert text.count(before) == 1
        text = text.replace(before, after)
    call_code = text.splitlines()
    prepare_index = call_code.index("interp_meta_prepare_call:")
    call_code.insert(prepare_index, "JS_FrameInterpCallMeta_prepare:")
    call_code += [
        "interp_meta_unready:",
        "test eax, 1",
        "jz interp_slow",
        "test eax, 4",
        "jnz interp_slow",
        "JS_FrameInterpCallMeta_init:",
        "interp_meta_init:",
    ]
    if diagnostics:
        call_code += [f"inc QWORD PTR [rbx+{hit_offset + 8}]"]
    # bytes 18..21 are verified padding in the ORIGINAL bytecode type. Both
    # compiler and serialized-bytecode constructors zero the complete header.
    # Keep the live object/class/qualification guards; cache no target pointers.
    call_code += [
        f"movzx eax, WORD PTR [r9+{bc_vars}]",
        f"mov BYTE PTR [r9+{bc_cached_vars}], al",
        f"movzx r10d, WORD PTR [r9+{bc_stack}]",
        "add eax, r10d",
        "shl rax, 4",
        "add rax, 160",
        f"test BYTE PTR [r9+{bc_kind}], 8",
        "jz interp_meta_size_cached",
        f"movzx r10d, WORD PTR [r9+{bc_refs}]",
        "shl r10, 3",
        "add r10, 15",
        "and r10, -16",
        "add rax, r10",
        "interp_meta_size_cached:",
        f"mov WORD PTR [r9+{bc_meta}], ax",
        f"movzx r10d, WORD PTR [r9+{bc_args}]",
        f"mov BYTE PTR [r9+{bc_cached_args}], r10b",
        f"or BYTE PTR [r9+{bc_kind}], 16",
        "jmp interp_meta_ready",
    ]
    # Like Interp strictEqOp, immediates need no C call or ownership release.
    # Preserve the existing integer lane and every main label position. Only
    # its two tag-miss branches reach this appended, chained-unwind kernel.
    # Reference-bearing values, doubles, and mixed BigInt representations keep
    # their original C path. Null/undefined equality ignores unused payload.
    main_code = code
    code = []
    label("interp_primitive_strict_eq")
    emit("xor ecx, ecx", "jmp interp_primitive_eq_check")
    label("interp_primitive_strict_neq")
    emit("mov ecx, 1")
    label("interp_primitive_eq_check")
    emit(
        "mov eax, DWORD PTR [r13-24]",
        "mov edx, DWORD PTR [r13-8]",
        "cmp eax, edx",
        "jne interp_primitive_eq_mixed",
        "cmp eax, 1",
        "jbe interp_primitive_eq_integer",
        "cmp eax, 3",
        "jbe interp_primitive_eq_true",
        "cmp eax, 7",
        "je interp_primitive_eq_integer",
        "jmp interp_primitive_eq_fallback",
    )
    label("interp_primitive_eq_mixed")
    emit(
        "cmp eax, 3",
        "ja interp_primitive_eq_fallback",
        "cmp edx, 3",
        "ja interp_primitive_eq_fallback",
        "xor eax, eax",
        "jmp interp_primitive_eq_store",
    )
    label("interp_primitive_eq_true")
    emit("mov eax, 1", "jmp interp_primitive_eq_store")
    label("interp_primitive_eq_integer")
    emit("mov edx, DWORD PTR [r13-32]", "xor eax, eax", "cmp edx, DWORD PTR [r13-16]", "sete al")
    label("interp_primitive_eq_store")
    emit("xor eax, ecx", "mov QWORD PTR [r13-32], rax", "mov QWORD PTR [r13-24], 1", "sub r13, 16")
    next_()
    label("interp_primitive_eq_fallback")
    if numeric_compare:
        # Keep the established boolean/null/undefined/short-BigInt equality
        # cases untouched. Inspect numeric tags only when equality would
        # otherwise leave the native interpreter for C.
        emit(
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "cmp eax, 8",
            "jne interp_primitive_eq_original_fallback",
            "test ecx, ecx",
            "jnz interp_number_compare_strict_neq",
            "jmp interp_number_compare_strict_eq",
        )
        label("interp_primitive_eq_original_fallback")
    if win64_native:
        emit(
            "mov eax, DWORD PTR [r13-24]",
            "mov edx, DWORD PTR [r13-8]",
            "cmp eax, -1",
            "jne interp_win64_strict_rhs",
            "cmp edx, -1",
            "jne interp_win64_strict_lhs_imm",
            "mov r8, QWORD PTR [r13-32]",
            "mov r9, QWORD PTR [r13-16]",
            "cmp r8, r9",
            "jne interp_win64_strict_diff",
            f"cmp DWORD PTR [r8{rc:+d}], 2",
            "jle interp_win64_strict_c",
            f"sub DWORD PTR [r8{rc:+d}], 2",
            "jmp interp_primitive_eq_true",
        )
        label("interp_win64_strict_diff")
        emit(
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle interp_win64_strict_c",
            f"cmp DWORD PTR [r9{rc:+d}], 1",
            "jle interp_win64_strict_c",
            f"dec DWORD PTR [r8{rc:+d}]",
            f"dec DWORD PTR [r9{rc:+d}]",
            "xor eax, eax",
            "jmp interp_primitive_eq_store",
        )
        label("interp_win64_strict_lhs_imm")
        emit(
            "test edx, edx",
            "js interp_win64_strict_c",
            "mov r8, QWORD PTR [r13-32]",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle interp_win64_strict_c",
            f"dec DWORD PTR [r8{rc:+d}]",
            "xor eax, eax",
            "jmp interp_primitive_eq_store",
        )
        label("interp_win64_strict_rhs")
        emit(
            "cmp edx, -1",
            "jne interp_win64_strict_c",
            "test eax, eax",
            "js interp_win64_strict_c",
            "mov r9, QWORD PTR [r13-16]",
            f"cmp DWORD PTR [r9{rc:+d}], 1",
            "jle interp_win64_strict_c",
            f"dec DWORD PTR [r9{rc:+d}]",
            "xor eax, eax",
            "jmp interp_primitive_eq_store",
        )
        label("interp_win64_strict_c")
    emit("test ecx, ecx", "jnz interp_op_slow_strict_neq", "jmp interp_op_slow_strict_eq")
    # Independently selectable ablation. Leave every integer handler's
    # instruction count unchanged and append the mixed/double cases to this
    # existing chained-unwind range. Coercion keeps its established C path.
    if numeric_compare:
        for name, miss in number_compare_paths:
            prefix = "interp_number_compare_" + name
            label(prefix)
            if name in ("lt", "lte", "gt", "gte"):
                rel_miss = "interp_rel_str_" + name
                number_to_xmm(prefix + "_lhs", "r13-32", "r13-24", "xmm0", rel_miss)
                number_to_xmm(prefix + "_rhs", "r13-16", "r13-8", "xmm1", rel_miss)
                emit_rel_xmm_compare(name)
            else:
                num_miss = (
                    ("interp_win64_loose_" + name)
                    if (win64_native and name in ("eq", "neq"))
                    else miss
                )
                number_to_xmm(prefix + "_lhs", "r13-32", "r13-24", "xmm0", num_miss)
                number_to_xmm(prefix + "_rhs", "r13-16", "r13-8", "xmm1", num_miss)
                emit("xor eax, eax", "ucomisd xmm0, xmm1")
                if name in ("eq", "strict_eq"):
                    emit("sete al", "setnp dl", "and al, dl")
                else:
                    emit("setne al", "setp dl", "or al, dl")
                emit("mov QWORD PTR [r13-32], rax", "mov QWORD PTR [r13-24], 1", "sub r13, 16")
                next_()
        if win64_native:
            label("interp_win64_loose_eq")
            emit("xor ecx, ecx", "jmp interp_win64_loose_common")
            label("interp_win64_loose_neq")
            emit("mov ecx, 1")
            label("interp_win64_loose_common")
            emit(
                "mov eax, DWORD PTR [r13-24]",
                "mov edx, DWORD PTR [r13-8]",
                "cmp eax, -1",
                "jne interp_win64_loose_not_lhs_obj",
                "cmp edx, -1",
                "jne interp_win64_loose_lhs_obj_prim",
                "mov r8, QWORD PTR [r13-32]",
                "mov r9, QWORD PTR [r13-16]",
                "cmp r8, r9",
                "jne interp_win64_loose_obj_diff",
                f"cmp DWORD PTR [r8{rc:+d}], 2",
                "jle interp_win64_loose_c",
                f"sub DWORD PTR [r8{rc:+d}], 2",
                "jmp interp_primitive_eq_true",
            )
            label("interp_win64_loose_obj_diff")
            emit(
                f"cmp DWORD PTR [r8{rc:+d}], 1",
                "jle interp_win64_loose_c",
                f"cmp DWORD PTR [r9{rc:+d}], 1",
                "jle interp_win64_loose_c",
                f"dec DWORD PTR [r8{rc:+d}]",
                f"dec DWORD PTR [r9{rc:+d}]",
                "xor eax, eax",
                "jmp interp_primitive_eq_store",
            )
            label("interp_win64_loose_lhs_obj_prim")
            emit(
                "lea r10d, [rdx-2]",
                "cmp r10d, 1",
                "ja interp_win64_loose_c",
                "mov r8, QWORD PTR [r13-32]",
                f"cmp DWORD PTR [r8{rc:+d}], 1",
                "jle interp_win64_loose_c",
                f"test BYTE PTR [r8+{htmldda_byte}], {htmldda_mask}",
                "jnz interp_win64_loose_c",
                f"dec DWORD PTR [r8{rc:+d}]",
                "xor eax, eax",
                "jmp interp_primitive_eq_store",
            )
            label("interp_win64_loose_not_lhs_obj")
            emit(
                "cmp edx, -1",
                "jne interp_win64_loose_both_nonobj",
                "lea r10d, [rax-2]",
                "cmp r10d, 1",
                "ja interp_win64_loose_c",
                "mov r9, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [r9{rc:+d}], 1",
                "jle interp_win64_loose_c",
                f"test BYTE PTR [r9+{htmldda_byte}], {htmldda_mask}",
                "jnz interp_win64_loose_c",
                f"dec DWORD PTR [r9{rc:+d}]",
                "xor eax, eax",
                "jmp interp_primitive_eq_store",
            )
            label("interp_win64_loose_both_nonobj")
            emit(
                "lea r10d, [rax-2]",
                "cmp r10d, 1",
                "ja interp_win64_loose_rhs_nullish",
                "lea r10d, [rdx-2]",
                "cmp r10d, 1",
                "jbe interp_primitive_eq_true",
                "test edx, edx",
                "jz interp_win64_loose_ret_false",
                "cmp edx, 1",
                "je interp_win64_loose_ret_false",
                "cmp edx, 8",
                "je interp_win64_loose_ret_false",
                "jmp interp_win64_loose_c",
            )
            label("interp_win64_loose_rhs_nullish")
            emit(
                "lea r10d, [rdx-2]",
                "cmp r10d, 1",
                "ja interp_win64_loose_c",
                "test eax, eax",
                "jz interp_win64_loose_ret_false",
                "cmp eax, 1",
                "je interp_win64_loose_ret_false",
                "cmp eax, 8",
                "jne interp_win64_loose_c",
            )
            label("interp_win64_loose_ret_false")
            emit("xor eax, eax", "jmp interp_primitive_eq_store")
            label("interp_win64_loose_c")
            emit("test ecx, ecx", "jnz interp_op_slow_neq", "jmp interp_op_slow_eq")
    code.extend(cold_stage3)
    if win64_native:
        if not stack_insert:
            op("insert3")
            emit(
                "cmp DWORD PTR [r13-8], 0",
                "jns interp_win64_insert3_copy",
                "mov rax, QWORD PTR [r13-16]",
                f"inc DWORD PTR [rax{rc:+d}]",
            )
            label("interp_win64_insert3_copy")
            emit(
                "movdqu xmm0, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13], xmm0",
                "movdqu xmm1, XMMWORD PTR [r13-32]",
                "movdqu XMMWORD PTR [r13-16], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                "movdqu XMMWORD PTR [r13-48], xmm0",
                "add r13, 16",
            )
            next_()
        op("insert2")
        emit(
            "cmp DWORD PTR [r13-8], 0",
            "jns interp_win64_insert2_copy",
            "mov rax, QWORD PTR [r13-16]",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label("interp_win64_insert2_copy")
        emit(
            "movdqu xmm0, XMMWORD PTR [r13-16]",
            "movdqu XMMWORD PTR [r13], xmm0",
            "movdqu xmm1, XMMWORD PTR [r13-32]",
            "movdqu XMMWORD PTR [r13-16], xmm1",
            "movdqu XMMWORD PTR [r13-32], xmm0",
            "add r13, 16",
        )
        next_()
        op("dup1")
        emit(
            "cmp DWORD PTR [r13-24], 0",
            "jns interp_win64_dup1_copy",
            "mov rax, QWORD PTR [r13-32]",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label("interp_win64_dup1_copy")
        emit(
            "movdqu xmm0, XMMWORD PTR [r13-16]",
            "movdqu XMMWORD PTR [r13], xmm0",
            "movdqu xmm1, XMMWORD PTR [r13-32]",
            "movdqu XMMWORD PTR [r13-16], xmm1",
            "add r13, 16",
        )
        next_()
        op("dup2")
        emit(
            "mov rax, QWORD PTR [r13-32]",
            "mov rdx, QWORD PTR [r13-24]",
            "test edx, edx",
            "jns interp_win64_dup2_first",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label("interp_win64_dup2_first")
        emit(
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], rdx",
            "mov rax, QWORD PTR [r13-16]",
            "mov rdx, QWORD PTR [r13-8]",
            "test edx, edx",
            "jns interp_win64_dup2_second",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label("interp_win64_dup2_second")
        emit(
            "mov QWORD PTR [r13+16], rax",
            "mov QWORD PTR [r13+24], rdx",
            "add r13, 32",
        )
        next_()
        op("nip")
        emit(
            "cmp DWORD PTR [r13-24], 0",
            "jns interp_win64_nip_copy",
            "mov rax, QWORD PTR [r13-32]",
            f"cmp DWORD PTR [rax{rc:+d}], 1",
            "jle interp_slow",
            f"dec DWORD PTR [rax{rc:+d}]",
        )
        label("interp_win64_nip_copy")
        emit(
            "movdqu xmm0, XMMWORD PTR [r13-16]",
            "movdqu XMMWORD PTR [r13-32], xmm0",
            "sub r13, 16",
        )
        next_()
        op("get_length")
        emit(
            "cmp DWORD PTR [r13-8], -1",
            "je interp_win64_get_length_obj",
            "cmp DWORD PTR [r13-8], -7",
            "jne interp_slow",
            "mov r8, QWORD PTR [r13-16]",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle interp_slow",
            f"mov eax, DWORD PTR [r8+{string_len_byte}]",
            "and eax, 2147483647",
            "xor edx, edx",
            f"dec DWORD PTR [r8{rc:+d}]",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], rdx",
        )
        next_()
        label("interp_win64_get_length_obj")
        emit(
            "mov r8, QWORD PTR [r13-16]",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle interp_slow",
            f"cmp WORD PTR [r8+{obj_class}], 2",
            "jne interp_slow",
            f"test BYTE PTR [r8+{obj_fast_byte}], {obj_fast_mask}",
            "jz interp_slow",
            f"mov r10, QWORD PTR [r8+{obj_props}]",
            "test r10, r10",
            "jz interp_slow",
            "mov rax, QWORD PTR [r10]",
            "mov rdx, QWORD PTR [r10+8]",
            "test edx, edx",
            "js interp_slow",
            f"dec DWORD PTR [r8{rc:+d}]",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], rdx",
        )
        next_()

        def emit_win64_truthy(p, done_label):
            emit(
                "cmp DWORD PTR [r13-8], -1",
                "je " + p + "_obj",
                "cmp DWORD PTR [r13-8], 8",
                "je " + p + "_f64",
                "cmp DWORD PTR [r13-8], -7",
                "jne interp_slow",
                "mov rcx, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [rcx{rc:+d}], 1",
                "jle interp_slow",
                f"mov edx, DWORD PTR [rcx+{string_len_byte}]",
                "and edx, 2147483647",
                "xor eax, eax",
                "test edx, edx",
                "setne al",
                f"dec DWORD PTR [rcx{rc:+d}]",
                "jmp " + done_label,
            )
            label(p + "_f64")
            emit(
                "xorpd xmm0, xmm0",
                "ucomisd xmm0, QWORD PTR [r13-16]",
                "setne al",
                "setnp dl",
                "and al, dl",
                "movzx eax, al",
                "jmp " + done_label,
            )
            label(p + "_obj")
            emit(
                "mov rcx, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [rcx{rc:+d}], 1",
                "jle interp_slow",
                f"test BYTE PTR [rcx+{htmldda_byte}], {htmldda_mask}",
                "jnz interp_slow",
                f"dec DWORD PTR [rcx{rc:+d}]",
                "mov eax, 1",
            )
            label(done_label)

        label("interp_lnot_cold")
        emit_win64_truthy("interp_win64_lnot_cold", "interp_win64_lnot_cold_done")
        emit("xor eax, 1", "mov QWORD PTR [r13-16], rax", "mov QWORD PTR [r13-8], 1")
        next_()
        for name, width in [("if_true", 4), ("if_false", 4), ("if_true8", 1), ("if_false8", 1)]:
            label("interp_" + name + "_cold")
            emit_win64_truthy(
                "interp_win64_" + name + "_cold", "interp_win64_" + name + "_cold_done"
            )
            emit(
                "sub r13, 16",
                f"dec DWORD PTR [rsi+{ctx_poll}]",
                "test eax, eax",
                ("jz" if "true" in name else "jnz") + " interp_" + name + "_untaken",
            )
            if width == 4:
                emit("movsxd rax, DWORD PTR [r12+1]")
            else:
                emit("movsx rax, BYTE PTR [r12+1]")
            emit("lea r12, [r12+rax+1]", "jmp interp_dispatch")
    eq_code, code = code, main_code
    eq_labels = {row[:-1] for row in eq_code if row.endswith(":")}
    new_labels = {row[:-1] for row in call_code if row.endswith(":")}
    assert not new_labels.intersection(labels)
    labels.update(new_labels)
    for name in (
        "call0",
        "call1",
        "call2",
        "call3",
        "call",
        "tail_call",
        "call_method",
        "tail_call_method",
    ):
        handlers[name] = call_labels["interp_" + name]

    label("interp_root_return")
    emit("xor ebp, ebp", "mov eax, 1")
    label("interp_exit")
    emit("mov QWORD PTR [rbx], rbp", "mov QWORD PTR [rbx+16], r12", "mov QWORD PTR [rbx+24], r13")

    assert not any("interp_push_value" in row or row == "jmp interp_dispatch" for row in code)
    regs = ["rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14", "r15"]
    if instruction_stream is not None:
        if (
            not foundation_only
            or not internal_entry
            or layout.get("platform") != "linux-x86_64-sysv"
        ):
            raise ValueError(
                "The development ELF instruction stream requires a measured Linux foundation profile"
            )
        return instruction_stream(
            dict(
                code=code,
                cold_code=cold_code,
                short_code=short_code,
                call_code=call_code,
                eq_code=eq_code,
                handlers=handlers,
                opcodes=ops,
                saved_registers=regs,
                diagnostics=diagnostics,
                internal_entry=internal_entry,
                reference_stores=reference_stores,
            )
        )
    banner = "Generated by tools/generate-register.py; do not edit."
    masm = [
        "; " + banner,
        "OPTION CASEMAP:NONE",
        "OPTION DOTNAME",
        "EXTERN JS_FreeValue:PROC",
        "EXTERN JS_FrameInterpSlow:PROC",
        "EXTERN JS_FrameInterpHost:PROC",
        "EXTERN JS_FrameInterpHostDirect:PROC",
        "EXTERN JS_FrameInterpClose:PROC",
        ".qjsvm$a SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC JS_FrameInterp",
        "JS_FrameInterp PROC",
    ]
    if internal_entry:
        masm.insert(3, "EXTERN JS_FrameInterpFree:PROC")
        masm[3:3] = [
            "EXTERN " + name + ":PROC"
            for name in (
                "JS_FrameInterpHostDirectShared",
                "JS_FrameInterpHostShared",
                "JS_FrameCallEntryShared",
                "JS_FrameCallEntryLegacy",
            )
            if not (foundation_only and name == "JS_FrameCallEntryLegacy")
        ]
        if win64_native:
            masm[3:3] = [
                "EXTERN JS_FrameInterpHostDirectScoped:PROC",
                "EXTERN JS_FrameInterpHostScoped:PROC",
            ]
    if binding_index and native_slice:
        masm.insert(3, "EXTERN JS_FrameBorrowedField:PROC")
    masm[3:3] = ["EXTERN JS_FrameInterpOp_" + name + ":PROC" for name in numeric_ops]
    masm[3:3] = ["EXTERN JS_FrameInterpBig_" + name + ":PROC" for name in ("add", "mul")]
    masm[3:3] = ["EXTERN JS_FrameInterpProperty_" + name + ":PROC" for name in property_ops]
    gas = [
        "/* " + banner + " */",
        ".intel_syntax noprefix",
        '.section .qjsvm$a,"xr"',
        ".globl JS_FrameInterp",
        ".def JS_FrameInterp; .scl 2; .type 32; .endef",
        "JS_FrameInterp:",
    ]
    for reg in regs:
        masm += [f"push {reg}", f"interp_prolog_push_{reg}::"]
        gas += [f"push {reg}", f"interp_prolog_push_{reg}:"]
    masm += ["sub rsp, 72", "interp_prolog_alloc::", "mov rbx, rcx", "lea rdi, interp_table"]
    gas += ["sub rsp, 72", "interp_prolog_alloc:", "mov rbx, rcx", "lea rdi, [rip+interp_table]"]

    # DWORD/QWORD/XMMWORD PTR and ordinary memory forms are accepted by both.
    # MASM procedure-local labels are invisible to a table in another section.
    def masm_main_line(line):
        if line.endswith(":"):
            return line[:-1] + "::"
        updated = (
            line.replace("jne interp_short_big_", "jne NEAR PTR interp_short_big_")
            .replace("jnz interp_primitive_strict_", "jnz NEAR PTR interp_primitive_strict_")
            .replace("jl interp_ref_store_", "jl NEAR PTR interp_ref_store_")
            .replace(
                "js JS_FramePropertyReferenceStore", "js NEAR PTR JS_FramePropertyReferenceStore"
            )
        )
        if updated != line:
            return updated
        return re.sub(
            r"^(j\w+) (\w+)$",
            lambda m: f"{m[1]} NEAR PTR {m[2]}" if m[2] in eq_labels else m[0],
            line,
        )

    def masm_eq_line(line):
        if line.endswith(":"):
            return line[:-1] + "::"
        return re.sub(
            r"^(j\w+) (\w+)$",
            lambda m: f"{m[1]} NEAR PTR {m[2]}" if m[2] not in eq_labels else m[0],
            line,
        )

    masm += [masm_main_line(line) for line in code]
    if emit_indexed_own:
        masm[3:3] = ["EXTERN JS_FrameSlowDirectData:BYTE"]
        masm = [x.replace("[rip+JS_FrameSlowDirectData]", "[JS_FrameSlowDirectData]") for x in masm]
    gas += code
    scoped_exit = (
        internal_entry and not foundation_only and (_frame_tool_path("native-c-scope")).is_file()
    )
    if scoped_exit:
        # Win64 permits a ModRM mod00 memory JMP to terminate an epilogue.
        # Restore the ORIGINAL SP/NV registers before the sole TLS/RET leaf.
        # Replacing RET1 with RIP-memory-JMP6 keeps raw_end at original+5,
        # exactly the existing Home32 footprint; no cold helpers move.
        masm.insert(3, "EXTERN JS_FrameNativeCScopeReturnTarget:QWORD")
        gas.insert(3, ".extern JS_FrameNativeCScopeReturnTarget")
        masm += ["PUBLIC JS_FrameNativeCScopeRawEpilog", "JS_FrameNativeCScopeRawEpilog LABEL NEAR"]
        gas += [".globl JS_FrameNativeCScopeRawEpilog", "JS_FrameNativeCScopeRawEpilog:"]
    for target in (masm, gas):
        target += ["add rsp, 72"] + ["pop " + r for r in reversed(regs)]
    if scoped_exit:
        masm += ["jmp QWORD PTR [JS_FrameNativeCScopeReturnTarget]"]
        gas += ["jmp QWORD PTR [rip+JS_FrameNativeCScopeReturnTarget]"]
    else:
        masm += ["ret"]
        gas += ["ret"]
    masm += [
        "JS_FrameInterp_end LABEL BYTE",
        "JS_FrameInterp ENDP",
        ".qjsvm$a ENDS",
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC JS_FrameInterpPropertyCold",
        "PUBLIC JS_FrameInterpPropertyCold_end",
        "JS_FrameInterpPropertyCold PROC",
    ]
    gas += [
        "JS_FrameInterp_end:",
        '.section .qjscold,"xr"',
        ".p2align 4",
        ".globl JS_FrameInterpPropertyCold, JS_FrameInterpPropertyCold_end",
        ".def JS_FrameInterpPropertyCold; .scl 2; .type 32; .endef",
        "JS_FrameInterpPropertyCold:",
    ]
    # MASM needs an explicit near conditional transfer across two PE sections;
    # the GNU stream already emits a rel32 relocation for this forward link.
    masm += [
        line[:-1] + "::"
        if line.endswith(":")
        else "jz NEAR PTR interp_reload"
        if line == "jz interp_reload"
        else line
        for line in cold_code
    ]
    gas += cold_code
    masm += [
        "JS_FrameInterpPropertyCold_end LABEL BYTE",
        "JS_FrameInterpPropertyCold ENDP",
        "PUBLIC JS_FrameInterpShortBig",
        "PUBLIC JS_FrameInterpShortBig_end",
        "JS_FrameInterpShortBig PROC",
    ]
    gas += [
        "JS_FrameInterpPropertyCold_end:",
        ".globl JS_FrameInterpShortBig, JS_FrameInterpShortBig_end",
        ".def JS_FrameInterpShortBig; .scl 2; .type 32; .endef",
        "JS_FrameInterpShortBig:",
    ]
    masm += [
        line[:-1] + "::"
        if line.endswith(":")
        else re.sub(r"^(jne|jo) (interp_op_slow_\w+)$", r"\1 NEAR PTR \2", line)
        for line in short_code
    ]
    gas += short_code
    masm += [
        "JS_FrameInterpShortBig_end LABEL BYTE",
        "JS_FrameInterpShortBig ENDP",
        "PUBLIC JS_FrameInterpCallMeta",
        "PUBLIC JS_FrameInterpCallMeta_end",
        "PUBLIC JS_FrameInterpCallMeta_prepare",
        "PUBLIC JS_FrameInterpCallMeta_init",
        "JS_FrameInterpCallMeta PROC",
    ]
    gas += [
        "JS_FrameInterpShortBig_end:",
        ".globl JS_FrameInterpCallMeta, JS_FrameInterpCallMeta_end",
        ".globl JS_FrameInterpCallMeta_prepare, JS_FrameInterpCallMeta_init",
        ".def JS_FrameInterpCallMeta; .scl 2; .type 32; .endef",
        "JS_FrameInterpCallMeta:",
    ]
    cross_targets = {"interp_slow", "interp_host_call"}
    masm += [
        row[:-1] + "::"
        if row.endswith(":")
        else re.sub(
            r"^(j\w+) (\w+)$",
            lambda m: m[1] + " NEAR PTR " + m[2] if m[2] in cross_targets else m[0],
            row,
        )
        for row in call_code
    ]
    gas += call_code
    masm += [
        "JS_FrameInterpCallMeta_end LABEL BYTE",
        "JS_FrameInterpCallMeta ENDP",
        "PUBLIC JS_FrameInterpPrimitiveEq",
        "PUBLIC JS_FrameInterpPrimitiveEq_end",
        "JS_FrameInterpPrimitiveEq PROC",
    ]
    gas += [
        "JS_FrameInterpCallMeta_end:",
        ".globl JS_FrameInterpPrimitiveEq, JS_FrameInterpPrimitiveEq_end",
        ".def JS_FrameInterpPrimitiveEq; .scl 2; .type 32; .endef",
        "JS_FrameInterpPrimitiveEq:",
    ]
    masm += [masm_eq_line(line) for line in eq_code]
    gas += eq_code
    masm += [
        "JS_FrameInterpPrimitiveEq_end LABEL BYTE",
        "JS_FrameInterpPrimitiveEq ENDP",
        ".qjscold ENDS",
        ".xdata SEGMENT ALIGN(4) READONLY 'DATA'",
        "JS_FrameInterp_unwind LABEL BYTE",
        "DB 1, interp_prolog_alloc - JS_FrameInterp, 9, 0",
        "DB interp_prolog_alloc - JS_FrameInterp, 082h",
    ]
    gas += [
        "JS_FrameInterpPrimitiveEq_end:",
        '.section .xdata,"dr"',
        ".p2align 2",
        "JS_FrameInterp_unwind:",
        ".byte 1, interp_prolog_alloc - JS_FrameInterp, 9, 0",
        ".byte interp_prolog_alloc - JS_FrameInterp, 0x82",
    ]
    # The primary record describes the exact existing 16-byte prologue. Use
    # label differences, so metadata cannot silently diverge from its encoding.
    reg_ids = dict(zip(regs, (3, 5, 6, 7, 12, 13, 14, 15)))
    for reg in reversed(regs):
        masm += [f"DB interp_prolog_push_{reg} - JS_FrameInterp, {reg_ids[reg] << 4}"]
        gas += [f".byte interp_prolog_push_{reg} - JS_FrameInterp, {reg_ids[reg] << 4}"]
    masm += [
        "DB 0, 0",
        "JS_FrameInterpPropertyCold_unwind LABEL BYTE",
        "DB 021h, 0, 0, 0",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        ".xdata ENDS",
        ".pdata SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        ".pdata ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL JS_FrameInterpPropertyCold, IMAGEREL JS_FrameInterpPropertyCold_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        "DD IMAGEREL JS_FrameInterpShortBig, IMAGEREL JS_FrameInterpShortBig_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        "DD IMAGEREL JS_FrameInterpCallMeta, IMAGEREL JS_FrameInterpCallMeta_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        "DD IMAGEREL JS_FrameInterpPrimitiveEq, IMAGEREL JS_FrameInterpPrimitiveEq_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        ".rdata$zzqjsinterp SEGMENT ALIGN(8) READONLY 'CONST'",
        "interp_table LABEL QWORD",
    ]
    gas += [
        ".short 0",
        "JS_FrameInterpPropertyCold_unwind:",
        ".byte 0x21, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .pdata,"dr"',
        ".p2align 2",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva JS_FrameInterpPropertyCold, JS_FrameInterpPropertyCold_end, JS_FrameInterpPropertyCold_unwind",
        ".rva JS_FrameInterpShortBig, JS_FrameInterpShortBig_end, JS_FrameInterpPropertyCold_unwind",
        ".rva JS_FrameInterpCallMeta, JS_FrameInterpCallMeta_end, JS_FrameInterpPropertyCold_unwind",
        ".rva JS_FrameInterpPrimitiveEq, JS_FrameInterpPrimitiveEq_end, JS_FrameInterpPropertyCold_unwind",
        '.section .rdata$zzqjsinterp,"dr"',
        ".p2align 3",
        "interp_table:",
    ]
    if internal_entry and not foundation_only:
        handlers["special_object"] = "JS_FrameNullProtoCold"
    for opcode in range(256):
        dest = handlers.get(ops[opcode], "interp_slow") if opcode < len(ops) else "interp_slow"
        masm += ["DQ " + dest]
        gas += [".quad " + dest]
    masm += ["DQ 0, 3"]
    gas += [".quad 0, 3"]
    masm += [".rdata$zzqjsinterp ENDS", "END"]
    # Independent Win64 leaf trampoline: preserve RCX/RDX/R8/R9, shadow space,
    # stack and nonvolatile VM registers. Only the original host-call operand
    # is redirected; all existing handler/kernel instruction offsets remain.
    # Tail transfers keep the standard C ABI and return to the original native
    # continuation. This frame has its own empty unwind record, not root chain
    # info: RSP contains an actual CALL return address, unlike the cold opcodes.
    use_host_gates = internal_entry and not foundation_only
    host_offset = 2297 if diagnostics else 161
    host_dispatch = [
        f"cmp BYTE PTR [rcx+{host_offset}], 0",
        "je interp_host_dispatch_legacy",
        "cmp QWORD PTR [rdx-8], -1",
        "jne interp_host_dispatch_legacy",
        "mov rax, QWORD PTR [rdx-16]",
        f"cmp WORD PTR [rax+{obj_class}], 12",
        "jne interp_host_dispatch_legacy",
        f"cmp BYTE PTR [rax+{obj_cproto}], 1",
        "ja "
        + ("interp_host_dispatch_numeric" if use_host_gates else "interp_host_dispatch_legacy"),
        "jmp "
        + (
            "JS_FrameInterpHostDirectGate"
            if use_host_gates
            else ("JS_FrameInterpHostDirectScoped" if win64_native else "JS_FrameInterpHostDirect")
        ),
        "interp_host_dispatch_legacy:",
        "jmp "
        + (
            "JS_FrameInterpHostGate"
            if use_host_gates
            else ("JS_FrameInterpHostScoped" if win64_native else "JS_FrameInterpHost")
        ),
    ]
    masm.pop()  # END follows the appended independent section and unwind.
    masm += [
        ".qjsvm$zzh SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC JS_FrameInterpHostDispatch",
        "PUBLIC JS_FrameInterpHostDispatch_end",
        "JS_FrameInterpHostDispatch PROC",
    ]
    masm += [
        line[:-1] + "::"
        if line.endswith(":")
        else line.replace(
            "jmp JS_FrameInterpHostDirectGate", "jmp NEAR PTR JS_FrameInterpHostDirectGate"
        )
        .replace("jmp JS_FrameInterpHostGate", "jmp NEAR PTR JS_FrameInterpHostGate")
        .replace("jmp JS_FrameInterpNumericDispatch", "jmp NEAR PTR JS_FrameInterpNumericDispatch")
        .replace("ja interp_host_dispatch_numeric", "ja SHORT interp_host_dispatch_numeric")
        for line in host_dispatch
    ]
    masm += ["JS_FrameInterpHostDispatch_end LABEL BYTE", "JS_FrameInterpHostDispatch ENDP"]
    if use_host_gates:
        # The checked C-function branch alone enters this five-byte tail leaf.
        # Other classes and disabled direct-host mode retain the original route.
        # It occupies the dispatch section's existing alignment envelope.
        masm += [
            "PUBLIC JS_FrameInterpNumericEntry",
            "PUBLIC JS_FrameInterpNumericEntry_end",
            "JS_FrameInterpNumericEntry PROC",
            "interp_host_dispatch_numeric::",
            "jmp NEAR PTR JS_FrameInterpNumericDispatch",
            "JS_FrameInterpNumericEntry_end LABEL BYTE",
            "JS_FrameInterpNumericEntry ENDP",
        ]
    masm += [
        ".qjsvm$zzh ENDS",
        ".xdata SEGMENT ALIGN(4) READONLY 'DATA'",
        "JS_FrameInterpHostDispatch_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        ".xdata ENDS",
        ".pdata$zzqjshost SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL JS_FrameInterpHostDispatch, IMAGEREL JS_FrameInterpHostDispatch_end, IMAGEREL JS_FrameInterpHostDispatch_unwind",
        ".pdata$zzqjshost ENDS",
        "END",
    ]
    if use_host_gates:
        masm[-1:-1] = [
            ".pdata$zzqjshost SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL JS_FrameInterpNumericEntry, IMAGEREL JS_FrameInterpNumericEntry_end, IMAGEREL JS_FrameInterpHostDispatch_unwind",
            ".pdata$zzqjshost ENDS",
        ]
    gas += [
        '.section .qjsvm$zzh,"xr"',
        ".p2align 4",
        ".globl JS_FrameInterpHostDispatch, JS_FrameInterpHostDispatch_end",
        ".def JS_FrameInterpHostDispatch; .scl 2; .type 32; .endef",
        "JS_FrameInterpHostDispatch:",
    ] + host_dispatch
    gas += ["JS_FrameInterpHostDispatch_end:"]
    if use_host_gates:
        gas += [
            ".globl JS_FrameInterpNumericEntry, JS_FrameInterpNumericEntry_end",
            ".def JS_FrameInterpNumericEntry; .scl 2; .type 32; .endef",
            "JS_FrameInterpNumericEntry:",
            "interp_host_dispatch_numeric:",
            "jmp JS_FrameInterpNumericDispatch",
            "JS_FrameInterpNumericEntry_end:",
        ]
    gas += [
        '.section .xdata,"dr"',
        ".p2align 2",
        "JS_FrameInterpHostDispatch_unwind:",
        ".byte 1, 0, 0, 0",
        '.section .pdata$zzqjshost,"dr"',
        ".p2align 2",
        ".rva JS_FrameInterpHostDispatch, JS_FrameInterpHostDispatch_end, JS_FrameInterpHostDispatch_unwind",
    ]
    if use_host_gates:
        gas += [
            ".rva JS_FrameInterpNumericEntry, JS_FrameInterpNumericEntry_end, JS_FrameInterpHostDispatch_unwind"
        ]
    if internal_entry and not foundation_only:
        # Actual tail calls: no hidden-result/argument/nonvolatile/stack changes.
        # Targets are external so MASM cannot shorten a cross-section transfer.
        leaves = [
            (
                "JS_FrameInterpNumericDispatch",
                ".qjsvm$zzznumA",
                [
                    f"movzx eax, BYTE PTR [rax+{obj_cproto}]",
                    "sub eax, 6",
                    "cmp eax, 1",
                    "ja JS_FrameInterpHostGate",
                    "mov rax, QWORD PTR [rcx+56]",
                    f"test BYTE PTR [rax+{rt_shared}], 32",
                    "jne JS_FrameInterpHostGate",
                    "jmp JS_FrameInterpNumericFast",
                ],
            ),
            (
                "JS_FrameInterpHostDirectGate",
                ".qjsvm$zzsd",
                [
                    "mov rax, QWORD PTR [rcx+56]",
                    f"test BYTE PTR [rax+{rt_shared}], 2",
                    "jne JS_FrameInterpHostDirect",
                    "test r8d, r8d",
                    "jz JS_FrameInterpZeroHost",
                    "jmp JS_FrameInterpGenericFast",
                ],
            ),
            (
                "JS_FrameInterpHostGate",
                ".qjsvm$zzsh",
                [
                    "mov rax, QWORD PTR [rcx+56]",
                    f"test BYTE PTR [rax+{rt_shared}], 2",
                    "jne JS_FrameInterpHost",
                    "jmp JS_FrameInterpHostShared",
                ],
            ),
            (
                "JS_FrameCallEntryDispatch",
                ".qjsvm$zzsf",
                [
                    f"mov rax, QWORD PTR [rdx+{ctx_rt}]",
                    f"test BYTE PTR [rax+{rt_shared}], 4",
                    "jne JS_FrameChildFast",
                    "jmp JS_FrameRootLeafSelect",
                ],
            ),
        ]
        masm.pop()
        masm[3:3] = ["EXTERN JS_FrameInterpHostNumeric:PROC"]
        # MS LINK requires each .pdata contribution to follow linked RVA order.
        for name, section, instructions in sorted(leaves, key=lambda leaf: leaf[1]):
            masm += [
                section + " SEGMENT ALIGN(16) 'CODE'",
                "PUBLIC " + name,
                "PUBLIC " + name + "_end",
                name + " PROC",
            ] + [
                re.sub(
                    r"^(j\w+) (JS_FrameInterpHostGate|JS_FrameInterpNumericFast|JS_FrameInterpGenericFast|JS_FrameInterpZeroHost)$",
                    r"\1 NEAR PTR \2",
                    line,
                ).replace("jmp JS_FrameRootLeafSelect", "jmp NEAR PTR JS_FrameRootLeafSelect")
                for line in instructions
            ]
            masm += [
                name + "_end LABEL BYTE",
                name + " ENDP",
                section + " ENDS",
                ".xdata SEGMENT ALIGN(4) READONLY 'DATA'",
                name + "_unwind LABEL BYTE",
                "DB 1, 0, 0, 0",
                ".xdata ENDS",
                ".pdata$zzqjsshared SEGMENT ALIGN(4) READONLY 'DATA'",
                "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind",
                ".pdata$zzqjsshared ENDS",
            ]
            gas += [
                ".section " + section + ',"xr"',
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
            ] + [
                row
                for line in instructions
                for row in (
                    [".byte 0xe9", ".long JS_FrameInterpNumericFast - . - 4"]
                    if line == "jmp JS_FrameInterpNumericFast"
                    else [line]
                )
            ]
            gas += [
                name + "_end:",
                '.section .xdata,"dr"',
                ".p2align 2",
                name + "_unwind:",
                ".byte 1, 0, 0, 0",
                '.section .pdata$zzqjsshared,"dr"',
                ".p2align 2",
                ".rva " + name + ", " + name + "_end, " + name + "_unwind",
            ]
        masm += ["END"]
        # Added in the already-late numeric island; the original VM is intact.
        import importlib.util

        numeric_spec = importlib.util.spec_from_file_location(
            "numeric_trampoline", _frame_tool_path("numeric-trampoline")
        )
        numeric_module = importlib.util.module_from_spec(numeric_spec)
        numeric_spec.loader.exec_module(numeric_module)
        numeric_module.append(masm, gas, diagnostics)
        generic_spec = importlib.util.spec_from_file_location(
            "generic_trampoline", _frame_tool_path("generic-trampoline")
        )
        generic_module = importlib.util.module_from_spec(generic_spec)
        generic_spec.loader.exec_module(generic_module)
        generic_module.append(masm, gas, diagnostics)
        window_spec = importlib.util.spec_from_file_location(
            "generic_window", _frame_tool_path("generic-window")
        )
        window_module = importlib.util.module_from_spec(window_spec)
        window_spec.loader.exec_module(window_module)
        window_module.append(masm, gas, diagnostics)
        child_spec = importlib.util.spec_from_file_location(
            "child_entry", _frame_tool_path("child-entry")
        )
        child_module = importlib.util.module_from_spec(child_spec)
        child_spec.loader.exec_module(child_module)
        child_module.append(masm, gas, diagnostics)
        legacy_spec = importlib.util.spec_from_file_location(
            "legacy_child_entry", _frame_tool_path("generate-internal")
        )
        legacy_module = importlib.util.module_from_spec(legacy_spec)
        legacy_spec.loader.exec_module(legacy_module)
        legacy_module.append_legacy_child(masm, gas)
        slot_spec = importlib.util.spec_from_file_location(
            "slot_store", _frame_tool_path("slot-store")
        )
        slot_module = importlib.util.module_from_spec(slot_spec)
        slot_spec.loader.exec_module(slot_module)
        slot_module.append(masm, gas, reference_stores, diagnostics, root)
        add_spec = importlib.util.spec_from_file_location(
            "add_boundary", _frame_tool_path("add-boundary")
        )
        add_module = importlib.util.module_from_spec(add_spec)
        add_spec.loader.exec_module(add_module)
        add_module.append(masm, gas, diagnostics, ids)
        zero_spec = importlib.util.spec_from_file_location(
            "zero_host", _frame_tool_path("zero-host")
        )
        zero_module = importlib.util.module_from_spec(zero_spec)
        zero_spec.loader.exec_module(zero_module)
        zero_module.append(masm, gas)
        leaf_spec = importlib.util.spec_from_file_location(
            "child_leaf", _frame_tool_path("child-leaf")
        )
        leaf_module = importlib.util.module_from_spec(leaf_spec)
        leaf_spec.loader.exec_module(leaf_module)
        leaf_module.append(masm, gas, ids, diagnostics)
        root_leaf_spec = importlib.util.spec_from_file_location(
            "root_leaf", _frame_tool_path("root-leaf")
        )
        root_leaf_module = importlib.util.module_from_spec(root_leaf_spec)
        root_leaf_spec.loader.exec_module(root_leaf_module)
        root_leaf_module.append(masm, gas, ids)
        null_spec = importlib.util.spec_from_file_location(
            "null_proto", _frame_tool_path("null-proto")
        )
        null_module = importlib.util.module_from_spec(null_spec)
        null_spec.loader.exec_module(null_module)
        null_module.append(masm, gas, diagnostics)
        local_spec = importlib.util.spec_from_file_location(
            "add_local", _frame_tool_path("add-local")
        )
        local_module = importlib.util.module_from_spec(local_spec)
        local_spec.loader.exec_module(local_module)
        local_module.append(masm, gas, diagnostics)
        free_spec = importlib.util.spec_from_file_location(
            "slot_free", _frame_tool_path("free-boundary")
        )
        free_module = importlib.util.module_from_spec(free_spec)
        free_spec.loader.exec_module(free_module)
        free_module.append(masm, gas, diagnostics, root)
        js_owned_spec = importlib.util.spec_from_file_location(
            "js_owned_missing", _frame_tool_path("js-owned-missing")
        )
        js_owned_module = importlib.util.module_from_spec(js_owned_spec)
        js_owned_spec.loader.exec_module(js_owned_module)
        js_owned_module.append(masm, gas, diagnostics, out)
        if native_slice:
            native_spec = importlib.util.spec_from_file_location(
                "native_slice", _frame_tool_path("native-slice")
            )
            native_module = importlib.util.module_from_spec(native_spec)
            native_spec.loader.exec_module(native_module)
            native_module.append(masm, gas, diagnostics, out)
            number_spec = importlib.util.spec_from_file_location(
                "number_property", _frame_tool_path("number-property")
            )
            number_module = importlib.util.module_from_spec(number_spec)
            number_spec.loader.exec_module(number_module)
            number_module.append(gas)
            proto_spec = importlib.util.spec_from_file_location(
                "proto_load", _frame_tool_path("proto-load")
            )
            proto_module = importlib.util.module_from_spec(proto_spec)
            proto_spec.loader.exec_module(proto_module)
            proto_module.append(gas, diagnostics, atoms.index("length") + 1)
            root_spec = importlib.util.spec_from_file_location(
                "native_root", _frame_tool_path("native-root")
            )
            root_module = importlib.util.module_from_spec(root_spec)
            root_spec.loader.exec_module(root_module)
            root_module.append(gas, diagnostics, out)
            zero_root_spec = importlib.util.spec_from_file_location(
                "native_root_zero", _frame_tool_path("native-root-zero")
            )
            zero_root_module = importlib.util.module_from_spec(zero_root_spec)
            zero_root_spec.loader.exec_module(zero_root_module)
            zero_root_module.append(gas, diagnostics, out)
            args_root_spec = importlib.util.spec_from_file_location(
                "native_root_args", _frame_tool_path("native-root-args")
            )
            args_root_module = importlib.util.module_from_spec(args_root_spec)
            args_root_spec.loader.exec_module(args_root_module)
            args_root_module.append(gas, diagnostics, out)
            public_root_spec = importlib.util.spec_from_file_location(
                "public_root", _frame_tool_path("public-root")
            )
            public_root_module = importlib.util.module_from_spec(public_root_spec)
            public_root_spec.loader.exec_module(public_root_module)
            public_root_module.append(gas, diagnostics, out)
        string_spec = importlib.util.spec_from_file_location(
            "local_string", _frame_tool_path("local-string")
        )
        string_module = importlib.util.module_from_spec(string_spec)
        string_spec.loader.exec_module(string_module)
        string_module.emit(out)
        if indexed_own:
            # Append before generating Dirty clones: a miss must retain its
            # exact clean/dirty publication path, not jump into a clean helper.
            property_store_append(masm, gas, layout)
        if native_slice:
            publish_spec = importlib.util.spec_from_file_location(
                "frame_publish", _frame_tool_path("publish-boundary")
            )
            publish_module = importlib.util.module_from_spec(publish_spec)
            publish_spec.loader.exec_module(publish_module)
            publish_module.append(gas, diagnostics, out)
            invoke_spec = importlib.util.spec_from_file_location(
                "frame_c_invoke", _frame_tool_path("c-invoke")
            )
            invoke_module = importlib.util.module_from_spec(invoke_spec)
            invoke_spec.loader.exec_module(invoke_module)
            invoke_module.append(gas, diagnostics, out)
        masm[3:3] = ["PUBLIC interp_reload, interp_exit"]
        gas[:0] = [".globl interp_reload, interp_exit"]
    if internal_entry and foundation_only:
        # Bring the independently ported release islands into the development
        # stage as soon as their ABI and ownership protocols are qualified.
        import importlib.util

        masm[3:3] = ["EXTERN __imp_getenv:QWORD"]
        for module_name, arguments in (
            ("slot-store", (reference_stores, diagnostics, root)),
            ("free-boundary", (diagnostics, root)),
        ):
            spec = importlib.util.spec_from_file_location(
                module_name, _frame_tool_path(module_name)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.append(masm, gas, *arguments)
    if leaf_entry_masm:
        assert internal_entry and not native_slice
        import importlib.util

        leaf_spec = importlib.util.spec_from_file_location(
            "primitive_leaf", _frame_tool_path("leaf-entry")
        )
        leaf_module = importlib.util.module_from_spec(leaf_spec)
        leaf_spec.loader.exec_module(leaf_module)
        leaf_module.append_masm(root, out, masm, diagnostics)
    if c_invoke_masm:
        assert internal_entry and not native_slice
        import importlib.util

        invoke_spec = importlib.util.spec_from_file_location(
            "msvc_c_invoke", _frame_tool_path("c-invoke")
        )
        invoke_module = importlib.util.module_from_spec(invoke_spec)
        invoke_spec.loader.exec_module(invoke_module)
        invoke_module.append_masm(masm, diagnostics, out)
        if indexed_own:
            # Capture the old own-probe template before routing the primary
            # receiver absence edge. String/Object holder clones have their
            # own input ownership and fallback contracts.
            proto_spec = importlib.util.spec_from_file_location(
                "proto_load_masm", _frame_tool_path("proto-load")
            )
            proto_module = importlib.util.module_from_spec(proto_spec)
            proto_spec.loader.exec_module(proto_module)
            proto_module.append_masm(masm, gas, layout)
    if internal_entry and not foundation_only and (native_slice or c_invoke_masm):
        legacy_module.append_shared_bypass(masm, gas, diagnostics, native_slice)
        callback_spec = importlib.util.spec_from_file_location(
            "prepared_callback", _frame_tool_path("prepared-callback")
        )
        callback_module = importlib.util.module_from_spec(callback_spec)
        callback_spec.loader.exec_module(callback_module)
        callback_module.append(masm, gas, diagnostics, native_slice)
    if internal_entry and not foundation_only and (native_slice or c_invoke_masm):
        append_spec = importlib.util.spec_from_file_location(
            "array_append", _frame_tool_path("array-append")
        )
        append_module = importlib.util.module_from_spec(append_spec)
        append_spec.loader.exec_module(append_module)
        append_module.route(out, masm, gas, diagnostics)
    if indexed_own and native_slice and pool_allocator:
        # Whole-app evidence supports the GNU backend. Do not retain an
        # inactive MASM island/metadata when its total application net loses.
        add_module.route_native_append(masm, gas, diagnostics, ids, out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "quickjs-interpreter-register-win64.asm").write_text("\n".join(masm) + "\n")
    (out / "quickjs-interpreter-register-win64.S").write_text("\n".join(gas) + "\n")
    print(f"Register Interp: {len(handlers)} handlers; diagnostics={diagnostics}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--internal-entry", action="store_true")
    parser.add_argument("--native-slice", action="store_true")
    parser.add_argument("--leaf-entry-masm", action="store_true")
    parser.add_argument("--c-invoke-masm", action="store_true")
    parser.add_argument(
        "--foundation-only",
        action="store_true",
        help="development ABI validation without the still-unported supplements",
    )
    parser.add_argument(
        "--numeric-compare",
        action="store_true",
        help="experimental mixed integer/double comparison handlers",
    )
    parser.add_argument(
        "--pool-allocator",
        action="store_true",
        help="emit capacity proofs only with the pool allocator",
    )
    args = parser.parse_args()
    generate(
        args.source,
        args.out,
        args.diagnostics,
        args.internal_entry,
        args.native_slice,
        args.leaf_entry_masm,
        args.c_invoke_masm,
        args.foundation_only,
        args.numeric_compare,
        args.pool_allocator,
    )
