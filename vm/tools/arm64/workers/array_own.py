"""Complete accepted core array-own leaf with actual AAPCS64 C fallback."""

import hashlib, json
from admission_c import function
from c_workers import replace_one


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(source, output, core, layout, enabled):
    path = source / "src/arm64/linux/abi/array-own.json"
    contract = json.loads(path.read_text())
    for name, expected in contract["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete array-own owner: " + name)
    original = function(core, "static bool js_get_fast_array_element(JSContext *ctx, JSObject *p,")
    if hashlib.sha256(original.encode()).hexdigest() != contract["core_helper_sha256"]:
        raise ValueError("Review original complete array/arguments/typed fallback")
    for group, name, expected in [
        ("sizes", "JSValue", 16),
        ("sizes", "JSShapeProperty", 8),
        ("offsets", "JSShapeProperty.atom", 4),
        ("constants", "JS_CLASS_ARRAY", 2),
        ("constants", "JS_PROP_TMASK", 48),
    ]:
        if layout[group][name] != expected:
            raise ValueError("Review actual array-own ABI: " + name)
    if layout["bits"]["JSShapeProperty.flags"] != [(3, 4)] and layout["bits"][
        "JSShapeProperty.flags"
    ] != [[3, 4]]:
        raise ValueError("Review measured property descriptor bitfield")
    header = "/* Actual compiler-private types at the original helper definition. */\n"
    entries = []
    if enabled:
        entries = ["JS_AArch64FastArrayOwnGet", "JS_AArch64FastArrayOwnFallback"]
        header += """extern bool JS_AArch64FastArrayOwnGet(JSContext*,JSObject*,uint32_t,JSValue*) __attribute__((visibility("hidden")));
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_AArch64FastArrayOwnGet),__typeof__(&JS_AArch64FastArrayOwnFallback)),"actual AAPCS64 array-own bool ABI");
_Static_assert(sizeof(JSValue)==16 && sizeof(JSShapeProperty)==8 && offsetof(JSShapeProperty,atom)==4,"actual shape/value profile");
#ifdef QJS_AARCH64_VM_INSTRUMENT
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_array_own_counters[4];
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_vm_array_own_counts(uint64_t words[4])
{
    memcpy(words,qjs_aarch64_array_own_counters,sizeof(qjs_aarch64_array_own_counters));
}
#endif
#define js_get_fast_array_element JS_AArch64FastArrayOwnGet
"""
        replacement = original.replace(
            "static bool js_get_fast_array_element(",
            '__attribute__((noipa,visibility("hidden"))) bool JS_AArch64FastArrayOwnFallback(',
            1,
        )
        replacement += '\n#include "interpreter-aarch64-array-own.h"\n'
        core = replace_one(core, original, replacement, "typed array-own core and cloned consumers")
    target = output / "interpreter-aarch64-array-own.h"
    target.write_text(header)
    record = dict(
        enabled=enabled,
        status="generated-not-qualified",
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/array_own.py"),
        header_sha256=sha(target),
        entries=entries,
        original_helper_sha256=contract["core_helper_sha256"],
        fallback="exact original body; four arguments unchanged on every miss",
        geometry=dict(frame_growth=0, state_growth=0, runtime_growth=0, release_tls_bytes=0),
        scope=contract["scope"],
    )
    (output / "ARRAY-OWN.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
