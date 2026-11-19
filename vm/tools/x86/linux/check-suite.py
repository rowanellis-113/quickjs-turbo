import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86

_act_x86()

"""Relink existing CTest hosts against the development archive, without
substituting portable-linked test binaries for candidate engine coverage.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portable", type=Path, required=True)
    ap.add_argument("--foundation", type=Path, required=True)
    a = ap.parse_args()
    portable, foundation = [p.resolve() for p in (a.portable, a.foundation)]
    out = foundation / "ctest"
    out.mkdir(exist_ok=False)
    suite = json.loads(
        subprocess.check_output(["ctest", "--test-dir", portable, "--show-only=json-v1"], text=True)
    )
    table = (portable / "CTestTestfile.cmake").read_text()
    targets = sorted(
        {
            Path(test["command"][0])
            for test in suite["tests"]
            if Path(test["command"][0]).parent == portable
        }
    )
    mappings = []
    for target in targets:
        if target.name == "qjs":
            replacement = foundation / "qjs"
            changed = True
        else:
            commands = subprocess.check_output(
                ["ninja", "-C", portable, "-t", "commands", target.name], text=True
            ).splitlines()
            link = next(
                (line for line in reversed(commands) if " -o " + target.name + " " in line), None
            )
            if link is None:
                raise ValueError("No native test link command for " + str(target))
            if " libqjs.a " not in link:
                replacement, changed = target, False
            else:
                replacement, changed = out / target.name, True
                args = shlex.split(link)
                first = next(
                    i
                    for i, v in enumerate(args)
                    if v in ("/usr/bin/gcc", "/usr/bin/cc", "/usr/bin/g++", "/usr/bin/c++")
                )
                args = args[first:]
                if args[-2:] == ["&&", ":"]:
                    args = args[:-2]
                args[args.index("-o") + 1] = str(replacement)
                args = [str(foundation / "libqjs.a") if v == "libqjs.a" else v for v in args]
                with (
                    (out / (target.name + ".link.stdout")).open("wb") as so,
                    (out / (target.name + ".link.stderr")).open("wb") as se,
                ):
                    subprocess.run(args, cwd=portable, stdout=so, stderr=se, check=True)
        if changed:
            table = table.replace('"' + str(target) + '"', '"' + str(replacement) + '"')
        mappings.append(
            dict(
                original=str(target),
                executed=str(replacement),
                candidate_linked=changed,
                sha256=sha(replacement),
            )
        )
    for test in suite["tests"]:
        wd = next(p["value"] for p in test["properties"] if p["name"] == "WORKING_DIRECTORY")
        table += (
            '\nset_tests_properties("'
            + test["name"]
            + '" PROPERTIES WORKING_DIRECTORY "'
            + wd
            + '")\n'
        )
    (out / "CTestTestfile.cmake").write_text(table)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    env["QJS_EXPERIMENT_ALLOCATOR"] = "256"
    with (out / "ctest.stdout").open("wb") as so, (out / "ctest.stderr").open("wb") as se:
        p = subprocess.run(
            [
                "ctest",
                "--test-dir",
                str(out),
                "--output-on-failure",
                "--parallel",
                "1",
                "--output-junit",
                str(out / "junit.xml"),
            ],
            env=env,
            stdout=so,
            stderr=se,
            timeout=600,
        )
    result = dict(
        status="passed" if p.returncode == 0 else "failed",
        exit_code=p.returncode,
        test_count=len(suite["tests"]),
        executable_mapping=mappings,
        original_manifest_sha256=sha(portable / "CTestTestfile.cmake"),
        manifest_sha256=sha(out / "CTestTestfile.cmake"),
        archive_sha256=sha(foundation / "libqjs.a"),
        register_vm=json.loads((foundation / "BUILD.json").read_text())["register_vm"],
        scope="Candidate-linked CTest execution; full feature and Test262 qualification remain separate",
    )
    (out / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    print("DEVELOPMENT FRAME SUITE", result["status"], result["test_count"], "tests")
    if p.returncode:
        print((out / "ctest.stdout").read_text()[-5000:])
        raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()
