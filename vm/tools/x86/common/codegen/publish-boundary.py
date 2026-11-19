"""Private native VM protocol: dispatch-table pointer tracks SF publication.

Clean handlers are original instructions/addresses. Dirty VM paths are isolated
copies; only their actual C/host boundaries ensure publication. RDI is a private
output of the ensuring tail proxy, not an ordinary Win64 nonvolatile contract.
The public VM prologue/epilogue still saves/restores the caller's RDI.
The physical frame remains 128 bytes, with all ownership/quota work unchanged.
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
import re

CONTROL = "JS_FramePublishControl"
SELECT = "JS_FramePublishSelect"
TABLE = "JS_FramePublishTable"
DIRTY = "JS_FramePublishDirtyTable"
BOUNDARIES = (
    "JS_FrameNativeCallLinkDispatch",
    "JS_FrameInterpSlow",
    "JS_FrameInterpClose",
    "JS_FrameInterpFree",
    "JS_FrameInterpAddDirect",
    "JS_FrameInterpOp_sub",
    "JS_FrameInterpBig_mul",
    "JS_FrameInterpOp_div",
    "JS_FrameInterpOp_mod",
    "JS_FrameInterpOp_lt",
    "JS_FrameInterpOp_lte",
    "JS_FrameInterpOp_gt",
    "JS_FrameInterpOp_gte",
    "JS_FrameInterpOp_eq",
    "JS_FrameInterpOp_neq",
    "JS_FrameInterpOp_strict_eq",
    "JS_FrameInterpOp_strict_neq",
    "JS_FrameInterpProperty_get_field",
    "JS_FrameInterpProperty_put_field",
    "JS_FrameInterpProperty_drop",
    "JS_FrameInterpProperty_call_constructor",
    "JS_FrameNewNullObject",
    "JS_FrameAddLocalBig",
    "JS_FreeValue",
    "JS_FrameInterpProperty_get_field2",
    "JS_FrameAddLocalString",
    "JS_FrameProtoPersistentFill",
)


def proxy(target):
    return "JS_FramePublishBefore_" + target.removeprefix("JS_")


def known_return_body(returns, abi_fields, root_return="interp_root_return"):
    """Derive both no-observer return phases from the retained owner once."""

    def region(lines, start, end, include_start=False):
        return lines[lines.index(start + ":") + (not include_start) : lines.index(end + ":")]

    def labels(lines):
        return {m[1] for x in lines if (m := re.match(r"^(\w+):", x))}

    def rewrite(lines, names):
        rx = re.compile(r"\b(?:" + "|".join(map(re.escape, names)) + r")\b")
        return [rx.sub(lambda m: names[m[0]], x) for x in lines]

    def once(lines, before, after):
        text = "\n".join(lines)
        assert text.count(before) == 1, (before, text.count(before))
        return text.replace(before, after).splitlines()

    # These additional kernels are entered only from the Dirty table.
    # Keep every DC kernel, including the C cleanup continuation, unchanged.
    # Guard failures go to old Dirty slow paths; no C call can return into the
    # specialized kernels. C cleanup permanently hands control to old code.
    change = "lea rdi, [rip+" + DIRTY + "]"

    # Derive all ownership, pop, and argument-range work from the retained
    # return kernel. Only the two phase selectors and repeated Dirty selection
    # disappear. Initial close/root tests and finalizer exits remain explicit.
    callee_range = region(returns, "publish_interp_return_refs_done", "publish_interp_pop_frame")
    callee_range = once(
        callee_range, "mov DWORD PTR [rsp+60], 0\njmp publish_interp_release_values", ""
    )
    pop = region(returns, "publish_interp_pop_frame", "publish_interp_finish_call", True)
    pop = once(
        pop,
        "\n".join(
            [
                "mov rax, QWORD PTR [rbp]",
                "cmp BYTE PTR [rbp+62], 0",
                "je publish_pop_child",
                "mov r10, QWORD PTR [rbx+56]",
                f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rax",
                "jmp " + root_return,
                "publish_pop_child:",
                "mov rbp, rax",
                change,
            ]
        ),
        "mov rax, QWORD PTR [rbp]\nmov rbp, rax",
    )
    pop = once(pop, "mov DWORD PTR [rsp+60], 1\njmp publish_interp_release_values", "")
    pop = rewrite(pop, {"publish_interp_pop_frame": "known_interp_pop_frame"})
    finish = region(returns, "publish_interp_finish_call", "publish_interp_release_values", True)
    finish = rewrite(
        finish,
        {
            "publish_interp_finish_call": "known_interp_finish_call",
            "publish_interp_return_frame": "known_interp_return_frame",
        },
    )

    old_loop = region(
        returns, "publish_interp_release_loop", "publish_interp_release_finalizer", True
    )
    old_next = region(returns, "publish_interp_release_next", "publish_interp_release_done", True)

    def phase(number, destination):
        phase_names = {
            n: "known_" + n.removeprefix("publish_") + "_" + str(number)
            for n in labels(old_loop + old_next) | {"publish_interp_release_finalizer"}
        }
        result = ["cmp r10, r11", "jae " + destination]
        result += rewrite(old_loop + old_next, phase_names)
        return result

    # Put ordinary return immediately before the shared header, removing its
    # old unconditional jump. Undef retains a jump; no old instruction moves.
    known_return = [
        "known_interp_return_undef:",
        "movdqu xmm0, XMMWORD PTR [rdi+2048]",
        "jmp known_interp_return_frame",
        "known_interp_return:",
        "sub r13, 16",
        "movdqu xmm0, XMMWORD PTR [r13]",
        "known_interp_return_frame:",
        "cmp BYTE PTR [rbp+62], 0",
        "jne publish_interp_return_frame",
        "cmp WORD PTR [rbp+56], 0",
        "jne publish_interp_return_frame",
        *callee_range,
        *phase(0, "known_interp_pop_frame"),
        *pop,
        *phase(1, "known_interp_finish_call"),
        *finish,
        "known_interp_release_finalizer_0:",
        "mov DWORD PTR [rsp+60], 0",
        "jmp publish_interp_release_finalizer",
        "known_interp_release_finalizer_1:",
        "mov DWORD PTR [rsp+60], 1",
        "jmp publish_interp_release_finalizer",
    ]
    assert not any(re.match(r"^(call|ret)\b", x) for x in known_return)
    assert not any(re.match(r"^.*\brdi\s*,", x) for x in known_return)
    known_table = {n: "known_" + n for n in ("interp_return", "interp_return_undef")}

    return known_return, known_table


def append(gas, diagnostics, out):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    output = out / "quickjs-interpreter-publish-win64.S"
    if diagnostics:
        output.write_text(".intel_syntax noprefix\n.text\n", encoding="utf-8")
        return
    original = list(gas)
    code = [".intel_syntax noprefix", '.section .qjspfrm,"xr"']
    ranges = []

    def region(lines, start, end, include_start=False):
        return lines[lines.index(start + ":") + (not include_start) : lines.index(end + ":")]

    def labels(lines):
        return {m[1] for x in lines if (m := re.match(r"^(\w+):", x))}

    def rewrite(lines, names):
        rx = re.compile(r"\b(?:" + "|".join(map(re.escape, names)) + r")\b")
        return [rx.sub(lambda m: names[m[0]], x) for x in lines]

    def once(lines, before, after):
        text = "\n".join(lines)
        assert text.count(before) == 1, (before, text.count(before))
        return text.replace(before, after).splitlines()

    def emit(name, lines, unwind="JS_FrameInterpPropertyCold_unwind"):
        # Existing padding belongs to old objects only. No padding/search is
        # introduced in the new islands; alignment is the fixed function ABI.
        lines = [x for x in lines if not x.startswith((".fill ", ".org "))]
        code.extend(
            [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *lines,
                name + "_end:",
            ]
        )
        ranges.append((name, unwind))

    # Copy native opcode paths, excluding the public prologue/epilogue and
    # return kernel. No original handler or old C-call operand is rewritten.
    pieces = [
        (
            "JS_FramePublishDirtyVM",
            region(original, "interp_reload", "interp_return", True)
            + region(original, "interp_call_capture_size", "interp_root_return", True),
        ),
    ]
    for name in (
        "JS_FrameInterpPropertyCold",
        "JS_FrameInterpShortBig",
        "JS_FrameInterpPrimitiveEq",
        "JS_FrameInterpSlotCold",
        "JS_FrameNullProtoCold",
        "JS_FrameAddLocalBigCold",
        "JS_FrameSlotFreeBorrowed",
        "JS_FrameNumberPropertyEntry",
        "JS_FrameProtoLoadEntry",
    ):
        pieces.append(
            (
                "JS_FramePublishDirty_" + name.removeprefix("JS_"),
                region(original, name, name + "_end", True),
            )
        )
    # This helper is CALLed by a native opcode. Its miss tail is a C boundary;
    # hits remain ASM-only and retain Dirty until a real C boundary is reached.
    if "JS_FramePropertyReferenceStore:" in original:
        pieces.append(
            (
                "JS_FramePublishDirty_FramePropertyReferenceStore",
                region(
                    original,
                    "JS_FramePropertyReferenceStore",
                    "JS_FramePropertyReferenceStore_end",
                    True,
                ),
            )
        )
    pieces.append(
        (
            "JS_FramePublishDirtyProtoTry",
            region(original, "JS_FrameProtoPersistentTry", "JS_FrameProtoPersistentTry_end", True),
        )
    )
    local = (
        (out / "quickjs-interpreter-local-string-win64.S").read_text(encoding="utf-8").splitlines()
    )
    pieces.append(
        (
            "JS_FramePublishDirtyLocalString",
            region(local, "JS_FrameAddLocalStringCold", "JS_FrameAddLocalStringCold_end", True),
        )
    )

    calls = region(original, "JS_FrameInterpCallMeta", "JS_FrameInterpCallMeta_end")
    owned = (out / "quickjs-interpreter-owned-win64.S").read_text(encoding="utf-8").splitlines()
    joined = []
    for name in ("JS_FrameJSOwnedMissingGuard", "JS_FrameJSOwnedMissingPush"):
        joined += region(owned, name, name + "_end", True)
    wide = region(original, "JS_FrameJSWideMissingGuard", "JS_FrameJSWideMissingGuard_end")
    returns = region(original, "interp_return", "interp_call_capture_size", True)

    mapped = {n: "dirty_" + n for _, p in pieces for n in labels(p)}
    mapped.update({n: "publish_" + n for n in labels(calls + joined + returns)})
    mapped["JS_FrameJSWideMissingGuard"] = "JS_FramePublishWideMissingGuard"
    assert len(mapped) == len(set(mapped.values()))
    calls = rewrite(calls, mapped)
    joined = rewrite(joined, mapped)
    returns = rewrite(returns, mapped)
    pieces = [(n, rewrite(p, mapped)) for n, p in pieces]
    store = f"mov r10, QWORD PTR [rbx+56]\nmov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp"
    # Same work/initialization, with a table transition instead of an eager
    # global store. Every child push/pop conservatively makes publication dirty.
    calls = once(calls, store, "lea rdi, [rip+" + DIRTY + "]")
    joined = once(joined, store, "lea rdi, [rip+" + DIRTY + "]")
    before = "\n".join(
        [
            "mov r10, QWORD PTR [rbx+56]",
            "mov rax, QWORD PTR [rbp]",
            "mov rdx, r10",
            f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.current_stack_frame']}], rax",
            "cmp BYTE PTR [rbp+62], 0",
            "jne interp_root_return",
        ]
    )
    after = "\n".join(
        [
            "mov rax, QWORD PTR [rbp]",
            "cmp BYTE PTR [rbp+62], 0",
            "je publish_pop_child",
            "mov r10, QWORD PTR [rbx+56]",
            f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rax",
            "jmp interp_root_return",
            "publish_pop_child:",
        ]
    )
    returns = once(returns, before, after)
    returns = once(returns, "mov rbp, rax", "mov rbp, rax\nlea rdi, [rip+" + DIRTY + "]")

    used = set()

    def boundary(lines):
        result = []
        for line in lines:
            m = re.fullmatch(r"(call|jmp) (\w+)", line)
            if m and m[2] in BOUNDARIES:
                used.add(m[2])
                line = m[1] + " " + proxy(m[2])
            result.append(line)
        return result

    emit("JS_FramePublishCallMeta", boundary(calls))
    emit("JS_FramePublishOwnedMissing", boundary(joined))
    emit("JS_FramePublishReturn", boundary(returns))
    for name, lines in pieces:
        emit(
            name,
            boundary(lines),
            "JS_FrameInterpAddDirect_unwind"
            if name == "JS_FramePublishDirtyProtoTry"
            else "JS_FrameInterpPropertyCold_unwind",
        )
    assert used == set(BOUNDARIES), (set(BOUNDARIES) - used, used - set(BOUNDARIES))
    for target in sorted(used):
        # A cloned path can continue after an earlier C call, or a new call
        # kernel can fall back while already Clean. Ensure, rather than
        # assuming Dirty. R10 is volatile and is no original callee input.
        emit(
            proxy(target),
            [
                "lea r10, [rip+" + TABLE + "]",
                "cmp rdi, r10",
                "je " + proxy(target) + "_tail",
                "mov rdi, r10",
                "mov r10, QWORD PTR [rbx+56]",
                f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp",
                proxy(target) + "_tail:",
                "jmp " + target,
            ],
            "JS_FrameInterpAddDirect_unwind",
        )

    known, known_table = known_return_body(returns, abi_fields)
    known_parts = [("JS_FramePublishKnownReturn", known)]

    table_at = original.index("interp_table:") + 1
    table_end = next(
        i for i in range(table_at, len(original)) if original[i].startswith(".section ")
    )
    table = original[table_at:table_end]
    assert len(table) == 257 and table[-1] == ".quad 0, 3"
    call_returns = set(
        (
            "interp_meta_call0",
            "interp_meta_call1",
            "interp_meta_call2",
            "interp_meta_call3",
            "interp_meta_call",
            "interp_meta_tail_call",
            "interp_meta_call_method",
            "interp_meta_tail_call_method",
            "interp_return",
            "interp_return_undef",
        )
    )
    clean = [
        mapped.get(n, n) if n in call_returns else n
        for line in table
        for n in (line.removeprefix(".quad "),)
    ]
    dirty = [mapped.get(line.removeprefix(".quad "), line.removeprefix(".quad ")) for line in table]
    dirty = [
        known_table.get(line.removeprefix(".quad "), target) for line, target in zip(table, dirty)
    ]
    # Only the ordinary Dirty instanceof table slot reaches this no-observer
    # C ABI. A miss changes no VM state and enters its original full boundary.
    # The cold helper configures switches only after normal publication.
    opcode_names = re.findall(
        r"^\s*DEF\(\s*(\w+)",
        _frame_source_file(_frame_project_root(), "quickjs-opcode.h").read_text(encoding="utf-8"),
        re.M,
    )
    instance_opcode = opcode_names.index("instanceof")
    assert table[instance_opcode] == ".quad interp_slow"
    assert dirty[instance_opcode] == "dirty_interp_slow"
    dirty[instance_opcode] = "JS_FramePublishInstanceOfLeaf"
    assert sum(a != b.removeprefix(".quad ") for a, b in zip(clean, table)) == 10
    assert all(n in mapped for n in call_returns)

    selector = [
        "cmp BYTE PTR [rip+" + CONTROL + "], 1",
        "je publish_new_table",
        "cmp BYTE PTR [rip+" + CONTROL + "], 2",
        "je publish_original_table",
        "xor eax, eax",
        "mov cl, 3",
        "lock cmpxchg BYTE PTR [rip+" + CONTROL + "], cl",
        "jne publish_config_wait",
        "lea rcx, [rip+JS_FramePublishDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "jnz publish_config_disabled",
    ]
    for destination, new_table in ((TABLE, clean), (DIRTY, dirty)):
        selector += [
            "lea rsi, [rip+interp_table]",
            "lea rdi, [rip+" + destination + "]",
            "mov ecx, 258",
            "rep movsq",
        ]
        for i, (before, after) in enumerate(zip(table, new_table)):
            if before != ".quad " + after:
                selector += [
                    "lea r10, [rip+" + after + "]",
                    "mov QWORD PTR [rip+" + destination + "+" + str(8 * i) + "], r10",
                ]
    # CAS owner publishes both complete tables together; x86 TSO release byte1.
    selector += [
        "mov BYTE PTR [rip+" + CONTROL + "], 1",
        "jmp " + SELECT,
        "publish_config_disabled:",
        "mov BYTE PTR [rip+" + CONTROL + "], 2",
        "jmp " + SELECT,
        "publish_config_wait:",
        "pause",
        "jmp " + SELECT,
        "publish_new_table:",
        "lea rdi, [rip+" + TABLE + "]",
        "jmp interp_reload",
        "publish_original_table:",
        "lea rdi, [rip+interp_table]",
        "jmp interp_reload",
    ]
    emit(SELECT, selector)

    # Append after all old RX/RO/RW islands; no searched layout setting.
    code.append('.section .qjsknown,"xr"')
    for name, lines in known_parts:
        emit(name, lines)

    # Keep every inherited publication kernel and section contribution intact.
    # Only same-width branch operands enter this separate cold admission island.
    # Its push targets the inherited deferred-publication owned kernel, preserving
    # the Dirty table transition and all initialization/ownership/GC boundaries.
    code.append('.section .qjszjw,"xr"')
    emit("JS_FramePublishWideMissingGuard", boundary(rewrite(wide, mapped)))

    # The original VM already owns its Win64 shadow space and nonvolatiles.
    # Retain the existing physical-stack margin before this bounded C call.
    # No frame/root/cursor publication is needed until the proof rejects.
    emit(
        "JS_FramePublishInstanceOfLeaf",
        [
            "mov rax, rsp",
            "sub rax, QWORD PTR [rbx+32]",
            "jc instance_leaf_miss",
            "sub rax, 8192",
            "jc instance_leaf_miss",
            "cmp rax, QWORD PTR [rbx+72]",
            "jb instance_leaf_miss",
            "mov rcx, rsi",
            "mov rdx, r13",
            "call JS_FrameSlowDirectTryInstanceOfLeaf",
            "test eax, eax",
            "jz instance_leaf_miss",
            "sub r13, 16",
            "add r12, 1",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
            "instance_leaf_miss:",
            "jmp dirty_interp_slow",
        ],
    )

    native = out / "quickjs-interpreter-native-slice-win64.S"
    text = native.read_text(encoding="utf-8")
    old = "JS_FrameNativeLifetimeEntry:\nmov QWORD PTR [rbx+96], 0\nlea rdi, [rip+interp_table]"
    assert text.count(old) == 1
    native.write_text(
        text.replace(
            old,
            "JS_FrameNativeLifetimeEntry:\nmov QWORD PTR [rbx+96], 0\njmp " + SELECT + "\nnop\nnop",
        ),
        encoding="utf-8",
    )

    # Export only original labels referenced by new islands; declarations add
    # no original RX/RO data. Old handlers and generated local helper are exact.
    old_labels = labels(original)
    refs = set(re.findall(r"\b\w+\b", "\n".join(code)))
    globals_needed = sorted(
        (refs & old_labels)
        | {"JS_FrameInterpPropertyCold_unwind", "JS_FrameInterpAddDirect_unwind"}
    )
    gas[:0] = [".globl " + ", ".join(globals_needed)]
    assert gas[1:] == original
    assert (out / "quickjs-interpreter-local-string-win64.S").read_text(
        encoding="utf-8"
    ).splitlines() == local
    code += [
        '.section .qjspfro,"dr"',
        "JS_FramePublishDisable:",
        '.asciz "QJS_DISABLE_DEFERRED_FRAME_PUBLISH"',
        '.section .qjspfwr,"dw"',
        ".globl " + CONTROL,
        CONTROL + ":",
        ".byte 0",
        ".p2align 3",
        ".globl " + TABLE,
        TABLE + ":",
        ".zero 2064",
        ".globl " + DIRTY,
        DIRTY + ":",
        ".zero 2064",
        '.section .pdata$zzpublish,"dr"',
        ".p2align 2",
    ]
    for name, unwind in ranges:
        code.append(".rva " + name + ", " + name + "_end, " + unwind)
    import json

    (out / "quickjs-interpreter-known-dirty-proof.json").write_text(
        json.dumps(
            dict(
                state="Dirty on every specialized entry and all native dispatch exits",
                dirty_table_overrides=[
                    dict(
                        slot=i,
                        original=line.removeprefix(".quad "),
                        parent=mapped[line.removeprefix(".quad ")],
                        target=known_table[line.removeprefix(".quad ")],
                    )
                    for i, line in enumerate(table)
                    if line.removeprefix(".quad ") in known_table
                ],
                kernels=[name for name, _ in known_parts],
                C_handoffs=["publish_interp_return_frame", "publish_interp_release_finalizer"],
                callee_phase_flag=0,
                parent_argument_phase_flag=1,
                physical_frame_bytes=128,
                unchanged="All DC code/data retained except two cold Dirty-table LEA target displacements.",
            ),
            indent=2,
        )
        + "\n"
    )
    output.write_text("\n".join(code) + "\n", encoding="utf-8")
