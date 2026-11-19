"""Prove shared arena reuse and compiler TLS isolation with presence controls."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    a = ap.parse_args()
    source, candidate = a.source.resolve(), a.candidate.resolve()
    output = candidate / "shared-check"
    output.mkdir(exist_ok=False)
    binary = output / "shared-tls"
    subprocess.run(
        [
            "gcc",
            "-std=c11",
            "-O2",
            "-g",
            "-I" + str(source),
            source / "tests/common/linux/native_linux_shared_tls.c",
            candidate / "libqjs.a",
            "-lm",
            "-ldl",
            "-pthread",
            "-o",
            binary,
        ],
        check=True,
    )
    base = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    base["QJS_EXPERIMENT_ALLOCATOR"] = "256"
    records = []
    for mode, controls in [
        ("on", {}),
        ("off-zero", {"QJS_DISABLE_SHARED_ENTRY": "0"}),
        ("off-one", {"QJS_DISABLE_SHARED_ENTRY": "1"}),
        ("retained-scoped", {"QJS_RETAIN_SCOPED_HOST": "0"}),
    ]:
        env = dict(base, **controls)
        p = subprocess.run([binary], env=env, capture_output=True, text=True, timeout=30)
        (output / (mode + ".stdout")).write_text(p.stdout)
        (output / (mode + ".stderr")).write_text(p.stderr)
        records.append(
            dict(
                mode=mode,
                controls=controls,
                exit_code=p.returncode,
                passed=p.returncode == 0 and "LINUX_SHARED_TLS_OK" in p.stdout,
            )
        )
        print(mode, p.returncode, p.stdout, p.stderr, flush=True)
    passed = all(r["passed"] for r in records)
    (output / "RESULT.json").write_text(
        json.dumps(
            dict(
                status="passed" if passed else "failed",
                records=records,
                scope="Two independent runtimes/threads, shared child arena identity, GC in callback and presence controls",
            ),
            indent=2,
        )
        + "\n"
    )
    if not passed:
        raise ValueError("Shared arena/TLS check failed; retain logs")


if __name__ == "__main__":
    main()
