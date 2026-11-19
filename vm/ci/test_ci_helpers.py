#!/usr/bin/env python3
"""Unit tests for QuickJS-Turbo CI verification helpers."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_win64_mingw
import verify_pe_imports
import verify_test262


def _build_synthetic_pe32_plus(dll_names: list[str], *, opt_magic: int = 0x20B) -> bytes:
    """Build a minimal valid x64 PE32+ image with an .idata import table."""
    e_lfanew = 0x80
    coff_size = 20
    opt_size = 240
    sec_off = e_lfanew + 4 + coff_size + opt_size
    sec_raw = 0x200
    sec_rva = 0x1000

    descriptors = bytearray()
    name_blob = bytearray()
    cur_rva = sec_rva + (len(dll_names) + 1) * 20
    for name in dll_names:
        descriptors.extend(struct.pack("<IIIII", 0, 0, 0, cur_rva + len(name_blob), 0))
        name_blob.extend(name.encode("ascii") + b"\x00")
    descriptors.extend(b"\x00" * 20)
    sec_data = bytes(descriptors + name_blob)
    total_size = sec_raw + len(sec_data)

    buf = bytearray(total_size)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, e_lfanew)
    buf[e_lfanew : e_lfanew + 4] = b"PE\x00\x00"

    coff = e_lfanew + 4
    struct.pack_into("<HHIIIHH", buf, coff, 0x8664, 1, 0, 0, 0, opt_size, 0)

    opt = coff + coff_size
    struct.pack_into("<H", buf, opt, opt_magic)
    struct.pack_into("<I", buf, opt + 108, 16)
    struct.pack_into("<II", buf, opt + 120, sec_rva, len(descriptors))

    buf[sec_off : sec_off + 8] = b".idata\x00\x00"
    struct.pack_into("<IIII", buf, sec_off + 8, len(sec_data), sec_rva, len(sec_data), sec_raw)
    buf[sec_raw : sec_raw + len(sec_data)] = sec_data
    return bytes(buf)


def _create_mock_runner(tmp: Path, payload: dict) -> Path:
    impl = tmp / "mock_impl.py"
    payload_file = tmp / "mock_payload.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    impl.write_text(
        "\n".join(
            [
                "import json, sys",
                "from pathlib import Path",
                f"data = json.loads(Path({str(payload_file)!r}).read_text(encoding='utf-8'))",
                "sys.stdout.write(data.get('stdout', ''))",
                "sys.stderr.write(data.get('stderr', ''))",
                "raise SystemExit(data.get('exit_code', 0))",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if os.name == "nt":
        runner = tmp / "run-test262.cmd"
        runner.write_text(
            f'@echo off\r\n"{sys.executable}" -B "{impl}" %*\r\n',
            encoding="utf-8",
        )
        return runner
    runner = tmp / "run-test262"
    runner.write_text(
        f"#!/bin/sh\nexec \"{sys.executable}\" -B \"{impl}\" \"$@\"\n",
        encoding="utf-8",
        newline="\n",
    )
    runner.chmod(0o755)
    return runner


class VerifyPEImportsTests(unittest.TestCase):
    def test_accepts_kernel32_only_and_rejects_dynamic_crt(self) -> None:
        pure = _build_synthetic_pe32_plus(["KERNEL32.dll"])
        self.assertEqual(verify_pe_imports.read_pe_imports(pure), ["KERNEL32.dll"])

        mixed = _build_synthetic_pe32_plus(["KERNEL32.dll", "VCRUNTIME140.dll"])
        self.assertEqual(
            verify_pe_imports.read_pe_imports(mixed), ["KERNEL32.dll", "VCRUNTIME140.dll"]
        )

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pure_path = tmp / "pure.exe"
            mixed_path = tmp / "mixed.exe"
            pure_path.write_bytes(pure)
            mixed_path.write_bytes(mixed)
            self.assertEqual(verify_pe_imports.main([str(pure_path)]), 0)
            self.assertEqual(verify_pe_imports.main([str(mixed_path)]), 1)
            self.assertEqual(
                verify_pe_imports.main(
                    ["--allow", "KERNEL32.dll", "--allow", "vcruntime140.dll", str(mixed_path)]
                ),
                0,
            )

    def test_rejects_non_pe_and_pe32(self) -> None:
        with self.assertRaisesRegex(ValueError, "Not an MZ"):
            verify_pe_imports.read_pe_imports(b"ELF\x00" + b"\x00" * 64)
        pe32 = _build_synthetic_pe32_plus(["KERNEL32.dll"], opt_magic=0x10B)
        with self.assertRaisesRegex(ValueError, "PE32\\+"):
            verify_pe_imports.read_pe_imports(pe32)


class VerifyTest262Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = {
            "test262/test/known/a.js [default]",
            "test262/test/known/b.js [strict]",
            "test262/test/known/fixed_target.js [default]",
        }

    def test_passing_run_with_fixed_errors_and_exit_code_1(self) -> None:
        stdout = "test262/test/known/fixed_target.js:12: OK, fixed error: TypeError: old\n"
        stderr = "Result: 2/100 errors, 5 excluded, 3 skipped, 1 fixed\n"
        res = verify_test262.evaluate_output(self.known, stdout, stderr, 1)
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["fixed_count"], 1)
        self.assertEqual(res["failed"], 2)

    def test_rejects_new_changed_and_crash_exit_codes(self) -> None:
        new_out = "test262/test/new/fail.js:5: unexpected error: ReferenceError: x\n"
        new_err = "Result: 4/100 errors, 1 new\n"
        self.assertFalse(verify_test262.evaluate_output(self.known, new_out, new_err, 1)["passed"])

        chg_out = (
            "test262/test/known/b.js:9: strict mode: unexpected error: RangeError: new\n"
            "test262/test/known/b.js:7: strict mode: previous error: TypeError: old\n"
        )
        chg_err = "Result: 3/100 errors, 1 changed\n"
        self.assertFalse(verify_test262.evaluate_output(self.known, chg_out, chg_err, 1)["passed"])

        ok_out = ""
        ok_err = "Result: 3/100 errors\n"
        self.assertFalse(verify_test262.evaluate_output(self.known, ok_out, ok_err, 139)["passed"])
        self.assertFalse(verify_test262.evaluate_output(self.known, ok_out, ok_err, -11)["passed"])

    def test_cli_end_to_end_with_mock_runner(self) -> None:
        script = Path(__file__).resolve().with_name("verify_test262.py")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "test262.conf").write_text("[config]\n", encoding="utf-8", newline="\n")
            (tmp / "test262_errors.txt").write_text(
                "\n".join(
                    [
                        "test262/test/known/a.js:1: TypeError: err",
                        "test262/test/known/b.js:2: strict mode: TypeError: err",
                        "test262/test/known/fixed_target.js:3: TypeError: old",
                    ]
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            pass_runner = _create_mock_runner(
                tmp,
                {
                    "stdout": (
                        "test262/test/known/fixed_target.js:3: "
                        "OK, fixed error: TypeError: old\n"
                    ),
                    "stderr": "Result: 2/100 errors, 4 excluded, 1 fixed\n",
                    "exit_code": 1,
                },
            )
            report = tmp / "out" / "pass.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(script),
                    "--repo-root",
                    str(tmp),
                    "--runner",
                    str(pass_runner),
                    "--name",
                    "mock-pass",
                    "--skip-corpus-pin",
                    "--output",
                    str(report),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            loaded = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(loaded["passed"])
            self.assertEqual(loaded["counts"]["fixed"], 1)

            fail_runner = _create_mock_runner(
                tmp,
                {
                    "stdout": "test262/test/new/reg.js:4: unexpected error: TypeError: boom\n",
                    "stderr": "Result: 4/100 errors, 1 new\n",
                    "exit_code": 1,
                },
            )
            fail_report = tmp / "out" / "fail.json"
            fail_proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(script),
                    "--repo-root",
                    str(tmp),
                    "--runner",
                    str(fail_runner),
                    "--name",
                    "mock-fail",
                    "--skip-corpus-pin",
                    "--output",
                    str(fail_report),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(fail_proc.returncode, 1)


class InstallWin64MinGWTests(unittest.TestCase):
    def test_rejects_checksum_mismatch_and_cleans_partial_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "winlibs"
            archive = dest / install_win64_mingw.ARCHIVE_NAME

            class _Resp(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.close()

            with patch.object(
                install_win64_mingw.urllib.request,
                "urlopen",
                side_effect=lambda req, timeout=180: _Resp(b"corrupt-archive-bytes"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                    install_win64_mingw.ensure_toolchain(dest)
            self.assertFalse(archive.exists())

    def test_writes_github_output_when_tools_already_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            dest = root / "winlibs"
            bin_dir = dest / "mingw64/bin"
            bin_dir.mkdir(parents=True)
            for exe in ("gcc.exe", "g++.exe", "objdump.exe", "as.exe", "ninja.exe"):
                (bin_dir / exe).write_bytes(b"")
            fake_cmake = root / "cmake.exe"
            fake_cmake.write_bytes(b"")
            gh_out = root / "github_output.txt"

            with patch.object(install_win64_mingw.shutil, "which", return_value=str(fake_cmake)):
                rc = install_win64_mingw.main(["--dest", str(dest), "--github-output", str(gh_out)])

            self.assertEqual(rc, 0)
            parsed = dict(
                line.split("=", 1) for line in gh_out.read_text(encoding="utf-8").splitlines()
            )
            self.assertEqual(
                set(parsed), {"cmake", "ninja", "gcc", "gxx", "objdump", "as", "mingw_bin"}
            )
            self.assertEqual(parsed["cmake"], fake_cmake.as_posix())
            self.assertEqual(parsed["gcc"], (bin_dir / "gcc.exe").as_posix())
            self.assertEqual(parsed["mingw_bin"], str(bin_dir))


if __name__ == "__main__":
    unittest.main()
