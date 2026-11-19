"""Complete original apply/owned-spread/fusion owners with AAPCS64 bindings."""

import hashlib, json, shutil
from c_workers import replace_one
from varargs_c import generate as shared_generate, finish_slow as shared_finish


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(source, output, core, layout, enabled):
    path = source / "src/arm64/linux/abi/varargs.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete ARM varargs semantic owner: " + n)
    if enabled:
        # Leave the shared factory untouched. Replace only
        # its single,explicit platform-binding include in this target output.
        core = shared_generate(source, output, core, layout)
        p = output / "quickjs-linux-varargs.h"
        text = p.read_text()
        text = replace_one(
            text,
            '#include "src/common/linux/interpreter-varargs.inc"',
            '#pragma push_macro("FRAME_CODE")\n#pragma push_macro("FRAME_INLINE")\n#include "src/arm64/linux/interpreter-varargs.inc"',
            "actual target C binding",
        )
        text += '\n#include "interpreter-aarch64-values.h"\n'
        text += '_Static_assert(sizeof(JSFrameApplyArgumentRecord)==ARM_SIZE_JSFrameApplyArgumentRecord,"actual target apply-record size");\n'
        for n in ("argv", "argc", "signature"):
            text += (
                "_Static_assert(offsetof(JSFrameApplyArgumentRecord,"
                + n
                + ")==ARM_OFF_JSFrameApplyArgumentRecord_"
                + n
                + ',"actual target apply-record field");\n'
            )
        text += '\n#pragma pop_macro("FRAME_INLINE")\n#pragma pop_macro("FRAME_CODE")\n'
        text += """
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_varargs_counters[4] __attribute__((visibility("hidden"),tls_model("local-exec")));
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_vm_varargs_counts(uint64_t output[4])
{for(unsigned i=0;i<4;i++)output[i]=qjs_aarch64_varargs_counters[i];}
#endif
"""
        p.write_text(text)
        record = json.loads((output / "VARARGS.json").read_text())
        record.update(
            enabled=True,
            generated_sha256=sha(p),
            native_intrinsic_guard=True,
            direct_owned_snapshot=True,
            single_spread_fusion=True,
            architecture="actual AAPCS64 int(state),complete original C owner and typed paused scope",
        )
    else:
        (output / "quickjs-linux-varargs.h").write_text(
            "/* Varargs optimizations compiled OFF. */\n"
        )
        record = dict(enabled=False, entries=[], frame_growth=0, state_growth=0)
    record.update(
        source_owners=contract["source_owners"],
        source_contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/varargs.py"),
        whole_qualification=False,
    )
    (output / "VARARGS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record


def extend_stage(source, output, stage, layout):
    record = json.loads((output / "VARARGS.json").read_text())
    if not record["enabled"]:
        return
    shutil.copyfile(output / "VARARGS.json", stage / "VARARGS.json")
    shared_finish(source, stage, layout)
    record = json.loads((stage / "VARARGS.json").read_text())
    p = stage / "quickjs-linux-construct.h"
    text = p.read_text()
    # Passive observers are absent from Release. They neither classify nor
    # retain JS values. Distinguish snapshots,fusion successes/attempts and
    # successfully published owned-copy children,including zero actuals.
    from admission_c import function

    part = function(text, "FRAME_CODE JSFunctionBytecode *JS_FrameVarargsTryFuse(")
    replacement = replace_one(
        part,
        "    JSFrame *frame = state->frame;",
        "    JSFrame *frame = state->frame;\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_varargs_counters[2];\n#endif",
        "passive fusion attempt",
    )
    replacement = replace_one(
        replacement,
        "    return target;",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_varargs_counters[1];\n#endif\n    return target;",
        "actual original fusion success",
    )
    text = replace_one(
        text, part, replacement, "complete unchanged fusion algorithm plus observers"
    )
    anchor = """        /* Own all actual arguments, including the extra prefix. Existing
           native/C var_buf-owned_args cleanup releases exactly this window. */
        arg_buf = local_buf;"""
    text = replace_one(
        text,
        anchor,
        anchor
        + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n        ++qjs_aarch64_varargs_counters[0];\n#endif",
        "actual complete snapshot copy",
    )
    anchor = """    rt->current_stack_frame = sf;
"""
    # Restrict this to the exact complete semantic step,not its cold helpers.
    start = text.index("FRAME_CODE int JS_FrameVarargsSlow(")
    before = text[:start]
    body = text[start:]
    marker = "    /* Snapshot before the call poll, like the original apply argument list."
    if body.count(marker) != 1:
        raise ValueError("Review original post-snapshot call poll")
    position = body.index(anchor, body.index(marker))
    body = (
        body[:position]
        + "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    if(incoming_copy==2)++qjs_aarch64_varargs_counters[3];\n#endif\n"
        + body[position:]
    )
    text = before + body
    text = (
        '#ifdef QJS_AARCH64_VM_INSTRUMENT\nextern __thread uint64_t qjs_aarch64_varargs_counters[4] __attribute__((visibility("hidden"),tls_model("local-exec")));\n#endif\n'
        + text
    )
    p.write_text(text)
    record["stage_instrumented_slow_sha256"] = sha(p)
    (output / "VARARGS.json").write_text(json.dumps(record, indent=2) + "\n")


def finish(output):
    p = output / "VARARGS.json"
    d = json.loads(p.read_text())
    if d["enabled"]:
        d["actual_extended_slow_sha256"] = sha(output / "interpreter-aarch64-constructors.h")
        if "JS_FrameVarargsTryFuse" not in d["entries"]:
            d["entries"] += ["JS_FrameVarargsTryFuse"]
    p.write_text(json.dumps(d, indent=2) + "\n")
    return d
