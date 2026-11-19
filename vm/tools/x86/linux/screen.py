import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, source_file

_act_x86()

"""Short serial, reverse-order Linux screen using unchanged upstream calibration.

This filters candidates; two blocks do not establish a stable performance claim.
Keep raw ns/op, process identity, mapped image addresses and peak RSS.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import time

from target_runner import source_identity, target_command, target_identity, verify_identity


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument(
        "--engines",
        type=Path,
        required=True,
        help="JSON list: name, binary, optional env and receipt paths",
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--cpu", type=int, default=2, help="Allowed CPU; default original CPU 2")
    selection = ap.add_mutually_exclusive_group()
    selection.add_argument(
        "--cases",
        nargs="+",
        default=["func_call", "closure_var", "int_arith", "float_arith", "string_concat0"],
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Run the original full test_list once per image, with no prefix expansion",
    )
    a = ap.parse_args()
    if a.cpu not in os.sched_getaffinity(0):
        raise ValueError("Selected CPU is not allowed")
    source, output = a.source.resolve(), a.output.resolve()
    source_binding = source_identity(source)
    output.mkdir(parents=True, exist_ok=False)
    engines = json.loads(a.engines.read_text())
    executions = {e["name"]: target_identity(e) for e in engines}
    emulated = any(e["runner"] for e in executions.values())
    workload = source_file(source, "tests/microbench.js")
    if a.all:
        text = workload.read_text()
        lists = re.findall(r"\bvar test_list\s*=\s*\[(.*?)\n\s*\];", text, re.S)
        if len(lists) != 1:
            raise ValueError("Review changed upstream test_list syntax")
        body = re.sub(r"/\*.*?\*/|//[^\n]*", "", lists[0], flags=re.S)
        a.cases = [item.strip() for item in body.split(",") if item.strip()]
        a.cases += re.findall(r"\btest_list\.push\((\w+)\);", text)
        if (
            not a.cases
            or len(set(a.cases)) != len(a.cases)
            or any(not re.fullmatch(r"\w+", name) for name in a.cases)
        ):
            raise ValueError("Review changed upstream test_list entries")
        for engine in engines:
            capability = subprocess.check_output(
                target_command(executions[engine["name"]], "-e", "print(typeof BigInt)"), text=True
            ).strip()
            if capability != "function":
                raise ValueError(
                    "Full common micro profile requires BigInt on each image: " + engine["name"]
                )
    hashes = {name: e["binary_sha256"] for name, e in executions.items()}
    manifest = dict(
        kind="emulated-functional-timing-not-hardware-performance"
        if emulated
        else "quick-screen-not-stable",
        execution=executions,
        workload=str(workload),
        workload_sha256=sha(workload),
        cases=a.cases,
        engines=engines,
        binary_sha256=hashes,
        source_commit=source_binding["commit"],
        source_dirty=source_binding["dirty"],
        source_identity=source_binding,
        affinity_cpu=a.cpu,
        original_full_list=a.all,
        normal_aslr=Path("/proc/sys/kernel/randomize_va_space").read_text().strip(),
    )
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for block, order in enumerate((engines, list(reversed(engines))), 1):
        for engine in order:
            name = engine["name"]
            binary = Path(engine["binary"]).resolve()
            execution = executions[name]
            mapped_image = execution.get("emulator", execution)["binary"]
            env = {
                k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))
            }
            env.update(QJS_EXPERIMENT_ALLOCATOR="256")
            env.update(engine.get("env", {}))
            stem = output / (str(block) + "-" + name)
            started = time.time()
            rss_file = stem.with_suffix(".rss")
            args = [
                "/usr/bin/time",
                "-f",
                "%M",
                "-o",
                str(rss_file),
                "taskset",
                "-c",
                str(a.cpu),
                *target_command(execution, workload, *([] if a.all else a.cases)),
            ]
            with (
                stem.with_suffix(".stdout").open("wb") as so,
                stem.with_suffix(".stderr").open("wb") as se,
            ):
                p = subprocess.Popen(
                    args, cwd=output, env=env, stdout=so, stderr=se, start_new_session=True
                )
                time.sleep(0.04)
                try:
                    children = (
                        Path("/proc/" + str(p.pid) + "/task/" + str(p.pid) + "/children")
                        .read_text()
                        .split()
                    )
                    if len(children) != 1:
                        raise ValueError("Expected one time-wrapper child")
                    engine_pid = int(children[0])
                    if (
                        str(Path("/proc/" + str(engine_pid) + "/exe").resolve(strict=True))
                        != mapped_image
                    ):
                        raise ValueError("Unexpected mapped execution image")
                    maps = Path("/proc/" + str(engine_pid) + "/maps").read_text()
                    maps = (
                        "\n".join(line for line in maps.splitlines() if mapped_image in line) + "\n"
                    )
                except FileNotFoundError:
                    maps = ""
                except Exception:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    p.wait()
                    raise
                stem.with_suffix(".maps").write_text(maps)
                while True:
                    child, status, usage = os.wait4(p.pid, os.WNOHANG)
                    if child:
                        p.returncode = os.waitstatus_to_exitcode(status)
                        break
                    if time.time() - started > engine.get("timeout_seconds", 900 if a.all else 180):
                        try:
                            os.killpg(p.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        child, status, usage = os.wait4(p.pid, 0)
                        p.returncode = os.waitstatus_to_exitcode(status)
                        raise TimeoutError(name)
                    time.sleep(0.05)
            text = stem.with_suffix(".stdout").read_text()
            verify_identity(execution)
            values = {
                m[1]: float(m[2])
                for m in re.finditer(r"^\s*(\w+)\s+\d+\s+([\d.]+)\s*$", text, re.M)
            }
            if (
                p.returncode
                or set(values) != set(a.cases)
                or not maps
                or sha(binary) != hashes[name]
            ):
                raise ValueError((name, p.returncode, values, "inspect retained raw evidence"))
            row = dict(
                block=block,
                engine=name,
                pid=engine_pid,
                wrapper_pid=p.pid,
                execution=execution,
                mapped_image=mapped_image,
                pid_role="host-emulator" if execution["runner"] else "engine",
                started_unix=started,
                elapsed_seconds=time.time() - started,
                command=args,
                environment_controls={k: v for k, v in env.items() if k.startswith("QJS_")},
                ns_per_op=values,
                peak_rss_kib=int(rss_file.read_text().strip()),
                peak_rss_scope="GNU time emulator process including translated code/cache; not engine-only memory"
                if execution["runner"]
                else "GNU time wait4 for engine child; excludes Python launcher RSS floor",
            )
            rows.append(row)
            (output / "SAMPLES.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(block, name, values, "RSS KiB", row["peak_rss_kib"], flush=True)
    summary = {
        e["name"]: {
            case: statistics.median(r["ns_per_op"][case] for r in rows if r["engine"] == e["name"])
            for case in a.cases
        }
        for e in engines
    }
    (output / "RESULT.json").write_text(
        json.dumps(dict(status="quick-screen-complete", ns_per_op=summary), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
