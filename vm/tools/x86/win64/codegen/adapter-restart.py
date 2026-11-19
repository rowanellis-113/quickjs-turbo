"""Start a fresh, verified adaptation epoch for the frame C object.

PRE_LINK adapters append aliases/relocations and classify extension sections.
On relink, replay from compiler bytes rather than applying the first adapter
to the last adapter's output. Each old epoch is preserved with its receipts.
Only build products are changed; engine source and generated machine code
do not change. An unrecognized adapted object is rejected.
"""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, shutil, time

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
STAGES = (
    "shared-alias",
    "null-route",
    "iterator",
    "iterator-fast",
    "iterator-literal",
    "extension",
    "bigint-release",
)


def restart(path, build):
    path = path.resolve()
    build = build.resolve()
    assert path.is_relative_to(build) and path.name == "quickjs-interpreter.c.obj"
    raw = path.read_bytes()
    parser = _frame_tool_path("object-adapter")
    spec = importlib.util.spec_from_file_location("restart_coff", parser)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    obj = mod.Coff(raw)
    assert "js_frame_call_entry" in obj.symbols
    adapted = "JS_FrameCallEntryLegacy" in obj.symbols
    alias = path.with_name(path.name + ".shared-alias.json")
    if not alias.exists():
        assert not adapted, "Adapted object lacks alias provenance"
        return
    rows = []
    for stage in STAGES:
        report = path.with_name(path.name + "." + stage + ".json")
        if not report.exists():
            continue
        receipt = read(report)
        backup = path.with_name(path.name + ".before-" + stage)
        assert backup.is_file() and sha(backup) == receipt["before_sha256"], stage
        if rows:
            assert rows[-1][2]["after_sha256"] == receipt["before_sha256"], stage
        rows.append((report, backup, receipt))
    assert rows and rows[0][0] == alias
    if adapted:
        assert hashlib.sha256(raw).hexdigest() == rows[-1][2]["after_sha256"], (
            "Unknown adapted object; inspect build state"
        )
        compiler = rows[0][1].read_bytes()
    else:
        # A real compiler rebuild replaced the object; retire the old epoch.
        compiler = raw
    history = path.with_name(path.name + ".adapter-history")
    epoch = history / (hashlib.sha256(raw).hexdigest() + "-" + str(time.time_ns()))
    epoch.mkdir(parents=True, exist_ok=False)
    (epoch / "input.obj").write_bytes(raw)
    for report, backup, _ in rows:
        for item in (report, backup):
            assert item.resolve().parent == path.parent
            shutil.copyfile(item, epoch / item.name)
            assert sha(item) == sha(epoch / item.name)
    (epoch / "epoch.json").write_text(
        json.dumps(
            dict(
                input_sha256=hashlib.sha256(raw).hexdigest(),
                compiler_sha256=hashlib.sha256(compiler).hexdigest(),
                compiler_rebuilt=not adapted,
                stages=[p.name for p, _, _ in rows],
                policy="Validated complete stage/backup hash chain; preserve old epoch before replay.",
            ),
            indent=2,
        )
        + "\n"
    )
    for report, backup, _ in rows:
        report.unlink()
        backup.unlink()
    stamp = path.stat()
    path.write_bytes(compiler)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    print(
        "FRAME ADAPTER EPOCH RESTART",
        path.name,
        "stages",
        len(rows),
        "compiler_rebuilt",
        not adapted,
        flush=True,
    )


def restart_core(path, build):
    path = path.resolve()
    build = build.resolve()
    assert path.is_relative_to(build) and path.name == "quickjs.c.obj"
    private = _frame_generated_file(build, "quickjs-interpreter-private.json")
    original = _frame_generated_file(build, "quickjs-core-original.obj")
    parser = _frame_tool_path("object-adapter")
    spec = importlib.util.spec_from_file_location("restart_core_coff", parser)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = path.read_bytes()
    obj = mod.Coff(raw)
    fresh = "JS_Call" in obj.symbols
    if not private.exists():
        assert fresh, "Core has no original compiler provenance"
        return
    pr = read(private)
    assert sha(original) == pr["original_object_sha256"]
    retired = [private, original]
    known = {pr["adapted_object_sha256"]}
    stages = [
        (
            path.with_name(path.name + ".atod-route.json"),
            path.with_name(path.name + ".before-atod"),
        ),
        (
            _frame_generated_file(build, "quickjs-native-slice-private.json"),
            path.with_name(path.name + ".before-native-slice"),
        ),
        (
            _frame_generated_file(build, "quickjs-callback-private.json"),
            path.with_name(path.name + ".before-prepared-callback"),
        ),
        (_frame_generated_file(build, "quickjs-json-private.json"), None),
        (
            _frame_generated_file(build, "quickjs-regexp-replace.compile.json"),
            path.with_name(path.name + ".before-regexp"),
        ),
        (path.with_name(path.name + ".literal-alias.json"), None),
        (
            path.with_name(path.name + ".iterator-literal.json"),
            path.with_name(path.name + ".before-iterator-literal"),
        ),
        (
            path.with_name(path.name + ".coroutine-resume.json"),
            path.with_name(path.name + ".before-coroutine-resume"),
        ),
    ]
    for report, backup in stages:
        if not report.exists():
            continue
        receipt = read(report)
        if report.name == "quickjs-json-private.json":
            # JSON owns no intermediate snapshot. Its input must be a known
            # endpoint; the compiler snapshot remains the replay source.
            assert receipt["original_object_sha256"] in known, report
            known.add(receipt["adapted_object_sha256"])
            retired.append(report)
            continue
        if report.name == "quickjs-regexp-replace.compile.json":
            # This record owns two artifacts. Core replay retires only its core part.
            if "core" not in receipt:
                assert not backup.exists()
                continue
            receipt = receipt["core"]
        known.add(receipt["after_sha256"])
        if backup is not None:
            assert backup.exists() and sha(backup) == receipt["before_sha256"], report
            retired.append(backup)
        retired.append(report)
    times = _frame_build_file(build, "interpreter-compiled-input-times.json")
    if times.exists():
        entry = read(times).get("inputs", {}).get(str(path), {})
        if "transformed_sha256" in entry:
            known.add(entry["transformed_sha256"])
    if not fresh:
        assert hashlib.sha256(raw).hexdigest() in known, "Unknown adapted core"
    compiler = raw if fresh else original.read_bytes()
    epoch = _frame_generated_file(build, "core-adapter-history") / (
        hashlib.sha256(raw).hexdigest() + "-" + str(time.time_ns())
    )
    epoch.mkdir(parents=True, exist_ok=False)
    (epoch / "input.obj").write_bytes(raw)
    for item in retired:
        assert item.resolve().is_relative_to(build)
        dest = epoch / item.relative_to(build)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, dest)
        assert sha(item) == sha(dest)
    (epoch / "epoch.json").write_text(
        json.dumps(
            dict(
                input_sha256=hashlib.sha256(raw).hexdigest(),
                compiler_sha256=hashlib.sha256(compiler).hexdigest(),
                compiler_rebuilt=fresh,
                retired=[str(p.relative_to(build)) for p in retired],
            ),
            indent=2,
        )
        + "\n"
    )
    # The next core adapter recreates the canonical original snapshot and receipts.
    for item in retired:
        if item.name == "quickjs-regexp-replace.compile.json":
            compiler_record = read(item)
            compiler_record.pop("core")
            item.write_text(json.dumps(compiler_record, indent=2) + "\n", encoding="utf-8")
        else:
            item.unlink()
    stamp = path.stat()
    path.write_bytes(compiler)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    print("CORE ADAPTER EPOCH RESTART", path.name, "compiler_rebuilt", fresh, flush=True)


def retire_generated(path, build):
    """Called before a compiler overwrites a generated extra C object."""
    path = path.resolve()
    build = build.resolve()
    assert path.is_relative_to(build) and path.parent == _frame_generated_file(build, "").resolve()
    assert path.name.startswith("quickjs-") and path.suffix == ".obj"
    compile_record = path.with_suffix(".compile.json")
    if not path.exists():
        assert not compile_record.exists(), "Missing object with existing compiler provenance"
        return
    assert compile_record.exists(), "Generated object has no compiler provenance"
    c = read(compile_record)
    assert c["status"] == "passed"
    known = {c["object_sha256"]}
    retired = [compile_record]
    stages = [
        ("extension", "extension"),
        ("cold-order", "cold-order"),
        ("iterator", "iterator"),
        ("iterator-fast", "iterator-fast"),
        ("iterator-slow", "iterator-slow"),
        ("iterator-checkpoint", "iterator-checkpoint"),
        ("iterator-literal", "iterator-literal"),
        ("owned-merge", "owned"),
        ("null-arena-merge", "null-arena"),
        ("atod-merge", "atod"),
        ("local-string-merge", "local-string"),
        ("local-string-guard-merge", "local-string-guard"),
        ("regexp-merge", "regexp"),
    ]
    for label, backup_label in stages:
        report = path.with_name(path.name + "." + label + ".json")
        backup = path.with_name(path.name + ".before-" + backup_label)
        if not report.exists():
            assert not backup.exists(), ("Snapshot without receipt", backup)
            continue
        r = read(report)
        assert backup.is_file() and sha(backup) == r["before_sha256"], report
        known.add(r["after_sha256"])
        retired.extend([report, backup])
    unwind = path.with_name(path.name + ".compiler-unwind")
    if unwind.exists():
        assert c.get("compiler_object_sha256") == sha(unwind), "Unwind snapshot provenance mismatch"
        retired.append(unwind)
    assert sha(path) in known, "Unrecognized generated-object endpoint"
    for suffix in (".compile.log", ".source.json"):
        item = path.with_suffix(suffix)
        if item.exists():
            retired.append(item)
    epoch = _frame_generated_file(build, "generated-adapter-history") / (
        path.name + "-" + sha(path) + "-" + str(time.time_ns())
    )
    epoch.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(path, epoch / "input.obj")
    assert sha(path) == sha(epoch / "input.obj")
    for item in retired:
        assert item.resolve().parent == _frame_generated_file(build, "").resolve()
        shutil.copyfile(item, epoch / item.name)
        assert sha(item) == sha(epoch / item.name)
    (epoch / "epoch.json").write_text(
        json.dumps(
            dict(
                object=path.name,
                input_sha256=sha(path),
                compiler_receipt_sha256=sha(compile_record),
                retired=[p.name for p in retired],
                policy="Validate old compiler endpoint and every snapshot before the compiler replaces this object.",
            ),
            indent=2,
        )
        + "\n"
    )
    for item in retired:
        item.unlink()
    print("GENERATED ADAPTER EPOCH RETIRED", path.name, len(retired), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--object", type=Path, required=True)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--core", action="store_true")
    a = p.parse_args()
    (restart_core if a.core else restart)(a.object, a.build)
