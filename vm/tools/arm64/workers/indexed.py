"""Complete source-owned indexed/append/instanceof mechanisms for AAPCS64."""

import hashlib, json, re
from c_workers import module, replace_one
from indexed_ops_c import generate as shared_generate


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def probe_types(source, text, names):
    # Measure the actual original source declarations,not a private mirror.
    for owner, constant, typ in [
        ("slow-direct-c", "BODY", "JSFrameSlowDirectData"),
        ("array-append-c", "DECLARATION", "JSFrameArrayAppendData"),
    ]:
        body = getattr(module(source, owner), constant)
        found = re.findall(r"typedef struct " + typ + r" \{.*?\} " + typ + r";", body, re.S)
        if len(found) != 1:
            raise ValueError("Review actual indexed policy type: " + typ)
        text += "\n#include <stdatomic.h>\n" + found[0] + "\n"
        names += [("SIZE_" + typ, "sizeof(" + typ + ")")]
        names += [
            ("OFF_" + typ + "_" + n, "offsetof(" + typ + "," + n + ")") for n in ("mode", "hits")
        ]
    names += [("OFF_JSObject_u_array_u1_size", "offsetof(JSObject,u.array.u1.size)")]
    for n in ("UINT8C", "INT8", "UINT8", "INT16", "UINT16", "INT32", "UINT32"):
        names += [("CONST_JS_CLASS_" + n + "_ARRAY", "JS_CLASS_" + n + "_ARRAY")]
    return text, names


def generate(source, output, core, layout, enabled):
    path = source / "src/arm64/linux/abi/indexed.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete indexed owner: " + n)
    if enabled:
        core = shared_generate(
            source,
            output,
            core,
            layout,
            route_core=False,
            platform_binding="src/arm64/linux/interpreter-indexed.inc",
            leaf_condition="#if defined(__linux__) && defined(__aarch64__)",
            contract_rel="src/arm64/linux/abi/indexed.json",
        )
        p = output / "quickjs-linux-indexed.h"
        text = p.read_text()
        append = module(source, "array-append-c")
        body = append.DECLARATION + append.GATEWAY + append.CONFIGURE
        body = body.replace("JS_FrameVarargsSlowSelect", "JS_LinuxIndexedSelect")
        body = body.replace('".qjslcm$zzzzarrayappend"', '".data.qjs_arm_array_append"')
        marker = "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{"
        # Original readonly guard/gateway/configuration remain verbatim except
        # the explicit existing target base-selector and ELF section binding.
        text = replace_one(text, marker, body + "\n" + marker, "complete capacity-append policy")
        text = replace_one(
            text,
            "        return JS_LinuxIndexedSelect(state);",
            "        return *state->pc==OP_put_array_el ? JS_FrameVarargsArrayStep(state) : JS_LinuxIndexedSelect(state);",
            "opcode-only append gateway",
        )
        text += '\n#include "interpreter-aarch64-values.h"\n'
        for typ in ("JSFrameSlowDirectData", "JSFrameArrayAppendData"):
            text += (
                "_Static_assert(sizeof("
                + typ
                + ")==ARM_SIZE_"
                + typ
                + ',"actual target policy type");\n'
            )
            for n in ("mode", "hits"):
                text += (
                    "_Static_assert(offsetof("
                    + typ
                    + ","
                    + n
                    + ")==ARM_OFF_"
                    + typ
                    + "_"
                    + n
                    + ',"actual target policy field");\n'
                )
        text += """
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameSlowDirectTryInstanceOfLeaf),int (*)(JSContext*,JSValue*)),"actual pure instanceof AAPCS64 ABI");
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_indexed_counters[10] __attribute__((visibility("hidden"),tls_model("local-exec")));
__attribute__((noipa,visibility("hidden"))) void qjs_aarch64_vm_indexed_counts(uint64_t out[10])
{memcpy(out,qjs_aarch64_indexed_counters,sizeof(qjs_aarch64_indexed_counters));}
#endif
#pragma pop_macro("FRAME_INLINE")
#pragma pop_macro("FRAME_CODE")
"""
        p.write_text(text)
        record = json.loads((output / "INDEXED.json").read_text())
        record.update(
            enabled=True,
            generated_sha256=sha(p),
            native_indexed=True,
            native_capacity_append=True,
            native_instanceof=True,
            owner_records="Complete shared narrow C steps and original readonly append guard;exact source proof",
        )
    else:
        p = output / "quickjs-linux-indexed.h"
        p.write_text("/* Indexed optimizations compiled OFF. */\n")
        record = dict(enabled=False, entries=[], generated_sha256=sha(p))
    record["pure_nonobserving_helpers"] = ["JS_FrameSlowDirectTryInstanceOfLeaf"] if enabled else []
    record.update(
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/indexed.py"),
        geometry=dict(
            frame_growth=0,
            state_growth=0,
            runtime_growth=0,
            release_tls_bytes=0,
            instrument_tls_bytes=80,
        ),
        whole_qualification=False,
        hardware_performance_qualified=False,
    )
    (output / "INDEXED.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record


def finish(output, record):
    if record["enabled"]:
        # Keep the complete checkpoint/forward/constructor executor on misses.
        p = output / "interpreter-aarch64-constructors.h"
        text = replace_one(
            p.read_text(),
            "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{",
            "FRAME_CODE int JS_LinuxIndexedBaseSlow(JSFrameRegisterState *state)\n{",
            "retain full target semantic selector",
        )
        p.write_text(text)
        record["base_slow_sha256"] = sha(p)
        ep = output / "EXTENDED-CALLS.json"
        d = json.loads(ep.read_text())
        d["generated_sha256"] = sha(p)
        ep.write_text(json.dumps(d, indent=2) + "\n")
        for n in ("CONSTRUCTORS.json", "ITERATORS.json"):
            p = output / n
            d = json.loads(p.read_text())
            d["complete_executor_receipt_sha256"] = sha(ep)
            p.write_text(json.dumps(d, indent=2) + "\n")
    (output / "INDEXED.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
