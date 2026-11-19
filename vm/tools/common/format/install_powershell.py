#!/usr/bin/env python3
"""Install the hash-pinned PowerShell formatter inside the ignored tools directory."""

import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
VERSION = "1.24.0"
SHA256 = "e86c97d44bb1bc8a1de35e753b85ea1d938f6f9f881639a181507e079bca4556"
URL = (
    "https://github.com/PowerShell/PSScriptAnalyzer/releases/download/"
    + VERSION
    + "/PSScriptAnalyzer."
    + VERSION
    + ".nupkg"
)
BUILD_ROOT = (
    ROOT.parent / "build"
    if (ROOT.parent / "build/format-tools").is_dir() or not (ROOT / "build").is_dir()
    else ROOT / "build"
)
DESTINATION = BUILD_ROOT / "format-tools/powershell/PSScriptAnalyzer" / VERSION


def main():
    with urllib.request.urlopen(URL, timeout=60) as response:
        payload = response.read()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise RuntimeError("PSScriptAnalyzer package checksum mismatch")
    destination = DESTINATION.resolve()
    if not destination.is_relative_to(BUILD_ROOT.resolve()):
        raise RuntimeError("Formatter installation must remain inside build/")
    files = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            path = (destination / entry.filename).resolve()
            if not path.is_relative_to(destination):
                raise RuntimeError("Foreign archive path: " + entry.filename)
            data = archive.read(entry)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files[entry.filename] = hashlib.sha256(data).hexdigest()
    receipt = {"version": VERSION, "package_sha256": SHA256, "files": files}
    (destination / "installed.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("Installed PSScriptAnalyzer", VERSION, "with verified package checksum")


if __name__ == "__main__":
    main()
