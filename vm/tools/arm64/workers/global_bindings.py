"""Complete source-owned GNU global mechanisms with measured AAPCS64 types."""

import hashlib, json, re
from global_bindings_c import source_rows
from c_workers import module, replace_one


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(source, output, layout, actual, enabled, reference_controls=False):
    contract = source / "src/arm64/linux/abi/global-bindings.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete global semantic owner: " + name)
    model = dict(
        layout,
        reference_count_model="allocator-prefix",
        property_ic=actual.receipt["property_ic"],
        compiler_input=str(actual.core),
        platform="linux-aarch64-aapcs64",
    )
    rows, proof = source_rows(source, model)
    symbols = [("JS_FrameSymbolGlobalCondition", ["/* checked common bytecode invariant */"])]
    symbol_proof = [
        dict(name="JS_FrameSymbolGlobalCondition", scope="Exact common global cell proof")
    ]
    original = "\n".join(rows) + "\n" + str(symbols)
    (output / "GLOBAL-ORIGINAL-ALGORITHMS.json").write_text(
        json.dumps(
            dict(rows=rows, symbol_blocks=symbols, proof=proof, symbol_proof=symbol_proof), indent=2
        )
        + "\n"
    )
    types = """#ifndef QJS_ARM_GLOBAL_TYPES_H
#define QJS_ARM_GLOBAL_TYPES_H
typedef struct JSFrameGlobalHint {
 uintptr_t pc;
 uint64_t arithmetic,atom_slot;
 int marker;
 uint32_t reserved;
} JSFrameGlobalHint;
#endif
"""
    (output / "interpreter-aarch64-global-types.h").write_text(types)
    assembly = (source / "asm/arm64/common/register-global-bindings.inc").read_text()
    calls = re.findall(r"^\s*bl (\w+)\s*$", assembly, re.M)
    if calls != ["JS_LinuxGlobalBindingInit"] or re.search(r"\b(?:blr|ret|x18|w18)\b", assembly):
        raise ValueError("Global kernels changed their pure C boundary/fixed CFA")
    for row in assembly.splitlines():
        code = row.split("//")[0].strip()
        if re.search(r"\bsp\b", code):
            raise ValueError("Global kernels cannot lease physical stack bytes")
    text = "/* Global binding supplement compiled OFF. */\n"
    if enabled or reference_controls:
        body = (source / "src/common/linux/interpreter-global-bindings.inc").read_text()
        body = body.replace(".text.qjs_linux_global_control", ".text.qjs_arm_global_control")
        body = body.replace(".data.qjs_linux_global_control", ".data.qjs_arm_global_control")
        body = body.replace(".rodata.qjs_linux_global_control", ".rodata.qjs_arm_global_control")
        for expression, key in (
            ("offsetof(JSFrame,bytecode)==80", "OFF_JSFrame_bytecode"),
            ("offsetof(JSStackFrame,cur_pc)==48", "OFF_JSStackFrame_cur_pc"),
            ("offsetof(JSFrameRegisterState,sites)==144", "OFF_JSFrameRegisterState_sites"),
            (
                "offsetof(JSFrameRegisterState,cache_next)==152",
                "OFF_JSFrameRegisterState_cache_next",
            ),
        ):
            body = replace_one(
                body,
                expression,
                expression.split("==")[0] + "==ARM_" + key,
                "compiler measured global field",
            )
        configuration = (source / "src/common/call/reference-config.inc").read_text()
        configuration = replace_one(
            configuration,
            "extern unsigned char JS_FrameReferenceMode[], JS_FrameLargeGlobalMode[];",
            "extern _Atomic(unsigned) JS_FrameReferenceMode,JS_FrameLargeGlobalMode;",
            "actual typed scalar control objects",
        )
        text = (
            """/* Complete original process controls;actual AAPCS64,not foreign ABI. */
#include <stdatomic.h>
#include "interpreter-aarch64-values.h"
#define FRAME_CODE __attribute__((section(".text.qjs_arm_global_control"),noipa))
#define OWN_PRIVATE_ADDRESS(name) (&(name))
__attribute__((visibility("hidden"),section(".data.qjs_arm_global_control")))
_Atomic(unsigned) JS_FrameReferenceMode,JS_FrameLargeGlobalMode;
__attribute__((visibility("hidden"),section(".data.qjs_arm_global_control"),aligned(8)))
_Atomic(uint64_t) JS_FrameGlobalUndefinedArithmetic=UINT32_MAX;
_Static_assert(sizeof(_Atomic(unsigned))==4 && __atomic_always_lock_free(4,0) &&
 __atomic_always_lock_free(8,0),"Actual target aligned scalar atomic controls");
"""
            + configuration
            + "\n#ifdef QJS_AARCH64_GLOBAL_BINDING\n"
            + body
            + """
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxGlobalBindingInit),
 int (*)(JSFrameRegisterState *)),"Actual pure global initializer type");
#endif
#undef OWN_PRIVATE_ADDRESS
#undef FRAME_CODE
"""
        )
        if re.search(
            r"\b(?:JS_Call|JS_RunGC|JS_FreeValue|js_malloc|js_realloc|js_free)\s*\(", text
        ):
            raise ValueError("Global initializer is nonobserving and cannot allocate/free")
    (output / "interpreter-aarch64-globals.h").write_text(text)
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        source_owners=data["source_owners"],
        source_contract_sha256=sha(contract),
        generator_sha256=sha(source / "tools/arm64/workers/global_bindings.py"),
        original_algorithms_sha256=hashlib.sha256(original.encode()).hexdigest(),
        source_factory=proof,
        original_algorithms_receipt_sha256=sha(output / "GLOBAL-ORIGINAL-ALGORITHMS.json"),
        worker_sha256=sha(output / "interpreter-aarch64-globals.h"),
        types_sha256=sha(output / "interpreter-aarch64-global-types.h"),
        entries=["JS_LinuxGlobalBindingInit", "frame_reference_configure"] if enabled else [],
        pure_nonobserving_helpers=["JS_LinuxGlobalBindingInit"] if enabled else [],
        mechanisms=[
            "native BC value cells/relink/TDZ",
            "complete activation global/lexical hints/two-way replacement",
            "undefined mask/bucket arithmetic",
            "large code bypass",
            "resolved-cell Symbol conditional",
        ],
        existing_activation_bytes_reused=520,
        new_logical_static_bytes=18 if enabled else 0,
        new_frame_fields=0,
        new_state_fields=0,
        new_strong_roots=0,
        extra_allocations=0,
        atomic="Current live lexical mask validates one captured aligned atomic64 arithmetic pair;no cached pointer dereference",
        hardware_performance_qualified=False,
    )
    return record


def finish(output, record, measured):
    if measured["CONST_JS_TAG_SYMBOL"] >= 1 << 63:
        measured["CONST_JS_TAG_SYMBOL"] -= 1 << 64
    if (
        measured["CONST_JS_TAG_SYMBOL"] != -8
        or measured["CONST_JS_ATOM_undefined"] != record["source_factory"]["undefined_atom"]
    ):
        raise ValueError("Review actual Symbol tag/undefined atom before source-kernel admission")
    keys = (
        "SIZE_JSFrameGlobalHint",
        "OFF_JSFrameGlobalHint_pc",
        "OFF_JSFrameGlobalHint_arithmetic",
        "OFF_JSFrameGlobalHint_atom_slot",
        "OFF_JSFrameGlobalHint_marker",
        "OFF_JSFrameOwnBytecodeControl_symbol_case",
    )
    record["actual_geometry"] = [measured[k] for k in keys]
    if record["actual_geometry"] != [32, 0, 8, 16, 24, 6]:
        raise ValueError("Review measured global/call/own-control fields")
    measured["HAS_GLOBAL_BINDING"] = int(record["enabled"])
    (output / "GLOBAL-BINDINGS.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
