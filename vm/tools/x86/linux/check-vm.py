import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, source_file

_act_x86()

"""Check actual ELF safety, cold CFI, native PIC hits and deep VM activation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from elf64 import Elf64


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    a = ap.parse_args()
    source, candidate = a.source.resolve(), a.candidate.resolve()
    output = a.output.resolve() if a.output else candidate / "elf-proof"
    output.mkdir(exist_ok=False)
    binary = candidate / "qjs"
    elf = Elf64.read(binary)
    receipt = json.loads((candidate / "BUILD.json").read_text())
    if (
        elf.kind != 3
        or not receipt["register_vm"]
        or hashlib.sha256(binary.read_bytes()).hexdigest() != receipt["binary_sha256"]
    ):
        raise ValueError("Expected the bound PIE register-VM candidate")

    def readelf(label, *flags):
        p = subprocess.run(
            ["readelf", "-W", *flags, str(binary)], capture_output=True, text=True, check=True
        )
        (output / (label + ".stdout")).write_text(p.stdout)
        (output / (label + ".stderr")).write_text(p.stderr)
        if p.stderr:
            raise ValueError("Inspect readelf diagnostic: " + p.stderr)
        return p.stdout

    headers = readelf("headers", "-l", "-d", "-n")
    frames = readelf("frames", "--debug-dump=frames")
    if "TEXTREL" in headers or not re.search(
        r"GNU_STACK\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+RW\s", headers
    ):
        raise ValueError("Expected a non-executable stack and no text relocations")
    functions = {s["name"]: s for s in elf.symbols() if s["type"] == 2}
    root = functions["qjs_linux_vm_enter_private"]
    names = [
        n
        for n in functions
        if n.startswith("qjs_linux_bridge_")
        or n
        in (
            root["name"],
            "JS_FrameInterpPropertyCold",
            "JS_FrameInterpShortBig",
            "JS_FrameInterpCallMeta",
            "JS_FrameInterpPrimitiveEq",
            "JS_FrameOwnBytecodeM1",
            "JS_FrameOwnBytecodeM2",
            "JS_FrameOwnBytecodeM3",
        )
    ]
    vm = (
        json.loads((candidate / "generated/linux-native/VM.json").read_text())
        if (candidate / "generated/linux-native/VM.json").exists()
        else None
    )
    publication = vm.get("native_publication") if vm else None
    actual_label = (
        lambda name: publication["label_mapping"].get(name, name) if publication else name
    )
    extra_native = (
        vm.get("extra_native_functions", []) + vm.get("returning_forward_functions", [])
        if vm
        else []
    )
    if vm and vm.get("native_entries"):
        extra_native += vm["native_entries"]["functions"]
    if vm:
        names += [name for name in extra_native if name not in names]
        names += [name for name in vm.get("extra_vm_functions", []) if name not in names]
    spans = [
        (int(m[1], 16), int(m[2], 16))
        for m in re.finditer(r"FDE .*pc=([0-9a-f]+)\.\.([0-9a-f]+)", frames)
    ]
    for name in names:
        s = functions[name]
        if not s["size"] or not any(
            lo <= s["value"] and s["value"] + s["size"] <= hi for lo, hi in spans
        ):
            raise ValueError("Missing complete FDE coverage: " + name)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QJS_", "JSC_", "BENCH_"))}
    env["QJS_EXPERIMENT_ALLOCATOR"] = "256"

    def gdb(label, commands, fixture, expected):
        script = output / (label + ".gdb")
        script.write_text(
            "set pagination off\nset confirm off\nset disable-randomization off\n"
            + commands
            + "run --std "
            + str(source_file(source, "tests/" + fixture))
            + "\n"
        )
        p = subprocess.run(
            ["gdb", "--batch", "-x", script, binary],
            capture_output=True,
            text=True,
            env=env,
            timeout=40,
        )
        (output / (label + ".stdout")).write_text(p.stdout)
        (output / (label + ".stderr")).write_text(p.stderr)
        if p.returncode or any(marker not in p.stdout for marker in expected):
            raise ValueError((label, p.returncode, p.stdout, p.stderr))

    # Clean retains original opcode addresses; Dirty has source-derived copies.
    # Observe either actual native entry once without requiring one table phase.
    ic_labels = {
        kind: sorted({name, actual_label(name)})
        for kind in (1, 2, 3)
        for name in ("property_ic_M" + str(kind) + "_matched",)
    }
    commands = """python
import gdb
groups={1:[],2:[],3:[]}
class NativeICProbe(gdb.Breakpoint):
    def __init__(self,name,kind):
        super().__init__(name,internal=True);self.kind=kind;groups[kind].append(self)
    def stop(self):
        print('LINUX_NATIVE_IC_'+str(self.kind)+'_HIT')
        for item in groups[self.kind]:item.enabled=False
        return False
for kind,labels in IC_LABELS.items():
    for name in labels:NativeICProbe(name,kind)
end
""".replace("IC_LABELS", repr(ic_labels))
    commands += (
        'break JS_FrameInterpProperty_get_field\ncommands\nsilent\nprintf "LINUX_COLD_HELPER_UNWIND\\n"\n'
        "bt 10\ndisable $bpnum\ncontinue\nend\n"
    )
    gdb(
        "pic-and-cold",
        commands,
        "common/test_property_ic.js",
        [
            "PROPERTY_IC_SMOKE",
            "LINUX_COLD_HELPER_UNWIND",
            *["LINUX_NATIVE_IC_" + str(k) + "_HIT" for k in (1, 2, 3)],
        ],
    )
    vm_spans = [
        (
            functions[n]["value"] - root["value"],
            functions[n]["value"] + functions[n]["size"] - root["value"],
        )
        for n in names
        if not n.startswith("qjs_linux_bridge_") and n not in extra_native
    ]
    deep = """break interp_meta_call_locals_done if *(unsigned long*)($rbx+32) > 5000
commands
silent
python
low = int(gdb.parse_and_eval('(unsigned long)&qjs_linux_vm_enter_private'))
ranges = VM_RANGES
frame = gdb.newest_frame()
count = 0
names = []
while frame is not None:
    count += any(low + lo <= frame.pc() < low + hi for lo, hi in ranges)
    names.append(frame.name())
    frame = frame.older()
print('LINUX_DEEP_VM_ACTIVATIONS=' + str(count))
print('LINUX_DEEP_NATIVE_STACK=' + repr(names))
if count != 1 or names.count('JS_RunFrame') != 1:
    gdb.execute('quit 3')
end
disable 1
continue
end
""".replace("VM_RANGES", repr(vm_spans)).replace(
        "break interp_meta_call_locals_done",
        "break " + actual_label("interp_meta_call_locals_done"),
    )
    gdb(
        "deep-stack",
        deep,
        "common/linux/test_linux_vm_stack.js",
        ["LINUX_VM_STACK_OK", "LINUX_DEEP_VM_ACTIVATIONS=1"],
    )
    if receipt.get("native_virtual_arguments"):
        commands = """python
import gdb
class VirtualArgumentsUnwind(gdb.Breakpoint):
    def stop(self):
        frame=gdb.newest_frame()
        names=[]
        while frame is not None:
            names.append(frame.name())
            frame=frame.older()
        if 'js_linux_virtual_arguments_step' not in names:
            return False
        if not all(n in names for n in ('js_linux_arguments_step_body','JS_FrameArgumentsStep')):
            print('LINUX_VIRTUAL_ARGUMENTS_BAD_UNWIND='+repr(names))
            gdb.execute('quit 3')
        print('LINUX_VIRTUAL_ARGUMENTS_CFI='+repr(names))
        self.enabled=False
        return False
VirtualArgumentsUnwind('JS_LinuxVirtualArgumentsPush',internal=True)
end
"""
        gdb(
            "virtual-arguments",
            commands,
            "common/linux/native_linux_virtual_arguments_unwind.js",
            ["LINUX_VIRTUAL_ARGUMENTS_UNWIND_OK", "LINUX_VIRTUAL_ARGUMENTS_CFI="],
        )
    result = dict(
        status="passed",
        binary_sha256=receipt["binary_sha256"],
        PIE=True,
        text_relocations=False,
        executable_stack=False,
        full_fde_coverage=names,
        native_pic_kinds=[1, 2, 3],
        deep_native_vm_activations=1,
        normal_aslr=True,
        scope="Observed native routes and unwind checks; not a full feature inventory or Test262 qualification",
    )
    (output / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    print("LINUX ELF/PIC/DEEP-VM PROOF PASSED", len(names), "FDEs")


if __name__ == "__main__":
    main()
