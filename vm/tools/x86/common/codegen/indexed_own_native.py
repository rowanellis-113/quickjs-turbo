"""Shape-array integer own-data hits in the current Win64 VM activation.

Interp's indexed-storage split, adapted to NG's live shape slots and refcounts.
No pointer cache, allocation, C call, length update or last release on a hit.
"""


def append(name, layout, rc, emit, label, next_):
    fields = layout["offsets"]
    assert layout["reference_count_model"] in ("inline-header", "allocator-prefix")
    assert layout["sizes"]["JSValue"] == 16 and layout["sizes"]["JSShapeProperty"] == 8
    assert fields["JSShapeProperty.atom"] == 4
    fast_byte, fast_mask = layout["bits"]["JSObject.fast_array"][0]
    writing = name == "put_array_el"
    p = "interp_" + name + "_indexed_own"
    label(p)
    # Mode 255 deliberately takes the old C path once, so configuration and
    # the existing roots/quota publication occur at a proper C boundary.
    emit(
        "test BYTE PTR [rip+JS_FrameSlowDirectData], 16",
        "jnz interp_slow",
        f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 2",
        "jne interp_slow",
        f"test BYTE PTR [r8+{fast_byte}], {fast_mask}",
        "jnz interp_slow",
    )
    if writing:
        emit(f"cmp DWORD PTR [r8{rc:+d}], 1", "jle interp_slow")
    emit(
        "mov r9d, DWORD PTR [r13-" + str(32 if writing else 16) + "]",
        "test r9d, r9d",
        "js interp_slow",
    )
    if layout["reference_count_model"] == "allocator-prefix":
        emit(
            "or r9d, 2147483648",
            "mov eax, r9d",
            "mov rcx, 7046029254386353131",
            "imul rax, rcx",
            "shr rax, 32",
            f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
            f"mov ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
            f"lea r10, [r10+rcx*4+{fields['JSShape.hash_table'] + 4}]",
            "inc ecx",
            "imul rax, rcx",
            "shr rax, 32",
            "neg rax",
            "mov ecx, DWORD PTR [r10+rax*4-4]",
        )
    else:
        emit(
            "mov ecx, r9d",
            "or r9d, 2147483648",
            f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
            f"and ecx, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
            "neg rcx",
            "mov ecx, DWORD PTR [r10+rcx*4-4]",
            f"add r10, {fields['JSShape.prop']}",
        )
    label(p + "_probe")
    emit(
        "test ecx, ecx",
        "jz interp_slow",
        "lea r11, [r10+rcx*8-8]",
        "cmp DWORD PTR [r11+4], r9d",
        "je " + p + "_found",
        "mov ecx, DWORD PTR [r11]",
        "and ecx, 67108863",
        "jmp " + p + "_probe",
    )
    label(p + "_found")
    if writing:
        # Same writable ordinary-data / non-length proof as the existing by-id
        # native store. A reference-valued old slot retains the original C
        # release order, including receiver/old-value aliases and finalizers.
        emit(
            "mov edx, DWORD PTR [r11]",
            "and edx, 3892314112",
            "cmp edx, 134217728",
            "jne interp_slow",
        )
    else:
        emit("test DWORD PTR [r11], 3221225472", "jnz interp_slow")
    emit(
        "dec ecx",
        "shl rcx, 4",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "add r10, rcx",
    )
    if writing:
        emit(
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
    else:
        emit(
            "mov rax, QWORD PTR [r10]",
            "mov rdx, QWORD PTR [r10+8]",
            "test edx, edx",
            "jns " + p + "_value",
            f"inc DWORD PTR [rax{rc:+d}]",
        )
        label(p + "_value")
        emit("jmp interp_" + name + "_ready")
