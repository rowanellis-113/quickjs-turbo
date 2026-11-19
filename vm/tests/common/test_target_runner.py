"""Wrong-architecture and changed-image rejection for explicit cross runners."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/common/elf"))
from target_runner import source_identity, target_command, target_identity, verify_identity


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Invalid execution identity was accepted")


with tempfile.TemporaryDirectory() as directory:
    source = Path(directory).resolve()
    item = source / "owned.c"
    item.write_bytes(b"int owned;\n")
    manifest = source / "SOURCE-TRANSFER.json"
    data = {
        "baseline_commit": "a" * 40,
        "source_dirty": " M owned.c\n",
        "files": {"owned.c": hashlib.sha256(item.read_bytes()).hexdigest()},
    }
    manifest.write_text(json.dumps(data))
    binding = source_identity(source)
    assert binding["kind"] == "verified-source-archive"
    assert binding["commit"] is None and binding["base_commit"] == "a" * 40
    assert binding["files_verified"] == 1
    item.write_bytes(b"int changed;\n")
    rejects(lambda: source_identity(source))
    data["files"] = {"../foreign.c": "0" * 64}
    manifest.write_text(json.dumps(data))
    rejects(lambda: source_identity(source))
    data["files"] = {str(item): hashlib.sha256(item.read_bytes()).hexdigest()}
    manifest.write_text(json.dumps(data))
    rejects(lambda: source_identity(source))
    manifest.unlink()
    rejects(lambda: source_identity(source))
print("SOURCE_IDENTITY_OK archive binding, stale and foreign source rejection")

if not Path("/bin/true").is_file() or Path("/bin/true").read_bytes()[:6] != b"\x7fELF\x02\x01":
    print("TARGET_RUNNER_SKIP host is outside the ELF64 little-endian runner scope")
    sys.exit(0)


with tempfile.TemporaryDirectory() as directory:
    binary = Path(directory) / "image"
    shutil.copyfile("/bin/true", binary)
    engine = dict(binary=str(binary))
    identity = target_identity(engine)
    verify_identity(identity)
    assert target_command(identity, "path with spaces", "-e", "a;b") == [
        str(binary),
        "path with spaces",
        "-e",
        "a;b",
    ]
    rejects(lambda: target_identity(dict(engine, guest_machine=0)))
    rejects(lambda: target_identity(dict(engine, runner="qemu-user-static -L /x")))
    rejects(lambda: target_identity(dict(engine, runner=[""])))
    rejects(lambda: target_identity(dict(engine, runner=["qjs-no-such-runner"])))
    emulated = target_identity(dict(engine, runner=[sys.executable, "-B"]))
    assert emulated["execution_mode"] == "emulated"
    assert emulated["emulator"]["binary"] == str(Path(sys.executable).resolve())
    assert json.loads(json.dumps(emulated)) == emulated
    binary.write_bytes(binary.read_bytes() + b"changed")
    rejects(lambda: verify_identity(identity))
    rejects(lambda: verify_identity(emulated))
    binary.write_bytes(b"not an ELF")
    rejects(lambda: target_identity(engine))

print("TARGET_RUNNER_OK architecture, argv, guest and emulator identities")
