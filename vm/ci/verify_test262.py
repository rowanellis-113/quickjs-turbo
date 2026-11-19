#!/usr/bin/env python3
"""Run QuickJS-Turbo run-test262 and enforce zero new or changed failures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

DEFAULT_CORPUS_REV = "de8e621cdba4f40cff3cf244e6cfb8cb48746b4a"
IDENTITY_RE = re.compile(r"(test262[/\\]test[/\\][^:]+):\d+: (.*)")
SUMMARY_RE = re.compile(r"Result: ([^\r\n]+)")
COUNTS_RE = re.compile(r"(\d+)/(\d+) errors?(.*)")
LABEL_RE = re.compile(r", (\d+) (new|changed|fixed|excluded|skipped)")


def identity(line: str) -> str | None:
    """Normalize a Test262 diagnostic line into `<path> [strict|default]`."""
    match = IDENTITY_RE.match(line)
    if not match:
        return None
    test_path = match.group(1).replace("\\", "/")
    mode = " [strict]" if match.group(2).startswith("strict mode: ") else " [default]"
    return test_path + mode


def _is_difference_line(line: str) -> bool:
    return (
        "unexpected error:" in line
        or "unexpected error type:" in line
        or "previous error:" in line
        or line.endswith(": expected error")
        or ": strict mode: expected error" in line
    )


def evaluate_output(known: set[str], stdout: str, stderr: str, exit_code: int) -> dict:
    """Validate run-test262 exit code, summary counts, fixed cases, and zero regressions."""
    failure_reasons: list[str] = []
    if exit_code not in (0, 1):
        failure_reasons.append(f"unexpected runner exit code {exit_code}")

    summaries = SUMMARY_RE.findall(stderr)
    summary = summaries[0] if len(summaries) == 1 else ""
    tested = 0
    failed = 0
    counts: dict[str, int] = {}
    if len(summaries) != 1:
        failure_reasons.append(f"expected 1 Result summary line in stderr, got {len(summaries)}")
    else:
        match = COUNTS_RE.match(summary)
        if not match:
            failure_reasons.append(f"unrecognized Result summary format: {summary}")
        else:
            failed = int(match.group(1))
            tested = int(match.group(2))
            counts = {label: int(value) for value, label in LABEL_RE.findall(summary)}

    lines = stdout.splitlines() + stderr.splitlines()
    fixed_lines = [
        line for line in lines if "OK, fixed error:" in line or "OK, now has error" in line
    ]
    fixed_raw = [identity(line) for line in fixed_lines]
    if any(item is None for item in fixed_raw):
        failure_reasons.append("unparsed fixed-error diagnostic line")
    fixed = {item for item in fixed_raw if item is not None}

    difference_lines = [line for line in lines if _is_difference_line(line) and identity(line)]
    new_ids = {identity(line) for line in difference_lines if "previous error:" not in line}
    new_ids.discard(None)
    failures = (known - fixed) | new_ids

    if not failure_reasons:
        if tested == 0:
            failure_reasons.append("0 tests executed")
        if len(failures) != failed:
            failure_reasons.append(
                f"reconstructed failure count {len(failures)} != reported {failed}"
            )
        if len(fixed) != counts.get("fixed", 0):
            failure_reasons.append(
                f"parsed fixed count {len(fixed)} != reported {counts.get('fixed', 0)}"
            )
    if counts.get("new", 0) != 0:
        failure_reasons.append(f"new failures reported: {counts['new']}")
    if counts.get("changed", 0) != 0:
        failure_reasons.append(f"changed failures reported: {counts['changed']}")
    if difference_lines:
        failure_reasons.append(f"unexpected difference lines present: {len(difference_lines)}")

    return {
        "passed": not failure_reasons,
        "failure_reasons": failure_reasons,
        "exit_code": exit_code,
        "summary": summary,
        "tested": tested,
        "failed": failed,
        "counts": counts,
        "fixed_count": len(fixed),
        "fixed_identities": sorted(fixed),
        "failure_identities": sorted(failures),
        "difference_lines": difference_lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root containing test262.conf and test262_errors.txt",
    )
    parser.add_argument("--runner", type=Path, required=True, help="Path to run-test262 executable")
    parser.add_argument("--name", required=True, help="Logical target name for report logs")
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 4))
    parser.add_argument("--allocator", default="256", help="QJS_EXPERIMENT_ALLOCATOR value")
    parser.add_argument("--extra-env", action="append", default=[], help="Extra KEY=VALUE env var")
    parser.add_argument("--expected-corpus", default=DEFAULT_CORPUS_REV)
    parser.add_argument("--skip-corpus-pin", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    runner = args.runner.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_corpus_pin:
        corpus = repo_root / "test262"
        rev = subprocess.check_output(
            ["git", "-C", str(corpus), "rev-parse", "HEAD"], text=True
        ).strip()
        if rev != args.expected_corpus:
            print(
                f"TEST262_FAILED {args.name}: corpus rev {rev} != {args.expected_corpus}",
                file=sys.stderr,
            )
            return 1

    errors_file = repo_root / "test262_errors.txt"
    known = {identity(line) for line in errors_file.read_text(encoding="utf-8").splitlines()}
    known.discard(None)

    env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    if args.allocator:
        env["QJS_EXPERIMENT_ALLOCATOR"] = args.allocator
    for item in args.extra_env:
        if "=" not in item:
            parser.error(f"Expected KEY=VALUE for --extra-env, got {item!r}")
        key, val = item.split("=", 1)
        env[key] = val

    cmd = [str(runner), "-m", "-c", "test262.conf", "-a", "-t", str(args.threads)]
    stdout_path = output.with_name(f"{args.name}.stdout")
    stderr_path = output.with_name(f"{args.name}.stderr")

    start = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        capture_output=True,
        timeout=args.timeout,
    )
    elapsed = round(time.monotonic() - start, 3)

    stdout_text = proc.stdout.decode("utf-8", errors="replace")
    stderr_text = proc.stderr.decode("utf-8", errors="replace")
    stdout_path.write_text(stdout_text, encoding="utf-8", newline="\n")
    stderr_path.write_text(stderr_text, encoding="utf-8", newline="\n")

    result = evaluate_output(known, stdout_text, stderr_text, proc.returncode)
    result.update({"name": args.name, "elapsed_seconds": elapsed, "command": cmd})
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")

    if result["passed"]:
        print(
            f"TEST262_OK {args.name}: {result['summary']} ({elapsed}s)",
            flush=True,
        )
        return 0

    print(
        f"TEST262_FAILED {args.name}: {result['failure_reasons']} summary={result['summary']!r}",
        file=sys.stderr,
    )
    for line in result["difference_lines"][:20]:
        print(f"  diff: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
