"""Enforce strict one-way DAG and symmetric common/arm64/x86 boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_ROOT = ROOT.parent

UPSTREAM_TESTS = frozenset(
    {
        "array-fromasync-enumerable.js",
        "array-sort-identical-values.js",
        "assert.js",
        "atomics-store-leak.js",
        "bug1296.js",
        "bug1297.js",
        "bug1301.js",
        "bug1302.js",
        "bug1305.js",
        "bug1318.js",
        "bug1352.js",
        "bug1354.js",
        "bug1355.js",
        "bug1368.js",
        "bug1430.js",
        "bug1468.js",
        "bug1498.js",
        "bug1552.js",
        "bug1557.js",
        "bug1562.js",
        "bug1564.js",
        "bug1565.js",
        "bug1571.js",
        "bug1572.js",
        "bug1591.js",
        "bug1598.js",
        "bug1625.js",
        "bug1626.js",
        "bug1627.js",
        "bug1628.js",
        "bug1661.js",
        "bug1672",
        "bug1683.js",
        "bug1690.js",
        "bug1691.js",
        "bug1693.js",
        "bug1730.js",
        "bug1732.js",
        "bug1735.js",
        "bug1795.js",
        "bug1835.js",
        "bug39",
        "bug488-upstream.js",
        "bug492.js",
        "bug493.js",
        "bug567.js",
        "bug633",
        "bug645",
        "bug648.js",
        "bug652.js",
        "bug741.js",
        "bug775.js",
        "bug776.js",
        "bug832.js",
        "bug858.js",
        "bug904.js",
        "bug988.js",
        "bug999.js",
        "callsite-isconstructor.js",
        "callsite-native-position.js",
        "destructured-export.js",
        "detect_module",
        "dynamic_import_rejection_handled.js",
        "empty.js",
        "fix_set_array_length-uaf.js",
        "fixture_cyclic_import.js",
        "fixture_import_attributes.json",
        "fixture_reexport_direct.js",
        "fixture_reexport_missing.js",
        "fixture_reexport_source.js",
        "fixture_string_exports.js",
        "fixture_throwing_module.js",
        "for-await-normal-close.js",
        "function_source.js",
        "global-reference-column.js",
        "import-attributes-identity.js",
        "iterator-filter-leak.js",
        "iterator-tostringtag-setter.js",
        "microbench.js",
        "null_or_undefined.js",
        "parse-error-column.js",
        "reexport-error-module.js",
        "resize_array_buffer_index_valueOf.js",
        "str-pad-leak.js",
        "suspended-coroutine-closure-gc.js",
        "suspended-coroutine-mapped-arguments-gc.js",
        "suspended-generator-closure-gc.js",
        "test_array_to_gc.js",
        "test_base64.js",
        "test_bigint.js",
        "test_bjson.js",
        "test_builtin.js",
        "test_closure.js",
        "test_domexception.js",
        "test_dynamic_import_line_numbers.js",
        "test_for_of_line_numbers.js",
        "test_language.js",
        "test_loop.js",
        "test_queue_microtask.js",
        "test_std.js",
        "test_string_exports.js",
        "test_worker.js",
        "test_worker_module.js",
        "typedarray-lastindexof-shrink.js",
        "typedarray-set-invalid-index.js",
        "typedarray-slice-overlap.js",
        "typedarray-subarray-species.js",
        "wasi-stack-limit.js",
    }
)

ALLOWLISTED_COMMON = frozenset(
    {
        "src/sources.json",
        "tools/common/modules.json",
        "tools/common/format/native-frozen.json",
        "tools/common/format/js-frozen.json",
        "cmake/common/InterpreterOptions.cmake",
        "tests/common/validate_layout.py",
        "tests/common/test_arch_boundaries.py",
    }
)

FORBIDDEN_COMMON = re.compile(
    r"(?i)\b(?:arm64|aarch64|x86|x86_64|win64|mingw64|mingw|msvc|coff)\b"
    r"|<(?:emmintrin|immintrin|xmmintrin|intrin)\.h>|_mm_\w+|__asm__|%%rip|%%rsp|%%gs"
)
FORBIDDEN_ARM64 = re.compile(
    r"(?i)\b(?:x86|x86_64|win64|mingw64|mingw|msvc|coff)\b"
    r"|<(?:emmintrin|immintrin|xmmintrin|intrin)\.h>|_mm_\w+|%%rip|%%rsp|%%gs"
)
FORBIDDEN_X86 = re.compile(r"(?i)\b(?:arm64|aarch64)\b")

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".inc",
        ".S",
        ".asm",
        ".cmake",
        ".js",
        ".json",
        ".sh",
        ".ps1",
        ".txt",
        ".md",
    }
)


def main() -> int:
    errors = []

    # 1. Symmetric vm/ root structure
    expected_subs = {
        "src": {"common", "arm64", "x86", "sources.json"},
        "asm": {"arm64", "x86"},
        "tools": {"common", "arm64", "x86"},
        "cmake": {"common", "arm64", "x86", "QuickJSUpstreamPin.cmake"},
        "tests": {"common", "arm64", "x86"},
        "docs/architecture": {"common", "arm64", "x86"},
    }
    for rel, allowed in expected_subs.items():
        actual = {p.name for p in (ROOT / rel).iterdir() if p.name != "__pycache__"}
        if actual != allowed:
            errors.append(
                f"Non-symmetric root {rel}: got {sorted(actual)}, expected {sorted(allowed)}"
            )

    # 2. Exact 108 upstream entries at UPSTREAM_ROOT/tests root
    test_root = {p.name for p in (UPSTREAM_ROOT / "tests").iterdir()}
    missing_up = sorted(UPSTREAM_TESTS - test_root)
    if missing_up:
        errors.append(f"Missing upstream tests entries: {missing_up}")
    extra_tests = sorted(test_root - UPSTREAM_TESTS)
    if extra_tests:
        errors.append(f"Stray non-upstream entries at tests/ root: {extra_tests}")

    # 3. 19 pinned upstream files & non-vm upstream tree untouched
    pin_txt = (ROOT / "cmake/QuickJSUpstreamPin.cmake").read_text(encoding="utf-8")
    pin_pairs = re.findall(r'"([^":]+):([0-9a-f]{64})"', pin_txt)
    if len(pin_pairs) != 19:
        errors.append(
            f"Expected 19 pinned upstream files in QuickJSUpstreamPin.cmake, got {len(pin_pairs)}"
        )
    for name, expected_sha in pin_pairs:
        up_file = UPSTREAM_ROOT / name
        if not up_file.is_file():
            errors.append(f"Missing pinned upstream file: {name}")
        else:
            actual_sha = hashlib.sha256(up_file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            if actual_sha != expected_sha:
                errors.append(f"Pinned upstream SHA256 mismatch: {name}")
    pin_rev_match = re.search(r'set\(QJS_UPSTREAM_REVISION\s+"([0-9a-f]{40})"\)', pin_txt)
    if not pin_rev_match:
        errors.append("Missing QJS_UPSTREAM_REVISION in QuickJSUpstreamPin.cmake")
    git_probe = subprocess.run(
        ["git", "-C", str(UPSTREAM_ROOT), "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
    )
    if git_probe.returncode == 0 and pin_pairs:
        rev = pin_rev_match.group(1) if pin_rev_match else "HEAD"
        rev_probe = subprocess.run(
            ["git", "-C", str(UPSTREAM_ROOT), "cat-file", "-e", f"{rev}^{{commit}}"],
            capture_output=True,
        )
        if rev_probe.returncode == 0:
            diff_pin = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(UPSTREAM_ROOT),
                    "diff",
                    "--name-only",
                    rev,
                    "--",
                    ".",
                    ":!vm",
                    ":!README.md",
                    ":!.github",
                    ":!perf-site",
                    ":!CMakeLists.txt",
                ],
                text=True,
            ).strip()
            if diff_pin:
                changed = diff_pin.splitlines()
                errors.append(
                    f"Upstream files outside vm/ (except README.md, .github/, perf-site/): {changed}"
                )
        untracked = subprocess.check_output(
            [
                "git",
                "-C",
                str(UPSTREAM_ROOT),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                ".",
                ":!vm",
                ":!.github",
                ":!perf-site",
            ],
            text=True,
        ).strip()
        if untracked:
            errors.append(f"Untracked files outside vm/: {untracked.splitlines()}")

    # 4. Strict One-Way DAG regex scan (excluding build/, node_modules/, ci/, docs/)
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        parts = p.relative_to(ROOT).parts
        if (
            parts[0] in {"build", ".git", ".ruff_cache", "node_modules", "ci", "docs"}
            or "__pycache__" in parts
        ):
            continue
        if len(parts) == 1:
            continue
        if p.suffix not in TEXT_SUFFIXES:
            continue
        if rel in ALLOWLISTED_COMMON or rel.startswith("docs/architecture/common/"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        domain = parts[1]
        if domain == "common":
            m = FORBIDDEN_COMMON.search(text)
            if m:
                errors.append(f"COMMON leak in {rel}: {m.group(0)!r}")
        elif domain == "arm64":
            m = FORBIDDEN_ARM64.search(text)
            if m:
                errors.append(f"ARM64->X86 leak in {rel}: {m.group(0)!r}")
        elif domain == "x86":
            m = FORBIDDEN_X86.search(text)
            if m:
                errors.append(f"X86->ARM64 leak in {rel}: {m.group(0)!r}")

    if errors:
        for e in errors:
            print("BOUNDARY_ERR:", e)
        print(f"ARCH_BOUNDARIES_FAILED ({len(errors)} errors)")
        return 1
    print("ARCH_BOUNDARIES_OK common/arm64/x86 DAG verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
