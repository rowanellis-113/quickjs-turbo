"""Accepted reference-slot ownership,with measured ELF/SysV boundaries."""

import hashlib
from arguments import asm_body
from c_workers import module

OWNER = "tools/x86/common/codegen/slot-store.py"
OWNER_SHA = "8a31469609990b677b03e941f9139547b6805bc2f77bb46dbc7149684e57628a"


def append(source, stream, layout):
    if hashlib.sha256((source / OWNER).read_bytes()).hexdigest() != OWNER_SHA:
        raise ValueError("Review accepted complete slot-store factory")
    fields = layout["offsets"]
    mode = fields["JSRuntime.module_normalize_has_attr"] + 5
    prefix_rc = layout["reference_count_model"] == "allocator-prefix"
    rc_off = (
        fields["JSMallocBlockHeader.ref_count"] - fields["JSMallocBlockHeader.user_data"]
        if prefix_rc
        else fields["JSGCObjectHeader.ref_count"]
    )
    if (
        layout["reference_count_model"] not in ("inline-header", "allocator-prefix")
        or layout["sizes"]["JSValue"] != 16
        or (not prefix_rc and rc_off != 0)
        or not fields["JSRuntime.module_normalize_has_attr"]
        < mode
        < fields["JSRuntime.normalize_u"]
    ):
        raise ValueError("Review actual slot mode padding and inline reference ABI")
    entries = stream["reference_stores"]
    if not entries or any(
        action not in ("put", "set") or size not in (1, 2, 3) for _, action, size in entries
    ):
        raise ValueError("Review actual reference-slot producers")
    owner = module(source, "slot-store")
    owner.load_layout = lambda _: layout
    masm, gas = ["END"], []
    owner.append(masm, gas, entries, False, source)
    rows = asm_body(source, OWNER, "JS_FrameInterpSlotCold", layout, expanded="\n".join(gas))
    first = rows.index("slot_store_config:")
    # The shared factory retains its complete incoming-value/alias/finalizer
    # order. Use the already-qualified C free/quota wrapper,not a second
    # handwritten release protocol. Published SF is the consumed/next view.
    rows = rows[:first]
    needle = "jmp JS_FrameSlotFreeBorrowed"
    if rows.count(needle) != 1:
        raise ValueError("Review accepted final-release boundary")
    i = rows.index(needle)
    rows[i : i + 1] = [
        f"mov QWORD PTR [rbp+{fields['JSStackFrame.cur_pc']}], r12",
        f"mov QWORD PTR [rbp+{fields['JSStackFrame.cur_sp']}], r13",
        "call JS_FrameInterpFree",
    ]
    # libc getenv uses RDI/RAX and may clobber the private VM RDI/RSI.
    # Its non-JS setup call leases only existing scratch32..63;R10 is reloaded.
    rows += [
        "slot_store_config:",
        "mov QWORD PTR [rsp+32], r8",
        "mov QWORD PTR [rsp+40], r9",
        "mov QWORD PTR [rsp+48], rdi",
        "mov QWORD PTR [rsp+56], rsi",
        "lea rdi, [rip+JS_LinuxSlotDisable]",
        "call getenv@PLT",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov r10, QWORD PTR [rbx+56]",
        f"mov BYTE PTR [r10+{mode}], r11b",
        "mov r8, QWORD PTR [rsp+32]",
        "mov r9, QWORD PTR [rsp+40]",
        "mov rdi, QWORD PTR [rsp+48]",
        "mov rsi, QWORD PTR [rsp+56]",
        "jmp slot_store_common",
    ]
    record = dict(
        owner=OWNER,
        owner_sha256=OWNER_SHA,
        source_files={
            "tools/x86/linux/slot_store.py": hashlib.sha256(
                (source / "tools/x86/linux/slot_store.py").read_bytes()
            ).hexdigest()
        },
        mode_offset=mode,
        control="QJS_DISABLE_NATIVE_SLOT_STORE",
        control_presence=True,
        entries=entries,
        functions=["JS_LinuxSlotCold"],
        new_frame_bytes=0,
        new_public_or_runtime_fields=0,
        existing_padding_bytes_used=1,
        final_release="Commit incoming slot/PC/SP before existing JS_FrameInterpFree;no post-finalizer slot rewrite",
        libc_call="getenv@PLT actual SysV,private RDI/RSI and target/flags saved in scratch32..63;no engine callback",
        publication="Original and Dirty clones use their proper observing C free boundary",
        section=".qjs_linux_slots",
        rows_sha256=hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest(),
    )
    return [("JS_LinuxSlotCold", rows)], record


def readonly():
    return [
        '.section .qjs_linux_slots_ro,"a",@progbits',
        ".type JS_LinuxSlotDisable,@object",
        "JS_LinuxSlotDisable:",
        '.asciz "QJS_DISABLE_NATIVE_SLOT_STORE"',
        ".size JS_LinuxSlotDisable,.-JS_LinuxSlotDisable",
    ]
