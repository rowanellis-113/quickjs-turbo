"""Generate source-bound private declarations for the cold IC C module.

No core COFF mutation, frozen private snapshot or compiler/OS assumption in
the common implementation. PORTABLE retains the same body in the core.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import activate_tools, source_file, tool_path

activate_tools()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--core", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location(
        "ic_lifetime_adapter", tool_path("object-adapter.py")
    )
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    source = source_file(a.source, "quickjs.c")
    bodies = [
        source_file(a.source, name)
        for name in ["property-ic-lifetime.c", "property-ic-lifetime.inc"]
    ]
    header, exports, copies = adapter.generate(
        source.read_text(encoding="utf-8"),
        adapter.Coff(a.core.read_bytes()),
        "\n".join(path.read_text(encoding="utf-8") for path in bodies),
    )
    # This module accesses source-private types but calls only public value
    # release and the existing explicit private shape-release entry.
    # An upgrade requiring a new core alias must be reviewed, never inferred.
    if exports or copies:
        raise ValueError("Review new IC lifecycle dependencies: " + str((exports, copies)))
    a.output.write_text(header, encoding="utf-8", newline="\n")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = dict(
        source_sha256=sha(source),
        core_sha256=sha(a.core),
        inputs={str(path): sha(path) for path in bodies},
        output_sha256=sha(a.output),
        core_exports=exports,
        copied_helpers=copies,
        core_mutated=False,
    )
    a.output.with_suffix(".json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
