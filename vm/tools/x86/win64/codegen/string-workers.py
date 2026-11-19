"""Build source-bound string workers outside the original core call graph."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import (
    activate_tools,
    tool_path,
    generated_file,
    build_file,
    source_file,
    source_text,
)

activate_tools()
from string_rope import equality_function

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "string_" + name.replace("-", "_"), tool_path(name)
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def generate(source, build, target):
    adapter = module("object-adapter")
    text = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    original, body = equality_function(text)
    body = (
        "int JS_FrameStringLooseEq(JSContext *ctx, JSValue *sp, bool is_neq)\n"
        + body[body.index("{") :]
    )
    body += "\n" + source_text(source, "string-concat-win64-control.inc")
    body += "\n" + source_text(source, "string-concat-rope.inc")
    hint = re.search(r"typedef enum JSToNumberHintEnum \{[^{}]*\} JSToNumberHintEnum;", text, re.S)
    assert hint, "Review current numeric conversion types"
    expanded = text.replace(
        "static inline bool double_is_int32", hint[0] + "\nstatic inline bool double_is_int32", 1
    )
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    core = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    assert "js_eq_slow" in core.symbols, "Need the original complete slow comparison ABI"
    assert "JS_ConcatString" in core.symbols and "js_new_string_rope" in core.symbols, (
        "Need exact original consuming string helpers"
    )
    header, exports, copies = adapter.generate(expanded, core, body, owned_functions=["js_eq_slow"])
    assert header.count("#define JS_ConcatString qjs_frame_core_JS_ConcatString\n") == 1
    private = generated_file(build, "quickjs-string-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    target.write_text(
        '#include "quickjs-string-private.h"\n' + body, encoding="utf-8", newline="\n"
    )
    return dict(
        exports=exports,
        copies=copies,
        original_equality_sha256=hashlib.sha256(original[0].encode()).hexdigest(),
        private_sha256=sha(private),
        generated_sha256=sha(target),
        semantics="Full original conversion/redo/cleanup algorithm; flat and rope strings share the same language type.",
    )


def compile_extra(source, build, out):
    compiler = module("atod")
    records = json.loads(build_file(build, "compile_commands.json").read_text())
    msvc = any(
        "/nologo" in row["command"].lower()
        for row in records
        if Path(row["file"]).name == "quickjs-interpreter.c"
    )
    generated = {}

    def generator(src, target):
        generated.update(generate(src, build, target))

    compiler.compile_extra(
        source,
        build,
        out,
        generator=generator,
        filename="quickjs-string.c",
        late_name=".qjscold$zznullfast" if msvc else ".qjsex$strings",
    )
    from retained_routes import Router

    router = Router(out, build)
    router.alias("qjs_frame_core_js_eq_slow", "JS_FrameStringLooseEq")
    generated["worker_aliases"] = router.finish()
    if msvc:
        from core_routes import section_name

        destination = generated_file(build, "quickjs-interpreter-null-proto.obj")
        stamp = destination.stat()
        controls = [
            r
            for n, r in enumerate(router.co.section_records, 1)
            if section_name(router.co, n) == ".qjsstmd"
        ]
        assert len(controls) == 1 and controls[0]["size"] == 2 and controls[0]["count"] == 0
        assert router.co.data[controls[0]["raw"] : controls[0]["raw"] + 2] == b"\0\0"
        module("extension-merge").append(
            destination,
            out,
            "JS_FrameSharedConcatRope",
            "strings",
            keep_all=True,
            writable_metadata_inputs=(".qjsstmd",),
            metadata_inputs=(".voltbl",),
        )
        os.utime(destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    receipt = out.with_suffix(".compile.json")
    record = json.loads(receipt.read_text())
    record.update(
        object_sha256=sha(out),
        generated=generated,
        contract="Independent source-generated C worker; all new code/readonly helpers stay in the semantic island. Original core is not recompiled with this algorithm.",
    )
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return generated


def route_core(source, build):
    from retained_routes import Router
    from core_routes import rewrite
    from native_build import find_objdump

    path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    stamp = path.stat()
    router = Router(path, build)
    router.rename("qjs_frame_core_js_eq_slow", "qjs_frame_core_js_eq_slowLegacy")
    alias_proof = router.finish()
    result, routes = rewrite(
        path.read_bytes(),
        path,
        find_objdump(build),
        [dict(before="js_eq_slow", after="JS_FrameStringLooseEq", minimum=1)],
    )
    path.write_bytes(result)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    proof = dict(
        status="passed",
        alias_proof=alias_proof,
        routes=routes,
        object_sha256=sha(path),
        scope="Only decoded/relocated complete loose-comparison calls and explicit original alias rename. Other allocated object bytes/relocations are verified unchanged.",
    )
    generated_file(build, "quickjs-string-route.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    return proof


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--route", action="store_true", required=True)
    args = parser.parse_args()
    route_core(args.source, args.build)
