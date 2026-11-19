"""Shared owned-argv constructor and bounded readonly-capture admission."""

import ast
import hashlib
import json
from c_workers import module


def policy(source, output, loop):
    path = source / "tools/x86/common/codegen/call-forward-owned.py"
    tree = ast.parse(path.read_text())
    definitions = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CAPTURED_PROOF" for t in n.targets)
    ]
    if len(definitions) != 1:
        raise ValueError("Review shared readonly-capture proof owner")
    proof = ast.literal_eval(definitions[0].value)
    if not isinstance(proof, str) or proof.count("js_frame_captured_readonly(") != 1:
        raise ValueError("Review readonly-capture proof definition")
    (output / "quickjs-linux-captured-proof.h").write_text(proof)
    name_path = source / "tools/x86/common/codegen/set-name.py"
    name_tree = ast.parse(name_path.read_text())
    names = [
        n
        for n in name_tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "STEP" for t in n.targets)
    ]
    if len(names) != 1:
        raise ValueError("Review accepted set_name step owner")
    name_step = ast.literal_eval(names[0].value)
    for old, new in [
        ("FRAME_CODE", "QJS_FRAME_LITERAL_CODE"),
        ("JS_FrameVarargsNameStep", "JS_FrameLinuxSetNameStep"),
        ("JS_FrameVarargsDefineObjectName", "JS_DefineObjectName"),
        ("JS_FrameVarargsSlowSelect", "JS_FrameInterpSlow"),
    ]:
        if name_step.count(old) != 1:
            raise ValueError("Review set_name boundary: " + old)
        name_step = name_step.replace(old, new)
    # Keep the real Linux running-frame cursor convention after allocation.
    # Deferred publication proxies establish coherence before this C worker.
    name_step = name_step.replace(
        "    js_frame_finish_c(state);", "    sf->cur_sp=NULL;\n    js_frame_finish_c(state);", 1
    )
    name_step = name_step.replace(
        "static QJS_FRAME_LITERAL_CODE int JS_FrameLinuxSetNameStep(",
        "QJS_FRAME_LITERAL_CODE int JS_FrameLinuxSetNameStep(",
        1,
    )
    (output / "quickjs-linux-set-name.h").write_text(name_step)
    marker = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    final = "    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);"
    if loop.count(marker) != 1 or loop.count(final) != 1:
        raise ValueError("Review base classifier/proof publication")
    loop = loop.replace(marker, '#include "src/x86/linux/interpreter-js-calls.inc"\n\n' + marker, 1)
    loop = loop.replace(final, final + "\n    JS_LinuxCapturedReadonlyClassify(b);", 1)
    record = dict(
        status="generated-not-qualified",
        proof_source=str(path.relative_to(source)),
        proof_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        proof_sha256=hashlib.sha256(proof.encode()).hexdigest(),
        limits=dict(nodes=64, code_bytes=65536, pool_values=4096),
        qualification="Positive opcode whitelist;all descendant bytecode constants;no recursion/allocation",
        set_name_source_sha256=hashlib.sha256(name_path.read_bytes()).hexdigest(),
        set_name_sha256=hashlib.sha256(name_step.encode()).hexdigest(),
        entries=[
            "js_frame_captured_readonly",
            "JS_LinuxCapturedReadonlyClassify",
            "JS_FrameLinuxSetNameStep",
        ],
    )
    (output / "JS-CALLS.json").write_text(json.dumps(record, indent=2) + "\n")
    return loop


def append(source, stream, layout):
    if (
        layout["reference_count_model"] != "inline-header"
        or layout["offsets"]["JSGCObjectHeader.ref_count"] != 0
    ):
        raise ValueError("Review native owned-argument reference model")
    fields = layout["offsets"]
    code = fields["JSFunctionBytecode.byte_code_buf"]
    rows = stream["call_code"]
    start = rows.index("interp_meta_call_size_ready:") + 1
    end = rows.index("interp_meta_unready:")
    shared = module(source, "js-owned-missing")
    body = [
        s.replace("owned_js_", "linux_owned_")
        for s in shared.frame_body(rows[start:end], layout, False)
    ]
    publication = "mov QWORD PTR [r10+" + str(fields["JSRuntime.current_stack_frame"]) + "], rbp"
    if body.count(publication) != 1:
        raise ValueError("Review owned child publication")
    body.insert(body.index(publication), "linux_owned_publish:")
    owned, wide, push = (
        "JS_FrameLinuxJSOwnedMissing",
        "JS_FrameLinuxJSWideMissing",
        "JS_FrameLinuxJSOwnedPush",
    )
    ready = rows.index("interp_meta_ready:")
    stop = rows.index("interp_meta_call_arity_ok:", ready)
    for before in ("jne interp_slow", "jz interp_slow"):
        indices = [i for i in range(ready, stop) if rows[i] == before]
        if len(indices) != 1:
            raise ValueError("Review missing-arity admission: " + before)
        rows[indices[0]] = before.replace("interp_slow", owned)
    indices = [i for i in range(ready, stop) if rows[i] == "ja interp_slow"]
    if len(indices) != 1:
        raise ValueError("Review caller window bound")
    rows[indices[0]] = "ja " + wide
    index = rows.index("interp_meta_unready:")
    if rows[index + 1 : index + 5] != [
        "test eax, 1",
        "jz interp_slow",
        "test eax, 4",
        "jnz interp_slow",
    ]:
        raise ValueError("Review captured-argument rejection")
    rows[index + 4] = "jnz JS_FrameLinuxJSCaptured"
    if fields["JSRuntime.u"] - fields["JSRuntime.module_loader_has_attr"] != 8:
        raise ValueError("Review native argument-window policy padding")
    guard = [
        "cmp BYTE PTR [rip+JS_LinuxJSOwnedControl], 1",
        "jne interp_slow",
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{fields['JSRuntime.module_loader_has_attr'] + 7}], 0",
        "jne interp_slow",
    ]
    narrow = guard + [
        "cmp eax, 4",
        "ja " + wide,
        "mov r10, rax",
        "shl r10, 4",
        f"movzx eax, WORD PTR [r9+{code - 6}]",
        "sub eax, 32",
        "add rax, r10",
        "jmp " + push,
    ]
    broad = guard + [
        f"movzx eax, BYTE PTR [r9+{code - 3}]",
        "cmp eax, 128",
        "ja interp_slow",
        "mov r10, rax",
        "shl r10, 4",
        f"movzx eax, WORD PTR [r9+{code - 6}]",
        "sub eax, 32",
        "add rax, r10",
        "jmp " + push,
    ]
    captured = [
        f"movzx eax, BYTE PTR [r9+{code - 1}]",
        "and eax, 7",
        "cmp eax, 7",
        "jne interp_slow",
        "cmp BYTE PTR [rip+JS_LinuxJSCapturedControl], 1",
        "jne interp_slow",
        "linux_jscaptured_admitted:",
        f"test BYTE PTR [r9+{code - 1}], 16",
        "jz interp_meta_init",
        "jmp interp_meta_ready",
    ]
    record = dict(
        owned_missing=True,
        maximum_formals=128,
        captured_low_kind=7,
        shared_constructor_sha256=hashlib.sha256(
            (source / "tools/x86/common/codegen/js-owned-missing.py").read_bytes()
        ).hexdigest(),
        source_edges=dict(missing=2, window=1, captured=1),
        public_or_state_growth=False,
        ownership="Independent Dup for each supplied owned cell;undefined suffix;original close/pop/tail cleanup",
        publication="Owned cells,locals and captured table initialized before runtime SF publication",
        controls=[
            "QJS_DISABLE_FRAME_JS_OWNED_MISSING",
            "QJS_DISABLE_FRAME_JS_CAPTURED",
            "QJS_DISABLE_FRAME_CAPTURED_READONLY",
        ],
    )
    return (
        [(owned, narrow), (wide, broad), (push, body), ("JS_FrameLinuxJSCaptured", captured)],
        ["JS_LinuxJSOwnedControl", "JS_LinuxJSCapturedControl"],
        record,
    )
