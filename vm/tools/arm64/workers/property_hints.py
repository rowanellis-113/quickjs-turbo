"""Actual-type AArch64 bytecode-tail lifetime and native slot/PIC witnesses."""

import hashlib, json, re
from pathlib import Path
from c_workers import module, replace_one
from property_family_c import own_body


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output, layout, *, reference_controls=False):
    contract = source / "src/arm64/linux/abi/property-hints.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review own-tail/PIC semantic owner: " + name)
    assembly = (source / "asm/arm64/common/register-property-hints.inc").read_text()
    for row in assembly.splitlines():
        code = row.split("//")[0].strip()
        if re.match(r"(?:bl|blr|br|ret)\b", code) or re.search(r"\b(?:sp|x18|w18)\b", code):
            raise ValueError("Own/PIC hint must remain a noncalling fixed-CFA kernel: " + code)
    owner = module(source, "own-bytecode-c")
    owner.load_layout = lambda _: dict(
        reference_count_model="allocator-prefix", sizes=layout["sizes"]
    )
    inventory = owner.bytecode_source_contract(source)
    text = own_body(source, reference_controls=reference_controls)
    text = replace_one(text, '#include "qjs-own-sync.h"', "", "no foreign sync header")
    text = replace_one(
        text, "qjs_own_pause();", '__asm__ volatile("yield" ::: "memory");', "target lock wait"
    )
    text = replace_one(
        text,
        "qjs_own_seq_cst_fence();",
        "atomic_thread_fence(memory_order_seq_cst);",
        "target cold StoreLoad fence",
    )
    text = text.replace("JS_FrameProtoDirectConfigure", "JS_FrameLengthConfigure")
    text = replace_one(
        text,
        "offsetof(JSFrame,bytecode)==80",
        "offsetof(JSFrame,bytecode)==ARM_OFF_JSFrame_bytecode",
        "actual owned frame offset",
    )
    text = text.replace('".data.qjs_linux_own"', '".data.qjs_arm_own"')
    text = replace_one(
        text,
        "static _Atomic(unsigned char) js_linux_own_lock;",
        'static _Atomic(unsigned char) js_linux_own_lock __attribute__((section(".data.qjs_arm_own")))=0;',
        "owned cold lock section",
    )
    text = replace_one(
        text,
        "#ifdef QJS_INTERP_FRAME_DIAGNOSTICS",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT",
        "passive target diagnostics",
    )
    text = replace_one(
        text,
        '!getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") &&',
        '!getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") && !getenv("QJS_DISABLE_AARCH64_PROPERTY_HINTS") &&',
        "whole target family control",
    )
    kind = re.search(
        r"typedef struct JSFrameOwnBytecodeControl \{.*?\} JSFrameOwnBytecodeControl;", text, re.S
    )
    if not kind:
        raise ValueError("Review complete own-tail control type")
    types = (
        "#include <stdatomic.h>\n"
        + kind[0]
        + "\nextern JSFrameOwnBytecodeControl JS_FrameOwnBytecodeData;\n"
    )
    (output / "interpreter-aarch64-own-types.h").write_text(types)
    text = replace_one(
        text, kind[0], '#include "interpreter-aarch64-own-types.h"', "same actual control type"
    )
    text = replace_one(
        text,
        "JSFrameOwnBytecodeControl JS_FrameOwnBytecodeData=",
        '__attribute__((visibility("hidden"))) JSFrameOwnBytecodeControl JS_FrameOwnBytecodeData=',
        "hidden same-image control",
    )
    prefix = """/* Complete accepted immutable-ELF own-tail C lifetime;actual AAPCS64. */
#include "interpreter-aarch64-values.h"
#undef FRAME_CODE
#undef FRAME_INLINE
#define FRAME_CODE __attribute__((visibility("hidden"),section(".text.qjs_arm_own_cold"),noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
FRAME_CODE void JS_FrameOwnBytecodeDisable(void);
FRAME_CODE void *JS_FrameOwnBytecodeAllocateRT(JSRuntime *,size_t,size_t);
FRAME_CODE void *JS_FrameOwnBytecodeAllocateContext(JSContext *,size_t);
"""
    suffix = """
static __attribute__((constructor,noipa)) void js_arm_own_startup(void)
{JS_FrameOwnBytecodeConfigure();}
#ifdef QJS_AARCH64_VM_INSTRUMENT
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_vm_own_allocation_counts(uintptr_t words[6])
{
 words[0]=atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_acquire);
 words[1]=atomic_load_explicit(&JS_FrameOwnBytecodeData.allocations,memory_order_relaxed);
 words[2]=atomic_load_explicit(&JS_FrameOwnBytecodeData.base_bytes,memory_order_relaxed);
 words[3]=atomic_load_explicit(&JS_FrameOwnBytecodeData.reserved_bytes,memory_order_relaxed);
 words[4]=atomic_load_explicit(&JS_FrameOwnBytecodeData.fallbacks,memory_order_relaxed);
 words[5]=JS_FrameOwnBytecodeData.reserved[1];
}
#endif
#undef FRAME_CODE
#undef FRAME_INLINE
"""
    if reference_controls:
        prefix += "static void frame_reference_configure(void);\n"
    text = prefix + text + suffix
    if re.search(
        r"\b(?:qjs_own_pause|qjs_own_seq_cst_fence|OWN_PRIVATE_ADDRESS|interp_table|JS_FrameProtoDirectConfigure)\b",
        text,
    ):
        raise ValueError("An unadapted dispatch/ISA or prototype owner escaped extraction")
    if text.count("atomic_thread_fence(memory_order_seq_cst)") != 1:
        raise ValueError("Cold disable must retain its complete StoreLoad fence")
    (output / "interpreter-aarch64-own.h").write_text(text)
    return dict(
        status="generated-not-qualified",
        source_owners=data["source_owners"],
        creator_inventory=inventory,
        worker_sha256=hashlib.sha256(text.encode()).hexdigest(),
        types_sha256=hashlib.sha256(types.encode()).hexdigest(),
        entries=[
            "JS_FrameOwnBytecodeDisable",
            "JS_FrameOwnBytecodeConfigure",
            "JS_FrameOwnBytecodeAllocateRT",
            "JS_FrameOwnBytecodeAllocateContext",
            "js_arm_own_startup",
        ],
        lifetime="Both original creator allocations and frees;zeroed bounded tail;optional allocation failure permanently disables before original-size allocation",
        reservation="6+min(original allocation bytes,2048);native bytecode length<=2048",
        fences="Acquire/release atomic byte lock plus C11 seq_cst StoreLoad fence;AAPCS64 compiler emits target barrier",
        new_frame_fields=0,
        new_state_fields=0,
        new_strong_roots=0,
        hardware_performance_qualified=False,
    )


def finish(output, record, measured):
    record["control_geometry"] = [
        measured[k]
        for k in (
            "SIZE_JSFrameOwnBytecodeControl",
            "OFF_JSFrameOwnBytecodeControl_mode",
            "OFF_JSFrameOwnBytecodeControl_local_field",
        )
    ]
    if record["control_geometry"] != [80, 0, 3]:
        raise ValueError("Review actual own-tail control geometry")
    return record


def generate(source, output, core, layout, record):
    decl = '\n__attribute__((visibility("hidden"))) void *JS_FrameOwnBytecodeAllocateContext(JSContext *,size_t);\n'
    core = replace_one(
        core,
        '#include "quickjs.h"',
        '#include "quickjs.h"' + decl,
        "actual context producer declaration",
    )
    core = replace_one(
        core,
        "b = js_mallocz(ctx, function_size);",
        "b = JS_FrameOwnBytecodeAllocateContext(ctx, function_size);",
        "original compiler creator",
    )
    wire = (Path(layout["compiler_input"]).parent / "quickjs-portable-regexp-wire.h").read_text()
    wire = replace_one(
        wire,
        "b = js_mallocz(ctx, function_size);",
        "b = JS_FrameOwnBytecodeAllocateContext(ctx, function_size);",
        "original wire reader creator",
    )
    path = output / "interpreter-aarch64-own-wire.h"
    path.write_text(wire)
    core = replace_one(
        core,
        '#include "quickjs-portable-regexp-wire.h"',
        '#include "interpreter-aarch64-own-wire.h"',
        "complete original wire reader",
    )
    core += '\n#include "interpreter-aarch64-own.h"\n'
    record["wire_sha256"] = sha(path)
    (output / "PROPERTY-HINTS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
