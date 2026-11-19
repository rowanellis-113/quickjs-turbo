"""Build policy, source epochs and ordinary COFF unwind regression checks.

Run: python -B tests/x86/win64/test_vm_build.py --cmake /path/to/cmake
Platform-policy cases do not claim to execute code on their simulated OS/CPU.
"""

# Shared source/tool/artifact addressing for this backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_sys.path.insert(0, str(_FramePath(__file__).resolve().parents[3] / "tools"))
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import native_build as B
import native_epoch as E
import standard_unwind as U
import archive_stage as F

restart_spec = importlib.util.spec_from_file_location(
    "frame_restart", _frame_tool_path("adapter-restart")
)
R = importlib.util.module_from_spec(restart_spec)
restart_spec.loader.exec_module(R)

extension_spec = importlib.util.spec_from_file_location(
    "frame_extension", _frame_tool_path("extension-section")
)
S = importlib.util.module_from_spec(extension_spec)
extension_spec.loader.exec_module(S)

CMAKE = shutil.which("cmake")
if "--cmake" in sys.argv:
    at = sys.argv.index("--cmake")
    CMAKE = sys.argv[at + 1]
    del sys.argv[at : at + 2]


def mini_coff(with_chain=False):
    unwind = b"\x01\0\0\0"
    if with_chain:
        unwind += b"\x21\0\0\0" + struct.pack("<III", 0, 1, 0)
    sections = [
        (".text", b"\x90\xc3", 0x60300020),
        (".xdata", unwind, 0x40300040),
        (".qjscfi", struct.pack("<III", 0, 2, 4 if with_chain else 0) * 2, 0x40300040),
    ]
    result = bytearray(20 + 40 * len(sections))
    for i, (name, data, flags) in enumerate(sections):
        pos = len(result)
        result += data
        fields = (
            list(range(0, 24, 4))
            if i == 2
            else list(range(8, 20, 4))
            if i == 1 and with_chain
            else []
        )
        reloc = len(result) if fields else 0
        count = len(fields)
        if count:
            for offset in fields:
                is_unwind = offset % 12 == 8 if i == 2 else offset == 16
                result += struct.pack("<IIH", offset, 1 if is_unwind else 0, 3)
        struct.pack_into(
            "<8sIIIIIIHHI",
            result,
            20 + i * 40,
            name.encode().ljust(8, b"\0"),
            0,
            0,
            len(data),
            pos,
            reloc,
            0,
            count,
            0,
            flags,
        )
    table = len(result)
    for section, name in ((1, ".text"), (2, ".xdata")):
        result += struct.pack("<8sIhHBB", name.encode().ljust(8, b"\0"), 0, section, 0, 3, 0)
    result += struct.pack("<I", 4)
    struct.pack_into("<HHIIIHH", result, 0, 0x8664, 3, 0, table, 2, 0, 0)
    return bytes(result)


class BuildContracts(unittest.TestCase):
    def receipt_outputs(self, toolchain, shared, files, include_products=True):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is required for the Windows build wrapper")
        with tempfile.TemporaryDirectory(prefix="frame receipt space ") as directory:
            build = Path(directory)
            for name in files:
                (build / name).write_bytes(("artifact:" + name).encode())
            script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $env:FRAME_FIXTURE_SOURCE 'tools/x86/win64/build/build-interpreter.ps1'),[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw $parseErrors[0]}
$function=$ast.Find({param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-FrameBuildOutputs'
},$true)
if(!$function){throw 'Artifact collector missing'}
. ([scriptblock]::Create($function.Extent.Text))
$result=Get-FrameBuildOutputs -BuildDirectory $env:FRAME_FIXTURE_DIRECTORY `
    -Toolchain $env:FRAME_FIXTURE_TOOLCHAIN -Shared:($env:FRAME_FIXTURE_SHARED -eq '1') `
    -IncludeProducts:($env:FRAME_FIXTURE_PRODUCTS -eq '1')
$result | ConvertTo-Json
"""
            environment = dict(
                os.environ,
                FRAME_FIXTURE_SOURCE=str(ROOT),
                FRAME_FIXTURE_DIRECTORY=str(build),
                FRAME_FIXTURE_TOOLCHAIN=toolchain,
                FRAME_FIXTURE_SHARED="1" if shared else "0",
                FRAME_FIXTURE_PRODUCTS="1" if include_products else "0",
            )
            return subprocess.run(
                [powershell, "-NoProfile", "-Command", script],
                env=environment,
                capture_output=True,
                text=True,
            )

    def test_receipt_seals_shared_dll_and_import_library(self):
        import hashlib

        for tc, dll, library in [
            ("mingw", "libqjs.dll", "libqjs.dll.a"),
            ("msvc", "qjs.dll", "qjs.lib"),
        ]:
            with self.subTest(toolchain=tc):
                result = self.receipt_outputs(tc, True, [dll, library, "qjs.exe", "qjsc.exe"])
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs = json.loads(result.stdout)
                for name in [dll, library, "qjs.exe", "qjsc.exe"]:
                    self.assertEqual(
                        outputs[name], hashlib.sha256(("artifact:" + name).encode()).hexdigest()
                    )

    def test_receipt_does_not_claim_stale_dll_or_configure_only_products(self):
        for tc, library in [("mingw", "libqjs.a"), ("msvc", "qjs.lib")]:
            files = [library, "qjs.exe", "qjs.dll", "libqjs.dll", "libqjs.dll.a", "CMakeCache.txt"]
            result = self.receipt_outputs(tc, False, files)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = json.loads(result.stdout)
            self.assertIn(library, outputs)
            self.assertNotIn("qjs.dll", outputs)
            self.assertNotIn("libqjs.dll", outputs)
            self.assertNotIn("libqjs.dll.a", outputs)
            configured = self.receipt_outputs(tc, True, files, False)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            self.assertEqual(set(json.loads(configured.stdout)), {"CMakeCache.txt"})

    def test_receipt_rejects_missing_shared_dll(self):
        for tc, library, dll in [
            ("mingw", "libqjs.dll.a", "libqjs.dll"),
            ("msvc", "qjs.lib", "qjs.dll"),
        ]:
            result = self.receipt_outputs(tc, True, [library])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Required engine artifact missing: " + dll, result.stderr)

    def test_extension_identity_retains_and_checks_producer_evidence(self):
        with tempfile.TemporaryDirectory(prefix="frame extension ") as directory:
            path = Path(directory) / "producer.obj"
            raw = bytearray(mini_coff())
            raw[20:28] = b".qjsprop"
            struct.pack_into("<I", raw, 20 + 36, 0x60300040)
            path.write_bytes(raw)
            S.adapt(path)
            backup = path.with_name(path.name + ".before-extension")
            receipt = path.with_name(path.name + ".extension.json")
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(backup.read_bytes(), raw)
            record = json.loads(receipt.read_text())
            self.assertTrue(record["producer_input_already_compliant"])
            self.assertEqual(record["changed_offsets"], [])
            S.adapt(path)
            backup.write_bytes(b"changed producer")
            with self.assertRaises(AssertionError):
                S.adapt(path)
            backup.write_bytes(raw)
            receipt.unlink()
            with self.assertRaisesRegex(AssertionError, "original evidence"):
                S.adapt(path)

    def test_extension_still_rejects_writable_or_nonexecutable_storage(self):
        with tempfile.TemporaryDirectory(prefix="frame extension ") as directory:
            path = Path(directory) / "producer.obj"
            for flags in (0xE0300040, 0x40300040):
                raw = bytearray(mini_coff())
                raw[20:28] = b".qjsprop"
                struct.pack_into("<I", raw, 20 + 36, flags)
                path.write_bytes(raw)
                with self.subTest(flags=hex(flags)), self.assertRaises(AssertionError):
                    S.adapt(path)
                self.assertEqual(path.read_bytes(), raw)
                self.assertFalse(path.with_name(path.name + ".extension.json").exists())

    def test_generated_nested_members_do_not_alias_build_root(self):
        with tempfile.TemporaryDirectory(prefix="frame artifact paths ") as directory:
            build = Path(directory)
            self.assertEqual(
                _frame_build_file(build, "native-c-scope/implementation.obj"),
                build / "generated/native-c-scope/implementation.obj",
            )
            self.assertEqual(
                _frame_build_file(build, "generated/helper.obj"), build / "generated/helper.obj"
            )
            self.assertEqual(
                _frame_build_file(build, "compile_commands.json"), build / "compile_commands.json"
            )
            with self.assertRaisesRegex(RuntimeError, "build-relative"):
                _frame_generated_file(build, "../foreign.obj")

    def test_platform_policy(self):
        if not CMAKE:
            self.skipTest("Supply --cmake to execute the platform policy matrix")
        defaults = dict(
            WIN32="TRUE",
            CMAKE_SIZEOF_VOID_P="8",
            QJS_FRAME_COMPILER_X64="TRUE",
            CMAKE_GENERATOR="Ninja",
            BUILD_SHARED_LIBS="OFF",
            MINGW="TRUE",
            CMAKE_C_COMPILER_ID="GNU",
            CMAKE_BUILD_TYPE="Release",
            CMAKE_SOURCE_DIR="source",
            CMAKE_CURRENT_SOURCE_DIR="source",
        )
        cases = [
            ({}, True),
            ({"CMAKE_C_COMPILER_ID": "MSVC", "MINGW": "FALSE"}, True),
            ({"WIN32": "FALSE"}, False),
            ({"QJS_FRAME_COMPILER_X64": "FALSE"}, False),
            ({"CMAKE_SIZEOF_VOID_P": "4"}, False),
            ({"BUILD_SHARED_LIBS": "ON"}, False),
            ({"CMAKE_C_COMPILER_ID": "Clang", "MINGW": "FALSE", "MSVC": "TRUE"}, False),
            ({"CMAKE_GENERATOR": "Ninja Multi-Config"}, False),
            ({"CMAKE_GENERATOR": "Visual Studio 18 2026"}, False),
            ({"CMAKE_CURRENT_SOURCE_DIR": "nested"}, False),
            ({"CMAKE_BUILD_TYPE": "Debug"}, False),
            ({"QJS_ENABLE_ASAN": "ON"}, False),
            ({"QJS_ENABLE_GC_STRESS": "ON"}, False),
            ({"CMAKE_INTERPROCEDURAL_OPTIMIZATION": "ON"}, False),
            ({"CMAKE_C_FLAGS": "/GL"}, False),
            ({"CMAKE_C_FLAGS": "-flto=auto"}, False),
        ]
        with tempfile.TemporaryDirectory(prefix="frame policy ") as directory:
            script = Path(directory) / "policy.cmake"
            for changes, supported in cases:
                with self.subTest(changes=changes):
                    values = {**defaults, **changes}
                    text = "\n".join(f'set({k} "{v}")' for k, v in values.items())
                    text += (
                        '\ninclude("'
                        + (ROOT / "cmake/x86/win64/InterpreterPolicy.cmake").as_posix()
                        + '")\n'
                    )
                    text += "qjs_frame_platform_reason(reason)\n"
                    text += "if(reason)" if supported else "if(NOT reason)"
                    text += (
                        '\nmessage(FATAL_ERROR "Unexpected policy result: ${reason}")\nendif()\n'
                    )
                    script.write_text(text, encoding="utf-8")
                    result = subprocess.run([CMAKE, "-P", script], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_hash_observes_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "quickjs.c").write_text("one", encoding="utf-8")
            first = B.source_digest(source)
            (source / "quickjs.c").write_text("two", encoding="utf-8")
            self.assertNotEqual(first, B.source_digest(source))

    def test_build_local_tool_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="frame tools ") as directory:
            build = Path(directory)
            tool = _frame_build_file(build, "fake objdump.exe")
            tool.write_bytes(b"not executed")
            (_frame_build_file(build, "quickjs-interpreter-tools.json")).write_text(
                json.dumps({"objdump": str(tool)}), encoding="utf-8"
            )
            child = _frame_build_file(build, "scratch") / "nested"
            child.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(B.find_objdump(child), tool)
            with patch.dict(
                os.environ,
                {"QJS_FRAME_OBJDUMP": str(_frame_build_file(build, "missing"))},
                clear=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "does not exist"):
                    B.find_objdump(build)

    def test_reject_wrong_coff_architecture(self):
        raw = bytearray(60)
        struct.pack_into("<HHHH", raw, 0, 0, 0xFFFF, 2, 0xAA64)
        with self.assertRaisesRegex(RuntimeError, "x64 bigobj"):
            U.C.Coff(raw)

    def test_epoch_invalidation_and_noop(self):
        with tempfile.TemporaryDirectory(prefix="frame epoch ") as directory:
            source, build = Path(directory) / "source", Path(directory) / "build"
            source.mkdir()
            build.mkdir()
            (source / "quickjs.c").write_text("first", encoding="utf-8")
            (_frame_build_file(build, "CMakeCache.txt")).write_text(
                "CMAKE_HOME_DIRECTORY:INTERNAL=" + str(source) + "\n", encoding="utf-8"
            )
            owned = _frame_generated_file(build, "quickjs-owned.obj")
            unrelated = _frame_build_file(build, "keep-user-notes.txt")
            owned.write_bytes(b"old")
            unrelated.write_bytes(b"keep")
            native_folder = _frame_build_file(build, "CMakeFiles/qjs.dir")
            native_folder.mkdir(parents=True)
            env_products = [
                native_folder / ("quickjs-interpreter-call-env.c.obj" + suffix)
                for suffix in ("", ".before-call-env", ".call-env.json")
            ]
            for product in env_products:
                product.write_bytes(b"stale-native-epoch")
            E.prepare(source, build, "configuration")
            self.assertFalse(owned.exists())
            self.assertTrue(all(not product.exists() for product in env_products))
            # Configuration recreates the generated root after epoch retirement.
            owned.parent.mkdir(parents=True)
            owned.write_bytes(b"current")
            E.prepare(source, build, "configuration")
            self.assertEqual(owned.read_bytes(), b"current")
            (source / "quickjs.c").write_text("second", encoding="utf-8")
            E.prepare(source, build, "configuration")
            self.assertFalse(owned.exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_epoch_refuses_foreign_build(self):
        with tempfile.TemporaryDirectory() as directory:
            source, build = Path(directory) / "source", Path(directory) / "build"
            source.mkdir()
            build.mkdir()
            (_frame_build_file(build, "CMakeCache.txt")).write_text(
                "CMAKE_HOME_DIRECTORY:INTERNAL=" + str(source / "other") + "\n", encoding="utf-8"
            )
            owned = _frame_generated_file(build, "quickjs-owned.obj")
            owned.write_bytes(b"keep")
            with self.assertRaisesRegex(RuntimeError, "another source tree"):
                E.checked_targets(source, build)
            self.assertEqual(owned.read_bytes(), b"keep")

    def test_restart_validates_and_retires_final_bigint_stage(self):
        compiler = U.C.Coff(mini_coff())
        compiler.external("js_frame_call_entry")
        struct.pack_into("<h", compiler.aliases[-1], 12, 1)
        compiler_bytes = compiler.finish()
        alias = U.C.Coff(compiler_bytes)
        alias.external("JS_FrameCallEntryLegacy")
        struct.pack_into("<h", alias.aliases[-1], 12, 1)
        alias_bytes = alias.finish()
        final = U.C.Coff(alias_bytes)
        final.external("bigint_release_test_target")
        final_bytes = final.finish()
        with tempfile.TemporaryDirectory(prefix="frame replay ") as directory:
            build = Path(directory)
            path = _frame_generated_file(build, "quickjs-interpreter.c.obj")
            for stage, before, after in [
                ("shared-alias", compiler_bytes, alias_bytes),
                ("bigint-release", alias_bytes, final_bytes),
            ]:
                path.with_name(path.name + ".before-" + stage).write_bytes(before)
                path.with_name(path.name + "." + stage + ".json").write_text(
                    json.dumps(dict(before_sha256=U.sha(before), after_sha256=U.sha(after)))
                )
            path.write_bytes(final_bytes + b"unknown")
            with self.assertRaisesRegex(AssertionError, "Unknown adapted object"):
                R.restart(path, build)
            self.assertEqual(path.read_bytes(), final_bytes + b"unknown")
            path.write_bytes(final_bytes)
            stamp = path.stat().st_mtime_ns
            R.restart(path, build)
            self.assertEqual(path.read_bytes(), compiler_bytes)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            self.assertFalse(path.with_name(path.name + ".bigint-release.json").exists())
            epochs = list(path.with_name(path.name + ".adapter-history").glob("*/epoch.json"))
            self.assertEqual(len(epochs), 1)
            self.assertEqual(
                json.loads(epochs[0].read_text())["stages"],
                [path.name + ".shared-alias.json", path.name + ".bigint-release.json"],
            )

    def test_core_restart_retires_callback_and_json_provenance(self):
        compiler = U.C.Coff(mini_coff())
        compiler.external("JS_Call")
        struct.pack_into("<h", compiler.aliases[-1], 12, 1)
        compiler_bytes = compiler.finish()
        core = U.C.Coff(compiler_bytes)
        core.rename("JS_Call", "JS_LegacyCall")
        core_bytes = core.finish()
        callback = U.C.Coff(core_bytes)
        callback.external("callback_epoch_marker")
        callback_bytes = callback.finish()
        final = U.C.Coff(callback_bytes)
        final.external("json_epoch_marker")
        final_bytes = final.finish()
        for rebuilt in (False, True):
            with self.subTest(compiler_rebuilt=rebuilt), tempfile.TemporaryDirectory() as directory:
                build = Path(directory)
                path = build / "quickjs.c.obj"
                generated = _frame_generated_file(build, "")
                generated.mkdir(parents=True, exist_ok=True)
                original = generated / "quickjs-core-original.obj"
                original.write_bytes(compiler_bytes)
                private = generated / "quickjs-interpreter-private.json"
                private.write_text(
                    json.dumps(
                        dict(
                            original_object_sha256=U.sha(compiler_bytes),
                            adapted_object_sha256=U.sha(core_bytes),
                        )
                    )
                )
                backup = path.with_name(path.name + ".before-prepared-callback")
                backup.write_bytes(core_bytes)
                callback_report = generated / "quickjs-callback-private.json"
                callback_report.write_text(
                    json.dumps(
                        dict(before_sha256=U.sha(core_bytes), after_sha256=U.sha(callback_bytes))
                    )
                )
                json_report = generated / "quickjs-json-private.json"
                json_report.write_text(
                    json.dumps(
                        dict(
                            original_object_sha256=U.sha(callback_bytes),
                            adapted_object_sha256=U.sha(final_bytes),
                        )
                    )
                )
                path.write_bytes(compiler_bytes if rebuilt else final_bytes)
                # Broken snapshots must fail before an epoch is retired.
                backup.write_bytes(core_bytes + b"changed")
                with self.assertRaises(AssertionError):
                    R.restart_core(path, build)
                self.assertTrue(callback_report.exists())
                backup.write_bytes(core_bytes)
                if not rebuilt:
                    path.write_bytes(final_bytes + b"unknown")
                    with self.assertRaisesRegex(AssertionError, "Unknown adapted core"):
                        R.restart_core(path, build)
                    path.write_bytes(final_bytes)
                stamp = path.stat().st_mtime_ns
                R.restart_core(path, build)
                self.assertEqual(path.read_bytes(), compiler_bytes)
                self.assertEqual(path.stat().st_mtime_ns, stamp)
                for retired in (private, original, backup, callback_report, json_report):
                    self.assertFalse(retired.exists())
                epochs = list((generated / "core-adapter-history").glob("*/epoch.json"))
                self.assertEqual(len(epochs), 1)
                receipt = json.loads(epochs[0].read_text())
                self.assertEqual(receipt["compiler_rebuilt"], rebuilt)
                self.assertIn(str(callback_report.relative_to(build)), receipt["retired"])
                self.assertIn(str(json_report.relative_to(build)), receipt["retired"])
                self.assertEqual(
                    (epochs[0].parent / backup.relative_to(build)).read_bytes(), core_bytes
                )

    def test_archive_stage_reuses_only_exact_completed_inputs(self):
        with tempfile.TemporaryDirectory(prefix="archive stage ") as directory:
            build = Path(directory)
            member = _frame_build_file(build, "member.obj")
            member.write_bytes(b"compiler")
            pipeline = _frame_generated_file(build, "quickjs-interpreter-stage.cmake")
            pipeline.write_text("# pipeline")
            (_frame_build_file(build, "build.ninja")).write_text(
                "build qjs.lib: C_STATIC member.obj\n"
            )
            (_frame_build_file(build, "interpreter-native-epoch.json")).write_text(
                json.dumps(dict(fingerprint="epoch-one"))
            )

            def mutate(*args, **kwargs):
                member.write_bytes(b"adapted")

            with patch.object(F.subprocess, "run", side_effect=mutate) as run:
                F.finalize(build, _frame_build_file(build, "qjs.lib"), Path("cmake"), pipeline)
                F.finalize(build, _frame_build_file(build, "qjs.lib"), Path("cmake"), pipeline)
                self.assertEqual(run.call_count, 1)
                member.write_bytes(b"unknown-object")
                with self.assertRaisesRegex(RuntimeError, "clean-first"):
                    F.finalize(build, _frame_build_file(build, "qjs.lib"), Path("cmake"), pipeline)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(member.read_bytes(), b"unknown-object")

    def test_failed_archive_stage_requires_clean_rebuild(self):
        with tempfile.TemporaryDirectory(prefix="failed stage ") as directory:
            build = Path(directory)
            (_frame_build_file(build, "member.obj")).write_bytes(b"compiler")
            pipeline = _frame_generated_file(build, "quickjs-interpreter-stage.cmake")
            pipeline.write_text("# failed pipeline")
            (_frame_build_file(build, "build.ninja")).write_text(
                "build qjs.lib: C_STATIC member.obj\n"
            )
            (_frame_build_file(build, "interpreter-native-epoch.json")).write_text(
                json.dumps(dict(fingerprint="epoch-one"))
            )
            with patch.object(
                F.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["cmake"])
            ) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    F.finalize(build, _frame_build_file(build, "qjs.lib"), Path("cmake"), pipeline)
                receipt = json.loads(
                    (
                        _frame_generated_file(build, "quickjs-interpreter-archive-stage.json")
                    ).read_text()
                )
                self.assertEqual(receipt["status"], "failed")
                with self.assertRaisesRegex(RuntimeError, "clean-first"):
                    F.finalize(build, _frame_build_file(build, "qjs.lib"), Path("cmake"), pipeline)
                self.assertEqual(run.call_count, 1)

    def test_ninja_escaped_paths(self):
        self.assertEqual(
            U.ninja_words("rule D$:/with$ space/a.obj dollar$$.obj || order"),
            ["rule", "D:/with space/a.obj", "dollar$.obj", "||", "order"],
        )

    def test_archive_rule_ignores_cmake_variable_aliases(self):
        with tempfile.TemporaryDirectory(prefix="frame ninja ") as directory:
            build = Path(directory)
            (_frame_build_file(build, "build.ninja")).write_text(
                "build ${cmake_ninja_workdir}CMakeFiles/check: phony\n"
                "build nested/qjs.lib: C_STATIC input.obj || generated\n",
                encoding="utf-8",
            )
            self.assertEqual(
                U.inputs(build, _frame_build_file(build, "nested/qjs.lib")),
                [(_frame_build_file(build, "input.obj")).resolve()],
            )

    def test_standard_unwind_dedup_and_restore(self):
        raw = mini_coff()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.obj"
            path.write_bytes(raw)
            report = Path(directory) / "report.json"
            original_time = path.stat().st_mtime_ns
            U.publish([path], report)
            self.assertEqual(path.stat().st_mtime_ns, original_time)
            receipt = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(receipt["total_added_rows"], 1)
            before, after = U.C.Coff(raw), U.C.Coff(path.read_bytes())
            self.assertEqual(before.sections, after.sections[:-1])
            self.assertEqual(U.section_name(after, after.count), ".pdata")
            objects, definitions = U.load([path])
            self.assertEqual(
                len(list(U.runtime_rows(path, objects[path], objects, definitions, True))), 1
            )
            U.restore([path])
            self.assertEqual(path.read_bytes(), raw)

    def test_embedded_chain_parent_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.obj"
            path.write_bytes(mini_coff(with_chain=True))
            report = Path(directory) / "chain.json"
            U.publish([path], report)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["total_added_rows"], 1)

    def test_validate_native_image_accepts_pe32plus_unwind_v1_and_v2(self):
        spec = importlib.util.spec_from_file_location(
            "validate_native_image_under_test", _frame_tool_path("validate-native-image")
        )
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)

        def minimal_pe(unwind_version):
            # Minimal PE32+ image with .text (RVA 0x1000), .pdata (RVA 0x2000),
            # .rdata (RVA 0x3000), and .reloc (RVA 0x4000).
            raw = bytearray(0x2800)
            raw[0:2] = b"MZ"
            pe = 0x80
            struct.pack_into("<I", raw, 60, pe)
            raw[pe : pe + 4] = b"PE\0\0"
            struct.pack_into("<HHIIIHH", raw, pe + 4, 0x8664, 4, 0, 0, 0, 0xF0, 0x22)
            opt = pe + 24
            struct.pack_into("<H", raw, opt, 0x20B)
            struct.pack_into("<I", raw, opt + 60, 0x400)
            struct.pack_into("<H", raw, opt + 70, 0x140)
            struct.pack_into("<II", raw, opt + 112 + 3 * 8, 0x2000, 12)
            struct.pack_into("<II", raw, opt + 112 + 5 * 8, 0x4000, 8)
            sections = [
                (b".text\0\0\0", 0x10, 0x1000, 0x200, 0x400, 0x60000020),
                (b".pdata\0\0", 12, 0x2000, 0x200, 0x600, 0x40000040),
                (b".rdata\0\0", 8, 0x3000, 0x200, 0x800, 0x40000040),
                (b".reloc\0\0", 8, 0x4000, 0x200, 0xA00, 0x42000040),
            ]
            sec_table = opt + 0xF0
            for idx, (name, vsize, rva, psize, poff, flags) in enumerate(sections):
                struct.pack_into(
                    "<8sIIIIIIHHI",
                    raw,
                    sec_table + idx * 40,
                    name,
                    vsize,
                    rva,
                    psize,
                    poff,
                    0,
                    0,
                    0,
                    0,
                    flags,
                )
            struct.pack_into("<III", raw, 0x600, 0x1000, 0x1010, 0x3000)
            raw[0x800] = unwind_version
            return bytes(raw)

        with tempfile.TemporaryDirectory() as directory:
            for ver in (1, 2):
                image = Path(directory) / f"valid_v{ver}.exe"
                image.write_bytes(minimal_pe(ver))
                result = validator.validate(image)
                self.assertEqual(result["status"], "passed")
                self.assertEqual(result["runtime_functions"], 1)
            for ver in (0, 3):
                image = Path(directory) / f"invalid_v{ver}.exe"
                image.write_bytes(minimal_pe(ver))
                with self.assertRaisesRegex(ValueError, "unwind-info version"):
                    validator.validate(image)

    def test_default_experiment_allocator_option_validation(self):
        if not CMAKE:
            self.skipTest("Supply --cmake to execute Backports option checks")
        backports = (ROOT / "cmake/common/Backports.cmake").as_posix()
        cases = [
            ([], True, None),
            (
                ["-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON", "-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=256"],
                True,
                None,
            ),
            (
                ["-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON", "-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=0"],
                True,
                None,
            ),
            (
                [
                    "-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=OFF",
                    "-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=256",
                ],
                False,
                "requires QJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON",
            ),
            (
                ["-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON", "-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=999"],
                False,
                "must be empty, off, 0, header, 128, 256 or 512",
            ),
        ]
        with tempfile.TemporaryDirectory(prefix="default allocator opt ") as directory:
            script = Path(directory) / "check.cmake"
            script.write_text(
                f'set(QJS_UPSTREAM_DIR "{ROOT.parent.as_posix()}")\n'
                'set(CMAKE_SIZEOF_VOID_P "8")\n'
                f'include("{backports}")\n',
                encoding="utf-8",
            )
            for flags, expected_ok, err_substr in cases:
                with self.subTest(flags=flags):
                    res = subprocess.run(
                        [CMAKE, *flags, "-P", str(script)], capture_output=True, text=True
                    )
                    self.assertEqual(res.returncode == 0, expected_ok, res.stdout + res.stderr)
                    if err_substr:
                        self.assertIn(err_substr, " ".join(res.stderr.split()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
