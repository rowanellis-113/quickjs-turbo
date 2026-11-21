"""Compile pinned core/libc inputs with explicitly declared source overlays.

The original upstream file stays byte-identical. The compiler input and its
hash receipt live under the build tree. Keep logical source lines unchanged
because native creator-call proofs use those line tables.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import source_file

from bellard_backports import (
    value_header,
    mixed_numbers,
    writable_array_append,
    map_pointer_hash,
    VALUE_COMMIT,
    MIXED_COMMIT,
    ARRAY_APPEND_RELEASE,
    MAP_HASH_COMMIT,
)

SOURCE_SHA256 = "ddab054455e43cfafbe5c0671fa38acd9f3a1eac4ce2a49a97dfec6437701ebe"
UPSTREAM_FIX = "8e14a39fc5a043f44cf86394ea2b07151aed3670"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source-root", type=Path, required=True)
parser.add_argument("--build-root", type=Path, required=True)
parser.add_argument("--allocator", action="store_true")
parser.add_argument("--computed-assign", action="store_true")
parser.add_argument("--value64-init", action="store_true")
parser.add_argument("--narrow-value-readers", action="store_true")
parser.add_argument("--mixed-numbers", action="store_true")
parser.add_argument("--map-pointer-hash", action="store_true")
parser.add_argument("--property-ic", action="store_true")
parser.add_argument("--hybrid-gc", action="store_true")
parser.add_argument("--native-string-module", action="store_true")
parser.add_argument("--native-array-length-module", action="store_true")
parser.add_argument("--native-regexp-test-module", action="store_true")
parser.add_argument("--portable-regexp", action="store_true")
parser.add_argument("--external-compiler-plan", action="store_true")
parser.add_argument("--generate-only", action="store_true")
args, command = parser.parse_known_args()
if command and command[0] == "--":
    command = command[1:]
if not command and not args.generate_only:
    parser.error("compiler command required after --")
if command and args.generate_only:
    parser.error("--generate-only does not take a compiler command")
root = args.source_root.resolve()
build_root = args.build_root.resolve()
libc_original = source_file(root, "quickjs-libc.c").resolve()
libc_candidates = {libc_original, (build_root / "quickjs-libc.c").resolve()}
libc_matching = [
    i
    for i, value in enumerate(command)
    if value.replace("\\", "/").lower().endswith("quickjs-libc.c")
    and Path(value).resolve() in libc_candidates
]
if libc_matching:
    if len(libc_matching) != 1:
        raise ValueError("expected one pinned libc compiler input")
    from file_loader import compiler_input

    command[libc_matching[0]] = str(compiler_input(root, args.build_root))
    raise SystemExit(subprocess.call(command))
original = source_file(root, "quickjs.c").resolve()
core_candidates = {original, (build_root / "quickjs.c").resolve()}
matching = [
    i
    for i, value in enumerate(command)
    if (value.replace("\\", "/").lower().endswith("/quickjs.c") or value.lower() == "quickjs.c")
    and Path(value).resolve() in core_candidates
]
if not matching and not args.generate_only:
    raise SystemExit(subprocess.call(command))
if not args.generate_only and len(matching) != 1:
    raise ValueError("expected one original core compiler input")
raw_data = original.read_bytes()
data = raw_data.replace(b"\r\n", b"\n")
if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
    raise ValueError("upstream changed: review or remove the context-OOM backport")
text = data.decode("utf-8")
before = "    if (!ctx->class_proto) {\n        js_free_rt(rt, ctx);\n        return NULL;\n    }"
after = "    if (!ctx->class_proto) { remove_gc_object(&ctx->header);\n        js_free_rt(rt, ctx);\n        return NULL;\n    }"
if text.count(before) != 1:
    raise ValueError("context-OOM backport anchor changed")
patched = text.replace(before, after, 1)
fixes = [
    dict(
        commit=UPSTREAM_FIX,
        summary="Unlink the context GC node before freeing a failed context construction",
    )
]
# The failed second resolving-function allocation releases the first output.
# Clear that released slot: async/module state still owns and cleans the array.
# Keep this correction inside the original cold failure branch and preserve
# logical source lines used by native creator-call proofs.
promise_start = patched.index("static int js_create_resolving_functions(JSContext *ctx,\n")
promise_end = patched.index("\n}\n", promise_start) + 3
promise_body = patched[promise_start:promise_end]
promise_before = "            if (i != 0)\n                JS_FreeValue(ctx, resolving_funcs[0]);"
promise_after = "            if (i != 0) {\n                JS_FreeValue(ctx, resolving_funcs[0]); resolving_funcs[0] = JS_UNDEFINED; }"
if promise_body.count(promise_before) != 1:
    raise ValueError("Promise resolving-function OOM cleanup anchor changed")
patched = (
    patched[:promise_start]
    + promise_body.replace(promise_before, promise_after, 1)
    + patched[promise_end:]
)
fixes.append(
    dict(
        mechanism="Clear a released resolving-function output on partial capability OOM",
        scope="Original second-function failure branch only; avoid repeated release by async/module state cleanup",
        upstream_function="js_create_resolving_functions",
        success_path_unchanged=True,
    )
)
if not args.native_regexp_test_module:
    from regexp_test import portable_core

    patched, test_fix = portable_core(patched, root, args.build_root)
    fixes.append(test_fix)
if not args.native_array_length_module:
    from array_length import portable_core

    patched, length_fix = portable_core(patched, root, args.build_root)
    fixes.append(length_fix)
if not args.native_string_module:
    from string_rope import portable_equality

    patched = portable_equality(patched)
    fixes.append(
        dict(
            mechanism="Flat/rope strings are one language type in loose equality",
            summary="Preserve original comparison/ToPrimitive redo/cleanup; correct the same-string-type branch",
            source="tools/common/backports/string_rope.py",
        )
    )
if args.portable_regexp:
    assert not args.native_regexp_test_module, (
        "Portable RegExp overlay is not a native builtin replacement"
    )
    from portable_regexp import portable_core

    patched, regexp_fix = portable_core(patched, root, args.build_root)
    fixes.append(regexp_fix)
append_start = patched.index("        CASE(OP_put_array_el):")
append_end = patched.index("\n        CASE(", append_start + 1)
patched = (
    patched[:append_start]
    + writable_array_append(patched[append_start:append_end])
    + patched[append_end:]
)
fixes.append(
    dict(
        release_revision=ARRAY_APPEND_RELEASE,
        summary="Respect readonly length before an in-capacity dense append; retain the original complete setter on failure",
    )
)
if args.computed_assign:
    # Exact upstream #1780 compiler change. Blank lines retain the original
    # line table used by the creator/call proofs; no opcode IDs are changed.
    replacements = [
        (
            "        case OP_get_array_el:\n            emit_op(s, OP_to_propkey2);\n            break;\n"
            "        case OP_get_super_value:\n            emit_op(s, OP_to_propkey);\n            break;",
            "        default:\n            break;",
        ),
        (
            """        // comply with rather obtuse evaluation order of computed properties:
        // obj[key]=val evaluates val->obj->key when obj is null/undefined
        // but key->obj->val when an object
        // FIXME(bnoordhuis) less stack shuffling; don't to_propkey twice in
        // happy path; replace `dup is_undefined_or_null if_true` with new
        // opcode if_undefined_or_null? replace `swap dup` with over?
        if (op == '=' && opcode == OP_get_array_el) {
            int label_next = -1;
            JSFunctionDef *fd = s->cur_func;
            assert(OP_to_propkey2 == fd->byte_code.buf[fd->last_opcode_pos]);
            fd->byte_code.size = fd->last_opcode_pos;
            fd->last_opcode_pos = -1;
            emit_op(s, OP_swap); // obj key -> key obj
            emit_op(s, OP_dup);
            emit_op(s, OP_is_undefined_or_null);
            label_next = emit_goto(s, OP_if_true, -1);
            emit_op(s, OP_swap);
            emit_op(s, OP_to_propkey);
            emit_op(s, OP_swap);
            emit_label(s, label_next);
            emit_op(s, OP_swap);
        }
""",
            "",
        ),
        (
            """        if (op == '=' && opcode == OP_get_array_el) {
            emit_op(s, OP_swap); // obj key val -> obj val key
            emit_op(s, OP_to_propkey);
            emit_op(s, OP_swap);
        }
""",
            "",
        ),
    ]
    for old, new in replacements:
        if patched.count(old) != 1:
            raise ValueError("computed-assignment backport anchor changed")
        new += "\n" * (old.count("\n") - new.count("\n"))
        patched = patched.replace(old, new, 1)
    fixes.append(
        dict(
            commit="0db3949a02a6a84339aa3b8df25dff074e69afa0",
            summary="Match the upstream computed-property assignment evaluation order; remove obsolete stack shuffling",
        )
    )
if args.allocator:
    old_runtime = (
        "JSRuntime *JS_NewRuntime(void)\n{\n    return JS_NewRuntime2(&def_malloc_funcs, NULL);\n}"
    )
    new_runtime = (
        "extern JSRuntime *FramePool_NewRuntime(const JSMallocFunctions *, void *); JSRuntime *JS_NewRuntime(void)\n"
        "{\n    return FramePool_NewRuntime(&def_malloc_funcs, NULL);\n}"
    )
    if patched.count(old_runtime) != 1:
        raise ValueError("default runtime allocator anchor changed")
    patched = patched.replace(old_runtime, new_runtime, 1)
if args.mixed_numbers:
    patched = mixed_numbers(patched)
    fixes.append(
        dict(
            commit=MIXED_COMMIT,
            summary="Keep mixed int/double add/sub/mul in the existing numeric path",
        )
    )
if args.map_pointer_hash:
    patched = map_pointer_hash(patched)
    old_float_hash = (
        "        u.d = d;\n"
        "        h = (u.u32[0] ^ u.u32[1]) * 3163;\n"
        "        return h ^= JS_TAG_FLOAT64;"
    )
    new_float_hash = (
        "        u.d = (d == 0) ? 0.0 : d;\n"
        "        u.u64 = ((u.u64 ^ (u.u64 >> 33)) ^ JS_TAG_FLOAT64) * UINT64_C(0xff51afd7ed558ccd);\n"
        "        return (uint32_t)((u.u64 ^ (u.u64 >> 33)) * UINT64_C(0xc4ceb9fe1a85ec53) >> 32);"
    )
    if patched.count(old_float_hash) != 1:
        raise ValueError("review Map/Set numeric hash anchor")
    patched = patched.replace(old_float_hash, new_float_hash, 1)
    old_add_loc_str = (
        "                    op1 = JS_ConcatString(ctx, js_dup(*pv), op1);\n"
        "                    if (JS_IsException(op1))\n"
        "                        goto exception;\n"
        "                    set_value(ctx, pv, op1);"
    )
    new_add_loc_str = (
        "                    if (JS_VALUE_GET_TAG(op1) == JS_TAG_STRING && JS_VALUE_GET_STRING(*pv)->header.ref_count == 1 && !JS_VALUE_GET_STRING(*pv)->atom_type && JS_VALUE_GET_STRING(*pv)->is_wide_char == JS_VALUE_GET_STRING(op1)->is_wide_char && js_malloc_usable_size(ctx, JS_VALUE_GET_STRING(*pv)) >= sizeof(JSString) + (((size_t)JS_VALUE_GET_STRING(*pv)->len + (size_t)JS_VALUE_GET_STRING(op1)->len) << JS_VALUE_GET_STRING(*pv)->is_wide_char) + 1 - JS_VALUE_GET_STRING(*pv)->is_wide_char) {\n"
        "                        JSString *p1 = JS_VALUE_GET_STRING(*pv), *p2 = JS_VALUE_GET_STRING(op1);\n"
        "                        if (p1->is_wide_char) { memcpy(str16(p1) + p1->len, str16(p2), (size_t)p2->len << 1); p1->len += p2->len; } else { memcpy(str8(p1) + p1->len, str8(p2), p2->len); p1->len += p2->len; str8(p1)[p1->len] = '\\0'; }\n"
        "                        JS_FreeValue(ctx, op1); } else { op1 = JS_ConcatString(ctx, js_dup(*pv), op1); if (JS_IsException(op1)) goto exception; set_value(ctx, pv, op1); }"
    )
    if patched.count(old_add_loc_str) != 1:
        raise ValueError("review OP_add_loc in-place string append anchor")
    patched = patched.replace(old_add_loc_str, new_add_loc_str, 1)
    old_concat2_empty = (
        "    /* XXX: could also check if p1 is empty */\n"
        "    if (p2->len == 0) {\n"
        "        goto ret_op1;\n"
        "    }"
    )
    new_concat2_empty = (
        "    if (p1->len == 0) { JS_FreeValue(ctx, op1); return op2; }\n"
        "    if (p2->len == 0) {\n"
        "        goto ret_op1;\n"
        "    }"
    )
    if patched.count(old_concat2_empty) != 1:
        raise ValueError("review JS_ConcatString2 empty LHS anchor")
    patched = patched.replace(old_concat2_empty, new_concat2_empty, 1)
    old_divrem_hdr = (
        "/* return the division or the remainder. 'b' must be != 0. return NULL\n"
        "   in case of exception (division by zero or memory error) */\n"
        "static JSBigInt *js_bigint_divrem(JSContext *ctx, const JSBigInt *a,"
    )
    new_divrem_hdr = (
        '#include "src/common/value/bigint-divrem-fast.inc"\n'
        "/* stack-limb and pseudo-Mersenne modulus fast paths */\n"
        "static JSBigInt *js_bigint_divrem(JSContext *ctx, const JSBigInt *a,"
    )
    if patched.count(old_divrem_hdr) != 1:
        raise ValueError("review js_bigint_divrem header anchor")
    patched = patched.replace(old_divrem_hdr, new_divrem_hdr, 1)
    old_divrem_body = (
        "    a_sign = js_bigint_sign(a);\n"
        "    b_sign = js_bigint_sign(b);\n"
        "    na = a->len;\n"
        "    nb = b->len;\n"
        "\n"
        "    r = js_bigint_new(ctx, na + 2);"
    )
    new_divrem_body = (
        "    a_sign = js_bigint_sign(a);\n"
        "    b_sign = js_bigint_sign(b);\n"
        "    na = a->len;\n"
        "    nb = b->len;\n"
        "    { JSBigInt *fast_r = NULL; if (js_bigint_try_divrem_stack(ctx, a, b, na, nb, a_sign, b_sign, is_rem, &fast_r)) return fast_r; }\n"
        "    r = js_bigint_new(ctx, na + 2);"
    )
    if patched.count(old_divrem_body) != 1:
        raise ValueError("review js_bigint_divrem body anchor")
    patched = patched.replace(old_divrem_body, new_divrem_body, 1)
    old_int_to_str = (
        "    case JS_TAG_INT:\n"
        "        len = i32toa(buf, JS_VALUE_GET_INT(val));\n"
        "        return js_new_string8_len(ctx, buf, len);"
    )
    new_int_to_str = (
        "    case JS_TAG_INT:\n"
        "        { int32_t v = JS_VALUE_GET_INT(val); if ((uint32_t)v < 10u) return js_new_string_char(ctx, '0' + v);\n"
        "        len = i32toa(buf, v); return js_new_string8_len(ctx, buf, len); }"
    )
    if patched.count(old_int_to_str) != 1:
        raise ValueError("review JS_ToStringInternal int anchor")
    patched = patched.replace(old_int_to_str, new_int_to_str, 1)
    fixes.append(
        dict(
            commit=MAP_HASH_COMMIT,
            summary="Mix pointer and numeric keys before narrowing to the existing uint32 Map hash",
            adaptation="Bellard uint64 multiply/high-word mixing; preserve SameValueZero(-0/+0), NG tables, masks, equality and ordered record list",
        )
    )
from keyed_async import core_overlay as keyed_async_overlay

patched = keyed_async_overlay(patched)
fixes.append(
    dict(
        mechanism="Unified Map/Set string-key hash with short rope flattening and capability-free ordinary async output",
        sources=["src/common/value/map-string-keys.inc", "src/common/promise/async-output.inc"],
    )
)
if args.property_ic:
    from property_ic import core_overlay

    patched = core_overlay(patched)
    from closure_templates import core_overlay as closure_overlay

    patched = closure_overlay(patched, text)
    fixes.append(
        dict(
            mechanism="Context-owned initial length/name shape for unnamed C-data and Promise resolving functions",
            private_layout="Append one ordinary owned shape edge and cached policy after closure context storage; old offsets unchanged",
            source="src/common/function/internal-function-template.inc",
            ablation="QJS_DISABLE_INTERNAL_FUNCTION_TEMPLATE presence; cached per context; named functions retain original creation",
        )
    )
    fixes.append(
        dict(
            mechanism="Interp by-id IC adapted to NG shape COW and RC/GC",
            private_layout="Append bytecode IC pointer and runtime prototype epoch/mode; all original field offsets unchanged",
            source="src/common/property/property-ic.inc",
        )
    )
if args.hybrid_gc:
    from hybrid_gc import core_overlay as hybrid_gc_overlay

    patched = hybrid_gc_overlay(patched)
    fixes.append(
        dict(
            mechanism="Hybrid RC + generational partial cycle GC + synchronous iterative fast RC",
            private_layout="Reorder JSGCObjectHeader before JSRuntime and append hybrid GC / fast-free state; all original offsets unchanged",
            source="src/common/memory/hybrid-gc.inc",
            ablation="QJS_DISABLE_HYBRID_GC / QJS_DISABLE_PARTIAL_CYCLE / QJS_DISABLE_FAST_RC",
        )
    )

# A small borrowed compiler view; all analyses compile in a separate C TU.
compiler_marker = "\n\n/* create a function object from a function definition. The function"
assert patched.count(compiler_marker) == 1
compiler_declaration = (
    "extern void JS_CompilerFunctionPlan(JSContext *, void *);"
    if args.external_compiler_plan
    else '#include "src/common/bytecode/compiler-plan-shim.inc"'
)
patched = patched.replace(
    compiler_marker,
    "\n"
    + compiler_declaration
    + "\n/* create a function object from a function definition. The function",
    1,
)
compiler_start = patched.index(
    "static JSValue js_create_function(JSContext *ctx, JSFunctionDef *fd)"
)
compiler_end = patched.index("\n}\n", compiler_start) + 3
compiler_body = patched[compiler_start:compiler_end]
compiler_resolve = "    if (resolve_labels(ctx, fd))"
assert compiler_body.count(compiler_resolve) == 1
compiler_entry = (
    "JS_CompilerFunctionPlan" if args.external_compiler_plan else "js_compiler_bytecode_plan"
)
compiler_body = compiler_body.replace(
    compiler_resolve, "    " + compiler_entry + "(ctx, fd); if (resolve_labels(ctx, fd))", 1
)
patched = patched[:compiler_start] + compiler_body + patched[compiler_end:]
fixes.append(
    dict(
        mechanism="Independent compiler TU for bounded lexical proof and first-entry sentinel removal",
        source="src/common/bytecode/compiler-plan.c",
        retained_runtime_metadata_bytes=0,
        original_resolve_labels_body=True,
    )
)

# One isolated C helper; retain original source lines and all root inputs.
spread_marker = "\n\n/* argv[] is modified if (flags & JS_CALL_FLAG_COPY_ARGV) = 0. */\nstatic JSValue JS_CallInternal(JSContext *caller_ctx,"
assert patched.count(spread_marker) == 1
patched = patched.replace(
    spread_marker,
    '\n#include "src/common/call/core-spread-call.inc"\n/* argv[] is modified if (flags & JS_CALL_FLAG_COPY_ARGV) = 0. */\nstatic JSValue JS_CallInternal(JSContext *caller_ctx,',
    1,
)
spread_start = patched.index("        CASE(OP_array_from):")
spread_end = patched.index("\n        CASE(", spread_start + 1)
spread_body = patched[spread_start:spread_end]
spread_old = "                call_argc = get_u16(pc);"
spread_new = "                call_argc = get_u16(pc); if (call_argc <= CORE_SPREAD_ARGV_CAP && b->byte_code_buf + b->byte_code_len - pc > 2 && ((pc[2] >= OP_push_0 && pc[2] <= OP_push_i16) || pc[2] == OP_push_i32) && (i = js_core_spread_call(ctx, b, sf, pc, sp))) { call_argc = i > 0 ? i : -i; pc += call_argc & 255; sp -= (unsigned)call_argc >> 8; if (i < 0) goto exception; BREAK; }"
assert spread_body.count(spread_old) == 1
spread_body = spread_body.replace(spread_old, spread_new, 1)
patched = patched[:spread_start] + spread_body + patched[spread_end:]
fixes.append(
    dict(
        mechanism="Guarded C prefix+single dense-array spread into normal const-argv call",
        source="src/common/call/core-spread-call.inc",
        ablation="QJS_DISABLE_CORE_SPREAD_CALL presence;cached process-wide when atomics exist",
    )
)

from cvm_segments_c import core_overlay as coroutine_overlay

patched = coroutine_overlay(patched, text, root, args.build_root)
fixes.append(
    dict(
        mechanism="Derived persistent-frame interpreter input; original compiler TU unchanged",
        source="src/common/call/cvm-native-segments.inc",
    )
)

if text.count("\n") != patched.count("\n"):
    raise ValueError("logical line numbers changed")
output = args.build_root.resolve() / "generated/backports"
output.mkdir(parents=True, exist_ok=True)
header = output / "quickjs.h"
header_receipt = None
if args.value64_init:
    header_content = value_header(
        source_file(root, "quickjs.h"), narrow_readers=args.narrow_value_readers
    ).encode("utf-8")
    if not header.exists() or header.read_bytes() != header_content:
        header.write_bytes(header_content)
    header_receipt = dict(
        path=str(header),
        sha256=hashlib.sha256(header_content).hexdigest(),
        integer_readers="int32" if args.narrow_value_readers else "uint64_then_int32",
        scope="private core compilation; public header and ABI unchanged; big-endian uses original",
    )
    fixes.append(
        dict(commit=VALUE_COMMIT, summary="Initialize the entire non-NaN-boxed integer payload")
    )
elif header.exists():
    # A reconfigured build must not retain a previously enabled header overlay.
    header.unlink()
target = output / "quickjs.c"
content = ('#line 1 "' + original.as_posix() + '"\n' + patched).encode("utf-8")
if not target.exists() or target.read_bytes() != content:
    target.write_bytes(content)
receipt = dict(
    schema=1,
    upstream_source=str(original),
    upstream_source_sha256=SOURCE_SHA256,
    upstream_checkout_sha256=hashlib.sha256(raw_data).hexdigest(),
    fixes=fixes,
    compiler_input=str(target),
    compiler_input_sha256=hashlib.sha256(content).hexdigest(),
    line_count_preserved=True,
    original_file_modified=False,
    experimental_allocator=args.allocator,
    value64_header=header_receipt,
    mixed_numbers=args.mixed_numbers,
    map_pointer_hash=args.map_pointer_hash,
    property_ic=args.property_ic,
    hybrid_gc=args.hybrid_gc,
)
(output / "BACKPORTS.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
if args.generate_only:
    from file_loader import compiler_input

    compiler_input(root, args.build_root)
    raise SystemExit(0)
command[matching[0]] = str(target)
raise SystemExit(subprocess.call(command))
