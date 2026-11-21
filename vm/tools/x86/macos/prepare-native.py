"""Prepare normal CMake macOS x86-64 native C/Mach-O ASM inputs."""

import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86

_act_x86()

import argparse
import json
from pathlib import Path
import subprocess
import sys
from x86.macos.adapt_macho import adapt_all


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--numeric-compare", action="store_true")
    ap.add_argument("--disable-global-bindings", action="store_true")
    a = ap.parse_args()
    source, build = a.source.resolve(), a.build.resolve()
    output = build / "generated/macos-native"
    layout = build / "generated/macos-abi"
    command_source = output / "quickjs-linux-foundation.c"

    def run(rel_script, *args):
        subprocess.run(
            [sys.executable, "-B", source / "tools/x86" / rel_script, *map(str, args)], check=True
        )

    run(
        "macos/measure-layout.py",
        "--source",
        source,
        "--build",
        build,
        "--output",
        layout,
        "--command-source",
        command_source,
    )
    ic = (
        ["--property-ic"] if json.loads((layout / "layout.json").read_text())["property_ic"] else []
    )
    numeric = ["--numeric-compare"] if a.numeric_compare else []
    global_flags = ["--disable-global-bindings"] if a.disable_global_bindings else []
    run(
        "linux/generate-vm.py",
        "--source",
        source,
        "--layout",
        layout / "layout.json",
        "--output",
        output,
        *ic,
        *numeric,
        *global_flags,
        "--sysv-bridges",
        "--shared-entry",
        "--allow-existing",
    )
    run(
        "linux/build-foundation.py",
        "--source",
        source,
        "--build",
        build,
        "--layout",
        layout,
        "--output",
        output,
        "--internal-quota",
        "--route-internal",
        "--register-vm",
        output,
        "--prepare-only",
        "--command-source",
        command_source,
    )
    adapt_all(source, output)


if __name__ == "__main__":
    main()
