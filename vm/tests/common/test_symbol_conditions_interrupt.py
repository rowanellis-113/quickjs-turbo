"""Public-API regression: exact original polls, owners, exceptions and GC."""

import argparse
import hashlib
import os
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--exe", required=True)
parser.add_argument(
    "--runner", nargs=argparse.REMAINDER, default=[], help="Explicit cross runner argv, placed last"
)
args = parser.parse_args()
PROGRAM_SHA256 = [
    "ac302095f1ed19d715b1e15dc93b1f6fd7ae4d153ea428749181456437425fb6",
    "26be0b269f387901da133d315593b689d633cbab64de14964ba60ee3fc375f99",
    "7c9744205f11f3ae2d34b09f6d28ae79344c03205b45a406d40bee6f37419cdf",
    "20fcabc938a4ac6a8f91b2b640cde9cb57f6df65879dbadd9902eb63dce78d2e",
]


def run(extra=None, options=()):
    env = {
        k: v for k, v in os.environ.items() if not k.upper().startswith(("QJS_", "JSC_", "BENCH_"))
    }
    env["QJS_EXPERIMENT_ALLOCATOR"] = "256"
    env.update(extra or {})
    p = subprocess.run(
        [*args.runner, args.exe, *options],
        env=env,
        capture_output=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if p.returncode:
        raise AssertionError(
            (p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace"))
        )
    return p.stdout


programs = run(options=("--dump-programs",)).decode("ascii").splitlines()
assert len(programs) == 4
assert [hashlib.sha256(bytes.fromhex(p)).hexdigest() for p in programs] == PROGRAM_SHA256
enabled = run()
disabled = run({"QJS_DISABLE_SYMBOL_CASE": "0"})
assert enabled == disabled, "Poll/progress/result/exception stack/GC memory changed"
text = enabled.decode("ascii")
assert text.count("CASE ") == 16 and "SYMBOL_CONDITIONS_INTERRUPT_OK" in text
for case, result in enumerate((150000, 105000, 150000, 105000)):
    m = re.search(
        r"^CASE " + str(case) + r" LIMIT 0 POLLS \d+ EXCEPTION 0 RESULT ([0-9a-f]+)"
        r" PROGRESS ([0-9a-f]+) TOTAL ([0-9a-f]+) MEMORY ",
        text,
        re.M,
    )
    assert m, (case, text)
    values = [int(bytes.fromhex(x).decode("ascii")) for x in m.groups()]
    assert values == [result, 29999, result], (case, values)
print("SYMBOL_CONDITIONS_PUBLIC_OK records=16")
