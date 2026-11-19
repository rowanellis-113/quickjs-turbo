"""The bad saved-register fixture must fail; an arbitrary crash is not success."""

import argparse
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--exe", required=True)
ap.add_argument("--runner", nargs=argparse.REMAINDER, default=[])
a = ap.parse_args()
p = subprocess.run([*a.runner, a.exe], capture_output=True, text=True, timeout=120)
if (
    p.returncode != 1
    or "ABI_CHECK_FAILED" not in p.stderr
    or "qjs_aarch64_test_saved" not in p.stderr
):
    raise AssertionError((p.returncode, p.stdout, p.stderr))
print("AARCH64_BAD_SAVED_REJECTED")
