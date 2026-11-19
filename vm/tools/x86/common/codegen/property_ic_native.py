"""Native property hits using the same bytecode-owned proof as the C VM.

No C ABI, allocation, GC or last release on a hit. Misses use the established
property boundary with its publication/unwind protocol. All old handlers are
retained for unsupported shapes and same-image policy OFF.
"""


def enabled(build):
    return "QJS_PROPERTY_IC:BOOL=ON" in (build / "CMakeCache.txt").read_text(encoding="utf-8")


def blocks(build, abi, generation, fallbacks=None, method_learning=False):
    fields = abi["offsets"]
    assert abi["reference_count_model"] == "inline-header"
    # Windows profiles describe the original core followed by owned tails.
    # Linux measures the complete overlaid types, including those fields.
    bc_extra = fields.get("JSFunctionBytecode.property_ic", abi["sizes"]["JSFunctionBytecode"])
    rt_extra = fields.get("JSRuntime.property_ic_epoch", abi["sizes"]["JSRuntime"])
    exotic_byte, exotic_mask = abi["bits"]["JSObject.is_exotic"][0]
    proto_byte, proto_mask = abi["bits"]["JSObject.is_prototype"][0]
    ext_byte, ext_mask = abi["bits"]["JSObject.extensible"][0]
    entries, external, contracts = [], {"JS_FrameInterpPropertyCold_unwind"}, []
    for family in generation["aliases"]:
        original_prefix = "" if family == "M" else "dirty_"
        for kind, op in ((1, "get_field"), (2, "get_field2"), (3, "put_field")):
            name = "JS_FrameOwnBytecode" + family + str(kind)
            original = original_prefix + "interp_" + op
            slow = original_prefix + "interp_property_slow_" + op
            external.update((original, slow))
            p = "property_ic_" + family + str(kind)
            miss, legacy, ready = p + "_miss", p + "_legacy", p + "_ready"
            receiver_slot = 32 if kind == 3 else 16
            g = [
                "cmp DWORD PTR [r13-" + str(receiver_slot - 8) + "], -1",
                "jne " + p + "_primitive",
                "mov r8, QWORD PTR [r13-" + str(receiver_slot) + "]",
            ]
            if kind != 2:
                g += ["cmp DWORD PTR [r8], 1", "jle " + slow]
            # Arrays/typed arrays and other exotic receivers retain the R9
            # dispatch before metadata lookup. They cannot learn prototype or
            # transition ways; routing every method/length miss through the IC
            # adds an otherwise unproductive C boundary on every operation.
            g += [
                f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
                "jnz " + legacy,
                "mov r11, QWORD PTR [rbp+80]",
                f"mov r10, QWORD PTR [r11+{bc_extra}]",
                "cmp r10, 1",
                "je " + legacy,
                "test r10, r10",
                "jz " + miss,
                # Code buffers are4-aligned. Compute the relative index
                # independently of the IC slab load,then address its map
                # directly; no extra storage or change to cache ownership.
                "mov rcx, r12",
                f"sub rcx, QWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_buf']}]",
                "shr rcx, 2",
                "mov r11, QWORD PTR [r10+rcx*8+56]",
                "test r11, r11",
                "jz " + legacy,
                f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
                "cmp QWORD PTR [r11], r10",
                "jne " + p + "_site_miss",
                p + "_matched:",
            ]
            if kind == 3:
                g += [
                    "cmp DWORD PTR [r11+12], 4",
                    "je " + p + "_replace",
                    "cmp DWORD PTR [r11+12], 5",
                    "jne " + miss,
                    f"test BYTE PTR [r8+{ext_byte}], {ext_mask}",
                    "jz " + slow,
                    f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
                    "jnz " + slow,
                    f"test BYTE PTR [r8+{proto_byte}], {proto_mask}",
                    "jnz " + slow,
                    "mov rdx, QWORD PTR [rbx+56]",
                    f"mov rax, QWORD PTR [rdx+{rt_extra}]",
                    "test rax, rax",
                    "jz " + slow,
                    "cmp QWORD PTR [r11+24], rax",
                    "jne " + miss,
                    "mov rax, QWORD PTR [r11+32]",
                    f"test BYTE PTR [rax+{fields['JSShape.is_hashed']}], 64",
                    "jz " + p + "_target_active",
                    f"and BYTE PTR [rax+{fields['JSShape.is_hashed']}], 191",
                    f"mov rcx, QWORD PTR [rax+{fields['JSShape.proto']}]",
                    "inc DWORD PTR [rcx]",
                    p + "_target_active:",
                    "inc DWORD PTR [rax]",
                    f"mov QWORD PTR [r8+{fields['JSObject.shape']}], rax",
                    "dec DWORD PTR [r10]",
                    f"test DWORD PTR [rdx+{rt_extra + 12}], 4",
                    "jnz " + p + "_store",
                    f"mov ecx, DWORD PTR [r10+{fields['JSShape.is_hashed']}]",
                    "shr ecx, 8",
                    "cmp DWORD PTR [r10], ecx",
                    "jne " + p + "_store",
                    f"mov rcx, QWORD PTR [r10+{fields['JSShape.proto']}]",
                    "test rcx, rcx",
                    "jz " + p + "_store",
                    f"or BYTE PTR [r10+{fields['JSShape.is_hashed']}], 64",
                    # Successor owns the same prototype before this decref;
                    # it cannot be a last release or require a C boundary.
                    "dec DWORD PTR [rcx]",
                    "jmp " + p + "_store",
                    p + "_replace:",
                    "mov ecx, DWORD PTR [r11+8]",
                    "shl rcx, 4",
                    f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
                    "cmp DWORD PTR [rcx+8], 0",
                    "jge " + p + "_store_at",
                    "mov rax, QWORD PTR [rcx]",
                    "cmp DWORD PTR [rax], 1",
                    "jle " + slow,
                    # Replacing obj.value===obj also consumes the receiver
                    # operand. Two references would BOTH be released here;
                    # defer the final release to the published C boundary.
                    "cmp rax, r8",
                    "jne " + p + "_old_ref_safe",
                    "cmp DWORD PTR [rax], 2",
                    "jle " + slow,
                    p + "_old_ref_safe:",
                    "dec DWORD PTR [rax]",
                    "jmp " + p + "_store_at",
                    p + "_store:",
                    "mov ecx, DWORD PTR [r11+8]",
                    "shl rcx, 4",
                    f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
                    p + "_store_at:",
                    "mov rax, QWORD PTR [r13-16]",
                    "mov rdx, QWORD PTR [r13-8]",
                    "mov QWORD PTR [rcx], rax",
                    "mov QWORD PTR [rcx+8], rdx",
                    "dec DWORD PTR [r8]",
                    "sub r13, 32",
                    "add r12, 5",
                    "movzx eax, BYTE PTR [r12]",
                    "jmp QWORD PTR [rdi+rax*8]",
                ]
            else:
                g += [
                    "cmp DWORD PTR [r11+12], 1",
                    "je " + p + "_own",
                    f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
                    "jnz " + legacy,
                    "mov rax, QWORD PTR [rbx+56]",
                    f"mov rax, QWORD PTR [rax+{rt_extra}]",
                    "test rax, rax",
                    "jz " + miss,
                    "cmp QWORD PTR [r11+24], rax",
                    "jne " + miss,
                    "cmp DWORD PTR [r11+12], 3",
                    "je " + p + "_unset",
                    "cmp DWORD PTR [r11+12], 2",
                    "jne " + miss,
                    "mov r10, QWORD PTR [r11+16]",
                    "jmp " + p + "_load",
                    p + "_own:",
                    "mov r10, r8",
                    p + "_load:",
                    "mov ecx, DWORD PTR [r11+8]",
                    "shl rcx, 4",
                    f"add rcx, QWORD PTR [r10+{fields['JSObject.prop']}]",
                    "mov rax, QWORD PTR [rcx]",
                    "mov rdx, QWORD PTR [rcx+8]",
                    "test edx, edx",
                    "jns " + ready,
                    "inc DWORD PTR [rax]",
                    "jmp " + ready,
                    p + "_unset:",
                    "xor eax, eax",
                    "mov edx, 3",
                    ready + ":",
                ]
                if kind == 1:
                    g += [
                        "dec DWORD PTR [r8]",
                        "mov QWORD PTR [r13-16], rax",
                        "mov QWORD PTR [r13-8], rdx",
                    ]
                else:
                    g += ["mov QWORD PTR [r13], rax", "mov QWORD PTR [r13+8], rdx", "add r13, 16"]
                g += ["add r12, 5", "movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"]
            # All four ways are native hits. Merely promoting a secondary
            # through C would turn alternating shapes into a C call on EVERY
            # access, losing the parent's cross-shape slot-hint coverage.
            g += [
                p + "_site_miss:",
                "cmp BYTE PTR [r11+54], 0",
                "jne " + legacy,
                "mov rax, QWORD PTR [r11+40]",
                "test rax, rax",
                "jz " + miss,
                "cmp QWORD PTR [rax], r10",
                "je " + p + "_secondary0",
                "cmp QWORD PTR [rax+40], r10",
                "je " + p + "_secondary1",
                "cmp QWORD PTR [rax+80], r10",
                "jne " + miss,
                "lea r11, [rax+80]",
                "jmp " + p + "_matched",
                p + "_secondary1:",
                "lea r11, [rax+40]",
                "jmp " + p + "_matched",
                p + "_secondary0:",
                "mov r11, rax",
                "jmp " + p + "_matched",
                miss + ":",
                "mov r10, QWORD PTR [rbx+56]",
                f"cmp DWORD PTR [r10+{rt_extra + 8}], 1",
                "jne " + legacy,
                f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
                f"cmp BYTE PTR [r10+{abi['sizes']['JSGCObjectHeader']}], 0",
                "je " + legacy,
                "jmp " + ("JS_FrameMethodICMiss" if method_learning and kind == 2 else slow),
                legacy + ":",
            ]
            if kind != 3 and fallbacks:
                external.add("JS_FrameOwnBytecodeData")
                g += [
                    "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData], 1",
                    "jne " + p + "_primitive",
                    # IC hit/map capacity is independent of the old tail.
                    "mov r11, QWORD PTR [rbp+80]",
                    f"cmp DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}], 2048",
                    "ja " + p + "_primitive",
                    "jmp " + fallbacks[original],
                ]
            else:
                g += ["jmp " + original]
            g += [p + "_primitive:", "jmp " + original]
            local = {line[:-1] for line in g if line.endswith(":")}
            for line in g:
                assert not line.startswith(("call ", "ret", "push ", "pop ")) and "rsp" not in line
                if line.startswith(("j",)):
                    target = line.split(" ", 1)[1]
                    if target not in local and not target.startswith("QWORD "):
                        external.add(target)
            entries.append((name, g))
            contracts.append(
                dict(
                    family=family,
                    kind=kind,
                    entry=name,
                    original_entry=original,
                    miss=slow,
                    cache="bytecode-owned C/native IC; retained immutable hashed shapes, prototype epoch, all four ways checked natively",
                    ownership="Get duplicates before receiver decref; replace declines before any last release; transition activates the successor prototype edge before weakening an IC-only predecessor of exactly the same prototype; no last release",
                    ABI="Original PC/SP/frame/table registers; volatile GPRs only; no call or RSP access; existing root-VM CFI",
                    status="unqualified candidate",
                )
            )
    if method_learning:
        # A legacy prototype hit used to complete an IC miss before the C
        # learner could fill this site. Enter the original published C path
        # only for cacheable M2 misses; mega/dictionary/OFF stay on old tails.
        assert (
            generation["msvc"]
            and set(generation["aliases"]) == {"M"}
            and not generation["diagnostics"]
        )
        assert abi["reference_count_model"] == "inline-header"
        external.update(
            (
                "JS_FrameOwnBytecodeData",
                "interp_property_slow_get_field2",
                "JS_FrameStringProtoFallback",
            )
        )
        publication = [
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov rcx, rbx",
        ]
        body = [
            "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData+4], 1",
            "jne interp_property_slow_get_field2",
            *publication,
            "jmp JS_FrameStringProtoFallback",
        ]
        assert all(
            not line.startswith(("call ", "ret", "push ", "pop ")) and "rsp" not in line
            for line in body
        )
        entries.append(("JS_FrameMethodICMiss", body))
        contracts.append(
            dict(
                entry="JS_FrameMethodICMiss",
                family="M",
                kind=2,
                publication=publication,
                ownership="Original owned receiver and complete C getter/IC learner; no partial result or new owner before publication",
                ABI="Original full slow publication and StringProto C fallback/return, unchanged root VM CFI",
                policy="MSVC normal inline-header only; reserved[2] presence-disable policy; no extra checks on IC hits",
                status="isolated candidate, not qualified",
            )
        )
    # Whole-suite net supports the GNU backend; omit both the hot checks
    # and unused helper on MSVC, rather than merely switching its hits off.
    if "P" not in generation["aliases"]:
        return entries, external, generation, contracts
    # A live local/argument/closure slot already owns the receiver. Between
    # this load and a proven data-property hit there is no call or safepoint.
    # Reuse exactly the ordinary PIC proof, but materialize only its result.
    # Any unsupported/missing proof first reconstructs the original owned
    # operand and dispatches the unchanged get_field at the unchanged PC.
    ordinary = next(body for name, body in entries if name == "JS_FrameOwnBytecodeM1")
    start = ordinary.index("mov r11, QWORD PTR [rbp+80]")
    stop = ordinary.index("property_ic_M1_miss:")
    fallback = "property_ic_borrowed_fallback"
    body = [
        "mov r8, rax",
        "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData+3], 1",
        "jne " + fallback,
        f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
        "jnz " + fallback,
    ]
    replacements = {
        "property_ic_M1_miss": fallback,
        "property_ic_M1_legacy": fallback,
        "interp_property_slow_get_field": fallback,
    }
    import re

    for line in ordinary[start:stop]:
        line = re.sub(r"\b\w+\b", lambda m: replacements.get(m[0], m[0]), line)
        line = line.replace("property_ic_M1_", "property_ic_borrowed_")
        if line == "dec DWORD PTR [r8]":
            continue
        line = line.replace("[r13-16]", "[r13]").replace("[r13-8]", "[r13+8]")
        if line == "add r12, 5":
            body.append("add r13, 16")
        body.append(line)
    body += [
        fallback + ":",
        "inc DWORD PTR [r8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], -1",
        "add r13, 16",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    local = {line[:-1] for line in body if line.endswith(":")}
    assert all(
        not line.startswith(("call ", "ret", "push ", "pop ")) and "rsp" not in line
        for line in body
    )
    assert all(
        line.split(" ", 1)[1] in local or line.startswith("jmp QWORD ")
        for line in body
        if line.startswith("j")
    )
    entries.append(("JS_FrameBorrowedField", body))
    external.add("JS_FrameOwnBytecodeData")
    contracts.append(
        dict(
            entry="JS_FrameBorrowedField",
            cache="Identical existing four-way own/prototype/unset PIC guards; no new metadata/owners",
            ownership="Live slot borrows receiver without a safepoint; duplicate result before publishing; every miss reconstructs original owned operand before original dispatch",
            ABI="Same PC/frame/table/VM stack registers, volatile GPRs only; no CALL/RSP; existing root unwind",
            status="unqualified experiment",
        )
    )
    return entries, external, generation, contracts


def global_cell_probe(abi, prefix, ready, relink, *, measured_tail=False):
    """An armed borrowed value cell;no per-hit name/descriptor/slot lookup."""
    f = abi["offsets"]
    miss = prefix + "_binding_cell_miss"
    if measured_tail:
        bc_ic = f["JSFunctionBytecode.property_ic"]
        rt_mode = f["JSRuntime.property_ic_mode"]
        ic_map = f["JSPropertyIC.map"]
        if not (
            0 <= bc_ic <= abi["sizes"]["JSFunctionBytecode"] - 8
            and 0 <= rt_mode <= abi["sizes"]["JSRuntime"] - 4
            and ic_map == abi["sizes"]["JSPropertyIC"]
        ):
            raise ValueError("Review measured global-cell private field extents")
    else:
        # The inherited Win64 package binds its original pre-overlay types.
        bc_ic = abi["sizes"]["JSFunctionBytecode"]
        rt_mode = abi["sizes"]["JSRuntime"] + 8
        ic_map = 56
    return [
        "mov r11, QWORD PTR [rbp+80]",
        f"mov r10, QWORD PTR [r11+{bc_ic}]",
        "cmp r10, 1",
        "ja " + prefix + "_binding_cell_metadata",
        "je " + miss,
        "mov rcx, QWORD PTR [rbx+56]",
        f"cmp DWORD PTR [rcx+{rt_mode}], 1",
        "jne " + miss,
        "jmp " + relink,
        prefix + "_binding_cell_metadata:",
        "mov rcx, r12",
        f"sub rcx, QWORD PTR [r11+{f['JSFunctionBytecode.byte_code_buf']}]",
        "shr rcx, 2",
        f"mov rcx, QWORD PTR [r10+rcx*8+{ic_map}]",
        "test cl, 1",
        "jnz " + prefix + "_binding_cell_hit",
        "test rcx, rcx",
        "jz " + relink,
        "jmp " + miss,
        prefix + "_binding_cell_hit:",
        "mov r9, rcx",
        "and rcx, -4",
        "mov rax, QWORD PTR [rcx]",
        "mov rdx, QWORD PTR [rcx+8]",
        "cmp edx, 4",
        "jne " + ready,
        "test r9b, 2",
        "jz " + miss,
        "jmp " + ready,
        miss + ":",
    ]
