import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import activate_arm64_tools, source_file, upstream_root

activate_arm64_tools()
"""Record an installed ARM64 portable SDK without claiming a native VM port."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

from target_runner import target_identity


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def machine(data):
    if len(data) < 20 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected a little-endian ELF64 object")
    return struct.unpack_from("<H", data, 18)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "prefix"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    source, build, prefix = (p.resolve() for p in (a.source, a.build, a.prefix))
    cache = dict(
        re.findall(r"^([^/#\n][^:\n]*):[^=\n]*=(.*)$", (build / "CMakeCache.txt").read_text(), re.M)
    )
    backend = json.loads((build / "interpreter-backend.json").read_text())
    if backend["effective"] != "PORTABLE":
        raise ValueError("This receipt supports only PORTABLE")
    artifacts = {}
    for relative, built in (("bin/qjs", "qjs"), ("bin/qjsc", "qjsc"), ("lib/libqjs.a", "libqjs.a")):
        target = prefix / relative
        if sha(target) != sha(build / built):
            raise ValueError("Installed SDK differs from build: " + relative)
        artifacts[relative] = sha(target)
    for name in ("qjs", "qjsc"):
        if machine((prefix / "bin" / name).read_bytes()) != 183:
            raise ValueError("Wrong installed executable architecture")
    if not (prefix / "include/quickjs.h").is_file():
        raise ValueError("Missing installed public quickjs.h")
    for header in (prefix / "include").glob("*.h"):
        source_header = source_file(source, header.name)
        if not source_header.is_file() or sha(header) != sha(source_header):
            raise ValueError("Installed public header differs from source: " + header.name)
        artifacts["include/" + header.name] = sha(header)
    ar = cache.get("CMAKE_AR", "aarch64-linux-gnu-ar")
    members = subprocess.check_output([ar, "t", build / "libqjs.a"], text=True).splitlines()
    if len(members) != len(set(members)):
        raise ValueError("Ambiguous archive member names")
    for member in members:
        if machine(subprocess.check_output([ar, "p", build / "libqjs.a", member])) != 183:
            raise ValueError("Foreign archive member: " + member)
    inputs = {}
    for directory in ("src", "asm", "cmake", "tools"):
        for path in (source / directory).rglob("*"):
            if path.is_file() and path.suffix in (
                ".c",
                ".h",
                ".inc",
                ".S",
                ".asm",
                ".py",
                ".cmake",
                ".sh",
                ".json",
            ):
                inputs[path.relative_to(source).as_posix()] = sha(path)
    pin = (source / "cmake/QuickJSUpstreamPin.cmake").read_text()
    pins = re.findall(r'"([^"\n:]+):([a-f0-9]{64})"', pin)
    if len(pins) != 19:
        raise ValueError("Review the changed upstream pin inventory")
    for name, expected in pins:
        actual = sha(source_file(source, name))
        if actual != expected:
            raise ValueError("Changed upstream pin: " + name)
        inputs[name] = actual
    inputs["CMakeLists.txt"] = sha(source / "CMakeLists.txt")
    generated = {p.name: sha(p) for p in (build / "generated/backports").iterdir() if p.is_file()}
    compiler = cache["CMAKE_C_COMPILER"]
    triple = subprocess.check_output([compiler, "-dumpmachine"], text=True).strip()
    if not triple.startswith("aarch64"):
        raise ValueError("Wrong recorded compiler target: " + triple)
    revision = None
    dirty = None
    git_root = upstream_root(source)
    git = subprocess.run(
        ["git", "-C", git_root, "rev-parse", "--show-toplevel"], text=True, capture_output=True
    )
    if git.returncode == 0 and Path(git.stdout.strip()).resolve() in {source, git_root}:
        revision = subprocess.check_output(
            ["git", "-C", git_root, "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = subprocess.check_output(["git", "-C", git_root, "status", "--porcelain"], text=True)
    runner = cache.get("CMAKE_CROSSCOMPILING_EMULATOR", "").split(";")
    runner = runner if runner != [""] else []
    execution = target_identity(
        dict(binary=str(prefix / "bin/qjs"), runner=runner, guest_machine=183)
    )
    receipt = dict(
        schema=1,
        kind="linux-aarch64-portable",
        backend=backend,
        native_register_vm=False,
        hardware_performance="not-verified",
        qualification="build-provenance-only; consult the separate compatibility results",
        source_commit=revision,
        source_dirty=dirty,
        upstream_pins_verified=len(pins),
        compiler=dict(
            path=compiler,
            target=triple,
            version=subprocess.check_output([compiler, "--version"], text=True),
        ),
        cmake_cache=cache,
        execution=execution,
        artifacts=artifacts,
        archive_members=members,
        source_inputs=dict(sorted(inputs.items())),
        generated_inputs=generated,
        compile_commands_sha256=sha(build / "compile_commands.json"),
    )
    destination = prefix / "share/doc/quickjs"
    destination.mkdir(parents=True, exist_ok=True)
    foundation = build / "generated/aarch64-abi"
    if cache.get("QJS_AARCH64_BUILD_ABI_CHECKS") == "ON":
        check = json.loads((foundation / "CHECK.json").read_text())
        layout = json.loads((foundation / "LAYOUT.json").read_text())
        if (
            check["status"] != "passed-aarch64-standard-call-foundation"
            or check["linked_into_qjs"]
            or check["native_vm"]
            or check["engine_sha256"] != sha(build / "qjs")
            or check["archive_sha256"] != sha(build / "libqjs.a")
            or check["layout_sha256"] != sha(foundation / "LAYOUT.json")
            or layout["profile_sha256"] != sha(source / "src/arm64/linux/abi/profile.json")
        ):
            raise ValueError("AArch64 foundation receipt is stale or has the wrong scope")
        for name, digest in layout["reviewed_inputs"].items():
            if sha(source_file(source, name)) != digest:
                raise ValueError("Reviewed foundation input changed: " + name)
        receipt["abi_foundation"] = dict(
            scope="standalone standard C-call ABI, not linked into qjs",
            check_sha256=sha(foundation / "CHECK.json"),
            layout_sha256=sha(foundation / "LAYOUT.json"),
        )
        shutil.copyfile(foundation / "CHECK.json", destination / "AARCH64-CALL-ABI.json")
        shutil.copyfile(foundation / "LAYOUT.json", destination / "AARCH64-LAYOUT.json")
    (destination / "ARM64-BUILD.json").write_text(json.dumps(receipt, indent=2) + "\n")
    shutil.copyfile(build / "interpreter-backend.json", destination / "interpreter-backend.json")
    shutil.copyfile(
        source / "docs/architecture/arm64/LINUX-AARCH64.txt", destination / "LINUX-AARCH64.txt"
    )
    print("ARM64_PORTABLE_RECEIPT_OK members=" + str(len(members)) + " pins=" + str(len(pins)))


if __name__ == "__main__":
    main()
