# Linux AArch64 (glibc and musl) native backend options.
# AUTO falls back safely to PORTABLE on unsupported toolchains or sanitizers;
# explicit LINUX_AARCH64 fails fast.
set(frame_unavailable "")
set(_qjs_arm64_all_flags
    "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_DEBUG} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO} ${CMAKE_C_FLAGS_MINSIZEREL} ${CMAKE_EXE_LINKER_FLAGS}"
)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux"
   OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8
   OR NOT CMAKE_C_COMPILER_ID STREQUAL "GNU"
   OR CMAKE_C_COMPILER_VERSION VERSION_LESS 13
   OR (NOT QJS_USE_PREGEN_ASM AND NOT CMAKE_GENERATOR STREQUAL "Ninja")
   OR CMAKE_VERSION VERSION_LESS 3.20)
    set(frame_unavailable "LINUX_AARCH64 requires Linux LP64, GCC 13+, CMake 3.20+ and Ninja")
elseif(
    BUILD_SHARED_LIBS
    OR QJS_BUILD_CLI_STATIC
    OR QJS_ENABLE_ASAN
    OR QJS_ENABLE_MSAN
    OR QJS_ENABLE_TSAN
    OR QJS_ENABLE_UBSAN
    OR QJS_INTERP_FRAME_DIAGNOSTICS
    OR NOT QJS_BACKPORT_CONTEXT_OOM)
    set(frame_unavailable
        "LINUX_AARCH64 currently requires static qjs, source overlays, no sanitizers or old VM diagnostics"
    )
elseif(_qjs_arm64_all_flags MATCHES "-mabi=|-fpack-struct|-fshort-enums|-fsanitize")
    set(frame_unavailable "LINUX_AARCH64 does not admit ABI-altering or sanitizer/fuzz flags")
elseif(
    _qjs_arm64_all_flags
    MATCHES
    "-Ofast|-ffast-math|-ffinite-math-only|-funsafe-math-optimizations|-fno-signed-zeros|-freciprocal-math|-fassociative-math|-fno-trapping-math|-fsingle-precision-constant"
)
    set(frame_unavailable
        "LINUX_AARCH64 requires IEEE double arithmetic, signed zero and NaN semantics; unsafe floating-point flags are not qualified"
    )
endif()
foreach(required REGISTER_ABI INTERNAL_ENTRY)
    if(DEFINED QJS_INTERP_FRAME_${required} AND NOT QJS_INTERP_FRAME_${required})
        set(frame_unavailable
            "LINUX_AARCH64 requires register ABI and internal entry; select PORTABLE to disable them"
        )
    endif()
endforeach()
foreach(unsupported TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    if(QJS_INTERP_FRAME_${unsupported})
        set(frame_unavailable
            "LINUX_AARCH64 has not implemented ${unsupported}; omit this option for the experimental tier"
        )
    endif()
endforeach()
if(NOT frame_unavailable)
    include(CheckCSourceCompiles)
    unset(QJS_AARCH64_VM_TARGET CACHE)
    check_c_source_compiles(
        "#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__\n#error Linux AArch64 LE LP64 required\n#endif\n#if defined(__ARM_FEATURE_BTI_DEFAULT) || defined(__ARM_FEATURE_PAC_DEFAULT)\n#error BTI/PAC not qualified\n#endif\nint main(void){return 0;}"
        QJS_AARCH64_VM_TARGET)
    if(NOT QJS_AARCH64_VM_TARGET)
        set(frame_unavailable
            "LINUX_AARCH64 requires an actual AArch64 LE LP64 compiler without BTI/PAC")
    endif()
    if(NOT QJS_USE_PREGEN_ASM)
        find_package(Python3 3.10 QUIET COMPONENTS Interpreter)
        if(NOT Python3_Interpreter_FOUND)
            set(frame_unavailable "LINUX_AARCH64 native generation requires Python 3.10 or newer")
        endif()
    elseif(NOT EXISTS "${QJS_PREGEN_DIR}/linux_aarch64/PREGEN-MANIFEST.json")
        set(frame_unavailable
            "QJS_USE_PREGEN_ASM=ON requires ${QJS_PREGEN_DIR}/linux_aarch64/PREGEN-MANIFEST.json")
    endif()
endif()
set(QJS_ENABLE_INTERP_FRAME OFF)
set(QJS_FRAME_BACKEND_EFFECTIVE PORTABLE)
if(frame_unavailable)
    if(frame_requested STREQUAL "LINUX_AARCH64")
        message(
            FATAL_ERROR
                "QJS_FRAME_BACKEND=LINUX_AARCH64: ${frame_unavailable}. Use PORTABLE or AUTO for fallback."
        )
    endif()
    message(STATUS "QuickJS frame AUTO fallback: ${frame_unavailable}")
else()
    set(CMAKE_EXPORT_COMPILE_COMMANDS
        ON
        CACHE BOOL "" FORCE)
    set(QJS_ENABLE_INTERP_FRAME ON)
    set(QJS_FRAME_BACKEND_EFFECTIVE LINUX_AARCH64)
endif()
set(QJS_INTERP_FRAME_REGISTER_ABI ${QJS_ENABLE_INTERP_FRAME})
set(QJS_INTERP_FRAME_INTERNAL_ENTRY ${QJS_ENABLE_INTERP_FRAME})
foreach(feature TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    set(QJS_INTERP_FRAME_${feature} OFF)
endforeach()
option(QJS_INTERP_FRAME_GLOBAL_BINDING
       "Native global cells,activation hints and resolved Symbol continuations" ON)
if(NOT QJS_ENABLE_INTERP_FRAME)
    set(QJS_INTERP_FRAME_GLOBAL_BINDING OFF)
endif()
option(QJS_INTERP_FRAME_COMPARISONS "Complete native loose/strict and C identity comparison family"
       ON)
option(QJS_INTERP_FRAME_CONSTRUCT_CONTINUATION
       "Ordinary same-activation construction and complete cleanup" ON)
option(QJS_INTERP_FRAME_ITERATORS "Complete synchronous iterator/checkpoint and dense-array family"
       ON)
option(QJS_INTERP_FRAME_CALL_FORWARD "Logical Function.call forwarding family (experimental)" ON)
option(QJS_INTERP_FRAME_ARRAY_OWN "Native ordinary numeric-array own-data leaf" ON)
option(QJS_AARCH64_VM_INSTRUMENT
       "Instrument completed ARM64 VM activations for functional path proof" OFF)
message(
    STATUS "QuickJS frame backend: ${QJS_FRAME_BACKEND_EFFECTIVE} (requested ${frame_requested})")
file(
    WRITE "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
    "{\"schema\":1,\"requested\":\"${frame_requested}\",\"effective\":\"${QJS_FRAME_BACKEND_EFFECTIVE}\",\"fallback_reason\":\"${frame_unavailable}\",\"qualification\":\"build receipt only; source-bound acceptance in docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt\"}\n"
)

option(QJS_INTERP_FRAME_ARRAY_SORT
       "Complete array copy and default/cached/prepared sort C owners (experimental)" ON)

option(QJS_INTERP_FRAME_NATIVE_NULL_PROTO
       "Complete native null-prototype admission and warm allocation" ON)

option(QJS_INTERP_FRAME_ARGUMENTS "Shared argument root,child and object owners (experimental)" ON)
option(QJS_INTERP_FRAME_SCALAR_OPS
       "Source-owned base scalar,stack,atom and predicate opcodes (experimental)" ON)
option(QJS_INTERP_FRAME_CALL_LEAVES
       "Source-owned frame-free root and child call leaves (experimental)" ON)
option(QJS_INTERP_FRAME_STACK_INSERT "Enable original GNU native insert3 on AArch64" ON)
option(QJS_INTERP_FRAME_STRING_WORKERS "Enable original GNU string worker owners on ARM64" ON)
option(QJS_INTERP_FRAME_NATIVE_NUMERIC "Native BigInt/local/decimal owners (experimental)" ON)
option(QJS_INTERP_FRAME_COMPILER_PROJECTION "Independent target FD projection (experimental)" ON)
option(QJS_INTERP_FRAME_LITERALS
       "Activation literal ownership and native scalar opcodes (experimental)" ON)
option(QJS_INTERP_FRAME_INDEXED "Native indexed/append/instanceof mechanisms (experimental)" ON)
option(QJS_INTERP_FRAME_VARARGS "Owned spread,fusion and intrinsic apply (experimental)" ON)

option(
    QJS_AARCH64_FAST_VM
    "Enable R89v10e fast VM paths (property IC, call leaves, constructors, numeric/branch, indexed/stack)"
    ON)
