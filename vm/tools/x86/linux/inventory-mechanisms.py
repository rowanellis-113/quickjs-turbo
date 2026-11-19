"""Index accepted Windows decisions and actual Linux inputs for port review.

This optional audit takes an explicit SDK, never a build dependency. Receipt
units and source references are not counts of optimizations or dynamic proof.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--accepted-sdk", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    source, build, sdk, output = [
        p.resolve() for p in (a.source, a.build, a.accepted_sdk, a.output)
    ]
    output.mkdir(parents=True, exist_ok=False)
    units, bindings, digest = {}, {}, None
    for profile in ("msvc", "mingw"):
        path = sdk / "audit" / ("FEATURE-PARITY-product-r1-" + profile + ".json")
        parity = json.loads(path.read_text(encoding="utf-8-sig"))
        if (
            parity["status"] != "passed-all-common-generated-decision-receipts"
            or parity["differences"]
        ):
            raise ValueError("Accepted decision qualification failed: " + str(path))
        if digest is not None and digest != parity["source_digest"]:
            raise ValueError("Accepted profiles are from different sources")
        digest = parity["source_digest"]
        bindings[str(path)] = sha(path)
        for record in parity["records"]:
            if not record["exact"] or record["expected"] != record["observed"]:
                raise ValueError("Unqualified accepted decision: " + record["file"])
            unit = units.setdefault(
                record["file"], dict(receipt=record["file"], windows={}, linux_review="pending")
            )
            unit["windows"][profile] = dict(sha256=record["sha256"], decisions=record["observed"])
    modules = json.loads((source / "tools/common/modules.json").read_text())
    by_name = {name.replace("_", "-"): path for name, path in modules.items()}
    by_name.update({Path(path).stem.replace("_", "-"): path for path in modules.values()})
    for unit in units.values():
        stem = (
            unit["receipt"]
            .removeprefix("quickjs-interpreter-")
            .removeprefix("quickjs-")
            .split(".")[0]
        )
        candidates = [
            stem,
            stem.removesuffix("-generation"),
            stem.removesuffix("-route"),
            stem.removesuffix("-c"),
        ]
        matches = sorted({by_name[name] for name in candidates if name in by_name})
        unit["source_tools"] = ["tools/" + name for name in matches]
        unit["source_tool_sha256"] = {name: sha(source / name) for name in unit["source_tools"]}
    backend = json.loads((build / "BUILD.json").read_text())
    if sha(build / "qjs") != backend["binary_sha256"]:
        raise ValueError("Linux image no longer matches its actual build receipt")
    common_path = build / "generated/backports/BACKPORTS.json"
    common = json.loads(common_path.read_text())
    core = Path(common["compiler_input"])
    if sha(core) != common["compiler_input_sha256"]:
        raise ValueError("Linux compiler input changed")
    bindings[str(common_path)] = sha(common_path)
    bindings[str(source / "tools/common/modules.json")] = sha(source / "tools/common/modules.json")
    report = dict(
        schema=1,
        accepted_source_digest=digest,
        linux_source_commit=subprocess.check_output(
            ["git", "-C", source, "rev-parse", "HEAD"], text=True
        ).strip(),
        linux_source_dirty=subprocess.check_output(
            ["git", "-C", source, "status", "--porcelain"], text=True
        ),
        linux_binary_sha256=backend["binary_sha256"],
        bindings=bindings,
        counts=dict(
            receipt_units=len(units),
            msvc=sum("msvc" in u["windows"] for u in units.values()),
            mingw=sum("mingw" in u["windows"] for u in units.values()),
        ),
        accepted_decisions=[units[name] for name in sorted(units)],
        actual_linux_common_changes=common["fixes"],
        linux_vm=json.loads((build / "generated/linux-native/VM.json").read_text()),
        declared_bundle=json.loads(
            (source / "docs/architecture/x86/linux/LINUX-MECHANISMS.json").read_text()
        )["declared_bundle"],
        scope="Review index only. Receipt statuses, source matches and compiler-input presence do not prove dynamic Linux coverage. No inherited compiler/COFF profile is admitted by this report.",
    )
    (output / "INDEX.json").write_text(json.dumps(report, indent=2) + "\n")
    print("ACCEPTED DECISION INDEX", report["counts"], "Linux review remains explicit")


if __name__ == "__main__":
    main()
