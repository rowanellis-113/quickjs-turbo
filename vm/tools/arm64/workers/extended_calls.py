"""Shared complete semantic owner for independent ARM call/iterator families."""

import hashlib, json, re, shutil
from pathlib import Path
from c_workers import replace_one, module
from constructors_c import generate as shared_generate


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare(source, output, constructor_record, iterator_record, *, forwarding=False):
    enabled = constructor_record["enabled"] or iterator_record["enabled"] or forwarding
    ops = (source / "src/common/call/quickjs-interpreter-ops.inc").read_text()
    if enabled:
        start = ops.index("        CASE(OP_put_array_el):")
        end = ops.index("        CASE(OP_define_array_el):", start)
        ops = (
            ops[:start]
            + module(source, "slow-direct-c").writable_array_append(ops[start:end])
            + ops[end:]
        )
    (output / "interpreter-aarch64-complete-ops.inc").write_text(ops)
    owners = dict(constructor_record["source_owners"])
    owners.update(iterator_record["source_owners"])
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        constructors=constructor_record["enabled"],
        iterators=iterator_record["enabled"],
        generator_sha256=sha(source / "tools/arm64/workers/extended_calls.py"),
        source_owners=owners,
        semantic_ops_sha256=sha(output / "interpreter-aarch64-complete-ops.inc"),
        entries=[
            "JS_FrameVarargsSlow",
            "JS_FrameLinuxBaseSlow",
            "JS_AArch64ExtendedStep",
            "JS_AArch64Resume",
        ]
        if enabled
        else [],
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        hardware_performance_qualified=False,
    )
    if not enabled:
        for name in (
            "interpreter-aarch64-constructors.h",
            "interpreter-aarch64-construct-host.h",
            "interpreter-aarch64-construct-dispatch.h",
        ):
            (output / name).write_text("/* Complete call executor compiled OFF. */\n")
        (output / "EXTENDED-CALLS.json").write_text(json.dumps(record, indent=2) + "\n")
        for name, data in [
            ("CONSTRUCTORS.json", constructor_record),
            ("ITERATORS.json", iterator_record),
        ]:
            data["complete_executor_receipt_sha256"] = sha(output / "EXTENDED-CALLS.json")
            (output / name).write_text(json.dumps(data, indent=2) + "\n")
    return record


def prepare_loop(loop, enabled):
    if not enabled:
        return loop
    loop = replace_one(
        loop,
        '#include "src/common/call/interpreter-context-types.inc"',
        '#include "src/common/call/interpreter-retained-context.inc"',
        "actual shared root3/logical parent owner",
    )
    loop = replace_one(
        loop,
        '#include "src/common/call/quickjs-interpreter-ops.inc"',
        '#include "interpreter-aarch64-complete-ops.inc"',
        "accepted readonly array append guard in complete owned executor",
    )
    return loop


def finish(
    source, output, layout, loop, record, constructor_record, iterator_record, *, varargs=False
):
    if not record["enabled"]:
        return record
    # The original complete factory takes this target's already reviewed loop,
    # retaining THIS_FUNC,set_name,host initialization and typed ARM boundaries.
    stage = output / "constructor-source"
    stage.mkdir(exist_ok=True)
    base = output / "quickjs-interpreter-slow.h"
    shutil.copyfile(base, stage / "quickjs-interpreter-slow.h")
    shared_generate(source, stage, layout, loop_override=loop)
    from arm64.workers.iterators import extend_stage, observe_stage

    extend_stage(source, stage, layout, iterator_record)
    if varargs:
        from arm64.workers.varargs import extend_stage as extend_varargs

        extend_varargs(source, output, stage, layout)
    original = json.loads((stage / "CONSTRUCT.json").read_text())
    text = (stage / "quickjs-linux-construct.h").read_text()
    base_text = (stage / "quickjs-interpreter-slow.h").read_text()
    names = {
        "quickjs-linux-construct.h": "interpreter-aarch64-constructors.h",
        "quickjs-linux-construct-host.h": "interpreter-aarch64-construct-host.h",
        "quickjs-linux-construct-dispatch.h": "interpreter-aarch64-construct-dispatch.h",
    }
    for old, new in names.items():
        text = text.replace(old, new)
        base_text = base_text.replace(old, new)
    text = text.replace(".data.qjs_linux_construct", ".data.qjs_arm_construct")
    # A retained complete executor is also needed by iterator-only builds.
    # Constructor-OFF must never admit root3 merely because that owner exists.
    if not constructor_record["enabled"]:
        from admission_c import function

        policy = function(text, "static FRAME_INLINE bool js_frame_construct_enabled(")
        text = replace_one(
            text,
            policy,
            "static FRAME_INLINE bool js_frame_construct_enabled(void)\n{return false;}",
            "independent compiled constructor OFF",
        )
        decl = 'static _Atomic(unsigned) js_frame_construct_policy\n    __attribute__((section(".data.qjs_arm_construct")));\n'
        text = replace_one(text, decl, "", "compiled constructor OFF has no policy storage")
    text = observe_stage(text, iterator_record)
    # Only the iterator-enabled factory has the reviewed checkpoint/selector shape.
    # Other compiled feature sets retain their original semantic routing.
    if iterator_record["enabled"]:
        # The retained complete owner contains every restored base opcode and
        # the original forwarding/constructor/iterator cleanup. Choosing that
        # superset directly avoids walking the complete parent chain per miss.
        # Compiled-OFF configurations return before this stage. No cached frame
        # property, private state field, admission rule or semantic body changes.
        original_selector = """    if (state->iterator_checkpoint_depth)
            return JS_FrameVarargsSlow(state);
        for (JSFrame *f=state->frame; f; f=js_frame_parent(f))
            if (FRAME_ROOT(f)==3 || (FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)) ||
                FRAME_ITERATOR_KIND(f->bytecode))
                return JS_FrameVarargsSlow(state);
        return JS_FrameLinuxBaseSlow(state);"""
        # Keep the base C boundary's builtin-window geometry invalidation.
        # The complete executor also uses these fields as legacy counters.
        text = replace_one(
            text,
            original_selector,
            "    state->arities=0;\n    return JS_FrameVarargsSlow(state);",
            "direct retained complete AArch64 semantic selector",
        )
        record["semantic_selector"] = "direct-complete-owner-with-window-invalidation"

    # C returns after a partially consumed tail/host call must resume labels,
    # rather than replaying an already observed user call or constructor.
    signature = "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)\n{"
    text = replace_one(
        text,
        signature,
        "static FRAME_CODE int JS_AArch64ExtendedStep(JSFrameRegisterState *state,unsigned resume)\n{",
        "complete extended resumed executor",
    )
    entry = "    goto execute_opcode;\n"
    text = replace_one(
        text,
        entry,
        "    if(resume==1){ret_val=state->result;goto return_frame;}\n    if(resume==2){ret_val=state->result;goto finish_call;}\n"
        + entry,
        "exact extended return/host-consumer resume",
    )
    text = (
        """static FRAME_CODE int JS_AArch64ExtendedStep(JSFrameRegisterState *,unsigned);
FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)
{return JS_AArch64ExtendedStep(state,0);}
"""
        + text
    )
    text += """
static FRAME_CODE int JS_AArch64Resume(JSFrameRegisterState *state,unsigned resume)
{
    for(JSFrame *f=state->frame;f;f=js_frame_parent(f))
        if(FRAME_ROOT(f)==3 || FRAME_ITERATOR_KIND(f->bytecode) ||
           (FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)))
            return JS_AArch64ExtendedStep(state,resume);
    return JS_AArch64Step(state,resume);
}
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameInterpProperty_call_constructor),
 int (*)(JSFrameRegisterState *)),"Actual typed constructor opcode boundary");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameVarargsConstructHeapReturn),
 int (*)(JSFrameRegisterState *)),"Actual typed constructor owning result boundary");
"""
    declaration = "static FRAME_CODE int JS_AArch64Resume(JSFrameRegisterState *,unsigned);\n"
    base_text = declaration + base_text
    for number in (1, 2):
        base_text = replace_one(
            base_text,
            "return JS_AArch64Step(state, " + str(number) + ");",
            "return JS_AArch64Resume(state, " + str(number) + ");",
            "retain consumed return/host continuation",
        )
    # Existing opcode counters remain at the single semantic selector,not twice
    # at the retained base wrapper. New private counters have their own64bytes.
    observer = """#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_slow_entry(*state->pc);
#endif
"""
    base_text = replace_one(base_text, observer, "", "single slow-opcode observation owner")
    select = "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{"
    text = replace_one(
        text, select, select + "\n" + observer, "complete semantic selector opcode observation"
    )
    init = "static FRAME_CODE int JS_AArch64ExtendedStep(JSFrameRegisterState *state,unsigned resume)\n{"
    text = replace_one(
        text,
        init,
        init
        + """
#if defined(QJS_AARCH64_VM_INSTRUMENT) && defined(QJS_AARCH64_CONSTRUCTORS)
    ++qjs_aarch64_construct_counters[4];
    if(resume==1)++qjs_aarch64_construct_counters[5];
    if(resume==2)++qjs_aarch64_construct_counters[6];
#endif
""",
        "passive complete-executor resume counters",
    )
    text = replace_one(
        text,
        "construct_step_done:\n",
        "construct_step_done:\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_construct_counters[0];\n#endif\n",
        "actual successful root3 push observation",
    )
    heap = "FRAME_CODE int JS_FrameVarargsConstructHeapReturn(JSFrameRegisterState *state)\n{"
    text = replace_one(
        text,
        heap,
        heap
        + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_construct_counters[3];\n#endif\n",
        "actual owning heap-result observation",
    )
    definitions = (stage / "quickjs-linux-construct-host.h").read_text()
    from arm64.workers.iterators import observe_host

    definitions = observe_host(definitions, iterator_record)
    create = "js_linux_construct_host_create("
    # This actual helper retains the same complete checked TLS/paused boundary.
    start = definitions.index(create)
    brace = definitions.index("{", start)
    definitions = (
        definitions[: brace + 1]
        + """\n#if defined(QJS_AARCH64_VM_INSTRUMENT) && defined(QJS_AARCH64_CONSTRUCTORS)
    ++qjs_aarch64_construct_counters[7];
#endif
"""
        + definitions[brace + 1 :]
    )
    base.write_text(base_text)
    (output / "interpreter-aarch64-constructors.h").write_text(text)
    (output / "interpreter-aarch64-construct-host.h").write_text(definitions)
    # The supplied loop already contains the target's THIS_FUNC/set_name
    # bodies. Its base dispatch is the contract for every such entry;the
    # shared superset factory starts from the original platform-neutral map.
    dispatch = (stage / "quickjs-linux-construct-dispatch.h").read_text()
    inherited = (output / "interpreter-aarch64-dispatch-c.inc").read_text()
    base_entries = dict(re.findall(r"FRAME_TARGET\((\w+),\s*(\w+)\)", inherited))
    full_entries = dict(re.findall(r"FRAME_TARGET\((\w+),\s*(\w+)\)", dispatch))
    if set(base_entries) != set(full_entries):
        raise ValueError("Complete/base dispatch domains differ")
    restored = []
    for opcode, target in base_entries.items():
        if target == "invalid":
            continue
        current = full_entries[opcode]
        if current == target:
            continue
        if current != "invalid":
            raise ValueError("Conflicting complete dispatch owner: " + opcode)
        dispatch = replace_one(
            dispatch,
            "FRAME_TARGET(" + opcode + ", invalid)",
            "FRAME_TARGET(" + opcode + ", " + target + ")",
            "retain actual target semantic dispatch " + opcode,
        )
        restored.append(dict(opcode=opcode, from_target=current, to_target=target))
    (output / "interpreter-aarch64-construct-dispatch.h").write_text(dispatch)
    record["inherited_dispatch_entries_restored"] = restored

    for p in (output / "interpreter-aarch64-constructors.h",):
        t = p.read_text().replace(
            '#include "quickjs-linux-construct-dispatch.h"',
            '#include "interpreter-aarch64-construct-dispatch.h"',
        )
        p.write_text(t)
    record.update(
        shared_factory_record=original,
        generated_sha256=sha(output / "interpreter-aarch64-constructors.h"),
        host_sha256=sha(output / "interpreter-aarch64-construct-host.h"),
        dispatch_sha256=sha(output / "interpreter-aarch64-construct-dispatch.h"),
        base_slow_sha256=sha(base),
        resume="Original complete return_frame/finish_call labels;never replay consumed calls",
        entries=record["entries"]
        + ["js_linux_construct_host_" + n for n in ("start", "next", "close", "append", "apply")],
    )
    (output / "EXTENDED-CALLS.json").write_text(json.dumps(record, indent=2) + "\n")
    for name, data in [
        ("CONSTRUCTORS.json", constructor_record),
        ("ITERATORS.json", iterator_record),
    ]:
        data["complete_executor_receipt_sha256"] = sha(output / "EXTENDED-CALLS.json")
        (output / name).write_text(json.dumps(data, indent=2) + "\n")
    return record
