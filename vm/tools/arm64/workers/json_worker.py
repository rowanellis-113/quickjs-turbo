"""Adapt complete JSON C owners to measured ARM types and actual AdvSIMD."""

import hashlib
import re

VECTOR_OPS = {
    "qjs_vec_setzero_si128": "zero",
    "qjs_vec_set1_epi8": "splat8",
    "qjs_vec_set1_epi16": "splat16",
    "qjs_vec_loadu_si128": "load",
    "qjs_vec_storeu_si128": "store",
    "qjs_vec_or_si128": "or",
    "qjs_vec_and_si128": "and",
    "qjs_vec_cmpeq_epi8": "eq8",
    "qjs_vec_cmpeq_epi16": "eq16",
    "qjs_vec_subs_epu8": "subsat8",
    "qjs_vec_subs_epu16": "subsat16",
    "qjs_vec_sub_epi16": "sub16",
    "qjs_vec_unpacklo_epi8": "interleave_low",
    "qjs_vec_unpackhi_epi8": "interleave_high",
    "qjs_vec_movemask_epi8": "sign_mask",
}


def generate(text):
    before = hashlib.sha256(text.encode()).hexdigest()
    operations = set(re.findall(r"\bqjs_vec_\w+", text))
    if operations != set(VECTOR_OPS):
        raise ValueError("Review the complete JSON vector operation set: " + str(operations))
    counts = {name: len(re.findall(r"\b" + name + r"\b", text)) for name in VECTOR_OPS}
    text = re.sub(r"\bqjs_vec_\w+\b", lambda m: "qjs_json_vec_" + VECTOR_OPS[m[0]], text)
    text = re.sub(r"\bqjs_vec128_t\b", "QJSJSONVector", text)
    includes = text.count('#include "qjs-json-simd.h"')
    if includes != 4:
        raise ValueError("Review all four parser/quote source islands")
    text = text.replace('#include "qjs-json-simd.h"', '#include "src/arm64/common/json-vector.h"')
    text = text.replace("/* @QJS_MSC_INTRIN@ */", "")
    # Retain original typed core stack check via js_check_stack_overflow.
    stack_pat = re.compile(r"QJS_JSON_STACK_CHECK\(([^,]+),\s*([^\)]+)\);")
    guards = stack_pat.findall(text)
    if len(guards) != 8:
        raise ValueError("Review original GNU/Linux typed JSON stack guards: " + str(len(guards)))
    text = stack_pat.sub(lambda m: f"return js_check_stack_overflow({m[2].strip()}, 0);", text)
    sp_stmt = "QJS_STACK_POINTER(sp);"
    sp_count = text.count(sp_stmt)
    if sp_count:
        text = text.replace(sp_stmt, '__asm__ volatile("mov %0, sp" : "=r"(sp));')
    elif '__asm__ volatile("mov %0, sp" : "=r"(sp));' in text:
        sp_count = text.count('__asm__ volatile("mov %0, sp" : "=r"(sp));')
    address = r"QJS_CONTROL_SLOT_ADDR\(p,\s*(\w+)\);"
    symbols = re.findall(address, text)
    if symbols != ["JS_FrameJSONControl"] * 3 + ["linux_json_source_frame_source_control"]:
        raise ValueError("Review actual JSON atomic address owners: " + str(symbols))
    text = re.sub(address, lambda m: "p = &" + m[1] + ";", text)
    text, leaf_count = re.subn(r"\s*\|\|\s*frame_callback_may_have_leaf\(b\)", "", text)
    if leaf_count != 5:
        raise ValueError("Review all JSON competing native-leaf exclusions")
    substitutions = {
        "memcpy(&rt, (unsigned char *)host->state + 56, 8);": "rt = host->state->rt;",
        "memcpy(&used, (unsigned char *)host->state + 32, 8);": "used = host->state->used_bytes;",
        "memcpy(&committed, (unsigned char *)host->state + CALLBACK_COMMITTED, 8);": "committed = host->state->committed_bytes;",
        "memcpy(call->state + 56, &ctx->rt, 8);": "call->native_state.rt = ctx->rt;",
        "memcpy(call->state + CALLBACK_CALLER, &ctx, 8);": "call->native_state.caller_ctx = ctx;",
        "memcpy(call->state + CALLBACK_SITES, (unsigned char *)host->state + CALLBACK_SITES, 8);": "call->native_state.sites = host->state->sites;",
        "memcpy(call->state + CALLBACK_NEXT, (unsigned char *)host->state + CALLBACK_NEXT, 8);": "call->native_state.cache_next = host->state->cache_next;",
        "call->state[CALLBACK_DIRECT] = host->state->direct_host_calls;": "call->native_state.direct_host_calls = host->state->direct_host_calls;",
    }
    for old, new in substitutions.items():
        if text.count(old) != 5:
            raise ValueError("Review five actual-type JSON capsule owners: " + old)
        text = text.replace(old, new)
    text, frames = re.subn(r"\bbytes\s*=\s*128\s*\+", "bytes = FRAME_HEADER_BYTES +", text)
    text, headers = re.subn(r"call->data\s*\+\s*128\b", "call->data + FRAME_HEADER_BYTES", text)
    if frames != 5 or headers != 5:
        raise ValueError("Review actual JSON header geometry: " + str((frames, headers)))
    return text, dict(
        source_linux_sha256=before,
        vector_operations=counts,
        scanner_quote_islands=includes,
        physical_stack_readers=sp_count,
        original_typed_core_stack_guards=len(guards),
        atomic_addresses=symbols,
        typed_capsules=5,
        competing_native_leaf_provider=False,
        instruction_set="Actual AArch64 AdvSIMD through typed C intrinsics",
        lengths="Original fully bounded vector load/store and mask/ctz owners unchanged",
    )


def arch_adapt(source, output, text, adapter):
    text, architecture_record = generate(text)
    scan_names = ["linux_json_base_frame_json_" + n for n in ("first_lane", "scan8", "scan16")]
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(text)}
    fixture = (
        "\n".join(functions[n] for n in scan_names).replace(
            "linux_json_base_JSON_INLINE", "static inline"
        )
        + "\n"
    )
    (output / "interpreter-aarch64-json-scan-test.h").write_text(fixture)
    architecture_record["scan_fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
    return text, architecture_record
