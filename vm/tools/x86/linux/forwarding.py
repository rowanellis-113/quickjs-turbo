"""Complete shared .call normalization, logical frames and native ownership.

Private returning probes receive32 separate scratch bytes. They never borrow
the live SysV VM's canonical TLS anchor or copy a Win64 unwind/clone contract.
"""

import ast
import hashlib
import json
import re
from c_workers import module, replace_one


def _owner_path(source, name):
    modules = json.loads((source / "tools/common/modules.json").read_text())
    return source / "tools" / modules[name]


def literal(source, name, variable):
    path = _owner_path(source, name)
    tree = ast.parse(path.read_text())
    values = [
        n.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets)
    ]
    if len(values) != 1:
        raise ValueError("Review shared forward owner " + variable)
    value = ast.literal_eval(values[0])
    if not isinstance(value, str):
        raise ValueError("Expected shared C source")
    return value


def release(text):
    old = "    rt->current_stack_frame = frame->sf.prev_frame;"
    new = (
        """    /* Keep logical wrappers visible through every observable close/free. */
    size_t forward_bytes=js_frame_forward_take(frame);
    used_bytes-=forward_bytes;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_release_stack(rt,forward_bytes);
#endif
"""
        + old
    )
    return replace_one(text, old, new, "logical wrapper release after child cleanup")


def policy(source, output, loop):
    from admission import function

    prepare = module(source, "call-prepare")
    entry = literal(source, "call-forward", "ENTER")
    marker = "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)"
    body = function(entry, marker) + "\n"
    kernel = prepare.prepared_commit_body(body)
    kernel = replace_one(
        kernel,
        "    JSValue leaf_value;\n",
        "",
        "prepared kernel removes its unreachable leaf temporary",
    )
    data = literal(source, "call-prepare", "DATA_TYPE")
    header = (
        """/* Shared source algorithms; actual Linux private types and ABI. */
#include "src/x86/linux/interpreter-forward.inc"
"""
        + data
        + """
__attribute__((visibility("hidden"),section(".data.qjs_linux_forward")))
JSFramePrepareData JS_FrameCallPrepareData={.control=255};
"""
        + entry
        + "\n"
        + kernel
        + """
static FRAME_INLINE void js_linux_forward_controls_init(void)
{
    __atomic_store_n(&JS_FrameCallForwardBorrowMissingControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardBorrowControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardOwnedControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED")?2:1,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallPrepareData.owned_control,
        getenv("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED")?2:1,__ATOMIC_RELAXED);
    unsigned char mode=getenv("QJS_DISABLE_FRAME_CALL_PREPARE")?2:1;
    if(getenv("QJS_OBSERVE_FRAME_CALL_PREPARE"))mode|=4;
    __atomic_store_n(&JS_FrameCallPrepareData.control,mode,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallForwardNativeControl,
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE")?2:1,__ATOMIC_RELAXED);
}

FRAME_CODE int JS_FrameCallForwardNativeCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
FRAME_CODE int JS_FrameCallForwardOwnedCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
FRAME_CODE int JS_FrameCallPrepareCold(JSFrameRegisterState *state)
{
    js_linux_forward_controls_init();
    return JS_FrameVarargsForwardTry(state);
}
"""
    )
    (output / "quickjs-linux-forward.h").write_text(header)
    loop = replace_one(
        loop,
        '#include "src/common/call/interpreter-context-types.inc"',
        '#include "src/common/call/interpreter-retained-context.inc"',
        "shared logical parent context",
    )
    loop = replace_one(
        loop,
        "/* This is one C activation for the complete supported JS call chain.",
        '#include "quickjs-linux-forward.h"\n\n/* This is one C activation for the complete supported JS call chain.',
        "shared forward algorithms after actual register/state helpers",
    )
    loop = release(loop)
    owners = [
        "call-forward",
        "call-forward-native",
        "call-forward-owned",
        "call-forward-borrow",
        "call-forward-borrow-missing",
        "call-prepare",
        "call-prepare-owned",
    ]
    record = dict(
        status="generated-not-qualified",
        source_files={
            p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [_owner_path(source, n) for n in owners]
        },
        generated_sha256=hashlib.sha256(header.encode()).hexdigest(),
        logical_frame_bytes=80,
        maximum_depth=64,
        private_scratch_bytes=32,
        entries=[
            "JS_FrameVarargsForwardTry",
            "JS_FrameCallPrepareCommit",
            "JS_FrameCallForwardNativeCold",
            "JS_FrameCallForwardOwnedCold",
            "JS_FrameCallPrepareCold",
        ],
        scope="Shared C normalizer/prepared constructor and native leaf/owned/borrow/missing/deep producers;not whole native entry/root/publication coverage",
    )
    (output / "FORWARDING.json").write_text(json.dumps(record, indent=2) + "\n")
    return loop


def append(source, stream, layout):
    fields = layout["offsets"]
    native = module(source, "call-forward-native")
    owned = module(source, "call-forward-owned")
    prepare = module(source, "call-prepare")
    probe = owned.route_probe(native.lines(source, False, layout_override=layout))
    probe = prepare.route_probe(probe)
    leaf = [
        ("JS_FrameCallForwardNativeProbe", probe),
        ("JS_FrameCallForwardOwnedTry", owned.lines(source, False, layout_override=layout)),
        (
            "JS_FrameCallForwardBorrowTry",
            module(source, "call-forward-borrow").lines(source, False, layout_override=layout),
        ),
        (
            "JS_FrameCallForwardBorrowMissingTry",
            module(source, "call-forward-borrow-missing").lines(
                source, False, layout_override=layout
            ),
        ),
    ]
    leaf += prepare.blocks(source, False, layout_override=layout)
    all_names = {name for name, _ in leaf}
    for _, rows in leaf:
        all_names.update(row[:-1] for row in rows if row.endswith(":"))
        for row in rows:
            if row.startswith(("call ", "push ", "pop ", "sub rsp", "add rsp", "mov rsp")):
                raise ValueError(
                    "Returning forward probe changed native stack/nonvolatile contract: " + row
                )
            for match in re.finditer(r"\[rsp\+(\d+)\]", row):
                width = re.search(r"\b(XMMWORD|QWORD|DWORD|WORD|BYTE) PTR $", row[: match.start()])
                if not width:
                    raise ValueError("Unknown returning probe scratch width: " + row)
                size = dict(XMMWORD=16, QWORD=8, DWORD=4, WORD=2, BYTE=1)[width[1]]
                if not 8 <= int(match[1]) < int(match[1]) + size <= 40:
                    raise ValueError(
                        "Returning forward probe escapes separate32-byte scratch: " + row
                    )
    # Native descriptor guards use the address of the actual original function,
    # supplied by a compiler-checked ELF alias, never a private clone guess.
    for _, rows in leaf:
        for i, row in enumerate(rows):
            rows[i] = row.replace(
                "qjs_frame_core_js_function_call", "qjs_linux_core_js_function_call"
            )
    code = stream["code"]
    at = code.index("interp_host_call:") + 1
    # Existing argc/method/PC-size scratch is already live at this boundary.
    # The original host setup has not advanced PC or installed pending yet.
    guard = [
        "cmp QWORD PTR [r8-8], -1",
        "jne linux_forward_original_host",
        "mov rax, QWORD PTR [r8-16]",
        f"cmp WORD PTR [rax+{fields['JSObject.class_id']}], 12",
        "jne linux_forward_original_host",
        "lea r10, [rip+qjs_linux_core_js_function_call]",
        f"cmp QWORD PTR [rax+{fields['JSObject.u.cfunc.c_function']}], r10",
        "jne linux_forward_original_host",
        f"cmp BYTE PTR [rax+{fields['JSObject.u.cfunc.cproto']}], 0",
        "jne linux_forward_original_host",
        f"cmp WORD PTR [rax+{fields['JSObject.u.cfunc.magic']}], 0",
        "jne linux_forward_original_host",
        f"cmp BYTE PTR [rax+{fields['JSObject.u.cfunc.length']}], 1",
        "jne linux_forward_original_host",
        "mov rax, QWORD PTR [rbp+80]",
        f"cmp BYTE PTR [rax+{fields['JSFunctionBytecode.pc2line_len'] + 7}], 2",
        "je linux_forward_original_host",
        "jmp JS_FrameLinuxForwardEnter",
        "linux_forward_original_host:",
    ]
    code[at:at] = guard
    enter = [
        "mov DWORD PTR [rsp+40], ecx",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov r10, QWORD PTR [rbx+56]",
        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], rbp",
        "mov rcx, rbx",
        "sub rsp, 32",
        ".cfi_adjust_cfa_offset 32",
        "call JS_FrameCallForwardNativeProbe",
        "add rsp, 32",
        ".cfi_adjust_cfa_offset -32",
        "test eax, eax",
        "jz linux_forward_fallback",
        "mov QWORD PTR [rbx+96], 0",
        "cmp eax, 2",
        "je linux_forward_leaf_return",
        "mov r10, QWORD PTR [rbx]",
        "mov QWORD PTR [r10+64], 0",
        "jmp interp_reload",
        "linux_forward_leaf_return:",
        "mov QWORD PTR [rbp+64], 0",
        "movdqu xmm0, XMMWORD PTR [rbx+40]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "mov r11, r13",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
        "jmp interp_release_values",
        "linux_forward_fallback:",
        "mov ecx, DWORD PTR [rsp+40]",
        "mov r8, rcx",
        "shl r8, 4",
        "neg r8",
        "add r8, r13",
        "jmp linux_forward_original_host",
    ]
    hits = [i for i, row in enumerate(code) if row == "jne interp_root_return"]
    if len(hits) != 1:
        raise ValueError("Review physical child/root return routing")
    code[hits[0]] = "jne JS_FrameLinuxForwardReturn"
    ret = [
        "cmp BYTE PTR [rbp+62], 2",
        "jne interp_root_return",
        "mov r10, QWORD PTR [rbp]",
        "linux_forward_pop_logical:",
        "sub QWORD PTR [rbx+32], 80",
        "mov r10, QWORD PTR [r10]",
        "cmp QWORD PTR [r10+32], 0",
        "jne linux_forward_parent_ready",
        "cmp BYTE PTR [r10+63], 199",
        "je linux_forward_pop_logical",
        "linux_forward_parent_ready:",
        "mov rax, QWORD PTR [rbx+56]",
        f"mov QWORD PTR [rax+{fields['JSRuntime.current_stack_frame']}], r10",
        "mov QWORD PTR [r10+64], 0",
        "mov rbp, r10",
        "mov rax, QWORD PTR [rbp+80]",
        f"mov rsi, QWORD PTR [rax+{fields['JSFunctionBytecode.realm']}]",
        "mov r14, QWORD PTR [rbp+32]",
        "mov r15, QWORD PTR [rbp+24]",
        "mov r12, QWORD PTR [rbp+48]",
        "mov r11, QWORD PTR [rbp+104]",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
        "jmp interp_release_values",
    ]
    globals = [
        "qjs_linux_core_js_function_call",
        "JS_FrameCallForwardNativeControl",
        "JS_FrameCallForwardOwnedControl",
        "JS_FrameCallForwardBorrowControl",
        "JS_FrameCallForwardBorrowMissingControl",
        "JS_FrameCallPrepareData",
    ]
    contract = dict(
        logical_frame_bytes=80,
        maximum_depth=64,
        returning_probe_scratch=32,
        private_call="RCX state;audited volatile registers;separate private scratch;normal RET/CFI",
        producers=[
            "native leaf",
            "owned one",
            "borrowed one",
            "missing borrowed one",
            "deep prepared leaf/owned",
        ],
        shared_factories=True,
        measured_SysV_layout=True,
        root_and_exception_cleanup="Shared logical parent/take helpers and original release order",
    )
    return (
        [("JS_FrameLinuxForwardEnter", enter), ("JS_FrameLinuxForwardReturn", ret)],
        leaf,
        globals,
        contract,
    )
