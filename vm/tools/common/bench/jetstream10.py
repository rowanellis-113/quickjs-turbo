"""Pinned JetStream application subset for QuickJS shells, not official scores."""

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


p = argparse.ArgumentParser(description=__doc__)
p.add_argument("phase", choices=("prepare", "quick", "stable"))
p.add_argument("--corpus", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
p.add_argument("--images", type=Path)
p.add_argument("--manifest", type=Path, default=HERE / "jetstream10.json")
p.add_argument("--cases")
p.add_argument("--only-images")
p.add_argument("--rounds", type=int)
p.add_argument("--iterations", type=int, default=2)
p.add_argument("--warmups", type=int, default=1)
p.add_argument("--timeout", type=int, default=300)
a = p.parse_args()
assert a.iterations >= 1 and a.warmups >= 1
manifest = read(a.manifest)
revision = subprocess.check_output(
    ["git", "-C", str(a.corpus), "rev-parse", "HEAD"], text=True
).strip()
assert revision == manifest["revision"], (revision, manifest["revision"])
for relative, expected in manifest["files"].items():
    assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
    assert sha(a.corpus / relative) == expected, relative
prepared = a.output / "prepared"
prepared.mkdir(parents=True, exist_ok=True)
files = {}
for relative in manifest["files"]:
    original = a.corpus / relative
    if relative.endswith(".z"):
        dest = prepared / "assets" / relative[:-2]
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = zlib.decompress(original.read_bytes())
        if not dest.exists() or dest.read_bytes() != content:
            dest.write_bytes(content)
        files[relative] = str(dest.resolve())
    else:
        files[relative] = str(original.resolve())
driver = (a.corpus / "JetStreamDriver.js").read_text(encoding="utf-8")
import re

random_code = re.search(r"addDeterministicRandom\(\) \{\s*this\.add\(`(.*?)`\);", driver, re.S)
assert random_code
random_script = prepared / "deterministic-random.js"
license_header = driver[: driver.index("*/") + 2]
random_script.write_text(license_header + "\n" + random_code[1], encoding="utf-8")
write(
    prepared / "INPUTS.json",
    dict(
        revision=revision,
        manifest_sha256=sha(a.manifest),
        originals={
            key: dict(path=str(a.corpus / key), sha256=value)
            for key, value in manifest["files"].items()
        },
        prepared={key: dict(path=value, sha256=sha(value)) for key, value in files.items()},
        random_script_sha256=sha(random_script),
    ),
)
if a.phase == "prepare":
    print("PREPARED", prepared, flush=True)
    raise SystemExit(0)
assert a.images
images = read(a.images)["images"]
if a.only_images:
    names = a.only_images.split(",")
    assert set(names) <= {image["name"] for image in images}
    images = [image for image in images if image["name"] in names]
assert images
for image in images:
    assert sha(image["path"]) == image["sha256"], image["name"]
cases = manifest["cases"]
if a.cases:
    names = a.cases.split(",")
    assert set(names) <= {case["name"] for case in cases}
    cases = [case for case in cases if case["name"] in names]
rounds = a.rounds or (2 if a.phase == "stable" else 1)
folder = a.output / (a.phase + "-" + str(time.time_ns()))
folder.mkdir()
env = {key: value for key, value in os.environ.items() if not key.startswith("QJS_")}
if os.name == "nt":
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    affinity = ctypes.windll.kernel32.SetProcessAffinityMask
    affinity.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    affinity.restype = ctypes.c_int
records, checks = [], {}
case_positions = {case["name"]: i for i, case in enumerate(cases)}
print("RUN", folder, "processes", rounds * len(cases) * len(images), flush=True)
for block in range(rounds):
    for case in cases if block % 2 == 0 else reversed(cases):
        case_index = case_positions[case["name"]]
        order = images[case_index % len(images) :] + images[: case_index % len(images)]
        if block % 2:
            order = list(reversed(order))
        for image in order:
            run = folder / f"{block}-{case['name']}-{image['name']}"
            run.mkdir()
            config = dict(
                case,
                phase=a.phase,
                iterations=a.iterations,
                warmups=a.warmups,
                files=[files[f] for f in case["files"]],
                preload={key: files[value] for key, value in case.get("preload", {}).items()},
                randomScript=str(random_script.resolve())
                if case.get("deterministic_random")
                else None,
                runner=str((HERE / "jetstream10-runner.js").resolve()),
            )
            write(run / "config.json", config)
            command = [
                image["path"],
                str(HERE / "jetstream10.mjs"),
                str((run / "config.json").resolve()),
            ]
            childenv = dict(env, **image.get("environment", {}))
            start = time.monotonic()
            child = subprocess.Popen(
                command,
                cwd=a.corpus,
                env=childenv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if os.name == "nt":
                assert affinity(int(child._handle), 4)
            try:
                while True:
                    try:
                        stdout, stderr = child.communicate(timeout=20)
                        break
                    except subprocess.TimeoutExpired:
                        print(
                            "RUNNING",
                            block,
                            case["name"],
                            image["name"],
                            round(time.monotonic() - start),
                            flush=True,
                        )
                        if time.monotonic() - start > a.timeout:
                            child.kill()
                            stdout, stderr = child.communicate()
                            break
            except BaseException:
                child.kill()
                child.communicate()
                raise
            (run / "stdout.log").write_bytes(stdout)
            (run / "stderr.log").write_bytes(stderr)
            result_lines = [
                line[len("JETSTREAM10_RESULT ") :]
                for line in stdout.decode("utf-8", "replace").splitlines()
                if line.startswith("JETSTREAM10_RESULT ")
            ]
            row = dict(
                block=block,
                case=case["name"],
                image=image["name"],
                toolchain=image["toolchain"],
                command=command,
                environment=image.get("environment", {}),
                image_sha256=image["sha256"],
                exit_code=child.returncode,
                seconds=time.monotonic() - start,
                stdout=str(run / "stdout.log"),
                stderr=str(run / "stderr.log"),
                passed=False,
            )
            if child.returncode == 0 and len(result_lines) == 1:
                result = json.loads(result_lines[0])
                assert result["name"] == case["name"] and result["phase"] == a.phase
                assert all(math.isfinite(x) and x > 0 for x in result["samples_ms"])
                if case["name"] not in checks:
                    checks[case["name"]] = result["checks"]
                assert checks[case["name"]] == result["checks"], (
                    case["name"],
                    image["name"],
                    "output differs",
                )
                row.update(
                    passed=True, result=result, median_ms=statistics.median(result["samples_ms"])
                )
            records.append(row)
            write(folder / "RUNS.json", records)
            print(
                "BENCH",
                block,
                case["name"],
                image["name"],
                "OK" if row["passed"] else "FAILED",
                round(row.get("median_ms", 0), 3),
                "ms",
                flush=True,
            )
            if not row["passed"]:
                print(stderr.decode("utf-8", "replace")[-1800:], flush=True)
summary = {}
for image in images:
    medians = {}
    for case in cases:
        rows = [r for r in records if r["image"] == image["name"] and r["case"] == case["name"]]
        if len(rows) == rounds and all(r["passed"] for r in rows):
            medians[case["name"]] = dict(
                ms=statistics.median(r["median_ms"] for r in rows),
                samples_ms=[r["median_ms"] for r in rows],
                cold_ms=statistics.median(r["result"]["cold_ms"] for r in rows),
                load_ms=statistics.median(r["result"]["load_ms"] for r in rows),
            )
    summary[image["name"]] = medians
for image in images:
    assert sha(image["path"]) == image["sha256"]
report = dict(
    schema=1,
    phase=a.phase,
    rounds=rounds,
    iterations=a.iterations,
    warmups=a.warmups,
    images=images,
    cases=[case["name"] for case in cases],
    summary=summary,
    records=records,
    checks=checks,
    host=platform.platform(),
    source_revision=revision,
    manifest_sha256=sha(a.manifest),
    inputs=str(prepared / "INPUTS.json"),
    harness_sha256={
        f: sha(HERE / f) for f in ("jetstream10.py", "jetstream10.mjs", "jetstream10-runner.js")
    },
    policy="Whole original runIteration; unmodified workload files; CPU2; serial rotated/reversed cohorts; ordinary ASLR. Subset timings, not official JetStream scores.",
)
write(folder / "RESULTS.json", report)
write(a.output / ("LATEST-" + a.phase.upper() + ".json"), dict(report=str(folder / "RESULTS.json")))
print("REPORT", folder / "RESULTS.json", flush=True)
raise SystemExit(0 if all(r["passed"] for r in records) else 1)
