"""Independent GNU compiler projection from this exact actual C type input."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from admission import function
from c_workers import replace_one

OWNERS = (
    "src/common/bytecode/compiler-plan-shim.inc",
    "src/common/bytecode/compiler-plan-view.h",
    "src/common/bytecode/compiler-plan.c",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actual_type_prefix(actual_input):
    prefix = actual_input[: actual_input.index("static inline bool double_is_int32")]
    prefix = re.sub(r"^const char\* JS_GetVersion\(void\) \{.*?^\}", "", prefix, flags=re.M | re.S)
    prefix = re.sub(r"^static\s+[^;{}]+\([^;{}]*\);\s*", "", prefix, flags=re.M)
    prefix = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", prefix, flags=re.M)
    return prefix


def generate(source, output, core, actual_input, layout):
    data = json.loads((source / "src/common/abi/compiler-projection.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review common compiler projection owner: " + name)
    if sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]:
        raise ValueError("Review original FD,opcode and compiler stack contracts")
    # This is source extraction,not a COFF-derived header. Preserve the actual
    # allocator/property/closure overlays and compile with the core target's
    # very same definitions/options. Both translation units use real C types.
    prefix = actual_type_prefix(actual_input)
    start = actual_input.index("typedef struct BlockEnv {")
    end = actual_input.index("} JSFunctionDef;", start) + len("} JSFunctionDef;")
    fd = actual_input[start:end]
    raw = source_file(source, "quickjs.c").read_text()
    if raw.count(fd) != 1:
        raise ValueError("Review original unchanged FD source types")
    start = actual_input.index("typedef struct JSOpCode {")
    end = (
        actual_input.index("\n};", actual_input.index("static const JSOpCode opcode_info[", start))
        + 3
    )
    opcodes = actual_input[start:end]
    stack = "\n".join(
        function(actual_input, signature)
        for signature in (
            "static inline uintptr_t js_get_stack_pointer(void)",
            "static inline bool js_check_stack_overflow(JSRuntime *rt, size_t alloca_size)",
        )
    )
    header = output / "quickjs-linux-compiler-private.h"
    header.write_text(
        """/* Exact actual core type prefix and original source definitions. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-const-variable"
"""
        + prefix
        + "\n"
        + fd
        + "\n"
        + stack
        + "\n"
        + opcodes
        + """
#include "interpreter-private-abi.h"
_Static_assert(sizeof(JSValue)==QJS_ABI_SIZE_JSValue,"same actual value type");
_Static_assert(offsetof(JSContext,rt)==QJS_ABI_OFF_JSContext_rt,"same actual context type");
#pragma GCC diagnostic pop
"""
    )
    shim = (source / OWNERS[0]).read_text()
    original = "static COMPILER_SHIM_CODE void js_compiler_bytecode_plan(JSContext *ctx, JSFunctionDef *fd)\n{"
    shim = replace_one(
        shim,
        original,
        '__attribute__((visibility("hidden"),section(".text.qjs_linux_compiler_projection")))\n'
        "COMPILER_SHIM_CODE void JS_CompilerFunctionPlan(JSContext *ctx, void *opaque)\n"
        "{\n    JSFunctionDef *fd=opaque;",
        "same common projection with ordinary typed opaque FD boundary",
    )
    path = output / "quickjs-linux-compiler-projection.c"
    path.write_text('#include "quickjs-linux-compiler-private.h"\n' + shim)
    core = replace_one(
        core,
        '#include "src/common/bytecode/compiler-plan-shim.inc"',
        "extern void JS_CompilerFunctionPlan(JSContext *,void *);",
        "independent compiler projection declaration",
    )
    core = replace_one(
        core,
        "    js_compiler_bytecode_plan(ctx, fd); if (resolve_labels(ctx, fd))",
        "    JS_CompilerFunctionPlan(ctx, fd); if (resolve_labels(ctx, fd))",
        "original typed compiler call before the unchanged final resolver",
    )
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            "tools/x86/linux/compiler_projection.py": sha(
                source / "tools/x86/linux/compiler_projection.py"
            )
        },
        generated_sha256=sha(path),
        private_sha256=sha(header),
        actual_input_sha256=hashlib.sha256(actual_input.encode()).hexdigest(),
        FD_source_sha256=hashlib.sha256(fd.encode()).hexdigest(),
        opcode_source_sha256=hashlib.sha256(opcodes.encode()).hexdigest(),
        actual_C_types=True,
        COFF_input=False,
        exported_runtime_helpers=[],
        entries=["JS_CompilerFunctionPlan"],
        lifetime="Borrowed FD,context,bytecode and labels only;no allocation or retained metadata",
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
    )
    (output / "COMPILER-PROJECTION.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
