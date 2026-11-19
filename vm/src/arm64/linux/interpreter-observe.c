/* Optional functional evidence only; never linked in the default image. */
#include "interpreter-observe.h"
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_global_counters[16];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_global_counts(uint64_t out[16])
{
    for (unsigned i = 0; i < 16; i++)
        out[i] = qjs_aarch64_global_counters[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_store_counters[8];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_store_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = qjs_aarch64_store_counters[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_proto_counters[16];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_proto_counts(uint64_t out[16])
{
    for (unsigned i = 0; i < 16; i++)
        out[i] = qjs_aarch64_proto_counters[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_hint_counters[8];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_hint_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = qjs_aarch64_hint_counters[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_primitive_counters[8];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_primitive_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = qjs_aarch64_primitive_counters[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_property_counters[8];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_property_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = qjs_aarch64_property_counters[i];
}
#include <stddef.h>
static _Thread_local QJSArmVMCounts counts;
static _Thread_local uint64_t c_entry_counts[8];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_c_entry(unsigned kind)
{
    if (kind < 8)
        ++c_entry_counts[kind];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_c_entry_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = c_entry_counts[i];
}
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_publish_counters[17];
__attribute__((visibility("hidden"))) _Thread_local uint64_t qjs_aarch64_host_return_counters[4];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_host_return_counts(uint64_t out[4])
{
    for (unsigned i = 0; i < 4; i++)
        out[i] = qjs_aarch64_host_return_counters[i];
}
__attribute__((visibility("hidden"))) void
qjs_aarch64_vm_publication_extended_counts(uint64_t out[17])
{
    for (unsigned i = 0; i < 17; i++)
        out[i] = qjs_aarch64_publish_counters[i];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_publication_counts(uint64_t out[16])
{
    for (unsigned i = 0; i < 16; i++)
        out[i] = qjs_aarch64_publish_counters[i];
}
static _Thread_local uint64_t regexp_op_count;
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_regexp_started(void)
{
    ++regexp_op_count;
}
__attribute__((visibility("hidden"))) uint64_t qjs_aarch64_vm_regexp_count(void)
{
    return regexp_op_count;
}
static _Thread_local uint64_t json_vector_counts[2];
__attribute__((visibility("hidden"))) void qjs_aarch64_json_vector_loaded(void)
{
    ++json_vector_counts[0];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_json_vector_stored(void)
{
    ++json_vector_counts[1];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_json_vector_counts(uint64_t out[2])
{
    out[0] = json_vector_counts[0];
    out[1] = json_vector_counts[1];
}
__attribute__((visibility("hidden"))) void
qjs_aarch64_vm_completed(void *state, uint64_t native_ops, uint64_t c_steps, uintptr_t sp,
                         uint64_t calls, uint64_t returns, uint64_t tail_calls,
                         uint64_t tail_returns)
{
    (void)state;
    counts.activations++;
    counts.native_ops += native_ops;
    counts.c_steps += c_steps;
    counts.last_sp = sp;
    counts.native_calls += calls;
    counts.native_returns += returns;
    counts.tail_calls += tail_calls;
    counts.tail_returns += tail_returns;
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_counts(QJSArmVMCounts *out)
{
    *out = counts;
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_return_resume(void)
{
    ++counts.return_resumes;
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_direct_host(int kind)
{
    if (kind == 2)
        ++counts.class_host;
    else if (kind == 1)
        ++counts.direct_magic;
    else
        ++counts.direct_generic;
}
static _Thread_local uint64_t opcode_counts[256];
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_slow_entry(unsigned opcode)
{
    ++counts.slow_entries;
    ++opcode_counts[opcode];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_opcode_counts(uint64_t out[256])
{
    for (unsigned i = 0; i < 256; i++)
        out[i] = opcode_counts[i];
}
__attribute__((visibility("hidden"))) void qjs_aarch64_vm_window_observe(uint64_t flags)
{
    counts.last_window_flags = flags;
}

__thread uint64_t qjs_aarch64_compare_counters[16];
void qjs_aarch64_vm_comparison_counts(uint64_t out[16])
{
    for (unsigned i = 0; i < 16; i++)
        out[i] = qjs_aarch64_compare_counters[i];
}

__thread uint64_t qjs_aarch64_construct_counters[8];
void qjs_aarch64_vm_constructor_counts(uint64_t out[8])
{
    for (unsigned i = 0; i < 8; i++)
        out[i] = qjs_aarch64_construct_counters[i];
}

__thread uint64_t qjs_aarch64_iterator_counters[16];
void qjs_aarch64_vm_iterator_counts(uint64_t out[16])
{
    for (unsigned i = 0; i < 16; i++)
        out[i] = qjs_aarch64_iterator_counters[i];
}
