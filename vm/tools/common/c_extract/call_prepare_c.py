"""Shared prepared .call C data layout and commit kernel extractor."""

import importlib.util
from common.paths import tool_path as _frame_tool_path

DATA = "JS_FrameCallPrepareData"
KERNEL = "JS_FrameCallPrepareCommit"
ONE = "JS_FrameCallPrepareOne"
DEEP = "JS_FrameCallPrepareDeep"
EXEC = "JS_FrameCallPrepareExecute"


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "prepared_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


DATA_TYPE = r"""
typedef struct JSFramePrepareData {
    unsigned char control;
    unsigned char owned_control, reserved[6];
    uint64_t leaf_hits, prepared_entries, depths[65];
} JSFramePrepareData;
_Static_assert(sizeof(JSFramePrepareData)==544 && offsetof(JSFramePrepareData,owned_control)==1 && offsetof(JSFramePrepareData,leaf_hits)==8 &&
    offsetof(JSFramePrepareData,prepared_entries)==16 && offsetof(JSFramePrepareData,depths)==24,
    "prepared diagnostics are separate from every frame and boundary record");
"""


def prepared_commit_body(body):
    """Shared prepared constructor without compiler-object or TU ownership."""
    marker = "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)"
    body = body.replace(
        marker,
        "FRAME_CODE int "
        + KERNEL
        + "(JSFrameRegisterState *state, JSValueConst *prepared_target,\n"
        "    JSValue *prepared_argv, unsigned geometry)",
    )
    lo = body.index("    if (!((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3])")
    last = "    target_func=callee;target_this=receiver;"
    hi = body.index(last, lo) + len(last)
    body = (
        body[:lo]
        + """    /* Native admission proved a warm supported JS target and genuine builtin
       wrappers, without a safepoint. Preserve the original operand window. */
    argc=geometry&65535;depth=geometry>>16;size=3;method=1;
    tail=op==OP_tail_call_method;
    original_argv=prepared_argv;original_func=original_argv[-1];
    original_this=original_argv[-2];callee=*prepared_target;
    target=JS_VALUE_GET_OBJ(callee)->u.func.function_bytecode;
    receiver=argc>=depth?original_argv[depth-1]:JS_UNDEFINED;
    argv=original_argv+(argc<depth?argc:depth);
    count=argc>depth?argc-depth:0;
    target_func=callee;target_this=receiver;"""
        + body[hi:]
    )
    # Execute reaches C only with leaf control !=1, or after the complete
    # inherited leaf predicate has failed. Quota/near-poll failures go to H,
    # never here. Therefore this old branch cannot succeed for the descriptor.
    # Keep quota, poll rollback, ownership, logical frames and publication.
    lo = body.index("    if (((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3]==1 &&")
    hi = body.index("    /* There is now no allocation, JS, callback", lo)
    removed = body[lo:hi]
    assert removed.count("js_frame_forward_leaf(target,argv,count,&leaf_value)") == 1
    assert "result=2;goto done;" in removed and "poll_ctx->interrupt_counter--;" in removed
    body = (
        body[:lo]
        + "    /* Native descriptor already classified this nonleaf/leaf-disabled target. */\n"
        + body[hi:]
    )
    return body
