"""Source-owned GNU iterator workers with the measured Linux C/ELF boundary.

The existing semantic owner remains responsible for all exceptional unwinding.
The inherited JS-next continuation reuses its exact ordinary enter_frame body;
array guards and done/value extraction come from the accepted GNU generators.
"""

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

OWNERS = tuple(
    "tools/x86/common/codegen/" + name + ".py"
    for name in ("iterator", "iterator-fast", "iterator-slow", "iterator-checkpoint", "varargs")
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal(source, owner, name, *, augmented=False):
    """Read reviewed C factory literals without executing COFF generators."""
    tree = ast.parse((source / ("tools/x86/common/codegen/" + owner + ".py")).read_text())
    generator = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == ("checkpoint_text" if owner == "varargs" else "generate")
    )
    values = []
    for node in ast.walk(generator):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif augmented and isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            value = node.value
            while isinstance(value, (ast.Call, ast.BinOp)):
                if isinstance(value, ast.BinOp):
                    value = value.left
                elif isinstance(value.func, ast.Attribute):
                    value = value.func.value
                else:
                    break
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values.append(value.value)
    if not values or (len(values) != 1 and not augmented):
        raise ValueError("Review iterator factory literal: " + owner + ":" + name)
    return "".join(values)


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/iterators.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review accepted iterator algorithm owner: " + name)
    return data


def append(source, output, stream, handlers):
    contract(source)
    from admission import vm_block

    blocks = []
    for op in module(source, "iterator").OPS:
        name = "JS_LinuxIteratorOpcode_" + op
        rows = [r.replace("JS_FrameInterpRegExp", "JS_LinuxIterator_" + op) for r in vm_block()]
        blocks.append((name, rows))
        handlers[op] = name
    record = dict(
        status="generated-not-qualified",
        owners={n: sha(source_file(source, n)) for n in OWNERS},
        functions=[n for n, _ in blocks],
        c_helpers=["JS_LinuxIterator_" + op for op in module(source, "iterator").OPS],
        C_ABI="actual SysV state-only int; ordinary VM CFA retained",
        frame_growth=0,
        state_growth=0,
    )
    (output / "ITERATORS-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return blocks, record


def dense_workers(source):
    fast = literal(source, "iterator-fast", "body")
    fast = fast[fast.index("FRAME_CODE int JS_FrameIteratorArrayNext(") :]
    # Same-TU compiler address materialization, never MinGW refptr/inline ABI.
    fast = fast.replace("qjs_frame_core_js_array_iterator_next", "js_array_iterator_next")
    fast = replace_one(
        fast,
        '    __asm__("lea js_array_iterator_next(%%rip), %0" : "=r"(expected_next));',
        "    expected_next = &js_array_iterator_next;",
        "actual Linux C function identity",
    )
    begin = fast.index("    /* Materialize this inherited function address")
    end = fast.index("    expected_next = ", begin)
    fast = fast[:begin] + fast[end:]
    fast = replace_one(
        fast,
        "ITERATOR_KIND(b)&2",
        "ITERATOR_KIND(b)&4",
        "array enabled bit independent from combined varargs bit",
    )
    slow = literal(source, "iterator-slow", "body")
    slow = slow[slow.index("FRAME_CODE int JS_FrameIteratorSlowNext(") :]
    start = fast.index("    JSObject *method,*iterator,*array;")
    end = fast.index("    frame->saved_sp=sp;", start)
    guard = fast[start:end]
    at = guard.index("    if (!(ITERATOR_KIND(b)&4)")
    declaration, checks = guard[:at], guard[at:]
    slow = slow.replace("DECLARATION", declaration.rstrip()).replace("CHECKS", checks.rstrip())
    slow = replace_one(
        slow,
        "(ITERATOR_KIND(b)&3)!=3",
        "(ITERATOR_KIND(b)&5)!=5",
        "extended and array guard enable bits",
    )
    slow = slow.replace("ITERATOR_KIND(b)&16", "ITERATOR_KIND(b)&32")
    slow = slow.replace("ITERATOR_KIND(b)|=16", "ITERATOR_KIND(b)|=32")
    slow = slow.replace("ITERATOR_KIND(b)|=8", "ITERATOR_KIND(b)|=16")
    slow = slow.replace("ITERATOR_KIND(b)&8", "ITERATOR_KIND(b)&16")
    slow = slow.replace("qjs_frame_iterator_legacy_next", "js_for_of_next")
    fast = replace_one(
        fast,
        "FRAME_CODE int JS_FrameIteratorArrayNext(JSFrameRegisterState *state)",
        "static bool js_linux_try_dense_next(JSFrameRegisterState *state)",
        "reuse the guarded dense step before publishing a shared C anchor",
    )
    fast = replace_one(
        fast,
        "    return 0;\nslow:\n    return JS_FrameIteratorOp_for_of_next(state);",
        "    return true;\nslow:\n    return false;",
        "leave the iterator and operand stack untouched on a guard miss",
    )
    fast += """
FRAME_CODE int JS_FrameIteratorArrayNext(JSFrameRegisterState *state)
{
    if (js_linux_try_dense_next(state))
        return 0;
    return JS_FrameIteratorOp_for_of_next(state);
}
"""
    return fast + "\n" + slow


def checkpoint_workers(source, full):
    helpers = literal(source, "iterator-checkpoint", "helpers", augmented=True)
    # Prefix byte30 belongs to leaf/argument descriptors. The combined iterator
    # tail byte also reserves bit1 for varargs; do not alias either namespace.
    helpers = helpers.replace("FRAME_ITERATOR_KIND(b)&64", "FRAME_ITERATOR_KIND(b)&128")
    helpers = helpers.replace("FRAME_ITERATOR_KIND(b)|=64", "FRAME_ITERATOR_KIND(b)|=128")
    helpers = helpers.replace("FRAME_ITERATOR_KIND(b)|=32", "FRAME_ITERATOR_KIND(b)|=64")
    helpers = helpers.replace("FRAME_ITERATOR_KIND(b)&32", "FRAME_ITERATOR_KIND(b)&64")
    helpers = helpers.replace("JS_FrameIteratorSlow(", "JS_FrameVarargsSlow(")
    helpers = helpers.replace("extern bool", "FRAME_CODE bool").replace(
        "extern int", "FRAME_CODE int"
    )
    # The shared source already checks every measured frame/state field below.
    helpers = helpers.replace(
        "QJS_ABI_OFF_JSStackFrame_cur_sp && FRAME_STACK_CORO_OFFSET_VALID",
        "QJS_ABI_OFF_JSStackFrame_cur_sp",
    )
    core = source_file(source, "quickjs.c").read_text()
    original = function(core, "static JSValue JS_IteratorNext(")
    tail = original[original.index("    if (JS_IsException(obj))") :]
    value = """
FRAME_CODE JSValue JS_FrameIteratorCheckpointValue(JSContext *ctx,JSValue obj,int *pdone)
{
    JSValue value,done_val;
    int done=2;
    if (!JS_IsObject(obj)) {
        JS_FreeValue(ctx,obj);
        JS_ThrowTypeError(ctx,"iterator must return an object");
        *pdone=false;
        return JS_EXCEPTION;
    }
""" + tail.replace("JS_GetProperty(ctx, obj,", "js_frame_iterator_checkpoint_getfield(ctx, obj,")
    enter = full[full.index("enter_frame:\n") : full.index("dispatch:\n")]
    footer_start = full.index("slow_step_done:")
    footer = full[footer_start : full.index("\n#undef CASE", footer_start)]
    counters = module(source, "generate-slow").COUNTERS
    stats = (
        "\n#ifdef QJS_INTERP_FRAME_DIAGNOSTICS\n"
        + "".join(
            "    "
            + (
                "unsigned"
                if n in ("depth", "max_depth")
                else "size_t"
                if n == "peak_bytes"
                else "uint64_t"
            )
            + " "
            + n
            + "=state->"
            + n
            + ";\n"
            for n in counters
        )
        + "#endif\n"
    )
    push = literal(source, "iterator-checkpoint", "push")
    push = push.replace("STATS", stats).replace("ENTER", enter).replace("FOOTER", footer)
    # This separate entry has no incoming goto to the retained source label.
    push = replace_one(push, "enter_frame:\n", "", "dedicated next entry label")
    push = push.replace("JS_FrameIteratorSlow(", "JS_FrameVarargsSlow(")
    selectors = literal(source, "iterator-checkpoint", "selectors")
    selectors = selectors.replace("JS_FrameIteratorSlow(", "JS_FrameVarargsSlow(")
    selectors = selectors.replace(
        "return JS_FrameIteratorOp_for_of_next(state);", "return JS_FrameIteratorArrayNext(state);"
    )
    return (
        helpers,
        value + "\n" + push + "\n" + selectors,
        hashlib.sha256(tail.encode()).hexdigest(),
    )


def scoped(source, body_name, name):
    from arguments import scoped as shared_scope

    return (
        shared_scope(source, body_name, name)
        .replace("FRAME_CODE int ", "QJS_FRAME_SLOW_HOST_CODE int ", 1)
        .replace(
            "if(state->frame)state->frame->sf.cur_sp=NULL;",
            "if(state->frame && !FRAME_CHECKPOINT(state->frame))state->frame->sf.cur_sp=NULL;",
        )
    )


def generate(source, output, layout):
    data = contract(source)
    path = output / "quickjs-linux-construct.h"
    full = path.read_text()
    inherited = full
    # A normal C-step return can resume a paused next() parent. Its real
    # output top must survive until the checkpoint consumes the result.
    full = replace_one(
        full,
        "    else if (frame) frame->sf.cur_sp=NULL;",
        "    else if (frame && !FRAME_CHECKPOINT(frame)) frame->sf.cur_sp=NULL;",
        "complete slow return preserves a paused checkpoint parent",
    )
    helpers, checkpoint, tail_sha = checkpoint_workers(source, full)
    # Reuse the superset's exact safer exception hook, never the obsolete
    # standalone hook that releases before clearing the consumed live slot.
    hook = literal(source, "varargs", "hook")
    full = replace_one(
        full,
        "exception:\n    sf->cur_pc = pc;",
        "exception:\n" + hook + "    sf->cur_pc = pc;",
        "active next exception cleanup",
    )
    original_trace = """    if (needs_backtrace(rt->current_exception) || JS_IsUndefined(ctx->error_back_trace))
        build_backtrace(ctx, rt->current_exception, JS_UNDEFINED, NULL, 0, 0, 0);"""
    trace = """    if (needs_backtrace(rt->current_exception) || JS_IsUndefined(ctx->error_back_trace)) {
        JSFrame *trace_frame;
        for(trace_frame=frame;trace_frame;trace_frame=js_frame_parent(trace_frame))
            if(FRAME_CHECKPOINT(trace_frame))trace_frame->sf.cur_pc+=2;
        build_backtrace(ctx, rt->current_exception, JS_UNDEFINED, NULL, 0, 0, 0);
        for(trace_frame=frame;trace_frame;trace_frame=js_frame_parent(trace_frame))
            if(FRAME_CHECKPOINT(trace_frame))trace_frame->sf.cur_pc-=2;
    }"""
    full = replace_one(full, original_trace, trace, "checkpoint backtrace pc")
    start = full.index("        CASE(OP_for_of_next):")
    end = full.index("        CASE(OP_iterator_close):", start)
    replacement = literal(source, "iterator-checkpoint", "replacement")
    replacement = replacement.replace(
        "js_frame_iterator_checkpoint_admit(", "JS_FrameIteratorCheckpointAdmit("
    )
    replacement = replace_one(
        replacement,
        "                    JS_FreeValue(ctx,sp[offset]);\n                    sp[offset]=JS_UNDEFINED;",
        "                    JSValue consumed=sp[offset];\n"
        "                    sp[offset]=JS_UNDEFINED;\n                    JS_FreeValue(ctx,consumed);",
        "checkpoint slow consumes iterator owner before observable release",
    )
    replacement = replace_one(
        replacement,
        "                sp+=2;\n                goto dispatch;",
        "                sp+=2;\n                sf->cur_sp=sp;\n                goto dispatch;",
        "completed value/done ordinary live window",
    )
    replacement = replacement.replace(
        "JS_FrameIteratorSlowNext(ctx,sp,offset)",
        "js_linux_construct_host_next(state,frame,segment,used_bytes,pc,sp,ctx,offset)",
    )
    full = full[:start] + replacement + full[end:]
    select = """FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{"""
    full = replace_one(
        full,
        select,
        select
        + """
    if (!state->exception_pending && *state->pc==OP_for_of_next)
        return JS_LinuxIterator_for_of_next(state);
    if (state->iterator_checkpoint_depth)
        return JS_FrameVarargsSlow(state);""",
        "all slow returns retain the active next protocol",
    )
    declarations = """
FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state);
FRAME_CODE int JS_FrameIteratorCheckpointPush(JSFrameRegisterState *state);
FRAME_CODE JSValue JS_FrameIteratorCheckpointValue(JSContext *,JSValue,int *);
FRAME_CODE int JS_FrameIteratorArrayNext(JSFrameRegisterState *state);
FRAME_CODE int JS_FrameIteratorSlowNext(JSContext *,JSValue *,int);
#define ITERATOR_KIND(b) FRAME_ITERATOR_KIND(b)
"""
    boundaries = []
    scopes = []
    bodies = module(source, "iterator").bodies(source)[0]
    boundary_template = literal(source, "iterator", "boundary")
    for op, body in bodies.items():
        body = body.split(":", 1)[1].replace("BREAK;", "goto iterator_done;")
        boundary = boundary_template % (op, body)
        # These workers execute inside the same proven coherent C scope.
        boundary = boundary.replace(
            "js_for_of_next(ctx, sp, offset)", "JS_FrameIteratorSlowNext(ctx, sp, offset)"
        )
        boundary = boundary.replace("JS_FrameIteratorSlow(", "JS_FrameVarargsSlow(")
        boundary = boundary.replace(
            "    js_frame_finish_c(state);\n    return 0;",
            "    if(!FRAME_CHECKPOINT(frame))sf->cur_sp=NULL;\n"
            "    js_frame_finish_c(state);\n    return 0;",
        )
        if "goto exception;" not in body:
            boundary = boundary[: boundary.index("\nexception:")] + "\n}\n"
        boundary = boundary.replace(
            "FRAME_CODE int JS_FrameIteratorOp_" + op + "(",
            "static FRAME_CODE int js_linux_iterator_" + op + "_body(",
        )
        if op == "for_of_next":
            boundary += """
FRAME_CODE int JS_FrameIteratorOp_for_of_next(JSFrameRegisterState *state)
{ return js_linux_iterator_for_of_next_body(state); }
"""
            scoped_next = scoped(
                source, "JS_FrameIteratorCheckpointOp", "js_linux_iterator_for_of_next_scoped"
            ).replace(
                "QJS_FRAME_SLOW_HOST_CODE int ",
                "static QJS_FRAME_SLOW_HOST_CODE int ",
                1,
            )
            scopes.append(
                '#include "src/common/call/fast-for-of-next.inc"\n'
                + scoped_next
                + """
static bool js_linux_try_dense_next(JSFrameRegisterState *state);
QJS_FRAME_SLOW_HOST_CODE int JS_LinuxIterator_for_of_next(JSFrameRegisterState *state)
{
    if (!state->exception_pending && state->frame && !FRAME_CHECKPOINT(state->frame)) {
        int offset = -3 - (int)state->pc[1];
        JSValue *sp = state->sp;
        if (JS_IsObject(sp[offset]) && JS_IsObject(sp[offset + 1])) {
            JSObject *it = JS_VALUE_GET_OBJ(sp[offset]);
            JSObject *method = JS_VALUE_GET_OBJ(sp[offset + 1]);
            if (it->class_id == JS_CLASS_ARRAY_ITERATOR) {
                if (js_linux_try_dense_next(state)) {
                    state->frame->sf.cur_sp = NULL;
                    return 0;
                }
            } else if (method->class_id == JS_CLASS_C_FUNCTION &&
                method->u.cfunc.cproto == JS_CFUNC_iterator_next) {
                int r = js_fast_cfunc_for_of_next_impl(state);
                return r == 2 ? 0 : r;
            }
        }
    }
    return js_linux_iterator_for_of_next_scoped(state);
}
"""
            )
        else:
            scopes.append(
                scoped(source, "js_linux_iterator_" + op + "_body", "JS_LinuxIterator_" + op)
            )
        boundaries.append(boundary)
    declarations += "".join(
        "QJS_FRAME_SLOW_HOST_CODE int JS_LinuxIterator_" + op + "(JSFrameRegisterState *state);\n"
        for op in bodies
    )
    checkpoint = replace_one(
        checkpoint,
        "            JS_FreeValue(ctx,sp[offset]);sp[offset]=JS_UNDEFINED;",
        "            JSValue consumed=sp[offset];sp[offset]=JS_UNDEFINED;\n"
        "            JS_FreeValue(ctx,consumed);",
        "checkpoint opcode consumes iterator owner before observable release",
    )
    # Function declarations precede the complete slow switch, definitions keep
    # its unchanged enter/return/cleanup owner and original C type visibility.
    full = (
        declarations
        + helpers
        + full
        + "\n"
        + dense_workers(source)
        + "\n"
        + checkpoint
        + "\n"
        + "\n".join(boundaries)
    )
    full += "\n#undef ITERATOR_KIND\n"
    path.write_text(full)
    host_path = output / "quickjs-linux-construct-host.h"
    host = host_path.read_text()
    if host.count("js_for_of_next(ctx, sp, offset)") != 2:
        raise ValueError("Review coherent and original next helper branches")
    host = host.replace(
        "js_for_of_next(ctx, sp, offset)", "JS_FrameIteratorSlowNext(ctx, sp, offset)"
    )
    host += "\n" + "\n".join(scopes)
    host_path.write_text(host)
    construct_path = output / "CONSTRUCT.json"
    construct = json.loads(construct_path.read_text())
    construct["before_iterator_sha256"] = construct["generated_sha256"]
    construct["generated_sha256"] = sha(path)
    construct["host_sha256"] = sha(host_path)
    construct["post_iterator_transform"] = (
        "Source-owned native JS-next/checkpoint and dense-array workers;superset cleanup retained"
    )
    construct_path.write_text(json.dumps(construct, indent=2) + "\n")
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        platform_source="tools/x86/linux/iterators.py",
        platform_sha256=sha(source / "tools/x86/linux/iterators.py"),
        original_complete_owner_sha256=hashlib.sha256(inherited.encode()).hexdigest(),
        generated_sha256=sha(path),
        host_sha256=sha(host_path),
        next_value_tail_sha256=tail_sha,
        iterator_offset=layout["offsets"]["JSFunctionBytecode.pc2line_len"] + 4,
        metadata_bits=data["metadata_bits"],
        entries=["JS_LinuxIterator_" + op for op in bodies]
        + [
            "JS_FrameIteratorCheckpointPush",
            "JS_FrameIteratorCheckpointValue",
            "JS_FrameIteratorCheckpointOp",
            "JS_FrameIteratorArrayNext",
            "JS_FrameIteratorSlowNext",
        ],
        frame_growth=0,
        state_growth=0,
        extra_GC_roots=0,
        scope="Native JS-next/checkpoint/array iteration and typed opcode workers;not append/apply/fusion/literal or final qualification",
    )
    (output / "ITERATORS.json").write_text(json.dumps(record, indent=2) + "\n")
