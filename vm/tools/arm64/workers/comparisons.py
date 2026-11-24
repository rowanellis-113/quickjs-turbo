"""Complete accepted comparison semantics with actual AAPCS64 boundaries."""

import hashlib, json, re
from c_workers import replace_one
from comparisons_c import contract


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(source, output, layout, enabled, global_enabled):
    data = json.loads((source / "src/arm64/linux/abi/comparisons.json").read_text())
    for path, expected in data["source_owners"].items():
        if sha(source / path) != expected:
            raise ValueError("Review complete ARM comparison owner: " + path)
    model = json.loads(json.dumps(dict(layout, reference_count_model="allocator-prefix")))
    original = contract(source, model, contract_rel="src/arm64/linux/abi/comparisons.json")
    rows = [dict(name="loose_control", sha256=sha(source / "src/common/value/loose_control.inc"))]
    (output / "COMPARISONS-ORIGINAL-ALGORITHMS.json").write_text(json.dumps(rows, indent=2) + "\n")
    worker = (source / "src/common/linux/interpreter-comparisons.inc").read_text()
    # Reference configuration is the single existing typed ARM owner emitted
    # before this worker,also when the independent global family is OFF.
    before = """#define OWN_PRIVATE_ADDRESS(name) ((uintptr_t)&(name))
#include "src/common/call/reference-config.inc"
#undef OWN_PRIVATE_ADDRESS"""
    worker = replace_one(
        worker,
        before,
        "/* Existing typed reference-config owner is already defined. */",
        "single shared reference configuration",
    )
    worker = worker.replace(".qjs_linux_comparison", ".qjs_arm_comparison")
    worker += "\nFRAME_CODE\n" + (source / "src/common/value/loose_control.inc").read_text()
    worker += """
FRAME_CODE int JS_LinuxLooseEqInit(JSFrameRegisterState *state)
{
    (void)state;JS_FrameLooseEqConfigure();return 1;
}
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxStrictIdentitySlow),
 int (*)(JSContext *,JSValue *,bool)),"Actual AAPCS64 strict consuming helper");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxComparisonInit),
 int (*)(JSFrameRegisterState *)),"Actual pure comparison initializer");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxLooseEqInit),
 int (*)(JSFrameRegisterState *)),"Actual pure loose initializer");
#undef FRAME_CODE
"""
    worker = worker.replace(
        "COMPARE_DATA _Atomic(unsigned) JS_FrameLooseEqMode;",
        """COMPARE_DATA _Atomic(unsigned) JS_FrameLooseEqMode;
COMPARE_DATA _Atomic(uint64_t) JS_FrameLooseEqStats[16],JS_FrameStrictEqStats[16];
__attribute__((section(".rodata.qjs_arm_comparison"),visibility("hidden")))
const unsigned JS_FrameStrictEqMode=3;
_Static_assert(__atomic_always_lock_free(8,0),"Actual lock-free observation words");""",
    )
    if not enabled:
        worker = "/* Complete comparison family compiled OFF. */\n"
    (output / "interpreter-aarch64-comparisons.h").write_text(worker)
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        source_owners=data["source_owners"],
        source_contract_sha256=sha(source / "src/arm64/linux/abi/comparisons.json"),
        generator_sha256=sha(source / "tools/arm64/workers/comparisons.py"),
        original_algorithms_sha256=sha(output / "COMPARISONS-ORIGINAL-ALGORITHMS.json"),
        worker_sha256=sha(output / "interpreter-aarch64-comparisons.h"),
        retained_strict_slow_sha256=original["retained_strict_slow_sha256"],
        pure_nonobserving_helpers=["JS_LinuxComparisonInit", "JS_LinuxLooseEqInit"]
        if enabled
        else [],
        entries=[
            "JS_LinuxComparisonInit",
            "JS_LinuxLooseEqInit",
            "JS_LinuxStrictIdentitySlow",
            "JS_LinuxStrictIdentityFallback",
            "JS_FrameLooseEqConfigure",
            "JS_LinuxStrictIdentityLeaf",
        ]
        if enabled
        else [],
        shared_reference_owner="existing interpreter-aarch64-globals.h typed reference-config",
        new_logical_static_bytes=265 if enabled else 0,
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        extra_allocations=0,
        instrument_only_TLS_bytes=128,
        global_enabled=global_enabled,
        hardware_performance_qualified=False,
    )
    if enabled and not global_enabled:
        record["entries"].append("frame_reference_configure")
    return record


def finish(output, record, measured):
    measured["HAS_COMPARISONS"] = int(record["enabled"])
    measured["COMPARE_STRING_KIND_SHIFT"] = 28
    if measured["COMPARE_SLICE_PARENT"] != 0 or measured["COMPARE_SLICE_START"] != 8:
        raise ValueError("Review actual parent/start representation for source-owned string views")
    for name in ("CONST_JS_TAG_SHORT_BIG_INT", "CONST_JS_TAG_BIG_INT"):
        if measured[name] >= 1 << 63:
            measured[name] -= 1 << 64
    record["actual_string_geometry"] = [
        measured["SIZE_JSString"],
        measured["COMPARE_SLICE_PARENT"],
        measured["COMPARE_SLICE_START"],
    ]
    if record["actual_string_geometry"] != [24, 0, 8]:
        raise ValueError("Review source-owned flat/slice/indirect kernel")
    (output / "COMPARISONS.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def generate_core(output, core, record):
    if not record["enabled"]:
        return core
    a = core.index("static no_inline int js_strict_eq_slow(")
    b = core.index("\n}", a) + 2
    retained = core[a:b]
    if hashlib.sha256(retained.encode()).hexdigest() != record["retained_strict_slow_sha256"]:
        raise ValueError("Review actual unchanged strict C fallback body")
    text = core[:a] + "/* ARM_RETAINED_STRICT_EQ_BODY */" + core[b:]
    if text.count("js_strict_eq_slow(") != 2:
        raise ValueError("Review the two actual core strict consumers")
    text = text.replace("js_strict_eq_slow(", "JS_LinuxStrictIdentitySlow(")
    text = text.replace("/* ARM_RETAINED_STRICT_EQ_BODY */", retained)
    declaration = '\n__attribute__((visibility("hidden"))) int JS_LinuxStrictIdentitySlow(JSContext *,JSValue *,bool);\n'
    text = replace_one(
        text,
        '#include "quickjs.h"',
        '#include "quickjs.h"' + declaration,
        "typed consuming C identity declaration",
    )
    return text + '\n#include "interpreter-aarch64-comparisons.h"\n'


def finish_slow(output, record):
    p = output / "quickjs-interpreter-slow.h"
    text = p.read_text()
    if record["enabled"]:
        if text.count("js_strict_eq_slow(") != 2:
            raise ValueError("Review actual generated strict opcode consumers")
        text = text.replace("js_strict_eq_slow(", "JS_LinuxStrictIdentitySlow(")
        p.write_text(text)
