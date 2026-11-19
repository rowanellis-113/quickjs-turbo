"""Independently assemble retained macro/expanded OFF streams with real flags."""

import argparse, hashlib, importlib.util, json, re, shlex, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--source", type=Path, required=True)
ap.add_argument("--build", type=Path, required=True)
a = ap.parse_args()
source = a.source.resolve()
build = a.build.resolve()
sys.path.insert(0, str(source / "tools"))
from arm64.paths_arm64 import activate_arm64_tools

activate_arm64_tools()
from elf64 import Elf64
from arm64.vm.publication import expand_macros

wrapper = source / "asm/arm64/linux/interpreter.S"
rows = [
    row
    for row in json.loads((build / "compile_commands.json").read_text())
    if Path(row["file"]).resolve() == wrapper
]
flags_source = wrapper
if not rows:
    generated = build / "generated/aarch64-vm/interpreter-aarch64-number-dataflow.S"
    metadata = json.loads((generated.parent / "NUMBER-DATAFLOW.json").read_text())
    assert metadata["enabled"] is True
    assert hashlib.sha256(generated.read_bytes()).hexdigest() == metadata["generated_sha256"]
    rows = [
        row
        for row in json.loads((build / "compile_commands.json").read_text())
        if Path(row["file"]).resolve() == generated.resolve()
    ]
    flags_source = generated
assert len(rows) == 1
row = rows[0]
flags = shlex.split(row["command"])
out = build / "generated/publication-audit"
out.mkdir(exist_ok=True)
original = wrapper.read_text()
includes = re.findall(r'^#include "(asm/arm64/common/[^\"]+)"$', original, re.M)
expected = [
    "asm/arm64/common/register-ops.inc",
    "asm/arm64/common/register-slots.inc",
    "asm/arm64/common/register-reference-stores.inc",
    "asm/arm64/common/register-references.inc",
    "asm/arm64/common/register-global-bindings.inc",
    "asm/arm64/common/register-comparisons.inc",
    "asm/arm64/common/register-branch.inc",
    "asm/arm64/common/register-numeric.inc",
    "asm/arm64/common/register-forwarding.inc",
    "asm/arm64/common/register-iterators.inc",
    "asm/arm64/common/register-call.inc",
    "asm/arm64/common/register-constructors.inc",
    "asm/arm64/common/register-regexp.inc",
    "asm/arm64/common/register-null-proto.inc",
    "asm/arm64/common/register-arguments.inc",
    "asm/arm64/common/register-varargs.inc",
    "asm/arm64/common/register-indexed.inc",
    "asm/arm64/common/register-literals.inc",
    "asm/arm64/common/register-bigint.inc",
    "asm/arm64/common/register-strings.inc",
    "asm/arm64/common/register-string-append.inc",
    "asm/arm64/common/register-stack-insert.inc",
    "asm/arm64/common/register-host-return.inc",
    "asm/arm64/common/register-property-ic.inc",
    "asm/arm64/common/register-property-primitives.inc",
    "asm/arm64/common/register-property-hints.inc",
    "asm/arm64/common/register-property-prototypes.inc",
    "asm/arm64/common/register-scalar-ops.inc",
]
assert includes == expected, "Review the complete exact current native include stream"
dispatch_macro = re.search(r"(?ms)^\.macro ARM_DISPATCH_NEXT [^\n]+\n.*?^\.endm\n", original)
assert dispatch_macro is not None
expanded = expand_macros(
    dispatch_macro[0] + "".join((source / p).read_text() + "\n" for p in includes)
)
for i, path in enumerate(includes):
    anchor = '#include "' + path + '"'
    assert original.count(anchor) == 1
    original = original.replace(anchor, expanded if i == 0 else "", 1)
objects = []
commands = []
for label, text in [("original", wrapper.read_text()), ("expanded", original)]:
    assembly = out / (label + ".S")
    obj = out / (label + ".o")
    assembly.write_text(text)
    cmd = list(flags)
    cmd[cmd.index("-o") + 1] = str(obj)
    cmd[cmd.index("-c") + 1] = str(assembly)
    p = subprocess.run(cmd, cwd=row["directory"], capture_output=True)
    (out / (label + ".stdout")).write_bytes(p.stdout)
    (out / (label + ".stderr")).write_bytes(p.stderr)
    assert p.returncode == 0, p.stderr.decode(errors="replace")
    commands.append(cmd)
    objects.append(Elf64.read(obj, expected_machine=183))
comparisons = {}
for section in objects[0].sections:
    if section["type"] == 8 or not (section["flags"] & 2 or section["type"] == 4):
        continue
    other = objects[1].section(section["name"])
    raw = objects[0].section_data(section)
    assert raw == objects[1].section_data(other), (
        "GAS macro expansion changes actual object section " + section["name"]
    )
    comparisons[section["name"]] = dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
assert ".text" in comparisons and ".eh_frame" in comparisons
record = dict(
    status="passed-actual-assembly-and-relocation-byte-equivalence",
    commands=commands,
    source_files={p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in includes},
    compared_sections=comparisons,
    instrumented=any("QJS_AARCH64_VM_INSTRUMENT" in f for f in flags),
    real_flags_source=str(flags_source),
    scope="Independent retained macro/expanded parent stream equivalence using actual native compiler flags; actual candidate image is verified separately",
)
(build / "generated/aarch64-vm/PUBLICATION-MACROS.json").write_text(
    json.dumps(record, indent=2) + "\n"
)
print("AARCH64_PUBLICATION_MACROS_OK actual RX/RO/CFI and relocations byte-identical", flush=True)
