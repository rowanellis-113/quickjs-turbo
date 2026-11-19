"""Run the pinned extra JetStream workloads in four engines (five build roles).

Only external workload/host adaptation; no engine modifications. Windows CPU2,
ordinary ASLR, serial runs and exactly reversed block order. Not official scores.
"""

import argparse
import ctypes
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
import zlib
from jetstream_launch import environment, observe_process, kernel

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bound(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path), bytes=Path(path).stat().st_size)


def memory(pid):
    from ctypes import wintypes as W

    class Counters(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [
            (k, ctypes.c_size_t)
            for k in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
                "PrivateUsage",
            )
        ]

    handle = kernel.OpenProcess(0x0410, False, pid)
    assert handle
    try:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(Counters), W.DWORD]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        assert psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb)
        return {
            k: getattr(value, k)
            for k in ("PeakWorkingSetSize", "WorkingSetSize", "PrivateUsage", "PeakPagefileUsage")
        }
    finally:
        kernel.CloseHandle(handle)


def prepare(corpus, manifest, output):
    revision = subprocess.check_output(
        ["git", "-C", str(corpus), "rev-parse", "HEAD"], text=True
    ).strip()
    assert revision == manifest["revision"]
    prepared = output / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    bindings = {}
    files = {}
    for relative, digest in manifest["files"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        source = corpus / relative
        assert sha(source) == digest, relative
        bindings[str(source.resolve())] = digest
        dest = source
        if relative.endswith(".z"):
            dest = prepared / relative[:-2]
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = zlib.decompress(source.read_bytes())
            if not dest.exists() or dest.read_bytes() != data:
                dest.write_bytes(data)
        files[relative] = str(dest.resolve())
        bindings[str(dest.resolve())] = sha(dest)
    driver = (corpus / "JetStreamDriver.js").read_text(encoding="utf-8")
    code = re.search(r"addDeterministicRandom\(\) \{\s*this\.add\(`(.*?)`\);", driver, re.S).group(
        1
    )
    random = prepared / "deterministic-random.js"
    random.write_text(driver[: driver.index("*/") + 2] + "\n" + code, encoding="utf-8")
    bindings[str(random)] = sha(random)
    for name in (
        "jetstream-extra.py",
        "jetstream-extra-runner.js",
        "jetstream_launch.py",
        "jetstream-extra8.json",
    ):
        path = HERE / name
        bindings[str(path)] = sha(path)
    result = dict(revision=revision, bindings=bindings, files=files, random=str(random))
    write(prepared / "INPUTS.json", result)
    return result


def make_host(config, image, path):
    common = "config:" + json.dumps(config, separators=(",", ":"))
    engine = image["engine"]
    if engine == "node":
        code = """const fs=require('node:fs'),vm=require('node:vm');
const nativePerformance=require('node:perf_hooks').performance;
globalThis.print=(...v)=>fs.writeSync(1,v.map(String).join(' ')+'\\n');
globalThis.__jetExtra={@CONFIG@,now:()=>nativePerformance.now(),read:p=>fs.readFileSync(p,'utf8'),
 load:p=>vm.runInThisContext(fs.readFileSync(p,'utf8'),{filename:p}),flush:()=>{},exit:n=>process.exit(n),
 readline:()=>{let s='',b=Buffer.alloc(1);while(fs.readSync(0,b,0,1,null)){if(b[0]===10)break;s+=b.toString('utf8');}return s.replace(/\\r$/,'');}};
""".replace("@CONFIG@", common)
    else:
        adapter = (
            "now:()=>$.agent.monotonicNow(),read:p=>readFile(p),load:p=>loadString(readFile(p)),flush:()=>{},readline:()=>readline(),exit:n=>quit(n)"
            if engine == "jsc"
            else ("now:()=>os.now()/1000," if engine == "quickjs-ng" else "now:()=>os.now(),")
            + "read:p=>std.loadFile(p),load:p=>std.loadScript(p),flush:()=>std.out.flush(),readline:()=>std.in.getline(),exit:n=>std.exit(n)"
        )
        code = "globalThis.__jetExtra={" + common + "," + adapter + "};\n"
    code += "__jetExtra.load(" + json.dumps(str(HERE / "jetstream-extra-runner.js")) + ");\n"
    path.write_text(code, encoding="utf-8")


def wait_marker(child, path, marker, deadline):
    last = time.monotonic()
    while True:
        if marker in path.read_text(encoding="utf-8", errors="replace").splitlines():
            return
        if child.poll() is not None:
            raise RuntimeError("Process ended before " + marker)
        if time.monotonic() > deadline:
            raise TimeoutError(marker)
        if time.monotonic() - last > 20:
            print("RUNNING", child.pid, marker, flush=True)
            last = time.monotonic()
        time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "compatibility", "bench"))
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--manifest", type=Path, default=HERE / "jetstream-extra8.json")
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--cases")
    parser.add_argument("--only-images")
    a = parser.parse_args()
    assert os.name == "nt", "This runner records Windows module identities and CPU affinity"
    assert a.iterations >= 1
    a.output.mkdir(parents=True, exist_ok=True)
    manifest = read(a.manifest)
    prepared = prepare(a.corpus, manifest, a.output)
    if a.phase == "prepare":
        print("PREPARED", a.output / "prepared")
        return
    images = read(a.images)["images"]
    cases = manifest["cases"]
    if a.cases:
        names = a.cases.split(",")
        assert set(names) <= {c["name"] for c in cases}
        cases = [c for c in cases if c["name"] in names]
    if a.only_images:
        names = a.only_images.split(",")
        assert set(names) <= {i["name"] for i in images}
        images = [i for i in images if i["name"] in names]
    assert images and cases
    checks = {}
    if a.phase == "bench":
        assert a.proof, "A successful compatibility report is required"
        proof = read(a.proof)
        assert proof["status"] == "passed" and proof["phase"] == "compatibility"
        assert proof["images"] == images and proof["cases"] == [c["name"] for c in cases]
        assert proof["bindings"] == prepared["bindings"], (
            "Harness or inputs changed since compatibility"
        )
        checks = proof["checks"]
        # Refuse timing alongside the user's disk cleanup or compiler activity.
        query = "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('cl.exe','ninja.exe','cmake.exe','MSBuild.exe','cc1.exe','cc1plus.exe') -or ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match '-File\\s+[^\\r\\n]*Clean-ProductOnly.ps1.*-Execute') } | Select-Object -ExpandProperty ProcessId"
        busy = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", query], text=True
        ).strip()
        assert not busy, ("Stop/wait for active build or cleanup before timing", busy)
    for image in images:
        for item in [image, *image.get("modules_and_symbols", [])]:
            assert sha(item["path"]) == item["sha256"]
    kernel.SetErrorMode(0x8003)
    assert kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(), 1)
    folder = a.output / (a.phase + "-" + str(time.time_ns()))
    folder.mkdir()
    hosts = folder / "shared-hosts"
    hosts.mkdir()
    report = dict(
        schema=1,
        status="running",
        phase=a.phase,
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        images=images,
        cases=[c["name"] for c in cases],
        manifest=bound(a.manifest),
        bindings=prepared["bindings"],
        records=[],
        checks=checks,
        iterations=a.iterations if a.phase == "bench" else 0,
        blocks=2 if a.phase == "bench" else 1,
        method="Original full runIteration; preparation and random reset unchanged; cold1, warmup1, measured iterations; primary body time excludes prepare; warm_elapsed includes prepare/await. Canonical per-case/per-engine host path and identical host bytes across image roles and blocks, with a common working directory. CPU2 serial exact reversed blocks; normal ASLR; supplemental validation outside timings and peak-memory observation.",
        corpus_revision=manifest["revision"],
        source_state={},
    )
    product = HERE.parents[2]
    if (product / "CMakeLists.txt").exists():
        report["source_state"] = {
            key: subprocess.check_output(["git", "-C", str(product), *command], text=True).strip()
            for key, command in [
                ("commit", ["rev-parse", "HEAD"]),
                ("status", ["status", "--porcelain"]),
            ]
        }
    output = folder / "RESULTS.json"
    write(output, report)
    for block in range(report["blocks"]):
        ordered = [(case, image) for case in cases for image in images]
        if block % 2:
            ordered.reverse()
        for case, image in ordered:
            name = case["name"]
            run = folder / f"{block}-{name}-{image['name']}"
            run.mkdir()
            config = dict(
                case,
                phase=a.phase,
                iterations=a.iterations,
                files=[prepared["files"][f] for f in case["files"]],
                preload={k: prepared["files"][v] for k, v in case["preload"].items()},
                randomScript=prepared["random"] if case["deterministic_random"] else None,
                binaryPreloads={},
            )
            for key, path in config["preload"].items():
                if key.endswith(".wasm"):
                    config["binaryPreloads"][path] = list(Path(path).read_bytes())
            extension = ".cjs" if image["engine"] == "node" else ".js"
            draft = run / ("host" + extension)
            make_host(config, image, draft)
            host = hosts / (name + "-" + image["engine"] + extension)
            if host.exists():
                assert host.read_bytes() == draft.read_bytes(), (
                    "Host bytes differ across image roles"
                )
            else:
                host.write_bytes(draft.read_bytes())
            out = run / "stdout.log"
            err = run / "stderr.log"
            command = [image["path"], *image["arguments"], str(host)]
            row = dict(
                block=block,
                case=name,
                image=image["name"],
                command=command,
                cwd=str(folder),
                host=bound(host),
                host_source_copy=bound(draft),
                passed=False,
            )
            child = None
            start = time.monotonic()
            print("START", block, name, image["name"], flush=True)
            try:
                with out.open("wb") as so, err.open("wb") as se:
                    assert kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(), 4)
                    try:
                        child = subprocess.Popen(
                            command,
                            cwd=folder,
                            env=environment(image),
                            stdin=subprocess.PIPE,
                            stdout=so,
                            stderr=se,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    finally:
                        assert kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(), 1)
                    row["pid"] = child.pid
                    deadline = start + a.timeout
                    wait_marker(child, out, "READY " + name, deadline)
                    row["observed"] = observe_process(child.pid, image)
                    actual = {
                        str(Path(m["path"]).resolve()).lower() for m in row["observed"]["modules"]
                    }
                    assert str(Path(image["path"]).resolve()).lower() in actual
                    for module in row["observed"]["modules"]:
                        module["sha256"] = sha(module["path"])
                    if image["engine"] == "jsc":
                        core = next(
                            m
                            for m in image["modules_and_symbols"]
                            if Path(m["path"]).name.lower() == "libjavascriptcore.dll"
                        )
                        assert str(Path(core["path"]).resolve()).lower() in actual
                    row["memory_before"] = memory(child.pid)
                    child.stdin.write(b"GO\n")
                    child.stdin.flush()
                    wait_marker(child, out, "MEASURED " + name, deadline)
                    row["memory_after_measured"] = memory(child.pid)
                    child.stdin.write(b"CHECK\n")
                    child.stdin.flush()
                    child.stdin.close()
                    row["exit_code"] = child.wait(timeout=max(1, deadline - time.monotonic()))
                rawlines = [
                    line[5:]
                    for line in out.read_text(encoding="utf-8").splitlines()
                    if line.startswith("DONE ")
                ]
                assert row["exit_code"] == 0 and len(rawlines) == 1
                result = json.loads(rawlines[0])
                row["result"] = result
                assert (
                    result["name"] == name
                    and result["phase"] == a.phase
                    and result["supplemental_validation_completed"]
                )
                values = [result["cold"]["body_ms"], *[s["body_ms"] for s in result["samples"]]]
                assert all(math.isfinite(v) and v > 0 for v in values)
                if name not in checks:
                    checks[name] = result["checks"]
                assert checks[name] == result["checks"], ("Cross-engine validation mismatch", name)
                if a.phase == "bench":
                    assert len(result["samples"]) == a.iterations
                    row["body_ms"] = statistics.mean(s["body_ms"] for s in result["samples"])
                    row["cycle_ms"] = result["warm_elapsed_ms"] / a.iterations
                row["passed"] = True
            except Exception as exc:
                row["error"] = repr(exc)
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait()
                row["stdout_tail"] = (
                    out.read_text(encoding="utf-8", errors="replace")[-3000:]
                    if out.exists()
                    else ""
                )
                row["stderr_tail"] = (
                    err.read_text(encoding="utf-8", errors="replace")[-3000:]
                    if err.exists()
                    else ""
                )
            finally:
                row["seconds"] = time.monotonic() - start
                if out.exists():
                    row["stdout"] = bound(out)
                if err.exists():
                    row["stderr"] = bound(err)
                report["records"].append(row)
                write(output, report)
            print(
                "DONE" if row["passed"] else "FAILED",
                block,
                name,
                image["name"],
                round(row.get("body_ms", row["seconds"]), 3),
                flush=True,
            )
            if not row["passed"]:
                print(row.get("error"), row.get("stdout_tail"), row.get("stderr_tail"), flush=True)
    for path, digest in prepared["bindings"].items():
        assert sha(path) == digest, path
    for image in images:
        for item in [image, *image.get("modules_and_symbols", [])]:
            assert sha(item["path"]) == item["sha256"]
    report["status"] = "passed" if all(r["passed"] for r in report["records"]) else "failed"
    report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write(output, report)
    write(a.output / ("LATEST-" + a.phase.upper() + ".json"), bound(output))
    print("REPORT", output, report["status"], flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
