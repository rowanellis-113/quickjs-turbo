"""AAPCS64 logical forwarding owner;native producers are qualified separately."""

import hashlib, json
from c_workers import module, replace_one
from forwarding_c import literal, release


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(source, output, enabled):
    path = source / "src/arm64/linux/abi/forwarding.json"
    contract = json.loads(path.read_text())
    for name, expected in contract["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete forwarding owner: " + name)
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/forwarding.py"),
        entries=[
            "JS_FrameVarargsForwardTry",
            "JS_FrameCallPrepareCommit",
            "JS_FrameCallForwardNativeCold",
            "JS_FrameCallForwardOwnedCold",
            "JS_FrameCallPrepareCold",
            "JS_AArch64ForwardProbe",
            "JS_AArch64ForwardOwnedTry",
            "JS_AArch64ForwardBorrowTry",
            "JS_AArch64ForwardBorrowMissingTry",
            "JS_AArch64CallPrepareOne",
            "JS_AArch64CallPrepareDeep",
            "JS_AArch64CallPrepareExecute",
            "JS_AArch64CallPrepareOwned",
            "JS_AArch64CallPrepareFallback",
        ]
        if enabled
        else [],
        observing_helpers=["JS_AArch64ForwardProbe"] if enabled else [],
        logical_frame_bytes=80,
        maximum_depth=64,
        private_returning_probe_scratch_bytes=32,
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        complete_native_producer_family=False,
        warm_native_producers=[
            "single primitive integer leaf",
            "general owned child",
            "readonly provided child",
            "readonly missing child",
            "prepared one",
            "prepared deep",
            "prepared execute",
            "prepared owned",
            "prepared fallback",
        ],
        remaining_native_producers=0,
        captured_readonly_dependency="implemented-exact-shared-proof-native-kind7-and-owned-missing-recovery;qualification-pending",
        scope="Shared complete C normalizer/prepared constructor and native root2 return;nine native functions and captured-readonly dependency implemented;full family qualification remains open",
    )
    if not enabled:
        (output / "interpreter-aarch64-forward.h").write_text(
            "/* Forward family compiled OFF. */\n"
        )
        (output / "interpreter-aarch64-captured-readonly.h").write_text(
            "/* Forward dependency compiled OFF. */\n"
        )
    return record


def policy(source, output, loop, record):
    if not record["enabled"]:
        return loop
    if loop.count('#include "src/common/call/interpreter-retained-context.inc"') != 1:
        raise ValueError("Forwarding requires the complete logical-parent context")
    from constructors_c import loop_policy

    loop = loop_policy(loop)
    # Reuse both ORIGINAL source-owned proof and classifier,not private mirrors.
    from admission_c import function

    proof = literal(source, "call-forward-owned", "CAPTURED_PROOF")
    owner = source / "src/common/call/interpreter-captured-readonly.inc"
    signature = "static FRAME_CODE void JS_LinuxCapturedReadonlyClassify(JSFunctionBytecode *b)"
    classifier = function(owner.read_text(), signature).replace(
        "JS_LinuxCapturedReadonlyClassify", "JS_AArch64CapturedReadonlyClassify"
    )
    proof_header = output / "interpreter-aarch64-captured-readonly.h"
    proof_header.write_text(
        "/* Exact shared bounded proof and classifier over actual ARM types. */\n"
        + proof
        + "\n"
        + classifier
        + "\n"
    )
    record["captured_readonly"] = dict(
        header_sha256=sha(proof_header),
        proof_sha256=hashlib.sha256(proof.encode()).hexdigest(),
        classifier_source_sha256=sha(owner),
        classifier_source=str(owner.relative_to(source)),
        nodes=64,
        code_bytes=65536,
        pool_values=4096,
        stack_guard=1024,
        ordinary_kind=7,
        entries=["js_frame_captured_readonly", "JS_AArch64CapturedReadonlyClassify"],
    )
    marker = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    loop = replace_one(
        loop,
        marker,
        '#include "interpreter-aarch64-captured-readonly.h"\n\n' + marker,
        "actual source-owned readonly proof before validator",
    )
    final = "    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);"
    loop = replace_one(
        loop,
        final,
        final + "\n    JS_AArch64CapturedReadonlyClassify(b);",
        "all original short/long classifiers inherit bounded proof",
    )
    prepare = module(source, "call-prepare-c")
    entry = literal(source, "call-forward", "ENTER")
    from admission_c import function

    body = (
        function(entry, "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)")
        + "\n"
    )
    kernel = prepare.prepared_commit_body(body)
    kernel = replace_one(
        kernel,
        "    JSValue leaf_value;\n",
        "",
        "same accepted prepared descriptor removes unreachable leaf temporary",
    )
    entry = replace_one(
        entry,
        "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)\n{",
        "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)\n{\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_forward_counters[0];\n#endif",
        "passive actual C normalizer entries",
    )
    entry = replace_one(
        entry,
        "    result=1;goto done;",
        "    result=1;\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_forward_counters[1];\n#endif\n    goto done;",
        "passive actual C logical-child producer",
    )
    entry = replace_one(
        entry,
        "        result=2;goto done;",
        "        result=2;\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n        ++qjs_aarch64_forward_counters[2];\n#endif\n        goto done;",
        "passive actual C leaf producer",
    )
    header = (
        """/* Complete shared algorithms with actual AAPCS64 C types. */
#ifndef QJS_AARCH64_FORWARD_OWNER
#define QJS_AARCH64_FORWARD_OWNER
#include "src/arm64/linux/interpreter-forward.inc"
#ifdef QJS_AARCH64_VM_INSTRUMENT
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_forward_counters[16];
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_vm_forward_counts(uint64_t words[16])
{memcpy(words,qjs_aarch64_forward_counters,sizeof(qjs_aarch64_forward_counters));}
#endif
"""
        + literal(source, "call-prepare-c", "DATA_TYPE")
        + """
__attribute__((visibility("hidden"),section(".data.qjs_arm_forward")))
JSFramePrepareData JS_FrameCallPrepareData={.control=255};
"""
        + entry
        + "\n"
        + kernel
        + """
static FRAME_INLINE void js_aarch64_forward_controls_init(void)
{
    __atomic_store_n(&JS_FrameCallForwardBorrowMissingControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardBorrowControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardOwnedControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallPrepareData.owned_control,
        getenv("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED")?2:1,__ATOMIC_RELAXED);
    unsigned char mode=getenv("QJS_DISABLE_FRAME_CALL_PREPARE")?2:1;
    if(getenv("QJS_OBSERVE_FRAME_CALL_PREPARE"))mode|=4;
    __atomic_store_n(&JS_FrameCallPrepareData.control,mode,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardNativeControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE")?2:1,__ATOMIC_RELAXED);
}
FRAME_CODE int JS_FrameCallForwardNativeCold(JSFrameRegisterState *state)
{js_aarch64_forward_controls_init();return JS_FrameVarargsForwardTry(state);}
FRAME_CODE int JS_FrameCallForwardOwnedCold(JSFrameRegisterState *state)
{js_aarch64_forward_controls_init();return JS_FrameVarargsForwardTry(state);}
FRAME_CODE int JS_FrameCallPrepareCold(JSFrameRegisterState *state)
{js_aarch64_forward_controls_init();return JS_FrameVarargsForwardTry(state);}
typedef int QJSAArch64PreparedCommit(JSFrameRegisterState *,JSValueConst *,JSValue *,unsigned);
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameCallPrepareCommit),
    QJSAArch64PreparedCommit *),"actual original prepared descriptor boundary");
extern int JS_AArch64ForwardProbe(JSFrameRegisterState *);
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_AArch64ForwardProbe),
    __typeof__(&JS_FrameVarargsForwardTry)),"actual forwarding int(state) AAPCS64 boundary");
"""
    )
    header += "#endif\n"
    target = output / "interpreter-aarch64-forward.h"
    target.write_text(header)
    record["header_sha256"] = sha(target)
    return replace_one(
        loop,
        "/* This is one C activation for the complete supported JS call chain.",
        '#include "interpreter-aarch64-forward.h"\n\n/* This is one C activation for the complete supported JS call chain.',
        "shared source algorithms after actual frame/state/quota helpers",
    )


def finish(source, output, record, extended, constructors, iterators):
    if record["enabled"]:
        # The complete constructor/iterator owner already takes logical tails.
        # Its loop_override intentionally predates these two base-owner hooks,
        # so no generated C owner can accidentally charge/release tails twice.
        for name in ("interpreter-aarch64-loop.h", "quickjs-interpreter-slow.h"):
            p = output / name
            p.write_text(release(p.read_text()))
        extended["base_slow_sha256"] = sha(output / "quickjs-interpreter-slow.h")
        (output / "EXTENDED-CALLS.json").write_text(json.dumps(extended, indent=2) + "\n")
        for name, data in [("CONSTRUCTORS.json", constructors), ("ITERATORS.json", iterators)]:
            data["complete_executor_receipt_sha256"] = sha(output / "EXTENDED-CALLS.json")
            (output / name).write_text(json.dumps(data, indent=2) + "\n")
        record["base_release_hooks"] = {
            n: sha(output / n) for n in ("interpreter-aarch64-loop.h", "quickjs-interpreter-slow.h")
        }
    else:
        record["header_sha256"] = sha(output / "interpreter-aarch64-forward.h")
    (output / "FORWARDING.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
