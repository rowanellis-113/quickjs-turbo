"""Optional pinned ordinary-async worker; unknown compiler shapes stay original."""

import hashlib, importlib.util, json, re, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import (
    activate_tools,
    tool_path,
    source_text,
    generated_file,
    build_file,
    normalized_source_digest,
    source_file,
)

activate_tools()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "generator_capability_" + name.replace("-", "_"), tool_path(name + ".py")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fingerprint(co, name, transfers=(), addresses=()):
    return module("function-fingerprint").fingerprint(co, name, transfers, addresses)


def contract(source):
    value = json.loads(source_text(source, "generator-capability-abi.json"))
    assert (
        normalized_source_digest(source, "quickjs.c") == value["source_sha256"]
        and normalized_source_digest(source, "cutils.h") == value["cutils_sha256"]
    )
    raw = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m[0] for m in module("object-adapter").FUNCTION.finditer(raw)}
    for name, digest in value["source_functions"].items():
        assert hashlib.sha256(functions[name].encode()).hexdigest() == digest, name
    return value


def pointer_sites(co, profile):
    """Prove the reviewed method table without depending on COFF section IDs."""
    table = profile["pointer_table"]
    owners = [
        s for s in co.all_symbols.values() if s["name"] == table["symbol"] and s["section"] > 0
    ]
    if len(owners) != 1:
        return None
    owner = owners[0]
    sn, begin = owner["section"], owner["value"]
    section = co.section_records[sn - 1]
    size = table["record_size"] * len(table["names"])
    if (
        co.sections[sn - 1]["name"] != table["section_name"]
        or not section["flags"] & 0x40000000
        or section["flags"] & 0xA0000000
        or begin + size > section["size"]
    ):
        return None
    payload = bytearray(co.data[section["raw"] + begin : section["raw"] + begin + size])
    positions = {}
    for at in co.relocation_positions(sn):
        offset, index, kind = struct.unpack_from("<IIH", co.data, at)
        if begin <= offset < begin + size:
            relative = offset - begin
            if kind != 1 or relative in positions or relative + 8 > size:
                return None
            positions[relative] = (index, struct.unpack_from("<Q", payload, relative)[0])
            payload[relative : relative + 8] = bytes(8)
    expected = {
        i * table["record_size"] + offset
        for i in range(len(table["names"]))
        for offset in (table["name_offset"], table["function_offset"])
    }
    if (
        set(positions) != expected
        or hashlib.sha256(payload).hexdigest() != table["normalized_sha256"]
    ):
        return None
    sites = []
    for i, name in enumerate(table["names"]):
        index, addend = positions[i * table["record_size"] + table["name_offset"]]
        symbol = co.all_symbols[index]
        if symbol["section"] <= 0:
            return None
        record = co.section_records[symbol["section"] - 1]
        offset = symbol["value"] + addend
        encoded = name.encode() + b"\0"
        if record["flags"] & 0xA0000000 or offset + len(encoded) > record["size"]:
            return None
        if (
            bytes(co.data[record["raw"] + offset : record["raw"] + offset + len(encoded)])
            != encoded
        ):
            return None
    for original in profile["sites"]:
        site = dict(original)
        if site["kind"] == "pointer":
            if site["owner"] != table["symbol"] or site["relative_offset"] not in positions:
                return None
            index, addend = positions[site["relative_offset"]]
            symbol = co.all_symbols[index]
            target = co.symbols.get(site["target"])
            if not target or (symbol["section"], symbol["value"] + addend) != (
                target["section"],
                target["value"],
            ):
                return None
            site.update(section=sn, offset=begin + site["relative_offset"])
        sites.append(site)
    return sites


def reviewed(source, build):
    C = module("object-adapter")
    original = C.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    actual_path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    if not actual_path.exists():
        return None
    actual = C.Coff(actual_path.read_bytes())
    matches = []
    for tc, profile in contract(source)["profiles"].items():
        if all(
            n in original.symbols
            and fingerprint(original, n, f["local_transfers"], f["local_addresses"]) == f
            for n, f in profile["original"].items()
        ) and all(
            n in actual.symbols
            and fingerprint(actual, n, f["local_transfers"], f["local_addresses"]) == f
            for n, f in profile["adapted"].items()
        ):
            sites = pointer_sites(actual, profile)
            if sites is not None:
                matches.append((tc, dict(profile, sites=sites)))
    return matches[0] if len(matches) == 1 else None


def prepare_source(source, source_contract):
    """Prepare the reviewed C algorithm independently of object-file routing.

    The caller validates its platform's source contract first.  Win64 still
    requires reviewed COFF caller/callee shapes; a source-owned platform can
    compile this algorithm with the real private types in the core TU.
    """
    adapter = module("object-adapter")
    raw = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(raw)}
    begin = raw.index("typedef struct JSPromiseData {")
    end = raw.index("} JSPromiseReactionData;", begin) + len("} JSPromiseReactionData;")
    types = raw[begin:end]
    assert hashlib.sha256(types.encode()).hexdigest() == source_contract["promise_types_sha256"]
    begin = raw.index("typedef enum JSAsyncGeneratorStateEnum")
    end = raw.index("} JSAsyncGeneratorData;", begin) + len("} JSAsyncGeneratorData;")
    gen_types = raw[begin:end]
    assert (
        hashlib.sha256(gen_types.encode()).hexdigest() == source_contract["generator_types_sha256"]
    )
    expanded = raw.replace(
        "static inline bool double_is_int32",
        types + "\n" + gen_types + "\nstatic inline bool double_is_int32",
        1,
    )
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    boundary = "\n }\n\nstatic void js_async_generator_reject("
    assert expanded.count(boundary) == 1
    expanded = expanded.replace(boundary, "\n}\n\nstatic void js_async_generator_reject(", 1)
    formatted = "static int JS_PRINTF_FORMAT_ATTR(3, 4) JS_ThrowTypeErrorOrFalse("
    assert expanded.count(formatted) == 1
    expanded = expanded.replace(formatted, "static int JS_ThrowTypeErrorOrFalse(", 1)
    settle = functions["js_async_generator_resolve_or_reject"]
    call = "    ret = JS_Call(ctx, next->resolving_funcs[is_reject], JS_UNDEFINED, 1,\n                  &result);"
    assert settle.count(call) == 1
    settle = settle.replace(
        call,
        """    if (JS_IsUndefined(next->resolving_funcs[0]) && JS_IsUndefined(next->resolving_funcs[1]))
        ret = js_generator_capability_settle(ctx, next->promise, result, is_reject);
    else
"""
        + call,
        1,
    )
    assert expanded.count(functions["js_async_generator_resolve_or_reject"]) == 1
    expanded = expanded.replace(functions["js_async_generator_resolve_or_reject"], settle, 1)
    await_body = functions["js_async_generator_await"].replace(
        "static int js_async_generator_await(", "static int js_generator_capability_await(", 1
    )
    assert await_body.count("JSValue value)") == 1
    await_body = await_body.replace("JSValue value)", "JSValue value, unsigned await_flags)", 1)
    marker = "    if (JS_IsException(promise))\n        goto fail;"
    assert await_body.count(marker) == 1
    await_body = await_body.replace(
        marker,
        marker
        + """
    if (await_flags & 2) {
        int ready = js_ready_generator_await_try(ctx, s, promise);
        if (ready) {
            JS_FreeValue(ctx, promise);
            return ready < 0 ? -1 : 0;
        }
    }
""",
        1,
    )
    marker = "    promise = js_promise_resolve(ctx, ctx->promise_ctor,"
    assert await_body.count(marker) == 1
    await_body = await_body.replace(
        marker,
        """    if (await_flags & 1) {
        int ready = js_ready_generator_direct_try(ctx, s, value);
        if (ready) return ready < 0 ? -1 : 0;
    }
"""
        + marker,
        1,
    )
    parent = functions["js_async_generator_resume_next"].replace(
        "static void js_async_generator_resume_next(", "void JS_GeneratorCapabilityResume(", 1
    )
    opening = parent.index("\n{") + 2
    parent = (
        parent[:opening]
        + """
    unsigned char mode = js_generator_capability_get_mode();
    if (mode & 128) { qjs_generator_capability_original(ctx, s); return; }
"""
        + parent[opening:]
    )
    call = "js_async_generator_await(ctx, s, value)"
    assert parent.count(call) == 1
    parent = parent.replace(call, "js_generator_capability_await(ctx, s, value, mode & 3)", 1)
    promise_new = functions["js_promise_new"].replace(
        "static JSValue js_promise_new(", "static JSValue js_generator_capability_new(", 1
    )
    opening = promise_new.index("\n{") + 2
    promise_new = (
        promise_new[:opening]
        + "\n    resolving_funcs[0] = resolving_funcs[1] = JS_UNDEFINED;\n"
        + promise_new[opening:]
    )
    call = "    if (js_create_resolving_functions(ctx, resolving_funcs, obj)) {"
    assert promise_new.count(call) == 1
    promise_new = promise_new.replace(
        call,
        "    if (ctx->rt->promise_hook && js_create_resolving_functions(ctx, resolving_funcs, obj)) {",
        1,
    )
    next_body = functions["js_async_generator_next"].replace(
        "static JSValue js_async_generator_next(", "JSValue JS_GeneratorCapabilityNext(", 1
    )
    opening = next_body.index("\n{") + 2
    next_body = (
        next_body[:opening]
        + """
    if (!(js_generator_capability_get_mode() & 4) ||
        !JS_GetOpaque(this_val, JS_CLASS_ASYNC_GENERATOR) || !JS_IsObject(ctx->promise_ctor) ||
        ctx->rt->promise_hook ||
        js_check_stack_overflow(ctx->rt, 4096))
        return qjs_generator_capability_original_next(ctx, this_val, argc, argv, magic);
"""
        + next_body[opening:]
    )
    call = "JS_NewPromiseCapability(ctx, resolving_funcs)"
    assert next_body.count(call) == 1
    next_body = next_body.replace(
        call, "js_generator_capability_new(ctx, JS_UNDEFINED, resolving_funcs)", 1
    )
    call = "js_async_generator_resume_next(ctx, s)"
    assert next_body.count(call) == 1
    next_body = next_body.replace(call, "JS_GeneratorCapabilityResume(ctx, s)", 1)
    callback = functions["js_async_generator_resolve_function"].replace(
        "static JSValue js_async_generator_resolve_function(",
        "static JSValue JS_GeneratorCapabilityReaction(",
        1,
    )
    assert callback.count(call) == 1
    callback = callback.replace(call, "JS_GeneratorCapabilityResume(ctx, s)", 1)
    preface = """
#undef JS_CallInternal
#define JS_CallInternal JS_FrameDispatchInternal
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst,
                                       JSValueConst, int, JSValueConst *, int);
#define js_async_generator_resolve_function JS_GeneratorCapabilityReaction
static JSValue JS_GeneratorCapabilityReaction(JSContext *, JSValueConst, int,
                                               JSValueConst *, int, JSValueConst *);
static JSValue js_generator_capability_settle(JSContext *, JSValueConst, JSValueConst, bool);
"""
    body = (
        source_text(source, "generator-capability.inc")
        + "\n"
        + promise_new
        + "\n"
        + await_body
        + "\n"
        + parent
        + "\n"
        + next_body
        + "\n"
        + callback
    )
    return expanded, preface, body


def generate(source, build, target):
    selected = reviewed(source, build)
    if selected is None:
        target.write_text(
            "/* Unknown optional generator capability ABI: retain original. */\ntypedef int qjs_generator_capability_disabled;\n",
            encoding="utf-8",
        )
        return dict(
            enabled=False, exports=[], copies=[], reason="unreviewed compiler/caller/callee shape"
        )
    adapter = module("object-adapter")
    expanded, preface, body = prepare_source(source, contract(source))
    original = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    adapter.HOT_LOCAL_HELPERS |= {
        "js_async_generator_complete",
        "js_async_generator_reject",
        "js_async_generator_resolve",
        "js_async_generator_resolve_function_create",
        "js_async_generator_resolve_or_reject",
        "js_async_generator_completed_return",
        "async_func_free",
        "close_var_refs",
        "close_var_ref",
        "fulfill_or_reject_promise",
        "promise_reaction_data_free",
    }
    owned = (
        "JS_CallInternal",
        "js_async_generator_resume_next",
        "js_async_generator_next",
        "js_async_generator_resolve_function",
        "js_async_generator_await",
        "js_promise_new",
        "JS_GeneratorCapabilityResume",
        "JS_GeneratorCapabilityNext",
        "JS_GeneratorCapabilityReaction",
        "js_generator_capability_await",
        "js_generator_capability_new",
        "js_generator_capability_settle",
    )
    header, exports, copies = adapter.generate(
        expanded, original, preface + body, owned_functions=owned, disabled_macros=("ENABLE_DUMPS",)
    )
    # The fixed core helper, not the unpatched pinned-source copy, is mandatory.
    assert (
        "js_create_resolving_functions" in exports and "js_create_resolving_functions" not in copies
    )
    assert not any(n.startswith("js_async_generator_") for n in exports), (
        "Generator request ownership escaped into an inherited helper"
    )
    private = generated_file(build, "quickjs-generator-capability-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    assertions = """
_Static_assert(sizeof(JSValue)==16 && sizeof(JSJobEntry)==40 && offsetof(JSJobEntry,argv)==40 &&
    sizeof(JSPromiseData)==64 && sizeof(JSPromiseReactionData)==64 &&
    offsetof(JSAsyncGeneratorRequest,promise)==40 && offsetof(JSAsyncGeneratorRequest,resolving_funcs)==56,
    "Pinned generator request and Promise ownership layout");
"""
    target.write_text(
        '#include "quickjs.h"\n'
        + preface
        + '#include "quickjs-generator-capability-private.h"\n'
        + assertions
        + body,
        encoding="utf-8",
        newline="\n",
    )
    return dict(
        enabled=True,
        toolchain=selected[0],
        exports=exports,
        copies=copies,
        private_sha256=sha(private),
        parent_abi="void(JSContext*,JSAsyncGeneratorData*)",
        next_abi="JSCFunctionMagic",
        ownership="Original request.promise; two undefined internal capabilities; original real visible CData recovery callbacks",
    )


def place_control(out):
    C = module("object-adapter")
    raw = out.read_bytes()
    co = C.Coff(raw)
    modes = [
        s
        for s in co.all_symbols.values()
        if s["name"] == "js_generator_capability_mode" and s["section"] > 0
    ]
    assert len(modes) == 1
    mode = modes[0]
    sn = mode["section"]
    rec = co.section_records[sn - 1]
    name = co.sections[sn - 1]["name"]
    assert name == ".bss" and mode["value"] == 0 and mode["storage"] == 3
    assert (
        rec["flags"] & 0x80
        and not rec["flags"] & 0x20000000
        and rec["count"] == 0
        and 0 < rec["size"] <= 16
    )
    assert all(
        s["name"] in (name, mode["name"]) for s in co.all_symbols.values() if s["section"] == sn
    )
    renamed = ".qjsem$zzzzzzgeneratorcapability"
    offset = len(co.strings)
    co.strings += renamed.encode() + b"\0"
    encoded = ("/" + str(offset)).encode()
    assert len(encoded) <= 8
    saved = bytes(co.data[rec["pos"] : rec["pos"] + 8])
    co.data[rec["pos"] : rec["pos"] + 8] = encoded.ljust(8, b"\0")
    symbols = []
    for index, sym in co.all_symbols.items():
        if (
            sym["section"] == sn
            and sym["name"] == name
            and sym["storage"] == 3
            and sym["type"] == 0
        ):
            at = co.table + index * co.stride
            symbols.append((at, bytes(co.data[at : at + 8])))
            struct.pack_into("<II", co.data, at, 0, offset)
    result = co.finish()
    restored = bytearray(result)
    restored[rec["pos"] : rec["pos"] + 8] = saved
    for at, name_bytes in symbols:
        restored[at : at + 8] = name_bytes
    assert C.Coff(restored).sections == C.Coff(raw).sections
    backup = out.with_suffix(".before-control.obj")
    assert not backup.exists()
    backup.write_bytes(raw)
    out.write_bytes(result)
    return dict(
        status="passed-name-only-control-placement", to_section=renamed, exact_restoration=True
    )


def compile_extra(source, build, out):
    generated = {}

    def generator(src, target):
        generated.update(generate(src, build, target))

    selected = reviewed(source, build)
    late = (
        ".qjsex$zzzzzzgeneratorcapability" if selected and selected[0] == "mingw" else ".qjsacp$G"
    )
    module("atod").compile_extra(
        source,
        build,
        out,
        generator=generator,
        filename="quickjs-generator-capability.c",
        late_name=late,
    )
    placement = place_control(out) if generated["enabled"] else None
    receipt = json.loads(out.with_suffix(".compile.json").read_text())
    receipt.update(object_sha256=sha(out), generated=generated, control_placement=placement)
    out.with_suffix(".compile.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return generated


def route_core(source, build):
    C = module("object-adapter")
    path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    original = path.read_bytes()
    raw, packing = module("call-metadata").packed(original, C)
    before, co = C.Coff(raw), C.Coff(raw)
    selected = reviewed(source, build)
    proof_path = generated_file(build, "quickjs-generator-capability-route.json")
    if selected is None:
        proof = dict(
            status="disabled-unknown-profile-input-retained",
            before_sha256=sha(path),
            after_sha256=sha(path),
            hits=[],
        )
        proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        return proof
    tc, profile = selected
    hits = []
    targets = {
        "js_async_generator_resume_next": "JS_GeneratorCapabilityResume",
        "js_async_generator_next": "JS_GeneratorCapabilityNext",
    }
    for site in profile["sites"]:
        callee = before.symbols[site["target"]]
        target = co.external(targets[site["target"]])
        old_index = None
        if site["kind"] == "pointer":
            sn, off = site["section"], site["offset"]
            rec = co.section_records[sn - 1]
            assert not rec["flags"] & 0x20000000
            positions = [
                at
                for at in co.relocation_positions(sn)
                if struct.unpack_from("<I", co.data, at)[0] == off
            ]
            assert len(positions) == 1
            at = positions[0]
            _, index, kind = struct.unpack_from("<IIH", co.data, at)
            old_operand = bytes(co.data[rec["raw"] + off : rec["raw"] + off + 8])
            addend = struct.unpack("<Q", old_operand)[0]
            sym = co.all_symbols[index]
            assert (
                kind == 1
                and sym["section"] == callee["section"]
                and sym["value"] + addend == callee["value"]
            )
            old_index = index
            struct.pack_into("<I", co.data, at + 4, target)
            co.data[rec["raw"] + off : rec["raw"] + off + 8] = bytes(8)
        else:
            caller = before.symbols[site["caller"]]
            sn = caller["section"]
            rec = co.section_records[sn - 1]
            off = caller["value"] + site["offset"]
            assert co.data[rec["raw"] + off - 1] == 0xE8
            positions = [
                at
                for at in co.relocation_positions(sn)
                if struct.unpack_from("<I", co.data, at)[0] == off
            ]
            old_operand = bytes(co.data[rec["raw"] + off : rec["raw"] + off + 4])
            if site["relocated"]:
                assert len(positions) == 1
                at = positions[0]
                _, index, kind = struct.unpack_from("<IIH", co.data, at)
                sym = co.all_symbols[index]
                addend = struct.unpack("<i", old_operand)[0]
                assert (
                    kind == 4
                    and sym["section"] == callee["section"]
                    and sym["value"] + addend == callee["value"]
                )
                old_index = index
                struct.pack_into("<I", co.data, at + 4, target)
            else:
                assert not positions and sn == callee["section"]
                assert off + 4 + struct.unpack("<i", old_operand)[0] == callee["value"]
                co.extra_relocations.setdefault(sn, []).append(struct.pack("<IIH", off, target, 4))
            co.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
        hits.append(
            dict(
                **site,
                actual_section=sn,
                absolute_offset=off,
                old_operand=old_operand.hex(),
                old_symbol=old_index,
            )
        )
    for name, alias_name in (
        ("js_async_generator_resume_next", "qjs_generator_capability_original"),
        ("js_async_generator_next", "qjs_generator_capability_original_next"),
    ):
        callee = before.symbols[name]
        offset = len(co.strings)
        co.strings += alias_name.encode() + b"\0"
        alias = bytearray(co.stride)
        struct.pack_into("<III", alias, 0, 0, offset, callee["value"])
        struct.pack_into("<i" if co.stride == 20 else "<h", alias, 12, callee["section"])
        struct.pack_into("<H", alias, 16 if co.stride == 20 else 14, 32)
        alias[co.class_offset] = 2
        co.aliases.append(alias)
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for hit in hits:
        rec = after.section_records[hit["actual_section"] - 1]
        off = hit["absolute_offset"]
        operand = bytes.fromhex(hit["old_operand"])
        restored[rec["raw"] + off : rec["raw"] + off + len(operand)] = operand
        if hit["old_symbol"] is not None:
            at = next(
                at
                for at in after.relocation_positions(hit["actual_section"])
                if struct.unpack_from("<I", after.data, at)[0] == off
            )
            struct.pack_into("<I", restored, at + 4, hit["old_symbol"])
    for sn in co.extra_relocations:
        old, new = before.section_records[sn - 1], after.section_records[sn - 1]
        struct.pack_into("<I", restored, new["pos"] + 24, old["reloc"])
        struct.pack_into("<H", restored, new["pos"] + 32, old["count"])
    assert C.Coff(restored).sections == before.sections, "Mutation beyond admitted sites"
    assert all(after.all_symbols[i] == s for i, s in before.all_symbols.items()), (
        "Old symbol changed"
    )
    backup = path.with_name(path.name + ".before-generator-capability")
    assert not backup.exists()
    backup.write_bytes(original)
    path.write_bytes(result)
    proof = dict(
        status="passed-generic-abi-and-exact-site-restoration",
        toolchain=tc,
        hits=hits,
        packing=packing,
        all_old_symbols_held=True,
        sections_equal_after_restoration=True,
        before_sha256=sha(backup),
        after_sha256=sha(path),
    )
    proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof
