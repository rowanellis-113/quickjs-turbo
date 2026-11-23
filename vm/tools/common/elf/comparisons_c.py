"""Shared C comparison contract checks without architecture assembly."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, layout, *, contract_rel):
    data = json.loads((source / contract_rel).read_text())
    owners = data.get("owners") or data.get("source_owners") or {}
    for name, digest in owners.items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review comparison semantic owner: " + name)
    if (
        "pinned_core_sha256" in data
        and sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]
    ):
        raise ValueError("Review pinned comparison core before native admission")
    ref_model = layout["reference_count_model"]
    if ref_model == "allocator-prefix":
        if (
            layout["offsets"]["JSMallocBlockHeader.ref_count"]
            - layout["offsets"]["JSMallocBlockHeader.user_data"]
            != -4
        ):
            raise ValueError("Review comparison reference profile")
    elif ref_model != "inline-header":
        raise ValueError("Review comparison reference profile")
    for name, position in data.get("string_bits", {}).items():
        if layout["bits"][name] != position:
            raise ValueError("Review comparison string representation: " + name)
    return data
