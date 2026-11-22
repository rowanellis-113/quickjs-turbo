"""Measure the actual compiler's JSValue return and typed final-release ABI."""

import hashlib, json, re, shutil, struct, subprocess


def generate(source, output, actual, probe, preamble, checks):
    path = source / "src/arm64/linux/abi/c-return.json"
    contract = json.loads(path.read_text())
    for name, expected in contract["source_owners"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review host-result ownership owner: " + name)
    loop = (source / "src/common/call/quickjs-interpreter-loop.inc").read_text()
    signature = re.findall(r"^FRAME_CODE void JS_FrameInterpFree\([^;{}]+\)", loop, re.M)
    if len(signature) != 1:
        raise ValueError("Review actual typed final-release declaration")
    declaration = signature[0].replace("FRAME_CODE", "extern", 1) + ";\n"
    code = (
        actual.prelude
        + preamble
        + '\n#include "src/common/call/interpreter-context-types.inc"\n'
        + checks
        + declaration
        + """
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameInterpFree),
    void (*)(JSFrameRegisterState *,JSContext *,JSValue)),"Actual final-release type");
__attribute__((visibility("hidden"),noipa))
JSValue qjs_aarch64_value_return_witness(uintptr_t payload,int64_t tag)
{JSValue value;value.u.ptr=(void *)payload;value.tag=tag;return value;}
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_value_free_witness(JSFrameRegisterState *state,JSContext *ctx,
                                  uintptr_t payload,int64_t tag)
{JSValue value;value.u.ptr=(void *)payload;value.tag=tag;JS_FrameInterpFree(state,ctx,value);}
__attribute__((used,section(".qjs.arm.creturn"),aligned(8)))
const uint64_t qjs_aarch64_value_geometry[]={sizeof(JSValue),_Alignof(JSValue),
    offsetof(JSValue,tag),sizeof(JSFrameRegisterState),sizeof(JSFrame)};
"""
    )
    elf, values = probe("c-return-abi-probe", code, ".qjs.arm.creturn")
    if values != [16, 8, 8, 168, 128]:
        raise ValueError("Actual C return/value/frame geometry changed")
    symbols = {s["name"]: s for s in elf.symbols() if s["size"] and s["type"] == 2}
    words = {}
    for name, expected in [
        ("qjs_aarch64_value_return_witness", 0xD65F03C0),
        ("qjs_aarch64_value_free_witness", 0x14000000),
    ]:
        symbol = symbols[name]
        section = elf.sections[symbol["section"]]
        data = elf.section_data(section)[symbol["value"] :][: symbol["size"]]
        if len(data) != 4 or struct.unpack("<I", data)[0] != expected:
            raise ValueError(
                "Review target scalar/aggregate ABI witness: " + name + " " + data.hex()
            )
        words[name] = data.hex()
    obj = output / "c-return-abi-probe.o"
    objdump = shutil.which("aarch64-linux-gnu-objdump") or shutil.which("objdump")
    if not objdump:
        raise FileNotFoundError("aarch64-linux-gnu-objdump or objdump is required")
    dump = subprocess.check_output([objdump, "-dr", obj], text=True)
    output.joinpath("c-return-abi-probe.disassembly.txt").write_text(dump)
    if not re.search(r"R_AARCH64_JUMP26\s+JS_FrameInterpFree(?:\s|$)", dump):
        raise ValueError("Free witness must tail-call the actual typed owner")
    record = dict(
        schema=1,
        status="actual-target-ABI-measured-not-executed",
        geometry=values,
        return_abi="Scalar payload/tag x0/x1 are the actual JSValue aggregate return;RET-only compiler witness",
        free_abi="State/context x0/x1 and scalar payload/tag x2/x3 already match actual typed JSValue free;B-only target relocation witness",
        witness_instructions=words,
        actual_free_declaration=signature[0],
        object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256((output / "c-return-abi-probe.c").read_bytes()).hexdigest(),
        contract_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        native_consumer="Ascending receiver/callee/argv;detach before decref;last owner uses original typed Free and owning result spill;tail uses consumed-parent continuation",
        frame_growth=0,
        state_growth=0,
        physical_stack_growth=0,
        hardware_performance_qualified=False,
    )
    output.joinpath("C-RETURN.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
