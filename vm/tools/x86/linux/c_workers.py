"""Compile shared C workers with the real Linux core types and helper owners.

This is a source transformation before ordinary CMake compilation.  It does
not copy private struct layouts, patch objects, or admit Win64 compiler shapes.
Every replacement is bound to a source contract and an exact original site.
"""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def module(source, name):
    sys.path.insert(0, str(source / "tools"))
    from common.paths import activate_tools, tool_path

    activate_tools()
    spec = importlib.util.spec_from_file_location(
        "linux_worker_" + name.replace("-", "_"), tool_path(name + ".py")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def replace_one(text, old, new, label):
    matches = text.count(old)
    if matches == 1:
        return text.replace(old, new, 1)
    if matches:
        raise ValueError("Source-owned C worker boundary changed: " + label)
    # Keep the qualified exact-text path. Reflowed owned C may use the same
    # unique tokens across different whitespace; literals remain byte-sensitive.
    matcher = module(Path(__file__).resolve().parents[3], "c_source_match")
    try:
        return matcher.replace_one(text, old, new)
    except ValueError as error:
        raise ValueError("Source-owned C worker boundary changed: " + label) from error


def generate_async_generator(source, output, core):
    source, output = Path(source), Path(output)
    contract_path = source / "src/x86/linux/abi/c-workers.json"
    contract = json.loads(contract_path.read_text())
    for name, expected in contract.get("source_owners", {}).items():
        if hashlib.sha256(source_file(source, name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review async generator semantic owner: " + name)
    for name, key in (("quickjs.c", "source_sha256"), ("cutils.h", "cutils_sha256")):
        if hashlib.sha256(source_file(source, name).read_bytes()).hexdigest() != contract[key]:
            raise ValueError("Unreviewed Linux source-owned worker input: " + name)
    adapter = module(source, "object-adapter")
    raw = source_file(source, "quickjs.c").read_text()
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(raw)}
    async_contract = contract["async_generator"]
    for name, expected in async_contract["source_functions"].items():
        if digest(functions[name]) != expected:
            raise ValueError("Unreviewed async generator source: " + name)
    generator = module(source, "generator-capability")
    expanded, preface, body = generator.prepare_source(source, async_contract)
    prepared = {m[2]: m[0] for m in adapter.FUNCTION.finditer(expanded)}

    # All old and new paths share this owner.  In particular, a pending/rejected
    # await recovery callback, completed return or late-hook fallback may settle
    # a request whose two private resolver slots are undefined.
    old = functions["js_async_generator_resolve_or_reject"]
    new = prepared["js_async_generator_resolve_or_reject"]
    declarations = """
static JSValue js_generator_capability_settle(JSContext *, JSValueConst, JSValueConst, bool);
static void JS_GeneratorCapabilityResume(JSContext *, JSAsyncGeneratorData *);
static JSValue JS_GeneratorCapabilityNext(JSContext *, JSValueConst, int, JSValueConst *, int);
"""
    core = replace_one(core, old, declarations + new, "generator settlement owner")

    # Retain the original parent for the process-wide disabled control.  Only
    # its definition is renamed: both inherited recovery and inherited next
    # must enter the owned dispatcher, so mixed old/new requests stay safe.
    old = functions["js_async_generator_resume_next"]
    original_resume = old.replace(
        "js_async_generator_resume_next(", "js_linux_generator_resume_original(", 1
    )
    core = replace_one(core, old, original_resume, "retained generator parent")
    if len(re.findall(r"\bjs_async_generator_resume_next\b", core)) != 2:
        raise ValueError("Review every inherited generator parent caller")
    core = re.sub(r"\bjs_async_generator_resume_next\b", "JS_GeneratorCapabilityResume", core)
    routes = []
    for name, magic in (
        ("next", "GEN_MAGIC_NEXT"),
        ("return", "GEN_MAGIC_RETURN"),
        ("throw", "GEN_MAGIC_THROW"),
    ):
        old = 'JS_CFUNC_MAGIC_DEF("' + name + '", 1, js_async_generator_next, ' + magic + " )"
        new = old.replace("js_async_generator_next", "JS_GeneratorCapabilityNext")
        core = replace_one(core, old, new, "async generator method " + name)
        routes.append(dict(method=name, magic=magic, target="JS_GeneratorCapabilityNext"))

    # The COFF adapter's call-entry alias is not part of the C algorithm.
    # Here ordinary calls use the actual typed Linux selector already defined
    # in this TU.  Only the fresh, visible recovery-function specialization is
    # scoped over the worker body.
    begin = preface.index("#define js_async_generator_resolve_function")
    preface = preface[begin:]
    body = body.replace("qjs_generator_capability_original_next", "js_async_generator_next")
    body = body.replace("qjs_generator_capability_original", "js_linux_generator_resume_original")
    control = "static unsigned char js_generator_capability_mode;"
    body = replace_one(
        body,
        control,
        "static unsigned char js_generator_capability_mode "
        '__attribute__((section(".bss.qjs_generator_capability")));',
        "generator control",
    )
    # Added functions use their own named text family.  The common template is
    # unchanged; GCC determines real types, field accesses and SysV arguments.
    functions_added = []
    for match in reversed(list(adapter.FUNCTION.finditer(body))):
        functions_added.append(match[2])
        body = (
            body[: match.start()]
            + '__attribute__((section(".text.qjs_generator_capability")))\n'
            + body[match.start() :]
        )
    worker = preface + body + "\n#undef js_async_generator_resolve_function\n"
    target = output / "quickjs-linux-c-workers.h"
    target.write_text(worker)
    core += '\n/* Shared C workers: real core types, complete same-TU ownership. */\n#include "quickjs-linux-c-workers.h"\n'
    record = dict(
        routes=routes,
        inherited_parent_callers=2,
        added_functions=sorted(functions_added),
        settlement_owner="js_async_generator_resolve_or_reject",
        request_ownership="original public Promise; undefined private resolver pair; same-TU settlement",
        original_parent="js_linux_generator_resume_original",
        original_next="js_async_generator_next",
        public_abi="actual GCC SysV C",
    )
    return core, record


def generate(source, output, core, layout):
    source, output = Path(source), Path(output)
    contract_path = source / "src/x86/linux/abi/c-workers.json"
    adapter = module(source, "object-adapter")
    core, async_record = generate_async_generator(source, output, core)
    worker = (output / "quickjs-linux-c-workers.h").read_text()
    from x86.linux.prepared_callbacks import generate as generate_prepared_callbacks

    core, prepared_record = generate_prepared_callbacks(source, output, core, adapter)
    from x86.linux.json_workers import generate as generate_json_workers

    core, json_record = generate_json_workers(source, output, core, adapter, layout)
    from x86.linux.string_workers import generate as generate_string_workers

    core, string_record = generate_string_workers(source, output, core, adapter, layout)
    from x86.linux.array_workers import generate as generate_array_workers

    core, array_record = generate_array_workers(source, output, core, adapter)
    from builtin_workers import generate as generate_builtin_workers

    builtin_record = generate_builtin_workers(source, output)
    from x86.linux.regexp_workers import generate as generate_regexp_workers

    core, regexp_record = generate_regexp_workers(source, output, core, layout)
    record = dict(
        status="source-owned-workers-generated-not-qualified",
        source_contract_sha256=hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        worker_sha256=digest(worker),
        private_struct_clones=False,
        object_patching=False,
        prepared_callbacks=prepared_record,
        json=json_record,
        strings=string_record,
        arrays=array_record,
        builtins=builtin_record,
        regexp=regexp_record,
        async_generator=async_record,
    )
    (output / "C-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
