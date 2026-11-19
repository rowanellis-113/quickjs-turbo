"""Opcode-owned value flow, with the original final-release continuation.

Widths, keep/pop, TDZ checks and ownership are properties of each opcode.
Immediate, Dup and nonlast replacement stay in that opcode's continuation.
The last release still publishes through the inherited typed C owner.
"""

import re


def _rename(text, prefix, name):
    label = prefix + name
    old = prefix + "valueflow_original_" + name
    needle = label + ":\n"
    if text.count(needle) == 1:
        return text.replace(needle, old + ":\n", 1), old
    if prefix != ".L" or text.count(needle):
        raise ValueError("Review original value-flow entry: " + label)
    pattern = re.compile(r"(?m)^(    ARM_(?:SLOT_STORE|REF_SLOT|CHECKED_LOCAL) )" + name + r"(,)")
    text, count = pattern.subn(r"\g<1>valueflow_original_" + name + r"\2", text)
    if count != 1:
        raise ValueError("Review exact original macro entry: " + label)
    return text, old


def _local(base, first=None, operand=None):
    if first is not None:
        return f"    sub w10, w9, #ARM_OP_{first}\n    add x12, {base}, x10, lsl #4\n"
    load = "ldrb" if operand == 1 else "ldurh"
    return f"    {load} w10, [x20, #1]\n    add x12, {base}, x10, lsl #4\n"


def _capture(prefix, site, first=None):
    index = f"    sub w10, w9, #ARM_OP_{first}\n" if first else "    ldurh w10, [x20, #1]\n"
    ready = prefix + "valueflow_capture_enabled_" + site
    return (
        "    ldr w14, [sp, #ARM_VM_POLICY_OFF]\n"
        f"    tbnz w14, #3, {ready}\n"
        f"    b {prefix}slow\n"
        f"{ready}:\n" + index + "    ldr x12, [x22, #ARM_OFF_JSStackFrame_cur_func]\n"
        "    ldr x12, [x12, #ARM_OFF_JSObject_u_func_var_refs]\n"
        "    ldr x12, [x12, x10, lsl #3]\n"
        "    ldr x12, [x12, #ARM_OFF_JSVarRef_pvalue]\n"
    )


def _constant(operand):
    load = "ldrb" if operand == 1 else "ldur"
    return (
        f"    {load} w10, [x20, #1]\n"
        "    ldr x12, [x22, #ARM_OFF_JSFrame_bytecode]\n"
        "    ldr x12, [x12, #ARM_OFF_JSFunctionBytecode_cpool]\n"
        "    add x12, x12, x10, lsl #4\n"
    )


def _check(prefix, check):
    if not check:
        return ""
    condition = "eq" if check == 1 else "ne"
    return (
        "    ldr x15, [x12, #8]\n"
        "    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED\n"
        f"    b.{condition} {prefix}slow\n"
    )


def _read_reference(prefix, name, width, commit, borrow):
    stem = prefix + "valueflow_reference_" + name
    text = stem + ":\n"
    if borrow:
        text += f"""#if ARM_HAS_PROPERTY_IC
    cmp x11, #ARM_CONST_JS_TAG_OBJECT
    b.ne {stem}_dup
    ldrb w14, [x20, #{width}]
    cmp w14, #ARM_OP_get_field
    b.ne {stem}_dup
    add x20, x20, #{width}
    add x26, x26, #1
    mov x0, x10
    mov x1, x11
    b {prefix}property_borrow_entry
#endif
{stem}_dup:
"""
    return (
        text
        + f"""    ldr w14, [x10, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x10, #ARM_REF_COUNT_OFFSET]
    b {commit}
"""
    )


def _store_reference(prefix, name, width, keep, commit):
    stem = prefix + "valueflow_reference_" + name
    text = f"""{stem}:
    ldr w16, [sp, #ARM_VM_POLICY_OFF]
    tbnz w16, #0, {stem}_policy_ready
    b {prefix}slow
{stem}_policy_ready:
    tbz x15, #63, {stem}_old_ready
    ldr x14, [x12]
    ldr w16, [x14, #ARM_REF_COUNT_OFFSET]
    cmp w16, #1
    b.le {stem}_last
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x4, tpidr_el0
    add x4, x4, :tprel_hi12:qjs_aarch64_store_counters
    add x4, x4, :tprel_lo12_nc:qjs_aarch64_store_counters
    ldr x5, [x4]
    add x5, x5, #1
    str x5, [x4]
#endif
{stem}_old_ready:
"""
    if keep:
        text += f"""    tbz x11, #63, {stem}_new_ready
    ldr w16, [x10, #ARM_REF_COUNT_OFFSET]
    add w16, w16, #1
    str w16, [x10, #ARM_REF_COUNT_OFFSET]
{stem}_new_ready:
"""
    return (
        text
        + f"""    tbz x15, #63, {stem}_release_ready
// Reload after Dup because old and incoming can alias.
    ldr w16, [x14, #ARM_REF_COUNT_OFFSET]
    sub w16, w16, #1
    str w16, [x14, #ARM_REF_COUNT_OFFSET]
{stem}_release_ready:
    b {commit}
{stem}_last:
    mov x13, #{width}
    mov w17, #{keep}
    b {prefix}slot_last
"""
    )


def specialize(text):
    blocks, sites = [], []
    for prefix in [".L", ".Lpub_"]:
        for owner in ["slow", "slot_last", "property_borrow_entry"]:
            if text.count(prefix + owner + ":\n") != 1:
                raise ValueError("Review inherited observing/reference owner: " + owner)
        reads = [
            ("get_loc_short", 1, _local("x23", first="get_loc0"), 0),
            ("get_arg_short", 1, _local("x24", first="get_arg0"), 0),
            ("get_loc8", 2, _local("x23", operand=1), 0),
            ("get_loc", 3, _local("x23", operand=2), 0),
            ("get_arg", 3, _local("x24", operand=2), 0),
            (
                "get_var_ref_short",
                1,
                _capture(prefix, "get_var_ref_short", "get_var_ref0"),
                0,
            ),
            ("get_var_ref", 3, _capture(prefix, "get_var_ref"), 0),
            ("push_const8", 2, _constant(1), 0),
            ("push_const", 5, _constant(4), 0),
            ("get_loc_check", 3, _local("x23", operand=2), 1),
            ("get_var_ref_check", 3, _capture(prefix, "get_var_ref_check"), 1),
        ]
        for name, width, address, check in reads:
            text, original = _rename(text, prefix, name)
            label = prefix + name
            cold = prefix + "valueflow_reference_" + name
            commit = prefix + "valueflow_commit_" + name
            blocks.append(
                f"""{label}:
{address}{_check(prefix, check)}    ldp x10, x11, [x12]
    tbnz x11, #63, {cold}
{commit}:
    stp x10, x11, [x21], #16
    add x20, x20, #{width}
    ARM_DISPATCH_NEXT 1
"""
                + _read_reference(prefix, name, width, commit, True)
            )
            sites.append(
                dict(
                    entry=label,
                    original_entry=original,
                    width=width,
                    check=check,
                    kind="owned-read",
                    reference="original borrow/Dup with opcode-local continuation",
                )
            )
        text, original = _rename(text, prefix, "dup")
        blocks.append(
            f"""{prefix}dup:
    ldp x10, x11, [x21, #-16]
    tbnz x11, #63, {prefix}valueflow_reference_dup
{prefix}valueflow_commit_dup:
    stp x10, x11, [x21], #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
"""
            + _read_reference(prefix, "dup", 1, prefix + "valueflow_commit_dup", False)
        )
        sites.append(dict(entry=prefix + "dup", original_entry=original, kind="owned-dup"))
        writes = [
            ("put_loc_short", 1, 0, _local("x23", first="put_loc0"), 0),
            ("set_loc_short", 1, 1, _local("x23", first="set_loc0"), 0),
            ("put_arg_short", 1, 0, _local("x24", first="put_arg0"), 0),
            ("set_arg_short", 1, 1, _local("x24", first="set_arg0"), 0),
            ("put_loc8", 2, 0, _local("x23", operand=1), 0),
            ("set_loc8", 2, 1, _local("x23", operand=1), 0),
            ("put_loc", 3, 0, _local("x23", operand=2), 0),
            ("set_loc", 3, 1, _local("x23", operand=2), 0),
            ("put_arg", 3, 0, _local("x24", operand=2), 0),
            ("set_arg", 3, 1, _local("x24", operand=2), 0),
            (
                "put_var_ref_short",
                1,
                0,
                _capture(prefix, "put_var_ref_short", "put_var_ref0"),
                0,
            ),
            (
                "set_var_ref_short",
                1,
                1,
                _capture(prefix, "set_var_ref_short", "set_var_ref0"),
                0,
            ),
            ("put_var_ref", 3, 0, _capture(prefix, "put_var_ref"), 0),
            ("set_var_ref", 3, 1, _capture(prefix, "set_var_ref"), 0),
            ("put_loc_check", 3, 0, _local("x23", operand=2), 1),
            ("put_loc_check_init", 3, 0, _local("x23", operand=2), 2),
            ("put_var_ref_check", 3, 0, _capture(prefix, "put_var_ref_check"), 1),
            (
                "put_var_ref_check_init",
                3,
                0,
                _capture(prefix, "put_var_ref_check_init"),
                2,
            ),
            ("set_loc_uninitialized", 3, 1, _local("x23", operand=2), 0),
        ]
        for name, width, keep, address, check in writes:
            text, original = _rename(text, prefix, name)
            label = prefix + name
            cold = prefix + "valueflow_reference_" + name
            commit = prefix + "valueflow_commit_" + name
            pop = "" if keep else "    sub x21, x21, #16\n"
            incoming = (
                "    mov x10, #0\n    mov x11, #ARM_CONST_JS_TAG_UNINITIALIZED\n"
                if name == "set_loc_uninitialized"
                else "    ldp x10, x11, [x21, #-16]\n"
            )
            blocks.append(
                f"""{label}:
{address}{_check(prefix, check)}{incoming}    ldr x15, [x12, #8]
    orr x16, x11, x15
    tbnz x16, #63, {cold}
{commit}:
    stp x10, x11, [x12]
{pop}    add x20, x20, #{width}
    ARM_DISPATCH_NEXT 1
"""
                + _store_reference(prefix, name, width, keep, commit)
            )
            sites.append(
                dict(
                    entry=label,
                    original_entry=original,
                    last_owner=prefix + "slot_last",
                    width=width,
                    keep=keep,
                    check=check,
                    kind="owned-slot-replacement",
                )
            )
    if len(sites) != 62:
        raise ValueError("Review complete ordinary/published value-flow family")
    return text, "\n".join(blocks), sites


def cold_operator_modes(operators):
    """Keep operation selection out of already proven numeric success paths."""
    exits = []
    for prefix in [".L", ".Lpub_"]:
        for op, mode in [("add", 0), ("sub", 1), ("mul", 2), ("div", 3)]:
            entry = f"{prefix}{op}:\n    mov w17, #{mode}\n"
            if operators.count(entry) != 1:
                raise ValueError("Review operator-local mode")
            operators = operators.replace(entry, f"{prefix}{op}:\n", 1)
            first = operators.index(prefix + op + ":\n")
            target = f"    b.ne {prefix}binary_float\n"
            at = operators.index(target, first)
            cold = prefix + "valueflow_nonnumber_" + op
            operators = operators[:at] + operators[at:].replace(target, f"    b.ne {cold}\n", 1)
            exits.append(f"{cold}:\n    mov w17, #{mode}\n    b {prefix}binary_float\n")
    return operators + "\n".join(exits)
