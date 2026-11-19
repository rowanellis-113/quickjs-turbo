"""ARM64 tool path activation."""

import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from common.paths import (  # noqa: E402
    activate_tools as _activate_common,
    source_file,
    upstream_root,
)


def activate_arm64_tools():
    _activate_common()
    if str(TOOLS_ROOT) not in sys.path:
        sys.path.insert(0, str(TOOLS_ROOT))
