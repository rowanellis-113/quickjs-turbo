import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, source_file, upstream_root

_act_x86()

"""Bind a normally linked CMake Linux image to its actual generated inputs."""

import argparse
import hashlib
import json
import re
from pathlib import Path
import shlex
import subprocess
from elf64 import Elf64
from control_flow import read_property


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    a = ap.parse_args()
    source, build, binary, archive = [p.resolve() for p in (a.source, a.build, a.binary, a.archive)]
    generated = build / "generated/linux-native"
    prepare = json.loads((generated / "PREPARE.json").read_text())
    vm = json.loads((generated / "VM.json").read_text())
    if (
        sha(generated / "quickjs-linux-foundation.c") != prepare["generated_source_sha256"]
        or sha(generated / "quickjs-linux-vm.S") != vm["assembly_sha256"]
    ):
        raise ValueError("Generated native inputs changed")
    if sha(generated / "quickjs-linux-bridges.S") != prepare["bridges_assembly_sha256"]:
        raise ValueError("Generated native bridges changed")
    if sha(generated / "quickjs-interpreter-slow.h") != prepare["slow_header_sha256"]:
        raise ValueError("Generated C-step boundary changed")
    vm_leaves = json.loads((generated / "VM-LEAVES.json").read_text())
    if vm_leaves != vm.get("native_vm_leaves"):
        raise ValueError("Native VM leaf receipt differs from generated stream")
    if (
        sha(source_file(source, vm_leaves["source"])) != vm_leaves["source_sha256"]
        or sha(source / "src/x86/linux/interpreter-vm-leaf.inc") != vm_leaves["policy_sha256"]
    ):
        raise ValueError("Shared VM leaf owner/policy changed")
    for name, digest in prepare.get("c_workers", {}).items():
        if sha(generated / name) != digest:
            raise ValueError("Generated source-owned C worker changed: " + name)
    slots = vm.get("native_slots")
    if slots:
        for name, digest in {
            slots["owner"]: slots["owner_sha256"],
            **slots["source_files"],
        }.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Native slot source owner changed: " + name)
        if slots["new_frame_bytes"] or slots["new_public_or_runtime_fields"]:
            raise ValueError("Unexpected native slot ABI growth")
    elf = Elf64.read(binary)
    symbols = {s["name"]: s for s in elf.symbols() if s["type"] == 2 and s["size"]}
    required = [
        vm["private_entry"],
        *vm["helper_mapping"].values(),
        *vm.get("extra_native_functions", []),
        *vm.get("extra_vm_functions", []),
        *vm.get("returning_forward_functions", []),
    ]
    string_entry = (vm.get("string_contract") or {}).get("native_index_entry")
    if string_entry:
        for name, digest in string_entry["owners"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Native string-index source/route owner changed: " + name)
    worker_entries = []
    worker_indirect = []
    json_workers = {}
    string_workers = {}
    array_workers = {}
    builtin_workers = {}
    regexp_workers = {}
    js_calls = {}
    forwarding = {}
    entries = {}
    construct = {}
    arguments = {}
    virtual_arguments = {}
    if vm.get("native_arguments"):
        arguments = json.loads((generated / "ARGUMENTS.json").read_text())
        if json.loads((generated / "ARGUMENTS-VM.json").read_text()) != vm["native_arguments"]:
            raise ValueError("Argument native receipt differs from actual stream")
        for name, digest in {**arguments["owners"], **arguments["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Argument algorithm/platform owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-arguments.h") != arguments["generated_sha256"]
            or sha(generated / "quickjs-interpreter-slow.h") != arguments["slow_sha256"]
        ):
            raise ValueError("Argument worker/constructor routing changed")
        worker_entries += arguments["entries"]
        required += arguments["entries"]
        virtual_arguments = json.loads((generated / "VIRTUAL-ARGUMENTS.json").read_text())
        for name, digest in virtual_arguments["source_files"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Independent forwarding source owner changed: " + name)
        if (
            virtual_arguments["actual_input_sha256"] != prepare["compiler_input_sha256"]
            or sha(generated / "quickjs-linux-virtual-arguments-private.h")
            != virtual_arguments["private_sha256"]
            or sha(generated / "quickjs-linux-virtual-arguments.c")
            != virtual_arguments["worker_sha256"]
        ):
            raise ValueError("Independent forwarding actual input/types/body changed")
        if any(virtual_arguments[n] for n in ("frame_growth", "state_growth", "new_roots")):
            raise ValueError("Unexpected independent forwarding ABI growth")
        section = next(s for s in elf.sections if s["name"] == virtual_arguments["text_section"])
        if section["flags"] & 6 != 6 or section["flags"] & 1:
            raise ValueError(
                "Independent forwarding code must be allocated executable and nonwritable"
            )
        private_entries = [
            s["name"]
            for s in elf.symbols()
            if s["type"] == 2 and s["size"] and s["section"] == section["index"]
        ]
        if virtual_arguments["entry"] not in private_entries:
            raise ValueError("Missing independent forwarding entry")
        private_entries += ["JS_LinuxVirtualArgumentsPush"]
        worker_entries += private_entries
        required += private_entries
        frames = subprocess.check_output(
            ["readelf", "-W", "--debug-dump=frames", str(binary)], text=True
        )
        spans = [
            (int(m[1], 16), int(m[2], 16))
            for m in re.finditer(r"FDE .*pc=([0-9a-f]+)\.\.([0-9a-f]+)", frames)
        ]
        for name in private_entries:
            symbol = symbols[name]
            if not any(
                lo <= symbol["value"] and symbol["value"] + symbol["size"] <= hi for lo, hi in spans
            ):
                raise ValueError("Missing complete independent forwarding FDE: " + name)
        virtual_arguments["qualified_FDE_entries"] = private_entries
    iterators = {}
    if vm.get("native_iterators"):
        iterators = json.loads((generated / "ITERATORS.json").read_text())
        if json.loads((generated / "ITERATORS-VM.json").read_text()) != vm["native_iterators"]:
            raise ValueError("Iterator native receipt differs from actual stream")
        for name, digest in iterators["owners"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Iterator algorithm owner changed: " + name)
        if (
            sha(source_file(source, iterators["platform_source"])) != iterators["platform_sha256"]
            or sha(generated / "quickjs-linux-construct.h") != iterators["generated_sha256"]
            or sha(generated / "quickjs-linux-construct-host.h") != iterators["host_sha256"]
        ):
            raise ValueError("Iterator platform or complete semantic owner changed")
        worker_entries += iterators["entries"]
        required += iterators["entries"]
    varargs = {}
    if vm.get("native_varargs"):
        varargs = json.loads((generated / "VARARGS.json").read_text())
        if json.loads((generated / "VARARGS-VM.json").read_text()) != vm["native_varargs"]:
            raise ValueError("Varargs native receipt differs from actual stream")
        for name, digest in {**varargs["owners"], **varargs["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Varargs algorithm/platform owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-varargs.h") != varargs["generated_sha256"]
            or sha(generated / "quickjs-linux-construct.h") != varargs["slow_sha256"]
        ):
            raise ValueError("Varargs worker/owned-copy2/fusion routing changed")
        worker_entries += varargs["entries"]
        required += varargs["entries"]
    literals = {}
    if vm.get("native_literals"):
        literals = json.loads((generated / "LITERALS.json").read_text())
        if json.loads((generated / "LITERALS-VM.json").read_text()) != vm["native_literals"]:
            raise ValueError("Literal native receipt differs from actual stream")
        for name, digest in {**literals["owners"], **literals["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Literal algorithm/platform owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-literals.h") != literals["generated_sha256"]
            or sha(generated / "quickjs-linux-construct.h") != literals["slow_sha256"]
        ):
            raise ValueError("Literal worker/base-selector routing changed")
        worker_entries += literals["entries"]
        required += literals["entries"]
    indexed = {}
    if vm.get("native_indexed"):
        indexed = json.loads((generated / "INDEXED.json").read_text())
        if json.loads((generated / "INDEXED-VM.json").read_text()) != vm["native_indexed"]:
            raise ValueError("Indexed native receipt differs from actual stream")
        for name, digest in {**indexed["owners"], **indexed["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Indexed owner changed: " + name)
        if sha(generated / "quickjs-linux-indexed.h") != indexed["generated_sha256"]:
            raise ValueError("Indexed semantic owner changed")
        worker_entries += indexed["entries"]
        required += indexed["entries"]
        worker_entries += ["JS_LinuxFastArrayOwnFallback"]
        required += ["JS_LinuxFastArrayOwnFallback"]
    properties = {}
    if vm.get("native_properties"):
        properties = json.loads((generated / "PROPERTIES.json").read_text())
        if json.loads((generated / "PROPERTIES-VM.json").read_text()) != vm["native_properties"]:
            raise ValueError("Complete property native receipt differs from actual stream")
        for name, digest in {**properties["owners"], **properties["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("GNU property owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-properties.h") != properties["generated_sha256"]
            or sha(generated / "quickjs-linux-property-wire.h") != properties["wire_sha256"]
        ):
            raise ValueError("Property producer/reader/semantic owner changed")
        worker_entries += properties["entries"]
        required += properties["entries"]
    comparisons = {}
    if vm.get("native_comparisons"):
        comparisons = json.loads((generated / "COMPARISONS.json").read_text())
        if json.loads((generated / "COMPARISONS-VM.json").read_text()) != vm["native_comparisons"]:
            raise ValueError("Comparison native receipt differs from actual stream")
        for name, digest in {**comparisons["owners"], **comparisons["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Comparison semantic owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-comparisons.h") != comparisons["generated_sha256"]
            or sha(generated / "quickjs-interpreter-slow.h") != comparisons["slow_sha256"]
        ):
            raise ValueError("Comparison core/typed slow routing changed")
        worker_entries += comparisons["entries"]
        required += comparisons["entries"]
    numeric_workers = {}
    compiler_projection = {}
    if vm.get("native_numeric"):
        numeric_workers = json.loads((generated / "NUMERIC.json").read_text())
        if json.loads((generated / "NUMERIC-VM.json").read_text()) != vm["native_numeric"]:
            raise ValueError("Numeric native receipt differs from actual stream")
        compiler_projection = json.loads((generated / "COMPILER-PROJECTION.json").read_text())
        for record in (numeric_workers, compiler_projection):
            for name, digest in {**record["owners"], **record["source_files"]}.items():
                if sha(source_file(source, name)) != digest:
                    raise ValueError("Numeric/compiler source owner changed: " + name)
            worker_entries += record["entries"]
            required += record["entries"]
        paths = {
            "quickjs-linux-numeric.h": numeric_workers["generated_sha256"],
            "quickjs-linux-bigint.h": numeric_workers["primitive_sha256"],
            "quickjs-linux-atod.c": numeric_workers["decimal_sha256"],
            "quickjs-linux-loop.h": numeric_workers["loop_after_sha256"],
            "quickjs-linux-compiler-projection.c": compiler_projection["generated_sha256"],
            "quickjs-linux-compiler-private.h": compiler_projection["private_sha256"],
        }
        for name, digest in paths.items():
            if sha(generated / name) != digest:
                raise ValueError("Generated numeric/compiler source changed: " + name)
    global_bindings = {}
    if vm.get("native_global_bindings"):
        global_bindings = json.loads((generated / "GLOBAL-BINDINGS.json").read_text())
        native_global = json.loads((generated / "GLOBAL-BINDINGS-VM.json").read_text())
        if native_global != vm["native_global_bindings"]:
            raise ValueError("Shared global VM receipt differs from current stream")
        for name, digest in {
            **global_bindings["owners"],
            **global_bindings["source_files"],
        }.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Global semantic/platform owner changed: " + name)
        if (
            sha(generated / "quickjs-linux-global-bindings.h")
            != global_bindings["generated_sha256"]
        ):
            raise ValueError("Global typed control differs from its generated receipt")
        worker_entries += global_bindings["entries"]
        required += global_bindings["entries"]
    null_proto = {}
    if vm.get("native_null_proto"):
        null_proto = json.loads((generated / "NULL-PROTO.json").read_text())
        if json.loads((generated / "NULL-PROTO-VM.json").read_text()) != vm["native_null_proto"]:
            raise ValueError("Native null-prototype stream changed")
        for name, digest in {**null_proto["owners"], **null_proto["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Null-prototype source changed: " + name)
        if (
            sha(generated / "quickjs-linux-null-proto.h") != null_proto["generated_sha256"]
            or sha(generated / "quickjs-linux-admission.h") != null_proto["admission_sha256"]
        ):
            raise ValueError("Null allocator/classifier changed")
        worker_entries += null_proto["entries"]
        required += null_proto["entries"]
    publication = {}
    if vm.get("native_publication"):
        publication = json.loads((generated / "PUBLICATION.json").read_text())
        if publication != vm["native_publication"]:
            raise ValueError("Deferred publication receipt differs from actual VM stream")
        for name, digest in publication["source_files"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Deferred publication shared/platform owner changed: " + name)
        worker_entries += ["JS_LinuxPublishInit"]
        required += ["JS_LinuxPublishInit"]
    if vm.get("native_construct"):
        construct = json.loads((generated / "CONSTRUCT.json").read_text())
        if (
            sha(generated / "quickjs-linux-construct.h") != construct["generated_sha256"]
            or sha(generated / "quickjs-linux-construct-dispatch.h") != construct["dispatch_sha256"]
            or sha(generated / "quickjs-linux-construct-host.h") != construct["host_sha256"]
        ):
            raise ValueError("Complete constructor semantic owner/dispatch changed")
        for name, digest in construct["source_files"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Shared constructor/cleanup owner changed: " + name)
        worker_entries += construct["entries"]
        required += construct["entries"]
    if vm.get("native_entries"):
        entries = json.loads((generated / "ENTRIES.json").read_text())
        if (
            entries != vm["native_entries"]
            or sha(generated / "quickjs-linux-entry.S") != entries["assembly_sha256"]
        ):
            raise ValueError("Native SysV entries changed after generation")
        for name, digest in entries["shared_owners"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Native entry shared owner changed: " + name)
        required += entries["functions"]
        entry_workers = [
            "JS_LinuxEntryInit",
            "JS_LinuxEntrySlot",
            "JS_LinuxEntryPoll",
            "JS_LinuxEntryOverflow",
        ]
        required += entry_workers
        worker_entries += entry_workers
    if prepare.get("c_workers"):
        worker_entries += [
            "JS_GeneratorCapabilityNext",
            "JS_GeneratorCapabilityResume",
            "JS_GeneratorCapabilityReaction",
            "JS_FrameCallbackArrayEvery",
            "JS_FrameCallbackArrayReduce",
            "JS_FrameCallbackWriteArrayEvery",
            "JS_FrameCallbackWriteArrayReduce",
            "JS_FrameCallbackScopeRun",
            "JS_FrameCallbackWriteScopeRun",
            "JS_FramePreparedCallbackSelect",
            "JS_FramePreparedCallbackWriteSelect",
        ]
        required += worker_entries
        # GCC may omit ENDBR on a static function whose callers are all direct.
        # Require it at the actual method-table/CData/loop-pointer targets,
        # not at unrelated direct-only C helpers such as capability Resume.
        worker_indirect = [
            "JS_GeneratorCapabilityNext",
            "JS_GeneratorCapabilityReaction",
            "JS_FrameCallbackWriteArrayEvery",
            "JS_FrameCallbackWriteArrayReduce",
            "JS_FrameCallbackArrayEvery",
            "JS_FrameCallbackArrayReduce",
            "frame_callback_array_every",
            "frame_callback_array_reduce",
            "frame_callback_write_array_every",
            "frame_callback_write_array_reduce",
        ]
        json_workers = json.loads((generated / "JSON-WORKERS.json").read_text())
        if sha(generated / "quickjs-linux-json.h") != json_workers["generated_sha256"]:
            raise ValueError("JSON worker body differs from its receipt")
        worker_entries += json_workers["entries"]
        required += json_workers["entries"]
        worker_indirect += ["JS_FrameJSONParse", "JS_FrameJSONStringify"]
        string_workers = json.loads((generated / "STRING-WORKERS.json").read_text())
        if sha(generated / "quickjs-linux-strings.h") != string_workers["generated_sha256"]:
            raise ValueError("String worker body differs from its receipt")
        worker_entries += string_workers["entries"]
        required += string_workers["entries"]
        worker_indirect += ["JS_FrameLocaleCompare"]
        array_workers = json.loads((generated / "ARRAY-WORKERS.json").read_text())
        if sha(generated / "quickjs-linux-arrays.h") != array_workers["generated_sha256"]:
            raise ValueError("Array worker body differs from its receipt")
        worker_entries += array_workers["entries"]
        required += array_workers["entries"]
        worker_indirect += [
            "JS_FrameCachedArraySort",
            "JS_FrameDenseArrayPop",
            "JS_FramePreparedSortCompare",
        ]
        builtin_workers = json.loads((generated / "BUILTIN-WORKERS.json").read_text())
        if sha(generated / "quickjs-linux-builtin.h") != builtin_workers["generated_sha256"]:
            raise ValueError("Builtin semantic body differs from its receipt")
        worker_entries += builtin_workers["entries"]
        required += builtin_workers["entries"]
        regexp_workers = json.loads((generated / "REGEXP-WORKERS.json").read_text())
        if sha(generated / "quickjs-linux-regexp.h") != regexp_workers["generated_sha256"]:
            raise ValueError("RegExp semantic workers differ from actual source")
        for name, digest in {**regexp_workers["owners"], **regexp_workers["source_files"]}.items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("RegExp worker owner changed: " + name)
        for row in (regexp_workers["shared_original_exec"], regexp_workers["shared_original_test"]):
            if sha(Path(row["path"])) != row["sha256"]:
                raise ValueError("Shared RegExp intrinsic owner changed")
        worker_entries += regexp_workers["entries"]
        required += regexp_workers["entries"]
        worker_indirect += list(regexp_workers["builtin_routes"].values())
        js_calls = json.loads((generated / "JS-CALLS.json").read_text())
        if sha(generated / "quickjs-linux-captured-proof.h") != js_calls["proof_sha256"]:
            raise ValueError("Readonly capture proof differs from its shared source receipt")
        if sha(generated / "quickjs-linux-set-name.h") != js_calls["set_name_sha256"]:
            raise ValueError("set_name step differs from its shared source receipt")
        js_entries = js_calls["entries"] + (["JS_LinuxJSFrameProbe"] if vm["shared_entry"] else [])
        worker_entries += js_entries
        required += js_entries
        forwarding = json.loads((generated / "FORWARDING.json").read_text())
        if sha(generated / "quickjs-linux-forward.h") != forwarding["generated_sha256"]:
            raise ValueError("Forward algorithms differ from their shared source receipt")
        for name, digest in forwarding["source_files"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Forward shared owner changed: " + name)
        worker_entries += forwarding["entries"]
        required += forwarding["entries"]
    if elf.kind != 3 or any(name not in symbols for name in required):
        raise ValueError("Expected the actually linked PIE native backend")
    commands = json.loads((build / "compile_commands.json").read_text())
    cet = vm["compiler_cet"]
    object_properties = {}
    object_names = ["quickjs-linux-foundation.c", "quickjs-linux-vm.S", "quickjs-linux-bridges.S"]
    if virtual_arguments:
        object_names.append("quickjs-linux-virtual-arguments.c")
    if entries:
        object_names.append("quickjs-linux-entry.S")
    if vm.get("native_numeric"):
        object_names += ["quickjs-linux-atod.c", "quickjs-linux-compiler-projection.c"]
    for name in object_names:
        command = next(c for c in commands if Path(c["file"]).resolve() == generated / name)
        argv = shlex.split(command["command"])
        obj = Path(command["directory"]) / argv[argv.index("-o") + 1]
        actual_cet = read_property(Elf64.read(obj))
        if actual_cet != cet:
            raise ValueError(
                "Native object CET profile differs from measured compiler: " + str(obj)
            )
        object_properties[name] = dict(cet=actual_cet, sha256=sha(obj))
    if cet & 1:
        all_symbols = {s["name"]: s for s in elf.symbols()}
        direct_only = set(vm.get("direct_only_vm_functions", []))
        if not direct_only.issubset(vm.get("extra_vm_functions", [])) or direct_only.intersection(
            vm["indirect_destinations"]
        ):
            raise ValueError("Invalid direct-only VM entry classification")
        for name in [
            *(n for n in required if n not in worker_entries and n not in direct_only),
            *vm["indirect_destinations"],
            *worker_indirect,
        ]:
            symbol = all_symbols[name]
            section = elf.sections[symbol["section"]]
            offset = symbol["value"] - section["address"]
            if elf.section_data(section)[offset : offset + 4] != b"\xf3\x0f\x1e\xfa":
                raise ValueError("Native indirect destination lacks ENDBR64: " + name)
    actual = subprocess.run(
        ["readelf", "-W", "-l", "-d", binary], capture_output=True, text=True, check=True
    )
    if actual.stderr or "TEXTREL" in actual.stdout:
        raise ValueError("Unexpected ELF diagnostic/text relocation")
    (build / "native-elf.txt").write_text(actual.stdout)
    record = dict(
        status="built-normal-CMake-native-development-backend",
        register_vm=True,
        internal_quota=True,
        internal_entry_routed=True,
        source=str(source),
        binary_sha256=sha(binary),
        archive_sha256=sha(archive),
        backend="LINUX_X86_64",
        PIE=True,
        prepare_sha256=sha(generated / "PREPARE.json"),
        compiler_cet=cet,
        native_object_properties=object_properties,
        linked_cet_property=read_property(elf),
        vm_sha256=sha(generated / "VM.json"),
        compile_commands_sha256=sha(build / "compile_commands.json"),
        c_workers=prepare.get("c_workers", {}),
        c_worker_entries=worker_entries,
        c_worker_indirect_targets=worker_indirect,
        json_workers=json_workers,
        string_workers=string_workers,
        array_workers=array_workers,
        builtin_workers=builtin_workers,
        regexp_workers=regexp_workers,
        js_calls=js_calls,
        forwarding=forwarding,
        native_entries=entries,
        native_vm_leaves=vm_leaves,
        native_construct=construct,
        native_publication=publication,
        native_arguments=arguments,
        native_virtual_arguments=virtual_arguments,
        native_null_proto=null_proto,
        native_iterators=iterators,
        native_varargs=varargs,
        native_literals=literals,
        native_indexed=indexed,
        native_properties=properties,
        native_comparisons=comparisons,
        native_numeric=numeric_workers,
        compiler_projection=compiler_projection,
        native_global_bindings=global_bindings,
        native_string_entry=string_entry,
        layout=str(build / "generated/linux-abi/layout.json"),
        layout_sha256=sha(build / "generated/linux-abi/layout.json"),
        source_binding="Actual generated inputs, compile commands and binary are bound; source package sealing is separate",
        scope="Normal native build, with complete mechanism/release qualification still in progress",
    )
    git_root = upstream_root(source)
    git = subprocess.run(
        ["git", "-C", git_root, "rev-parse", "--show-toplevel"], text=True, capture_output=True
    )
    if git.returncode == 0 and Path(git.stdout.strip()).resolve() in {
        source.resolve(),
        git_root.resolve(),
    }:
        record["source_commit"] = subprocess.check_output(
            ["git", "-C", git_root, "rev-parse", "HEAD"], text=True
        ).strip()
        record["source_dirty"] = subprocess.check_output(
            ["git", "-C", git_root, "status", "--porcelain"], text=True
        )
    (build / "BUILD.json").write_text(json.dumps(record, indent=2) + "\n")
    print("LINUX NATIVE CMAKE IMAGE BOUND", binary)


if __name__ == "__main__":
    main()
