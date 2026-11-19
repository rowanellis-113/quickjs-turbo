"""Linux process adapter for retained JetStream subset and original V8-v7.

Workloads, calibration and validation are unchanged. External retained harnesses
are explicit inputs. Run correctness separately from serial reverse-order timing.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import statistics
import signal
import sys
import subprocess
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elf"))
from target_runner import (
    observe_process,
    source_identity,
    target_command,
    target_identity,
    verify_identity,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("suite", choices=["jetstream", "v8"])
    ap.add_argument("phase", choices=["prepare", "compatibility", "bench"])
    ap.add_argument("--harness", type=Path, required=True)
    ap.add_argument("--corpus", type=Path)
    ap.add_argument("--engines", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--proof", type=Path)
    ap.add_argument("--cases", help="Comma-separated explicit subset; default retained17")
    ap.add_argument("--iterations", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument(
        "--cpu", type=int, default=2, help="Explicit allowed CPU; default original CPU2"
    )
    ap.add_argument(
        "--blocks",
        type=int,
        choices=(1, 2),
        default=2,
        help="One quick block or original reversed pair; compatibility always one",
    )
    a = ap.parse_args()
    if a.timeout <= 0 or a.cpu not in os.sched_getaffinity(0):
        raise ValueError("Timeout must be positive and --cpu must be allowed")
    if a.iterations < 1 or (a.suite == "v8" and a.phase == "compatibility"):
        raise ValueError("V8 uses its original calibration; use v8 bench")
    aslr_mode = int(Path("/proc/sys/kernel/randomize_va_space").read_text())
    if a.phase == "bench" and aslr_mode == 0:
        raise ValueError("Timing requires normal kernel ASLR")
    output, harness = a.output.resolve(), a.harness.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prepared = output / "prepared"
    prepared.mkdir()
    engines = load(a.engines)
    if not engines or len({e["name"] for e in engines}) != len(engines):
        raise ValueError("Supply nonempty, uniquely named engine records")
    executions = {}
    for engine in engines:
        engine["binary"] = str(Path(engine["binary"]).resolve())
        actual_sha = sha(engine["binary"])
        if engine.get("sha256", actual_sha) != actual_sha:
            raise ValueError("Configured engine hash differs: " + engine["name"])
        engine["sha256"] = actual_sha
        if not isinstance(engine.get("arguments", []), list) or any(
            not isinstance(v, str) for v in engine.get("arguments", [])
        ):
            raise ValueError("Engine arguments must be a JSON string list")
        executions[engine["name"]] = target_identity(engine)
    bindings, configs, hosts = {}, {}, {}

    def bind(path):
        bindings[str(path)] = sha(path)

    bind(Path(__file__).resolve())
    bind(Path(__file__).resolve().parents[1] / "elf/target_runner.py")
    if a.suite == "jetstream":
        corpus = a.corpus.resolve()
        manifest_path = harness / "jetstream-selected18.json"
        runner = harness / "jetstream-selected-runner.js"
        manifest = load(manifest_path)
        corpus_binding = source_identity(corpus)
        revision = corpus_binding.get("commit") or corpus_binding.get("base_commit")
        if revision != manifest["revision"]:
            raise ValueError("JetStream pin differs")
        if (corpus / "SOURCE-TRANSFER.json").is_file():
            bind(corpus / "SOURCE-TRANSFER.json")
        bind(manifest_path)
        bind(runner)
        files = {}
        for relative, digest in manifest["files"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError(relative)
            path = corpus / relative
            if sha(path) != digest:
                raise ValueError("Retained corpus bytes differ: " + relative)
            bind(path)
            dest = prepared / relative.removesuffix(".z")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(
                zlib.decompress(path.read_bytes()) if relative.endswith(".z") else path.read_bytes()
            )
            files[relative] = str(dest)
            bind(dest)
        driver = corpus / "JetStreamDriver.js"
        bind(driver)
        text = driver.read_text()
        random_code = re.search(
            r"addDeterministicRandom\(\) \{\s*this\.add\(`(.*?)`\);", text, re.S
        )[1]
        random = prepared / "deterministic-random.js"
        random.write_text(text[: text.index("*/") + 2] + "\n" + random_code)
        bind(random)
        cases = [c for c in manifest["cases"] if c["name"] != "OfflineAssembler"]
        if a.cases:
            selected = a.cases.split(",")
            if not set(selected) <= {c["name"] for c in manifest["cases"]}:
                raise ValueError("Unknown case")
            cases = [c for c in manifest["cases"] if c["name"] in selected]
        checks = {}
        compatible = {}
        if a.phase == "bench":
            if not a.proof:
                raise ValueError("JetStream timing requires the matching compatibility report")
            proof = load(a.proof)
            if (
                proof["engines"] != engines
                or proof["harness_manifest_sha256"] != sha(manifest_path)
                or proof["harness_runner_sha256"] != sha(runner)
            ):
                raise ValueError("Compatibility bindings changed")
            checks = proof["checks"]
            compatible = {(r["case"], r["engine"]): r["passed"] for r in proof["records"]}
        for case in cases:
            config = dict(
                case,
                phase=a.phase,
                iterations=a.iterations,
                files=[files[f] for f in case["files"]],
                preload={k: files[v] for k, v in case["preload"].items()},
                randomScript=str(random) if case["deterministic_random"] else None,
                binaryPreloads={},
            )
            for key, path in config["preload"].items():
                if key.endswith(".wasm"):
                    config["binaryPreloads"][path] = list(Path(path).read_bytes())
            configs[case["name"]] = config
            host = output / (case["name"] + "-host.js")
            host.write_text(
                "globalThis.__jetExtra={config:"
                + json.dumps(config)
                + ",now:()=>os.now()/1000,read:p=>std.loadFile(p),load:p=>std.loadScript(p),"
                "flush:()=>std.out.flush(),readline:()=>std.in.getline(),exit:n=>std.exit(n)};\n"
                "__jetExtra.load(" + json.dumps(str(runner)) + ");\n"
            )
            hosts[case["name"]] = host
        names = list(configs)
    else:
        preparation = load(harness / "PREPARATION.json")
        if preparation["status"] != "passed":
            raise ValueError("V8 preparation missing")
        for path, digest in preparation["bindings"].items():
            win = PureWindowsPath(path)
            if "corpus" not in win.parts:
                continue
            relative = Path(*win.parts[win.parts.index("corpus") + 1 :])
            actual = harness / "corpus" / relative
            if sha(actual) != digest:
                raise ValueError("V8 source bytes differ: " + str(relative))
            bind(actual)
        original_host = harness / "v8-hosts/quickjs-ng.js"
        bind(original_host)
        text = original_host.read_text()
        text, count = re.subn(
            r'__v8Host\.load\("D:.*?combined\.js"\);',
            lambda _: "__v8Host.load(" + json.dumps(str(harness / "corpus/combined.js")) + ");",
            text,
        )
        if count != 1:
            raise ValueError("Expected one host-only path adaptation")
        host = output / "bench-v8-host.js"
        host.write_text(text)
        hosts, names, checks, compatible = {"bench-v8": host}, ["bench-v8"], {}, {}
    for path in hosts.values():
        bind(path)
    report = dict(
        status="running",
        suite=a.suite,
        phase=a.phase,
        engines=engines,
        bindings=bindings,
        cases=names,
        records=[],
        checks=checks,
        blocks=1 if a.phase == "compatibility" else a.blocks,
        affinity_cpu=a.cpu,
        normal_aslr=aslr_mode > 0,
        aslr_mode=aslr_mode,
        aslr_scope="Host kernel; guest layout under emulation is not hardware ASLR",
        host_platform=dict(zip(("system", "node", "release", "version", "machine"), os.uname())),
        PGO=False,
        executions=executions,
        emulated_engines=[n for n, e in executions.items() if e["runner"]],
        method="Unchanged retained workload/calibration; explicit CPU and blocks; emulator timing/RSS are host-emulator diagnostics,never physical guest performance",
    )
    if a.suite == "jetstream":
        report.update(
            harness_manifest_sha256=sha(manifest_path),
            harness_runner_sha256=sha(runner),
            corpus_revision=revision,
            corpus_identity=corpus_binding,
        )

    def save():
        (output / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    if a.phase == "prepare":
        report["status"] = "prepared-not-executed"
        save()
        print("LINUX SUITE INPUTS PREPARED", a.suite, len(bindings), flush=True)
        return

    def wait_marker(child, log, marker, deadline):
        while marker not in log.read_text().splitlines():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Process ended/timed out before " + marker)
            time.sleep(0.03)

    for block in range(report["blocks"]):
        order = [(name, e) for name in names for e in engines]
        if block % 2:
            order.reverse()
        for name, engine in order:
            if (
                a.suite == "jetstream"
                and a.phase == "bench"
                and not compatible.get((name, engine["name"]), False)
            ):
                report["records"].append(
                    dict(
                        block=block,
                        case=name,
                        engine=engine["name"],
                        passed=False,
                        error="Not compatibility-qualified",
                    )
                )
                save()
                continue
            run = output / (str(block) + "-" + name + "-" + engine["name"])
            run.mkdir()
            out, err = run / "stdout", run / "stderr"
            env = {
                k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))
            }
            env.update(QJS_EXPERIMENT_ALLOCATOR="256")
            env.update(engine.get("env", {}))
            execution = executions[engine["name"]]
            command = [
                "taskset",
                "-c",
                str(a.cpu),
                *target_command(execution, *engine.get("arguments", []), "--std", str(hosts[name])),
            ]
            peak_file = run / "engine-peak-rss-kib"
            if a.suite == "v8":
                command = ["/usr/bin/time", "-f", "%M", "-o", str(peak_file), *command]
            row = dict(
                block=block,
                case=name,
                engine=engine["name"],
                passed=False,
                command=command,
                execution_mode=execution["execution_mode"],
                pid_role="host-emulator" if execution["runner"] else "engine",
            )
            child = None
            start = time.monotonic()
            deadline = start + a.timeout
            print("START", block, name, engine["name"], flush=True)
            try:
                with out.open("wb") as so, err.open("wb") as se:
                    child = subprocess.Popen(
                        command,
                        cwd=output,
                        env=env,
                        stdin=subprocess.PIPE,
                        stdout=so,
                        stderr=se,
                        start_new_session=True,
                    )
                    row["wrapper_pid"] = child.pid
                    wait_marker(child, out, "READY " + name, deadline)
                    engine_pid = child.pid
                    if a.suite == "v8":
                        children = (
                            Path(
                                "/proc/" + str(child.pid) + "/task/" + str(child.pid) + "/children"
                            )
                            .read_text()
                            .split()
                        )
                        if len(children) != 1:
                            raise ValueError("Expected one GNU time engine child")
                        engine_pid = int(children[0])
                    row["pid"] = engine_pid
                    before = observe_process(execution, engine_pid)
                    if before["affinity"] != [a.cpu]:
                        raise ValueError("Observed CPU differs")
                    row["observed_process"] = {
                        k: v for k, v in before.items() if k not in ("maps", "status")
                    }
                    (run / "execution.json").write_text(
                        json.dumps(row["observed_process"], indent=2) + "\n"
                    )
                    (run / "before.maps").write_text(before["maps"])
                    (run / "before.status").write_text(before["status"])
                    child.stdin.write(b"GO\n")
                    child.stdin.flush()
                    if a.suite == "jetstream":
                        wait_marker(child, out, "MEASURED " + name, deadline)
                        after = observe_process(execution, engine_pid)
                        (run / "measured.status").write_text(after["status"])
                        key = (
                            "host_emulator_measured_peak_rss_kib"
                            if execution["runner"]
                            else "measured_peak_rss_kib"
                        )
                        row[key] = int(re.search(r"^VmHWM:\s+(\d+) kB", after["status"], re.M)[1])
                        row["memory_scope"] = (
                            "Host emulator VmHWM including TCG and guest;not guest engine RSS"
                            if execution["runner"]
                            else "Engine VmHWM at MEASURED,before supplemental validation"
                        )
                        child.stdin.write(b"CHECK\n")
                        child.stdin.flush()
                    child.stdin.close()
                    row["exit_code"] = child.wait(timeout=max(1, deadline - time.monotonic()))
                    if a.suite == "v8" and row["exit_code"] == 0:
                        value = peak_file.read_text().strip()
                        if not value.isdecimal() or int(value) <= 0:
                            raise ValueError("Missing actual engine peak RSS")
                        row[
                            "host_emulator_peak_rss_kib" if execution["runner"] else "peak_rss_kib"
                        ] = int(value)
                        row["memory_scope"] = (
                            "GNU time host-emulator peak including TCG/guest;not guest engine RSS"
                            if execution["runner"]
                            else "GNU time wait4 peak for actual engine child;includes original full suite/validation,excludes Python launcher"
                        )
                prefix = "DONE " if a.suite == "jetstream" else "RAW "
                rows = [
                    json.loads(line[len(prefix) :])
                    for line in out.read_text().splitlines()
                    if line.startswith(prefix)
                ]
                if row["exit_code"] or len(rows) != 1 or err.read_bytes():
                    raise ValueError("Engine/harness failed; inspect retained logs")
                raw = rows[0]
                row["raw"] = raw
                if a.suite == "jetstream":
                    if (
                        not raw["supplemental_validation_completed"]
                        or raw["name"] != name
                        or raw["phase"] != a.phase
                    ):
                        raise ValueError("Validation incomplete")
                    if name in checks and raw["checks"] != checks[name]:
                        raise ValueError("Cross-image output differs")
                    checks[name] = raw["checks"]
                    if a.phase == "bench":
                        if len(raw["samples"]) != a.iterations:
                            raise ValueError("Missing original iterations")
                        row["body_ms"] = statistics.mean(s["body_ms"] for s in raw["samples"])
                        row["cycle_ms"] = raw["warm_elapsed_ms"] / a.iterations
                        if not math.isfinite(row["body_ms"]) or row["body_ms"] <= 0:
                            raise ValueError("Invalid measured time")
                elif raw["version"] != "7" or raw["original_errors"] or len(raw["cases"]) != 8:
                    raise ValueError("Original V8 calibration/validation failed")
                verify_identity(execution)
                if sha(engine["binary"]) != engine["sha256"]:
                    raise ValueError("Measured image changed")
                row["passed"] = True
            except Exception as exc:
                row["error"] = repr(exc)
            finally:
                if child is not None and child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            row["seconds"] = time.monotonic() - start
            report["records"].append(row)
            save()
            print(
                "DONE" if row["passed"] else "FAILED",
                block,
                name,
                engine["name"],
                round(row.get("body_ms", row["seconds"]), 3),
                flush=True,
            )
    for path, digest in bindings.items():
        if sha(path) != digest:
            raise ValueError("Input changed during suite: " + path)
    report["status"] = "passed" if all(r["passed"] for r in report["records"]) else "partial"
    save()
    print("LINUX SUITE", a.suite, a.phase, report["status"], output / "RESULT.json", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
