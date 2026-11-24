import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, upstream_root

_act_x86()

"""Run stock/portable/native serially with the accepted corpus and error list.

Failure identities are the known set minus explicitly reported fixed cases,
plus new/changed lines. This reconstruction is accepted only when its count
matches the runner's complete summary. No source or expected error is edited.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from target_runner import (
    observe_process,
    source_identity,
    target_command,
    target_identity,
    verify_identity,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(line):
    match = re.match(r"(test262/test/[^:]+):\d+: (.*)", line)
    if not match:
        return None
    return match[1] + (" [strict]" if match[2].startswith("strict mode: ") else " [default]")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--engines", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--cpu", type=int, default=2, help="Allowed CPU; default original CPU 2")
    a = ap.parse_args()
    if a.cpu not in os.sched_getaffinity(0):
        raise ValueError("Selected CPU is not allowed")
    source, out = a.source.resolve(), a.output.resolve()
    source_binding = source_identity(source)
    out.mkdir(parents=True, exist_ok=False)
    up = upstream_root(source)
    corpus = up / "test262"
    revision = subprocess.check_output(
        ["git", "-C", corpus, "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != "5ef1e5723be95296f36afb0386676fed0205869c":
        raise ValueError("Wrong accepted corpus revision")
    if subprocess.check_output(["git", "-C", corpus, "status", "--porcelain"], text=True).strip():
        raise ValueError("Corpus must be unchanged")
    known = {identity(line) for line in (up / "test262_errors.txt").read_text().splitlines()}
    known.discard(None)
    engines = json.loads(a.engines.read_text())
    report = dict(
        status="running",
        source_identity=source_binding,
        affinity_cpu=a.cpu,
        corpus_revision=revision,
        known_error_sha256=sha(up / "test262_errors.txt"),
        config_sha256=sha(up / "test262.conf"),
        known_failure_identities=sorted(known),
        records=[],
    )

    def save():
        (out / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    for engine in engines:
        name, binary = engine["name"], Path(engine["binary"]).resolve()
        execution = target_identity(engine)
        digest = execution["binary_sha256"]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
        env.update(engine.get("env", {}))
        args = [
            "taskset",
            "-c",
            str(a.cpu),
            *target_command(execution, "-m", "-c", "test262.conf", "-a", "-t", "1"),
        ]
        timeout = engine.get("timeout_seconds", 1800)
        if type(timeout) is not int or timeout <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        start = time.monotonic()
        with (
            (out / (name + ".stdout")).open("wb") as so,
            (out / (name + ".stderr")).open("wb") as se,
        ):
            p = subprocess.Popen(args, cwd=up, env=env, stdout=so, stderr=se)
            try:
                process = observe_process(execution, p.pid)
                if process["affinity"] != [a.cpu]:
                    raise ValueError("Unexpected Test262 process affinity")
                (out / (name + ".process.json")).write_text(json.dumps(process, indent=2) + "\n")
            except Exception:
                p.kill()
                p.wait()
                raise
            report["active"] = dict(
                name=name,
                pid=p.pid,
                command=args,
                binary_sha256=digest,
                execution=execution,
                pid_role="host-emulator" if execution["runner"] else "engine",
            )
            save()
            print("TEST262 START", name, p.pid, flush=True)
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                report["status"] = "incomplete-timeout"
                report["active"]["terminated"] = True
                save()
                raise
        stdout = (out / (name + ".stdout")).read_text()
        stderr = (out / (name + ".stderr")).read_text()
        summaries = re.findall(r"Result: ([^\r\n]+)", stderr)
        verify_identity(execution)
        if len(summaries) != 1 or sha(binary) != digest:
            raise ValueError("Incomplete or changed Test262 image: " + name)
        summary = summaries[0]
        counts = re.match(r"(\d+)/(\d+) errors?", summary)
        if not counts:
            raise ValueError(summary)
        fixed_lines = [
            line
            for line in stdout.splitlines()
            if "OK, fixed error:" in line or "OK, now has error" in line
        ]
        fixed = {identity(line) for line in fixed_lines}
        differences = [
            line
            for line in stdout.splitlines()
            if "unexpected error:" in line
            or "unexpected error type:" in line
            or "previous error:" in line
        ]
        differences = [line for line in differences if identity(line)]
        new_ids = {identity(line) for line in differences if "previous error:" not in line}
        failures = (known - fixed) | new_ids
        count_by_label = {
            label: int(value)
            for value, label in re.findall(r", (\d+) (new|changed|fixed|excluded|skipped)", summary)
        }
        if (
            None in fixed
            or len(failures) != int(counts[1])
            or len(fixed) != count_by_label.get("fixed", 0)
        ):
            raise ValueError((name, "Failure-identity count mismatch", len(failures), summary))
        row = dict(
            name=name,
            exit_code=rc,
            binary_sha256=digest,
            execution=execution,
            summary=summary,
            seconds=time.monotonic() - start,
            tested=int(counts[2]),
            failed=int(counts[1]),
            counts=count_by_label,
            fixed_identities=sorted(fixed),
            failure_identities=sorted(failures),
            difference_lines=differences,
            stdout_sha256=sha(out / (name + ".stdout")),
            stderr_sha256=sha(out / (name + ".stderr")),
        )
        report["records"].append(row)
        report["active"] = None
        save()
        print("TEST262 COMPLETE", name, summary, flush=True)
    reference = report["records"][0]
    for row in report["records"]:
        row["introduced_vs_first"] = sorted(
            set(row["failure_identities"]) - set(reference["failure_identities"])
        )
        row["fixed_vs_first"] = sorted(
            set(reference["failure_identities"]) - set(row["failure_identities"])
        )
        row["same_test_count"] = row["tested"] == reference["tested"]
    # A changed error type can retain the same test identity. Equal counts or
    # identity sets must never hide that correctness difference.
    report["status"] = (
        "passed-no-new-failure-identities"
        if all(
            not r["introduced_vs_first"]
            and r["same_test_count"]
            and not r["counts"].get("new", 0)
            and not r["counts"].get("changed", 0)
            and not r["difference_lines"]
            for r in report["records"]
        )
        else "regression"
    )
    save()
    print("TEST262 COMPARISON", report["status"], flush=True)


if __name__ == "__main__":
    main()
