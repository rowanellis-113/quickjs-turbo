# Source-level Windows x86-64 native ASM VM (MSVC cl+ml64, clang-cl, and MinGW GNU/Clang).
# Zero custom COFF patching required; supports standalone, add_subdirectory(), and pregen builds.
set(qjs_win64_native_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/win64-native")
set(qjs_win64_abi_dir "${CMAKE_CURRENT_BINARY_DIR}/generated/win64-abi")
set(qjs_win64_core "${qjs_win64_native_dir}/quickjs-win64-foundation.c")
set(qjs_win64_vm_masm "${qjs_win64_native_dir}/quickjs-win64-vm.asm")
set(qjs_win64_vm_gas "${qjs_win64_native_dir}/quickjs-win64-vm.S")
set(qjs_win64_vm_object "${qjs_win64_native_dir}/quickjs-win64-vm.obj")

if(QJS_USE_PREGEN_ASM)
    include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/common/Pregen.cmake")
    qjs_load_pregen_bundle("win_x86_64")
else()
    # Ensure backported quickjs.c exists before running layout measurement.
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    set(qjs_win64_backport_args
        "${Python3_EXECUTABLE}"
        -X
        utf8
        -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/backport-core.py"
        --source-root
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build-root
        "${CMAKE_CURRENT_BINARY_DIR}"
        --portable-regexp)
    if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        list(APPEND qjs_win64_backport_args --allocator)
    endif()
    if(QJS_BACKPORT_COMPUTED_ASSIGN)
        list(APPEND qjs_win64_backport_args --computed-assign)
    endif()
    if(QJS_BACKPORT_VALUE64_INIT)
        list(APPEND qjs_win64_backport_args --value64-init)
    endif()
    if(QJS_BACKPORT_MIXED_NUMBERS)
        list(APPEND qjs_win64_backport_args --mixed-numbers)
    endif()
    if(QJS_BACKPORT_MAP_POINTER_HASH)
        list(APPEND qjs_win64_backport_args --map-pointer-hash)
    endif()
    if(QJS_PROPERTY_IC)
        list(APPEND qjs_win64_backport_args --property-ic)
    endif()
    if(QJS_TURBO_COROUTINE_SEGMENTS)
        list(APPEND qjs_win64_backport_args --coroutine-segments)
    endif()
    if(QJS_HYBRID_GC)
        list(APPEND qjs_win64_backport_args --hybrid-gc)
    endif()
    get_property(qjs_win64_bp_ready GLOBAL PROPERTY QJS_DECLARED_BACKPORTS_READY)
    if(NOT qjs_win64_bp_ready)
        execute_process(
            COMMAND ${qjs_win64_backport_args} --generate-only
            RESULT_VARIABLE qjs_win64_bp_rc
            OUTPUT_VARIABLE qjs_win64_bp_out
            ERROR_VARIABLE qjs_win64_bp_err)
        if(NOT qjs_win64_bp_rc EQUAL 0)
            message(
                FATAL_ERROR
                    "WIN_X86_64 failed to prepare backported core:\n${qjs_win64_bp_out}\n${qjs_win64_bp_err}"
            )
        endif()
        set_property(GLOBAL PROPERTY QJS_DECLARED_BACKPORTS_READY TRUE)
    endif()

    set(qjs_win64_prepare_args
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --upstream
        "${QJS_UPSTREAM_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        --compiler
        "${CMAKE_C_COMPILER}"
        --define
        QUICKJS_NG_BUILD
        --define
        WIN32
        --define
        _WINDOWS
        --define
        WIN32_LEAN_AND_MEAN
        --define
        _WIN32_WINNT=0x0601
        --define
        _GNU_SOURCE)
    if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
        list(APPEND qjs_win64_prepare_args --define NDEBUG)
    endif()
    if(QJS_PROPERTY_IC)
        list(APPEND qjs_win64_prepare_args --define QJS_PROPERTY_IC)
    endif()
    if(QJS_HYBRID_GC)
        list(APPEND qjs_win64_prepare_args --define QJS_HYBRID_GC)
    endif()
    if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        list(APPEND qjs_win64_prepare_args --define QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
    endif()
    if(MINGW)
        list(APPEND qjs_win64_prepare_args --gnu)
    elseif(CMAKE_C_COMPILER_ID STREQUAL "Clang")
        list(APPEND qjs_win64_prepare_args --clang-cl)
    endif()

    file(
        GLOB_RECURSE
        qjs_win64_generator_inputs
        CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/*.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/*.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/*.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.inc"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.h"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/internal/*.inc")
    add_custom_command(
        OUTPUT "${qjs_win64_core}" "${qjs_win64_vm_masm}" "${qjs_win64_vm_gas}"
               "${qjs_win64_native_dir}/quickjs-interpreter-slow.h"
               "${qjs_win64_abi_dir}/interpreter-private-abi.h" "${qjs_win64_abi_dir}/layout.json"
        BYPRODUCTS "${qjs_win64_native_dir}/PREPARE.json"
                   "${qjs_win64_abi_dir}/interpreter-private-abi-values.h"
        COMMAND
            "${Python3_EXECUTABLE}" -X utf8 -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/prepare_win64_native.py"
            ${qjs_win64_prepare_args}
        DEPENDS ${qjs_win64_generator_inputs}
                "${QJS_UPSTREAM_DIR}/quickjs.c"
                "${QJS_UPSTREAM_DIR}/quickjs.h"
                "${QJS_UPSTREAM_DIR}/quickjs-opcode.h"
                "${QJS_UPSTREAM_DIR}/quickjs-atom.h"
                "${CMAKE_CURRENT_BINARY_DIR}/generated/backports/BACKPORTS.json"
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
        COMMENT "Measure Windows x86-64 ABI and generate native Win64 ASM VM"
        VERBATIM)
    set_source_files_properties("${qjs_win64_core}" "${qjs_win64_vm_masm}" "${qjs_win64_vm_gas}"
                                PROPERTIES GENERATED TRUE)
endif()

# Assemble the Win64 VM object via ml64 (MSVC) or clang-cl (ClangCL).
if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
    get_filename_component(qjs_win64_compiler_dir "${CMAKE_C_COMPILER}" DIRECTORY)
    find_program(
        QJS_FRAME_MASM
        NAMES ml64
        HINTS "${qjs_win64_compiler_dir}" REQUIRED)
    add_custom_command(
        OUTPUT "${qjs_win64_vm_object}"
        COMMAND "${QJS_FRAME_MASM}" /nologo /c "/Fo${qjs_win64_vm_object}" "${qjs_win64_vm_masm}"
        DEPENDS "${qjs_win64_vm_masm}"
        COMMENT "Assemble Windows x86-64 native ASM VM (ml64)"
        VERBATIM)
elseif(MINGW)
    add_custom_command(
        OUTPUT "${qjs_win64_vm_object}"
        COMMAND "${CMAKE_C_COMPILER}" -c -x assembler-with-cpp -fno-lto "${qjs_win64_vm_gas}" -o
                "${qjs_win64_vm_object}"
        DEPENDS "${qjs_win64_vm_gas}"
        COMMENT "Assemble Windows x86-64 native ASM VM (MinGW GAS)"
        VERBATIM)
elseif(CMAKE_C_COMPILER_ID STREQUAL "Clang")
    add_custom_command(
        OUTPUT "${qjs_win64_vm_object}"
        COMMAND "${CMAKE_C_COMPILER}" /c -x assembler-with-cpp -fno-lto "${qjs_win64_vm_gas}"
                "/Fo${qjs_win64_vm_object}"
        DEPENDS "${qjs_win64_vm_gas}"
        COMMENT "Assemble Windows x86-64 native ASM VM (clang-cl)"
        VERBATIM)
else()
    message(FATAL_ERROR "WIN_X86_64 requires MSVC (cl.exe), clang-cl, or MinGW (gcc/clang)")
endif()

set_source_files_properties("${qjs_win64_vm_object}" PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
