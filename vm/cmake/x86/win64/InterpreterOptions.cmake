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

# Evaluate source-level WIN_X86_64 native ASM VM availability (MSVC / clang-cl,
# zero GNU binutils required, supports add_subdirectory() and local LTO isolation).
function(qjs_win_x86_64_reason out_reason)
    set(reason "")
    string(
        TOLOWER
            "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_DEBUG} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO} ${CMAKE_C_FLAGS_MINSIZEREL} ${CMAKE_EXE_LINKER_FLAGS}"
            all_flags)
    if(NOT WIN32
       OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8
       OR NOT QJS_FRAME_COMPILER_X64)
        set(reason "WIN_X86_64 requires a Windows x86-64 compiler")
    elseif(
        NOT (CMAKE_C_COMPILER_ID STREQUAL "MSVC"
             OR (CMAKE_C_COMPILER_ID STREQUAL "Clang" AND MSVC)
             OR (MINGW AND CMAKE_C_COMPILER_ID MATCHES "^(GNU|Clang)$")))
        set(reason "WIN_X86_64 supports MSVC (cl.exe), clang-cl, or MinGW (gcc/clang)")
    elseif(BUILD_SHARED_LIBS)
        set(reason "WIN_X86_64 shared library builds fall back to portable C")
    elseif(QJS_DISABLE_PARSER)
        set(reason "WIN_X86_64 requires parser enabled")
    elseif(NOT QJS_BACKPORT_CONTEXT_OOM)
        set(reason "WIN_X86_64 requires the source-bound core overlay")
    elseif(
        QJS_ENABLE_ASAN
        OR QJS_ENABLE_MSAN
        OR QJS_ENABLE_TSAN
        OR QJS_ENABLE_UBSAN
        OR QJS_ENABLE_GC_STRESS
        OR all_flags MATCHES "[-/]fsanitize")
        set(reason "WIN_X86_64 instrumented/sanitizer builds fall back to portable C")
    elseif(CMAKE_VERSION VERSION_LESS 3.20)
        set(reason "WIN_X86_64 requires CMake 3.20 or newer")
    else()
        if(CMAKE_C_COMPILER_ID STREQUAL "MSVC")
            get_filename_component(compiler_dir "${CMAKE_C_COMPILER}" DIRECTORY)
            find_program(
                QJS_FRAME_MASM
                NAMES ml64
                HINTS "${compiler_dir}")
            if(NOT QJS_FRAME_MASM OR NOT EXISTS "${QJS_FRAME_MASM}")
                set(reason "WIN_X86_64 MSVC builds require ml64.exe")
            endif()
        endif()
        if(NOT reason)
            if(QJS_USE_PREGEN_ASM)
                if(NOT EXISTS "${QJS_PREGEN_DIR}/win_x86_64/PREGEN-MANIFEST.json")
                    set(reason
                        "QJS_USE_PREGEN_ASM=ON requires ${QJS_PREGEN_DIR}/win_x86_64/PREGEN-MANIFEST.json"
                    )
                endif()
            else()
                find_package(Python3 3.10 QUIET COMPONENTS Interpreter)
                if(NOT Python3_Interpreter_FOUND)
                    set(reason "WIN_X86_64 native generation requires Python 3.10 or newer")
                endif()
            endif()
        endif()
    endif()
    set(${out_reason}
        "${reason}"
        PARENT_SCOPE)
endfunction()

if(frame_requested STREQUAL "WIN_X86_64")
    qjs_win_x86_64_reason(frame_unavailable)
    set(QJS_ENABLE_INTERP_FRAME OFF)
    set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
    if(frame_unavailable)
        message(
            FATAL_ERROR
                "QJS_FRAME_BACKEND=WIN_X86_64: ${frame_unavailable}. Use PORTABLE or AUTO for C fallback."
        )
    endif()
    set(QJS_ENABLE_INTERP_FRAME ON)
    set(QJS_FRAME_BACKEND_EFFECTIVE WIN_X86_64)
    set(QJS_INTERP_FRAME_REGISTER_ABI ON)
    set(QJS_INTERP_FRAME_INTERNAL_ENTRY ON)
    foreach(opt DIAGNOSTICS TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL GLOBAL_BINDING LEAF_ENTRY)
        set(QJS_INTERP_FRAME_${opt} OFF)
    endforeach()
    set(QJS_BACKPORT_PORTABLE_REGEXP_REQUIRED ON)
    return()
endif()

if(frame_requested STREQUAL "AUTO")
    qjs_win_x86_64_reason(frame_unavailable)
    if(NOT frame_unavailable)
        set(QJS_ENABLE_INTERP_FRAME ON)
        set(QJS_FRAME_BACKEND_EFFECTIVE WIN_X86_64)
        set(QJS_INTERP_FRAME_REGISTER_ABI ON)
        set(QJS_INTERP_FRAME_INTERNAL_ENTRY ON)
        foreach(opt DIAGNOSTICS TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL GLOBAL_BINDING LEAF_ENTRY)
            set(QJS_INTERP_FRAME_${opt} OFF)
        endforeach()
        set(QJS_BACKPORT_PORTABLE_REGEXP_REQUIRED ON)
        return()
    endif()
    set(QJS_ENABLE_INTERP_FRAME OFF)
    set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
    message(STATUS "QuickJS frame AUTO fallback: ${frame_unavailable}")
    return()
endif()

set(QJS_ENABLE_INTERP_FRAME OFF)
set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
option(QJS_INTERP_FRAME_DIAGNOSTICS "Record frame path counters" OFF)
option(QJS_INTERP_FRAME_REGISTER_ABI "Win64 register dispatch (native backend requires ON)" ON)
option(QJS_INTERP_FRAME_INTERNAL_ENTRY "Internal frame entry (native backend requires ON)" ON)
option(QJS_INTERP_FRAME_TAIL_ENTRY "Win64 tail dispatcher" OFF)
option(QJS_INTERP_FRAME_INLINE_WINDOW "Inline spare-window check" ON)
option(QJS_INTERP_FRAME_ITERATOR_LITERAL "Activation-owned synchronous iterator literals" OFF)
option(QJS_INTERP_FRAME_GLOBAL_BINDING "Live global and lexical binding hints" OFF)
option(QJS_INTERP_FRAME_LEAF_ENTRY "Function-owned primitive leaf entries" ON)
