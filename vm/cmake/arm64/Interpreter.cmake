enable_language(ASM)
option(QJS_AARCH64_NUMBER_DATAFLOW "Opcode-owned value flow and native number operators" ON)
set(qjs_arm_number_dataflow_arg)
if(QJS_AARCH64_NUMBER_DATAFLOW)
    list(APPEND qjs_arm_number_dataflow_arg --number-dataflow)
endif()
option(QJS_AARCH64_LINEAR_RETURN "Opcode-owned single-pass ordinary return cleanup" ON)
if(QJS_AARCH64_LINEAR_RETURN)
    if(NOT QJS_AARCH64_NUMBER_DATAFLOW)
        message(FATAL_ERROR "Linear return requires QJS_AARCH64_NUMBER_DATAFLOW")
    endif()
    list(APPEND qjs_arm_number_dataflow_arg --linear-return)
endif()
if(QJS_INTERP_FRAME_SCALAR_OPS)
    list(APPEND qjs_defines QJS_AARCH64_SCALAR_OPS)
endif()
if(QJS_INTERP_FRAME_CALL_LEAVES)
    list(APPEND qjs_defines QJS_AARCH64_CALL_LEAVES)
endif()
if(QJS_INTERP_FRAME_STRING_WORKERS)
    list(APPEND qjs_defines QJS_AARCH64_STRING_WORKERS)
    if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        list(APPEND qjs_defines QJS_AARCH64_STRING_POOL)
    endif()
endif()
if(QJS_INTERP_FRAME_NATIVE_NUMERIC)
    list(APPEND qjs_defines QJS_AARCH64_NUMERIC_WORKERS)
endif()
if(QJS_INTERP_FRAME_COMPILER_PROJECTION AND QJS_BACKPORT_CONTEXT_OOM)
    list(APPEND qjs_defines QJS_AARCH64_COMPILER_PROJECTION)
endif()
set(qjs_arm_indexed_enabled OFF)
if(QJS_INTERP_FRAME_INDEXED
   AND (QJS_INTERP_FRAME_CONSTRUCT_CONTINUATION
        OR QJS_INTERP_FRAME_ITERATORS
        OR QJS_INTERP_FRAME_CALL_FORWARD))
    set(qjs_arm_indexed_enabled ON)
    list(APPEND qjs_defines QJS_AARCH64_INDEXED)
endif()
if(QJS_INTERP_FRAME_STACK_INSERT AND qjs_arm_indexed_enabled)
    list(APPEND qjs_defines QJS_AARCH64_STACK_INSERT)
endif()
set(qjs_arm_arguments_enabled OFF)
if(QJS_INTERP_FRAME_ARGUMENTS
   AND QJS_INTERP_FRAME_CALL_FORWARD
   AND QJS_INTERP_FRAME_CONSTRUCT_CONTINUATION)
    set(qjs_arm_arguments_enabled ON)
    list(APPEND qjs_defines QJS_AARCH64_ARGUMENTS)
endif()
set(qjs_arm_varargs_enabled OFF)
if(QJS_INTERP_FRAME_VARARGS
   AND qjs_arm_arguments_enabled
   AND QJS_INTERP_FRAME_ITERATORS)
    set(qjs_arm_varargs_enabled ON)
    list(APPEND qjs_defines QJS_AARCH64_VARARGS)
endif()
set(qjs_arm_literals_enabled OFF)
if(QJS_INTERP_FRAME_LITERALS AND qjs_arm_indexed_enabled)
    set(qjs_arm_literals_enabled ON)
    list(APPEND qjs_defines QJS_AARCH64_LITERALS)
endif()
if(QJS_INTERP_FRAME_NATIVE_NULL_PROTO)
    list(APPEND qjs_defines QJS_AARCH64_NULL_PROTO)
endif()
if(QJS_INTERP_FRAME_ARRAY_SORT)
    list(APPEND qjs_defines QJS_AARCH64_ARRAY_WORKERS)
endif()
if(QJS_INTERP_FRAME_CALL_FORWARD)
    list(APPEND qjs_defines QJS_AARCH64_FORWARDING)
endif()
if(QJS_INTERP_FRAME_ARRAY_OWN)
    list(APPEND qjs_defines QJS_AARCH64_ARRAY_OWN)
endif()
if(QJS_INTERP_FRAME_CONSTRUCT_CONTINUATION
   OR QJS_INTERP_FRAME_ITERATORS
   OR QJS_INTERP_FRAME_CALL_FORWARD)
    list(APPEND qjs_defines QJS_AARCH64_EXTENDED_CALLS)
endif()
if(QJS_INTERP_FRAME_ITERATORS)
    list(APPEND qjs_defines QJS_AARCH64_ITERATORS)
endif()
if(QJS_INTERP_FRAME_CONSTRUCT_CONTINUATION)
    list(APPEND qjs_defines QJS_AARCH64_CONSTRUCTORS QJS_LINUX_CONSTRUCT_CONTINUATION)
endif()
if(QJS_INTERP_FRAME_COMPARISONS)
    list(APPEND qjs_defines QJS_AARCH64_COMPARISONS)
endif()
if(QJS_INTERP_FRAME_GLOBAL_BINDING)
    list(APPEND qjs_defines QJS_AARCH64_GLOBAL_BINDING)
endif()
set(qjs_arm_fast_vm_arg)
set(qjs_arm_fast_vm_outputs)
set(qjs_arm_fast_vm_inputs)
if(QJS_AARCH64_FAST_VM)
    list(APPEND qjs_arm_fast_vm_arg --fast-vm)
    list(APPEND qjs_arm_fast_vm_outputs
         "${CMAKE_CURRENT_BINARY_DIR}/generated/aarch64-vm/FAST-VM.json")
    file(GLOB qjs_arm_fast_vm_scripts CONFIGURE_DEPENDS
         "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/*.py"
         "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/*.py")
    list(APPEND qjs_arm_fast_vm_inputs ${qjs_arm_fast_vm_scripts}
         "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/fast-vm.json")
endif()
set(qjs_arm_vm_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/aarch64-vm")
set(qjs_arm_vm_core "${qjs_arm_vm_dir}/quickjs-aarch64.c")
set(qjs_arm_vm_assembly "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/interpreter.S")
if(QJS_AARCH64_NUMBER_DATAFLOW)
    set(qjs_arm_vm_assembly "${qjs_arm_vm_dir}/interpreter-aarch64-number-dataflow.S")
    set_source_files_properties("${qjs_arm_vm_assembly}" PROPERTIES GENERATED TRUE)
endif()
file(
    GLOB_RECURSE
    qjs_arm_vm_inputs
    CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/value/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/*.inc")
add_custom_command(
    OUTPUT "${qjs_arm_vm_core}"
           "${qjs_arm_vm_dir}/interpreter-aarch64-number-dataflow.S"
           "${qjs_arm_vm_dir}/NUMBER-DATAFLOW.json"
           "${qjs_arm_vm_dir}/VM.json"
           "${qjs_arm_vm_dir}/NULL-PROTO.json"
           "${qjs_arm_vm_dir}/quickjs-linux-null-proto.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-leaf-bridge.inc"
           "${qjs_arm_vm_dir}/SCALAR-OPS.json"
           "${qjs_arm_vm_dir}/CALL-LEAVES.json"
           "${qjs_arm_vm_dir}/quickjs-aarch64-call-leaves.c"
           "${qjs_arm_vm_dir}/quickjs-aarch64-call-leaves-private.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-leaf-supplements.h"
           "${qjs_arm_vm_dir}/STACK-INSERT.json"
           "${qjs_arm_vm_dir}/STRING-WORKERS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-strings.h"
           "${qjs_arm_vm_dir}/NUMERIC-WORKERS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-numeric.h"
           "${qjs_arm_vm_dir}/quickjs-linux-bigint.h"
           "${qjs_arm_vm_dir}/quickjs-linux-atod.c"
           "${qjs_arm_vm_dir}/quickjs-linux-compiler-projection.c"
           "${qjs_arm_vm_dir}/quickjs-linux-compiler-private.h"
           "${qjs_arm_vm_dir}/LITERALS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-literals.h"
           "${qjs_arm_vm_dir}/INDEXED.json"
           "${qjs_arm_vm_dir}/quickjs-linux-indexed.h"
           "${qjs_arm_vm_dir}/VARARGS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-varargs.h"
           "${qjs_arm_vm_dir}/ARGUMENTS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-arguments.h"
           "${qjs_arm_vm_dir}/quickjs-linux-virtual-arguments.c"
           "${qjs_arm_vm_dir}/quickjs-linux-virtual-arguments-private.h"
           "${qjs_arm_vm_dir}/VIRTUAL-ARGUMENTS.json"
           "${qjs_arm_vm_dir}/ARRAY-WORKERS.json"
           "${qjs_arm_vm_dir}/quickjs-linux-arrays.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-values.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-array-own.h"
           "${qjs_arm_vm_dir}/ARRAY-OWN.json"
           "${qjs_arm_vm_dir}/FORWARDING.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-forward.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-captured-readonly.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-dispatch.inc"
           "${qjs_arm_vm_dir}/interpreter-private-abi.h"
           "${qjs_arm_vm_dir}/quickjs-interpreter-slow.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-loop.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-dispatch-c.inc"
           "${qjs_arm_vm_dir}/interpreter-aarch64-shared.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-shared-host.h"
           "${qjs_arm_vm_dir}/quickjs-linux-prepared-callback.h"
           "${qjs_arm_vm_dir}/quickjs-linux-c-workers.h"
           "${qjs_arm_vm_dir}/ASYNC-GENERATOR.json"
           "${qjs_arm_vm_dir}/quickjs-linux-json.h"
           "${qjs_arm_vm_dir}/JSON-WORKERS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-json-scan-test.h"
           "${qjs_arm_vm_dir}/quickjs-linux-regexp.h"
           "${qjs_arm_vm_dir}/REGEXP-WORKERS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-admission.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-regexp.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-publication.inc"
           "${qjs_arm_vm_dir}/interpreter-aarch64-publication-tables.inc"
           "${qjs_arm_vm_dir}/interpreter-aarch64-publication-proxies.inc"
           "${qjs_arm_vm_dir}/PUBLICATION.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-c-entry.h"
           "${qjs_arm_vm_dir}/quickjs-linux-builtin.h"
           "${qjs_arm_vm_dir}/BUILTIN-WORKERS.json"
           "${qjs_arm_vm_dir}/C-ENTRY.json"
           "${qjs_arm_vm_dir}/C-RETURN.json"
           "${qjs_arm_vm_dir}/PROPERTIES.json"
           "${qjs_arm_vm_dir}/PROPERTY-PROTOTYPES.json"
           "${qjs_arm_vm_dir}/REFERENCE-STORES.json"
           "${qjs_arm_vm_dir}/GLOBAL-BINDINGS.json"
           "${qjs_arm_vm_dir}/COMPARISONS.json"
           "${qjs_arm_vm_dir}/CONSTRUCTORS.json"
           "${qjs_arm_vm_dir}/ITERATORS.json"
           "${qjs_arm_vm_dir}/EXTENDED-CALLS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-complete-ops.inc"
           "${qjs_arm_vm_dir}/interpreter-aarch64-constructors.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-construct-host.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-construct-dispatch.h"
           "${qjs_arm_vm_dir}/COMPARISONS-ORIGINAL-ALGORITHMS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-comparisons.h"
           "${qjs_arm_vm_dir}/GLOBAL-ORIGINAL-ALGORITHMS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-global-types.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-globals.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-proto.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-proto-types.h"
           "${qjs_arm_vm_dir}/PROPERTY-HINTS.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-own.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-own-types.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-own-wire.h"
           "${qjs_arm_vm_dir}/PROPERTY-PRIMITIVES.json"
           "${qjs_arm_vm_dir}/interpreter-aarch64-property-types.h"
           "${qjs_arm_vm_dir}/interpreter-aarch64-property-primitives.h"
           ${qjs_arm_fast_vm_outputs}
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/prepare_vm.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --output
        "${qjs_arm_vm_dir}" ${qjs_arm_number_dataflow_arg} ${qjs_arm_fast_vm_arg}
    DEPENDS ${qjs_arm_fast_vm_inputs}
            ${qjs_arm_vm_inputs}
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/scalar_ops.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/vm_source.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/number_dataflow.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/value_flow.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/linear_return.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/linear-return.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/number-dataflow.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-number-local.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/scalar-ops.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-scalar-ops.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/scalar-policy.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/call_leaves.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/call-leaves.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-call-leaves.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/stack_insert.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/stack-insert.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-stack-insert.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/generate_shared_host.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/strings.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/strings.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/string_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-strings.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-string-append.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory/allocator-pool.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/local_string_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/numeric_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/numeric_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/compiler_projection_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/add_local_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/free_boundary_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-bigint.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/string-to-number.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/common/number-rounding.h"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/bytecode/compiler-plan-shim.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/bytecode/compiler-plan-view.h"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/bytecode/compiler-plan.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/abi/compiler-projection.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/numeric-workers.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/bigint-release.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-bigint.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/literals.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/literal_shapes_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/iterator_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/ordinary-literal.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/literals.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-literals.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-literals.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/indexed.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/indexed_ops_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/slow_direct_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/array_append_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/publish_boundary_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/value/instanceof.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-indexed.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/indexed.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-indexed.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/varargs.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/varargs_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/varargs_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/call_forward_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/varargs.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-varargs.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/apply-forward.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-varargs.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/arguments.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/arguments_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/virtual_arguments_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/arguments.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-arguments.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-virtual-arguments.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/ordinary-arguments.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/argument-constructor.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-arguments.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/null_proto.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/null_proto_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/null_arena_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/null-proto.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-null-proto.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-null-proto.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/array_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/array_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/array/copy-grow.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/array/default-string-sort.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/cached-sort.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-prepared-entry.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-sort.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-shared.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/array-workers.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/forwarding.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/forwarding.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-forward.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-forwarding.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/forwarding-probe.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/forwarding-owned.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/forwarding-prepared.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/interpreter-captured-readonly.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/call_prepare_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/array_own.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/array-own.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/array-own.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/iterators.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/extended_calls.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/iterators_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/iterators.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-iterators.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/constructors.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/bellard_backports.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/constructors.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-constructors.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/constructors_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/forwarding_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/construct_continuation_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/interpreter-retained-context.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/comparisons.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/comparisons.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-comparisons.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/comparison-identity.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/comparisons_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/value/loose_control.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/global_bindings.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/global-bindings.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-global-bindings.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/global_bindings_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/global_binding_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/reference-config.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/global-binding-cell.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/reference_stores.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/reference-stores.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-reference-stores.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/own_bytecode_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/asm_text.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/property_store_native.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/prepare_vm.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/c_entry.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/c_return.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/properties.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/property_prototypes.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-prototypes.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-property-prototypes.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/proto_direct_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/proto-load.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/proto-persistent.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/property_hints.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-hints.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-property-hints.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/property_family_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/property_primitives.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-primitives.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-property-primitives.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/length_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/number-property.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/properties.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-property-ic.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/c-return.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-host-return.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/builtin_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-c-entry.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/c-entry.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-linux-c-invoke.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-linux-builtin.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/slice-native.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/admission.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/publication.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/publication.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/large-code-policy.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/interpreter-literal.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-regexp.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/admission.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/elf64.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/layout_input.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/generate_slow_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/prepared_callback_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/generator_capability_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/promise/generator-capability.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/object_adapter_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/c_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/json_workers.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/regexp_workers_arm64.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/regexp_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/regexp_test.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/linux/interpreter-regexp.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/regexp-replace.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/regexp-flags.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/split.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/replace-empty.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/flag-atoms.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/exec.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/test.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/json_worker.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/json_callback_c.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/json.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/kernel/json-callback.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/common/json-vector.h"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/prepared_callbacks_arm64.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/value/arithmetic.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/internal/abi/core-fields.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/linux/interpreter.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-ops.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-call.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-slots.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-references.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-branch.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/common/register-numeric.inc"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/numeric.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/window.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/captures.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/shared.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/prepared-callbacks.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/async-generator.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/json.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/regexp.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-policy.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-policy.h"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-observe.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/interpreter-observe.h"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/vm/__init__.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/workers/__init__.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/hybrid_gc.py"
            "${CMAKE_CURRENT_BINARY_DIR}/generated/backports/BACKPORTS.json"
            "${CMAKE_CURRENT_BINARY_DIR}/compile_commands.json"
    VERBATIM)
add_custom_target(qjs-aarch64-vm-inputs DEPENDS "${qjs_arm_vm_dir}/VM.json")
set_source_files_properties("${qjs_arm_vm_core}" PROPERTIES GENERATED TRUE)
