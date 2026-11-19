"""Shared GNU argument C owners and actual AAPCS64 root/child bindings."""

import hashlib, json, re
from arguments_c import generate as shared
from c_workers import replace_one


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare_loop(source, output, loop, enabled):
    if not enabled:
        return loop
    decl = """
struct JSFrame;
struct JSFrameRegisterState;
static JSValue JS_AArch64ArgumentsObject(struct JSFrame *,unsigned);
int JS_FrameArgumentsConstructCall(struct JSFrameRegisterState *);
"""
    loop = decl + loop
    # Generic semantic fallbacks must use the admitted argument record as well.
    for owner in (
        "src/common/call/interpreter-current-function.inc",
        "src/common/call/interpreter-current-function-null.inc",
    ):
        if owner in loop:
            loop = replace_one(
                loop,
                owner,
                "src/common/call/interpreter-arguments-special.inc",
                "complete argument special-object C fallback",
            )
    return loop


def generate(source, output, core, layout, actual_input, enabled):
    path = source / "src/arm64/linux/abi/arguments.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete argument semantic owner: " + n)
    if enabled:
        core = shared(
            source,
            output,
            core,
            layout,
            actual_input,
            route_core=False,
            forward_header="interpreter-aarch64-forward.h",
            binding_header="src/arm64/linux/interpreter-arguments.inc",
            compat_header="src/arm64/linux/interpreter-compat.inc",
            source_files=(
                "tools/common/elf/arguments_c.py",
                "src/arm64/linux/interpreter-arguments.inc",
                "src/common/call/interpreter-slow-host.inc",
                "src/common/linux/interpreter-virtual-arguments.inc",
                "src/common/call/interpreter-retained-context.inc",
                "src/common/kernel/ordinary-arguments.c",
            ),
        )
        p = output / "quickjs-linux-arguments.h"
        text = p.read_text()
        # This is the exact original allocating special-object switch. The
        # generic executor and typed native owner share it, never a new layout.
        start = text.index("    if (record->signature != ARGUMENTS_SIGNATURE) {")
        end = text.index("    *sp++ = value;", start)
        body = text[start:end].replace("state->pc[1]", "special")
        object_helper = (
            """static FRAME_CODE JSValue JS_AArch64ArgumentsObject(JSFrame *frame,unsigned special)
{
    JSStackFrame *sf=&frame->sf;
    JSFunctionBytecode *b=frame->bytecode;
    JSContext *ctx=b->realm;
    JSFrameArgumentsRecord *record=(void *)((uint8_t *)frame+FRAME_HEADER_BYTES);
    JSValue value;
"""
            + body
            + "    return value;\n}\n"
        )
        text = (
            text[:start] + "    value=JS_AArch64ArgumentsObject(frame,state->pc[1]);\n" + text[end:]
        )
        text = text.replace(
            '#include "src/arm64/linux/interpreter-arguments.inc"',
            '#pragma push_macro("FRAME_CODE")\n#pragma push_macro("FRAME_INLINE")\n#include "src/arm64/linux/interpreter-arguments.inc"',
        )
        from admission_c import function

        step = function(text, "static FRAME_CODE int js_linux_arguments_step_body(")
        clean = (
            step.replace("    JSFunctionBytecode *b = frame->bytecode;\n", "")
            .replace("    JSContext *ctx = b->realm;\n", "")
            .replace(
                "    JSFrameArgumentsRecord *record =\n        (JSFrameArgumentsRecord *)((uint8_t *)frame + FRAME_HEADER_BYTES);\n",
                "",
            )
        )
        text = replace_one(
            text,
            step,
            clean,
            "only remove declarations moved with the shared complete special-object switch",
        )
        # The helper declaration is before the loop. Define it before Step,
        # after its actual record/policy declarations have been established.
        marker = "static FRAME_CODE int js_linux_arguments_step_body("
        assert text.count(marker) == 1
        text = text.replace(marker, object_helper + "\n" + marker, 1)
        text += '\n#pragma pop_macro("FRAME_INLINE")\n#pragma pop_macro("FRAME_CODE")\n'
        p.write_text(text)
        # Real AAPCS64 aggregate wrappers; all unsupported classes/flags retain
        # their original public/internal dispatch. No Win entry ABI is copied.
        decl = """
bool JS_LinuxArgumentsCandidate(JSContext *,JSValueConst);
JSValue JS_FrameArgumentsRootBridge(JSContext *,JSValueConst,JSValueConst,JSValueConst,int,JSValueConst *,int);
"""
        marker = "\n#undef JS_CallInternal\nstatic JSValue JS_CallInternal("
        core = replace_one(
            core, marker, "\n" + decl + marker, "actual typed argument root declarations"
        )
        marker = "    return JS_FrameCallEntryDispatch(ctx,func_obj,this_obj,new_target,argc,argv,flags);"
        core = replace_one(
            core,
            marker,
            "    if(JS_LinuxArgumentsCandidate(ctx,func_obj))\n        return JS_FrameArgumentsRootBridge(ctx,func_obj,this_obj,new_target,argc,argv,flags);\n"
            + marker,
            "internal argument root after exact existing class/control guards",
        )
        marker = "    return JS_FrameCallEntryDispatch(ctx,func_obj,this_obj,JS_UNDEFINED,argc,argv,JS_CALL_FLAG_COPY_ARGV);"
        core = replace_one(
            core,
            marker,
            """    if(JS_IsObject(func_obj) && JS_VALUE_GET_OBJ(func_obj)->class_id==JS_CLASS_BYTECODE_FUNCTION &&
       JS_LinuxArgumentsCandidate(ctx,func_obj))
        return JS_FrameArgumentsRootBridge(ctx,func_obj,this_obj,JS_UNDEFINED,argc,argv,JS_CALL_FLAG_COPY_ARGV);
"""
            + marker,
            "public argument root after actual class proof",
        )
        core += '\nextern __typeof__(js_function_apply) qjs_linux_core_js_function_apply __attribute__((alias("js_function_apply"),visibility("hidden")));\n'
        record = json.loads((output / "ARGUMENTS.json").read_text())
        record.update(
            enabled=True,
            generated_sha256=sha(p),
            architecture="actual AAPCS64 C aggregates and state-only opcode/child bridge",
            native_ready=True,
            native_access=True,
            native_forward_probe=True,
        )
    else:
        (output / "quickjs-linux-arguments.h").write_text("/* Argument workers compiled OFF. */\n")
        (output / "quickjs-linux-virtual-arguments.c").write_text(
            "/* Argument virtual worker compiled OFF. */\n"
        )
        (output / "quickjs-linux-virtual-arguments-private.h").write_text(
            "/* Argument virtual types compiled OFF. */\n"
        )
        (output / "VIRTUAL-ARGUMENTS.json").write_text(
            json.dumps(dict(enabled=False, entries=[]), indent=2) + "\n"
        )
        record = dict(enabled=False, entries=[], frame_growth=0, state_growth=0)
    record.update(
        source_owners=contract["source_owners"],
        source_contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/arguments.py"),
        whole_qualification=False,
    )
    (output / "ARGUMENTS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
