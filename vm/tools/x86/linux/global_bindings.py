"""Complete shared GNU global hints,with measured Linux cells and SysV init."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import ast
import copy
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from arguments import asm_body
from c_workers import module

OWNERS = (
    "tools/x86/common/codegen/global-binding.py",
    "tools/x86/common/codegen/property_ic_native.py",
    "src/common/call/reference-config.inc",
    "src/common/call/interpreter-context-types.inc",
    "tools/x86/common/codegen/own-bytecode.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, layout):
    data = json.loads((source / "src/x86/linux/abi/global-bindings.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review complete global semantic owner: " + name)
    if sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]:
        raise ValueError("Review global constructor,shape and lexical invariants")
    if layout["reference_count_model"] != "inline-header":
        raise ValueError("Review actual global value reference model")
    for name, expected in (
        ("JSFrame.bytecode", 80),
        ("JSStackFrame.cur_pc", 48),
        ("JSFrameRegisterState.sites", 144),
        ("JSFrameRegisterState.cache_next", 152),
    ):
        # State/physical frame fields are asserted by the actual C header.
        if name in layout["offsets"] and layout["offsets"][name] != expected:
            raise ValueError("Review global VM field: " + name)
    return data


def source_rows(source, layout):
    """Execute only the existing source invariant/complete-rows factory.

    PE selector installation, IAT config and file/object adaptation are not
    executable Linux ABIs. Keep every getter/undefined algorithm row and every
    original constructor check; Linux supplies typed initialization and RELRO.
    """
    path = source / OWNERS[0]
    tree = ast.parse(path.read_text())
    original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate")

    def assignment(node, name):
        return isinstance(node, ast.Assign) and any(
            isinstance(x, ast.Name) and x.id == name for x in node.targets
        )

    begin = next(i for i, n in enumerate(original.body) if assignment(n, "selector_source"))
    resume = next(i for i, n in enumerate(original.body) if assignment(n, "guard_bucket"))
    end = next(i for i, n in enumerate(original.body) if assignment(n, "g"))
    if not begin < resume < end:
        raise ValueError("Review source-only global factory boundaries")
    selected = copy.deepcopy(original)
    selected.name = "linux_complete_global_source"
    selected.decorator_list = []
    selected.body = (
        copy.deepcopy(original.body[:begin])
        + ast.parse("selector=[]").body
        + copy.deepcopy(original.body[resume : end + 1])
        + ast.parse("return g,object_invariants,slots,undefined_atom").body
    )
    model = ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))
    shared = module(source, "global-binding")
    native = module(source, "property_ic_native")

    def measured_probe(abi, prefix, ready, relink):
        if relink != "JS_FrameGlobalBindingFallback":
            raise ValueError("Review source global-cell relink contract")
        # The retained Linux native base resolver has no cell-relink probe.
        # Use its original typed C step,with the current publication identity.
        if ready != "global_binding_ready":
            raise ValueError("Review resolved global-cell Symbol continuation")
        return native.global_cell_probe(
            abi,
            prefix,
            "JS_FrameLinuxGlobalSymbolCondition",
            "JS_FrameLinuxGlobalCellRelink",
            measured_tail=True,
        )

    def requested_module(root, name):
        if root != source or name != "property_ic_native":
            raise ValueError("Review new global source module dependency")
        return SimpleNamespace(global_cell_probe=measured_probe)

    namespace = dict(shared.__dict__)
    namespace.update(current_abi=lambda: layout, module=requested_module)
    exec(compile(model, str(path), "exec"), namespace)
    build = Path(layout["compiler_input"]).parents[2]
    cache = build / "CMakeCache.txt"
    if not cache.is_file() or ("QJS_PROPERTY_IC:BOOL=ON" in cache.read_text()) != bool(
        layout["property_ic"]
    ):
        raise ValueError("Global source factory needs the actual measured property configuration")
    rows, invariants, slots, atom = namespace[selected.name](source, build, False, False)
    return rows, dict(
        complete_source_factory_sha256=sha(path),
        selected_source_spans=[
            [original.body[0].lineno, original.body[begin - 1].end_lineno],
            [original.body[resume].lineno, original.body[end].end_lineno],
        ],
        constructor_invariants=invariants,
        dispatch_slots=slots,
        undefined_atom=atom,
        measured_configuration_sha256=sha(cache),
        cell_adapter="Actual measured tail fields and typed C-step relink,not inherited Win tail offsets",
    )


def append(source, output, stream, handlers, layout):
    data = contract(source, layout)
    rows, proof = source_rows(source, layout)
    text = "\n".join(rows)
    getter = asm_body(source, OWNERS[0], "JS_FrameGlobalBindingGet", layout, expanded=text)
    undefined = asm_body(source, OWNERS[0], "JS_FrameGlobalUndefinedLink", layout, expanded=text)
    original_hash = hashlib.sha256("\n".join(getter + undefined).encode()).hexdigest()
    # Static RELRO destinations replace the PE's one-time writable table
    # installation. One normal hot guard retains the complete original OFF
    # handler;first use calls only the typed nonobserving process initializer.
    getter = [
        "cmp BYTE PTR [rip+JS_FrameGlobalBindingControl], 1",
        "jne linux_global_control",
        *getter,
        "linux_global_control:",
        "cmp BYTE PTR [rip+JS_FrameGlobalBindingControl], 0",
        "jne JS_FrameGlobalBindingFallback",
        "mov rcx, rbx",
        "call JS_LinuxGlobalBindingInit",
        "jmp JS_FrameGlobalBindingGet",
    ]
    blocks = [("JS_FrameGlobalBindingGet", getter), ("JS_FrameGlobalUndefinedLink", undefined)]
    if layout["property_ic"]:
        blocks.append(
            (
                "JS_FrameLinuxGlobalCellRelink",
                [
                    "lea r10, [rip+JS_FramePublishDirtyTable]",
                    "cmp rdi, r10",
                    "je dirty_interp_slow",
                    "jmp interp_slow",
                ],
            )
        )
    symbol_proof = []
    if layout["property_ic"]:
        own = module(source, "own-bytecode")
        symbol, _, symbol_proof = own.symbol_global_blocks(
            layout,
            source,
            name="JS_FrameLinuxGlobalSymbolCondition",
            old="JS_FrameLinuxGlobalSymbolOriginalReady",
            prefix="linux_symbol_global",
        )
        symbol[0][1].extend(["JS_FrameLinuxGlobalSymbolOriginalReady:", "jmp global_binding_ready"])
        blocks += symbol
    names = ("get_var", "get_var_undef")
    slots = [stream["opcodes"].index(n) for n in names]
    if slots != proof["dispatch_slots"]:
        raise ValueError("Review the two real global opcode slots")
    original_handlers = {n: handlers.get(n, "interp_" + n) for n in names}
    for n in names:
        handlers[n] = "JS_FrameGlobalBindingGet"
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=[n for n, _ in blocks],
        shared_Clean_Dirty=True,
        nonobserving_helpers=["JS_LinuxGlobalBindingInit"],
        original_source_rows_sha256=original_hash,
        source_factory=proof,
        original_handlers=original_handlers,
        dispatch_slots=slots,
        resolved_cell_symbol_contracts=symbol_proof,
        controls=[
            "QJS_DISABLE_FRAME_GLOBAL_BINDING",
            "QJS_DISABLE_FRAME_GLOBAL_UNDEFINED",
            "QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS",
        ],
        cache=dict(
            slots=16,
            slot_bytes=32,
            global_marker=-2,
            lexical_marker=-3,
            existing_state_sites=144,
            existing_state_next=152,
            lifetime="Borrowed activation address/atom/index/arithmetic hints;no retained object,shape or value",
        ),
        frame_growth=0,
        state_growth=0,
        extra_activation_bytes=0,
        new_strong_roots=0,
    )
    (output / "GLOBAL-BINDINGS-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return blocks, record


def render_native():
    return [
        '.section .data.qjs_linux_global_arithmetic,"aw",@progbits',
        ".p2align 3",
        ".globl JS_FrameGlobalUndefinedArithmetic",
        ".hidden JS_FrameGlobalUndefinedArithmetic",
        ".type JS_FrameGlobalUndefinedArithmetic,@object",
        "JS_FrameGlobalUndefinedArithmetic:",
        ".quad 4294967295",
        ".size JS_FrameGlobalUndefinedArithmetic,.-JS_FrameGlobalUndefinedArithmetic",
        ".hidden JS_FrameGlobalBindingControl",
        ".hidden JS_FrameGlobalUndefinedControl",
    ]


def generate(source, output, core, layout):
    data = contract(source, layout)
    assignments = re.findall(r"->(global_obj|global_var_obj)\s*=(?!=)\s*(.*?);", core, re.S)
    expected = {
        "global_obj": "JS_NewObjectProtoClassAlloc(ctx, ctx->class_proto[JS_CLASS_OBJECT], JS_CLASS_OBJECT, 64)",
        "global_var_obj": "JS_NewObjectProtoClassAlloc(ctx, JS_NULL, JS_CLASS_OBJECT, 16)",
    }
    if len(assignments) != 2 or {n: " ".join(v.split()) for n, v in assignments} != expected:
        raise ValueError("Review actual overlaid global constructor assignments")
    text = '#include "src/common/linux/interpreter-global-bindings.inc"\n'
    path = output / "quickjs-linux-global-bindings.h"
    path.write_text(text)
    core += '\n#include "quickjs-linux-global-bindings.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/global_bindings.py",
                "src/common/linux/interpreter-global-bindings.inc",
            )
        },
        generated_sha256=sha(path),
        entries=["JS_LinuxGlobalBindingInit"],
        pure_helpers=["JS_LinuxGlobalBindingInit"],
        ABI="int(actual JSFrameRegisterState*),unused state;CRT getenv and scalar atomics only",
        actual_global_constructors=expected,
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
        per_runtime_heap_growth=0,
        restored_own_bytecode_reference_configuration=bool(layout["property_ic"]),
    )
    (output / "GLOBAL-BINDINGS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
