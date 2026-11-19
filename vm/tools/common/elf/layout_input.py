"""Shared actual-core input and field requests; architecture policy stays with callers."""

import hashlib
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_input(source, build, command_source=None):
    source, build = Path(source).resolve(), Path(build).resolve()
    catalogue_path = source / "src/common/internal/abi/core-fields.json"
    catalogue = json.loads(catalogue_path.read_text())
    receipt = json.loads((build / "generated/backports/BACKPORTS.json").read_text())
    core = Path(receipt["compiler_input"])
    core_src = source_file(source, "quickjs.c")
    if sha(core) != receipt["compiler_input_sha256"] or sha(core_src) != catalogue["source_sha256"]:
        raise ValueError("Core input changed; regenerate/review before measuring Linux layout")
    selected = Path(command_source).resolve() if command_source else core_src.resolve()
    command = next(
        c
        for c in json.loads((build / "compile_commands.json").read_text())
        if Path(c["file"]).resolve() == selected
    )
    argv, flags, index = shlex.split(command["command"]), [], 1
    while index < len(argv):
        if argv[index] in ("-o", "-c"):
            index += 2
        else:
            flags.append(argv[index])
            index += 1
    text, anchor = core.read_text(), "static inline bool double_is_int32"
    if text.count(anchor) != 1:
        raise ValueError("Core prelude anchor changed")
    return SimpleNamespace(
        catalogue_path=catalogue_path,
        catalogue=catalogue,
        receipt=receipt,
        core=core,
        command=command,
        compiler=argv[0],
        flags=flags,
        prelude=text[: text.index(anchor)],
    )


def requests(catalogue, property_ic, alignment=False):
    keys, expressions = [], []
    for name in catalogue["sizes"] + (
        catalogue.get("property_ic_sizes", []) if property_ic else []
    ):
        keys.append(("sizes", name))
        expressions.append("sizeof(" + name + ")")
    for name in catalogue["offsets"] + (
        catalogue.get("property_ic_offsets", []) if property_ic else []
    ):
        owner, field = name.split(".", 1)
        keys.append(("offsets", name))
        expressions.append("offsetof(" + owner + ", " + field + ")")
    for name in catalogue["constants"]:
        keys.append(("constants", name))
        expressions.append("(uint64_t)(int64_t)(" + name + ")")
    if alignment:
        for name in catalogue["sizes"]:
            keys.append(("alignment", name))
            expressions.append("_Alignof(" + name + ")")
    return keys, expressions
