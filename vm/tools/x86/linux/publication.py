"""Deferred SF publication using immutable ELF tables and shared return phases.

RDI is the private publication token. The original table/handlers remain the
component OFF path. Clean dispatch redirects only call/return; Dirty dispatch
uses source-derived copies whose observing C tails first ensure publication.
"""

import hashlib
import json
import re
from c_workers import module

CLEAN = "JS_FramePublishTable"
DIRTY = "JS_FramePublishDirtyTable"
SELECT = "JS_FrameLinuxPublishSelect"


def labels(rows):
    return {m[1] for row in rows if (m := re.fullmatch(r"(\w+):", row))}


def once(rows, before, after):
    text = "\n".join(rows)
    if text.count(before) != 1:
        raise ValueError("Review Linux publication anchor: " + before[:120])
    return text.replace(before, after).splitlines()


def generate(
    source,
    output,
    stream,
    blocks,
    handlers,
    forward_leaves,
    layout,
    dirty_stats_banks=None,
    shared_blocks=(),
):
    old_hash = hashlib.sha256(
        json.dumps([stream["code"], blocks, handlers], sort_keys=True).encode()
    ).hexdigest()
    code = stream["code"]
    rt = layout["offsets"]["JSRuntime.current_stack_frame"]
    start = code.index("interp_return:")
    stop = code.index("interp_call_capture_size:")
    end = code.index("interp_root_return:")
    original_return = code[start:stop]
    main = code[:start] + code[stop:end]
    defined = labels(code) | {n for n, _ in blocks}
    for _, rows in blocks:
        defined |= labels(rows)
    defined -= {"interp_root_return", "interp_exit"}
    shared_defined = {n for n, _ in shared_blocks}
    for _, rows in shared_blocks:
        shared_defined |= labels(rows)
    if shared_defined & defined:
        raise ValueError("Shared publication/global label collision")
    shared_hash = hashlib.sha256(json.dumps(shared_blocks).encode()).hexdigest()
    returns = labels(original_return)
    calls = set(
        (
            "interp_meta_call0",
            "interp_meta_call1",
            "interp_meta_call2",
            "interp_meta_call3",
            "interp_meta_call",
            "interp_meta_tail_call",
            "interp_meta_call_method",
            "interp_meta_tail_call_method",
        )
    )
    if not calls <= defined:
        raise ValueError("Review complete call/return opcode label set")
    renamed = {n: ("publish_" if n in returns or n in calls else "dirty_") + n for n in defined}
    pattern = re.compile(
        r"\b(?:" + "|".join(map(re.escape, sorted(renamed, key=len, reverse=True))) + r")\b"
    )

    def rewrite(rows):
        result = [pattern.sub(lambda m: renamed[m[0]], row) for row in rows]
        for name, delta in (dirty_stats_banks or {}).items():
            reference = re.compile(r"\[rip\+" + re.escape(name) + r"(?:\+(\d+))?\]")
            result = [
                reference.sub(
                    lambda m: "[rip+" + name + "+" + str(int(m[1] or 0) + delta) + "]", row
                )
                for row in result
            ]
        return result

    ret = rewrite(original_return)
    target = renamed["JS_FrameLinuxForwardReturn"]
    before = "\n".join(
        [
            "mov r10, QWORD PTR [rbx+56]",
            "mov rax, QWORD PTR [rbp]",
            "mov rdx, r10",
            f"mov QWORD PTR [rdx+{rt}], rax",
            "cmp BYTE PTR [rbp+62], 0",
            "jne " + target,
            "mov rbp, rax",
        ]
    )
    after = "\n".join(
        [
            "mov rax, QWORD PTR [rbp]",
            "cmp BYTE PTR [rbp+62], 0",
            "je publish_pop_child",
            "mov r10, QWORD PTR [rbx+56]",
            f"mov QWORD PTR [r10+{rt}], rax",
            "jmp " + target,
            "publish_pop_child:",
            "mov rbp, rax",
            "lea rdi, [rip+" + DIRTY + "]",
        ]
    )
    ret = once(ret, before, after)
    copies = [("JS_FrameLinuxPublishDirtyVM", rewrite(main)), ("JS_FramePublishReturn", ret)]
    push_sites = []
    for name, rows in blocks:
        cloned = rewrite(rows)
        if name in ("JS_FrameInterpCallMeta", "JS_FrameLinuxJSOwnedPush"):
            store = f"mov QWORD PTR [r10+{rt}], rbp"
            if cloned.count(store) != 1:
                raise ValueError("Review fully initialized deferred child publication: " + name)
            at = cloned.index(store)
            cloned[at] = "lea rdi, [rip+" + DIRTY + "]"
            # A read-only observer label may sit between the original load/store.
            load = at - 1 if not cloned[at - 1].endswith(":") else at - 2
            if cloned[load] != "mov r10, QWORD PTR [rbx+56]":
                raise ValueError("Review child publication runtime load: " + name)
            del cloned[load]
            push_sites.append(name)
        elif name == "JS_FrameLinuxForwardEnter":
            # Returning probes may prepare/allocate through C. Retain this
            # original coherent boundary and acknowledge the actual publication.
            store = f"mov QWORD PTR [r10+{rt}], rbp"
            if cloned.count(store) != 1:
                raise ValueError("Review forwarding parent coherence boundary")
            at = cloned.index(store) + 1
            cloned[at:at] = ["lea rdi, [rip+" + CLEAN + "]"]
        elif name == "JS_FrameOwnBytecodeM2":
            # Fuse Dirty get_field2 -> 0-arg OP_call_method to eliminate indirect
            # dispatch mispredictions on obj.method() calls.
            call_method_op = stream["opcodes"].index("call_method")
            cloned = once(
                cloned,
                "movzx eax, BYTE PTR [r12]\njmp QWORD PTR [rdi+rax*8]",
                "movzx eax, BYTE PTR [r12]\n"
                f"cmp al, {call_method_op}\n"
                f"je {renamed['interp_meta_call_method']}\n"
                "jmp QWORD PTR [rdi+rax*8]",
            )
        copies.append((renamed[name], cloned))

    # Derive the actual current helper set rather than copying Win-only names.
    original_defined = defined | {
        "interp_root_return",
        "interp_exit",
        *(n for n, _ in forward_leaves),
    }
    for _, rows in forward_leaves:
        original_defined |= labels(rows)
    # Shared continuations may branch into an original or Dirty VM handler.
    original_defined |= shared_defined | {n for n, _ in copies}
    for _, rows in copies:
        original_defined |= labels(rows)
    targets = set()
    for rows in [code, *(v for _, v in blocks), *(v for _, v in shared_blocks)]:
        for row in rows:
            m = re.fullmatch(r"(?:call|j\w+) (\w+)", row)
            if m and (m[1] not in original_defined or m[1] == "JS_FrameInterpHostDispatch"):
                targets.add(m[1])
    # This exact-source uint64_t helper neither allocates nor calls JavaScript.
    pure = {
        "JS_FrameLocaleCompareCompound",
        "JS_FrameSlowDirectTryInstanceOfLeaf",
        "JS_LinuxComparisonInit",
        "JS_LinuxLooseEqInit",
        "JS_LinuxGlobalBindingInit",
    } & targets
    observing = targets - pure
    for _, rows in shared_blocks:
        for row in rows:
            m = re.fullmatch(r"(?:call|j\w+) (\w+)", row)
            if m and m[1] in observing:
                raise ValueError("Shared global continuation observes unpublished SF: " + row)
    if any(not n.startswith("JS_") for n in observing):
        raise ValueError("Unreviewed publication C transfer: " + repr(sorted(observing)))
    proxies = {n: "JS_FramePublishBefore_" + n.removeprefix("JS_") for n in observing}
    used = set()

    def boundary(rows):
        result = []
        for row in rows:
            m = re.fullmatch(r"(call|j\w+) (\w+)", row)
            if m and m[2] in proxies:
                used.add(m[2])
                row = m[1] + " " + proxies[m[2]]
            result.append(row)
        return result

    copies = [(n, boundary(rows)) for n, rows in copies]
    if used != observing:
        raise ValueError("Incomplete observing C publication coverage: " + repr(observing - used))
    ret = next(rows for n, rows in copies if n == "JS_FramePublishReturn")
    shared = module(source, "publish-boundary")
    known, known_table = shared.known_return_body(ret, layout["offsets"], root_return=target)
    copies.append(("JS_FramePublishKnownReturn", known))
    select = [
        "cmp BYTE PTR [rip+JS_FramePublishControl], 1",
        "je linux_publish_enabled",
        "cmp BYTE PTR [rip+JS_FramePublishControl], 2",
        "je linux_publish_disabled",
        "mov rcx, rbx",
        "call JS_LinuxPublishInit",
        "cmp eax, 1",
        "je linux_publish_enabled",
        "linux_publish_disabled:",
        "lea rdi, [rip+interp_table]",
        "jmp interp_reload",
        "linux_publish_enabled:",
        "lea rdi, [rip+" + CLEAN + "]",
        "jmp interp_reload",
    ]
    copies.append((SELECT, select))
    proxy_blocks = []
    for name in sorted(observing):
        proxy = proxies[name]
        proxy_blocks.append(
            (
                proxy,
                [
                    "lea r10, [rip+" + CLEAN + "]",
                    "cmp rdi, r10",
                    "je " + proxy + "_tail",
                    "mov rdi, r10",
                    "mov r10, QWORD PTR [rbx+56]",
                    f"mov QWORD PTR [r10+{rt}], rbp",
                    proxy + "_tail:",
                    "jmp " + name,
                ],
            )
        )
    original = [
        handlers.get(stream["opcodes"][i], "interp_slow")
        if i < len(stream["opcodes"])
        else "interp_slow"
        for i in range(256)
    ]
    clean = [
        renamed[n] if n in calls or n in ("interp_return", "interp_return_undef") else n
        for n in original
    ]
    dirty = [n if n in shared_defined else known_table.get(n, renamed[n]) for n in original]
    if sum(a != b for a, b in zip(original, clean)) != 10:
        raise ValueError("Review exactly eight call/two return Clean dispatch overrides")
    clone_def = {n for n, _ in copies}
    for _, rows in copies:
        clone_def |= labels(rows)
    if not set(clean + dirty) <= original_defined | clone_def:
        raise ValueError("Deferred dispatch escapes actual source-defined handlers")
    if (
        hashlib.sha256(
            json.dumps([stream["code"], blocks, handlers], sort_keys=True).encode()
        ).hexdigest()
        != old_hash
    ):
        raise ValueError("Deferred generation mutated retained OFF instruction streams")
    if hashlib.sha256(json.dumps(shared_blocks).encode()).hexdigest() != shared_hash:
        raise ValueError("Publication generation mutated shared global rows")
    record = dict(
        status="generated-not-qualified",
        entry=SELECT,
        clean_table=CLEAN,
        dirty_table=DIRTY,
        control="JS_FramePublishControl",
        tables="linker-relocated ELF .data.rel.ro;no runtime copies or writable dispatch tables",
        opcodes=256,
        table_bytes=2064,
        clean_destinations=clean,
        dirty_destinations=dirty,
        label_mapping=renamed,
        observing_helpers=sorted(observing),
        nonobserving_helpers=sorted(pure),
        proxies=[n for n, _ in proxy_blocks],
        functions=[n for n, _ in copies],
        deferred_push_sites=push_sites,
        shared_known_return_rows=len(known),
        source_files={
            n: hashlib.sha256((source / n).read_bytes()).hexdigest()
            for n in (
                "tools/x86/common/codegen/publish-boundary.py",
                "src/common/linux/interpreter-publish.inc",
                "tools/x86/linux/publication.py",
            )
        },
        frame_growth=0,
        state_growth=0,
        extra_GC_roots=0,
        dirty_stats_banks=dirty_stats_banks or {},
        scope="Complete Clean/Dirty/call-pop/two-phase return and observing-boundary protocol;native instanceof leaf remains a scalar supplement",
    )
    if shared_blocks:
        record.update(
            shared_vm_functions=[n for n, _ in shared_blocks],
            shared_rows_sha256=shared_hash,
            shared_protocol="Original Clean/Dirty token;pure init or current VM tails only",
        )
    (output / "PUBLICATION.json").write_text(json.dumps(record, indent=2) + "\n")
    return copies, proxy_blocks, record
