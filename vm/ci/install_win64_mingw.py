#!/usr/bin/env python3
"""Download and verify pinned WinLibs MinGW GCC 13.1.0 + COFF binutils for CI."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

RELEASE_TAG = "13.1.0-16.0.5-11.0.0-msvcrt-r5"
ARCHIVE_NAME = "winlibs-x86_64-posix-seh-gcc-13.1.0-mingw-w64msvcrt-11.0.0-r5.7z"
URL = (
    "https://github.com/brechtsanders/winlibs_mingw/releases/download/"
    f"{RELEASE_TAG}/{ARCHIVE_NAME}"
)
SHA256 = "4aa182a6ecf05140e66189ef38673482cb910164d2b8ee65c9297b080445deb5"


def _download_with_retries(url: str, target: Path, expected_sha256: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        hasher = hashlib.sha256()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "quickjs-turbo-ci"})
            with urllib.request.urlopen(req, timeout=180) as resp, target.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    out.write(chunk)
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            target.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(2 * attempt)
            continue

        digest = hasher.hexdigest()
        if digest != expected_sha256:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum mismatch for {url}: got {digest}, expected {expected_sha256}"
            )
        return
    raise RuntimeError(f"Failed to download {url} after 3 attempts: {last_error}")


def _find_7z() -> str:
    found = shutil.which("7z")
    if found:
        return found
    fallback = Path(r"C:\Program Files\7-Zip\7z.exe")
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("7z executable is required to extract WinLibs archive")


def _find_cmake() -> Path:
    found = shutil.which("cmake")
    if found:
        return Path(found)
    fallback = Path(r"C:\Program Files\CMake\bin\cmake.exe")
    if fallback.is_file():
        return fallback
    raise RuntimeError("System cmake.exe not found on PATH or default location")


def ensure_toolchain(dest: Path, *, url: str = URL, sha256: str = SHA256) -> dict[str, str]:
    """Ensure pinned WinLibs GCC 13.1.0 is extracted at `dest` and return CI outputs."""
    dest = dest.resolve()
    bin_dir = (dest / "mingw64/bin").resolve()
    if not (bin_dir / "gcc.exe").is_file():
        archive_path = dest / ARCHIVE_NAME
        _download_with_retries(url, archive_path, sha256)
        try:
            seven_zip = _find_7z()
            subprocess.run(
                [seven_zip, "x", "-y", f"-o{dest}", str(archive_path)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        finally:
            archive_path.unlink(missing_ok=True)

    required_tools = {
        "gcc": bin_dir / "gcc.exe",
        "gxx": bin_dir / "g++.exe",
        "objdump": bin_dir / "objdump.exe",
        "as": bin_dir / "as.exe",
    }
    for name, path in required_tools.items():
        if not path.is_file():
            raise RuntimeError(f"Missing expected toolchain binary {name}: {path}")

    ninja_path = bin_dir / "ninja.exe"
    if not ninja_path.is_file():
        found_ninja = shutil.which("ninja")
        if not found_ninja:
            raise RuntimeError(f"Missing ninja.exe in {bin_dir} and PATH")
        ninja_path = Path(found_ninja)

    cmake_path = _find_cmake()
    outputs = {
        "cmake": cmake_path.resolve().as_posix(),
        "ninja": ninja_path.resolve().as_posix(),
        "gcc": required_tools["gcc"].resolve().as_posix(),
        "gxx": required_tools["gxx"].resolve().as_posix(),
        "objdump": required_tools["objdump"].resolve().as_posix(),
        "as": required_tools["as"].resolve().as_posix(),
        "mingw_bin": str(bin_dir),
    }
    return outputs


def write_github_outputs(path: Path, outputs: dict[str, str]) -> None:
    """Append `key=value` lines to a GitHub Actions output file."""
    lines = "".join(f"{k}={v}\n" for k, v in outputs.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)


def main(argv: list[str] | None = None) -> int:
    base_tmp = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    default_dest = base_tmp / "winlibs-gcc-13.1.0"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=default_dest)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    outputs = ensure_toolchain(args.dest)
    if args.github_output:
        write_github_outputs(args.github_output, outputs)
    print("WIN64_MINGW_13_READY", outputs["gcc"], "cmake=", outputs["cmake"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
