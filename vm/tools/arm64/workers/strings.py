"""Complete original GNU C string owners with actual target types."""

import hashlib, json, re
from c_workers import module, replace_one
from string_workers import generate as shared


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def probe_types(source, text, names):
    raw = (source / "src/common/memory/allocator-pool.c").read_text()
    types = re.findall(
        r"typedef struct FramePoolPage FramePoolPage;\s*typedef struct FramePoolHeader \{.*?\} FramePoolHeader;",
        raw,
        re.S,
    )
    if len(types) != 1:
        raise ValueError("Review actual original pool header type")
    text += "\n" + types[0] + "\n"
    names += [
        ("SIZE_FramePoolHeader", "sizeof(FramePoolHeader)"),
        ("OFF_FramePoolHeader_capacity", "offsetof(FramePoolHeader,capacity)"),
        ("STRING_FLAGS_OFFSET", "offsetof(JSString,hash_next)-sizeof(uint32_t)"),
    ]
    text += '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Woverflow"\n'
    for name, init in [
        ("len", ".len=-1"),
        ("kind", ".kind=-1"),
        ("nonnormal", ".kind=-1,.atom_type=-1"),
    ]:
        text += (
            '__attribute__((used,section(".qjs.arm.string_'
            + name
            + '"))) const JSString qjs_arm_string_'
            + name
            + "={"
            + init
            + "};\n"
        )
    text += "#pragma GCC diagnostic pop\n"
    return text, names


def generate(source, output, core, layout, enabled):
    cp = source / "src/arm64/linux/abi/strings.json"
    contract = json.loads(cp.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete string source owner: " + n)
    if enabled:
        core, record = shared(source, output, core, module(source, "object-adapter-c"), layout)
        p = output / "quickjs-linux-strings.h"
        t = p.read_text()
        for signature, index in [
            ("LINUX_STRING_CODE int JS_FrameStringIndexStep(JSFrameRegisterState *state)", 3),
            ("LINUX_STRING_CODE int JS_FrameAddLocalString(JSFrameRegisterState *state)", 4),
            ("LINUX_STRING_CODE int JS_FrameLinuxStringAdd(JSFrameRegisterState *state)", 5),
            ("LINUX_STRING_CODE JSValue JS_FrameSmallCharNew(JSContext *ctx, uint16_t c)", 6),
        ]:
            start = signature + "\n{"
            t = replace_one(
                t,
                start,
                start
                + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_string_counters["
                + str(index)
                + "];\n#endif",
                "actual source-owned string entry count",
            )
        t = (
            '#ifdef QJS_AARCH64_VM_INSTRUMENT\n__thread uint64_t qjs_aarch64_string_counters[8] __attribute__((visibility("hidden"),tls_model("local-exec")));\n__attribute__((visibility("hidden"),noipa)) void qjs_aarch64_vm_string_counts(uint64_t out[8]){memcpy(out,qjs_aarch64_string_counters,sizeof(qjs_aarch64_string_counters));}\n#endif\n'
            + t
        )
        t += '\n#include "interpreter-aarch64-values.h"\n'
        for n in ("JS_FrameLinuxStringAdd", "JS_FrameAddLocalString", "JS_FrameStringIndexStep"):
            t += (
                "_Static_assert(__builtin_types_compatible_p(__typeof__(&"
                + n
                + '),int (*)(JSFrameRegisterState*)),"actual target string C state ABI");\n'
            )
        t += '_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameSharedConcatRope),JSValue (*)(JSContext*,JSValue,JSValue)),"actual target string aggregate ABI");\n'
        t += "#undef LINUX_STRING_CODE\n"
        t = (
            '#pragma push_macro("QJS_FRAME_EXPERIMENTAL_ALLOCATOR")\n#if defined(QJS_AARCH64_STRING_POOL) && !defined(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)\n#define QJS_FRAME_EXPERIMENTAL_ALLOCATOR\n#endif\n'
            + t
            + '\n#pragma pop_macro("QJS_FRAME_EXPERIMENTAL_ALLOCATOR")\n'
        )
        p.write_text(t)
        record.update(
            enabled=True, generated_sha256=sha(p), frame_growth=0, state_growth=0, runtime_growth=0
        )
    else:
        (output / "quickjs-linux-strings.h").write_text("/* String workers compiled OFF. */\n")
        record = dict(enabled=False, entries=[])
    record.update(
        source_owners=contract["source_owners"],
        contract_sha256=sha(cp),
        generator_sha256=sha(source / "tools/arm64/workers/strings.py"),
        native_byte_append_complete=bool(layout.get("native_string_append")),
        whole_qualification=False,
    )
    (output / "STRING-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
