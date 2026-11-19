"""Source-owned indexed/instanceof workers with actual Linux publication."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import ast
import hashlib
import json
import re
from c_workers import module, replace_one
from admission import function
from iterators import scoped

OWNERS = (
    "tools/x86/common/codegen/slow-direct.py",
    "tools/x86/common/codegen/indexed_own_native.py",
    "tools/x86/common/codegen/publish-boundary.py",
    "src/common/value/instanceof.c",
    "src/common/call/quickjs-interpreter-ops.inc",
    "asm/x86/win64/common/array_own.S",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/indexed.json").read_text())
    for n, h in data["owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Review accepted indexed owner: " + n)
    return data


def array_own_rows(source, layout):
    contract(source)
    if layout["reference_count_model"] != "inline-header" or any(
        layout[group].get(name) != value
        for group, name, value in (
            ("sizes", "JSValue", 16),
            ("sizes", "JSShapeProperty", 8),
            ("offsets", "JSShapeProperty.atom", 4),
        )
    ):
        raise ValueError("Review actual core array own value/shape profile")
    raw = (source / OWNERS[-1]).read_text()
    first = raw.index("JS_FrameFastArrayOwnGet:")
    last = raw.index("JS_FrameFastArrayOwnGet_end:", first)
    text = raw[first:last] + "JS_FrameFastArrayOwnGet_end:"
    if text.count(".if ") != 2 or text.count(".endif") != 2 or text.count(".error ") != 1:
        raise ValueError("Review original inline-profile-only leaf directives")
    text = "\n".join(
        row
        for row in text.splitlines()
        if not row.strip().startswith((".if ", ".endif", ".error "))
    )
    from arguments import asm_body

    rows = asm_body(
        source,
        OWNERS[-1],
        "JS_FrameFastArrayOwnGet",
        layout,
        extra_values={"QJS_ABI_CONST_JS_CLASS_ARRAY": layout["constants"]["JS_CLASS_ARRAY"]},
        expanded=text,
    )
    # Original arguments are never used as temporaries on any miss. A token
    # rename is therefore the complete reviewed SysV C ABI adaptation.
    mapping = {
        "rdx": "rsi",
        "r8d": "edx",
        "r9": "rcx",
        "JS_FrameFastArrayOwnGet": "JS_LinuxFastArrayOwnGet",
        "JS_FrameFastArrayOwnGet_probe": "linux_core_array_probe",
        "JS_FrameFastArrayOwnGet_found": "linux_core_array_found",
        "JS_FrameFastArrayOwnGet_value": "linux_core_array_value",
        "JS_FrameFastArrayOwnGet_fallback": "linux_core_array_fallback",
        "qjs_frame_core_js_get_fast_array_element": "JS_LinuxFastArrayOwnFallback",
    }
    expression = re.compile(
        r"\b(?:" + "|".join(map(re.escape, sorted(mapping, key=len, reverse=True))) + r")\b"
    )
    return [expression.sub(lambda match: mapping[match[0]], row) for row in rows]


def render_native(source, layout):
    name = "JS_LinuxFastArrayOwnGet"
    return [
        '.section .text.qjs_linux_array_own,"ax",@progbits',
        ".p2align 4",
        ".globl " + name,
        ".hidden " + name,
        ".hidden JS_LinuxFastArrayOwnFallback",
        ".type " + name + ",@function",
        name + ":",
        ".cfi_startproc",
        "endbr64",
        *array_own_rows(source, layout),
        ".cfi_endproc",
        ".size " + name + ",.-" + name,
    ]


def append(source, output, stream, handlers, layout):
    data = contract(source)
    code = stream["code"]
    blocks = []
    worker = module(source, "indexed_own_native")
    for op in ("get_array_el", "get_array_el2", "put_array_el"):
        name = "JS_LinuxIndexedOwn_" + op
        rows = []
        worker.append(
            op,
            layout,
            0,
            lambda *v: rows.extend(v),
            lambda v: rows.append(v + ":"),
            lambda: rows.extend(
                ["inc r12", "movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"]
            ),
        )
        label = "interp_" + op + "_indexed_own"
        if rows[0] != label + ":":
            raise ValueError("Review native indexed entry")
        rows = [r.replace(label, name) for r in rows[1:]]
        start = code.index("interp_" + op + ":")
        end = (
            code.index("interp_" + op + "_typed:", start)
            if op != "put_array_el"
            else code.index("interp_put_array_el_typed:", start)
        )
        expected = 2 if op != "put_array_el" else 1
        anchors = []
        if op != "put_array_el":
            anchors = [
                "cmp ecx, DWORD PTR [r8+"
                + str(layout["offsets"]["JSObject.u.array.count"])
                + "]\njae interp_slow",
                "test BYTE PTR [r8+"
                + str(layout["bits"]["JSObject.fast_array"][0][0])
                + "], "
                + str(layout["bits"]["JSObject.fast_array"][0][1])
                + "\njz interp_slow",
            ]
        else:
            anchors = [
                "test BYTE PTR [r8+"
                + str(layout["bits"]["JSObject.fast_array"][0][0])
                + "], "
                + str(layout["bits"]["JSObject.fast_array"][0][1])
                + "\njz interp_slow"
            ]
        fragment = "\n".join(code[start:end])
        for anchor in anchors:
            fragment = replace_one(
                fragment,
                anchor,
                anchor.rsplit("interp_slow", 1)[0] + name,
                "original sparse-array miss " + op,
            )
        if len(anchors) != expected:
            raise ValueError("Review native indexed edges")
        code[start:end] = fragment.splitlines()
        blocks.append((name, rows))
    # This is the source-owned nonobserving leaf, adapted only at its miss edge.
    tree = ast.parse((source / OWNERS[2]).read_text())
    matches = []
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "emit"
            and len(n.args) == 2
        ):
            if (
                isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "JS_FramePublishInstanceOfLeaf"
            ):
                matches.append(ast.literal_eval(n.args[1]))
    if len(matches) != 1:
        raise ValueError("Review actual instanceof leaf factory")
    rows = [r.replace("dirty_interp_slow", "interp_slow") for r in matches[0]]
    if handlers.get("instanceof", "interp_slow") != "interp_slow":
        raise ValueError("Review original instanceof dispatch")
    handlers["instanceof"] = "JS_LinuxInstanceOfLeaf"
    blocks.append(("JS_LinuxInstanceOfLeaf", rows))
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=[n for n, _ in blocks],
        core_array_own=dict(
            entry="JS_LinuxFastArrayOwnGet",
            fallback="JS_LinuxFastArrayOwnFallback",
            ABI="bool(JSContext*,JSObject*,uint32_t,JSValue*) via actual SysV C;leaf CFA8",
            rows_sha256=hashlib.sha256(
                "\n".join(array_own_rows(source, layout)).encode()
            ).hexdigest(),
        ),
        pure_helper="JS_FrameSlowDirectTryInstanceOfLeaf",
        C_ABI="int(JSContext *,JSValue *) via actual SysV typed bridge",
        scope="Complete sparse indexed-own kernels and source-owned instanceof leaf;existing dense/typed lanes and Dirty factory retained",
    )
    (output / "INDEXED-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return blocks, record


def generate(
    source,
    output,
    core,
    layout,
    *,
    route_core=True,
    platform_binding="src/x86/linux/interpreter-indexed.inc",
    leaf_condition="#if defined(__linux__) && defined(__x86_64__)",
):
    data = contract(source)
    owner = module(source, "slow-direct")
    if route_core:
        original_array = function(
            core, "static bool js_get_fast_array_element(JSContext *ctx, JSObject *p,"
        )
        expected = contract(source)["core_array_helper_sha256"]
        if hashlib.sha256(original_array.encode()).hexdigest() != expected:
            raise ValueError("Review complete original core array/typed fallback")
        signature = "static bool js_get_fast_array_element("
        replacement = original_array.replace(
            signature,
            '__attribute__((noipa,visibility("hidden"))) bool JS_LinuxFastArrayOwnFallback(',
            1,
        )
        replacement += '\nextern bool JS_LinuxFastArrayOwnGet(JSContext*,JSObject*,uint32_t,JSValue*) __attribute__((visibility("hidden")));\n'
        replacement += '_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxFastArrayOwnGet),__typeof__(&JS_LinuxFastArrayOwnFallback)),"actual core array SysV bool ABI");\n'
        replacement += "#define js_get_fast_array_element JS_LinuxFastArrayOwnGet\n"
        core = replace_one(
            core,
            original_array,
            replacement,
            "original core and cloned consumers share typed array leaf",
        )
    text = owner.BODY
    text = text.replace('".qjslcm$zzzzslowdirect"', '".data.qjs_linux_indexed"')
    text = replace_one(
        text,
        "if(mode&4)JS_FrameSlowDirectData.hits++;",
        "if(mode&4)__atomic_fetch_add(&JS_FrameSlowDirectData.hits,1,__ATOMIC_RELAXED);",
        "thread-safe observation counter",
    )
    # Linux already has a complete literal/checkpoint-aware base selector.
    # Nonselected operations keep it; do not replace it with a reduced C loop.
    text = text.replace("JS_FrameVarargsSlowSelect", "JS_LinuxIndexedBaseSlow")
    text = replace_one(
        text,
        "        return JS_FrameVarargsSlow(state);",
        "        return JS_LinuxIndexedBaseSlow(state);",
        "complete Linux nonselected base",
    )
    steps = owner.indexed_steps(source)
    publish = "js_linux_indexed_publish(state,sp,pc);"
    if steps.count("    js_frame_begin_c(state);\n") != 3:
        raise ValueError("Review three indexed entry publications")
    steps = steps.replace(
        "    js_frame_begin_c(state);\n", "    js_frame_begin_c(state);\n    " + publish + "\n"
    )
    # A key/RHS is consumed by the core on every result, including OOM. Remove
    # the VM owner before the call. Move results before any receiver release.
    needle = "val = JS_GetPropertyValue(ctx, sp[-2], sp[-1]);"
    replacement = (
        "JSValue key=sp[-1];sp[-1]=JS_UNDEFINED;"
        + publish
        + "\n                val = JS_GetPropertyValue(ctx, sp[-2], key);"
    )
    if steps.count(needle) != 2:
        raise ValueError("Review both consuming indexed getters")
    steps = steps.replace(needle, replacement)
    pattern = r"JS_FreeValue\(ctx, sp\[-2\]\);\s*sp\[-2\] = val;\s*sp--;"
    steps, count = re.subn(
        pattern,
        "JSValue receiver=sp[-2];--sp;sp[-1]=val;"
        + publish
        + "\n                        JS_FreeValue(ctx, receiver);",
        steps,
    )
    if count != 3:
        raise ValueError("Review dense/typed/generic indexed receiver releases")
    steps = replace_one(
        steps,
        "                val = sp[-1];",
        "                val = sp[-1];sp[-1]=JS_UNDEFINED;" + publish,
        "consuming indexed RHS owner",
    )
    needle = "ret = JS_SetPropertyValue(ctx, sp[-3], sp[-2], sp[-1], JS_PROP_THROW_STRICT);"
    replacement = (
        "JSValue key=sp[-2];sp[-2]=JS_UNDEFINED;"
        + publish
        + "\n                ret = JS_SetPropertyValue(ctx, sp[-3], key, val, JS_PROP_THROW_STRICT);"
    )
    steps = replace_one(steps, needle, replacement, "consuming indexed setter key/value")
    pattern = r"JS_FreeValue\(ctx, sp\[-3\]\);\s*sp -= 3;"
    steps, count = re.subn(
        pattern,
        "JSValue receiver=sp[-3];sp[-3]=sp[-2]=sp[-1]=JS_UNDEFINED;sp-=3;"
        + publish
        + "\n                            JS_FreeValue(ctx, receiver);",
        steps,
    )
    if count != 3:
        raise ValueError("Review replace/append/generic receiver releases")
    original = function(
        source_file(source, "quickjs.c").read_text(),
        "static __exception int js_operator_instanceof(JSContext *ctx, JSValue *sp)",
    )
    operator = original.replace(
        "static __exception int js_operator_instanceof(JSContext *ctx, JSValue *sp)",
        "static FRAME_CODE int js_linux_indexed_instance_operator(JSFrameRegisterState *state, JSContext *ctx, JSValue *sp, uint8_t *pc)",
        1,
    )
    operator = replace_one(
        operator,
        "    JS_FreeValue(ctx, op1);\n    JS_FreeValue(ctx, op2);\n    sp[-2] = js_bool(ret);",
        "    sp[-2]=JS_UNDEFINED;"
        + publish
        + "\n    JS_FreeValue(ctx, op1);\n    --sp;sp[-1]=js_bool(ret);"
        + publish
        + "\n    JS_FreeValue(ctx, op2);",
        "instanceof release order with published consumed slots",
    )
    instance_step = owner.instanceof_step(source).replace(
        "js_operator_instanceof(ctx, sp)", "js_linux_indexed_instance_operator(state, ctx, sp, pc)"
    )
    instance_step = replace_one(
        instance_step,
        "    js_frame_begin_c(state);\n",
        "    js_frame_begin_c(state);\n    " + publish + "\n",
        "initial instanceof C-step live window",
    )
    leaf = owner.instance_leaf(source)
    leaf = leaf.replace("#if defined(__MINGW32__) && defined(__GNUC__)", leaf_condition)
    leaf = re.sub(r"extern JSValue qjs_frame_core_js_function_hasInstance\([^;]*;\n", "", leaf)
    binding = '    JSCFunction *builtin_has_instance;\n    __asm__("lea qjs_frame_core_js_function_hasInstance(%%rip), %0" : "=r"(builtin_has_instance));\n'
    leaf = replace_one(
        leaf,
        binding,
        "    JSCFunction *builtin_has_instance=&js_function_hasInstance;\n",
        "actual same-TU intrinsic identity",
    )
    leaf = replace_one(
        leaf,
        "FRAME_CODE int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *ctx, JSValue *sp)\n{",
        "#ifdef QJS_PROPERTY_IC\n"
        "#define QJS_FAST_INSTANCEOF_CTX_ENTRY\n"
        '#include "src/common/value/instanceof-fast.inc"\n'
        "#undef QJS_FAST_INSTANCEOF_CTX_ENTRY\n"
        "#endif\n"
        "FRAME_CODE int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *ctx, JSValue *sp)\n"
        "{\n"
        "#ifdef QJS_PROPERTY_IC\n"
        "    if (JS_FastInstanceOfContext(ctx, sp))\n"
        "        return 1;\n"
        "#endif",
        "shared instanceof fast leaf entry",
    )
    wrapper = """
FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{
    if (!state->exception_pending && state->frame &&
        (*state->pc==OP_get_array_el || *state->pc==OP_get_array_el2 ||
         *state->pc==OP_put_array_el || *state->pc==OP_instanceof))
        return JS_LinuxIndexedSelect(state);
    return JS_LinuxIndexedBaseSlow(state);
}
"""
    text = (
        '#include "'
        + platform_binding
        + '"\n'
        + text
        + "\n"
        + steps
        + "\n"
        + operator
        + "\n"
        + instance_step
        + "\n"
        + leaf
    )
    text += (
        "\n"
        + scoped(source, "JS_FrameSlowDirectSelect", "JS_LinuxIndexedSelect")
        + "\n"
        + wrapper
        + "\n#undef FRAME_CODE\n#undef FRAME_INLINE\n"
    )
    target = output / "quickjs-linux-indexed.h"
    target.write_text(text)
    core += '\n#include "quickjs-linux-indexed.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/indexed_ops.py",
                "src/x86/linux/interpreter-indexed.inc",
                "src/common/value/instanceof-fast.inc",
            )
        },
        generated_sha256=sha(target),
        entries=[
            "JS_FrameSlowDirectSelect",
            "JS_LinuxIndexedSelect",
            "JS_FrameSlowDirectTryInstanceOfLeaf",
            "JS_LinuxIndexedBaseSlow",
        ],
        frame_growth=0,
        state_growth=0,
        operator_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
        publication="Source-owned opcode semantics;consumed key/RHS and released receivers leave the published stack before calls/finalizers;exact original release order",
    )
    (output / "INDEXED.json").write_text(json.dumps(record, indent=2) + "\n")
    return core


def finish_slow(source, output):
    contract(source)
    p = output / "quickjs-linux-literals.h"
    text = replace_one(
        p.read_text(),
        "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{",
        "FRAME_CODE int JS_LinuxIndexedBaseSlow(JSFrameRegisterState *state)\n{",
        "retain complete literal-aware base selector",
    )
    p.write_text(text)
    receipt = output / "LITERALS.json"
    d = json.loads(receipt.read_text())
    d["before_indexed_sha256"] = d["generated_sha256"]
    d["generated_sha256"] = sha(p)
    receipt.write_text(json.dumps(d, indent=2) + "\n")


def render_slow_selector(ids):
    """Match the accepted unified slow owner without an O(depth) classifier.

    The existing direct-selector mode is already configured at a coherent C
    boundary. Cold, disabled and observed modes retain the exact old selector.
    Literal/indexed gateways run first; for_of_next keeps its native worker.
    Everything else uses the COMPLETE checkpoint/forward/constructor executor,
    including pending exceptions. No frame, ownership or state write occurs.
    """
    name = "JS_LinuxUnifiedSlowSelect"
    return [
        '.section .text.qjs_linux_slow_selector,"ax",@progbits',
        ".p2align 4",
        ".hidden " + name,
        ".globl " + name,
        ".type " + name + ",@function",
        name + ":",
        ".cfi_startproc",
        "endbr64",
        ".hidden JS_FrameSlowDirectData, JS_LinuxLiteralBaseSlow, JS_FrameVarargsSlow, JS_LinuxIterator_for_of_next",
        "movzx eax, BYTE PTR [rip+JS_FrameSlowDirectData]",
        "and eax, 7",
        "cmp eax, 1",
        "jne linux_unified_slow_original",
        "cmp BYTE PTR [rdi+160], 0",
        "jne linux_unified_slow_complete",
        "mov rax, QWORD PTR [rdi+16]",
        f"cmp BYTE PTR [rax], {ids['for_of_next']}",
        "je JS_LinuxIterator_for_of_next",
        "linux_unified_slow_complete:",
        "jmp JS_FrameVarargsSlow",
        "linux_unified_slow_original:",
        "jmp JS_LinuxLiteralBaseSlow",
        ".cfi_endproc",
        ".size " + name + ",.-" + name,
    ]
