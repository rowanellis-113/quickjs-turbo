# macOS x86-64 (Darwin/Mach-O) SysV backend. The source-derived ABI is measured
# at build time from Apple Clang / Clang; Windows compiler clones and COFF
# profiles are never admitted here. Host LTO/IPO is isolated locally via -fno-lto.
set(frame_unavailable "")
set(_qjs_macos_all_flags
    "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_DEBUG} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO} ${CMAKE_C_FLAGS_MINSIZEREL} ${CMAKE_EXE_LINKER_FLAGS}"
)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Darwin" OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(frame_unavailable "macOS x86-64 native backend requires a macOS LP64 x86-64 target")
elseif(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    set(frame_unavailable "macOS x86-64 native backend requires AppleClang or Clang")
elseif((NOT QJS_USE_PREGEN_ASM AND NOT CMAKE_GENERATOR STREQUAL "Ninja") OR CMAKE_VERSION
                                                                            VERSION_LESS 3.20)
    set(frame_unavailable "macOS x86-64 native backend requires CMake 3.20 and Ninja")
elseif(
    BUILD_SHARED_LIBS
    OR QJS_BUILD_CLI_STATIC
    OR QJS_ENABLE_ASAN
    OR QJS_ENABLE_MSAN
    OR QJS_ENABLE_TSAN
    OR QJS_ENABLE_UBSAN)
    set(frame_unavailable
        "macOS shared-library, fully static CLI and sanitizer native profiles are not qualified yet"
    )
elseif(QJS_INTERP_FRAME_DIAGNOSTICS)
    set(frame_unavailable "macOS native diagnostic record profile is not implemented yet")
elseif(NOT QJS_BACKPORT_CONTEXT_OOM)
    set(frame_unavailable "macOS native backend requires the source-bound core overlay")
elseif(_qjs_macos_all_flags MATCHES "-mabi=|-mx32|-m32|-fpack-struct|-fshort-enums|-fsanitize")
    set(frame_unavailable
        "macOS native backend does not admit ABI-altering or sanitizer/fuzz flags")
endif()
foreach(required REGISTER_ABI INTERNAL_ENTRY)
    if(DEFINED QJS_INTERP_FRAME_${required} AND NOT QJS_INTERP_FRAME_${required})
        set(frame_unavailable
            "macOS native backend requires register ABI and internal entry; select PORTABLE to disable them"
        )
    endif()
endforeach()
option(QJS_INTERP_FRAME_GLOBAL_BINDING "Live global and lexical binding hints" ON)
foreach(unsupported TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    if(QJS_INTERP_FRAME_${unsupported})
        set(frame_unavailable
            "Win64-specific entry switches are not macOS configuration options. Use the integrated macOS profile and its component controls"
        )
    endif()
endforeach()
if(NOT frame_unavailable)
    include(CheckCSourceCompiles)
    unset(QJS_MACOS_NATIVE_TARGET CACHE)
    check_c_source_compiles(
        "#if !defined(__APPLE__) || !defined(__x86_64__) || !defined(__LP64__) || defined(_WIN32) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__\n#error macOS LP64 little-endian x86-64 required\n#endif\n_Static_assert(sizeof(long)==8 && sizeof(void*)==8,\"LP64\");\nint main(void){return 0;}"
        QJS_MACOS_NATIVE_TARGET)
    if(NOT QJS_MACOS_NATIVE_TARGET)
        set(frame_unavailable "Compiler target failed the macOS x86-64 LP64 capability probe")
    endif()
    if(QJS_USE_PREGEN_ASM)
        if(NOT EXISTS "${QJS_PREGEN_DIR}/macos_x86_64/PREGEN-MANIFEST.json")
            set(frame_unavailable
                "QJS_USE_PREGEN_ASM=ON requires ${QJS_PREGEN_DIR}/macos_x86_64/PREGEN-MANIFEST.json"
            )
        endif()
    else()
        find_package(Python3 3.9 QUIET COMPONENTS Interpreter)
        if(NOT Python3_Interpreter_FOUND)
            set(frame_unavailable "macOS native generation requires Python 3.9 or newer")
        endif()
        find_program(QJS_MACOS_OTOOL NAMES otool)
        find_program(QJS_MACOS_DWARFDUMP NAMES dwarfdump)
        if(NOT QJS_MACOS_OTOOL OR NOT EXISTS "${QJS_MACOS_OTOOL}")
            set(frame_unavailable
                "macOS native validation requires otool (Xcode Command Line Tools)")
        elseif(NOT QJS_MACOS_DWARFDUMP OR NOT EXISTS "${QJS_MACOS_DWARFDUMP}")
            set(frame_unavailable
                "macOS native validation requires dwarfdump (Xcode Command Line Tools)")
        endif()
    endif()
endif()
set(QJS_ENABLE_INTERP_FRAME OFF)
set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
if(frame_unavailable)
    if(frame_requested STREQUAL "MACOS_X86_64")
        message(
            FATAL_ERROR
                "QJS_FRAME_BACKEND=MACOS_X86_64: ${frame_unavailable}. Use PORTABLE or AUTO for fallback."
        )
    endif()
    message(STATUS "QuickJS frame AUTO fallback: ${frame_unavailable}")
else()
    set(QJS_ENABLE_INTERP_FRAME ON)
    set(QJS_FRAME_BACKEND_EFFECTIVE MACOS_X86_64)
    set(CMAKE_EXPORT_COMPILE_COMMANDS
        ON
        CACHE BOOL "" FORCE)
endif()
foreach(option DIAGNOSTICS TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    set(QJS_INTERP_FRAME_${option} OFF)
endforeach()
if(NOT QJS_ENABLE_INTERP_FRAME)
    set(QJS_INTERP_FRAME_GLOBAL_BINDING OFF)
endif()
set(QJS_INTERP_FRAME_REGISTER_ABI ${QJS_ENABLE_INTERP_FRAME})
set(QJS_INTERP_FRAME_INTERNAL_ENTRY ${QJS_ENABLE_INTERP_FRAME})
message(
    STATUS "QuickJS frame backend: ${QJS_FRAME_BACKEND_EFFECTIVE} (requested ${frame_requested})")
file(
    WRITE "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
    "{\"schema\":1,\"requested\":\"${frame_requested}\",\"effective\":\"${QJS_FRAME_BACKEND_EFFECTIVE}\",\"fallback_reason\":\"${frame_unavailable}\"}\n"
)

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
    set(QJS_BACKPORT_PORTABLE_REGEXP_REQUIRED ON)
    set(QJS_FRAME_STRING_POOL_NATIVE ON)
endif()
