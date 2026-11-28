"""Export a deterministic, SHA256-verified pre-generated assembly bundle.

Snapshots generated native assembly/C/header artifacts from a completed build
directory into <output>/<backend_slug>/ along with PREGEN-MANIFEST.json so
downstream offline/cross/embedded builds can enable -DQJS_USE_PREGEN_ASM=ON
without invoking Python generators at build time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

INCLUDED_SUFFIXES = frozenset({".S", ".asm", ".c", ".h", ".inc", ".json"})
EXCLUDED_NAMES = frozenset({"layout-probe.c", "compile.stdout", "compile.stderr"})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_upstream_pin(source_root: Path) -> str:
    pin = (source_root / "cmake/QuickJSUpstreamPin.cmake").read_text(encoding="utf-8")
    m = re.search(r'set\(QJS_UPSTREAM_REVISION\s+"([0-9a-f]{40})"\)', pin)
    if not m:
        raise RuntimeError("Cannot find QJS_UPSTREAM_REVISION in cmake/QuickJSUpstreamPin.cmake")
    return m.group(1)


def detect_property_ic(build_dir: Path) -> str:
    bp = build_dir / "generated/backports/BACKPORTS.json"
    if bp.is_file():
        data = json.loads(bp.read_text(encoding="utf-8"))
        return "ON" if data.get("property_ic") else "OFF"
    cache = build_dir / "CMakeCache.txt"
    if cache.is_file() and "QJS_PROPERTY_IC:BOOL=ON" in cache.read_text(encoding="utf-8"):
        return "ON"
    return "OFF"


def _load_macos_adapt_filter(
    effective: str, generated_dir: Path
) -> tuple[set[str], dict[str, str]] | None:
    """Return allowed (root_files, adapted_include_hashes) from MACOS-ADAPT.json when present."""
    if effective != "MACOS_X86_64":
        return None
    adapt_path = generated_dir / "macos-native/MACOS-ADAPT.json"
    if not adapt_path.is_file():
        raise FileNotFoundError(f"Missing macOS adapt receipt: {adapt_path}")
    adapt = json.loads(adapt_path.read_text(encoding="utf-8"))
    for field, expected_type in (
        ("c_files", dict),
        ("asm_files", dict),
        ("adapted_includes", list),
        ("adapted_include_files", dict),
    ):
        if field not in adapt or not isinstance(adapt[field], expected_type):
            raise ValueError(f"Missing or invalid {field} in {adapt_path}")
    expected_inc = {"macos-inc/" + rel for rel in adapt["adapted_includes"]}
    actual_inc = set(adapt["adapted_include_files"].keys())
    if actual_inc != expected_inc:
        raise ValueError(
            f"adapted_include_files mismatch in {adapt_path}: "
            f"missing={sorted(expected_inc - actual_inc)[:5]}, "
            f"extra={sorted(actual_inc - expected_inc)[:5]}"
        )
    allowed_root = set(adapt["c_files"].keys()) | set(adapt["asm_files"].keys())
    expected_hashes = {
        **adapt["c_files"],
        **adapt["asm_files"],
        **adapt["adapted_include_files"],
    }
    return allowed_root, expected_hashes


def export_bundle(source_root: Path, build_dir: Path, out_root: Path) -> Path:
    source_root = source_root.resolve()
    build_dir = build_dir.resolve()
    out_root = out_root.resolve()

    backend_json = build_dir / "interpreter-backend.json"
    if not backend_json.is_file():
        raise FileNotFoundError(f"Missing {backend_json}; configure and build first")
    backend_info = json.loads(backend_json.read_text(encoding="utf-8"))
    effective = backend_info.get("effective", "")
    if not effective or effective == "PORTABLE":
        raise RuntimeError(f"Cannot export pregen bundle from non-native backend: {effective!r}")

    slug = effective.lower()
    generated_dir = build_dir / "generated"
    if not generated_dir.is_dir():
        raise FileNotFoundError(f"Missing generated directory: {generated_dir}")

    macos_filter = _load_macos_adapt_filter(effective, generated_dir)

    bundle_dir = out_root / slug
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    files_manifest: dict[str, str] = {}
    for src in sorted(generated_dir.rglob("*")):
        if not src.is_file():
            continue
        if src.name in EXCLUDED_NAMES:
            continue
        if src.suffix not in INCLUDED_SUFFIXES:
            continue
        rel = src.relative_to(build_dir).as_posix()
        if macos_filter is not None and rel.startswith("generated/macos-native/"):
            allowed_root, expected_hashes = macos_filter
            sub_rel = rel[len("generated/macos-native/") :]
            if sub_rel.startswith("macos-inc/"):
                if sub_rel not in expected_hashes:
                    continue
            elif "/" not in sub_rel and src.suffix != ".json":
                if sub_rel not in allowed_root:
                    continue
        dst = bundle_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = src.read_bytes()
        # Normalize CRLF -> LF for deterministic cross-platform manifests.
        if b"\r\n" in raw:
            raw = raw.replace(b"\r\n", b"\n")
        dst.write_bytes(raw)
        files_manifest[rel] = hashlib.sha256(raw).hexdigest()

    if macos_filter is not None:
        _, expected_hashes = macos_filter
        for sub_rel, expected_sha in sorted(expected_hashes.items()):
            manifest_key = "generated/macos-native/" + sub_rel
            actual_sha = files_manifest.get(manifest_key)
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"macOS pregen receipt mismatch for {manifest_key}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )

    if not files_manifest:
        raise RuntimeError(f"No generated assembly/C artifacts found under {generated_dir}")

    manifest = {
        "schema": 1,
        "backend": effective,
        "slug": slug,
        "upstream_revision": parse_upstream_pin(source_root),
        "property_ic": detect_property_ic(build_dir),
        "file_count": len(files_manifest),
        "files": files_manifest,
    }
    manifest_path = bundle_dir / "PREGEN-MANIFEST.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    print(f"PREGEN EXPORTED: {bundle_dir} ({len(files_manifest)} files, backend={effective})")
    return bundle_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True, help="Path to vm/ directory")
    ap.add_argument("--build", type=Path, required=True, help="Path to completed CMake build dir")
    ap.add_argument("--output", type=Path, required=True, help="Output pregen root directory")
    args = ap.parse_args()
    export_bundle(args.source, args.build, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
