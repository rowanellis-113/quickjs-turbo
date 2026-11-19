"""Own accepted array/sort C algorithms using actual Linux types and calls."""

import hashlib
import json
import re
from c_workers import module, replace_one


def generate(
    source,
    output,
    core,
    adapter,
    *,
    include_dense=True,
    include_append=True,
    stack_pointer_stmt="QJS_STACK_POINTER(sp);",
):
    from common.paths import source_file, source_text

    raw = source_file(source, "quickjs.c").read_text()
    original = {m[2]: m[0] for m in adapter.FUNCTION.finditer(raw)}
    # Source semantics are pinned independently of private compiler clones.
    contract = json.loads(source_text(source, "default-string-sort-abi.json"))
    for name, expected in contract["bodies"].items():
        if hashlib.sha256(original[name].encode()).hexdigest() != expected:
            raise ValueError("Review source-owned sort semantics: " + name)
    copy = source_text(source, "array-copy-grow.inc").replace(".qjsacm", ".bss.qjs_array")
    copy = copy.replace(
        "int JS_FrameArrayCopySubArray(", "LINUX_ARRAY_CODE int JS_FrameArrayCopySubArray(", 1
    )
    # Keep the original splice identity, conversion/species/item/commit owner.
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(core)}
    splice = functions["js_array_slice"]
    routed = replace_one(
        splice, "JS_CopySubArray(", "JS_FrameArrayCopySubArray(", "single splice copy call"
    )
    core = replace_one(
        core,
        splice,
        "int JS_FrameArrayCopySubArray(JSContext *, JSValue, int64_t, int64_t, int64_t, int);\n"
        + routed,
        "original splice builtin and typed copy route",
    )

    default = source_text(source, "default-string-sort.inc")
    boundary = "#ifdef _MSC_VER\nextern void qjs_default_string_sort_original"
    if default.count(boundary) != 1:
        raise ValueError("Review shared radix algorithm versus private Windows ABI")
    default = default[: default.index(boundary)]
    default = replace_one(
        default,
        "static unsigned char js_default_string_sort_mode;",
        'static unsigned char js_default_string_sort_mode __attribute__((section(".bss.qjs_array")));',
        "ELF sort control",
    )
    default += """
LINUX_ARRAY_CODE void JS_ArrayDefaultStringSortDispatch(
    void *base, size_t count, size_t size, cmp_f compare, void *opaque)
{
    if (size != sizeof(ValueSlot) || !js_default_string_sort_try(base, count, opaque))
        rqsort(base, count, size, compare, opaque);
}
"""
    sort = functions["js_array_sort"]
    sort = replace_one(
        sort,
        "rqsort(array, pos, sizeof(*array), js_array_cmp_generic, &asc);",
        "JS_ArrayDefaultStringSortDispatch(array, pos, sizeof(*array), js_array_cmp_generic, &asc);",
        "actual five-argument source sorter",
    )
    core = replace_one(
        core,
        functions["js_array_sort"],
        "void JS_ArrayDefaultStringSortDispatch(void *, size_t, size_t, cmp_f, void *);\n" + sort,
        "original collection and commit",
    )
    compare = functions["js_array_cmp_generic"]
    compare = replace_one(
        compare,
        "JS_Call(ctx, psc->method, JS_UNDEFINED, 2, argv)",
        "JS_FrameLinuxSortCall(ctx, psc->method, JS_UNDEFINED, 2, argv)",
        "scoped original comparator call",
    )
    core = replace_one(
        core,
        functions["js_array_cmp_generic"],
        "JSValue JS_FrameLinuxSortCall(JSContext *, JSValueConst, JSValueConst, int, JSValueConst *);\n"
        + compare,
        "cached comparator source route",
    )

    shared = source_text(source, "linux-cached-sort.inc")
    bodies = {m[2]: m[0] for m in adapter.FUNCTION.finditer(shared)}
    prefix = shared[: shared.index("#ifndef QJS_PREPARED_SCOPE_ONLY")]
    begin = prefix.index("typedef struct JSFrameCachedHost {")
    end = prefix.index("_Static_assert(sizeof(JSFrameCachedSort)", begin)
    prefix = prefix[:begin] + "typedef JSFrameSharedAnchor JSFrameCachedHost;\n" + prefix[end:]
    begin = prefix.index("typedef struct JSFramePreparedSegment {")
    end = prefix.index("#ifdef QJS_INTERP_FRAME_DIAGNOSTICS", begin)
    prefix = (
        prefix[:begin]
        + """typedef JSFrameSegment JSFramePreparedSegment;
typedef JSFrame JSFramePreparedHeader;
"""
        + prefix[end:]
    )
    tls = re.search(
        r"static inline __attribute__\(\(always_inline\)\) void \*frame_sort_tls_address\(void\)\n\{.*?\n\}",
        prefix,
        re.S,
    )
    if not tls:
        raise ValueError("Review exact cached-sort TLS boundary")
    prefix = replace_one(
        prefix,
        tls[0],
        """static inline __attribute__((always_inline))
void *frame_sort_tls_address(void) { return js_frame_shared_slot(); }
""",
        "compiler-managed Linux TLS",
    )
    prefix = replace_one(
        prefix,
        "_Alignas(16) unsigned char state[SORT_PREP_STATE_BYTES];",
        "union { _Alignas(16) JSFrameRegisterState native_state; unsigned char state[SORT_PREP_STATE_BYTES]; };",
        "actual typed prepared state",
    )
    cached = bodies["JS_FrameCachedArraySort"]
    cached = replace_one(
        cached,
        "QJS_STACK_POINTER(sp);",
        stack_pointer_stmt,
        "actual target stack cursor;same optional workspace guard",
    )
    cached = replace_one(
        cached,
        "result = js_array_sort(ctx, this_val, argc, argv);",
        "result = js_linux_sort_loop(ctx, this_val, argc, argv, &call, NULL, host);",
        "cached scope consumer",
    )
    prepared = bodies["JS_FramePreparedArraySort"]
    prepared = replace_one(
        prepared,
        "result = js_array_sort(ctx, this_val, argc, argv);",
        "result = js_linux_sort_loop(ctx, this_val, argc, argv, &call.cache, &call, host);",
        "prepared generic-comparator scope",
    )
    for old, new in (
        ("host->state +", "(unsigned char *)host->state +"),
        ("host->state[SORT_PREP_DIRECT]", "host->state->direct_host_calls"),
        ("call.barrier.state = call.state;", "call.barrier.state = &call.native_state;"),
        ("((unsigned char *)&frame->sf)[62] = 1;", "FRAME_ROOT(frame) = 1;"),
    ):
        cached, prepared = cached.replace(old, new), prepared.replace(old, new)
    prepared_control = """static _Atomic unsigned char frame_entry_control
    __attribute__((section(".bss.qjs_sort")));
extern JSValue JS_FramePreparedEntryArraySort(JSContext *, JSValueConst, int, JSValueConst *,
                                             JSFramePreparedSort *, JSFrameCachedHost *);
"""
    entry = source_text(source, "quickjs-interpreter-prepared-entry.h")
    slot_type = re.search(r"typedef struct ValueSlot \{.*?\} ValueSlot;", entry, re.S)
    if not slot_type:
        raise ValueError("Review original sort slot owner")
    entry = replace_one(entry, slot_type[0], "", "use real core ValueSlot")
    shared_entry = source_text(source, "quickjs-interpreter-shared.h")
    cached_run = next(
        m[0] for m in adapter.FUNCTION.finditer(shared_entry) if m[2] == "js_frame_run_shared"
    )
    cached_run_original_sha256 = hashlib.sha256(cached_run.encode()).hexdigest()
    cached_run = replace_one(
        cached_run,
        "static SHARED_CODE JSValue js_frame_run_shared(",
        "NATIVE_SORT_CODE JSValue JS_FrameLinuxCachedSortInvoke(",
        "typed cached child owner",
    )
    cached_run = replace_one(
        cached_run,
        "JSFrameSharedAnchor *host)\n",
        "JSFrameSharedAnchor *host, size_t cached_bytes)\n",
        "per-sort cached frame geometry",
    )
    geometry = """    owned = ((flags & JS_CALL_FLAG_COPY_ARGV) || argc < b->arg_count || FRAME_CAPTURED_ARGS(b))
                ? b->arg_count
                : 0;
    bytes = FRAME_HEADER_BYTES + sizeof(JSValue) * (owned + b->var_count + b->stack_size) +
            FRAME_CAPTURE_BYTES(b);"""
    cached_run = replace_one(
        cached_run,
        geometry,
        """    /* The scoped consumer has already checked kind3, no owned captured
     * cells, two actual arguments and at most two readonly formals. */
    owned = 0;
    bytes = cached_bytes;""",
        "reuse complete immutable cached geometry",
    )
    preface = """
#define LINUX_ARRAY_CODE __attribute__((section(".text.qjs_array"), noipa))
#define NATIVE_SORT_CODE __attribute__((section(".text.qjs_sort"), noipa))
"""
    typed = source_text(source, "linux-sort.inc")
    dense = module(source, "json-callback-c").DENSE_ARRAY_POP_BACKEND
    dense = dense.replace(".qjssrc$C", ".text.qjs_dense_pop").replace(
        ".qjssrm", ".bss.qjs_dense_pop"
    )
    # These are Linux-owned optional leaf policy bytes. The shared C body
    # initializes them on its first eligible call; no fixed data offset is used.
    for old, new in (
        ("dense_pop_control", "JS_LinuxDensePopControl"),
        ("dense_pop_leaf_control", "JS_LinuxDensePopLeafControl"),
    ):
        dense = re.sub(r"\b" + old + r"\b", new, dense)
        dense = replace_one(
            dense,
            "static _Atomic unsigned char " + new,
            "_Atomic unsigned char " + new,
            "owned Linux leaf control",
        )
    append_module = module(source, "array-append-c")
    append = append_module.DECLARATION + append_module.GATEWAY + append_module.CONFIGURE
    append = append.replace("FRAME_CODE", "LINUX_ARRAY_CODE").replace(
        "FRAME_INLINE", "inline __attribute__((always_inline))"
    )
    append = append.replace(".qjslcm$zzzzarrayappend", ".data.qjs_array_append")
    append = replace_one(
        append,
        "    uint64_t hits;",
        "    _Atomic uint64_t hits;",
        "race-free optional native append observation",
    )
    append = re.sub(r"\bJS_FrameVarargsSlowSelect\b", "JS_FrameLinuxStringSlow", append)
    append = re.sub(r"\bJS_FrameVarargsArraySlowSelect\b", "JS_FrameLinuxArraySlow", append)
    if not include_dense:
        dense = ""
    if not include_append:
        append = ""
    worker = (
        preface
        + copy
        + "\n"
        + default
        + "\n"
        + prefix
        + "\n"
        + cached_run
        + "\n"
        + typed
        + "\n"
        + cached
        + "\n"
        + prepared_control
        + prepared
        + "\n"
        + entry
        + "\n"
        + dense
        + "\n"
        + append
        + "\n#undef SORT_CACHE_OWNER\n#undef SORT_CACHE_COMMITTED\n"
    )
    path = output / "quickjs-linux-arrays.h"
    path.write_text(worker)
    for old, new in (
        (
            'JS_CFUNC_DEF("sort", 1, js_array_sort )',
            'JS_CFUNC_DEF("sort", 1, JS_FrameCachedArraySort )',
        ),
        (
            'JS_CFUNC_MAGIC_DEF("pop", 0, js_array_pop, 0 )',
            'JS_CFUNC_MAGIC_DEF("pop", 0, JS_FrameDenseArrayPop, 0 )',
        ),
    ):
        if include_dense or "js_array_pop" not in old:
            core = replace_one(core, old, new, "explicit array method " + old)
    anchor = "static const JSCFunctionListEntry js_array_proto_funcs[] = {"
    core = replace_one(
        core,
        anchor,
        """
JSValue JS_FrameCachedArraySort(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_FrameDenseArrayPop(JSContext *, JSValueConst, int, JSValueConst *, int);
"""
        + anchor,
        "array method prototypes",
    )
    record = dict(
        status="generated-array-sort-kernels-not-qualified",
        generated_sha256=hashlib.sha256(worker.encode()).hexdigest(),
        entries=[
            "JS_FrameArrayCopySubArray",
            "JS_ArrayDefaultStringSortDispatch",
            "JS_FrameCachedArraySort",
            "JS_FramePreparedArraySort",
            "JS_FramePreparedEntryArraySort",
            "JS_FramePreparedSortCompare",
            "JS_FramePreparedSortInvoke",
            "JS_FrameLinuxCachedSortInvoke",
            "JS_FrameLinuxSortCall",
            "JS_FrameDenseArrayPop",
            "JS_FrameLinuxArraySlow",
        ],
        method_routes=["Array.prototype.sort", "Array.prototype.pop"],
        algorithm="Accepted complete dense-copy,default radix,cached/prepared sort and dense-pop C bodies",
        sorter_abi="Actual five-argument source rqsort;no private compiler clone",
        ownership="Actual core frame/segment/state,compiler TLS,strong per-sort callee and exact original collection/commit",
        cached_geometry=dict(
            source_entry_sha256=cached_run_original_sha256,
            original_algorithm="js_frame_run_shared",
            specialization="readonly kind3,two actuals,no local captured cells;complete source root/grow/quota/poll/cleanup with per-sort cached bytes",
        ),
        source_sha256={
            name: hashlib.sha256(source_text(source, name).encode()).hexdigest()
            for name in (
                "array-copy-grow.inc",
                "default-string-sort.inc",
                "linux-cached-sort.inc",
                "quickjs-interpreter-prepared-entry.h",
                "linux-sort.inc",
            )
        },
        remaining="Native dense-pop leaf/other builtin-view entry dependencies need explicit routes",
    )
    if not include_dense or not include_append:
        record["entries"] = [
            n
            for n in record["entries"]
            if (include_dense or n != "JS_FrameDenseArrayPop")
            and (include_append or n != "JS_FrameLinuxArraySlow")
        ]
        record["existing_dense_owner"] = not include_dense
        record["native_append_generated"] = include_append
        if not include_dense:
            record["method_routes"] = ["Array.prototype.sort"]
        record["algorithm"] = (
            "Complete accepted dense copy/growth and default radix/cached/prepared sort;dense pop separately owned"
        )
        record["remaining"] = (
            "Native append and remaining array opcodes require their complete independent port"
        )
    (output / "ARRAY-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core + '\n#include "quickjs-linux-arrays.h"\n', record
