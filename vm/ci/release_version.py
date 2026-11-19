#!/usr/bin/env python3
"""Validate QuickJS-Turbo release version metadata against the pinned upstream base."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

VERSION_RE = re.compile(
    r"^(?P<upstream>\d+\.\d+\.\d+)-turbo\.(?P<seq>[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:alpha|beta|rc)\.[1-9]\d*))?$"
)
UPSTREAM_VER_RE = re.compile(r'set\(QJS_UPSTREAM_VERSION\s+"([^"]+)"\)')
UPSTREAM_REV_RE = re.compile(r'set\(QJS_UPSTREAM_REVISION\s+"([0-9a-f]{40})"\)')


@dataclass(frozen=True)
class ReleaseInfo:
    """Validated QuickJS-Turbo release metadata bound to the upstream pin."""

    version: str
    tag: str
    upstream_version: str
    upstream_revision: str
    sequence: int
    prerelease_label: str | None

    @property
    def prerelease(self) -> bool:
        return self.prerelease_label is not None

    @property
    def make_latest(self) -> bool:
        return not self.prerelease


def read_upstream_pin(pin_path: Path) -> tuple[str, str]:
    """Read `QJS_UPSTREAM_VERSION` and `QJS_UPSTREAM_REVISION` from cmake pin file."""
    text = pin_path.read_text(encoding="utf-8")
    ver_match = UPSTREAM_VER_RE.search(text)
    rev_match = UPSTREAM_REV_RE.search(text)
    if not ver_match or not rev_match:
        raise ValueError(f"Missing QJS_UPSTREAM_VERSION or QJS_UPSTREAM_REVISION in {pin_path}")
    return ver_match.group(1), rev_match.group(1)


def resolve_release_info(vm_root: Path) -> ReleaseInfo:
    """Parse and cross-validate `vm/VERSION` against `QuickJSUpstreamPin.cmake`."""
    vm_root = vm_root.resolve()
    version_path = vm_root / "VERSION"
    pin_path = vm_root / "cmake/QuickJSUpstreamPin.cmake"

    raw_version = version_path.read_text(encoding="utf-8").strip()
    match = VERSION_RE.fullmatch(raw_version)
    if not match:
        raise ValueError(
            f"Invalid version {raw_version!r} in {version_path}: "
            "expected <major>.<minor>.<patch>-turbo.<N>[-(alpha|beta|rc).<K>] with N>=1"
        )

    upstream_version, upstream_revision = read_upstream_pin(pin_path)
    if match.group("upstream") != upstream_version:
        raise ValueError(
            f"Version prefix {match.group('upstream')!r} in {version_path} does not match "
            f"pinned QJS_UPSTREAM_VERSION {upstream_version!r} in {pin_path}"
        )

    return ReleaseInfo(
        version=raw_version,
        tag=f"v{raw_version}",
        upstream_version=upstream_version,
        upstream_revision=upstream_revision,
        sequence=int(match.group("seq")),
        prerelease_label=match.group("prerelease"),
    )


def validate_tag(info: ReleaseInfo, ref_or_tag: str) -> str:
    """Verify a Git tag or `refs/tags/...` matches the resolved release tag."""
    normalized = ref_or_tag.strip()
    if normalized.startswith("refs/tags/"):
        normalized = normalized[len("refs/tags/") :]
    if not normalized.startswith("v") or normalized != info.tag:
        raise ValueError(f"Tag {normalized!r} does not match vm/VERSION expected tag {info.tag!r}")
    return normalized


def write_github_outputs(path: Path, info: ReleaseInfo) -> None:
    """Append resolved release metadata lines to GitHub Actions outputs."""
    outputs = {
        "version": info.version,
        "tag": info.tag,
        "upstream_version": info.upstream_version,
        "upstream_revision": info.upstream_revision,
        "prerelease": "true" if info.prerelease else "false",
        "make_latest": "true" if info.make_latest else "false",
    }
    lines = "".join(f"{key}={val}\n" for key, val in outputs.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)


def write_sdk_metadata(sdk_dir: Path, info: ReleaseInfo, *, platform: str, git_sha: str) -> Path:
    """Write `quickjs-turbo-version.json` inside a staged SDK directory."""
    sdk_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "product": "quickjs-turbo",
        "version": info.version,
        "tag": info.tag,
        "upstream_version": info.upstream_version,
        "upstream_revision": info.upstream_revision,
        "platform": platform,
        "git_sha": git_sha,
    }
    out_path = sdk_dir / "quickjs-turbo-version.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return out_path


def write_release_notes(md_path: Path, info: ReleaseInfo, *, git_sha: str) -> Path:
    """Write structured Release Metadata Markdown header for GitHub Release notes."""
    commit_display = git_sha or "unknown"
    lines = [
        "## Release Metadata",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
        f"| **QuickJS-Turbo Version** | `{info.tag}` (`{info.version}`) |",
        f"| **QuickJS-NG Upstream Base** | `{info.upstream_version}` (`{info.upstream_revision}`) |",
        f"| **Release Type** | `{'prerelease' if info.prerelease else 'official'}` |",
        f"| **Commit SHA** | `{commit_display}` |",
        "",
        "### Included SDK Archives",
        "",
        f"- `quickjs-turbo-{info.tag}-linux-x86_64-sdk.tar.gz` (`LINUX_X86_64` native register VM)",
        (
            f"- `quickjs-turbo-{info.tag}-linux-aarch64-sdk.tar.gz` "
            "(`LINUX_AARCH64` native register VM)"
        ),
        f"- `quickjs-turbo-{info.tag}-windows-x86_64-msvc-md-sdk.zip` (`WIN64` MSVC `/MD`)",
        (
            f"- `quickjs-turbo-{info.tag}-windows-x86_64-msvc-mt-sdk.zip` "
            "(`WIN64` MSVC `/MT` static CRT + `QJS_DEFAULT_EXPERIMENT_ALLOCATOR=256`)"
        ),
        f"- `quickjs-turbo-{info.tag}-windows-x86_64-mingw-sdk.zip` (`WIN64` MinGW GCC 13.1)",
        f"- `quickjs-turbo-{info.tag}-macos-arm64-portable-sdk.tar.gz` (`PORTABLE` C fallback)",
        "- `SHA256SUMS.txt` (SHA-256 checksums for all archives)",
        "",
    ]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return md_path


def main(argv: list[str] | None = None) -> int:
    default_vm_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vm-root", type=Path, default=default_vm_root)
    parser.add_argument("--tag", help="Git tag or refs/tags/... to validate against vm/VERSION")
    parser.add_argument("--github-output", type=Path, help="GitHub Actions GITHUB_OUTPUT path")
    parser.add_argument(
        "--write-sdk-metadata",
        type=Path,
        help="Target SDK directory in which to write quickjs-turbo-version.json",
    )
    parser.add_argument("--platform", help="Platform slug required with --write-sdk-metadata")
    parser.add_argument(
        "--write-release-notes",
        type=Path,
        help="Markdown file path for structured GitHub Release notes header",
    )
    parser.add_argument("--git-sha", default="", help="Optional commit SHA for release metadata")
    args = parser.parse_args(argv)

    if args.write_sdk_metadata and not args.platform:
        parser.error("--platform is required when --write-sdk-metadata is provided")

    try:
        info = resolve_release_info(args.vm_root)
        if args.tag is not None:
            validate_tag(info, args.tag)
    except (FileNotFoundError, ValueError) as exc:
        print(f"RELEASE_VERSION_ERROR: {exc}", file=sys.stderr)
        return 1

    if args.github_output:
        write_github_outputs(args.github_output, info)
    if args.write_sdk_metadata:
        write_sdk_metadata(
            args.write_sdk_metadata,
            info,
            platform=args.platform,
            git_sha=args.git_sha,
        )
    if args.write_release_notes:
        write_release_notes(args.write_release_notes, info, git_sha=args.git_sha)

    prerelease_str = "true" if info.prerelease else "false"
    print(
        f"RELEASE_VERSION_OK {info.tag} "
        f"upstream={info.upstream_version}@{info.upstream_revision[:12]} "
        f"prerelease={prerelease_str}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
