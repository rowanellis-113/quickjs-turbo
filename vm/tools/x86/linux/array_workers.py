"""Own accepted array/sort C algorithms using actual Linux x86-64 types."""

from common.elf.array_workers import generate as _common_generate


def generate(source, output, core, adapter, *, include_dense=True, include_append=True):
    return _common_generate(
        source,
        output,
        core,
        adapter,
        include_dense=include_dense,
        include_append=include_append,
        stack_pointer_stmt='__asm__ volatile("movq %%rsp, %0" : "=r"(sp));',
    )
