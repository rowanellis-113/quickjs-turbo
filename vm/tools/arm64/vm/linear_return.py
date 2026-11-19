"""Consume ordinary return ranges once, retaining typed observing release.

The inherited no-capture/constructor/exception boundaries remain before any
consumption. Callee slots are detached and released, the exact inherited pop
publishes the caller, then pending caller operands are detached and released.
No partial interval can enter a whole-range C fallback.
"""

import hashlib
import json
import re


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parent(text, prefix, stem):
    start = text.index("    mov x4, #0\n", text.index(prefix + "return_prepare:\n"))
    end = text.index(prefix + "return_parent_pending:\n", start)
    block = text[start:end]
    for line in ["    mov x6, #0\n", "    mov x7, #0\n", "    mov w17, #0\n"]:
        if block.count(line) != 1:
            raise ValueError("Review original parent selection scratch")
        block = block.replace(line, "", 1)
    for name in ["return_parent_pending", "return_ranges_ready"]:
        block = block.replace(prefix + name, stem + "_parent_selected")
    for name in ["return_root_classified", "return_forward_parent"]:
        block = block.replace(prefix + name, stem + "_" + name)
    return block + stem + "_parent_selected:\n"


def _pop(text, prefix, stem):
    start = text.index(prefix + "return_pop:\n")
    finish = "    cbz x4, " + prefix + "return_root\n"
    end = text.index(finish, start)
    block = text[start:end]
    definitions = re.findall(r"(?m)^(\.L\w+):$", block)
    if prefix + "return_pop" not in definitions:
        raise ValueError("Review inherited native pop")
    # Includes publication token/root transitions already generated for this
    # exact ordinary or published stream. Do not reconstruct their protocol.
    for label in sorted(definitions, key=len, reverse=True):
        block = block.replace(label, stem + "_pop_" + label[len(prefix) :])
    return block + "    cbz x4, " + stem + "_root\n"


def _release(prefix, stem, phase, complete, call_target):
    loop = stem + "_" + phase
    final = loop + "_last"
    restore_dirty = (
        "    adrp x25, qjs_aarch64_publish_dirty\n"
        "    add x25, x25, :lo12:qjs_aarch64_publish_dirty\n"
        if prefix == ".Lknown_" and phase == "callee"
        else ""
    )
    return f"""{loop}:
    cmp x23, x24
    b.eq {complete}
    ldp x10, x11, [x23]
    mov x12, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x12, [x23], #16
    tbz x11, #63, {loop}
    ldr w12, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w12, #1
    b.le {final}
    sub w12, w12, #1
    str w12, [x10, #ARM_REF_COUNT_OFFSET]
    b {loop}
{final}:
// The cursor already names the next slot. The old cell is detached before
// observing C and is never rewritten after legal finalizer/GC reentry.
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    mov x2, x10
    mov x3, x11
    ldr x1, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x1, [x1, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    add x27, x27, #1
    bl {call_target}
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    ldp x0, x1, [x9]
{restore_dirty}    b {loop}
"""


def specialize(source, text):
    contract_path = source / "src/arm64/linux/abi/linear-return.json"
    contract = json.loads(contract_path.read_text())
    for name, digest in contract["source_owners"].items():
        if _sha(source / name) != digest:
            raise ValueError("Review linear return source owner: " + name)
    blocks, sites = [], []
    original = text
    for prefix in [".L", ".Lpub_", ".Lknown_"]:
        stem = prefix + "linear_return"
        published = prefix != ".L"
        observing_prefix = ".Lpub_" if published else ".L"
        prepare = prefix + "return_prepare:\n"
        if text.count(prepare) != 1:
            raise ValueError("Review complete ordinary/published return entry")
        start = original.index(prepare) + len(prepare)
        end = original.index("    ldrh w9, [x22, #ARM_OFF_JSFrame_owned_args]\n", start)
        guards = original[start:end]
        if (
            "    cmp x1, #ARM_CONST_JS_TAG_EXCEPTION\n" not in guards
            or "    cbnz w9, " + prefix + "return_fallback\n" not in guards
            or "    b.eq " + prefix + "construct_return\n" not in guards
        ):
            raise ValueError("Review return exception, constructor and captures")
        final_start = original.index(observing_prefix + "host_return_final:\n")
        final_end = original.index(observing_prefix + "host_return_released:\n", final_start)
        calls = re.findall(r"(?m)^    bl (\w+)$", original[final_start:final_end])
        target = (
            "JS_FrameInterpFree" if not published else "qjs_aarch64_publish_before_FrameInterpFree"
        )
        if calls != [target]:
            raise ValueError("Review exact typed Free/publication target")
        parent = _parent(original, prefix, stem)
        # KnownReturn normally owns Dirty through pop. If our callee release
        # observes, restore Dirty on that cold continuation before resuming
        # the scan. This preserves the original pop without extra hot work.
        pop = _pop(original, prefix, stem)
        parent_move = "    mov x22, x4\n"
        pop_end = original.index("    cbz x4, " + prefix + "return_root\n")
        observer_start = original.index(parent_move, pop_end) + len(parent_move)
        observer_end = original.index(
            "    strh wzr, [x22, #ARM_OFF_JSFrame_pending]\n", observer_start
        )
        parent_observer = original[observer_start:observer_end]
        for label in sorted(re.findall(r"(?m)^(\.L\w+):$", parent_observer), key=len, reverse=True):
            parent_observer = parent_observer.replace(
                label, stem + "_parent_observer_" + label[len(prefix) :]
            )
        # return_undef falls through into this label in every inherited
        # stream. Route that fallthrough too, not only explicit branches.
        text = text.replace(
            prepare,
            "    b " + prefix + "return_prepare\n" + prefix + "linear_return_original_prepare:\n",
            1,
        )
        callee_done = stem + "_callee_done"
        caller_done = stem + "_caller_done"
        body = prepare + guards
        body += """    ldrh w9, [x22, #ARM_OFF_JSFrame_owned_args]
    sub x23, x23, x9, lsl #4
    mov x24, x2
"""
        body += _release(prefix, stem, "callee", callee_done, target)
        body += callee_done + ":\n    mov x2, x24\n" + parent + pop
        body += "    mov x22, x4\n" + parent_observer
        body += f"""    ldr x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ldrh w28, [x22, #ARM_OFF_JSFrame_pending]
    and w9, w28, #0x7fff
    ldr x24, [x22, #ARM_OFF_JSFrame_saved_sp]
    sub x23, x24, x9, lsl #4
// Keep the original live top through observing cleanup; detached holes are
// undefined. The result retains its original single owning reference.
    mov x21, x24
"""
        body += _release(prefix, stem, "caller", caller_done, target)
        tail_dirty = (
            "    adrp x25, qjs_aarch64_publish_dirty\n"
            "    add x25, x25, :lo12:qjs_aarch64_publish_dirty\n"
            if prefix == ".Lknown_"
            else ""
        )
        body += f"""{caller_done}:
    and w9, w28, #0x7fff
    sub x21, x24, x9, lsl #4
    strh wzr, [x22, #ARM_OFF_JSFrame_pending]
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
    tbnz w28, #15, {stem}_tail_parent
    stp x0, x1, [x21], #16
    b {observing_prefix}dispatch
{stem}_tail_parent:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x9, [sp, #120]
    add x9, x9, #1
    str x9, [sp, #120]
#endif
{tail_dirty}    mov x2, x21
    mov w28, #1
    b {prefix}return_prepare
{stem}_root:
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x2, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    b .Ldone
"""
        blocks.append(body)
        sites.append(
            dict(
                entry=prefix + "return_prepare",
                original_entry=prefix + "linear_return_original_prepare",
                typed_free=target,
                last_release=[stem + "_callee_last", stem + "_caller_last"],
                pop="exact inherited stream pop; observing callee continuation restores Known Dirty token, and Known tail continuation restores Dirty before constructor/fallback guards",
                lease="x23/x24 cursors and existing x28 flags; original CFA and result spill",
                ordering="detach/release callee, original pop, detach/release caller, result or tail",
                original_no_capture_and_constructor_guards=True,
                fixed_cell_limit_removed=True,
                partial_range_C_fallback=False,
            )
        )
    return (
        text,
        "\n".join(blocks),
        dict(
            enabled=True,
            contract_sha256=_sha(contract_path),
            sites=sites,
            physical_frame_growth=0,
            public_ABI_growth=0,
            private_compiler_fingerprints_updated=False,
        ),
    )
