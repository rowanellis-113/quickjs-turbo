"""Reclaim x26/x27 as register-resident bytecode/cpool bias and snapshot policy flags."""

import re
from arm64.vm.specialize import _replace_exact


def _reclaim_x26_x27(text):
    # 1. Expand instrumented stack save area by 16 bytes for [sp,#128]=native_ops, [sp,#136]=slow_calls.
    text = _replace_exact(
        text,
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n#define ARM_VM_POLICY_OFF 128\n#else",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n#define ARM_VM_POLICY_OFF 144\n#else",
        1,
        "instrumented policy offset",
    )
    text = _replace_exact(
        text,
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    stp xzr, xzr, [sp, #96]\n"
        "    stp xzr, xzr, [sp, #112]\n"
        "    str xzr, [sp, #(ARM_VM_POLICY_OFF+8)]\n"
        "#endif",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    stp xzr, xzr, [sp, #96]\n"
        "    stp xzr, xzr, [sp, #112]\n"
        "    stp xzr, xzr, [sp, #128]\n"
        "    str xzr, [sp, #(ARM_VM_POLICY_OFF+8)]\n"
        "#endif",
        1,
        "instrumented counter zeroing",
    )
    text = _replace_exact(
        text,
        "    mov x1, x26\n    mov x2, x27\n    mov x3, sp",
        "    ldp x1, x2, [sp, #128]\n    mov x3, sp",
        1,
        "instrumented completion args",
    )
    text = _replace_exact(
        text,
        "    str w0, [sp, #ARM_VM_POLICY_OFF]\n"
        "    adrp x25, .Ldispatch_table\n"
        "    add x25, x25, :lo12:.Ldispatch_table\n"
        "    tbz w0, #9, .Lpublication_selected\n"
        "    adrp x25, qjs_aarch64_publish_clean\n"
        "    add x25, x25, :lo12:qjs_aarch64_publish_clean\n"
        ".Lpublication_selected:\n",
        "    str w0, [sp, #ARM_VM_POLICY_OFF]\n"
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    adrp x25, .Ldispatch_table\n"
        "    add x25, x25, :lo12:.Ldispatch_table\n"
        "    tbz w0, #9, .Lpublication_selected\n"
        "    adrp x25, qjs_aarch64_publish_clean\n"
        "    add x25, x25, :lo12:qjs_aarch64_publish_clean\n"
        "#else\n"
        "    adrp x25, .Lfast_orig_ptrs\n"
        "    add x25, x25, :lo12:.Lfast_orig_ptrs\n"
        "    tbz w0, #9, .Lpublication_selected\n"
        "    adrp x25, .Lfast_clean_ptrs\n"
        "    add x25, x25, :lo12:.Lfast_clean_ptrs\n"
        "#endif\n"
        ".Lpublication_selected:\n",
        1,
        "publication pointer table select",
    )
    text = _replace_exact(
        text,
        ".macro ARM_DISPATCH_NEXT native_ops\n"
        "    add x26, x26, #\\native_ops\n"
        "    ldrb w9, [x20]\n"
        "    ldrsw x10, [x25, x9, lsl #2]\n"
        "    add x10, x25, x10\n"
        "    br x10\n",
        ".macro ARM_DISPATCH_NEXT native_ops\n"
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    ldr x9, [sp, #128]\n"
        "    add x9, x9, #\\native_ops\n"
        "    str x9, [sp, #128]\n"
        "    ldrb w9, [x20]\n"
        "    ldrsw x10, [x25, x9, lsl #2]\n"
        "    add x10, x25, x10\n"
        "#else\n"
        "    ldrb w9, [x20]\n"
        "    ldr x10, [x25, x9, lsl #3]\n"
        "#endif\n"
        "    br x10\n",
        1,
        "ARM_DISPATCH_NEXT macro",
    )

    text, n_x26 = re.subn(
        r"(?m)^    add x26, x26, #(\d+)$",
        r"#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        r"    ldr x14, [sp, #128]\n"
        r"    add x14, x14, #\1\n"
        r"    str x14, [sp, #128]\n"
        r"#endif",
        text,
    )
    text, n_x27 = re.subn(
        r"(?m)^    add x27, x27, #(\d+)$",
        r"#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        r"    ldr x14, [sp, #136]\n"
        r"    add x14, x14, #\1\n"
        r"    str x14, [sp, #136]\n"
        r"#endif",
        text,
    )
    if n_x26 < 100 or n_x27 < 50:
        raise ValueError(f"Unexpected counter site counts: x26={n_x26}, x27={n_x27}")

    allowed_x26_x27 = {
        "stp x25, x26, [sp, #64]",
        "stp x27, x28, [sp, #80]",
        "mov x26, #0",
        "mov x27, #0",
        "ldp x25, x26, [sp, #64]",
        "ldp x27, x28, [sp, #80]",
    }
    for ln in text.splitlines():
        s = ln.strip()
        if re.search(r"\b[xw]2[67]\b", s) and s not in allowed_x26_x27:
            raise ValueError("Unexpected residual x26/x27 reference: " + s)

    x22_writes = [
        ln.strip()
        for ln in text.splitlines()
        if re.search(r"\b(ldr|mov|add|sub)\s+x22\b", ln) or re.search(r"\bldp\s+\w+,\s*x22\b", ln)
    ]
    if len(x22_writes) != 16:
        raise ValueError(f"Expected 16 x22 writes (15 frame + 1 epilogue), got {len(x22_writes)}")

    # 1b. Snapshot combined scalar/vm policy + leaf env controls + local_field bit 27 once per process.
    text = _replace_exact(
        text,
        "#ifdef QJS_AARCH64_SCALAR_OPS\n"
        "    bl qjs_aarch64_vm_scalar_policy\n"
        "#else\n"
        "    bl qjs_aarch64_vm_policy\n"
        "#endif\n"
        "    str w0, [sp, #ARM_VM_POLICY_OFF]\n",
        "    adrp x1, .Lfast_vm_leaf_env\n"
        "    add x1, x1, :lo12:.Lfast_vm_leaf_env\n"
        "    ldar w0, [x1]\n"
        "    cbz w0, .Lfast_vm_leaf_env_init\n"
        ".Lfast_vm_leaf_env_ready:\n"
        "    str w0, [sp, #ARM_VM_POLICY_OFF]\n",
        1,
        "leaf env policy snapshot",
    )

    # 2. SSA-safe fold FIRST (before inserting x26 reloads!):
    text, folded = re.subn(
        r"(?m)^    ldr x(\d+), \[x22, #ARM_OFF_JSFrame_bytecode\]\n"
        r"    (ldr[hb]? [xw]\1), \[x\1, (#[^\]]+)\]$",
        r"    \2, [x26, \3]",
        text,
    )
    text, moved = re.subn(
        r"(?m)^    ldr (x\d+), \[x22, #ARM_OFF_JSFrame_bytecode\]$",
        r"    mov \1, x26",
        text,
    )
    if folded + moved < 15:
        raise ValueError(f"Expected >=15 bytecode pointer folds, got {folded + moved}")

    # 3. Maintain x26 = frame->bytecode and x27 = 0 at all 15 frame updates.
    text, n_reload = re.subn(
        r"(?m)^    ldr x22, \[x19, #ARM_OFF_JSFrameRegisterState_frame\]\n",
        "    ldr x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]\n"
        "    ldr x26, [x22, #ARM_OFF_JSFrame_bytecode]\n"
        "    mov x27, #0\n"
        "#ifndef QJS_AARCH64_VM_INSTRUMENT\n"
        "    mov x28, #0\n"
        "#endif\n",
        text,
    )
    if n_reload != 2:
        raise ValueError(f"Expected 2 reload x26/x27 sites, got {n_reload}")

    text, n_child = re.subn(
        r"(?m)^    mov x22, x10\n",
        "    mov x22, x10\n    mov x26, x7\n    mov x27, #0\n",
        text,
    )
    if n_child != 4:
        raise ValueError(f"Expected 4 child commit x26/x27 sites, got {n_child}")

    text, n_parent = re.subn(
        r"(?m)^    mov x22, x4\n",
        "    mov x22, x4\n    ldr x26, [x22, #ARM_OFF_JSFrame_bytecode]\n    mov x27, #0\n",
        text,
    )
    if n_parent != 9:
        raise ValueError(f"Expected 9 parent restore x26/x27 sites, got {n_parent}")
    if "mov x26, x26" in text:
        raise ValueError("Self-move mov x26, x26 detected")
    return text, dict(
        x26_sites=n_x26,
        x27_sites=n_x27,
        bytecode_folds=folded,
        bytecode_moves=moved,
    )
