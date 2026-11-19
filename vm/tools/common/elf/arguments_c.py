"""Source-owned C argument and scoped host boundary helpers."""

import hashlib
import json
import re
from admission_c import function
from c_workers import replace_one


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def scoped(source, body_name, public_name):
    from admission_c import function

    template = function(
        (source / "src/common/call/interpreter-slow-host.inc").read_text(),
        "static QJS_FRAME_SLOW_HOST_CODE JSValue js_frame_slow_host_call(",
    )
    body = template[template.index("{") :]
    body = replace_one(body, "    JSValue result;", "    int result;", "argument C boundary result")
    old = "js_frame_legacy_call(ctx, callee, receiver, argc, argv)"
    if body.count(old) != 2:
        raise ValueError("Review complete argument scope owner")
    body = body.replace(old, body_name + "(state)")
    body = body.replace(
        "    return result;",
        "    if(state->frame)state->frame->sf.cur_sp=NULL;\n    return result;",
    )
    body = replace_one(
        body,
        "original:\n    return " + body_name + "(state);",
        "original:\n    result=" + body_name + "(state);\n"
        "    if(state->frame)state->frame->sf.cur_sp=NULL;\n    return result;",
        "argument unshared boundary cursor",
    )
    declarations = """    JSFrame *frame=state->frame;
    JSFrameSegment *segment=state->segment;
    JSContext *ctx=frame->bytecode->realm;
    size_t used=state->used_bytes;
    uint8_t *pc=state->pc;
    JSValue *sp=state->sp;
    js_frame_begin_c(state);
    js_frame_finish_c(state);
"""
    return (
        "FRAME_CODE int "
        + public_name
        + "(JSFrameRegisterState *state)\n"
        + body.replace("{\n", "{\n" + declarations, 1)
    )


def generate(
    source,
    output,
    core,
    layout,
    actual_input,
    *,
    route_core=True,
    forward_header,
    binding_header,
    compat_header,
    source_files=(),
):
    raw = (source / "src/common/kernel/ordinary-arguments.c").read_text()
    text = raw[raw.index("#include <stdatomic.h>") :]
    from admission_c import function

    signature = "static FRAME_INLINE bool js_frame_forward_is_call("
    predicate = function(text, signature)
    retained = function((output / forward_header).read_text(), signature)
    if re.sub(r"\s+", "", predicate) != re.sub(r"\s+", "", retained):
        raise ValueError("Review shared arguments/.call identity predicate")
    text = replace_one(text, predicate, "", "reuse exact existing .call identity owner")
    begin = text.index("extern JSValue qjs_frame_core_JS_NewObjectFromShape")
    end = text.index("static FRAME_INLINE unsigned arguments_mode", begin)
    text = text[:begin] + text[end:]
    text = text.replace('".qjzzpm"', '".data.qjs_linux_arguments"')
    text = text.replace("js_frame_opcode_sizes", "js_linux_arguments_opcode_sizes")
    text = text.replace("JS_FrameSlowDirectSelect", "JS_FrameInterpSlow")
    text = text.replace("JS_FrameResolveInternal(ctx, &func)", "JS_LinuxArgumentsInitialize(ctx)")
    text = text.replace("JS_FrameCEntry(", "JS_LegacyCallInternal(")
    text = replace_one(
        text,
        "    if ((arguments_mode() & 3) != 1 || !js_frame_register_enabled(b->realm->rt))",
        "    if (!js_linux_arguments_prefix(b)) return false;\n"
        "    if ((arguments_mode() & 3) != 1 || !js_frame_register_enabled(b->realm->rt))",
        "do not poison ordinary unknown targets before their retained classifier",
    )
    text = replace_one(
        text,
        '        mode = getenv("QJS_DISABLE_FRAME_ARGUMENTS") ? 2 : 1;',
        "        atomic_store_explicit(&JS_LinuxArgumentsLengthControl,\n"
        '            getenv("QJS_DISABLE_NATIVE_LENGTH")?2:1,memory_order_relaxed);\n'
        '        mode = getenv("QJS_DISABLE_FRAME_ARGUMENTS") ? 2 : 1;',
        "shared argument length policy",
    )
    text = replace_one(
        text,
        "    kind = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);",
        "    kind = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);\n    (void)kind;",
        "retained computed argument descriptor classification",
    )
    hook = "FRAME_CODE int JS_FrameArgumentsStep(JSFrameRegisterState *state)\n{"
    text = replace_one(
        text,
        hook,
        '__attribute__((visibility("hidden"))) int JS_LinuxVirtualArgumentsStep(JSFrameRegisterState *);\n'
        + hook
        + "\n    int virtual_result=JS_LinuxVirtualArgumentsStep(state);\n    if(virtual_result)return virtual_result<0?JS_FrameInterpSlow(state):0;",
        "exact nonescaping forwarding wrapper",
    )
    text = replace_one(
        text,
        "    if (!result)\n        return JS_FrameCallForwardNativeProbe(state);\n    return result;",
        "    return result;",
        "native returning probe owns private fallback transfer",
    )
    text = text.replace("extern int JS_FrameCallForwardNativeProbe(JSFrameRegisterState *);", "")
    for name in ("Try", "Step"):
        old = "FRAME_CODE int JS_FrameArguments" + name + "(JSFrameRegisterState *state)"
        text = replace_one(
            text,
            old,
            "static "
            + old.replace(
                "JS_FrameArguments" + name, "js_linux_arguments_" + name.lower() + "_body"
            ),
            "same owner behind typed coherent argument " + name,
        )
    text = replace_one(
        text,
        "    js_frame_finish_c(&state);\n    while (!JS_FrameInterp(&state))",
        "    js_frame_finish_c(&state);\n    state.frame->sf.cur_sp=NULL;\n    while (!JS_FrameInterp(&state))",
        "running argument root cursor",
    )
    ctor = (source / "src/common/kernel/argument-constructor.c").read_text()
    ctor = ctor[ctor.index('__attribute__((section(".qjzzpm"),') :]
    ctor = ctor.replace('".qjzzpm"', '".data.qjs_linux_arguments"')
    ctor = ctor.replace("JS_FrameConstructPolicyForArguments", "js_frame_construct_policy")
    ctor = ctor.replace("JS_FrameArgumentsTargetForConstruct", "js_frame_arguments_target")
    ctor = ctor.replace("JS_FrameArgumentsPushForConstruct", "js_frame_arguments_push")
    ctor = ctor.replace("JS_FrameSlowDirectSelect", "JS_FrameInterpSlow")
    ctor = ctor.replace("js_frame_opcode_sizes", "js_linux_arguments_constructor_sizes")
    ctor = ctor.replace("constructor_enabled", "js_linux_arguments_constructor_enabled").replace(
        "constructor_policy", "js_linux_arguments_constructor_policy"
    )
    ctor = replace_one(
        ctor,
        "object = js_create_from_ctor(ctx, argv[-1], JS_CLASS_OBJECT);",
        "object = js_linux_construct_host_create(state,parent,state->segment,state->used_bytes,\n"
        "        parent->sf.cur_pc,sp,ctx,argv[-1]);",
        "coherent argument constructor prototype/getter allocation",
    )
    ctor = replace_one(
        ctor,
        "    FRAME_ROOT(state->frame) = 3;",
        "    FRAME_ROOT(state->frame) = 3;\n    state->frame->sf.cur_sp=NULL;",
        "running argument constructor child cursor",
    )
    # This C candidate reproduces the existing 17-byte native prologue filter.
    candidate = """
static FRAME_CODE bool js_linux_arguments_prefix(JSFunctionBytecode *b)
{
    if(FRAME_SUPPORTED(b))return false;
    if(FRAME_KIND(b)==ARGUMENTS_KIND && ARGUMENTS_MARKER(b)==ARGUMENTS_READY)return true;
    if(FRAME_KIND(b)==ARGUMENTS_REJECTED && ARGUMENTS_MARKER(b)==ARGUMENTS_DENIED)return false;
    unsigned limit=b->byte_code_len<17?b->byte_code_len:17;
    if(b->byte_code_len<2||b->byte_code_len>FRAME_MAX_CODE)return false;
    for(unsigned p=0;p<limit;) {
        if(b->byte_code_buf[p]==OP_push_this)p++;
        else if(b->byte_code_buf[p]==OP_special_object) {
            if(++p>=limit)return false;
            unsigned kind=b->byte_code_buf[p++];
            if(kind<=OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS)return true;
            if(kind>OP_SPECIAL_OBJECT_HOME_OBJECT)return false;
        } else return false;
        if(p>=limit)return false;
        unsigned op=b->byte_code_buf[p++];
        if(op==OP_put_loc8)p++;
        else if(op<OP_put_loc0||op>OP_put_loc3)return false;
    }
    return false;
}
FRAME_CODE bool JS_LinuxArgumentsCandidate(JSContext *ctx,JSValueConst func)
{
    (void)ctx;
    return js_linux_arguments_prefix(JS_VALUE_GET_OBJ(func)->u.func.function_bytecode);
}
"""
    text = (
        '#include "'
        + binding_header
        + '"\n'
        + "static FRAME_CODE bool js_linux_arguments_prefix(JSFunctionBytecode *);\n"
        + text
        + "\n"
        + candidate
        + "\n"
        + ctor
        + "\n"
    )
    text += scoped(source, "js_linux_arguments_try_body", "JS_FrameArgumentsTry") + "\n"
    text += scoped(source, "js_linux_arguments_step_body", "JS_FrameArgumentsStep") + "\n"
    text += "\n#undef FRAME_CODE\n#undef FRAME_INLINE\n"
    target = output / "quickjs-linux-arguments.h"
    target.write_text(text)
    declaration = """
__attribute__((visibility("hidden"))) bool JS_LinuxArgumentsCandidate(JSContext *,JSValueConst);
__attribute__((visibility("hidden"))) JSValue JS_FrameArgumentsRootBridge(JSContext *,JSValueConst,
    JSValueConst,JSValueConst,int,JSValueConst *,int);
"""
    if route_core:
        marker = "\n#undef JS_CallInternal\nstatic JSValue JS_CallInternal("
        core = replace_one(
            core, marker, "\n" + declaration + marker, "typed argument root declarations"
        )
        marker = "    if (FRAME_INTERNAL_STATE(ctx->rt) != 1 ||\n"
        core = replace_one(
            core,
            marker,
            "    if (FRAME_INTERNAL_STATE(ctx->rt)==1 && JS_LinuxArgumentsCandidate(ctx,func_obj))\n"
            "        return JS_FrameArgumentsRootBridge(ctx,func_obj,this_obj,new_target,argc,argv,flags);\n"
            + marker,
            "internal original entry decline to argument root",
        )
        marker = (
            "    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, JS_UNDEFINED, argc,\n"
        )
        core = replace_one(
            core,
            marker,
            "    if(JS_LinuxArgumentsCandidate(ctx,func_obj))\n"
            "        return JS_FrameArgumentsRootBridge(ctx,func_obj,this_obj,JS_UNDEFINED,argc,argv,JS_CALL_FLAG_COPY_ARGV);\n"
            + marker,
            "actual public argument root",
        )
    core += '\n#include "quickjs-linux-arguments.h"\n'
    core += '\nextern __typeof__(js_frame_arguments_push) JS_LinuxVirtualArgumentsPush __attribute__((alias("js_frame_arguments_push"),visibility("hidden")));\n'
    from virtual_arguments_c import generate as generate_virtual_arguments

    generate_virtual_arguments(source, output, actual_input, layout, compat_header=compat_header)

    record = dict(
        status="generated-not-qualified",
        source_files={
            n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in source_files
        },
        generated_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        entries=[
            "JS_FrameArgumentsTry",
            "JS_FrameArgumentsStep",
            "JS_FrameArgumentsForwardTry",
            "JS_FrameArgumentsRootBridge",
            "JS_FrameArgumentsConstructCall",
            "JS_LinuxArgumentsCandidate",
        ],
        frame_growth=0,
        state_growth=0,
        private_argument_prefix=16,
        scope="Complete source-owned argument workers plus actual Linux C root/constructor/scoped boundary and measured native entry/access/forwarding",
    )
    (output / "ARGUMENTS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
