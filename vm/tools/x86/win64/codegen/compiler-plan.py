"""Compile all native compiler-only code/data outside the runtime core TU."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import (
    activate_tools,
    tool_path,
    source_file,
    source_text,
    generated_file,
    build_file,
)

activate_tools()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "compiler_plan_" + name.replace("-", "_"), tool_path(name)
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def generate_projection(source, build, target):
    raw = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    start = raw.index("typedef struct BlockEnv {")
    end = raw.index("} JSFunctionDef;", start) + len("} JSFunctionDef;")
    types = raw[start:end]
    # The pointer is private, but both TUs must use the same actual FD layout.
    actual = generated_file(build, "backports/quickjs.c").read_text(encoding="utf-8")
    assert actual.count(types) == 1, (
        "Compiler FD types changed: review the projection before enabling it"
    )
    expanded = raw.replace(
        "static inline bool double_is_int32", types + "\nstatic inline bool double_is_int32", 1
    )
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    expanded = expanded.replace(
        "static int JS_PRINTF_FORMAT_ATTR(3, 4) JS_ThrowTypeErrorOrFalse(",
        "static int JS_ThrowTypeErrorOrFalse(",
        1,
    )
    shim = source_text(source, "compiler-plan-shim.inc")
    needle = "static COMPILER_SHIM_CODE void js_compiler_bytecode_plan(JSContext *ctx, JSFunctionDef *fd)\n{"
    assert shim.count(needle) == 1
    shim = shim.replace(
        needle,
        "COMPILER_SHIM_CODE void JS_CompilerFunctionPlan(JSContext *ctx, void *opaque)\n{\n    JSFunctionDef *fd=opaque;",
    )
    adapter = module("object-adapter")
    header, exports, copies = adapter.generate(
        expanded,
        adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes()),
        shim,
        owned_functions=("JS_CompilerFunctionPlan",),
        disabled_macros=("ENABLE_DUMPS",),
    )
    assert not exports, "Compiler field projection cannot add runtime-core exports"
    private = generated_file(build, "quickjs-compiler-plan-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    target.write_text(
        '#include "quickjs-compiler-plan-private.h"\n' + shim, encoding="utf-8", newline="\n"
    )
    return dict(
        FD_source_sha256=hashlib.sha256(types.encode()).hexdigest(),
        private_sha256=sha(private),
        exports=exports,
        copies=copies,
        ownership="Borrowed FD/context/bytecode/label view only; no JS allocation or retained state",
    )


def compile_native(source, build):
    runner = module("atod")
    records = json.loads(build_file(build, "compile_commands.json").read_text(encoding="utf-8"))
    recipe = next(r for r in records if Path(r["file"]).name == "quickjs-interpreter.c")
    msvc = any(a.lower() == "/nologo" for a in runner.win_argv(recipe["command"]))
    results = []
    for kind, suffix in [("analysis", "A"), ("projection", "S")]:
        out = generated_file(build, "quickjs-compiler-plan-" + kind + ".obj")
        generated = {}

        def generator(src, target):
            if kind == "analysis":
                target.write_text(
                    '#include "src/common/bytecode/compiler-plan.c"\n',
                    encoding="utf-8",
                    newline="\n",
                )
            else:
                generated.update(generate_projection(src, build, target))

        late = ".qjzzec$zzcompiler" + suffix if msvc else ".qjscmp$" + suffix
        runner.compile_extra(
            source,
            build,
            out,
            generator=generator,
            filename="quickjs-compiler-plan-" + kind + ".c",
            late_name=late,
        )
        co = module("object-adapter").Coff(out.read_bytes())
        allocated = []
        for sn, record in enumerate(co.section_records, 1):
            name = co.sections[sn - 1]["name"]
            if name.startswith("/"):
                offset = int(name[1:])
                name = co.strings[offset : co.strings.find(0, offset)].decode()
            if not record["size"] or name.startswith(".debug") or record["flags"] & 0x02000000:
                continue
            if record["flags"] & 0x80:
                assert not record["size"], "Compiler-only code cannot retain ordinary BSS"
            if record["flags"] & 0x60:
                assert name.startswith((".qjscmp$", ".qjzzec$", ".pdata$", ".rdata$.refptr.")), (
                    kind,
                    name,
                    "ordinary allocated compiler contribution",
                )
                allocated.append(dict(name=name, size=record["size"], flags=hex(record["flags"])))
        receipt = json.loads(out.with_suffix(".compile.json").read_text(encoding="utf-8"))
        receipt.update(generated=generated, allocated_sections=allocated)
        out.with_suffix(".compile.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        results.append(
            dict(
                kind=kind,
                path=str(out),
                sha256=sha(out),
                allocated_sections=allocated,
                generated=generated,
            )
        )
    generated_file(build, "quickjs-compiler-plan-native.json").write_text(
        json.dumps(
            dict(
                status="passed-native-compiler-code-data-isolation",
                records=results,
                core_interface="One typed JSContext pointer and opaque FD pointer call before original resolve_labels; no compiler helper definition or private FD projection in the core TU",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    compile_native(args.source.resolve(), args.build.resolve())
