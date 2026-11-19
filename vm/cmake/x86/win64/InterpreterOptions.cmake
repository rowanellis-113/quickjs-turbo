set(QJS_FRAME_COMPILER_X64 FALSE)
if(NOT frame_requested STREQUAL "PORTABLE"
   AND WIN32
   AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    include(CheckCSourceCompiles)
    # Do not reuse an x86-64 result after the caller changes target flags.
    unset(QJS_FRAME_X64_PROBE CACHE)
    check_c_source_compiles(
        "#if defined(_M_ARM64) || defined(_M_ARM64EC) || defined(__aarch64__) || (!defined(_M_X64) && !defined(__x86_64__))\n#error x86_64 required\n#endif\nint main(void) { return 0; }"
        QJS_FRAME_X64_PROBE)
    set(QJS_FRAME_COMPILER_X64 "${QJS_FRAME_X64_PROBE}")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/InterpreterPolicy.cmake")
qjs_frame_platform_reason(frame_unavailable)
if(NOT frame_requested STREQUAL "PORTABLE" AND NOT frame_unavailable)
    if(CMAKE_VERSION VERSION_LESS 3.20)
        set(frame_unavailable "native backend requires CMake 3.20 or newer")
    else()
        find_package(Python3 3.10 QUIET COMPONENTS Interpreter)
        if(NOT Python3_Interpreter_FOUND)
            set(frame_unavailable "native backend requires Python 3.10 or newer")
        endif()
        if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
            get_filename_component(frame_compiler_dir "${CMAKE_C_COMPILER}" DIRECTORY)
            find_program(
                QJS_FRAME_MASM
                NAMES ml64
                HINTS "${frame_compiler_dir}")
            if(NOT QJS_FRAME_MASM OR NOT EXISTS "${QJS_FRAME_MASM}")
                set(frame_unavailable "native MSVC backend requires ml64")
            endif()
        endif()
        find_program(QJS_FRAME_OBJDUMP NAMES x86_64-w64-mingw32-objdump objdump)
        if(NOT QJS_FRAME_OBJDUMP)
            set(frame_unavailable "native adapters require GNU objdump; set QJS_FRAME_OBJDUMP")
        elseif(NOT EXISTS "${QJS_FRAME_OBJDUMP}")
            set(frame_unavailable "configured QJS_FRAME_OBJDUMP does not exist")
        else()
            execute_process(
                COMMAND "${QJS_FRAME_OBJDUMP}" --version
                RESULT_VARIABLE frame_objdump_result
                OUTPUT_VARIABLE frame_objdump_version
                ERROR_QUIET
                TIMEOUT 10)
            if(NOT frame_objdump_result EQUAL 0 OR NOT frame_objdump_version MATCHES "GNU objdump")
                set(frame_unavailable
                    "native adapters require GNU objdump, not llvm-objdump or an arbitrary decoder")
            endif()
        endif()
        get_filename_component(frame_binutils_directory "${QJS_FRAME_OBJDUMP}" DIRECTORY)
        find_program(
            QJS_FRAME_AS
            NAMES x86_64-w64-mingw32-as as
            HINTS "${frame_binutils_directory}")
        if(NOT QJS_FRAME_AS OR NOT EXISTS "${QJS_FRAME_AS}")
            set(frame_unavailable "native source bundle requires GNU COFF as; set QJS_FRAME_AS")
        else()
            execute_process(
                COMMAND "${QJS_FRAME_AS}" --version
                RESULT_VARIABLE frame_as_result
                OUTPUT_VARIABLE frame_as_version
                ERROR_QUIET
                TIMEOUT 10)
            if(NOT frame_as_result EQUAL 0
               OR NOT frame_as_version MATCHES "GNU assembler"
               OR NOT frame_as_version MATCHES "x86_64[^\n]*(mingw|windows|pe)")
                set(frame_unavailable
                    "native source bundle requires a GNU assembler targeting Windows x86-64 COFF")
            endif()
        endif()
    endif()
endif()

set(QJS_ENABLE_INTERP_FRAME OFF)
set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
if(NOT frame_requested STREQUAL "PORTABLE")
    if(frame_unavailable)
        if(frame_requested STREQUAL "WIN64")
            message(
                FATAL_ERROR
                    "QJS_FRAME_BACKEND=WIN64: ${frame_unavailable}. Use PORTABLE or AUTO for C fallback."
            )
        endif()
        message(STATUS "QuickJS frame AUTO fallback: ${frame_unavailable}")
    else()
        set(QJS_ENABLE_INTERP_FRAME ON)
        set(QJS_FRAME_BACKEND_EFFECTIVE WIN64)
    endif()
endif()

option(QJS_INTERP_FRAME_DIAGNOSTICS "Record frame path counters" OFF)
option(QJS_INTERP_FRAME_REGISTER_ABI "Win64 register dispatch (native backend requires ON)" ON)
option(QJS_INTERP_FRAME_INTERNAL_ENTRY "Internal frame entry (native backend requires ON)" ON)
set(qjs_frame_tail_default OFF)
set(qjs_frame_window_default ON)
if(MINGW)
    set(qjs_frame_tail_default ON)
    set(qjs_frame_window_default OFF)
endif()
option(QJS_INTERP_FRAME_TAIL_ENTRY "Win64 tail dispatcher" ${qjs_frame_tail_default})
option(QJS_INTERP_FRAME_INLINE_WINDOW "Inline spare-window check" ${qjs_frame_window_default})
set(qjs_frame_literal_default OFF)
set(qjs_frame_leaf_masm_default OFF)
if(MINGW)
    set(qjs_frame_literal_default ON)
endif()
if(QJS_ENABLE_INTERP_FRAME)
    # A supported compiler/platform cannot make another upstream ABI safe.
    # Check before generating assembly or adapting compiler output.
    file(READ "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/backend.json" frame_bundle_manifest)
    string(REGEX MATCH "\"upstream\"[ \t\r\n]*:[ \t\r\n]*\"([0-9a-f]+)\"" frame_bundle_match
                 "${frame_bundle_manifest}")
    set(frame_bundle_upstream "${CMAKE_MATCH_1}")
    if(NOT frame_bundle_upstream STREQUAL QJS_UPSTREAM_REVISION)
        message(
            FATAL_ERROR
                "WIN64 native bundle requires an ABI port: adapter upstream ${frame_bundle_upstream}, selected upstream ${QJS_UPSTREAM_REVISION}. PORTABLE builds the selected C engine; it does not validate these optimizations."
        )
    endif()
    include("${CMAKE_CURRENT_LIST_DIR}/InterpreterABI.cmake")
    qjs_frame_verify_abi("${CMAKE_CURRENT_SOURCE_DIR}")
    if(NOT QJS_INTERP_FRAME_REGISTER_ABI OR NOT QJS_INTERP_FRAME_INTERNAL_ENTRY)
        message(
            FATAL_ERROR
                "The integrated WIN64 backend requires register ABI and internal entry; select PORTABLE to disable it"
        )
    endif()
    if(MINGW)
        set(qjs_frame_literal_default ON)
    else()
        set(qjs_frame_leaf_masm_default ON)
    endif()
endif()
set(qjs_frame_binding_default "${qjs_frame_literal_default}")
set(qjs_frame_leaf_default ON)
option(QJS_INTERP_FRAME_ITERATOR_LITERAL "Activation-owned synchronous iterator literals"
       ${qjs_frame_literal_default})
option(QJS_INTERP_FRAME_GLOBAL_BINDING "Live global and lexical binding hints"
       ${qjs_frame_binding_default})
option(QJS_INTERP_FRAME_LEAF_ENTRY "Function-owned primitive leaf entries"
       ${qjs_frame_leaf_default})
if(QJS_ENABLE_INTERP_FRAME)
    if((QJS_INTERP_FRAME_ITERATOR_LITERAL OR QJS_INTERP_FRAME_GLOBAL_BINDING) AND NOT MINGW)
        message(FATAL_ERROR "Iterator literal and global binding backends require MinGW GCC")
    endif()
    if(NOT QJS_INTERP_FRAME_LEAF_ENTRY)
        message(
            FATAL_ERROR
                "The integrated WIN64 backend requires leaf entries; select PORTABLE to disable it")
    endif()
    if(MINGW AND NOT QJS_INTERP_FRAME_GLOBAL_BINDING)
        message(
            FATAL_ERROR
                "MinGW leaf entries require global binding support; select PORTABLE to disable the backend"
        )
    endif()
    set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
    set(frame_null_objdump "${QJS_FRAME_OBJDUMP}")
    set(frame_internal_assembler "${QJS_FRAME_MASM}")
    set(frame_register_assembler "${QJS_FRAME_MASM}")
    set(frame_masm "${QJS_FRAME_MASM}")
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    set(QJS_BACKPORT_NATIVE_MODULES ON)
    set(QJS_FRAME_STRING_POOL_NATIVE ON)
    if(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        set(QJS_BACKPORT_NARROW_VALUE_READERS ON)
    endif()
endif()
