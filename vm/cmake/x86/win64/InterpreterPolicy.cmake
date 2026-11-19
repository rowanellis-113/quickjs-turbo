# Pure policy function: no tool execution, assembler enablement or global flags.
# The caller obtains QJS_FRAME_COMPILER_X64 from a compiler macro probe.
function(qjs_frame_platform_reason result)
    set(reason "")
    if(NOT WIN32
       OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8
       OR NOT QJS_FRAME_COMPILER_X64)
        set(reason "requires a Windows x86-64 compiler (64-bit pointers alone are insufficient)")
    elseif(NOT CMAKE_GENERATOR STREQUAL "Ninja")
        set(reason "requires the single-configuration Ninja generator")
    elseif(NOT CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
        set(reason "native adapters currently require a standalone source build")
    elseif(BUILD_SHARED_LIBS)
        set(reason "shared libraries use the portable C interpreter")
    elseif(NOT (CMAKE_C_COMPILER_ID STREQUAL "MSVC" OR (MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU"
                                                       )))
        set(reason "supports MSVC cl or MinGW GCC; clang-cl is not qualified")
    elseif(NOT CMAKE_BUILD_TYPE MATCHES "^(Release|RelWithDebInfo)$")
        set(reason "native object adapters require Release or RelWithDebInfo")
    elseif(
        QJS_ENABLE_ASAN
        OR QJS_ENABLE_MSAN
        OR QJS_ENABLE_TSAN
        OR QJS_ENABLE_UBSAN
        OR QJS_ENABLE_GC_STRESS)
        set(reason "instrumented and GC-stress builds use the portable C interpreter")
    elseif(QJS_DISABLE_PARSER)
        set(reason "parser-disabled builds use the portable C interpreter")
    elseif(CMAKE_C_COMPILER_LAUNCHER)
        set(reason "native adapters require direct compiler commands, without a compiler launcher")
    elseif(
        CMAKE_INTERPROCEDURAL_OPTIMIZATION
        OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE
        OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO)
        set(reason "native COFF adapters require ordinary objects, without LTO")
    else()
        string(TOLOWER "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO}"
                       frame_flags)
        if(frame_flags MATCHES "(^|[ ;])[-/]gl([ ;]|$)" OR frame_flags MATCHES
                                                           "-flto|[-/]fsanitize")
            set(reason "instrumentation or LTO compiler flags require the portable C interpreter")
        endif()
    endif()
    set(${result}
        "${reason}"
        PARENT_SCOPE)
endfunction()
