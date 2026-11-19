"""Validate source ownership, backend membership and platform boundaries."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import project_root, source_file, source_text


def validate(root):
    root = Path(root).resolve()
    errors = []

    def input_file(relative):
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            errors.append("Missing or foreign source input: " + relative)
        return candidate

    sources = json.loads((root / "src/sources.json").read_text(encoding="utf-8"))
    for name, relative in sources.items():
        input_file(relative)
        if source_file(root, name) != root / relative:
            errors.append("Source ID mismatch: " + name)

    modules = json.loads((root / "tools/common/modules.json").read_text(encoding="utf-8"))
    for name, relative in modules.items():
        path = input_file("tools/" + relative)
        if path.suffix == ".py" and path.is_file():
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for path in (root / "src").rglob("*"):
        if path.suffix not in {".c", ".h", ".inc"}:
            continue
        # Functional common C is flat; private and architecture subtrees retain
        # their own ABI and instruction-set contracts below their named roots.
        if path.relative_to(root / "src").parts[0] in {"x86", "arm64"}:
            continue
        value = path.read_text(encoding="utf-8")
        if re.search(r"\b(?:__asm__?|__m128i?|_mm_\w+)\b", value):
            errors.append(
                "Architecture instruction in common C: " + path.relative_to(root).as_posix()
            )
        for include in re.findall(r'^#include "(src/[^"\n]+)"', value, re.M):
            input_file(include)
            if "/x86/" in include or "/arm64/" in include:
                errors.append("Concrete architecture include in common C: " + include)

    backend = json.loads((root / "src/x86/win64/backend.json").read_text(encoding="utf-8"))
    if backend.get("schema") == 2 and backend.get("route_model") != "live-symbols-v1":
        errors.append("Unknown retained live-route contract")
    counts = {}
    for compiler, data in backend["toolchains"].items():
        ids = {module["id"]: module for module in data["modules"]}
        ordered = sum((data["build_order"][kind] for kind in ("c", "gas", "masm")), [])
        if len(ids) != len(data["modules"]) or sorted(ordered) != sorted(ids):
            errors.append("Incomplete or repeated backend build order: " + compiler)
        objects = set()
        for module in data["modules"]:
            path = input_file(module["source"])
            if (
                path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() != module["source_sha256"]
            ):
                errors.append("Module source receipt is stale: " + module["source"])
            if (
                module["object"] in objects
                or Path(module["object"]).is_absolute()
                or ".." in Path(module["object"]).parts
            ):
                errors.append("Ambiguous or unsafe archive member: " + module["object"])
            objects.add(module["object"])
            if "private_header" in module:
                input_file(module["private_header"])
            if "generated_private_header" in module and (
                module["id"] != "wire"
                or module["generated_private_header"] != "interpreter-wire-private.h"
            ):
                errors.append("Unknown generated private interface: " + module["id"])
        for recipe in data["routes"]:
            if (
                "object_path" not in recipe
                or Path(recipe["object_path"]).is_absolute()
                or ".." in Path(recipe["object_path"]).parts
            ):
                errors.append(
                    "Root route has no build-relative member identity: " + recipe["object"]
                )
            if backend.get("schema") == 2:
                route_flags = {"strict_identity_calls", "strict_identity_only", "array_own_calls"}
                if set(recipe) - ({"object", "object_path", "aliases"} | route_flags):
                    errors.append(
                        "Historical object recipe in live-route bundle: " + recipe["object"]
                    )
                if any(type(recipe[key]) is not bool for key in route_flags if key in recipe):
                    errors.append("Live-route control must be boolean: " + recipe["object"])
                if recipe.get("strict_identity_only") and not recipe.get("strict_identity_calls"):
                    errors.append(
                        "Strict-only route requires strict-identity calls: " + recipe["object"]
                    )
                if any(
                    set(alias) != {"name"} or not alias["name"].startswith("qjs_frame_core_")
                    for alias in recipe.get("aliases", [])
                ):
                    errors.append(
                        "Non-symbol helper alias in live-route bundle: " + recipe["object"]
                    )
        counts[compiler] = len(ids)

    # Source extraction must see a complete C body after shared-fragment factoring.
    json_body = source_text(root, "quickjs-interpreter-json.h")
    for signature in (
        "static JSValue frame_json_number(",
        "static JSValue frame_json_value(",
        "JSON_INLINE unsigned frame_json_hash(",
    ):
        if json_body.count(signature) != 1:
            errors.append("Incomplete or repeated common JSON body: " + signature)
    wire_body = source_text(root, "wire.c")
    core_version = re.search(
        r"^#define BC_VERSION (\d+)",
        source_file(root, "quickjs.c").read_text(encoding="utf-8"),
        re.M,
    )
    wire_version = re.search(r"^#define BC_VERSION (\d+)", wire_body, re.M)
    if not core_version or not wire_version or core_version[1] != wire_version[1]:
        errors.append("Wire serializer does not retain the selected core format")
    for signature in (
        "static int JS_RegExpConstantMask(",
        "static int JS_FinishWriteRegExpBytecode(",
        "static int JS_PrepareFunctionRegExp(",
    ):
        if wire_body.count(signature) != 1:
            errors.append("Incomplete or repeated common wire behavior: " + signature)

    pin = (root / "cmake/QuickJSUpstreamPin.cmake").read_text(encoding="utf-8")
    revision = re.search(r'set\(QJS_UPSTREAM_REVISION "([0-9a-f]+)"\)', pin)[1]
    arm = json.loads((root / "src/arm64/linux/abi/profile.json").read_text(encoding="utf-8"))
    if arm.get("schema") != 1 or arm.get("machine") != 183 or arm.get("native_vm") is not False:
        errors.append("Unreviewed AArch64 standard-call foundation scope")
    for name, digest in arm["files"].items():
        path = input_file(name)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append("AArch64 foundation source receipt is stale: " + name)
    result = dict(
        schema=1,
        status="failed" if errors else "passed",
        source_ids=len(sources),
        tool_modules=len(modules),
        backend_modules=counts,
        upstream=revision,
        native_adapter_upstream=backend["upstream"],
        native_abi_compatible=revision == backend["upstream"],
        aarch64_standard_call_foundation=dict(
            inputs=len(arm["files"]),
            native_vm=False,
            upstream_compatible=revision == arm["upstream_revision"],
        ),
        errors=errors,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=project_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    result = validate(args.source)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    sys.exit(
        bool(result["errors"]) or (args.require_native and not result["native_abi_compatible"])
    )
