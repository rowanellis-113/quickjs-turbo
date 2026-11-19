"""Isolated suspended-frame entry and callback-free Win64 opcode segments.

The complete slow loop is copied from this build's declared core overlays.
Its opcode bodies, exception walker and suspended-slot cleanup are unchanged.
The pinned upstream input never changes. MIT, as in quickjs.c.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import source_file
import re

SIGNATURE = "static JSValue JS_CallInternal(JSContext *caller_ctx, JSValueConst func_obj,\n"
RAW_SHA = "66c75eb2039185806eaf19c37073b6314ff9ea0cf363a57764ac337c6aeccaeb"
ASM = "asm/x86/win64/common/cvm-segments.S"


def opnames(root):
    text = source_file(root, "quickjs-opcode.h").read_text(encoding="utf-8")
    result = re.findall(r"^DEF\(\s*(\w+)\s*,", text, re.M)
    assert len(result) == 252
    return result


def kernels():
    # Win64 volatile leaf: R8=PC, R9=SP, R10=boundary, R11=dispatch.
    # RAX/RCX/RDX and XMM0/1 are scratch. Immutable slot bases stay in the
    # activation boundary; no nonvolatile register or native stack is touched.
    result = {}
    dispatch = "movzx eax, BYTE PTR [r8]\njmp QWORD PTR [r11+rax*8]"
    exit = ".Lcvm_exit"

    def emit(name, lines, size=1):
        assert name not in result
        result[name] = [*lines, f"add r8, {size}", dispatch]

    def duplicate(label, source, destination="r9", finish=True):
        return [
            f"mov rax, QWORD PTR [{source}]",
            f"mov rdx, QWORD PTR [{source}+8]",
            "cmp edx, -9",
            f"jb .Lcvm_{label}_dup",
            "add DWORD PTR [rax], 1",
            f".Lcvm_{label}_dup:",
            f"mov QWORD PTR [{destination}], rax",
            f"mov QWORD PTR [{destination}+8], rdx",
            *(["add r9, 16"] if finish else []),
        ]

    for name, tag, payload in [
        ("undefined", 3, 0),
        ("null", 2, 0),
        ("push_false", 1, 0),
        ("push_true", 1, 1),
    ]:
        emit(name, [f"mov QWORD PTR [r9], {payload}", f"mov QWORD PTR [r9+8], {tag}", "add r9, 16"])
    for value in range(-1, 8):
        name = "push_minus1" if value == -1 else "push_" + str(value)
        emit(name, [f"mov QWORD PTR [r9], {value}", "mov QWORD PTR [r9+8], 0", "add r9, 16"])
    for name, load, size in [
        ("push_i8", "movsx rax, BYTE PTR [r8+1]", 2),
        ("push_i16", "movsx rax, WORD PTR [r8+1]", 3),
        ("push_i32", "movsxd rax, DWORD PTR [r8+1]", 5),
    ]:
        emit(name, [load, "mov QWORD PTR [r9], rax", "mov QWORD PTR [r9+8], 0", "add r9, 16"], size)
    # RCX always identifies an already-decoded live slot. No callback may run.
    for base, offset in [("loc", 16), ("arg", 24), ("var_ref", 32)]:
        specs = [(base, ["movzx eax, WORD PTR [r8+1]"], 3)]
        if base == "loc":
            specs += [("loc8", ["movzx eax, BYTE PTR [r8+1]"], 2)]
        specs += [(base + str(i), [f"mov eax, {i}"], 1) for i in range(4)]
        if base in ("loc", "var_ref"):
            specs += [(base + "_check", ["movzx eax, WORD PTR [r8+1]"], 3)]
        for suffix, index, size in specs:
            address = [*index, "shl rax, 4", f"mov rcx, QWORD PTR [r10+{offset}]", "add rcx, rax"]
            if base == "var_ref":
                address = [
                    *index,
                    "mov rcx, QWORD PTR [r10+32]",
                    "mov rcx, QWORD PTR [rcx+rax*8]",
                    "mov rcx, QWORD PTR [rcx+32]",
                ]
            name = "get_" + suffix
            checked = suffix.endswith("_check")
            check = ["cmp DWORD PTR [rcx+8], 4", "je " + exit] if checked else []
            emit(name, [*address, *check, *duplicate(name, "rcx")], size)
        writes = [(base, ["movzx eax, WORD PTR [r8+1]"], 3)]
        if base == "loc":
            writes += [("loc8", ["movzx eax, BYTE PTR [r8+1]"], 2)]
        writes += [(base + str(i), [f"mov eax, {i}"], 1) for i in range(4)]
        if base in ("loc", "var_ref"):
            writes += [
                (base + "_check", ["movzx eax, WORD PTR [r8+1]"], 3),
                (base + "_check_init", ["movzx eax, WORD PTR [r8+1]"], 3),
            ]
        for suffix, index, size in writes:
            for operation in ("put", "set"):
                # No checked set opcode exists in this upstream pin.
                if operation == "set" and "_check" in suffix:
                    continue
                name = operation + "_" + suffix
                address = [
                    *index,
                    "shl rax, 4",
                    f"mov rcx, QWORD PTR [r10+{offset}]",
                    "add rcx, rax",
                ]
                if base == "var_ref":
                    address = [
                        *index,
                        "mov rcx, QWORD PTR [r10+32]",
                        "mov rcx, QWORD PTR [rcx+rax*8]",
                        "mov rcx, QWORD PTR [rcx+32]",
                    ]
                check = []
                if suffix.endswith("_check"):
                    check = ["cmp DWORD PTR [rcx+8], 4", "je " + exit]
                elif suffix.endswith("_check_init"):
                    check = ["cmp DWORD PTR [rcx+8], 4", "jne " + exit]
                old = [
                    "mov rax, QWORD PTR [rcx]",
                    "mov rdx, QWORD PTR [rcx+8]",
                    "cmp edx, -9",
                    f"jb .Lcvm_{name}_safe",
                    "cmp DWORD PTR [rax], 1",
                    "jle " + exit,
                    f".Lcvm_{name}_safe:",
                ]
                new = ["movdqu xmm0, XMMWORD PTR [r9-16]"]
                if operation == "set":
                    new += [
                        "movq xmm1, rax",
                        "mov rax, QWORD PTR [r9-16]",
                        "cmp DWORD PTR [r9-8], -9",
                        f"jb .Lcvm_{name}_owned",
                        "add DWORD PTR [rax], 1",
                        f".Lcvm_{name}_owned:",
                        "movq rax, xmm1",
                    ]
                new += [
                    "movdqu XMMWORD PTR [rcx], xmm0",
                    "cmp edx, -9",
                    f"jb .Lcvm_{name}_stored",
                    "sub DWORD PTR [rax], 1",
                    f".Lcvm_{name}_stored:",
                ]
                if operation == "put":
                    new += ["sub r9, 16"]
                emit(name, [*address, *check, *old, *new], size)
    emit(
        "get_loc0_loc1",
        [
            "mov rcx, QWORD PTR [r10+16]",
            *duplicate("get_loc0_loc1_a", "rcx"),
            *duplicate("get_loc0_loc1_b", "rcx+16"),
        ],
    )
    emit("dup", duplicate("dup", "r9-16"))
    # a b -> a a b. The old top is transferred, not duplicated or released.
    emit(
        "dup1",
        [
            "movdqu xmm1, XMMWORD PTR [r9-16]",
            *duplicate("dup1", "r9-32", "r9-16", False),
            "movdqu XMMWORD PTR [r9], xmm1",
            "add r9, 16",
        ],
    )
    for name in ("drop", "nip"):
        offset = 16 if name == "drop" else 32
        body = [
            f"mov rax, QWORD PTR [r9-{offset}]",
            f"cmp DWORD PTR [r9-{offset - 8}], -9",
            f"jb .Lcvm_{name}_safe",
            "cmp DWORD PTR [rax], 1",
            "jle " + exit,
            "sub DWORD PTR [rax], 1",
            f".Lcvm_{name}_safe:",
        ]
        if name == "nip":
            body += ["movdqu xmm0, XMMWORD PTR [r9-16]", "movdqu XMMWORD PTR [r9-32], xmm0"]
        emit(name, [*body, "sub r9, 16"])
    emit(
        "swap",
        [
            "movdqu xmm0, XMMWORD PTR [r9-32]",
            "movdqu xmm1, XMMWORD PTR [r9-16]",
            "movdqu XMMWORD PTR [r9-16], xmm0",
            "movdqu XMMWORD PTR [r9-32], xmm1",
        ],
    )
    both_int = ["cmp DWORD PTR [r9-24], 0", "jne " + exit, "cmp DWORD PTR [r9-8], 0", "jne " + exit]
    commit_int = [
        "movsxd rax, eax",
        "mov QWORD PTR [r9-32], rax",
        "mov QWORD PTR [r9-24], 0",
        "sub r9, 16",
    ]
    for name, instruction in [("add", "add"), ("sub", "sub"), ("mul", "imul")]:
        body = [
            *both_int,
            "movsxd rax, DWORD PTR [r9-32]",
            "movsxd rdx, DWORD PTR [r9-16]",
            f"{instruction} rax, rdx",
        ]
        if name == "mul":
            body += [
                "test rax, rax",
                "jnz .Lcvm_mul_nonzero",
                "mov ecx, DWORD PTR [r9-32]",
                "or ecx, DWORD PTR [r9-16]",
                "js " + exit,
                ".Lcvm_mul_nonzero:",
            ]
        body += ["movsxd rcx, eax", "cmp rcx, rax", "jne " + exit, *commit_int]
        emit(name, body)
    emit(
        "mod",
        [
            *both_int,
            "mov eax, DWORD PTR [r9-32]",
            "test eax, eax",
            "js " + exit,
            "mov ecx, DWORD PTR [r9-16]",
            "test ecx, ecx",
            "jle " + exit,
            "xor edx, edx",
            "div ecx",
            "mov eax, edx",
            *commit_int,
        ],
    )
    for name, instruction in [
        ("and", "and"),
        ("or", "or"),
        ("xor", "xor"),
        ("shl", "shl"),
        ("sar", "sar"),
        ("shr", "shr"),
    ]:
        body = [*both_int, "mov eax, DWORD PTR [r9-32]", "mov ecx, DWORD PTR [r9-16]"]
        body += [f"{instruction} eax, " + ("cl" if name in ("shl", "sar", "shr") else "ecx")]
        if name == "shr":
            body += ["test eax, eax", "js " + exit]
        emit(name, [*body, *commit_int])
    for name, condition in [
        ("lt", "l"),
        ("lte", "le"),
        ("gt", "g"),
        ("gte", "ge"),
        ("eq", "e"),
        ("neq", "ne"),
        ("strict_eq", "e"),
        ("strict_neq", "ne"),
    ]:
        emit(
            name,
            [
                *both_int,
                "mov edx, DWORD PTR [r9-32]",
                "xor eax, eax",
                "cmp edx, DWORD PTR [r9-16]",
                f"set{condition} al",
                "mov QWORD PTR [r9-32], rax",
                "mov QWORD PTR [r9-24], 1",
                "sub r9, 16",
            ],
        )
    for name, amount in [("inc", 1), ("dec", -1)]:
        emit(
            name,
            [
                "cmp DWORD PTR [r9-8], 0",
                "jne " + exit,
                "mov eax, DWORD PTR [r9-16]",
                f"add eax, {amount}",
                "jo " + exit,
                "movsxd rax, eax",
                "mov QWORD PTR [r9-16], rax",
            ],
        )
    for name, amount in [("inc_loc", 1), ("dec_loc", -1)]:
        emit(
            name,
            [
                "movzx ecx, BYTE PTR [r8+1]",
                "shl rcx, 4",
                "mov rax, QWORD PTR [r10+16]",
                "add rcx, rax",
                "cmp DWORD PTR [rcx+8], 0",
                "jne " + exit,
                "mov eax, DWORD PTR [rcx]",
                f"add eax, {amount}",
                "jo " + exit,
                "movsxd rax, eax",
                "mov QWORD PTR [rcx], rax",
            ],
            2,
        )
    emit(
        "add_loc",
        [
            "movzx ecx, BYTE PTR [r8+1]",
            "shl rcx, 4",
            "mov rax, QWORD PTR [r10+16]",
            "add rcx, rax",
            "cmp DWORD PTR [rcx+8], 0",
            "jne " + exit,
            "cmp DWORD PTR [r9-8], 0",
            "jne " + exit,
            "movsxd rax, DWORD PTR [rcx]",
            "movsxd rdx, DWORD PTR [r9-16]",
            "add rax, rdx",
            "movsxd rdx, eax",
            "cmp rdx, rax",
            "jne " + exit,
            "mov QWORD PTR [rcx], rax",
            "sub r9, 16",
        ],
        2,
    )
    emit(
        "lnot",
        [
            "cmp DWORD PTR [r9-8], 3",
            "ja " + exit,
            "xor eax, eax",
            "cmp DWORD PTR [r9-16], 0",
            "sete al",
            "mov QWORD PTR [r9-16], rax",
            "mov QWORD PTR [r9-8], 1",
        ],
    )
    for name, width, condition in [
        ("if_false8", 1, "z"),
        ("if_true8", 1, "nz"),
        ("if_false", 4, "z"),
        ("if_true", 4, "nz"),
    ]:
        load = "movsx rax, BYTE PTR [r8+1]" if width == 1 else "movsxd rax, DWORD PTR [r8+1]"
        # Every original branch polls, including forward/not-taken branches.
        body = [
            "cmp DWORD PTR [r9-8], 3",
            "ja " + exit,
            "mov rcx, QWORD PTR [r10+40]",
            "cmp DWORD PTR [rcx+568], 1",
            "jle " + exit,
            "sub DWORD PTR [rcx+568], 1",
            "mov eax, DWORD PTR [r9-16]",
            "sub r9, 16",
            "test eax, eax",
            f"j{condition} .Lcvm_{name}_taken",
            f"add r8, {1 + width}",
            dispatch,
            f".Lcvm_{name}_taken:",
            load,
            "lea r8, [r8+rax+1]",
            dispatch,
        ]
        result[name] = body
    for name, width in [("goto8", 1), ("goto16", 2), ("goto", 4)]:
        load = (
            f"movsx rax, {'BYTE' if width == 1 else 'WORD'} PTR [r8+1]"
            if width < 4
            else "movsxd rax, DWORD PTR [r8+1]"
        )
        result[name] = [
            "mov rcx, QWORD PTR [r10+40]",
            "cmp DWORD PTR [rcx+568], 1",
            "jle " + exit,
            "sub DWORD PTR [rcx+568], 1",
            load,
            "lea r8, [r8+rax+1]",
            dispatch,
        ]
    emit("nop", [])
    return result


def assembly(root):
    names = opnames(root)
    abi = json.loads((root / "src/x86/win64/abi/quickjs-0151.json").read_text())
    assert abi["offsets"]["JSContext.interrupt_counter"] == 568
    assert abi["offsets"]["JSVarRef.pvalue"] == 32
    blocks = kernels()
    assert set(blocks) <= set(names), sorted(set(blocks) - set(names))
    lines = [
        "/* Generated by tools/x86/win64/codegen/cvm_segments.py. MIT. */",
        ".intel_syntax noprefix",
        '.section .qjscvm$segments,"xr"',
        ".p2align 4",
        ".globl JS_CVMRunSegment, JS_CVMRunSegment_end",
        ".def JS_CVMRunSegment; .scl 2; .type 32; .endef",
        ".seh_proc JS_CVMRunSegment",
        "JS_CVMRunSegment:",
    ]
    lines += [
        ".seh_endprologue",
        "mov r10, rcx",
        "mov r8, QWORD PTR [r10]",
        "mov r9, QWORD PTR [r10+8]",
        "lea r11, [rip+.Lcvm_table]",
        ".Lcvm_dispatch:",
        "movzx eax, BYTE PTR [r8]",
        "jmp QWORD PTR [r11+rax*8]",
    ]
    for name, body in blocks.items():
        lines += [".Lcvm_" + name + ":", *body]
    lines += [
        ".Lcvm_exit:",
        "mov QWORD PTR [r10], r8",
        "mov QWORD PTR [r10+8], r9",
        "ret",
        "JS_CVMRunSegment_end:",
        ".seh_endproc",
        '.section .rdata$cvm_segments,"dr"',
        ".p2align 3",
        ".Lcvm_table:",
    ]
    # The declared ordinary readonly table stays in .rdata through integration,
    # with one validated PE DIR64 fixup per entry. It is not an extension island.
    lines += [".quad .Lcvm_" + (name if name in blocks else "exit") for name in names]
    lines += [".quad .Lcvm_exit"] * (256 - len(names))
    return "\n".join(lines) + "\n"


def core_overlay(text, raw, root, build):
    start = raw.index(SIGNATURE)
    end = raw.index("\n}\n", start) + 3
    assert hashlib.sha256(raw[start:end].encode()).hexdigest() == RAW_SHA
    line_count = text.count("\n")
    start = text.index(SIGNATURE)
    end = text.index("\n}\n", start) + 3
    body = text[start:end]
    loops = body[body.index(" restart:\n") :]
    macros = body[
        body.index("#ifdef ENABLE_DUMPS") : body.index("    if (js_poll_interrupts(caller_ctx))")
    ]
    assert macros.count("goto *dispatch_table[opcode = *pc++]") == 1
    marker = "#define SWITCH(pc)      DUMP_BYTECODE_OR_DONT(pc) __extension__ ({ goto *dispatch_table[opcode = *pc++]; });"
    assert macros.count(marker) == 1
    switch = "#define SWITCH(pc)      DUMP_BYTECODE_OR_DONT(pc) switch (opcode = *pc++)"
    assert macros.count(switch) == 1
    macros = macros.replace(
        switch,
        "#define SWITCH(pc) DUMP_BYTECODE_OR_DONT(pc) CVM_SEGMENT_TRY() switch (opcode = *pc++)",
    )
    declaration = """static JSValue JS_CVMResumeInternal(JSContext *caller_ctx, JSValueConst func_obj,
                                    JSValueConst this_obj, JSValueConst new_target,
                                    int argc, JSValueConst *argv, int flags)
{
    JSRuntime *rt = caller_ctx->rt;
    JSAsyncFunctionState *s;
    JSContext *ctx;
    JSObject *p;
    JSFunctionBytecode *b;
    JSStackFrame *sf;
    uint8_t *pc;
    int opcode, i;
    JSValue *local_buf, *stack_buf, *var_buf, *arg_buf, *sp, ret_val, *pval;
    JSVarRef **var_refs;
#ifdef QJS_CVM_NATIVE_OPS
    bool use_native;
    JSCVMSegmentState native_state;
#endif
"""
    entry = """    /* Preserve caller-realm poll before reading/publishing the persistent SF. */
    if (js_poll_interrupts(caller_ctx))
        return JS_EXCEPTION;
    s = JS_VALUE_GET_PTR(func_obj);
    sf = &s->frame;
    p = JS_VALUE_GET_OBJ(sf->cur_func);
    b = p->u.func.function_bytecode;
    ctx = b->realm;
    var_refs = p->u.func.var_refs;
    local_buf = arg_buf = sf->arg_buf;
    var_buf = sf->var_buf;
    stack_buf = var_buf + b->var_count;
    sp = sf->cur_sp;
    sf->cur_sp = NULL;
    pc = sf->cur_pc;
    sf->prev_frame = rt->current_stack_frame;
    rt->current_stack_frame = sf;
#ifdef QJS_CVM_NATIVE_OPS
    use_native = js_cvm_segment_mode() == 1;
    if (use_native) {
        native_state.locals = var_buf;
        native_state.args = arg_buf;
        native_state.refs = var_refs;
        native_state.ctx = ctx;
    }
#endif
    if (s->throw_flag)
        goto exception;
    goto restart;
"""
    prefix = [
        "/* Generated from this build's fully declared JS_CallInternal loop. MIT. */",
        "#ifdef QJS_CVM_NATIVE_SEGMENTS",
        '#include "src/common/call/cvm-native-segments.inc"',
        "#undef SWITCH",
        "#undef CASE",
        "#undef DEFAULT",
        "#undef BREAK",
        "#undef DUMP_BYTECODE_OR_DONT",
    ]
    suffix = "\n#undef SWITCH\n#undef CASE\n#undef DEFAULT\n#undef BREAK\n#undef DUMP_BYTECODE_OR_DONT\n#else\n#define JS_CVMResumeEntry JS_CallInternal\n#endif\n"
    content = "\n".join(prefix) + "\n" + declaration + macros + entry + loops + suffix
    target = build.resolve() / "generated/backports/quickjs-coroutine-resume.inc"
    target.parent.mkdir(parents=True, exist_ok=True)
    generated = content.encode("utf-8")
    if not target.exists() or target.read_bytes() != generated:
        target.write_bytes(generated)
    receipt = dict(
        raw_function_sha256=RAW_SHA,
        patched_parent_function_sha256=hashlib.sha256(body.encode()).hexdigest(),
        inherited_loop_sha256=hashlib.sha256(loops.encode()).hexdigest(),
        opcode_bodies_unchanged=True,
        generated=str(target),
        generated_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        native_opcode_count=len(kernels()),
        native_opcodes=sorted(kernels()),
    )
    target.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    # This is a derived input, never part of the original compiler TU. The
    # separately compiled owner retargets one verified async_func_resume call
    # relocation after the normal core adapter. Ordinary core code generation
    # therefore sees the exact accepted compiler input.
    assert text.count("\n") == line_count
    return text


def _module(name):
    import importlib.util
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from x86.common.paths_x86 import activate_tools, tool_path

    activate_tools()
    spec = importlib.util.spec_from_file_location(
        "cvm_" + name.replace("-", "_"), tool_path(name + ".py")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def compile_isolated(source, build, msvc):
    if not msvc:
        return
    import struct

    adapter = _module("object-adapter")
    parent = _module("iterator")
    compiler = _module("atod")
    core_path = build / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
    original = core_path.read_bytes()
    core = adapter.Coff(original)
    raw = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    generated = build / "generated/backports/quickjs-coroutine-resume.inc"
    body = generated.read_text(encoding="utf-8")
    boundary = (source / "src/common/call/cvm-native-segments.inc").read_text(encoding="utf-8")
    special_start = raw.index("typedef enum {\n    OP_SPECIAL_OBJECT_ARGUMENTS,")
    special_end = raw.index("} OPSpecialObjectEnum;", special_start) + len("} OPSpecialObjectEnum;")
    special_enum = raw[special_start:special_end] + "\n"
    commands = json.loads((build / "compile_commands.json").read_text())
    frame_command = next(
        r["command"] for r in commands if Path(r["file"]).name == "quickjs-interpreter.c"
    )
    release = bool(re.search(r"(?:^|\s)(?:/|-D)D?NDEBUG(?:\s|$)", frame_command))
    # ENABLE_DUMPS only exists without NDEBUG in this pinned source. Debug
    # builds keep the complete original interpreter including live dump flags.
    if not release:
        body = """JSValue JS_CVMResumeEntry(JSContext *ctx, JSValueConst func, JSValueConst this_val,
    JSValueConst target, int argc, JSValueConst *argv, int flags)
{
    return JS_CallInternal(ctx, func, this_val, target, argc, argv, flags);
}
"""
    # Match the inherited adapter's native internal selector for nested calls.
    preface = """
#undef JS_CallInternal
#define JS_CallInternal JS_FrameDispatchInternal
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst,
                                       JSValueConst, int, JSValueConst *, int);
#define CORE_SPREAD_ARGV_CAP 16u
#define js_core_spread_call qjs_frame_core_js_core_spread_call
extern int qjs_frame_core_js_core_spread_call(JSContext *, JSFunctionBytecode *,
                                             JSStackFrame *, const uint8_t *, JSValue *);
#define js_global_binding_cell_get JS_FrameGlobalBindingCellGet
extern JSValue JS_FrameGlobalBindingCellGet(JSContext *, JSFunctionBytecode *,
                                          const uint8_t *, JSAtom, bool);
"""
    discovery = preface + body.replace(
        '#include "src/common/call/cvm-native-segments.inc"', boundary
    )
    core.symbols["JS_Call"] = dict(storage=2)
    header, exports, copies = adapter.generate(
        raw,
        core,
        discovery,
        owned_functions=("JS_CallInternal", "JS_CVMResumeInternal", "JS_CVMResumeEntry"),
        disabled_macros=("ENABLE_DUMPS",),
    )
    names = {s["name"] for s in core.all_symbols.values()}
    added = []
    for name in sorted(set(exports) | {"js_core_spread_call"}):
        if "qjs_frame_core_" + name not in names:
            core.expose(name)
            added.append(name)
    # Retarget one unspecialized direct CALL/JMP in the verified original owner.
    owner = core.symbols["async_func_resume"]
    rec = core.section_records[owner["section"] - 1]
    following = [
        s["value"]
        for s in core.all_symbols.values()
        if s["section"] == owner["section"] and s["type"] & 32 and s["value"] > owner["value"]
    ]
    end = min(following, default=rec["size"])
    target = core.external("JS_CVMResumeEntry")
    routes = []
    for i in range(rec["count"]):
        at = rec["reloc"] + 10 * i
        offset, index, kind = struct.unpack_from("<IIH", core.data, at)
        if (
            owner["value"] <= offset < end
            and core.all_symbols[index]["name"] == "JS_FrameDispatchInternal"
        ):
            assert kind == 4 and core.data[rec["raw"] + offset - 1] in (0xE8, 0xE9)
            struct.pack_into("<I", core.data, at + 4, target)
            routes.append(
                dict(
                    section=owner["section"],
                    offset=offset,
                    old_index=index,
                    new_index=target,
                    kind=kind,
                    caller="async_func_resume",
                )
            )
    assert len(routes) == 1, routes
    restored = bytearray(core.data)
    for route in routes:
        found = [
            rec["reloc"] + 10 * i
            for i in range(rec["count"])
            if struct.unpack_from("<I", restored, rec["reloc"] + 10 * i)[0] == route["offset"]
        ]
        assert len(found) == 1
        struct.pack_into("<I", restored, found[0] + 4, route["old_index"])
    assert adapter.Coff(restored).sections == adapter.Coff(original).sections
    backup = core_path.with_name(core_path.name + ".before-coroutine-resume")
    assert not backup.exists()
    backup.write_bytes(original)
    parent.finish_preserving_tail(core, original, core_path)
    core_receipt = dict(
        status="passed",
        before_sha256=hashlib.sha256(original).hexdigest(),
        after_sha256=hashlib.sha256(core_path.read_bytes()).hexdigest(),
        original_sections_and_relocations_held_except_one_callee=True,
        routes=routes,
    )
    core_path.with_name(core_path.name + ".coroutine-resume.json").write_text(
        json.dumps(core_receipt, indent=2) + "\n"
    )
    private = build / "generated/quickjs-coroutine-private.h"
    private.write_text(header, encoding="utf-8", newline="\n")
    output = build / "generated/quickjs-coroutine-resume.obj"

    def generate(_source, path):
        path.write_text(
            "#define QJS_CVM_NATIVE_SEGMENTS\n#define QJS_CVM_NATIVE_OPS\n"
            '#include "quickjs-coroutine-private.h"\n'
            + special_enum
            + preface
            + (body if not release else '#include "backports/quickjs-coroutine-resume.inc"\n'),
            encoding="utf-8",
            newline="\n",
        )

    old_argv = compiler.win_argv
    compiler.win_argv = lambda command: old_argv(command) + ["/we4013"]
    compiler.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-coroutine-resume.c",
        late_name=".qjscor",
    )
    compiled = output.read_bytes()
    result = adapter.Coff(compiled)
    renamed = []
    for index, symbol in result.all_symbols.items():
        if (
            symbol["section"] > 0
            and symbol["storage"] == 2
            and symbol["name"] != "JS_CVMResumeEntry"
        ):
            name = "cvm_private_" + hashlib.sha256(symbol["name"].encode()).hexdigest()[:32]
            at = len(result.strings)
            result.strings += name.encode() + b"\0"
            struct.pack_into("<II", result.data, result.table + index * result.stride, 0, at)
            renamed.append(dict(old=symbol["name"], new=name))
    output.write_bytes(result.finish())
    compiler_record = output.with_suffix(".compile.json")
    record = json.loads(compiler_record.read_text())
    record.update(
        before_private_symbols_sha256=hashlib.sha256(compiled).hexdigest(),
        object_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    )
    compiler_record.write_text(json.dumps(record, indent=2) + "\n")
    receipt = dict(
        status="passed-isolated-resume-and-single-original-caller-relocation",
        original_core=str(backup),
        original_core_sha256=hashlib.sha256(original).hexdigest(),
        core_object_sha256=hashlib.sha256(core_path.read_bytes()).hexdigest(),
        original_sections_and_relocations_held_except_one_callee=True,
        routes=routes,
        release_native=release,
        exported_helpers=exports,
        added_aliases=added,
        copied_helpers=copies,
        private_header_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
        generated_loop_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
        object_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        private_symbols=renamed,
    )
    (build / "generated/quickjs-coroutine-resume-source.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )


def append_isolated(source, build, output, msvc, group, prefix, owner, merge):
    if not msvc:
        return
    merge.append(
        output,
        build / "generated/quickjs-coroutine-resume.obj",
        "JS_CVMResumeEntry",
        "coroutine-resume-c",
        keep_all=True,
        code_input=".qjscor",
        code_output=group,
        pdata_output=prefix + "1",
        metadata_inputs=(".voltbl",),
        writable_metadata_inputs=(".qjcvmm",),
        base_owner=owner,
        baseline_sections=(),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    names = opnames(args.source_root)
    eligibility = "/* Generated by tools/common/backports/cvm_segments_c.py. MIT. */\n"
    eligibility += "static const uint8_t js_cvm_segment_eligible[256] = {\n"
    eligibility += ",\n".join(
        "    " + ", ".join("1" if name in kernels() else "0" for name in names[i : i + 16])
        for i in range(0, len(names), 16)
    )
    eligibility += ",\n    0, 0, 0, 0\n};\n"
    for relative, result in [
        (ASM, assembly(args.source_root)),
        ("src/common/call/cvm-native-segment-opcodes.inc", eligibility),
    ]:
        target = args.source_root / relative
        if args.check:
            assert target.read_text(encoding="utf-8") == result
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result, encoding="utf-8", newline="\n")
    print("CVM native segment catalog:", len(kernels()), "opcodes", flush=True)
