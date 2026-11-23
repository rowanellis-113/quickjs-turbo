"""Win64 CLI wrapper around common.c_extract.generate_slow_c."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.paths import activate_tools
from common.c_extract.generate_slow_c import (
    COUNTERS,
    numeric_bodies,
    numeric_boundaries,
    property_bodies,
    without_register_blocks,
    property_boundaries as _common_property_boundaries,
    generate as _common_generate,
)

WIN64_ARG_CONSTRUCT_CONDITION = (
    "#if defined(__MINGW32__) && !defined(QJS_WIN64_NATIVE_VM) "
    "&& defined(QJS_INTERP_FRAME_INTERNAL_ENTRY) "
    "&& defined(QJS_INTERP_FRAME_REGISTER_ABI) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)"
)


def property_boundaries(source):
    return _common_property_boundaries(
        source, arg_construct_condition=WIN64_ARG_CONSTRUCT_CONDITION
    )


def generate(source, output, *, interpreter_text=None):
    return _common_generate(
        source,
        output,
        interpreter_text=interpreter_text,
        arg_construct_condition=WIN64_ARG_CONSTRUCT_CONDITION,
    )


if __name__ == "__main__":
    activate_tools()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.output)
