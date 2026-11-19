/* Private, opt-in functional counters. Never part of the public SDK ABI. */
#ifndef QJS_AARCH64_INTERPRETER_OBSERVE_H
#define QJS_AARCH64_INTERPRETER_OBSERVE_H
#include <stdint.h>
typedef struct {
    uint64_t activations, native_ops, c_steps;
    uintptr_t last_sp;
    uint64_t native_calls, native_returns;
    uint64_t tail_calls, tail_returns;
    uint64_t return_resumes;
    uint64_t direct_generic, direct_magic;
    uint64_t class_host, slow_entries;
    uint64_t last_window_flags;
} QJSArmVMCounts;
void qjs_aarch64_vm_counts(QJSArmVMCounts *out);
void qjs_aarch64_vm_global_counts(uint64_t out[16]);
void qjs_aarch64_vm_comparison_counts(uint64_t out[16]);
extern __thread uint64_t qjs_aarch64_construct_counters[8];
void qjs_aarch64_vm_constructor_counts(uint64_t out[8]);
extern __thread uint64_t qjs_aarch64_iterator_counters[16];
void qjs_aarch64_vm_iterator_counts(uint64_t out[16]);
void qjs_aarch64_vm_store_counts(uint64_t out[8]);
void qjs_aarch64_vm_property_counts(uint64_t out[8]);
void qjs_aarch64_vm_primitive_counts(uint64_t out[8]);
void qjs_aarch64_vm_hint_counts(uint64_t out[8]);
extern _Thread_local uint64_t qjs_aarch64_proto_counters[16];
void qjs_aarch64_vm_proto_counts(uint64_t out[16]);
void qjs_aarch64_vm_own_allocation_counts(uintptr_t words[6]);
void qjs_aarch64_vm_host_return_counts(uint64_t out[4]);
void qjs_aarch64_vm_publication_extended_counts(uint64_t out[17]);
void qjs_aarch64_vm_c_entry(unsigned kind);
void qjs_aarch64_vm_c_entry_counts(uint64_t out[8]);
void qjs_aarch64_vm_publication_counts(uint64_t out[16]);
void qjs_aarch64_vm_regexp_started(void);
uint64_t qjs_aarch64_vm_regexp_count(void);
void qjs_aarch64_json_vector_loaded(void);
void qjs_aarch64_json_vector_stored(void);
void qjs_aarch64_json_vector_counts(uint64_t out[2]);
void qjs_aarch64_vm_return_resume(void);
void qjs_aarch64_vm_direct_host(int kind);
void qjs_aarch64_vm_slow_entry(unsigned opcode);
void qjs_aarch64_vm_opcode_counts(uint64_t out[256]);
void qjs_aarch64_vm_window_observe(uint64_t flags);
void qjs_aarch64_vm_completed(void *state, uint64_t native_ops, uint64_t c_steps, uintptr_t sp,
                              uint64_t calls, uint64_t returns, uint64_t tail_calls,
                              uint64_t tail_returns);
#endif
