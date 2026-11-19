"""Order original MSVC cold contributions independently of archive extraction."""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
import argparse, hashlib, importlib.util, json, shutil, struct, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("cold_order_coff", _frame_tool_path("object-adapter"))
M = importlib.util.module_from_spec(sp)
sp.loader.exec_module(M)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
ap = argparse.ArgumentParser()
ap.add_argument("--register", type=Path, required=True)
ap.add_argument("--last", type=Path, required=True)
a = ap.parse_args()
for p, late in ((a.register, ".qjs$a"), (a.last, ".qjs$z")):
    backup = p.with_name(p.name + ".before-cold-order")
    receipt = p.with_name(p.name + ".cold-order.json")
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        assert previous["status"] == "passed" and sha(backup) == previous["before_sha256"]
        evidence = [backup, receipt]
        known = {previous["after_sha256"]}
        ext = p.with_name(p.name + ".extension.json")
        if ext.exists():
            er = json.loads(ext.read_text())
            eb = p.with_name(p.name + ".before-extension")
            assert sha(eb) == er["before_sha256"] == previous["after_sha256"]
            known.add(er["after_sha256"])
            evidence.extend([eb, ext])
        if sha(p) in known:
            # An unchanged object already has the exact ordered contribution.
            continue
        fresh = M.Coff(p.read_bytes())
        names = []
        for sec in fresh.sections:
            name = sec["name"]
            if name.startswith("/"):
                at = int(name[1:])
                name = fresh.strings[at : fresh.strings.index(0, at)].decode()
            names.append(name)
        assert ".qjscold" in names and late not in names, "Unknown cold-order object"
        epoch = p.with_name(p.name + ".cold-order-history") / str(time.time_ns())
        epoch.mkdir(parents=True, exist_ok=False)
        for item in evidence:
            assert item.resolve().parent == p.resolve().parent
            shutil.copyfile(item, epoch / item.name)
            assert sha(item) == sha(epoch / item.name)
        for item in evidence:
            item.unlink()
    assert not backup.exists() and not receipt.exists()
    raw = p.read_bytes()
    c = M.Coff(raw)
    renamed = []
    for number, r in enumerate(c.section_records, 1):
        name = c.sections[number - 1]["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = c.strings[at : c.strings.index(0, at)].decode()
        if name != ".qjscold":
            continue
        at = len(c.strings)
        c.strings += late.encode() + b"\0"
        encoded = ("/" + str(at)).encode()
        assert len(encoded) <= 8
        c.data[r["pos"] : r["pos"] + 8] = encoded.ljust(8, b"\0")
        for index, sym in c.all_symbols.items():
            if (
                sym["section"] == number
                and sym["name"] == name
                and sym["storage"] == 3
                and sym["type"] == 0
            ):
                struct.pack_into("<II", c.data, c.table + index * c.stride, 0, at)
        renamed.append(dict(section=number, previous=name, candidate=late))
    assert renamed
    result = bytearray(c.finish())
    directive = None
    if p == a.last:
        # MERGE is a supported MSVC .drectve option. Short ordered input names
        # avoid growth from two long POGO/debug section labels; this has no PGO
        # training or address-policy effect. Preserve the existing output name.
        dr = next(r for i, r in enumerate(c.section_records) if c.sections[i]["name"] == ".drectve")
        old_payload = raw[dr["raw"] : dr["raw"] + dr["size"]]
        extra = b" /MERGE:.qjs=.qjscold "
        new_at = len(result)
        result.extend(old_payload + extra)
        struct.pack_into("<II", result, dr["pos"] + 16, len(old_payload) + len(extra), new_at)
        for i, x in c.all_symbols.items():
            if (
                x["name"] == ".drectve"
                and x["storage"] == 3
                and raw[c.table + i * c.stride + c.class_offset + 1]
            ):
                struct.pack_into(
                    "<I", result, c.table + i * c.stride + c.stride, len(old_payload) + len(extra)
                )
        directive = dict(
            old_hex=old_payload.hex(), extra=extra.decode(), new_hex=(old_payload + extra).hex()
        )
    d = M.Coff(result)
    for b, n in zip(c.sections, d.sections):
        for key in ("size", "flags", "sha256", "relocations_sha256", "lines_sha256"):
            if b["name"] == ".drectve" and directive and key in ("size", "sha256"):
                continue
            assert b[key] == n[key]
    for i, b in c.all_symbols.items():
        n = d.all_symbols[i]
        assert all(b[k] == n[k] for k in ("section", "type", "storage", "value"))
        assert b["name"] == n["name"] or b["name"] == ".qjscold" and n["name"] == late
    backup.write_bytes(raw)
    p.write_bytes(result)
    receipt.write_text(
        json.dumps(
            dict(
                status="passed",
                object=str(p),
                before_sha256=sha(backup),
                after_sha256=sha(p),
                runner_sha256=sha(Path(__file__)),
                renamed=renamed,
                merge_directive=directive,
                invariant="Only ordered input names, matching definitions and the explicit MERGE linker directive change. Payloads/relocations/function-symbol addresses/flags stay identical.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("EXPLICIT COLD ORDER", p.name, late, len(renamed), flush=True)
