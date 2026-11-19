"""x86-64 Linux RegExp workers adapter."""

from common.elf.regexp_workers import generate as shared_generate


def generate(source, output, core, layout):
    return shared_generate(
        source,
        output,
        core,
        layout,
        contract_rel="src/x86/linux/abi/regexp-workers.json",
        platform_binding="src/common/linux/interpreter-regexp.inc",
        abi_label="SysV",
    )
