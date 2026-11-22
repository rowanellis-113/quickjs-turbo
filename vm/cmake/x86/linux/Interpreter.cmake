# Native generation is a normal dependency edge before the core compilation.
# No previous archive, executable, object patching or compiler launcher is used.
enable_language(ASM)
set(qjs_linux_native_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/linux-native")
set(qjs_linux_abi_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/linux-abi")
set(qjs_linux_core "${qjs_linux_native_dir}/quickjs-linux-foundation.c")
set(qjs_linux_numeric "${qjs_linux_native_dir}/quickjs-linux-atod.c")
set(qjs_linux_virtual_arguments "${qjs_linux_native_dir}/quickjs-linux-virtual-arguments.c")
set(qjs_linux_projection "${qjs_linux_native_dir}/quickjs-linux-compiler-projection.c")
set(qjs_linux_vm "${qjs_linux_native_dir}/quickjs-linux-vm.S")
set(qjs_linux_bridges "${qjs_linux_native_dir}/quickjs-linux-bridges.S")
set(qjs_linux_entry "${qjs_linux_native_dir}/quickjs-linux-entry.S")
if(QJS_USE_PREGEN_ASM)
    include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/common/Pregen.cmake")
    qjs_load_pregen_bundle("linux_x86_64")
    return()
endif()
set(qjs_linux_global_outputs)
set(qjs_linux_generation_options)
if(QJS_INTERP_FRAME_GLOBAL_BINDING)
    list(APPEND qjs_linux_global_outputs "${qjs_linux_native_dir}/GLOBAL-BINDINGS.json"
         "${qjs_linux_native_dir}/GLOBAL-BINDINGS-VM.json"
         "${qjs_linux_native_dir}/quickjs-linux-global-bindings.h")
else()
    list(APPEND qjs_linux_generation_options --disable-global-bindings)
endif()
if(QJS_FRAME_EXPERIMENTAL_COMPARE)
    list(APPEND qjs_linux_generation_options --numeric-compare)
endif()
file(
    GLOB_RECURSE
    qjs_linux_generator_inputs
    CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/*.json"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.json"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/*.json")
file(GLOB qjs_linux_assembly_inputs CONFIGURE_DEPENDS
     "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/linux/*.inc")
add_custom_command(
    OUTPUT "${qjs_linux_virtual_arguments}"
           "${qjs_linux_core}"
           "${qjs_linux_vm}"
           "${qjs_linux_bridges}"
           "${qjs_linux_entry}"
           "${qjs_linux_numeric}"
           "${qjs_linux_projection}"
           "${qjs_linux_native_dir}/quickjs-interpreter-slow.h"
           "${qjs_linux_abi_dir}/interpreter-private-abi.h"
           "${qjs_linux_abi_dir}/layout.json"
    BYPRODUCTS "${qjs_linux_native_dir}/VM.json"
               "${qjs_linux_native_dir}/BRIDGES.json"
               "${qjs_linux_abi_dir}/interpreter-private-abi-values.h"
               "${qjs_linux_native_dir}/PREPARE.json"
               "${qjs_linux_native_dir}/SLOW-HOST.json"
               "${qjs_linux_native_dir}/quickjs-linux-loop.h"
               "${qjs_linux_native_dir}/quickjs-linux-admission.h"
               "${qjs_linux_native_dir}/ADMISSION.json"
               "${qjs_linux_native_dir}/NULL-PROTO.json"
               "${qjs_linux_native_dir}/NULL-PROTO-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-null-proto.h"
               "${qjs_linux_native_dir}/quickjs-linux-c-workers.h"
               "${qjs_linux_native_dir}/C-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-prepared-callback.h"
               "${qjs_linux_native_dir}/quickjs-linux-json.h"
               "${qjs_linux_native_dir}/JSON-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-strings.h"
               "${qjs_linux_native_dir}/STRING-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-arrays.h"
               "${qjs_linux_native_dir}/ARRAY-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-builtin.h"
               "${qjs_linux_native_dir}/BUILTIN-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-regexp.h"
               "${qjs_linux_native_dir}/REGEXP-WORKERS.json"
               "${qjs_linux_native_dir}/quickjs-linux-captured-proof.h"
               "${qjs_linux_native_dir}/JS-CALLS.json"
               "${qjs_linux_native_dir}/quickjs-linux-set-name.h"
               "${qjs_linux_native_dir}/quickjs-linux-forward.h"
               "${qjs_linux_native_dir}/FORWARDING.json"
               "${qjs_linux_native_dir}/ENTRIES.json"
               "${qjs_linux_native_dir}/VM-LEAVES.json"
               "${qjs_linux_native_dir}/CONSTRUCT.json"
               "${qjs_linux_native_dir}/quickjs-linux-construct.h"
               "${qjs_linux_native_dir}/quickjs-linux-construct-dispatch.h"
               "${qjs_linux_native_dir}/quickjs-linux-construct-host.h"
               "${qjs_linux_native_dir}/PUBLICATION.json"
               "${qjs_linux_native_dir}/ARGUMENTS.json"
               "${qjs_linux_native_dir}/ARGUMENTS-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-arguments.h"
               "${qjs_linux_native_dir}/quickjs-linux-virtual-arguments-private.h"
               "${qjs_linux_native_dir}/VIRTUAL-ARGUMENTS.json"
               "${qjs_linux_native_dir}/ITERATORS.json"
               "${qjs_linux_native_dir}/ITERATORS-VM.json"
               "${qjs_linux_native_dir}/VARARGS.json"
               "${qjs_linux_native_dir}/VARARGS-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-varargs.h"
               "${qjs_linux_native_dir}/LITERALS.json"
               "${qjs_linux_native_dir}/LITERALS-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-literals.h"
               "${qjs_linux_native_dir}/quickjs-linux-indexed.h"
               "${qjs_linux_native_dir}/INDEXED.json"
               "${qjs_linux_native_dir}/INDEXED-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-properties.h"
               "${qjs_linux_native_dir}/quickjs-linux-property-wire.h"
               "${qjs_linux_native_dir}/PROPERTIES.json"
               "${qjs_linux_native_dir}/PROPERTIES-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-comparisons.h"
               "${qjs_linux_native_dir}/COMPARISONS.json"
               "${qjs_linux_native_dir}/COMPARISONS-VM.json"
               "${qjs_linux_native_dir}/NUMERIC.json"
               "${qjs_linux_native_dir}/NUMERIC-VM.json"
               "${qjs_linux_native_dir}/quickjs-linux-numeric.h"
               "${qjs_linux_native_dir}/quickjs-linux-bigint.h"
               "${qjs_linux_native_dir}/COMPILER-PROJECTION.json"
               "${qjs_linux_native_dir}/quickjs-linux-compiler-private.h"
               ${qjs_linux_global_outputs}
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/linux/prepare-native.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
        ${qjs_linux_generation_options}
    DEPENDS ${qjs_linux_generator_inputs}
            ${qjs_linux_assembly_inputs}
            "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/linux/integer-expression.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/common/array_own.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/mingw-string_index_entry.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/value/instanceof.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/mingw64/mingw-arguments.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/mingw64/mingw-argument-constructor.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/mingw64/mingw-apply-forward.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/mingw64/mingw-ordinary_literal.c"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/mingw-ordinary_literal_entry.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/mingw-arguments_entry.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/mingw-arguments_access.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/mingw-arguments_forward.S"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/paths.py"
            "${QJS_UPSTREAM_DIR}/quickjs.c"
            "${QJS_UPSTREAM_DIR}/quickjs.h"
            "${QJS_UPSTREAM_DIR}/quickjs-opcode.h"
            "${QJS_UPSTREAM_DIR}/quickjs-atom.h"
            "${CMAKE_CURRENT_BINARY_DIR}/generated/backports/BACKPORTS.json"
            "${CMAKE_BINARY_DIR}/compile_commands.json"
    WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
    COMMENT "Measure Linux private ABI and generate native C/ELF sources"
    VERBATIM)
set_source_files_properties(
    "${qjs_linux_virtual_arguments}"
    "${qjs_linux_core}"
    "${qjs_linux_vm}"
    "${qjs_linux_bridges}"
    "${qjs_linux_entry}"
    "${qjs_linux_numeric}"
    "${qjs_linux_projection}"
    PROPERTIES GENERATED TRUE)
