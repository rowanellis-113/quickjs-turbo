"""Source, tool, and build artifact addressing for the x86 package."""

import sys
from pathlib import Path

X86_COMMON_ROOT = Path(__file__).resolve().parent
X86_ROOT = X86_COMMON_ROOT.parent
TOOLS_ROOT = X86_ROOT.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from common.paths import (  # noqa: E402
    GENERATED_DIRECTORIES,
    SOURCE_BODY_FRAGMENTS,
    SOURCE_ROOT,
    TOOL_ROOT,
    activate_tools as _activate_common,
    build_file as _common_build_file,
    generated_file,
    normalized_source_digest,
    project_root,
    source_file,
    source_text,
    tool_path,
    upstream_root,
)


def activate_tools():
    _activate_common()
    for path in (
        X86_COMMON_ROOT / "abi",
        X86_COMMON_ROOT / "codegen",
        X86_ROOT / "linux",
    ):
        s = str(path)
        while s in sys.path:
            sys.path.remove(s)
        sys.path.insert(0, s)


def build_file(build, name):
    return _common_build_file(build, name, extra_prefixes=("msvc-", "mingw-"))
