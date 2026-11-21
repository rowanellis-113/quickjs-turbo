"""Current and previous CMake option spellings must select the same policy."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmake", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    previous = "QJS_" + "".join(chr(c) for c in (76, 76, 73, 78, 84)) + "_FRAME_DIAGNOSTICS"
    current = "QJS_INTERP_FRAME_DIAGNOSTICS"
    with tempfile.TemporaryDirectory(prefix="interpreter-options-") as directory:
        cwd = Path(directory)
        script = cwd / "options.cmake"
        with script.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "cmake_minimum_required(VERSION 3.20)\n"
                'set(QJS_FRAME_BACKEND PORTABLE CACHE STRING "")\n'
                'include("' + (root / "cmake/common/InterpreterOptions.cmake").as_posix() + '")\n'
                "get_property(preference CACHE QJS_INTERP_FRAME_DIAGNOSTICS PROPERTY VALUE)\n"
                "if(NOT preference)\n"
                '  message(FATAL_ERROR "Diagnostic option was not propagated")\n'
                "endif()\n"
            )
        cases = [
            ([f"-D{previous}:BOOL=ON"], True),
            ([f"-D{current}:BOOL=ON"], True),
            ([f"-D{previous}:BOOL=ON", f"-D{current}:BOOL=1"], True),
            ([f"-D{previous}:BOOL=OFF", f"-D{current}:BOOL=ON"], False),
        ]
        for options, expected in cases:
            result = subprocess.run(
                [args.cmake, *options, "-P", str(script)],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if (result.returncode == 0) != expected:
                raise AssertionError((options, result.returncode, result.stdout, result.stderr))
            if not expected and "Conflicting current and previous values" not in result.stderr:
                raise AssertionError(result.stderr)
    print("INTERPRETER_CMAKE_OPTIONS_COMPAT_OK")


if __name__ == "__main__":
    main()
