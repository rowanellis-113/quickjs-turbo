"""Explicit source IDs, tool modules and build-local generated artifacts.

Source IDs describe inputs. Generated files always live below generated
and never resolve through the source catalogue. No legacy directory search or
fallback to a historical experiment is performed.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import sys

COMMON_ROOT = Path(__file__).resolve().parent
TOOL_ROOT = COMMON_ROOT.parent
SOURCE_ROOT = TOOL_ROOT.parent
SOURCE_BODY_FRAGMENTS = {
    "src/common/json/json_values.inc",
    "src/common/json/json_parser.inc",
    "src/common/value/loose_control.inc",
    "src/common/wire/regexp_wire.inc",
    "src/common/call/interpreter-context-types.inc",
    "src/common/call/interpreter-bytecode-metadata.inc",
    "src/common/call/interpreter-retained-context.inc",
}
GENERATED_DIRECTORIES = {
    "call-forward-link",
    "call-metadata-link",
    "forward-native-control",
    "generated-adapter-history",
    "core-adapter-history",
    "js-captured-link",
    "length-link",
    "native-c-scope",
    "native-scope-entry",
    "native-scope-link",
    "own-bytecode-link",
    "proto-direct-link",
    "varargs-generation",
    "varargs-link",
    "quickjs-retained-pristine",
    "call-link-vm-history",
    "native-c-scope-history",
}


def project_root():
    return SOURCE_ROOT


def upstream_root(source=None):
    base = Path(source).resolve() if source is not None else SOURCE_ROOT
    if (base / "quickjs.c").is_file():
        return base
    override = os.environ.get("QJS_UPSTREAM_DIR")
    if override:
        return Path(override).resolve()
    if (base.parent / "quickjs.c").is_file():
        return base.parent
    return base


def activate_tools():
    if str(TOOL_ROOT) not in sys.path:
        sys.path.insert(0, str(TOOL_ROOT))
    for group in ("abi", "backports", "c_extract", "elf"):
        path = str(COMMON_ROOT / group)
        if path not in sys.path:
            sys.path.insert(0, path)


def tool_path(name):
    name = str(name)
    if name.endswith(".py"):
        name = name[:-3]
    modules = json.loads((COMMON_ROOT / "modules.json").read_text(encoding="utf-8"))
    if name not in modules:
        raise RuntimeError("Unregistered frame tool: " + name)
    return TOOL_ROOT / modules[name]


def source_file(source, name):
    source = Path(source)
    name = str(name)
    catalogue = source / "src/sources.json"
    sources = json.loads(catalogue.read_text(encoding="utf-8")) if catalogue.is_file() else {}
    relative = sources.get(name, name)
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise RuntimeError("Frame source must be a checkout-relative input: " + relative)
    owned_candidate = source / relative
    if owned_candidate.exists() or relative.startswith(
        ("src/", "asm/", "cmake/", "tools/", "docs/")
    ):
        return owned_candidate
    up_candidate = upstream_root(source) / relative
    if up_candidate.exists():
        return up_candidate
    return owned_candidate


def normalized_source_digest(source, name):
    """Match the upstream source pin on LF and CRLF checkouts."""
    data = source_file(source, name).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def source_text(source, name):
    """Expand explicitly extracted .inc fragments for source-body generators.

    The C compiler uses ordinary includes at exactly the same location. The
    generator sees their original concatenated token stream. Upstream and
    declaration headers are not expanded and no conditional is evaluated here.
    """
    source = Path(source)
    active = set()

    def read(path):
        key = path.resolve()
        if key in active:
            raise RuntimeError("Recursive frame source fragment: " + str(path))
        active.add(key)
        value = path.read_text(encoding="utf-8")

        def fragment(match):
            relative = match[1]
            if relative not in SOURCE_BODY_FRAGMENTS:
                return match[0]
            if not relative.startswith("src/") or ".." in Path(relative).parts:
                raise RuntimeError("Invalid frame source fragment: " + relative)
            return read(source / relative)

        value = re.sub(r'^#include "(src/[^"\n]+\.inc)"\n', fragment, value, flags=re.M)
        active.remove(key)
        return value

    return read(source_file(source, name))


def generated_file(build, name):
    name = str(name)
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise RuntimeError("Generated frame artifact must be build-relative: " + name)
    directory = Path(build) / "generated"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


def build_file(build, name, extra_prefixes=()):
    """Resolve a build-relative member or a named generated artifact.

    Compiler members, CMake metadata and final libraries retain their actual
    build-relative identities. This also handles dynamically named generators
    without assuming every artifact resides beside CMakeCache.txt.
    """
    name = str(name)
    if (
        name.startswith(("quickjs-", *extra_prefixes)) and name != "quickjs-interpreter-tools.json"
    ) or (Path(name).parts and Path(name).parts[0] in GENERATED_DIRECTORIES):
        return generated_file(build, name)
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise RuntimeError("Expected build-relative member: " + name)
    return Path(build) / name
