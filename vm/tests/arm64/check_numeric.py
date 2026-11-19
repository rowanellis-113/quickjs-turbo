"""Compare real VM/C-frame/legacy numeric outputs with the same guest image."""

import argparse, json, os, re, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("--exe", required=True)
ap.add_argument("--runner", nargs=argparse.REMAINDER, default=[])
a = ap.parse_args()
rows = []
controls = {
    "native": {},
    "register-off": {"QJS_DISABLE_REGISTER_INTERP": "1"},
    "legacy": {
        "QJS_DISABLE_INTERP_FRAME": "1",
        "QJS_DISABLE_INTERNAL_INTERP": "1",
        "QJS_DISABLE_REGISTER_INTERP": "1",
    },
    "truth-off": {"QJS_DISABLE_FRAME_TRUTHINESS": "1"},
    "truth-zero": {"QJS_DISABLE_FRAME_TRUTHINESS": "0"},
    "number-off": {"QJS_DISABLE_FRAME_NUMBER_TRUTH": "1"},
    "number-zero": {"QJS_DISABLE_FRAME_NUMBER_TRUTH": "0"},
}
for mode, extra in controls.items():
    env = {k: v for k, v in os.environ.items() if not k.startswith("QJS_")}
    env.update(extra)
    p = subprocess.run(
        [*a.runner, a.exe, mode], env=env, text=True, capture_output=True, timeout=180
    )
    if p.returncode:
        raise RuntimeError((mode, p.returncode, p.stdout, p.stderr))
    print(p.stdout.strip(), flush=True)
    match = re.search(r"cases=(\d+) digest=([a-f0-9]{16}) semantic=([a-f0-9]{16})", p.stdout)
    if not match:
        raise ValueError((mode, p.stdout))
    rows.append((mode, match.groups()))
for mode, value in rows:
    if (value[0], value[2]) != (rows[0][1][0], rows[0][1][2]):
        raise ValueError(("Numeric JS value mismatch", rows))
    if mode != "legacy" and value != rows[0][1]:
        raise ValueError(("Numeric VM/C-frame representation mismatch", rows))
print(
    "AARCH64_NUMERIC_DIFFERENTIAL_OK modes=7 cases="
    + rows[0][1][0]
    + " equal-JS-values; native/C-frame equal-tags-and-bits"
)
