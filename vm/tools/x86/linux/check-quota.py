"""Public-API quota/reentry test against original and development archives."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--foundation", type=Path, required=True)
    ap.add_argument("--portable", type=Path, required=True)
    a = ap.parse_args()
    source, foundation, portable = [p.resolve() for p in (a.source, a.foundation, a.portable)]
    out = foundation / "quota-check"
    out.mkdir(exist_ok=False)
    obj = out / "quota.o"
    subprocess.run(
        [
            "gcc",
            "-std=c11",
            "-O2",
            "-g",
            "-I" + str(source),
            "-c",
            str(source / "tests/common/linux/native_linux_frame_quota.c"),
            "-o",
            str(obj),
        ],
        check=True,
    )
    records = []
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    env["QJS_EXPERIMENT_ALLOCATOR"] = "256"
    for mode, library in [
        ("portable", portable / "libqjs.a"),
        ("foundation", foundation / "libqjs.a"),
    ]:
        binary = out / mode
        subprocess.run(
            ["gcc", str(obj), str(library), "-lm", "-ldl", "-pthread", "-o", str(binary)],
            check=True,
        )
        p = subprocess.run([str(binary)], capture_output=True, text=True, env=env, timeout=20)
        records.append(dict(mode=mode, exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr))
        print(mode, p.returncode, p.stdout, p.stderr, flush=True)
    passed = all(
        r["exit_code"] == 0 and "LINUX_FRAME_QUOTA_REENTRY_INTERRUPT_OK" in r["stdout"]
        for r in records
    )
    (out / "RESULT.json").write_text(
        json.dumps(dict(status="passed" if passed else "failed", records=records), indent=2) + "\n"
    )
    if not passed:
        raise ValueError("Quota/reentry/interrupt behavior failed; retain this result")


if __name__ == "__main__":
    main()
