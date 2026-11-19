"""Derive AAPCS64 Clean/Dirty streams from the current ARM semantic owners.

x25 is both the relative dispatch base and the private publication token.
The retained original stream is the process-presence OFF path. All observing
C calls in the derived streams use tail proxies; no new physical activation,
GC root, frame field, absolute relocation or writable dispatch table is added.
"""

import hashlib
import json
import re


CLEAN = "qjs_aarch64_publish_clean"
DIRTY = "qjs_aarch64_publish_dirty"
HELPERS = (
    "JS_FrameInterpSlow",
    "JS_FrameAArch64HostDirectValue",
    "JS_FrameAArch64HostValue",
    "JS_FrameAArch64FinishCall",
    "JS_FrameAArch64Return",
    "JS_FrameInterpRegExp",
    "JS_FrameInterpFree",
)
PURE_HELPERS = ("JS_FrameNumberPropertyConfigure", "JS_FrameAArch64ProtoFill")


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("Review ARM publication source anchor: " + before[:120])
    return text.replace(before, after, 1)


from asm_text import assembly_line_start


def table_address(name):
    return f"    adrp x25, {name}\n    add x25, x25, :lo12:{name}"


def counter(index):
    return (
        f"    ldr x10, [x9, #{index * 8}]\n    add x10, x10, #1\n    str x10, [x9, #{index * 8}]\n"
    )


TLS = """    mrs x9, tpidr_el0
    add x9, x9, :tprel_hi12:qjs_aarch64_publish_counters
    add x9, x9, :tprel_lo12_nc:qjs_aarch64_publish_counters
"""


def event(index, stale=None):
    # Only x9..x11 are clobbered, at checked dead-register locations. Never
    # call C or retain frame/value addresses in the observer's numeric ledger.
    text = "#ifdef QJS_AARCH64_VM_INSTRUMENT\n" + TLS + counter(index)
    if stale is not None:
        label = f".Lpublish_event_{index}_coherent"
        text += (
            """    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    cmp x11, x22
"""
            + f"    b.eq {label}\n"
            + counter(stale)
            + label
            + ":\n"
        )
    return text + "#endif\n"


def phase_return(body):
    """Derive independent callee/caller guard and release phases once.

    Preserve the initial capture/root/alias-count guards and exact C cleanup
    exits. The Dirty entry already owns its token, so ordinary pop need not
    select Dirty again. A root still publishes its original external parent.
    """
    for action, next_label in (("guard", "commit"), ("release", "pop")):
        start = body.index(f"    mov x9, x3\n    mov x10, x2\n    mov w16, #0\n.Lreturn_{action}:")
        end = body.index(f".Lreturn_{next_label}:", start)
        original = body[start:end]
        loop = original[
            original.index(f".Lreturn_{action}:") : original.index(f".Lreturn_{action}_range_done:")
        ]
        first = loop.replace(f".Lreturn_{action}", f".Lreturn_{action}_callee")
        second = loop.replace(f".Lreturn_{action}", f".Lreturn_{action}_caller")
        replacement = (
            "    mov x9, x3\n    mov x10, x2\n" + first + f".Lreturn_{action}_callee_range_done:\n"
            "    mov x9, x7\n    mov x10, x6\n" + second + f".Lreturn_{action}_caller_range_done:\n"
        )
        body = once(body, original, replacement)
    return body


def expand_macros(text):
    """Expand the reviewed parameter-only GAS source macros.

    Leave assembler .if expressions to GAS. Float comparison may use ARM_NUMBER;
    integer comparison may use ARM_DISPATCH_NEXT. Other nesting needs review.
    """
    expected = {
        "ARM_DISPATCH_NEXT",
        "ARM_SLOT_STORE",
        "ARM_REF_SLOT",
        "ARM_CHECKED_LOCAL",
        "ARM_NUMBER",
        "ARM_FLOAT_COMPARE",
        "ARM_INT_COMPARE",
        "ARM_GOTO",
        "ARM_IF",
    }
    if ".macro ARM_SCALAR_EVENT " in text:
        expected.add("ARM_SCALAR_EVENT")
    if ".macro ARM_GLOBAL_EVENT " in text:
        expected.add("ARM_GLOBAL_EVENT")
    if ".macro ARM_COMPARE_EVENT " in text:
        expected.update(("ARM_COMPARE_EVENT", "ARM_COMPARE_STAT"))
    if ".macro ARM_CONSTRUCT_EVENT " in text:
        expected.add("ARM_CONSTRUCT_EVENT")
    definitions = {}
    pattern = re.compile(r"^\.macro (\w+) ([^\n]+)\n(.*?)^\.endm\n", re.M | re.S)

    def definition(m):
        name = m[1]
        parameters = [p.strip() for p in m[2].split(",")]
        if name in definitions or any(not p.isidentifier() for p in parameters):
            raise ValueError("Review GAS macro declaration: " + name)
        definitions[name] = (parameters, m[3])
        return ""

    text = pattern.sub(definition, text)
    if set(definitions) != expected:
        raise ValueError("Review current ARM parameter-only macro set")
    serial = 0

    def expand(text, parent=None):
        nonlocal serial
        rows = []
        for row in text.splitlines():
            if row.strip().startswith(".purgem "):
                if row.strip().split()[1] not in expected:
                    raise ValueError("Unreviewed GAS macro purge")
                continue
            found = re.match(r"\s*(ARM_\w+) (.*)", row)
            if not found:
                rows.append(row)
                continue
            name = found[1]
            if name not in definitions or (
                parent is not None
                and (parent, name)
                not in {
                    ("ARM_FLOAT_COMPARE", "ARM_NUMBER"),
                    ("ARM_INT_COMPARE", "ARM_DISPATCH_NEXT"),
                }
            ):
                raise ValueError("Unreviewed ARM macro/nested edge: " + str((parent, name)))
            parameters, body = definitions[name]
            args = [v.strip() for v in found[2].split(",")]
            if len(args) != len(parameters):
                raise ValueError("Changed ARM macro argument count")
            values = dict(zip(parameters, args))
            serial += 1
            body = body.replace("\\@", "_pub_" + str(serial))
            body = re.sub(r"\\(\w+)", lambda m: values[m[1]], body)
            if "\\" in body:
                raise ValueError("Unresolved ARM macro syntax: " + name)
            rows.extend(expand(body, name))
        return rows

    return "\n".join(expand(text)) + "\n"


def generate(
    source,
    output,
    table,
    *,
    global_bindings=False,
    comparisons=False,
    constructors=False,
    iterators=False,
    forwarding=False,
    null_proto=False,
    arguments=False,
    varargs=False,
    indexed=False,
    literals=False,
    numeric=False,
    strings=False,
    stack_insert=False,
    call_leaves=False,
    scalar=False,
):
    helpers = HELPERS + (
        ("JS_FrameInterpProperty_call_constructor", "JS_FrameVarargsConstructHeapReturn")
        if constructors
        else ()
    )
    if iterators:
        from c_workers import module

        helpers += tuple("JS_LinuxIterator_" + op for op in module(source, "iterator-c").OPS)
    if forwarding:
        helpers += ("JS_AArch64ForwardProbe",)
    if null_proto:
        helpers += ("JS_FrameLinuxNullProtoStep",)
    if arguments:
        helpers += ("JS_FrameArgumentsTry", "JS_FrameArgumentsStep")
    if varargs:
        helpers += ("JS_FrameApplyForwardCall",)
    if literals:
        helpers += ("JS_FrameOrdinaryLiteralStep",)
    if numeric:
        helpers += (
            "JS_FrameAddLocalBig",
            "JS_FrameInterpPrimitive_add",
            "JS_FrameInterpPrimitive_mul",
        )
    if strings:
        helpers += ("JS_FrameLinuxStringAdd", "JS_FrameAddLocalString", "JS_FrameStringIndexStep")
    wrapper = (source / "asm/arm64/linux/interpreter.S").read_text()
    start = wrapper.index(".Lreload:")
    done = wrapper.index(".Ldone:")
    end = assembly_line_start(wrapper, ".cfi_endproc")
    includes = re.findall(r'^#include "(asm/arm64/common/[^\"]+)"$', wrapper[done:end], re.M)
    if len(includes) != 28 or includes[-20:] != [
        "asm/arm64/common/register-forwarding.inc",
        "asm/arm64/common/register-iterators.inc",
        "asm/arm64/common/register-call.inc",
        "asm/arm64/common/register-constructors.inc",
        "asm/arm64/common/register-regexp.inc",
        "asm/arm64/common/register-null-proto.inc",
        "asm/arm64/common/register-arguments.inc",
        "asm/arm64/common/register-varargs.inc",
        "asm/arm64/common/register-indexed.inc",
        "asm/arm64/common/register-literals.inc",
        "asm/arm64/common/register-bigint.inc",
        "asm/arm64/common/register-strings.inc",
        "asm/arm64/common/register-string-append.inc",
        "asm/arm64/common/register-stack-insert.inc",
        "asm/arm64/common/register-host-return.inc",
        "asm/arm64/common/register-property-ic.inc",
        "asm/arm64/common/register-property-primitives.inc",
        "asm/arm64/common/register-property-hints.inc",
        "asm/arm64/common/register-property-prototypes.inc",
        "asm/arm64/common/register-scalar-ops.inc",
    ]:
        raise ValueError("Review complete current ARM VM include stream")
    active_includes = [
        p
        for p in includes
        if (global_bindings or not p.endswith("/register-global-bindings.inc"))
        and (comparisons or not p.endswith("/register-comparisons.inc"))
        and (constructors or not p.endswith("/register-constructors.inc"))
        and (iterators or not p.endswith("/register-iterators.inc"))
        and (forwarding or not p.endswith("/register-forwarding.inc"))
        and (null_proto or not p.endswith("/register-null-proto.inc"))
        and (arguments or not p.endswith("/register-arguments.inc"))
        and (varargs or not p.endswith("/register-varargs.inc"))
        and (indexed or not p.endswith("/register-indexed.inc"))
        and (literals or not p.endswith("/register-literals.inc"))
        and (numeric or not p.endswith("/register-bigint.inc"))
        and (strings or not p.endswith(("/register-strings.inc", "/register-string-append.inc")))
        and (stack_insert or not p.endswith("/register-stack-insert.inc"))
        and (scalar or not p.endswith("/register-scalar-ops.inc"))
    ]
    pure_helpers = (
        PURE_HELPERS
        + (("JS_FrameAArch64CallLeaf",) if call_leaves else ())
        + (("JS_FrameSlowDirectTryInstanceOfLeaf",) if indexed else ())
        + (("JS_LinuxGlobalBindingInit",) if global_bindings else ())
        + (("JS_LinuxComparisonInit", "JS_LinuxLooseEqInit") if comparisons else ())
    )
    body = wrapper[start:done] + "".join((source / p).read_text() + "\n" for p in active_includes)
    if call_leaves:
        from arm64.workers.call_leaves import bind_vm

        body = bind_vm(body)
    original = body
    # The retained slow exit falls through into the original common epilogue.
    # Its derived copy is appended after the opcode islands, so make that exact
    # fallthrough an explicit edge before concatenating those islands.
    body = once(body, wrapper[start:done], wrapper[start:done] + "    b .Ldone\n")
    body = expand_macros(body)
    calls = re.findall(r"^\s*bl (\w+)\s*$", body, re.M)
    if set(calls) != set(helpers + pure_helpers):
        raise ValueError("Review every actual ARM C/indirect transfer: " + repr(calls))
    for row in body.splitlines():
        row = row.split("//")[0].strip()
        transfer = re.fullmatch(r"(b(?:\.\w+)?|cbz|cbnz|tbz|tbnz)\s+(.+)", row)
        if transfer and not transfer[2].split(",")[-1].strip().startswith(".L"):
            raise ValueError("Review new ARM external/conditional tail: " + row)
        if re.match(r"(?:br|blr)\b", row) and row != "br x10":
            raise ValueError("Review new ARM indirect transfer: " + row)
    defined = set(re.findall(r"^(\.L\w+):", body, re.M))
    if set(table) - defined:
        raise ValueError("Dispatch targets escape retained ARM owners")
    # Fully initialized native child, after all guards and ownership copies.
    body = once(
        body,
        """    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x10, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    mov x22, x10""",
        table_address(DIRTY)
        + "\n    mov x22, x10\n"
        + event(0, 7)
        + "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    cbz w16, .Lpublish_borrowed_push\n"
        + TLS
        + counter(1)
        + ".Lpublish_borrowed_push:\n#endif",
    )
    if arguments:
        before = """// Dedicated commit marker for the shared publication factory.
    mov x22, x10
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x11, #ARM_OFF_JSRuntime_current_stack_frame]"""
        body = once(
            body,
            before,
            table_address(DIRTY)
            + "\n    mov x22, x10\n"
            + event(0, 7).replace(
                ".Lpublish_event_0_coherent", ".Lpublish_arguments_event_0_coherent"
            ),
        )
    # Ordinary pop may leave the public SF stale. Root cleanup retains the
    # actual original external-parent publication before leaving the VM.
    before = """    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x12, [x22, #ARM_OFF_JSStackFrame_prev_frame]
    str x12, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]"""
    after = (
        """    cbz x4, .Lpublish_root_pop
"""
        + table_address(DIRTY)
        + """
    b .Lpublish_pop_ready
.Lpublish_root_pop:
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x12, [x22, #ARM_OFF_JSStackFrame_prev_frame]
    str x12, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
"""
        + table_address(CLEAN)
        + "\n"
        + event(9)
        + """.Lpublish_pop_ready:
    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]"""
    )
    body = once(body, before, after)
    body = once(
        body,
        "    mov x22, x4\n    strh wzr, [x22, #ARM_OFF_JSFrame_pending]",
        "    mov x22, x4\n" + event(2, 8) + "    strh wzr, [x22, #ARM_OFF_JSFrame_pending]",
    )
    if constructors:
        before = """    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x4, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]"""
        body = once(
            body,
            before,
            table_address(DIRTY) + "\n    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]",
        )
    dirty_labels = set(re.findall(r"^(\.L\w+):", body, re.M))
    mapping = {n: ".Lpub_" + n[2:] for n in dirty_labels}

    def rename(text, names):
        pattern = re.compile(r"\.L\w+")
        return pattern.sub(lambda m: names.get(m[0], m[0]), text)

    proxies = {n: "qjs_aarch64_publish_before_" + n.removeprefix("JS_") for n in helpers}

    def boundaries(text):
        for name, proxy in proxies.items():
            text = re.sub(r"(?m)^(\s*bl )" + name + r"\s*$", r"\g<1>" + proxy, text)
        return text

    derived = boundaries(rename(body, mapping))
    returns = body[body.index(".Lreturn:") : body.index(".Lregexp:")]
    known = phase_return(returns)
    known = once(
        known, table_address(DIRTY) + "\n    b .Lpublish_pop_ready", "    b .Lpublish_pop_ready"
    )
    known = once(known, ".Lreturn_prepare:\n", ".Lreturn_prepare:\n" + event(3))
    known_names = dict(mapping)
    known_names.update({n: ".Lknown_" + n[2:] for n in re.findall(r"^(\.L\w+):", known, re.M)})
    known = boundaries(rename(known, known_names))
    calls = {"call_short", "call_wide", "return", "return_undef"}
    clean = [mapping[n] if n[2:] in calls else n for n in table]
    dirty = [known_names[n] if n in (".Lreturn", ".Lreturn_undef") else mapping[n] for n in table]
    if sum(a != b for a, b in zip(clean, table)) != 10:
        raise ValueError("Review exactly eight call and two return Clean overrides")
    expected_original = wrapper[start:done] + "".join(
        (source / p).read_text() + "\n" for p in active_includes
    )
    if call_leaves:
        expected_original = bind_vm(expected_original)
    if original != expected_original:
        raise ValueError("Publication mutated original OFF owners")
    output.joinpath("interpreter-aarch64-publication.inc").write_text(derived + "\n" + known + "\n")
    tables = ""
    for name, destinations in ((CLEAN, clean), (DIRTY, dirty)):
        tables += f"\n.p2align 2\n.global {name}\n.hidden {name}\n.type {name},%object\n{name}:\n"
        tables += "".join(f"    .word {target} - {name}\n" for target in destinations)
        tables += f".size {name}, .-{name}\n"
    output.joinpath("interpreter-aarch64-publication-tables.inc").write_text(tables)
    proxies_text = ""
    for i, name in enumerate(helpers):
        proxy = proxies[name]
        proxies_text += (
            f"""\n.p2align 2
.global {proxy}
.hidden {proxy}
.type {proxy},%function
{proxy}:
    .cfi_startproc
    .cfi_def_cfa sp, 0
    adrp x10, {CLEAN}
    add x10, x10, :lo12:{CLEAN}
    cmp x25, x10
    b.eq .Lproxy_{i}_clean
    mov x25, x10
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
"""
            + event(5)
            + f"    b .Lproxy_{i}_ready\n.Lproxy_{i}_clean:\n"
            + event(4)
            + f".Lproxy_{i}_ready:\n"
            + (event(10 + i) if i < len(HELPERS) else "")
            + f"""#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    cmp x11, x22
    b.eq .Lproxy_{i}_coherent
"""
            + TLS
            + counter(6)
            + f""".Lproxy_{i}_coherent:
#endif
    b {name}
    .cfi_endproc
.size {proxy}, .-{proxy}
"""
        )
    output.joinpath("interpreter-aarch64-publication-proxies.inc").write_text(proxies_text)
    generated = [
        "interpreter-aarch64-publication.inc",
        "interpreter-aarch64-publication-tables.inc",
        "interpreter-aarch64-publication-proxies.inc",
    ]
    record = dict(
        schema=1,
        qualification="implemented-not-whole-qualified",
        policy="QJS_DISABLE_DEFERRED_FRAME_PUBLISH presence including0 retains original OFF",
        token="x25 relative dispatch base;private helper output contract;public AAPCS64 callee-save retained",
        tables=[CLEAN, DIRTY],
        table_bytes=1024,
        original_stream_sha256=hashlib.sha256(original.encode()).hexdigest(),
        clean_destinations=clean,
        dirty_destinations=dirty,
        observing_helpers=list(helpers),
        nonobserving_helpers=list(pure_helpers),
        proxies=list(proxies.values()),
        return_protocol="Original two-range guards/releases;Dirty separate callee/caller phases;root/capture/finalizer original continuation",
        source_owners={
            p: hashlib.sha256((source / p).read_bytes()).hexdigest()
            for p in [
                "asm/arm64/linux/interpreter.S",
                *includes,
                "tools/arm64/vm/publication.py",
            ]
        },
        generated={p: hashlib.sha256((output / p).read_bytes()).hexdigest() for p in generated},
        frame_growth=0,
        state_growth=0,
        extra_GC_roots=0,
        physical_stack_growth=0,
        instrument_counter_words=17,
        original_reader_words=16,
        hardware_performance_qualified=False,
    )
    output.joinpath("PUBLICATION.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
