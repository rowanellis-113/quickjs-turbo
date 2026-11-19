"""Complete source-owned frame-free call family over actual AAPCS64 C types."""

import hashlib, json
from compiler_projection_c import actual_type_prefix
from admission_c import function
from c_workers import replace_one


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


BRIDGE = """    // x28 is the existing VM scratch register,not a data-frame field.
    // A decline restarts ordinary admission with original PC/SP/arguments.
    tbnz x28, #62, .Lcall_leaf_original
    ldr w12, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w12, #30
    b.hi .Lcall_leaf_original
    lsl x28, x17, #32
    orr x28, x28, x0
    ldr x0, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x0, [x0, #ARM_OFF_JSFunctionBytecode_realm]
    mov w5, w28
    mov x6, x2
    mov x1, x3
    mov x2, x4
    mov x3, #0
    mov x4, #ARM_CONST_JS_TAG_UNDEFINED
    tbz x28, #32, .Lcall_leaf_this_ready
    ldp x3, x4, [x6, #-32]
.Lcall_leaf_this_ready:
    mov w7, #1
    bl JS_FrameAArch64CallLeaf
    cmp x1, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lcall_leaf_decline
    ldrb w9, [x20]
    sub w9, w9, #ARM_OP_call0
    cmp w9, #3
    mov x10, #3
    mov x11, #1
    csel x10, x11, x10, ls
    add x20, x20, x10
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    lsr x17, x28, #32
    and w9, w17, #1
    add w9, w9, w28
    add w9, w9, #1
    tbz w17, #1, .Lcall_leaf_pending
    orr w9, w9, #0x8000
.Lcall_leaf_pending:
    strh w9, [x22, #ARM_OFF_JSFrame_pending]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    add x26, x26, #1
    b .Lhost_return
.Lcall_leaf_decline:
    mov w0, w28
    lsr x17, x28, #32
    orr x28, x28, #0x4000000000000000
    ldrb w9, [x20]
    sub w9, w9, #ARM_OP_call0
    cmp w9, #3
    mov x10, #3
    mov x11, #1
    csel x10, x11, x10, ls
    add x1, x20, x10
    b .Lcall_prepare
.Lcall_leaf_original:
"""


def bind_vm(body):
    return replace_one(
        body,
        '#include "interpreter-aarch64-leaf-bridge.inc"',
        BRIDGE,
        "complete native call leaf bridge",
    )


def generate(source, output, core, actual, enabled):
    path = source / "src/arm64/linux/abi/call-leaves.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review original call leaf owner: " + n)
    (output / "interpreter-aarch64-leaf-bridge.inc").write_text(
        BRIDGE if enabled else "/* OFF */\n"
    )
    header = output / "quickjs-aarch64-call-leaves-private.h"
    worker = output / "quickjs-aarch64-call-leaves.c"
    supp = output / "interpreter-aarch64-leaf-supplements.h"
    if enabled:
        prefix = actual_type_prefix(actual.core.read_text())
        stack = (
            function(actual.core.read_text(), "static inline uintptr_t js_get_stack_pointer(void)")
            + "\n"
            + function(
                actual.core.read_text(),
                "static inline bool js_check_stack_overflow(JSRuntime *rt, size_t alloca_size)",
            )
        )
        header.write_text(
            "/* Actual target core type prefix;no mirrored private structs. */\n"
            + prefix
            + "\n"
            + stack
            + '\n#include "interpreter-private-abi.h"\n'
        )
        worker.write_text(
            '#include "quickjs-aarch64-call-leaves-private.h"\n#include "src/arm64/linux/interpreter-call-leaves.inc"\n'
        )
        text = (source / "src/arm64/linux/interpreter-shared-supplements.inc").read_text()
        decl = "extern JSValue JS_FrameAArch64CallLeaf(JSContext *,JSValueConst,JSValueConst,int,const JSValue *,unsigned);\n"
        marker = (
            "    return JS_FrameCallEntryShared(ctx,function,receiver,new_target,argc,argv,flags);"
        )
        text = decl + replace_one(
            text,
            marker,
            """    if(!(flags&~JS_CALL_FLAG_COPY_ARGV)) {
        JSValue value=JS_FrameAArch64CallLeaf(ctx,function,receiver,argc,argv,0);
        if(!JS_IsException(value))return value;
    }
"""
            + marker,
            "root leaf rejection retains complete original shared call",
        )
        supp.write_text(text)
        p = output / "interpreter-aarch64-shared.h"
        shared = p.read_text()
        shared = replace_one(
            shared,
            "#include QJS_FRAME_SHARED_SUPPLEMENTS_HEADER",
            '#include "interpreter-aarch64-leaf-supplements.h"',
            "actual shared root leaf boundary",
        )
        p.write_text(shared)
    else:
        for p in (header, worker, supp):
            p.write_text("/* Call leaves compiled OFF. */\n")
    record = dict(
        enabled=enabled,
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/call_leaves.py"),
        worker_source_sha256=sha(source / "src/arm64/linux/interpreter-call-leaves.inc"),
        generated_sha256=sha(worker),
        private_sha256=sha(header),
        supplements_sha256=sha(supp),
        bridge_sha256=sha(output / "interpreter-aarch64-leaf-bridge.inc"),
        frame_growth=0,
        state_growth=0,
        runtime_growth=0,
        release_TLS_bytes=0,
        instrument_TLS_bytes=96 if enabled else 0,
        whole_qualification=False,
    )
    (output / "CALL-LEAVES.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
