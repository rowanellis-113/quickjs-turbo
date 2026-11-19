"""Source-owned C indexed/instanceof workers."""

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file
from admission_c import function
from c_workers import module, replace_one
from iterators_c import scoped


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, *, contract_rel):
    data = json.loads((source / contract_rel).read_text())
    owners = data.get("owners") or data.get("source_owners") or {}
    for n, h in owners.items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Review accepted indexed owner: " + n)
    return data


def generate(
    source,
    output,
    core,
    layout,
    *,
    route_core=True,
    contract_rel,
    platform_binding,
    leaf_condition,
    bind_has_instance="    JSCFunction *builtin_has_instance=&js_function_hasInstance;\n",
):
    data = contract(source, contract_rel=contract_rel)
    owner = module(source, "slow-direct-c")
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
    from common.paths import source_file

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
    leaf = owner.instance_leaf(
        source, leaf_condition=leaf_condition, bind_has_instance=bind_has_instance
    )
    leaf = re.sub(r"extern JSValue qjs_frame_core_js_function_hasInstance\([^;]*;\n", "", leaf)
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
        owners=data.get("owners") or data.get("source_owners", {}),
        source_files={
            n: sha(source / n) for n in ("tools/common/elf/indexed_ops_c.py", platform_binding)
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
