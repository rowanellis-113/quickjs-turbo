"""Prove owned-frame execution/disable paths, separately from performance."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--entry-only", action="store_true")
    ap.add_argument("--register-vm", action="store_true")
    ap.add_argument("--internal-control", action="store_true")
    a = ap.parse_args()
    source, output = a.source.resolve(), a.output.resolve()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    env["QJS_EXPERIMENT_ALLOCATOR"] = "256"
    rows = []
    fixture = "test_linux_internal_entry.js" if a.entry_only else "test_linux_frame_foundation.js"
    marker = "LINUX_INTERNAL_ENTRY_OK" if a.entry_only else "LINUX_FRAME_FOUNDATION_OK"
    modes = ("on", "register-off-zero", "off-zero") if a.register_vm else ("on", "off-zero")
    if a.internal_control:
        if not a.entry_only:
            raise ValueError("Internal routing control proof requires the pure-JS entry fixture")
        modes += ("internal-off-zero", "internal-off-one")
    for mode in modes:
        control = {
            "on": "",
            "register-off-zero": "set env QJS_DISABLE_REGISTER_INTERP 0\n",
            "off-zero": "set env QJS_DISABLE_INTERP_FRAME 0\n",
            "internal-off-zero": "set env QJS_DISABLE_INTERNAL_INTERP 0\n",
            "internal-off-one": "set env QJS_DISABLE_INTERNAL_INTERP 1\n",
        }[mode]
        gdb = output / ("path-" + mode + ".gdb")
        register = (
            (
                'break qjs_linux_vm_enter_private\ncommands\nsilent\nprintf "LINUX_REGISTER_VM_HIT\\n"\n'
                "bt 8\ndisable 2\ncontinue\nend\n"
            )
            if a.register_vm
            else ""
        )
        gdb.write_text(
            "set pagination off\nset confirm off\nset disable-randomization off\n"
            + control
            + 'break JS_RunFrame\ncommands\nsilent\nprintf "LINUX_OWNED_FRAME_HIT\\n"\ndisable 1\ncontinue\nend\n'
            + register
            + "run --std "
            + str(source / "tests" / fixture)
            + "\n"
        )
        p = subprocess.run(
            ["gdb", "--batch", "-x", str(gdb), str(output / "qjs")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        (output / ("path-" + mode + ".stdout")).write_text(p.stdout)
        (output / ("path-" + mode + ".stderr")).write_text(p.stderr)
        hit = "LINUX_OWNED_FRAME_HIT" in p.stdout
        vm_hit = "LINUX_REGISTER_VM_HIT" in p.stdout
        expected_frame = mode in ("on", "register-off-zero")
        if (
            p.returncode
            or marker not in p.stdout
            or hit != expected_frame
            or vm_hit != (a.register_vm and mode == "on")
        ):
            raise ValueError((mode, p.returncode, p.stdout, p.stderr))
        rows.append(
            dict(mode=mode, owned_frame_hit=hit, register_vm_hit=vm_hit, semantic_smoke_passed=True)
        )
    (output / "PATH-PROOF.json").write_text(
        json.dumps(
            dict(
                status="passed-real-owned-frame-and-disable-paths",
                register_vm=a.register_vm,
                fixture=fixture,
                rows=rows,
                performance=False,
            ),
            indent=2,
        )
        + "\n"
    )
    print("LINUX OWNED-FRAME ON/OFF PATHS PROVED")


if __name__ == "__main__":
    main()
