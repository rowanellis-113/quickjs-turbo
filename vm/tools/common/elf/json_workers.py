"""Complete source-owned JSON parser/writer/callback/source-record family.

Shared preparation supplies the reviewed algorithms.  Linux namespaces the
independent islands in one actual-type core TU and supplies compiler TLS via
the already-qualified prepared capsule; no binary object ABI or generated object input.
"""

import hashlib
import json
import re
from c_workers import module, replace_one


def generate(source, output, core, adapter, layout, *, arch_adapt=None):
    from common.paths import source_file, source_text
    from c_source_match import replace_one as replace_c

    callback = module(source, "json-callback-c")
    raw = source_file(source, "quickjs.c").read_text()
    originals = {m[2]: m[0] for m in adapter.FUNCTION.finditer(raw)}
    virtual, runtime, proto, callback_proof = callback.prepare(source, raw)
    virtual_functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(virtual)}
    context = re.search(
        r"typedef struct FrameJSONLegacyContext \{.*?\} FrameJSONLegacyContext;", virtual, re.S
    )[0]
    traversal_names = (
        "frame_json_replacer_check",
        "frame_json_replacer_to_str",
        "frame_json_replacer_stringify",
    )
    traversals = [virtual_functions[n] for n in traversal_names]
    declarations = "\n".join(body[: body.index("{")].rstrip() + ";" for body in traversals)
    traversal = context + "\n" + proto + "\n" + declarations + "\n" + "\n".join(traversals)

    capsule = source_text(source, "linux-prepared-callback.inc")
    begin = capsule.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS")
    end = capsule.index("typedef JSValue (*JSFrameCallbackLoop)", begin)
    capsule_declarations = capsule[begin:end]
    groups = []
    proofs = {}
    entries = []

    def remove_function(text, name):
        matches = [m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == name]
        if len(matches) != 1:
            raise ValueError("Review JSON source function: " + name + " " + str(len(matches)))
        return replace_one(text, matches[0], "", name)

    def linux_capsule(text):
        text = text.replace(capsule_declarations, "")
        text = text.replace(capsule_declarations.replace("CALLBACK_INLINE", "REVIVER_INLINE"), "")
        if "typedef struct JSFrameCallbackHost" in text or "CALLBACK_TLS_BODY" in text:
            raise ValueError("A foreign capsule/TLS declaration escaped source ownership")
        if re.search(r"\bframe_callback_may_have_leaf\s*\([^;{}]*\)\s*\{", text):
            text = remove_function(text, "frame_callback_may_have_leaf")
        text = re.sub(
            r"^#define CALLBACK_INLINE (?:JSONCB_INLINE|JSON_INLINE)\n", "", text, flags=re.M
        )
        text = re.sub(r"host->state\s*\+", "(unsigned char *)host->state +", text)
        text = re.sub(r"host->state\s*\[CALLBACK_DIRECT\]", "host->state->direct_host_calls", text)
        text = re.sub(
            r"call->barrier.state\s*=\s*call->state;",
            "call->barrier.state = &call->native_state;",
            text,
        )
        text = text.replace("((unsigned char *)&frame->sf)[62] = 1;", "FRAME_ROOT(frame) = 1;")
        return text

    def island(text, prefix, shared=()):
        # Prefix newly defined functions/types/macros, retaining the actual
        # core helpers and the shared prepared capsule types/accessors.
        text = text.replace("static inline __attribute__((always_inline))", "LINUX_JSON_INLINE")
        text = "#define LINUX_JSON_INLINE static inline __attribute__((always_inline))\n" + text
        names = {
            m[2] for m in adapter.FUNCTION.finditer(text) if not m[2].startswith(("JS_", "__"))
        }
        names |= set(re.findall(r"\b(?:FrameJSON\w*|FrameSource\w*|DirectJSONQuote)\b", text))
        names |= set(re.findall(r"^#define\s+(\w+)", text, re.M))
        names |= set(re.findall(r"\bJSON_NO_\w+\b", text))
        names |= set(
            re.findall(
                r"^static _Atomic\s+(?:unsigned char|uintptr_t|uint32_t)\s+(\w+)", text, re.M
            )
        )
        names -= set(shared)
        pattern = re.compile(
            r"\b(?:" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b"
        )
        text = pattern.sub(lambda m: prefix + m[0], text)
        for before, after in (
            (".qjsjson", ".text.qjs_json"),
            (".qjsjcwr$C", ".text.qjs_json_write"),
            (".qjsjcrv$C", ".text.qjs_json_value"),
            (".qjssrc$C", ".text.qjs_json_source"),
            (".qjscbmt$zzjson", ".bss.qjs_json_control"),
            (".qjsrvmd", ".bss.qjs_json_value"),
            (".qjssrm", ".bss.qjs_json_source"),
        ):
            text = text.replace(before, after)
        macros = sorted(set(re.findall(r"^#define\s+(\w+)", text, re.M)))
        # New non-inline traversal/walker helpers also belong to their island.
        for match in reversed(list(adapter.FUNCTION.finditer(text))):
            signature = match[0][: match[0].index("{")]
            if (
                "__attribute__" not in signature
                and not re.search(r"\b(?:JSON\w*INLINE|\w+_INLINE|inline)\b", signature)
                and not re.search(r"\b\w+_CODE\b", signature)
            ):
                text = (
                    text[: match.start()]
                    + '__attribute__((section(".text.qjs_json_owned"), noipa))\n'
                    + text[match.start() :]
                )
        return text + "\n" + "".join("#undef " + name + "\n" for name in macros)

    # The actual core atoms/types are visible; keep this bounded exact leaf
    # inline without exporting or cloning an upstream private ABI.
    atom = originals["JS_DupAtom"].replace(
        "JSAtom JS_DupAtom(",
        "static inline __attribute__((always_inline)) JSAtom linux_json_dup_atom(",
        1,
    )
    prefix = (
        atom
        + "\n"
        + """
JSValue JS_FrameJSONParse(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameJSONStringify(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameJSONReviverValue(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameJSONReviverSource(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameJSONReviverCodeUnits(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameJSONCallbackStringify(JSContext *, JSValueConst, JSValueConst, JSValueConst);
JSValue JS_FrameJSONWriteCallbackStringify(JSContext *, JSValueConst, JSValueConst, JSValueConst);
JSValue JS_FrameJSONToJSONProperty(JSContext *, JSValueConst, JSAtom, JSValueConst, bool);
"""
    )

    # Preserve original public/internal fallback bodies exactly. Original core
    # calls keep those original targets; only the public API and builtin table
    # routes select the new family, as in the object routing.
    for old, new in (
        ("JS_ParseJSON", "JS_LegacyParseJSON"),
        ("JS_JSONStringify", "JS_LegacyJSONStringify"),
    ):
        core = re.sub(r"\b" + old + r"\b", new, core)
    old_check = originals["js_json_check"]
    if core.count(old_check) != 1:
        raise ValueError("Original JSON toJSON check changed")
    slot_call = "JS_FrameJSONToJSONProperty(ctx, val, JS_ATOM_toJSON, val, false)"
    new_check = replace_one(
        old_check, "JS_GetProperty(ctx, val, JS_ATOM_toJSON)", slot_call, "core toJSON slot"
    )
    slot_declaration = "JSValue JS_FrameJSONToJSONProperty(JSContext *, JSValueConst, JSAtom, JSValueConst, bool);\n"
    core = replace_one(core, old_check, slot_declaration + new_check, "core toJSON property route")
    for old, new in (
        ("js_json_parse", "JS_FrameJSONParse"),
        ("js_json_stringify", "JS_FrameJSONStringify"),
    ):
        pattern = r'(JS_CFUNC_DEF\("(?:parse|stringify)",\s*\d+,\s*)' + old + r"(\s*\))"
        core, count = re.subn(pattern, lambda m: m[1] + new + m[2], core)
        if count != 1:
            raise ValueError("JSON builtin table route changed: " + old)
    anchor = "static const JSCFunctionListEntry js_json_funcs[] = {"
    core = replace_one(
        core,
        anchor,
        prefix[prefix.index("JSValue JS_FrameJSONParse") :] + anchor,
        "JSON builtin prototypes",
    )

    base = source_text(source, "linux-json.inc")
    # Two typed parser fallback operands enter value->source->codeunit->core.
    count = len(re.findall(r"\bjs_json_parse\(", base))
    if count != 2:
        raise ValueError("Review both original JSON parser fallback sites")
    base = re.sub(r"\bjs_json_parse\b", "JS_FrameJSONReviverValue", base)
    base = re.sub(r"\bJS_FrameJSONCallbackStringify\b", "JS_FrameJSONWriteCallbackStringify", base)
    base = base.replace("frame_json_dup_atom", "linux_json_dup_atom")
    groups.append(island(base, "linux_json_base_"))
    entries += ["JS_ParseJSON", "JS_JSONStringify", "JS_FrameJSONParse", "JS_FrameJSONStringify"]

    # Base readonly callback traversal deliberately retains its old reviver
    # fallback. The accepted value/source/codeunit chain below supplies that
    # optimization, including the full source context when it is observable.
    read_runtime = linux_capsule(remove_function(runtime, "frame_json_reviver_run"))
    groups.append(island(traversal + "\n" + read_runtime, "linux_json_callback_"))
    proofs["callback"] = callback_proof
    write_runtime = callback.prepare_writable_backend(runtime, adapter)
    write_traversal = callback.direct_quote_private(
        source, traversal, reference_count_model=layout["reference_count_model"]
    )
    write_traversal = replace_one(
        write_traversal,
        "JS_GetProperty(ctx, val, JS_ATOM_toJSON)",
        slot_call,
        "owned traversal toJSON slot",
    )
    groups.append(
        island(write_traversal + "\n" + linux_capsule(write_runtime), "linux_json_write_")
    )
    entries += ["JS_FrameJSONCallbackStringify", "JS_FrameJSONWriteCallbackStringify"]

    value, proof = callback.compile_reviver_value(source, None, None, None, source_owned=True)
    value = re.sub(r"\bjs_json_parse\b", "JS_FrameJSONReviverSource", value)
    groups.append(island(linux_capsule(value), "linux_json_value_"))
    proofs["reviver_value"] = proof
    entries.append("JS_FrameJSONReviverValue")

    for codeunits, name in ((False, "source"), (True, "codeunits")):
        body, proof = callback._prepare_source_variant(
            source, virtual, None, set(), codeunits, source_owned=True
        )
        body = linux_capsule(body).replace("frame_json_dup_atom", "linux_json_dup_atom")
        body = re.sub(r"\bframe_source_public_call\b", "JS_Call", body)
        # Binary unwind-carrier sentinels are not Linux executable/unwind input.
        body, removed = re.subn(
            r"^const unsigned char frame_source_unwind_(?:header|footer)\[[^\n]+\n",
            "",
            body,
            flags=re.M,
        )
        if removed != (0 if codeunits else 2):
            raise ValueError("Review source-record carrier removal: " + name + " " + str(removed))
        if codeunits:
            body = re.sub(
                r"\bframe_source_control\b", "linux_json_source_frame_source_control", body
            )
        else:
            body = re.sub(r"\bjs_json_parse\b", "JS_FrameJSONReviverCodeUnits", body)
        groups.append(
            island(
                body, "linux_json_" + name + "_", shared={"linux_json_source_frame_source_control"}
            )
        )
        proofs[name] = proof
    entries += ["JS_FrameJSONReviverSource", "JS_FrameJSONReviverCodeUnits"]

    slot = re.sub(
        r"\bJS_FrameJSONToJSONPropertySlow\b",
        "JS_FrameJSONToJSONProperty",
        callback.TOJSON_SLOT_BACKEND,
    )
    groups.append(island(slot, "linux_json_slot_"))
    entries += ["JS_FrameJSONToJSONProperty", "JS_FrameJSONToJSONSlotState"]
    text = prefix + "\n" + "\n".join(groups)
    architecture_record = {}
    if arch_adapt is not None:
        text, architecture_record = arch_adapt(source, output, text, adapter)
    path = output / "quickjs-linux-json.h"
    path.write_text(text)
    report = dict(
        status="complete-family-generated-not-qualified",
        entries=entries,
        generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
        proofs=proofs,
        fallback_chain="parser->value->ASCII source->code units->original core;writer->owned callback->readonly callback->original core",
        private_types="actual source types;shared prepared capsule aliases",
        object_inputs=False,
        layout_reference_count_model=layout["reference_count_model"],
    )
    if architecture_record:
        report["target_detail"] = architecture_record
    (output / "JSON-WORKERS.json").write_text(json.dumps(report, indent=2) + "\n")
    return core + '\n#include "quickjs-linux-json.h"\n', report
