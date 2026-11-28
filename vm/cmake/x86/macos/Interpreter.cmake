# Native macOS x86-64 generation is a normal dependency edge before core compilation.
enable_language(ASM)
set(qjs_macos_native_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/macos-native")
set(qjs_macos_abi_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/macos-abi")
set(qjs_macos_core "${qjs_macos_native_dir}/quickjs-linux-foundation.c")
set(qjs_macos_numeric "${qjs_macos_native_dir}/quickjs-linux-atod.c")
set(qjs_macos_virtual_arguments "${qjs_macos_native_dir}/quickjs-linux-virtual-arguments.c")
set(qjs_macos_projection "${qjs_macos_native_dir}/quickjs-linux-compiler-projection.c")
set(qjs_macos_int_expr "${qjs_macos_native_dir}/quickjs-macos-integer-expression.c")
set(qjs_macos_vm "${qjs_macos_native_dir}/quickjs-linux-vm.S")
set(qjs_macos_bridges "${qjs_macos_native_dir}/quickjs-linux-bridges.S")
set(qjs_macos_entry "${qjs_macos_native_dir}/quickjs-linux-entry.S")
# Apple Clang / LLVM's pre-RA early tail duplication expands the shared
# indirectbr dispatch block into ~300 blocks in both JS_LegacyCallInternal and
# JS_CVMResumeInternal, causing RAGreedy to emit ~10x-16x stack-to-stack copies
# across every opcode boundary. Cap early indirectbr duplication and let post-RA
# placement tail duplication emit clean zero-spill direct-threaded dispatches.
if(CMAKE_C_COMPILER_ID MATCHES "Clang")
    include(CheckCSourceCompiles)
    set(_qjs_saved_req_flags "${CMAKE_REQUIRED_FLAGS}")
    set(CMAKE_REQUIRED_FLAGS
        "-mllvm -tail-dup-indirect-size=4 -mllvm -tail-dup-placement-threshold=8")
    check_c_source_compiles("int main(void){return 0;}" QJS_MACOS_CLANG_TAIL_DUP_FLAGS)
    set(CMAKE_REQUIRED_FLAGS "${_qjs_saved_req_flags}")
    if(QJS_MACOS_CLANG_TAIL_DUP_FLAGS)
        set_source_files_properties(
            "${qjs_macos_core}"
            PROPERTIES COMPILE_OPTIONS
                       "-mllvm;-tail-dup-indirect-size=4;-mllvm;-tail-dup-placement-threshold=8")
    endif()
endif()
if(QJS_USE_PREGEN_ASM)
    include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/common/Pregen.cmake")
    qjs_load_pregen_bundle("macos_x86_64")
    return()
endif()
set(qjs_macos_global_outputs)
set(qjs_macos_generation_options)
if(QJS_INTERP_FRAME_GLOBAL_BINDING)
    list(APPEND qjs_macos_global_outputs "${qjs_macos_native_dir}/GLOBAL-BINDINGS.json"
         "${qjs_macos_native_dir}/GLOBAL-BINDINGS-VM.json"
         "${qjs_macos_native_dir}/quickjs-linux-global-bindings.h")
else()
    list(APPEND qjs_macos_generation_options --disable-global-bindings)
endif()
if(QJS_FRAME_EXPERIMENTAL_COMPARE)
    list(APPEND qjs_macos_generation_options --numeric-compare)
endif()
file(
    GLOB_RECURSE
    qjs_macos_generator_inputs
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
file(GLOB qjs_macos_assembly_inputs CONFIGURE_DEPENDS
     "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/linux/*.inc")
add_custom_command(
    OUTPUT "${qjs_macos_virtual_arguments}"
           "${qjs_macos_core}"
           "${qjs_macos_vm}"
           "${qjs_macos_bridges}"
           "${qjs_macos_entry}"
           "${qjs_macos_numeric}"
           "${qjs_macos_projection}"
           "${qjs_macos_int_expr}"
           "${qjs_macos_native_dir}/MACOS-ADAPT.json"
           "${qjs_macos_native_dir}/quickjs-interpreter-slow.h"
           "${qjs_macos_abi_dir}/interpreter-private-abi.h"
           "${qjs_macos_abi_dir}/layout.json"
    BYPRODUCTS "${qjs_macos_native_dir}/VM.json"
               "${qjs_macos_native_dir}/BRIDGES.json"
               "${qjs_macos_abi_dir}/interpreter-private-abi-values.h"
               "${qjs_macos_native_dir}/PREPARE.json"
               "${qjs_macos_native_dir}/SLOW-HOST.json"
               "${qjs_macos_native_dir}/quickjs-linux-loop.h"
               "${qjs_macos_native_dir}/quickjs-linux-admission.h"
               "${qjs_macos_native_dir}/ADMISSION.json"
               "${qjs_macos_native_dir}/NULL-PROTO.json"
               "${qjs_macos_native_dir}/NULL-PROTO-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-null-proto.h"
               "${qjs_macos_native_dir}/quickjs-linux-c-workers.h"
               "${qjs_macos_native_dir}/C-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-prepared-callback.h"
               "${qjs_macos_native_dir}/quickjs-linux-json.h"
               "${qjs_macos_native_dir}/JSON-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-strings.h"
               "${qjs_macos_native_dir}/STRING-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-arrays.h"
               "${qjs_macos_native_dir}/ARRAY-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-builtin.h"
               "${qjs_macos_native_dir}/BUILTIN-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-regexp.h"
               "${qjs_macos_native_dir}/REGEXP-WORKERS.json"
               "${qjs_macos_native_dir}/quickjs-linux-captured-proof.h"
               "${qjs_macos_native_dir}/JS-CALLS.json"
               "${qjs_macos_native_dir}/quickjs-linux-set-name.h"
               "${qjs_macos_native_dir}/quickjs-linux-forward.h"
               "${qjs_macos_native_dir}/FORWARDING.json"
               "${qjs_macos_native_dir}/ENTRIES.json"
               "${qjs_macos_native_dir}/VM-LEAVES.json"
               "${qjs_macos_native_dir}/CONSTRUCT.json"
               "${qjs_macos_native_dir}/quickjs-linux-construct.h"
               "${qjs_macos_native_dir}/quickjs-linux-construct-dispatch.h"
               "${qjs_macos_native_dir}/quickjs-linux-construct-host.h"
               "${qjs_macos_native_dir}/PUBLICATION.json"
               "${qjs_macos_native_dir}/ARGUMENTS.json"
               "${qjs_macos_native_dir}/ARGUMENTS-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-arguments.h"
               "${qjs_macos_native_dir}/quickjs-linux-virtual-arguments-private.h"
               "${qjs_macos_native_dir}/VIRTUAL-ARGUMENTS.json"
               "${qjs_macos_native_dir}/ITERATORS.json"
               "${qjs_macos_native_dir}/ITERATORS-VM.json"
               "${qjs_macos_native_dir}/VARARGS.json"
               "${qjs_macos_native_dir}/VARARGS-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-varargs.h"
               "${qjs_macos_native_dir}/LITERALS.json"
               "${qjs_macos_native_dir}/LITERALS-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-literals.h"
               "${qjs_macos_native_dir}/quickjs-linux-indexed.h"
               "${qjs_macos_native_dir}/INDEXED.json"
               "${qjs_macos_native_dir}/INDEXED-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-properties.h"
               "${qjs_macos_native_dir}/quickjs-linux-property-wire.h"
               "${qjs_macos_native_dir}/PROPERTIES.json"
               "${qjs_macos_native_dir}/PROPERTIES-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-comparisons.h"
               "${qjs_macos_native_dir}/COMPARISONS.json"
               "${qjs_macos_native_dir}/COMPARISONS-VM.json"
               "${qjs_macos_native_dir}/NUMERIC.json"
               "${qjs_macos_native_dir}/NUMERIC-VM.json"
               "${qjs_macos_native_dir}/quickjs-linux-numeric.h"
               "${qjs_macos_native_dir}/quickjs-linux-bigint.h"
               "${qjs_macos_native_dir}/COMPILER-PROJECTION.json"
               "${qjs_macos_native_dir}/quickjs-linux-compiler-private.h"
               ${qjs_macos_global_outputs}
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/macos/prepare-native.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
        ${qjs_macos_generation_options}
    DEPENDS ${qjs_macos_generator_inputs}
            ${qjs_macos_assembly_inputs}
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
    COMMENT "Measure macOS private ABI and generate native C/Mach-O sources"
    VERBATIM)
set_source_files_properties(
    "${qjs_macos_virtual_arguments}"
    "${qjs_macos_core}"
    "${qjs_macos_vm}"
    "${qjs_macos_bridges}"
    "${qjs_macos_entry}"
    "${qjs_macos_numeric}"
    "${qjs_macos_projection}"
    "${qjs_macos_int_expr}"
    PROPERTIES GENERATED TRUE)
