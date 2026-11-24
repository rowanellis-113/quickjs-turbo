"""Check the actual linked ARM64 register image and its measured source inputs."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import activate_arm64_tools, source_file

activate_arm64_tools()
Elf64 = importlib.import_module("elf64").Elf64


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_build_file(build, name):
    for directory in (build, *build.parents):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} not found in {build} or parent build directories")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "image", "readelf", "archive", "ar"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    source, build, image = (p.resolve() for p in (a.source, a.build, a.image))
    cache_text = find_build_file(build, "CMakeCache.txt").read_text()
    compile_commands_path = find_build_file(build, "compile_commands.json")
    output = build / "generated/aarch64-vm"
    receipt = json.loads((output / "VM.json").read_text())
    number = receipt["number_dataflow"]
    expected_number = "QJS_AARCH64_NUMBER_DATAFLOW:BOOL=ON" in cache_text
    if number["enabled"] != expected_number:
        raise ValueError("Number dataflow compile route changed")
    commands = json.loads(compile_commands_path.read_text())
    selected_number = [
        c for c in commands if c["file"].endswith("/interpreter-aarch64-number-dataflow.S")
    ]
    if len(selected_number) != int(expected_number):
        raise ValueError("Actual selected number dataflow assembly differs")
    if json.loads((output / "NUMBER-DATAFLOW.json").read_text()) != number:
        raise ValueError("Number dataflow receipt changed")
    for name, digest in number["source_owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Number dataflow source owner changed: " + name)
    if sha(source / "src/arm64/linux/abi/number-dataflow.json") != number["contract_sha256"]:
        raise ValueError("Number dataflow contract changed")
    if number["enabled"]:
        if sha(output / "interpreter-aarch64-number-dataflow.S") != number["generated_sha256"]:
            raise ValueError("Actual complete number dataflow stream changed")
    expected_fast_vm = "QJS_AARCH64_FAST_VM:BOOL=ON" in cache_text
    if expected_fast_vm != ("fast_vm" in receipt):
        raise ValueError("Fast VM compile route changed")
    if expected_fast_vm:
        from arm64.vm.specialize import generator_digest as fast_vm_digest

        fast_rec = receipt["fast_vm"]
        if json.loads((output / "FAST-VM.json").read_text()) != fast_rec:
            raise ValueError("Fast VM receipt changed")
        if sha(source / "src/arm64/linux/abi/fast-vm.json") != fast_rec["contract_sha256"]:
            raise ValueError("Fast VM contract changed")
        if fast_vm_digest(source) != fast_rec["generator_sha256"]:
            raise ValueError("Fast VM generator changed")
        for name, digest in fast_rec["source_owners"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Fast VM source owner changed: " + name)
    scalar = receipt["scalar_ops"]
    if sha(output / "SCALAR-OPS.json") != receipt["scalar_receipt_sha256"]:
        raise ValueError("Scalar receipt changed")
    if scalar["enabled"] != ("-DQJS_AARCH64_SCALAR_OPS" in receipt["flags"]):
        raise ValueError("Scalar compile route changed")
    for n, h in scalar["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Scalar original source owner changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/scalar-ops.json", "contract_sha256"),
        (source / "tools/arm64/vm/scalar_ops.py", "generator_sha256"),
        (source / "asm/arm64/common/register-scalar-ops.inc", "asm_sha256"),
        (source / "src/arm64/linux/scalar-policy.c", "policy_sha256"),
    ]:
        if sha(p) != scalar[key]:
            raise ValueError("Scalar actual source/target binding changed: " + str(p))
    call_leaves = receipt["call_leaves"]
    if sha(output / "CALL-LEAVES.json") != receipt["call_leaves_receipt_sha256"]:
        raise ValueError("Call leaves receipt changed")
    if call_leaves["enabled"] != ("-DQJS_AARCH64_CALL_LEAVES" in receipt["flags"]):
        raise ValueError("Call leaves target route changed")
    for n, h in call_leaves["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Call leaf original owner changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/call-leaves.json", "contract_sha256"),
        (source / "tools/arm64/workers/call_leaves.py", "generator_sha256"),
        (source / "src/arm64/linux/interpreter-call-leaves.inc", "worker_source_sha256"),
        (output / "quickjs-aarch64-call-leaves.c", "generated_sha256"),
        (output / "quickjs-aarch64-call-leaves-private.h", "private_sha256"),
        (output / "interpreter-aarch64-leaf-supplements.h", "supplements_sha256"),
        (output / "interpreter-aarch64-leaf-bridge.inc", "bridge_sha256"),
    ]:
        if sha(p) != call_leaves[key]:
            raise ValueError("Call leaf actual type/source binding changed: " + str(p))
    stack_insert = receipt["stack_insert"]
    if sha(output / "STACK-INSERT.json") != receipt["stack_insert_receipt_sha256"]:
        raise ValueError("Stack insert receipt changed")
    if stack_insert["enabled"] != ("-DQJS_AARCH64_STACK_INSERT" in receipt["flags"]):
        raise ValueError("Actual insert3 compile route changed")
    for n, h in stack_insert["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Stack insert source owner changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/stack-insert.json", "contract_sha256"),
        (source / "tools/arm64/workers/stack_insert.py", "generator_sha256"),
    ]:
        if sha(p) != stack_insert[key]:
            raise ValueError("Stack insert target/source binding changed")
    strings = receipt["strings"]
    if sha(output / "STRING-WORKERS.json") != receipt["strings_receipt_sha256"]:
        raise ValueError("String receipt changed")
    if strings["enabled"] != ("-DQJS_AARCH64_STRING_WORKERS" in receipt["flags"]):
        raise ValueError("Actual string target route changed")
    for n, h in strings["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("String semantic owner changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/strings.json", "contract_sha256"),
        (source / "tools/arm64/workers/strings.py", "generator_sha256"),
    ]:
        if sha(p) != strings[key]:
            raise ValueError("String actual-type/source binding changed")
    if (
        strings["enabled"]
        and sha(output / "quickjs-linux-strings.h") != strings["generated_sha256"]
    ):
        raise ValueError("Complete string owner changed")
    numeric = receipt["numeric_workers"]
    if sha(output / "NUMERIC-WORKERS.json") != receipt["numeric_workers_receipt_sha256"]:
        raise ValueError("Numeric/FD receipt changed")
    if numeric["numeric"]["enabled"] != ("-DQJS_AARCH64_NUMERIC_WORKERS" in receipt["flags"]):
        raise ValueError("Actual numeric target route changed")
    if numeric["projection"]["enabled"] != (
        "-DQJS_AARCH64_COMPILER_PROJECTION" in receipt["flags"]
    ):
        raise ValueError("Actual independent FD target route changed")
    for n, h in numeric["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Numeric/FD original owner changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/numeric-workers.json", "contract_sha256"),
        (source / "tools/arm64/workers/numeric_workers.py", "generator_sha256"),
    ]:
        if sha(p) != numeric[key]:
            raise ValueError("Numeric/FD source binding changed")
    if numeric["numeric"]["enabled"]:
        for name, key in [
            ("quickjs-linux-numeric.h", "generated_sha256"),
            ("quickjs-linux-bigint.h", "primitive_sha256"),
            ("quickjs-linux-atod.c", "decimal_sha256"),
            ("numeric-source/quickjs-linux-loop.h", "loop_after_sha256"),
        ]:
            if sha(output / name) != numeric["numeric"][key]:
                raise ValueError("Complete numeric owner changed: " + name)
    if numeric["projection"]["enabled"]:
        for name, key in [
            ("quickjs-linux-compiler-projection.c", "generated_sha256"),
            ("quickjs-linux-compiler-private.h", "private_sha256"),
        ]:
            if sha(output / name) != numeric["projection"][key]:
                raise ValueError("Independent actual FD owner changed")
    literals = receipt["literals"]
    if sha(output / "LITERALS.json") != receipt["literals_receipt_sha256"]:
        raise ValueError("Literal receipt changed")
    if literals["enabled"] != ("-DQJS_AARCH64_LITERALS" in receipt["flags"]):
        raise ValueError("Literal actual target route changed")
    for n, h in literals["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Literal source changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/literals.json", "contract_sha256"),
        (source / "tools/arm64/workers/literals.py", "generator_sha256"),
        (output / "quickjs-linux-literals.h", "generated_sha256"),
    ]:
        if sha(p) != literals[key]:
            raise ValueError("Literal measured type/source contract changed")
    indexed = receipt["indexed"]
    if sha(output / "INDEXED.json") != receipt["indexed_receipt_sha256"]:
        raise ValueError("Indexed receipt changed")
    if indexed["enabled"] != ("-DQJS_AARCH64_INDEXED" in receipt["flags"]):
        raise ValueError("Indexed actual compiler route changed")
    for n, h in indexed["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Indexed source changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/indexed.json", "contract_sha256"),
        (source / "tools/arm64/workers/indexed.py", "generator_sha256"),
        (output / "quickjs-linux-indexed.h", "generated_sha256"),
    ]:
        if sha(p) != indexed[key]:
            raise ValueError("Indexed typed source contract changed")
    varargs = receipt["varargs"]
    if sha(output / "VARARGS.json") != receipt["varargs_receipt_sha256"]:
        raise ValueError("Varargs receipt changed")
    if varargs["enabled"] != ("-DQJS_AARCH64_VARARGS" in receipt["flags"]):
        raise ValueError("Varargs actual compiler route changed")
    for n, h in varargs["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Varargs source changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/varargs.json", "source_contract_sha256"),
        (source / "tools/arm64/workers/varargs.py", "generator_sha256"),
    ]:
        if sha(p) != varargs[key]:
            raise ValueError("Varargs contract changed")
    if varargs["enabled"]:
        if sha(output / "quickjs-linux-varargs.h") != varargs["generated_sha256"]:
            raise ValueError("Complete shared apply owner changed")
        if (
            sha(output / "interpreter-aarch64-constructors.h")
            != varargs["actual_extended_slow_sha256"]
        ):
            raise ValueError("Complete direct/fusion slow owner changed")
    arguments = receipt["arguments"]
    if sha(output / "ARGUMENTS.json") != receipt["arguments_receipt_sha256"]:
        raise ValueError("Argument receipt changed")
    if arguments["enabled"] != ("-DQJS_AARCH64_ARGUMENTS" in receipt["flags"]):
        raise ValueError("Argument actual compiler route changed")
    for n, h in arguments["source_owners"].items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Argument source changed: " + n)
    for p, key in [
        (source / "src/arm64/linux/abi/arguments.json", "source_contract_sha256"),
        (source / "tools/arm64/workers/arguments.py", "generator_sha256"),
    ]:
        if sha(p) != arguments[key]:
            raise ValueError("Argument contract changed")
    if arguments["enabled"]:
        if sha(output / "quickjs-linux-arguments.h") != arguments["generated_sha256"]:
            raise ValueError("Complete shared argument owner changed")
        virtual = json.loads((output / "VIRTUAL-ARGUMENTS.json").read_text())
        for name, key in [
            ("quickjs-linux-virtual-arguments-private.h", "private_sha256"),
            ("quickjs-linux-virtual-arguments.c", "worker_sha256"),
        ]:
            if sha(output / name) != virtual[key]:
                raise ValueError("Actual private virtual-argument TU changed")
        for n, h in virtual["source_files"].items():
            if sha(source_file(source, n)) != h:
                raise ValueError("Virtual argument source changed: " + n)
    null = receipt["null_proto"]
    if sha(output / "NULL-PROTO.json") != receipt["null_proto_receipt_sha256"]:
        raise ValueError("Null-prototype receipt changed")
    if null["enabled"] != ("-DQJS_AARCH64_NULL_PROTO" in receipt["flags"]):
        raise ValueError("Null-prototype compiler route changed")
    for name, expected in null["source_owners"].items():
        if sha(source_file(source, name)) != expected:
            raise ValueError("Null-prototype source changed: " + name)
    for p, key in [
        (source / "src/arm64/linux/abi/null-proto.json", "source_contract_sha256"),
        (source / "tools/arm64/workers/null_proto.py", "generator_sha256"),
        (output / "quickjs-linux-null-proto.h", "generated_sha256"),
    ]:
        if sha(p) != null[key]:
            raise ValueError("Null-prototype typed contract changed")
    arrays = receipt["array_workers"]
    if sha(output / "ARRAY-WORKERS.json") != receipt["array_workers_receipt_sha256"]:
        raise ValueError("Array-worker receipt changed")
    if arrays["enabled"] != ("-DQJS_AARCH64_ARRAY_WORKERS" in receipt["flags"]):
        raise ValueError("Array C owner compiler route changed")
    for name, expected in arrays["source_owners"].items():
        if sha(source_file(source, name)) != expected:
            raise ValueError("Array/sort semantic owner changed: " + name)
    for p, key in [
        (source / "src/arm64/linux/abi/array-workers.json", "source_contract_sha256"),
        (source / "tools/arm64/workers/array_workers.py", "generator_sha256"),
        (output / "quickjs-linux-arrays.h", "header_sha256"),
    ]:
        if sha(p) != arrays[key]:
            raise ValueError("Array/sort typed source contract changed")
    array_own = receipt["array_own"]
    if sha(output / "ARRAY-OWN.json") != receipt["array_own_receipt_sha256"]:
        raise ValueError("Array-own receipt changed")
    for path, expected in array_own["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Array-own source changed: " + path)
    for path, key in [
        (source / "src/arm64/linux/abi/array-own.json", "contract_sha256"),
        (source / "tools/arm64/workers/array_own.py", "generator_sha256"),
        (output / "interpreter-aarch64-array-own.h", "header_sha256"),
    ]:
        if sha(path) != array_own[key]:
            raise ValueError("Array-own generated contract changed: " + str(path))
    if array_own["enabled"] != ("-DQJS_AARCH64_ARRAY_OWN" in receipt["flags"]):
        raise ValueError("Array-own must match actual compiler feature")
    forwarding = receipt["forwarding"]
    if sha(output / "FORWARDING.json") != receipt["forwarding_receipt_sha256"]:
        raise ValueError("Forward receipt changed")
    if forwarding["enabled"] != ("-DQJS_AARCH64_FORWARDING" in receipt["flags"]):
        raise ValueError("Forward compiler route mismatch")
    for path, expected in forwarding["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Forward semantic owner changed: " + path)
    for path, key in [
        (source / "src/arm64/linux/abi/forwarding.json", "contract_sha256"),
        (source / "tools/arm64/workers/forwarding.py", "generator_sha256"),
        (output / "interpreter-aarch64-forward.h", "header_sha256"),
    ]:
        if sha(path) != forwarding[key]:
            raise ValueError("Forward source/generated contract changed")
    if forwarding["enabled"]:
        captured = forwarding["captured_readonly"]
        if sha(output / "interpreter-aarch64-captured-readonly.h") != captured["header_sha256"]:
            raise ValueError("Captured-readonly source-derived proof changed")
        if (
            sha(source_file(source, captured["classifier_source"]))
            != captured["classifier_source_sha256"]
        ):
            raise ValueError("Captured-readonly original classifier changed")
        if (
            captured["nodes"],
            captured["code_bytes"],
            captured["pool_values"],
            captured["stack_guard"],
            captured["ordinary_kind"],
        ) != (64, 65536, 4096, 1024, 7):
            raise ValueError("Captured-readonly proof/entry bounds changed")
    globals_record = receipt["global_bindings"]
    if sha(output / "GLOBAL-BINDINGS.json") != receipt["global_bindings_receipt_sha256"]:
        raise ValueError("Global binding receipt changed")
    for name, key in (
        ("interpreter-aarch64-globals.h", "worker_sha256"),
        ("interpreter-aarch64-global-types.h", "types_sha256"),
        ("GLOBAL-ORIGINAL-ALGORITHMS.json", "original_algorithms_receipt_sha256"),
    ):
        if sha(output / name) != globals_record[key]:
            raise ValueError("Global generated semantic owner changed: " + name)
    for path, expected in globals_record["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Global semantic owner changed: " + path)
    if (
        sha(source / "src/arm64/linux/abi/global-bindings.json")
        != globals_record["source_contract_sha256"]
        or sha(source / "tools/arm64/workers/global_bindings.py")
        != globals_record["generator_sha256"]
    ):
        raise ValueError("Global source/generator contract changed")
    if globals_record["enabled"] != ("-DQJS_AARCH64_GLOBAL_BINDING" in receipt["flags"]):
        raise ValueError("Global native route must match actual compiler definition")
    constructors = receipt["constructors"]
    if sha(output / "CONSTRUCTORS.json") != receipt["constructors_receipt_sha256"]:
        raise ValueError("Constructor receipt changed")
    if constructors["enabled"] != ("-DQJS_AARCH64_CONSTRUCTORS" in receipt["flags"]):
        raise ValueError("Constructor route differs from actual compiler input")
    if (
        sha(source / "tools/arm64/workers/constructors.py") != constructors["generator_sha256"]
        or sha(source / "src/arm64/linux/abi/constructors.json") != constructors["contract_sha256"]
    ):
        raise ValueError("Constructor generator/contract changed")
    for path, expected in constructors["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Constructor source owner changed: " + path)
    iterators = receipt["iterators"]
    extended = receipt["extended_calls"]
    for name, data, key in [
        ("ITERATORS.json", iterators, "iterators_receipt_sha256"),
        ("EXTENDED-CALLS.json", extended, "extended_calls_receipt_sha256"),
    ]:
        if sha(output / name) != receipt[key]:
            raise ValueError("Extended/iterator receipt changed: " + name)
    if iterators["enabled"] != ("-DQJS_AARCH64_ITERATORS" in receipt["flags"]):
        raise ValueError("Iterator route differs from actual compiler input")
    if extended["enabled"] != ("-DQJS_AARCH64_EXTENDED_CALLS" in receipt["flags"]) or extended[
        "enabled"
    ] != (constructors["enabled"] or iterators["enabled"] or forwarding["enabled"]):
        raise ValueError("Complete executor must match independent constructor/iterator flags")
    if (
        sha(source / "tools/arm64/workers/iterators.py") != iterators["generator_sha256"]
        or sha(source / "src/arm64/linux/abi/iterators.json") != iterators["contract_sha256"]
    ):
        raise ValueError("Iterator generator/contract changed")
    if sha(source / "tools/arm64/workers/extended_calls.py") != extended["generator_sha256"]:
        raise ValueError("Complete executor generator changed")
    for path, expected in extended["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Complete executor source changed: " + path)
    if sha(output / "interpreter-aarch64-complete-ops.inc") != extended["semantic_ops_sha256"]:
        raise ValueError("Complete semantic opcode owner changed")
    for family in (constructors, iterators):
        if family["complete_executor_receipt_sha256"] != receipt["extended_calls_receipt_sha256"]:
            raise ValueError("Family refers to a different complete executor")
    if extended["enabled"]:
        for name, key in [
            ("interpreter-aarch64-constructors.h", "generated_sha256"),
            ("interpreter-aarch64-construct-host.h", "host_sha256"),
            ("interpreter-aarch64-construct-dispatch.h", "dispatch_sha256"),
            ("quickjs-interpreter-slow.h", "base_slow_sha256"),
        ]:
            if sha(output / name) != extended[key]:
                raise ValueError("Complete generated owner changed: " + name)
    if extended["enabled"]:
        original_map = dict(
            re.findall(
                r"FRAME_TARGET\((\w+),\s*(\w+)\)",
                (output / "interpreter-aarch64-dispatch-c.inc").read_text(),
            )
        )
        complete_map = dict(
            re.findall(
                r"FRAME_TARGET\((\w+),\s*(\w+)\)",
                (output / "interpreter-aarch64-construct-dispatch.h").read_text(),
            )
        )
        if set(original_map) != set(complete_map) or any(
            target != "invalid" and complete_map[op] != target
            for op, target in original_map.items()
        ):
            raise ValueError("Complete C executor lost an inherited target semantic dispatch")
    if iterators["enabled"]:
        if (
            receipt["owned"]["OFF_JSFrameRegisterState_iterator_checkpoint_depth"] != 164
            or receipt["owned"]["SIZE_JSFrameRegisterState"] != 168
        ):
            raise ValueError("Actual checkpoint field must retain the inherited state geometry")
    comparisons = receipt["comparisons"]
    if sha(output / "COMPARISONS.json") != receipt["comparisons_receipt_sha256"]:
        raise ValueError("Comparison receipt changed")
    if comparisons["enabled"] != ("-DQJS_AARCH64_COMPARISONS" in receipt["flags"]):
        raise ValueError("Comparison route differs from actual compiler flag")
    for path, key in (
        (output / "interpreter-aarch64-comparisons.h", "worker_sha256"),
        (output / "COMPARISONS-ORIGINAL-ALGORITHMS.json", "original_algorithms_sha256"),
        (source / "src/arm64/linux/abi/comparisons.json", "source_contract_sha256"),
        (source / "tools/arm64/workers/comparisons.py", "generator_sha256"),
    ):
        if sha(path) != comparisons[key]:
            raise ValueError("Comparison semantic owner changed: " + str(path))
    for path, expected in comparisons["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Comparison source changed: " + path)
    stores = receipt["reference_stores"]
    if sha(output / "REFERENCE-STORES.json") != receipt["reference_stores_receipt_sha256"]:
        raise ValueError("Reference store receipt changed")
    for path, expected in stores["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Reference store semantic owner changed: " + path)
    if (
        sha(source / "src/arm64/linux/abi/reference-stores.json")
        != stores["source_contract_sha256"]
        or sha(source / "tools/arm64/workers/reference_stores.py")
        != stores["source_generator_sha256"]
    ):
        raise ValueError("Reference store generation contract changed")
    proto = receipt["property_prototypes"]
    if sha(output / "PROPERTY-PROTOTYPES.json") != receipt["property_prototypes_receipt_sha256"]:
        raise ValueError("Prototype receipt changed")
    for name, key in (
        ("interpreter-aarch64-proto.h", "worker_sha256"),
        ("interpreter-aarch64-proto-types.h", "types_sha256"),
    ):
        if sha(output / name) != proto[key]:
            raise ValueError("Prototype generated owner changed: " + name)
    for path, expected in proto["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Prototype semantic owner changed: " + path)
    own_hints = receipt["property_hints"]
    if sha(output / "PROPERTY-HINTS.json") != receipt["property_hints_receipt_sha256"]:
        raise ValueError("Own-tail receipt changed")
    for name, key in (
        ("interpreter-aarch64-own.h", "worker_sha256"),
        ("interpreter-aarch64-own-types.h", "types_sha256"),
        ("interpreter-aarch64-own-wire.h", "wire_sha256"),
    ):
        if sha(output / name) != own_hints[key]:
            raise ValueError("Own-tail generated owner changed: " + name)
    for path, expected in own_hints["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Own-tail semantic owner changed: " + path)
    primitives = receipt["property_primitives"]
    for path, key in (
        (output / "PROPERTY-PRIMITIVES.json", "property_primitives_receipt_sha256"),
        (
            source / "tools/arm64/workers/property_primitives.py",
            "property_primitives_generator_sha256",
        ),
        (
            source / "src/arm64/linux/abi/property-primitives.json",
            "property_primitives_contract_sha256",
        ),
        (
            source / "asm/arm64/common/register-property-primitives.inc",
            "property_primitives_source_sha256",
        ),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("Primitive property input changed: " + str(path))
    for path, expected in primitives["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Primitive property semantic owner changed: " + path)
    for name, key in (
        ("interpreter-aarch64-property-primitives.h", "worker_sha256"),
        ("interpreter-aarch64-property-types.h", "types_sha256"),
    ):
        if sha(output / name) != primitives[key]:
            raise ValueError("Actual primitive C worker/type changed: " + name)
    properties = receipt["properties"]
    for path, key in (
        (output / "PROPERTIES.json", "properties_receipt_sha256"),
        (source / "tools/arm64/workers/properties.py", "properties_generator_sha256"),
        (source / "src/arm64/linux/abi/properties.json", "properties_contract_sha256"),
        (source / "asm/arm64/common/register-property-ic.inc", "properties_source_sha256"),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("Native property input changed: " + str(path))
    for path, expected in properties["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Native property/cache owner changed: " + path)
    c_return = receipt["c_return"]
    for path, key in (
        (output / "C-RETURN.json", "c_return_receipt_sha256"),
        (source / "tools/arm64/vm/c_return.py", "c_return_generator_sha256"),
        (source / "src/arm64/linux/abi/c-return.json", "c_return_contract_sha256"),
        (source / "asm/arm64/common/register-host-return.inc", "host_return_source_sha256"),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("Native host return input changed: " + str(path))
    for name, key in [
        ("c-return-abi-probe.c", "source_sha256"),
        ("c-return-abi-probe.o", "object_sha256"),
    ]:
        if sha(output / name) != c_return[key]:
            raise ValueError("Actual return/free ABI witness changed: " + name)
    for path, expected in json.loads((source / "src/arm64/linux/abi/c-return.json").read_text())[
        "source_owners"
    ].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Host return semantic owner changed: " + path)
    c_entry = receipt["c_entry"]
    for path, key in (
        (output / "C-ENTRY.json", "c_entry_receipt_sha256"),
        (source / "tools/arm64/vm/c_entry.py", "c_entry_generator_sha256"),
        (source / "src/arm64/linux/interpreter-c-entry.inc", "c_entry_source_sha256"),
        (source / "src/arm64/linux/abi/c-entry.json", "c_entry_contract_sha256"),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("Native C entry input changed: " + str(path))
    if sha(output / "interpreter-aarch64-c-entry.h") != c_entry["generated_entry_sha256"]:
        raise ValueError("Native C entry generated ownership changed")
    if sha(output / "quickjs-linux-builtin.h") != c_entry["generated_sha256"]:
        raise ValueError("Shared slice/decimal builtin semantic bodies changed")
    for path, expected in json.loads((source / "src/arm64/linux/abi/c-entry.json").read_text())[
        "source_owners"
    ].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Native C entry source owner changed: " + path)
    publication = receipt["deferred_publication"]
    for path, key in (
        (output / "PUBLICATION.json", "publication_receipt_sha256"),
        (source / "src/arm64/linux/abi/publication.json", "publication_contract_sha256"),
        (source / "tools/arm64/vm/publication.py", "publication_generator_sha256"),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("Publication input changed: " + str(path))
    for path, expected in publication["generated"].items():
        if sha(output / path) != expected:
            raise ValueError("Publication generated stream changed: " + path)
    contract = json.loads((source / "src/arm64/linux/abi/publication.json").read_text())
    for owner in (contract, publication):
        for path, expected in owner["source_owners"].items():
            if sha(source_file(source, path)) != expected:
                raise ValueError("Publication semantic owner changed: " + path)
    backports = json.loads((build / "generated/backports/BACKPORTS.json").read_text())
    for path, key in (
        (Path(backports["compiler_input"]), "compiler_input_sha256"),
        (output / "quickjs-aarch64.c", "core_sha256"),
        (output / "quickjs-interpreter-slow.h", "slow_sha256"),
        (source / "asm/arm64/linux/interpreter.S", "assembly_sha256"),
        (source / "asm/arm64/common/register-ops.inc", "common_ops_sha256"),
        (source / "asm/arm64/common/register-call.inc", "common_calls_sha256"),
        (source / "asm/arm64/common/register-slots.inc", "slots_sha256"),
        (source / "asm/arm64/common/register-references.inc", "references_sha256"),
        (source / "asm/arm64/common/register-branch.inc", "branches_sha256"),
        (source / "asm/arm64/common/register-numeric.inc", "numeric_sha256"),
        (source / "src/arm64/linux/abi/numeric.json", "numeric_contract_sha256"),
        (source / "src/arm64/linux/abi/window.json", "window_contract_sha256"),
        (source / "src/arm64/linux/abi/captures.json", "capture_contract_sha256"),
        (source / "src/arm64/linux/interpreter-policy.c", "policy_sha256"),
        (source / "src/arm64/linux/interpreter-policy.h", "policy_header_sha256"),
        (source / "src/arm64/linux/interpreter-observe.c", "observer_sha256"),
        (source / "src/arm64/linux/interpreter-observe.h", "observer_header_sha256"),
        (source / "src/common/call/interpreter-current-function.inc", "current_function_sha256"),
        (source / "src/common/call/interpreter-set-name.inc", "set_name_sha256"),
        (output / "interpreter-aarch64-shared.h", "shared_sha256"),
        (output / "interpreter-aarch64-shared-host.h", "shared_host_sha256"),
        (source / "src/common/call/quickjs-interpreter-shared.inc", "shared_source_sha256"),
        (source / "src/common/call/interpreter-shared-types.inc", "shared_types_sha256"),
        (source / "src/common/linux/interpreter-linux-shared-tls.inc", "shared_tls_sha256"),
        (
            source / "src/arm64/linux/interpreter-shared-supplements.inc",
            "shared_supplements_sha256",
        ),
        (source / "src/common/call/interpreter-slow-host.inc", "slow_host_sha256"),
        (source / "tools/common/c_extract/generate_shared_host.py", "shared_generator_sha256"),
        (source / "src/arm64/linux/abi/shared.json", "shared_contract_sha256"),
        (source / "src/arm64/linux/abi/prepared-callbacks.json", "callback_contract_sha256"),
        (source / "tools/arm64/workers/prepared_callbacks_arm64.py", "callback_generator_sha256"),
        (
            source / "src/common/linux/interpreter-linux-prepared-callback.inc",
            "callback_selector_sha256",
        ),
        (output / "quickjs-linux-c-workers.h", "async_worker_sha256"),
        (output / "ASYNC-GENERATOR.json", "async_receipt_sha256"),
        (source / "src/arm64/linux/abi/async-generator.json", "async_contract_sha256"),
        (source / "tools/common/elf/c_workers.py", "c_workers_generator_sha256"),
        (output / "quickjs-linux-json.h", "json_worker_sha256"),
        (output / "JSON-WORKERS.json", "json_receipt_sha256"),
        (source / "src/arm64/linux/abi/json.json", "json_contract_sha256"),
        (source / "tools/common/elf/json_workers.py", "json_generator_sha256"),
        (source / "tools/arm64/workers/json_worker.py", "json_arm_generator_sha256"),
        (source / "src/arm64/common/json-vector.h", "json_vector_sha256"),
        (output / "quickjs-linux-regexp.h", "regexp_worker_sha256"),
        (output / "REGEXP-WORKERS.json", "regexp_receipt_sha256"),
        (source / "src/arm64/linux/abi/regexp.json", "regexp_contract_sha256"),
        (source / "tools/arm64/workers/regexp_workers_arm64.py", "regexp_generator_sha256"),
        (source / "src/arm64/linux/abi/admission.json", "admission_contract_sha256"),
        (source / "tools/arm64/vm/admission.py", "admission_generator_sha256"),
        (source / "asm/arm64/common/register-regexp.inc", "regexp_opcode_sha256"),
        (output / "interpreter-aarch64-loop.h", "loop_sha256"),
        (output / "interpreter-aarch64-dispatch-c.inc", "c_dispatch_sha256"),
        (source / "tools/arm64/vm/prepare_vm.py", "generator_sha256"),
    ):
        if sha(path) != receipt[key]:
            raise ValueError("ARM64 VM input changed: " + str(path))
    elf = Elf64.read(image, expected_machine=183)
    if (
        sha(output / "quickjs-linux-prepared-callback.h")
        != receipt["prepared_callbacks"]["generated_sha256"]
    ):
        raise ValueError("Prepared callback generated source changed")
    contract = json.loads((source / "src/arm64/linux/abi/prepared-callbacks.json").read_text())
    for path, expected in contract["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Prepared callback source owner changed: " + path)
    async_contract = json.loads((source / "src/arm64/linux/abi/async-generator.json").read_text())
    for path, expected in async_contract["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Async generator source owner changed: " + path)
    json_contract = json.loads((source / "src/arm64/linux/abi/json.json").read_text())
    for path, expected in json_contract["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("JSON source owner changed: " + path)
    regexp_contract = json.loads((source / "src/arm64/linux/abi/regexp.json").read_text())
    for path, expected in regexp_contract["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("RegExp source owner changed: " + path)
    admission_contract = json.loads((source / "src/arm64/linux/abi/admission.json").read_text())
    for path, expected in admission_contract["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Admission source owner changed: " + path)
    for name, key in [
        ("interpreter-aarch64-admission.h", "generated_sha256"),
        ("interpreter-aarch64-regexp.h", "literal_sha256"),
    ]:
        if sha(output / name) != receipt["native_admission"][key]:
            raise ValueError("Admission/literal generated source changed: " + name)
    if (
        sha(output / "interpreter-aarch64-json-scan-test.h")
        != receipt["json_workers"]["target_detail"]["scan_fixture_sha256"]
    ):
        raise ValueError("JSON scanner fixture is not from the actual generated source")
    geometry = next(s for s in elf.symbols() if s["name"] == "qjs_aarch64_callback_abi")
    section = elf.sections[geometry["section"]]
    if geometry["size"] != 56 or section["flags"] & 1:
        raise ValueError("Actual callback geometry must be a readonly seven-word compiler record")
    callback_values = struct.unpack_from(
        "<7Q", elf.section_data(section), geometry["value"] - section["address"]
    )
    callback_geometry = dict(
        zip(
            (
                "scope_bytes",
                "scope_alignment",
                "barrier",
                "state",
                "data",
                "state_bytes",
                "frame_bytes",
            ),
            callback_values,
        )
    )
    if (
        callback_geometry["state_bytes"] != receipt["owned"]["SIZE_JSFrameRegisterState"]
        or callback_geometry["frame_bytes"] != receipt["owned"]["SIZE_JSFrame"]
    ):
        raise ValueError("Callback capsule does not use actual common ARM types")
    if elf.kind != 3:
        raise ValueError("Register VM executable must be PIE")
    symbols = {s["name"]: s for s in elf.symbols() if s["type"] == 2 and s["size"]}
    end = next(s for s in elf.symbols() if s["name"] == "qjs_aarch64_vm_end")
    vm_entry = symbols["JS_FrameInterp"]
    if vm_entry["value"] % 64:
        raise ValueError("Register VM entry must retain its 64-byte instruction alignment")
    if end["value"] != vm_entry["value"] + vm_entry["size"]:
        raise ValueError("VM unwind observation marker does not bound the real function")
    names = (
        "JS_FrameInterp",
        "JS_FrameInterpSlow",
        "JS_AArch64Step",
        "JS_FrameAArch64Return",
        "JS_FrameInterpHostDirect",
        "JS_FrameInterpHost",
        "JS_FrameAArch64FinishCall",
        "qjs_aarch64_vm_policy",
        "JS_RunFrame",
        "JS_LegacyCall",
        "JS_Call",
        "JS_FrameAArch64Run",
        "JS_FrameInterpHostDirectShared",
        "JS_FrameInterpHostShared",
        "JS_FrameCallEntryShared",
        "JS_FrameCallEntryDispatch",
        "js_frame_run_shared",
        "JS_FrameAArch64ScopeProbe",
        "JS_FrameCallbackScopeRun",
        "JS_FrameCallbackWriteScopeRun",
        "JS_FrameCallbackArrayEvery",
        "JS_FrameCallbackArrayReduce",
        "JS_FrameCallbackWriteArrayEvery",
        "JS_FrameCallbackWriteArrayReduce",
        "JS_FramePreparedCallbackSelect",
        "JS_FramePreparedCallbackWriteSelect",
        "js_linux_prepared_callback",
        "JS_FrameCallbackScopeProbe",
        "frame_callback_array_every",
        "frame_callback_array_reduce",
        "frame_callback_write_array_every",
        "frame_callback_write_array_reduce",
    )
    names += (
        "JS_GeneratorCapabilityNext",
        "JS_GeneratorCapabilityResume",
        "JS_GeneratorCapabilityReaction",
    )
    names += tuple(receipt["json_workers"]["entries"])
    names += tuple(receipt["regexp_workers"]["entries"])
    names += (
        tuple(c_entry["entries"])
        + tuple(c_entry["native_entries"])
        + tuple(c_entry["retained_entries"])
    )
    names += ("JS_FrameInterpFree",)
    if scalar["enabled"]:
        names += ("qjs_aarch64_vm_scalar_policy",)
    if call_leaves["enabled"]:
        names += ("JS_FrameAArch64CallLeaf",)
    names += tuple(varargs["entries"])
    names += tuple(strings["entries"])
    names += tuple(numeric["numeric"]["entries"]) + tuple(numeric["projection"]["entries"])
    if numeric["numeric"]["enabled"]:
        names += (
            "JS_FrameBigIntRelease",
            "JS_FrameInterpPrimitive_add",
            "JS_FrameInterpPrimitive_mul",
        )
    names += tuple(literals["entries"])
    names += tuple(indexed["entries"])
    names += tuple(forwarding["entries"])
    if forwarding["enabled"]:
        names += tuple(forwarding["captured_readonly"]["entries"])
    names += (
        tuple(array_own["entries"])
        + tuple(arrays["entries"])
        + tuple(null["entries"])
        + tuple(arguments["entries"])
    )
    names += tuple(constructors["entries"])
    names += tuple(iterators["entries"])
    names += tuple(extended["entries"])
    names += tuple(comparisons["entries"])
    names += (
        tuple(primitives["entries"])
        + tuple(own_hints["entries"])
        + tuple(proto["entries"])
        + tuple(globals_record["entries"])
    )
    names += (
        "JS_LinuxCInvokeInit",
        "JS_FrameDenseArrayPop",
        "JS_FrameDenseArrayPopState",
        "JS_FrameDensePopLeafState",
        "JS_FrameDensePopLeafCount",
        "dense_pop_initialize",
    )
    names += tuple(publication["proxies"])
    names += (
        "JS_FrameInterpRegExp",
        "js_frame_aarch64_admit",
        "JS_FrameAArch64ShortValidate",
        "JS_FrameLongValidate",
        "js_frame_large_select",
    )
    instrumented = "QJS_AARCH64_VM_INSTRUMENT:BOOL=ON" in cache_text
    if instrumented and scalar["enabled"]:
        names += ("qjs_aarch64_vm_scalar_counts",)
    if instrumented and call_leaves["enabled"]:
        names += ("qjs_aarch64_vm_call_leaf_counts",)
    if instrumented and stack_insert["enabled"]:
        names += ("qjs_aarch64_vm_stack_insert_count",)
    if instrumented and strings["enabled"]:
        names += ("qjs_aarch64_vm_string_counts",)
    if instrumented and (numeric["numeric"]["enabled"] or numeric["projection"]["enabled"]):
        names += ("qjs_aarch64_vm_numeric_counts",)
    if instrumented and literals["enabled"]:
        names += ("qjs_aarch64_vm_literal_counts",)
    if instrumented and indexed["enabled"]:
        names += ("qjs_aarch64_vm_indexed_counts",)
    if instrumented and varargs["enabled"]:
        names += ("qjs_aarch64_vm_varargs_counts",)
    if instrumented:
        names += (
            "qjs_aarch64_vm_primitive_counts",
            "qjs_aarch64_vm_store_counts",
            "qjs_aarch64_vm_global_counts",
        )
        names += ("qjs_aarch64_vm_property_counts", "qjs_aarch64_vm_opcode_counts")
        names += ("qjs_aarch64_vm_host_return_counts", "qjs_aarch64_vm_publication_extended_counts")
        names += ("qjs_aarch64_vm_c_entry", "qjs_aarch64_vm_c_entry_counts")
        names += ("qjs_aarch64_vm_publication_counts",)
        names += (
            "qjs_aarch64_vm_function_info",
            "qjs_aarch64_vm_function_code",
            "qjs_aarch64_vm_comparison_counts",
            "qjs_aarch64_vm_constructor_counts",
            "qjs_aarch64_vm_iterator_counts",
        )
        names += (
            "qjs_aarch64_json_vector_loaded",
            "qjs_aarch64_json_vector_stored",
            "qjs_aarch64_json_vector_counts",
        )
        names += ("qjs_aarch64_regexp_worker_kind",)
        names += (
            "qjs_aarch64_vm_regexp_started",
            "qjs_aarch64_vm_regexp_count",
            "qjs_aarch64_vm_quota",
        )
    frames = subprocess.check_output(
        [str(a.readelf), "-W", "--debug-dump=frames", image], text=True
    )
    spans = [
        (int(m[1], 16), int(m[2], 16))
        for m in re.finditer(r"FDE .*pc=([a-f0-9]+)\.\.([a-f0-9]+)", frames)
    ]
    code = {}
    for name in names:
        symbol = symbols[name]
        section = elf.sections[symbol["section"]]
        if section["flags"] & 6 != 6 or section["flags"] & 1:
            raise ValueError("Code is missing RX protection: " + name)
        if not any(
            lo <= symbol["value"] and symbol["value"] + symbol["size"] <= hi for lo, hi in spans
        ):
            raise ValueError("Missing complete FDE: " + name)
        code[name] = dict(address=symbol["value"], size=symbol["size"])
    # Inspect actual program headers instead of relying on source annotations.
    data = image.read_bytes()
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    stack = []
    for i in range(phnum):
        typ, flags = struct.unpack_from("<II", data, phoff + i * phsize)
        if typ == 1 and flags & 3 == 3:
            raise ValueError("Writable executable LOAD segment")
        if typ == 0x6474E551:
            stack.append(flags)
    if stack != [6]:
        raise ValueError("Expected exactly one RW/NX GNU stack")
    members = subprocess.check_output([str(a.ar), "t", str(a.archive)], text=True).splitlines()
    actual_vm = []
    for member in members:
        raw = subprocess.check_output([str(a.ar), "p", str(a.archive), member])
        obj = Elf64(raw, expected_machine=183)
        if any(s["name"] == "JS_FrameInterp" and s["section"] != 0 for s in obj.symbols()):
            actual_vm.append(dict(member=member, sha256=hashlib.sha256(raw).hexdigest()))
    if len(actual_vm) != 1:
        raise ValueError("Archive must contain exactly one AArch64 register VM definition")
    for name in (
        "qjs_aarch64_vm_completed",
        "qjs_aarch64_vm_slow_entry",
        "qjs_aarch64_vm_window_observe",
        "qjs_aarch64_vm_function_info",
        "qjs_aarch64_json_vector_loaded",
        "qjs_aarch64_json_vector_stored",
        "qjs_aarch64_json_vector_counts",
    ):
        if (name in symbols) != instrumented:
            raise ValueError("Instrumented/release image mismatch: " + name)
    if ("qjs_aarch64_regexp_worker_kind" in symbols) != instrumented:
        raise ValueError("RegExp observer must be absent in release")
    for name in (
        "qjs_aarch64_vm_regexp_started",
        "qjs_aarch64_vm_regexp_count",
        "qjs_aarch64_vm_quota",
    ):
        if (name in symbols) != instrumented:
            raise ValueError("Opcode/quota observer must be absent in release: " + name)
    result = dict(
        status="passed-aarch64-register-tier-image",
        qualification="experimental functional tier",
        image_sha256=sha(image),
        archive_sha256=sha(a.archive),
        vm_receipt_sha256=sha(output / "VM.json"),
        full_fde_coverage=code,
        archive_vm=actual_vm,
        pie=True,
        nx_stack=True,
        no_wx=True,
        instrumented=instrumented,
        native_opcodes=len(receipt["native_opcodes"]),
        native_call_return=receipt["native_call_return"],
        native_host=receipt["native_host"],
        prepared_callback_geometry=callback_geometry,
        async_generator=receipt["async_generator"],
        json_workers=receipt["json_workers"],
        regexp_workers=receipt["regexp_workers"],
        native_admission=receipt["native_admission"],
        hardware_performance_qualified=False,
    )
    objects = {s["name"]: s for s in elf.symbols() if s["type"] == 1 and s["size"]}
    geometry = objects["qjs_aarch64_c_entry_geometry"]
    section = elf.sections[geometry["section"]]
    if geometry["size"] != 14 * 8 or section["flags"] & 1:
        raise ValueError("Native C geometry must be the actual readonly14-word compiler record")
    values = struct.unpack_from(
        "<14Q", elf.section_data(section), geometry["value"] - section["address"]
    )
    if values != (
        104,
        8,
        136,
        8,
        104,
        128,
        128,
        8,
        80,
        104,
        112,
        120,
        receipt["owned"]["SIZE_JSFrameRegisterState"],
        receipt["owned"]["SIZE_JSFrame"],
    ):
        raise ValueError("Actual ARM C/frame/view geometry changed;review typed owner")
    for name in ("qjs_aarch64_vm_c_entry", "qjs_aarch64_vm_c_entry_counts"):
        if (name in symbols) != instrumented:
            raise ValueError("C entry observer must be absent in release: " + name)
    result["c_entry"] = dict(record=c_entry, actual_geometry=list(values))
    result["c_return"] = c_return
    result["properties"] = properties
    result["property_prototypes"] = proto
    for name in (
        "qjs_aarch64_vm_function_code",
        "qjs_aarch64_global_counters",
        "qjs_aarch64_vm_global_counts",
        "qjs_aarch64_store_counters",
        "qjs_aarch64_vm_store_counts",
        "qjs_aarch64_proto_counters",
        "qjs_aarch64_vm_proto_counts",
    ):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Prototype observer must be absent in release: " + name)
    for name in ("qjs_aarch64_vm_comparison_counts", "qjs_aarch64_compare_counters"):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Release comparison observer present: " + name)
    for name in ("qjs_aarch64_vm_constructor_counts", "qjs_aarch64_construct_counters"):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Constructor release observer present: " + name)
    for name in ("qjs_aarch64_iterator_counters", "qjs_aarch64_vm_iterator_counts"):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Iterator release observer present: " + name)
    for name in ("qjs_aarch64_array_own_counters", "qjs_aarch64_vm_array_own_counts"):
        if any(s["name"] == name for s in elf.symbols()) != (instrumented and array_own["enabled"]):
            raise ValueError("Array-own observation must be absent in release/OFF: " + name)
    for name in ("qjs_aarch64_forward_counters", "qjs_aarch64_vm_forward_counts"):
        if any(s["name"] == name for s in elf.symbols()) != (
            instrumented and forwarding["enabled"]
        ):
            raise ValueError("Forward release/OFF observer mismatch: " + name)
    for name in ("qjs_aarch64_vm_indexed_counts", "qjs_aarch64_indexed_counters"):
        if any(s["name"] == name for s in elf.symbols()) != (instrumented and indexed["enabled"]):
            raise ValueError("Indexed observer must be absent in release or compiled OFF: " + name)
    for name in ("qjs_aarch64_vm_literal_counts",):
        if any(s["name"] == name for s in elf.symbols()) != (instrumented and literals["enabled"]):
            raise ValueError("Literal observer must be absent in Release/compiled OFF: " + name)
    for name in ("qjs_aarch64_vm_numeric_counts", "qjs_aarch64_numeric_counters"):
        if any(s["name"] == name for s in elf.symbols()) != (
            instrumented and (numeric["numeric"]["enabled"] or numeric["projection"]["enabled"])
        ):
            raise ValueError("Numeric observer must be absent in Release/whole OFF: " + name)
    for name in ("qjs_aarch64_vm_string_counts", "qjs_aarch64_string_counters"):
        if any(s["name"] == name for s in elf.symbols()) != (instrumented and strings["enabled"]):
            raise ValueError("Release/OFF string observer present: " + name)
    for name in ("qjs_aarch64_vm_stack_insert_count", "qjs_aarch64_stack_insert_counter"):
        if any(s["name"] == name for s in elf.symbols()) != (
            instrumented and stack_insert["enabled"]
        ):
            raise ValueError("Release/OFF stack observer present: " + name)
    result["stack_insert"] = stack_insert
    result["call_leaves"] = call_leaves
    result["scalar_ops"] = scalar
    for name in ("qjs_aarch64_vm_scalar_counts", "qjs_aarch64_scalar_counters"):
        if any(s["name"] == name for s in elf.symbols()) != (instrumented and scalar["enabled"]):
            raise ValueError("Release/OFF scalar observer present: " + name)
    for name in ("qjs_aarch64_vm_scalar_policy", "scalar_mode"):
        if any(s["name"] == name for s in elf.symbols()) != scalar["enabled"]:
            raise ValueError("CompiledOFF scalar policy present: " + name)
    for name in ("qjs_aarch64_vm_call_leaf_counts", "qjs_aarch64_call_leaf_counters"):
        if any(s["name"] == name for s in elf.symbols()) != (
            instrumented and call_leaves["enabled"]
        ):
            raise ValueError("Release/OFF leaf observer present: " + name)
    result["strings"] = strings
    result["numeric_workers"] = numeric
    result["literals"] = literals
    result["indexed"] = indexed
    result["forwarding"] = forwarding
    result["array_own"] = array_own
    result["iterators"] = iterators
    result["extended_calls"] = extended
    result["constructors"] = constructors
    result["comparisons"] = comparisons
    result["global_bindings"] = globals_record
    result["reference_stores"] = stores
    result["property_hints"] = own_hints
    for name in (
        "qjs_aarch64_hint_counters",
        "qjs_aarch64_vm_hint_counts",
        "qjs_aarch64_vm_own_allocation_counts",
    ):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Own-tail observer must be absent in release: " + name)
    result["property_primitives"] = primitives
    if (
        receipt["deferred_publication"]["nonobserving_helpers"]
        != primitives["pure_nonobserving_helpers"]
        + proto["pure_nonobserving_helpers"]
        + (["JS_FrameAArch64CallLeaf"] if call_leaves["enabled"] else [])
        + indexed["pure_nonobserving_helpers"]
        + globals_record["pure_nonobserving_helpers"]
        + comparisons["pure_nonobserving_helpers"]
    ):
        raise ValueError(
            "Pure property helper must retain its explicit nonobserving classification"
        )
    for name in ("qjs_aarch64_vm_primitive_counts", "qjs_aarch64_primitive_counters"):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Primitive property observer must be absent in release: " + name)
    for name in (
        "qjs_aarch64_vm_property_counts",
        "qjs_aarch64_property_counters",
        "qjs_aarch64_vm_opcode_counts",
    ):
        if any(s["name"] == name for s in elf.symbols()) != instrumented:
            raise ValueError("Native property observer must be absent in release: " + name)
    for name in (
        "qjs_aarch64_vm_host_return_counts",
        "qjs_aarch64_vm_publication_extended_counts",
        "qjs_aarch64_host_return_counters",
    ):
        present = any(s["name"] == name for s in elf.symbols())
        if present != instrumented:
            raise ValueError("Host return observer must be absent in release: " + name)
    if instrumented:
        tls = next(s for s in elf.symbols() if s["name"] == "qjs_aarch64_publish_counters")
        if (
            tls["size"] != 17 * 8
            or publication["instrument_counter_words"] != 17
            or publication["original_reader_words"] != 16
        ):
            raise ValueError("Extended C-free publication counter must preserve old16-word reader")
    tables = {}
    table_protections = {}
    vm = symbols["JS_FrameInterp"]
    for name in ["qjs_aarch64_publish_original", *publication["tables"]]:
        symbol = objects[name]
        section = elf.sections[symbol["section"]]
        if symbol["size"] != 1024 or section["flags"] & 1 or section["flags"] & 4:
            raise ValueError("Dispatch must be1024 readonly non-executable relative bytes: " + name)
        loads = []
        for i in range(phnum):
            typ, flags, offset, address, physical, filesz, memsz, alignment = struct.unpack_from(
                "<IIQQQQQQ", elf.data, phoff + i * phsize
            )
            if (
                typ == 1
                and address <= symbol["value"]
                and symbol["value"] + 1024 <= address + filesz
            ):
                loads.append(flags)
        # GNU AArch64 ld may share immutable .rodata with the R-X text LOAD.
        # The original protocol requires read-only tables,not an NX data page.
        # Keep the actual default linker layout;reject missing/overlapping/W
        # mappings and report execute permission rather than assuming R--.
        if len(loads) != 1 or loads[0] not in (4, 5):
            raise ValueError("Dispatch must occupy exactly one read-only LOAD: " + name)
        table_protections[name] = dict(
            readonly=True, executable=bool(loads[0] & 1), load_flags=loads[0]
        )
        for relocations in elf.sections:
            if relocations["type"] != 4:
                continue
            raw = elf.section_data(relocations)
            if len(raw) % 24:
                raise ValueError("Changed ELF64 RELA extent")
            for offset in range(0, len(raw), 24):
                target, info, addend = struct.unpack_from("<QQq", raw, offset)
                if symbol["value"] <= target < symbol["value"] + 1024:
                    raise ValueError("Relative dispatch must need no dynamic relocation: " + name)
        data = elf.section_data(section)[symbol["value"] - section["address"] :][:1024]
        targets = [symbol["value"] + delta for delta in struct.unpack("<256i", data)]
        if any(
            target % 4 or not vm["value"] <= target < vm["value"] + vm["size"] for target in targets
        ):
            raise ValueError("Relative dispatch escaped current VM FDE: " + name)
        tables[name] = targets
    if (
        sum(
            a != b
            for a, b in zip(
                tables["qjs_aarch64_publish_original"], tables[publication["tables"][0]]
            )
        )
        != 10
    ):
        raise ValueError("Clean table must override exactly eight call/two returns")
    for name in ("qjs_aarch64_publish_counters", "qjs_aarch64_vm_publication_counts"):
        present = any(s["name"] == name for s in elf.symbols())
        if present != instrumented:
            raise ValueError("Publication observer must be absent in release: " + name)
    result["deferred_publication"] = dict(
        record=publication, tables=tables, table_protections=table_protections
    )
    (output / "CHECK.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "AARCH64_VM_ELF_OK native_opcodes="
        + str(result["native_opcodes"])
        + " full-FDE PIE NX no-WX instrumented="
        + str(instrumented)
    )


if __name__ == "__main__":
    main()
