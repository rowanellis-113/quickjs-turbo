"""Explicit guest runners; never confuse a guest ELF with its host emulator."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(source):
    """Bind a checkout or verify every file in an explicit source archive."""
    source = Path(source).resolve(strict=True)
    if (source / ".git").exists():
        top = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"], text=True
        ).strip()
        if Path(top).resolve() != source:
            raise ValueError("Source must be the actual checkout root")
        return dict(
            kind="git-checkout",
            commit=subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip(),
            dirty=subprocess.check_output(
                ["git", "-C", str(source), "status", "--porcelain"], text=True
            ),
        )
    manifest = source / "SOURCE-TRANSFER.json"
    if not manifest.is_file():
        raise ValueError("An archive requires SOURCE-TRANSFER.json provenance")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data.get("files"), dict) or not data["files"]:
        raise ValueError("Source archive has no file inventory")
    for relative, expected in data["files"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Source archive paths must be relative: " + relative)
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Foreign source archive path: " + relative)
        if not path.is_file() or sha(path) != expected:
            raise ValueError("Source archive file differs: " + relative)
    return dict(
        kind="verified-source-archive",
        commit=None,
        dirty=data.get("source_dirty"),
        base_commit=data.get("baseline_commit"),
        manifest_sha256=sha(manifest),
        files_verified=len(data["files"]),
    )


def target_identity(engine):
    binary = Path(engine["binary"]).resolve(strict=True)
    prefix = engine.get("runner", [])
    if not isinstance(prefix, list) or any(
        not isinstance(s, str) or not s or "\x00" in s for s in prefix
    ):
        raise ValueError("runner must be a JSON argv list of nonempty strings")
    data = binary.read_bytes()
    if len(data) < 20 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 little-endian guest: " + str(binary))
    machine = struct.unpack_from("<H", data, 18)[0]
    if "guest_machine" in engine and engine["guest_machine"] != machine:
        raise ValueError("Wrong guest ELF machine: " + str(binary))
    result = dict(
        binary=str(binary),
        binary_sha256=sha(binary),
        elf_machine=machine,
        runner=list(prefix),
        execution_mode="emulated" if prefix else "native",
    )
    if prefix:
        executable = shutil.which(prefix[0])
        if not executable:
            raise ValueError("Runner executable not found: " + prefix[0])
        executable = Path(executable).resolve(strict=True)
        result["runner"][0] = str(executable)
        result["emulator"] = dict(binary=str(executable), binary_sha256=sha(executable))
    return result


def target_command(identity, *arguments):
    return [*identity["runner"], identity["binary"], *map(str, arguments)]


def verify_identity(identity):
    for item in (identity, identity.get("emulator")):
        if item and sha(item["binary"]) != item["binary_sha256"]:
            raise ValueError("Execution image changed: " + item["binary"])


def observe_process(identity, pid, timeout=5):
    """Wait through launcher exec, then bind the actual host process image."""
    expected = identity.get("emulator", identity)["binary"]
    process = Path("/proc") / str(pid)
    deadline = time.monotonic() + timeout
    while True:
        actual = str((process / "exe").resolve(strict=True))
        if actual == expected:
            break
        if time.monotonic() >= deadline:
            raise ValueError("Unexpected execution image: " + actual)
        time.sleep(0.005)
    verify_identity(identity)
    return dict(
        pid=pid,
        pid_role="host-emulator" if identity["runner"] else "engine",
        host_executable=actual,
        affinity=sorted(os.sched_getaffinity(pid)),
        maps=(process / "maps").read_text(),
        status=(process / "status").read_text(),
        guest_binary=identity["binary"],
        guest_sha256=identity["binary_sha256"],
    )
