"""Full source-owned GNU C invocation/builtin owners over actual AAPCS64 types."""

import hashlib, json
from c_workers import module, replace_one


def generate(source, output, core):
    contract = source / "src/arm64/linux/abi/c-entry.json"
    for name, expected in json.loads(contract.read_text())["source_owners"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review complete native C/builtin owner: " + name)
    from builtin_workers import generate as generate_builtins

    record = generate_builtins(source, output)
    dense = module(source, "json-callback-c").DENSE_ARRAY_POP_BACKEND
    dense = dense.replace(".qjssrc$C", ".text.qjs_dense_pop").replace(
        ".qjssrm", ".bss.qjs_dense_pop"
    )
    for old, new in (
        ("dense_pop_control", "JS_LinuxDensePopControl"),
        ("dense_pop_leaf_control", "JS_LinuxDensePopLeafControl"),
    ):
        dense = replace_one(
            dense,
            "static _Atomic unsigned char " + old,
            '__attribute__((visibility("hidden"))) _Atomic unsigned char ' + old,
            "typed leaf policy",
        )
        dense = dense.replace(old, new)
    core = replace_one(
        core,
        'JS_CFUNC_MAGIC_DEF("pop", 0, js_array_pop, 0 )',
        'JS_CFUNC_MAGIC_DEF("pop", 0, JS_FrameDenseArrayPop, 0 )',
        "actual Array.pop intrinsic",
    )
    anchor = "static const JSCFunctionListEntry js_array_proto_funcs[] = {"
    core = replace_one(
        core,
        anchor,
        "JSValue JS_FrameDenseArrayPop(JSContext *,JSValueConst,int,JSValueConst *,int);\n"
        + anchor,
        "typed pop definition",
    )
    target = output / "interpreter-aarch64-c-entry.h"
    text = "/* Complete native C/builtin ownership; actual target compiler ABI. */\n" + dense
    text += '\n#include "src/common/linux/interpreter-linux-c-invoke.inc"\n'
    text += '#include "src/arm64/linux/interpreter-c-entry.inc"\n'
    target.write_text(text)
    core += '\n#include "interpreter-aarch64-c-entry.h"\n'
    record.update(
        architecture="aarch64",
        compiler_owned_abi=True,
        private_struct_clones=False,
        native_entries=[
            "JS_FrameAArch64CInvoke",
            "JS_FrameAArch64GenericInvoke",
            "JS_FrameAArch64NumericInvoke",
            "JS_FrameAArch64BuiltinInvoke",
            "JS_FrameInterpHostDirectShared",
            "JS_FrameInterpHostShared",
            "JS_FrameAArch64HostDirectValue",
            "JS_FrameAArch64HostValue",
        ],
        retained_entries=[
            "JS_FrameInterpHostDirectSharedOriginal",
            "JS_FrameInterpHostSharedOriginal",
        ],
        generated_entry_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_contract_sha256=hashlib.sha256(contract.read_bytes()).hexdigest(),
        worker_source_sha256=hashlib.sha256(
            (source / "src/arm64/linux/interpreter-c-entry.inc").read_bytes()
        ).hexdigest(),
        stack_reserve="actual C scope128+view128+512 C reserve+at most4080 borrowed padding",
        qualification="dedicated typed invoke/view/leaf workers;whole qualification pending",
        c_result="Actual standard AAPCS64 JSValue aggregate return in x0/x1;original int/source-C callers retain their explicit result/event wrappers",
        remaining=[
            "Frozen whole-corpus and noGit SDK qualification of the standard value return/owning consumer",
            "Hot builtin lifetime cache requires natural execution proof;current unported property/forwarding paths invalidate it",
        ],
        hardware_performance_qualified=False,
    )
    (output / "C-ENTRY.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
