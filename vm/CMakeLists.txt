cmake_minimum_required(VERSION 3.10)

if(POLICY CMP0091)
    cmake_policy(SET CMP0091 NEW)
endif()

project(quickjs LANGUAGES C)

if(NOT DEFINED QJS_UPSTREAM_DIR)
    get_filename_component(QJS_UPSTREAM_DIR "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
else()
    get_filename_component(QJS_UPSTREAM_DIR "${QJS_UPSTREAM_DIR}" ABSOLUTE)
endif()

include(CheckCCompilerFlag)
include(GNUInstallDirs)

set(CMAKE_C_VISIBILITY_PRESET hidden)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_C_STANDARD 11)

macro(xoption OPTION_NAME OPTION_TEXT OPTION_DEFAULT)
    option(${OPTION_NAME} ${OPTION_TEXT} ${OPTION_DEFAULT})
    if(DEFINED ENV{${OPTION_NAME}})
        # Allow setting the option through an environment variable.
        set(${OPTION_NAME} $ENV{${OPTION_NAME}})
    endif()
    if(${OPTION_NAME})
        add_definitions(-D${OPTION_NAME})
    endif()
    message(STATUS "  ${OPTION_NAME}: ${${OPTION_NAME}}")
endmacro()

# note: QJS_ENABLE_TSAN is currently incompatible with the other sanitizers but we
# don't explicitly check for that because who knows what the future will bring?
# QJS_ENABLE_MSAN only works with clang at the time of writing; also not checked
# for the same reason
xoption(BUILD_SHARED_LIBS "Build a shared library" OFF)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR OR QJS_PARENT_IS_TOP_LEVEL)
    set(qjs_default_top_level ON)
else()
    set(qjs_default_top_level OFF)
endif()
xoption(QJS_ENABLE_INSTALL "Enable quickjs installation" ${qjs_default_top_level})
xoption(QJS_BUILD_WERROR "Build with -Werror" OFF)
xoption(QJS_BUILD_EXAMPLES "Build examples" OFF)
xoption(QJS_BUILD_CLI "Build CLI and standalone tool executables" ${qjs_default_top_level})
xoption(QJS_BUILD_CLI_STATIC "Build a static qjs executable" OFF)
xoption(QJS_BUILD_CLI_WITH_MIMALLOC "Build the qjs executable with mimalloc" OFF)
xoption(QJS_BUILD_CLI_WITH_STATIC_MIMALLOC
        "Build the qjs executable with mimalloc (statically linked)" OFF)
xoption(QJS_DISABLE_PARSER "Disable JS source code parser" OFF)
xoption(QJS_ENABLE_ASAN "Enable AddressSanitizer (ASan)" OFF)
xoption(QJS_ENABLE_MSAN "Enable MemorySanitizer (MSan)" OFF)
xoption(QJS_ENABLE_TSAN "Enable ThreadSanitizer (TSan)" OFF)
xoption(QJS_ENABLE_UBSAN "Enable UndefinedBehaviorSanitizer (UBSan)" OFF)
xoption(QJS_ENABLE_GC_STRESS "Force a full GC before every allocation (GC stress test)" OFF)
if(QJS_ENABLE_GC_STRESS)
    add_compile_definitions(FORCE_GC_AT_MALLOC)
endif()

get_directory_property(qjs_dir_compile_defs COMPILE_DEFINITIONS)
get_directory_property(qjs_parent_dir PARENT_DIRECTORY)
set(qjs_parent_compile_defs "")
if(qjs_parent_dir)
    get_directory_property(qjs_parent_compile_defs DIRECTORY "${qjs_parent_dir}"
                                                             COMPILE_DEFINITIONS)
endif()
if(QJS_ENABLE_GC_STRESS
   OR "${qjs_dir_compile_defs};${qjs_parent_compile_defs}" MATCHES "(^|;)FORCE_GC_AT_MALLOC(=|;|$)"
   OR "${CMAKE_C_FLAGS}" MATCHES "(^|[ \t])-DFORCE_GC_AT_MALLOC([= \t]|$)"
   OR QJS_ENABLE_ASAN
   OR QJS_ENABLE_MSAN
   OR QJS_ENABLE_TSAN
   OR QJS_ENABLE_UBSAN)
    if(DEFINED QJS_FRAME_BACKEND AND NOT QJS_FRAME_BACKEND STREQUAL "PORTABLE")
        message(STATUS "Sanitizer or GC stress active; forcing PORTABLE backend")
    endif()
    set(QJS_FRAME_BACKEND
        "PORTABLE"
        CACHE STRING "Selected Turbo VM execution backend" FORCE)
    if(DEFINED QJS_HYBRID_GC AND QJS_HYBRID_GC)
        message(STATUS "Sanitizer or GC stress active; disabling QJS_HYBRID_GC")
    endif()
    set(QJS_HYBRID_GC
        OFF
        CACHE BOOL "Build hybrid reference counting with generational partial cycle collection"
              FORCE)
endif()

include(cmake/QuickJSUpstreamPin.cmake)
include(cmake/common/Backports.cmake)

# Used to properly define JS_LIBC_EXTERN.
add_compile_definitions(QUICKJS_NG_BUILD)

# MINGW doesn't exist in older cmake versions, newer versions don't know
# about CMAKE_COMPILER_IS_MINGW, and there is no unique CMAKE_C_COMPILER_ID
# for mingw-based compilers...
if(MINGW)
    # do nothing
elseif(CMAKE_C_COMPILER MATCHES "mingw")
    set(MINGW TRUE)
else()
    set(MINGW FALSE)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "tvOS")
    set(TVOS TRUE)
else()
    set(TVOS FALSE)
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "watchOS")
    set(WATCHOS TRUE)
else()
    set(WATCHOS FALSE)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "SunOS")
    set(SUNOS TRUE)
else()
    set(SUNOS FALSE)
endif()

if(NOT CMAKE_BUILD_TYPE)
    message(STATUS "No build type selected, default to Release")
    set(CMAKE_BUILD_TYPE "Release")
endif()

include(cmake/common/InterpreterOptions.cmake)

message(STATUS "Building in ${CMAKE_BUILD_TYPE} mode")
message(
    STATUS "Building with ${CMAKE_C_COMPILER_ID} ${CMAKE_C_COMPILER_VERSION} on ${CMAKE_SYSTEM}")

macro(xcheck_add_c_compiler_flag FLAG)
    string(REPLACE "-" "" FLAG_NO_HYPHEN ${FLAG})
    check_c_compiler_flag(${FLAG} COMPILER_SUPPORTS_${FLAG_NO_HYPHEN})
    if(COMPILER_SUPPORTS_${FLAG_NO_HYPHEN})
        add_compile_options("$<$<COMPILE_LANGUAGE:C>:${FLAG}>")
    endif()
endmacro()

xcheck_add_c_compiler_flag(-Wall)
if(NOT MSVC
   AND NOT IOS
   AND NOT TVOS
   AND NOT WATCHOS)
    if(QJS_BUILD_WERROR)
        xcheck_add_c_compiler_flag(-Werror)
    endif()
    xcheck_add_c_compiler_flag(-Wextra)
endif()
xcheck_add_c_compiler_flag(-Wformat=2)
xcheck_add_c_compiler_flag(-Wno-implicit-fallthrough)
xcheck_add_c_compiler_flag(-Wno-sign-compare)
xcheck_add_c_compiler_flag(-Wno-missing-field-initializers)
xcheck_add_c_compiler_flag(-Wno-unused-parameter)
xcheck_add_c_compiler_flag(-Wno-unused-but-set-variable)
xcheck_add_c_compiler_flag(-Wno-unused-result)
xcheck_add_c_compiler_flag(-Wno-stringop-truncation)
xcheck_add_c_compiler_flag(-Wno-array-bounds)
if(NOT SUNOS)
    xcheck_add_c_compiler_flag(-funsigned-char)
endif()

# Clang on Windows without MSVC command line fails because the codebase uses
# functions like strcpy over strcpy_s
if(CMAKE_C_COMPILER_ID STREQUAL "Clang"
   AND WIN32
   AND NOT MSVC)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
    add_compile_definitions(_CRT_NONSTDC_NO_DEPRECATE)
endif()

# ClangCL is command line compatible with MSVC, so 'MSVC' is set.
if(MSVC)
    xcheck_add_c_compiler_flag(-Wno-unsafe-buffer-usage)
    xcheck_add_c_compiler_flag(-Wno-sign-conversion)
    xcheck_add_c_compiler_flag(-Wno-nonportable-system-include-path)
    xcheck_add_c_compiler_flag(-Wno-implicit-int-conversion)
    xcheck_add_c_compiler_flag(-Wno-shorten-64-to-32)
    xcheck_add_c_compiler_flag(-Wno-reserved-macro-identifier)
    xcheck_add_c_compiler_flag(-Wno-reserved-identifier)
    xcheck_add_c_compiler_flag(-Wdeprecated-declarations)
    xcheck_add_c_compiler_flag(/utf-8)
    xcheck_add_c_compiler_flag(/experimental:c11atomics)
    xcheck_add_c_compiler_flag(/wd4018) # -Wno-sign-conversion
    xcheck_add_c_compiler_flag(/wd4061) # -Wno-implicit-fallthrough
    xcheck_add_c_compiler_flag(/wd4100) # -Wno-unused-parameter
    xcheck_add_c_compiler_flag(/wd4200) # -Wno-zero-length-array
    xcheck_add_c_compiler_flag(/wd4242) # -Wno-shorten-64-to-32
    xcheck_add_c_compiler_flag(/wd4244) # -Wno-shorten-64-to-32
    xcheck_add_c_compiler_flag(/wd4245) # -Wno-sign-compare
    xcheck_add_c_compiler_flag(/wd4267) # -Wno-shorten-64-to-32
    xcheck_add_c_compiler_flag(/wd4388) # -Wno-sign-compare
    xcheck_add_c_compiler_flag(/wd4389) # -Wno-sign-compare
    xcheck_add_c_compiler_flag(/wd4456) # Hides previous local declaration
    xcheck_add_c_compiler_flag(/wd4457) # Hides function parameter
    xcheck_add_c_compiler_flag(/wd4710) # Function not inlined
    xcheck_add_c_compiler_flag(/wd4711) # Function was inlined
    xcheck_add_c_compiler_flag(/wd4820) # Padding added after construct
    xcheck_add_c_compiler_flag(/wd4996) # -Wdeprecated-declarations
    xcheck_add_c_compiler_flag(/wd5045
    )# Compiler will insert Spectre mitigation for memory load if /Qspectre switch specified
    if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
        add_compile_options(
            "$<$<AND:$<COMPILE_LANGUAGE:C>,$<OR:$<CONFIG:Release>,$<CONFIG:RelWithDebInfo>>>:/Ob3>"
            "$<$<AND:$<COMPILE_LANGUAGE:C>,$<OR:$<CONFIG:Release>,$<CONFIG:RelWithDebInfo>>>:/Oi>"
            "$<$<AND:$<COMPILE_LANGUAGE:C>,$<OR:$<CONFIG:Release>,$<CONFIG:RelWithDebInfo>>>:/Ot>"
            "$<$<AND:$<COMPILE_LANGUAGE:C>,$<OR:$<CONFIG:Release>,$<CONFIG:RelWithDebInfo>>>:/Gw>")
    endif()
endif()

# Set a 8MB default stack size on Windows.
# It defaults to 1MB on MSVC, which is the same as our current JS stack size,
# so it will overflow and crash otherwise.
# On MinGW it defaults to 2MB.
if(WIN32)
    if(MSVC)
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /STACK:8388608")
    elseif(CMAKE_C_COMPILER_ID MATCHES "Clang" AND NOT MINGW)
        # Clang frontend (clang.exe) targeting the MSVC ABI (using lld-link)
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Xlinker /STACK:8388608")
    else()
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--stack,8388608")
    endif()
endif()

# MacOS and GCC 11 or later need -Wno-maybe-uninitialized
# https://github.com/quickjs-ng/quickjs/issues/453
if(APPLE
   AND CMAKE_C_COMPILER_ID STREQUAL "GNU"
   AND CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 11)
    xcheck_add_c_compiler_flag(-Wno-maybe-uninitialized)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "WASI")
    add_compile_definitions(_WASI_EMULATED_PROCESS_CLOCKS _WASI_EMULATED_SIGNAL)
    add_link_options(-lwasi-emulated-process-clocks -lwasi-emulated-signal)
endif()

if(CMAKE_BUILD_TYPE MATCHES "Debug")
    xcheck_add_c_compiler_flag(/Od)
    xcheck_add_c_compiler_flag(-O0)
    xcheck_add_c_compiler_flag(-ggdb)
    xcheck_add_c_compiler_flag(-fno-omit-frame-pointer)
endif()

if(BUILD_SHARED_LIBS)
    message(STATUS "Building a shared library")
endif()

if(QJS_ENABLE_ASAN)
    message(STATUS "Building with ASan")
    add_compile_options(-fsanitize=address -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address -fno-sanitize-recover=all -fno-omit-frame-pointer)
endif()

if(QJS_ENABLE_MSAN)
    message(STATUS "Building with MSan")
    add_compile_options(-fsanitize=memory -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=memory -fno-sanitize-recover=all -fno-omit-frame-pointer)
endif()

if(QJS_ENABLE_TSAN)
    message(STATUS "Building with TSan")
    add_compile_options(-fsanitize=thread -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=thread -fno-sanitize-recover=all -fno-omit-frame-pointer)
endif()

if(QJS_ENABLE_UBSAN)
    message(STATUS "Building with UBSan")
    add_compile_options(-fsanitize=undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    add_link_options(-fsanitize=undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang")
        # Upstream quickjs.c casts void *(JSContext *, void *, size_t) to DynBufReallocFunc *.
        add_compile_options(-fno-sanitize=function)
        add_link_options(-fno-sanitize=function)
    endif()
endif()

# QuickJS library
#

xoption(QJS_BUILD_LIBC "Build standard library modules as part of the library" OFF)
macro(add_qjs_libc_if_needed target)
    if(NOT QJS_BUILD_LIBC)
        target_link_libraries(${target} PRIVATE qjs-libc)
    endif()
endmacro()
macro(add_static_if_needed target)
    if(QJS_BUILD_CLI_STATIC OR MINGW)
        target_link_options(${target} PRIVATE -static)
        if(MINGW)
            target_link_options(${target} PRIVATE -static-libgcc)
        endif()
    endif()
endmacro()

set(qjs_sources "${QJS_UPSTREAM_DIR}/dtoa.c" "${QJS_UPSTREAM_DIR}/libregexp.c"
                "${QJS_UPSTREAM_DIR}/libunicode.c" "${QJS_UPSTREAM_DIR}/quickjs.c")

if(QJS_ENABLE_UBSAN)
    set(qjs_ubsan_copy_old "memcpy(cr->points, cr1->points, sizeof(cr->points[0]) * cr1->len);")
    set(qjs_ubsan_copy_new
        "if (cr1->len > 0) memcpy(cr->points, cr1->points, sizeof(cr->points[0]) * cr1->len);")
    set(qjs_ubsan_norm_old "memcpy(buf, src, src_len * sizeof(int));")
    set(qjs_ubsan_norm_new "if (src_len > 0) memcpy(buf, src, src_len * sizeof(int));")
    set(qjs_ubsan_libunicode_in "${CMAKE_CURRENT_BINARY_DIR}/generated/ubsan-libunicode.c.in")
    set(qjs_ubsan_libunicode_out "${CMAKE_CURRENT_BINARY_DIR}/generated/ubsan-libunicode.c")
    file(READ "${QJS_UPSTREAM_DIR}/libunicode.c" qjs_ubsan_libunicode)
    string(FIND "${qjs_ubsan_libunicode}" "${qjs_ubsan_copy_old}" qjs_ubsan_copy_pos)
    string(FIND "${qjs_ubsan_libunicode}" "${qjs_ubsan_norm_old}" qjs_ubsan_norm_pos)
    if(qjs_ubsan_copy_pos EQUAL -1 OR qjs_ubsan_norm_pos EQUAL -1)
        message(FATAL_ERROR "Expected empty-buffer memcpy sites missing in upstream libunicode.c")
    endif()
    string(REPLACE "${qjs_ubsan_copy_old}" "${qjs_ubsan_copy_new}" qjs_ubsan_libunicode
                   "${qjs_ubsan_libunicode}")
    string(REPLACE "${qjs_ubsan_norm_old}" "${qjs_ubsan_norm_new}" qjs_ubsan_libunicode
                   "${qjs_ubsan_libunicode}")
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
    file(WRITE "${qjs_ubsan_libunicode_in}" "${qjs_ubsan_libunicode}")
    configure_file("${qjs_ubsan_libunicode_in}" "${qjs_ubsan_libunicode_out}" COPYONLY)
    set_property(
        DIRECTORY
        APPEND
        PROPERTY CMAKE_CONFIGURE_DEPENDS "${QJS_UPSTREAM_DIR}/libunicode.c")
    list(REMOVE_ITEM qjs_sources "${QJS_UPSTREAM_DIR}/libunicode.c")
    list(APPEND qjs_sources "${qjs_ubsan_libunicode_out}")
endif()

if(QJS_BACKPORT_PORTABLE_REGEXP
   OR QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64"
   OR QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64"
   OR QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64"
   OR QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN_X86_64")
    # Native workers share this common engine and its wire translation;
    # the portable backend selects the same ordinary C through its option.
    list(REMOVE_ITEM qjs_sources "${QJS_UPSTREAM_DIR}/libregexp.c")
    list(APPEND qjs_sources src/common/regexp/libregexp.c
         src/common/regexp/unicode/regexp-unicode.c)
    set_property(
        SOURCE src/common/regexp/libregexp.c
        APPEND
        PROPERTY COMPILE_DEFINITIONS QJS_FRAME_REGEXP_PRIVATE_UNICODE=1)
endif()

if(QJS_BUILD_LIBC)
    list(APPEND qjs_sources "${QJS_UPSTREAM_DIR}/quickjs-libc.c")
    # The definition must be added to the entire project.
    add_compile_definitions(QJS_BUILD_LIBC)
endif()
list(APPEND qjs_defines _GNU_SOURCE)
if(WIN32)
    # NB: Windows 7 is EOL and we are only supporting in so far as it doesn't interfere with progress.
    list(APPEND qjs_defines WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0601)
else()
    # UNIX-y platforms.
    list(APPEND qjs_libs m)
endif()
if(TVOS)
    list(APPEND qjs_defines _TVOS)
endif()
if(WATCHOS)
    list(APPEND qjs_defines _WATCHOS)
endif()
list(APPEND qjs_libs ${CMAKE_DL_LIBS})
find_package(Threads)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "WASI")
    list(APPEND qjs_libs ${CMAKE_THREAD_LIBS_INIT})
endif()

# Always compile the runtime configuration API and environment helpers into qjs.
list(APPEND qjs_sources src/common/internal/turbo-config.c src/common/internal/interpreter-env.c)

set(qjs_turbo_backend_id 0)
set(qjs_turbo_backend_name "C_FALLBACK")
if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
    set(qjs_turbo_backend_id 1)
    set(qjs_turbo_backend_name "LINUX_X86_64")
elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64")
    set(qjs_turbo_backend_id 2)
    set(qjs_turbo_backend_name "LINUX_AARCH64")
elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
    set(qjs_turbo_backend_id 3)
    set(qjs_turbo_backend_name "MACOS_X86_64")
elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN_X86_64")
    set(qjs_turbo_backend_id 4)
    set(qjs_turbo_backend_name "WIN_X86_64")
endif()
if(QJS_USE_PREGEN_ASM AND QJS_ENABLE_INTERP_FRAME)
    set(qjs_turbo_pregen_asm 1)
else()
    set(qjs_turbo_pregen_asm 0)
endif()
list(APPEND qjs_defines QJS_TURBO_BACKEND_ID=${qjs_turbo_backend_id}
     "QJS_TURBO_BACKEND_NAME=\"${qjs_turbo_backend_name}\""
     QJS_TURBO_PREGEN_ASM=${qjs_turbo_pregen_asm})
if(NOT QJS_BACKPORT_CONTEXT_OOM)
    list(APPEND qjs_defines QJS_TURBO_NO_CORE_OVERLAY=1)
endif()

if(QJS_ENABLE_INTERP_FRAME)
    # Linux, macOS, ARM64 and WIN_X86_64 measure and generate source inputs first.
    # All keep the core in its own object target.
    list(REMOVE_ITEM qjs_sources "${QJS_UPSTREAM_DIR}/quickjs.c")
    if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN_X86_64")
        include(cmake/x86/win64/NativeWin64.cmake)
        add_library(qjs-core OBJECT "${qjs_win64_core}")
        target_compile_definitions(
            qjs-core PRIVATE QJS_ENABLE_INTERP_FRAME QJS_INTERP_FRAME_INTERNAL_ENTRY
                             QJS_INTERP_FRAME_REGISTER_ABI QJS_WIN64_NATIVE_VM)
        target_include_directories(
            qjs-core BEFORE PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/backports"
                                    "${qjs_win64_native_dir}" "${qjs_win64_abi_dir}")
        list(APPEND qjs_sources "${qjs_win64_vm_object}")
    elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64")
        include(cmake/arm64/Interpreter.cmake)
        add_library(qjs-core OBJECT "${qjs_arm_vm_core}")
        target_compile_definitions(
            qjs-core PRIVATE QJS_INTERP_FRAME_LINUX QJS_INTERP_FRAME_INTERNAL_ENTRY
                             QJS_INTERP_FRAME_REGISTER_ABI QJS_LINUX_REGISTER_FOUNDATION)
        target_include_directories(
            qjs-core BEFORE PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/backports"
                                    "${qjs_arm_vm_dir}")
        list(
            APPEND
            qjs_sources
            "${qjs_arm_vm_assembly}"
            asm/arm64/linux/comparison-identity.S
            asm/arm64/linux/array-own.S
            asm/arm64/linux/forwarding-probe.S
            asm/arm64/linux/forwarding-owned.S
            asm/arm64/linux/forwarding-prepared.S
            src/arm64/linux/interpreter-policy.c)
    elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
        include(cmake/x86/macos/Interpreter.cmake)
        add_library(qjs-core OBJECT "${qjs_macos_core}" "${qjs_macos_numeric}"
                                    "${qjs_macos_projection}" "${qjs_macos_virtual_arguments}")
        target_compile_definitions(
            qjs-core
            PRIVATE QJS_INTERP_FRAME_LINUX QJS_INTERP_FRAME_INTERNAL_ENTRY
                    QJS_INTERP_FRAME_REGISTER_ABI QJS_LINUX_REGISTER_FOUNDATION
                    QJS_INTERP_FRAME_LINUX_SHARED)
        target_include_directories(
            qjs-core BEFORE PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/backports"
                                    "${qjs_macos_native_dir}" "${qjs_macos_abi_dir}")
        list(APPEND qjs_sources "${qjs_macos_vm}" "${qjs_macos_bridges}" "${qjs_macos_entry}")
    else()
        include(cmake/x86/linux/Interpreter.cmake)
        add_library(qjs-core OBJECT "${qjs_linux_core}" "${qjs_linux_numeric}"
                                    "${qjs_linux_projection}" "${qjs_linux_virtual_arguments}")
        target_compile_definitions(
            qjs-core
            PRIVATE QJS_INTERP_FRAME_LINUX QJS_INTERP_FRAME_INTERNAL_ENTRY
                    QJS_INTERP_FRAME_REGISTER_ABI QJS_LINUX_REGISTER_FOUNDATION
                    QJS_INTERP_FRAME_LINUX_SHARED)
        target_include_directories(
            qjs-core BEFORE PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/backports"
                                    "${qjs_linux_native_dir}" "${qjs_linux_abi_dir}")
        list(APPEND qjs_sources "${qjs_linux_vm}" "${qjs_linux_bridges}" "${qjs_linux_entry}")
    endif()
    target_compile_definitions(qjs-core PRIVATE ${qjs_defines})
    target_include_directories(qjs-core PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}"
                                                "${CMAKE_CURRENT_BINARY_DIR}")
    list(APPEND qjs_sources $<TARGET_OBJECTS:qjs-core>)
endif()
if(QJS_BACKPORT_CONTEXT_OOM)
    list(APPEND qjs_sources src/common/bytecode/compiler-plan.c)
endif()
add_library(qjs ${qjs_sources})
add_library(qjs::qjs ALIAS qjs)
add_library(quickjs-turbo::qjs ALIAS qjs)

# Isolate native ASM/bridge compilation units from host LTO/IPO so downstream
# projects can keep full LTO enabled on their own code.
if(QJS_ENABLE_INTERP_FRAME)
    foreach(_qjs_lto_target IN ITEMS qjs-core qjs)
        if(TARGET ${_qjs_lto_target})
            set_target_properties(
                ${_qjs_lto_target}
                PROPERTIES INTERPROCEDURAL_OPTIMIZATION OFF
                           INTERPROCEDURAL_OPTIMIZATION_RELEASE OFF
                           INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO OFF
                           INTERPROCEDURAL_OPTIMIZATION_MINSIZEREL OFF
                           INTERPROCEDURAL_OPTIMIZATION_DEBUG OFF)
            if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
                target_compile_options(${_qjs_lto_target} PRIVATE "$<$<COMPILE_LANGUAGE:C>:/GL->")
            elseif(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
                target_compile_options(${_qjs_lto_target}
                                       PRIVATE "$<$<COMPILE_LANGUAGE:C>:-fno-lto>")
            endif()
        endif()
    endforeach()
endif()
if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64")
    add_dependencies(qjs qjs-aarch64-vm-inputs)
    if(QJS_INTERP_FRAME_SCALAR_OPS)
        target_sources(qjs PRIVATE src/arm64/linux/scalar-policy.c)
    endif()
    if(QJS_INTERP_FRAME_CALL_LEAVES)
        set(qjs_arm_leaves "${qjs_arm_vm_dir}/quickjs-aarch64-call-leaves.c")
        set_source_files_properties("${qjs_arm_leaves}" PROPERTIES GENERATED TRUE)
        target_sources(qjs PRIVATE "${qjs_arm_leaves}")
    endif()
    if(QJS_INTERP_FRAME_NATIVE_NUMERIC)
        set(qjs_arm_atod "${qjs_arm_vm_dir}/quickjs-linux-atod.c")
        set_source_files_properties("${qjs_arm_atod}" PROPERTIES GENERATED TRUE)
        target_sources(qjs PRIVATE "${qjs_arm_atod}" asm/arm64/linux/bigint-release.S)
    endif()
    if(QJS_INTERP_FRAME_COMPILER_PROJECTION AND QJS_BACKPORT_CONTEXT_OOM)
        set(qjs_arm_projection "${qjs_arm_vm_dir}/quickjs-linux-compiler-projection.c")
        set_source_files_properties(
            "${qjs_arm_projection}"
            PROPERTIES
                GENERATED TRUE
                COMPILE_DEFINITIONS
                "QJS_INTERP_FRAME_INTERNAL_ENTRY;QJS_INTERP_FRAME_REGISTER_ABI;QJS_INTERP_FRAME_LINUX;QJS_LINUX_REGISTER_FOUNDATION;QJS_INTERP_FRAME_LINUX_SHARED"
        )
        target_sources(qjs PRIVATE "${qjs_arm_projection}")
    endif()
    target_include_directories(qjs PRIVATE "${qjs_arm_vm_dir}")
    if(QJS_AARCH64_VM_INSTRUMENT)
        target_compile_definitions(qjs PRIVATE QJS_AARCH64_VM_INSTRUMENT)
        target_compile_definitions(qjs-core PRIVATE QJS_AARCH64_VM_INSTRUMENT)
        target_sources(qjs PRIVATE src/arm64/linux/interpreter-observe.c)
    endif()
endif()
qjs_apply_declared_backports(qjs)
if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
    target_sources(qjs PRIVATE src/x86/linux/integer-expression.c)
elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
    target_sources(qjs PRIVATE "${qjs_macos_int_expr}")
endif()
target_compile_definitions(qjs PRIVATE ${qjs_defines})
target_include_directories(
    qjs
    PUBLIC $<BUILD_INTERFACE:${QJS_UPSTREAM_DIR}> $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
           $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_link_libraries(qjs PUBLIC ${qjs_libs})

# Pass a compiler definition so that Windows gets its declspec's right.
get_target_property(QJS_LIB_TYPE qjs TYPE)
if(QJS_LIB_TYPE STREQUAL "SHARED_LIBRARY")
    target_compile_definitions(
        qjs
        PRIVATE BUILDING_QJS_SHARED
        PUBLIC USING_QJS_SHARED)
endif()

# An interface library for modules.
add_library(qjs_module_lib INTERFACE)
target_include_directories(qjs_module_lib
                           INTERFACE $<TARGET_PROPERTY:qjs,INTERFACE_INCLUDE_DIRECTORIES>)
target_compile_definitions(
    qjs_module_lib INTERFACE QUICKJS_NG_MODULE_BUILD
                             $<TARGET_PROPERTY:qjs,INTERFACE_COMPILE_DEFINITIONS>)
if(WIN32)
    # Since Windows cannot resolve symbols at load time, we need to
    # explicitly link it to qjs.
    target_link_libraries(qjs_module_lib INTERFACE qjs)
endif()

if(NOT QJS_BUILD_LIBC)
    add_library(qjs-libc STATIC EXCLUDE_FROM_ALL "${QJS_UPSTREAM_DIR}/quickjs-libc.c")
    qjs_apply_declared_backports(qjs-libc)
    target_include_directories(qjs-libc PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(qjs-libc PRIVATE ${qjs_defines})
    target_link_libraries(qjs-libc PRIVATE ${qjs_libs} qjs)
endif()

if(EMSCRIPTEN)
    add_executable(qjs_wasm ${qjs_sources})
    target_include_directories(qjs_wasm PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}")
    qjs_apply_declared_backports(qjs_wasm)
    target_link_options(
        qjs_wasm
        PRIVATE
        # in emscripten 3.x, this will be set to 16k which is too small for quickjs. #write sth. to force github rebuild
        -sSTACK_SIZE=2097152 # let it be 2m = 2 * 1024 * 1024 = 2097152, otherwise, stack overflow may be occured at bootstrap
        -sNO_INVOKE_RUN
        -sNO_EXIT_RUNTIME
        -sMODULARIZE # do not mess the global
        -sEXPORT_ES6 # export js file to morden es module
        -sEXPORT_NAME=getQuickJs # give a name
        -sTEXTDECODER=1 # it will be 2 if we use -Oz, and that will cause js -> c string convertion fail
        -sNO_DEFAULT_TO_CXX # this project is pure c project, no need for c plus plus handle
        -sEXPORTED_RUNTIME_METHODS=ccall,cwrap)
    target_compile_definitions(qjs_wasm PRIVATE ${qjs_defines})
    target_link_libraries(qjs_wasm PRIVATE m)
endif()

# QuickJS bytecode compiler & CLI
#

if(QJS_BUILD_CLI)
    add_executable(qjsc "${QJS_UPSTREAM_DIR}/qjsc.c")
    add_qjs_libc_if_needed(qjsc)
    add_static_if_needed(qjsc)
    target_compile_definitions(qjsc PRIVATE ${qjs_defines})
    target_link_libraries(qjsc PRIVATE qjs)

    add_executable(qjs_exe "${QJS_UPSTREAM_DIR}/gen/repl.c" "${QJS_UPSTREAM_DIR}/gen/standalone.c"
                           "${QJS_UPSTREAM_DIR}/qjs.c")
    add_qjs_libc_if_needed(qjs_exe)
    add_static_if_needed(qjs_exe)
    set_target_properties(
        qjs_exe
        PROPERTIES OUTPUT_NAME "qjs"
                   PDB_NAME "qjs_cli"
                   COMPILE_PDB_NAME "qjs_cli")
    target_compile_definitions(qjs_exe PRIVATE ${qjs_defines})
    target_link_libraries(qjs_exe PRIVATE qjs)
    if(NOT WIN32)
        set_target_properties(qjs_exe PROPERTIES ENABLE_EXPORTS TRUE)
    endif()
endif()

# WASI Reactor
#

if(CMAKE_SYSTEM_NAME STREQUAL "WASI")
    option(QJS_WASI_REACTOR "Build WASI reactor (exports library functions, no _start)" OFF)
    if(QJS_WASI_REACTOR)
        add_executable(qjs_wasi "${QJS_UPSTREAM_DIR}/quickjs-libc.c"
                                "${QJS_UPSTREAM_DIR}/qjs-wasi-reactor.c")
        target_include_directories(qjs_wasi PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                    "${QJS_UPSTREAM_DIR}")
        qjs_apply_declared_backports(qjs_wasi)
        set_target_properties(qjs_wasi PROPERTIES OUTPUT_NAME "qjs" SUFFIX ".wasm")
        target_compile_definitions(qjs PRIVATE BUILDING_QJS_SHARED)
        target_compile_definitions(qjs_wasi PRIVATE ${qjs_defines} BUILDING_QJS_SHARED)
        target_link_libraries(qjs_wasi qjs)
        target_link_options(
            qjs_wasi
            PRIVATE
            -mexec-model=reactor
            # Export all symbols with default visibility (JS_EXTERN functions)
            -Wl,--export-dynamic
            # Memory management (libc symbols need explicit export)
            -Wl,--export=malloc
            -Wl,--export=free
            -Wl,--export=realloc
            -Wl,--export=calloc)
    endif()
endif()

if(QJS_BUILD_CLI)
    if(QJS_BUILD_CLI_WITH_MIMALLOC OR QJS_BUILD_CLI_WITH_STATIC_MIMALLOC)
        find_package(mimalloc REQUIRED)
        target_compile_definitions(qjs_exe PRIVATE QJS_USE_MIMALLOC)
        # Upstream mimalloc doesn't provide a way to know if both libraries are supported.
        if(QJS_BUILD_CLI_WITH_STATIC_MIMALLOC)
            target_link_libraries(qjs_exe PRIVATE mimalloc-static)
        else()
            target_link_libraries(qjs_exe PRIVATE mimalloc)
        endif()
    endif()

    # Test262 runner
    #

    if(NOT EMSCRIPTEN)
        add_executable(run-test262 "${QJS_UPSTREAM_DIR}/run-test262.c")
        add_qjs_libc_if_needed(run-test262)
        target_compile_definitions(run-test262 PRIVATE ${qjs_defines})
        target_link_libraries(run-test262 PRIVATE qjs)
    endif()

    # Interrupt test
    #

    add_executable(api-test "${QJS_UPSTREAM_DIR}/api-test.c")
    target_compile_definitions(api-test PRIVATE ${qjs_defines})
    target_link_libraries(api-test PRIVATE qjs)
    add_qjs_libc_if_needed(api-test)

    add_executable(lre-test "${QJS_UPSTREAM_DIR}/lre-test.c" "${QJS_UPSTREAM_DIR}/libregexp.c"
                            "${QJS_UPSTREAM_DIR}/libunicode.c")
    target_include_directories(lre-test PRIVATE "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(lre-test PRIVATE ${qjs_defines})

    # Unicode generator
    #

    # Note: do not link libunicode.c here, it needs the generated libunicode-table.h,
    # which would make it impossible to regenerate the table from scratch.
    add_executable(unicode_gen EXCLUDE_FROM_ALL "${QJS_UPSTREAM_DIR}/unicode_gen.c")
    target_include_directories(unicode_gen PRIVATE "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(unicode_gen PRIVATE ${qjs_defines})

    add_executable(function_source "${QJS_UPSTREAM_DIR}/gen/function_source.c")
    add_qjs_libc_if_needed(function_source)
    target_include_directories(function_source PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                       "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(function_source PRIVATE ${qjs_defines})
    target_link_libraries(function_source PRIVATE qjs)
endif()

# Examples
#

if(QJS_BUILD_EXAMPLES)
    if(WIN32 AND NOT (QJS_LIB_TYPE STREQUAL "SHARED_LIBRARY"))
        message(
            AUTHOR_WARNING
                "Binary modules used with static qjs on Windows. There might be\n"
                "runtime errors when the module is used due to two copies of qjs\n" "in memory.\n"
                "Please use \"-DBUILD_SHARED_LIBS=true\" if possible.")
    endif()

    add_executable(hello "${QJS_UPSTREAM_DIR}/gen/hello.c")
    add_qjs_libc_if_needed(hello)
    target_include_directories(hello PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(hello PRIVATE ${qjs_defines})
    target_link_libraries(hello PRIVATE qjs)

    add_executable(hello_module "${QJS_UPSTREAM_DIR}/gen/hello_module.c")
    add_qjs_libc_if_needed(hello_module)
    target_include_directories(hello_module PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                    "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(hello_module PRIVATE ${qjs_defines})
    target_link_libraries(hello_module PRIVATE qjs)

    add_library(fib MODULE "${QJS_UPSTREAM_DIR}/examples/fib.c")
    set_target_properties(fib PROPERTIES PREFIX "")
    target_link_libraries(fib PRIVATE qjs_module_lib)
    if(APPLE)
        target_link_options(fib PRIVATE -undefined dynamic_lookup)
    endif()

    add_library(point MODULE "${QJS_UPSTREAM_DIR}/examples/point.c")
    set_target_properties(point PROPERTIES PREFIX "")
    target_link_libraries(point PRIVATE qjs_module_lib)
    if(APPLE)
        target_link_options(point PRIVATE -undefined dynamic_lookup)
    endif()

    add_executable(test_fib "${QJS_UPSTREAM_DIR}/gen/test_fib.c")
    add_qjs_libc_if_needed(test_fib)
    target_include_directories(test_fib PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}")
    target_compile_definitions(test_fib PRIVATE ${qjs_defines})
    target_link_libraries(test_fib PRIVATE qjs)
    # Loads fib.so which depends on symbols from libqjs.
    set_target_properties(test_fib PROPERTIES ENABLE_EXPORTS TRUE)
endif()

# Install target
#

if(QJS_ENABLE_INSTALL)
    file(STRINGS "${QJS_UPSTREAM_DIR}/quickjs.h" quickjs_h REGEX QJS_VERSION)
    string(REGEX MATCH "QJS_VERSION_MAJOR ([0-9]*)" _ "${quickjs_h}")
    set(QJS_VERSION_MAJOR ${CMAKE_MATCH_1})
    string(REGEX MATCH "QJS_VERSION_MINOR ([0-9]*)" _ "${quickjs_h}")
    set(QJS_VERSION_MINOR ${CMAKE_MATCH_1})
    string(REGEX MATCH "QJS_VERSION_PATCH ([0-9]*)" _ "${quickjs_h}")
    set(QJS_VERSION_PATCH ${CMAKE_MATCH_1})
    set_target_properties(
        qjs PROPERTIES VERSION ${QJS_VERSION_MAJOR}.${QJS_VERSION_MINOR}.${QJS_VERSION_PATCH}
                       SOVERSION ${QJS_VERSION_MAJOR})
    install(FILES "${QJS_UPSTREAM_DIR}/quickjs.h" "${CMAKE_CURRENT_SOURCE_DIR}/quickjs-turbo.h"
            DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
    if(QJS_BUILD_LIBC)
        install(FILES "${QJS_UPSTREAM_DIR}/quickjs-libc.h" DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
    endif()
    if(QJS_BUILD_CLI
       AND NOT IOS
       AND NOT TVOS
       AND NOT WATCHOS)
        install(TARGETS qjs_exe RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
        install(TARGETS qjsc RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
    endif()
    install(
        TARGETS qjs
        EXPORT qjsConfig
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
    install(EXPORT qjsConfig DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/qjs)
    install(
        TARGETS qjs
        EXPORT quickjs-turboConfig
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
    install(
        EXPORT quickjs-turboConfig
        NAMESPACE quickjs-turbo::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/quickjs-turbo)
    install(FILES "${QJS_UPSTREAM_DIR}/LICENSE" DESTINATION ${CMAKE_INSTALL_DOCDIR})
    install(DIRECTORY "${QJS_UPSTREAM_DIR}/examples" DESTINATION ${CMAKE_INSTALL_DOCDIR})
endif()

option(QJS_FRAME_BUILD_TESTS "Build and register frame integration tests" OFF)
if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
    include(cmake/x86/linux/Install.cmake)
elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
    include(cmake/x86/macos/Install.cmake)
endif()
if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64")
    include(cmake/arm64/Install.cmake)
endif()
if(QJS_FRAME_BUILD_TESTS)
    if(NOT QJS_BUILD_CLI)
        message(FATAL_ERROR "QJS_FRAME_BUILD_TESTS requires QJS_BUILD_CLI=ON")
    endif()
    include(cmake/common/InterpreterTests.cmake)
    if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64")
        include(cmake/arm64/InterpreterTests.cmake)
    elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
        include(cmake/x86/linux/InterpreterTests.cmake)
    elseif(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
        include(cmake/x86/macos/InterpreterTests.cmake)
    endif()
endif()

if(QJS_ENABLE_INSTALL
   AND CMAKE_SYSTEM_NAME STREQUAL "Linux"
   AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
endif()

option(QJS_AARCH64_BUILD_ABI_CHECKS
       "Build standalone Linux AArch64 ABI foundation checks (not a native VM)" OFF)
if(QJS_AARCH64_BUILD_ABI_CHECKS)
    include(cmake/arm64/ABI.cmake)
endif()
