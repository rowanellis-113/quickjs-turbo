# Explicit opt-in; qualification is bound to a source, toolchain and actual image.
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux"
   OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8
   OR NOT CMAKE_C_COMPILER_ID STREQUAL "GNU"
   OR CMAKE_C_COMPILER_VERSION VERSION_LESS 13
   OR NOT CMAKE_GENERATOR STREQUAL "Ninja"
   OR CMAKE_VERSION VERSION_LESS 3.20)
    message(FATAL_ERROR "LINUX_AARCH64 requires Linux LP64, GCC 13+, CMake 3.20+ and Ninja")
endif()
if(BUILD_SHARED_LIBS
   OR QJS_BUILD_CLI_STATIC
   OR QJS_ENABLE_ASAN
   OR QJS_ENABLE_MSAN
   OR QJS_ENABLE_TSAN
   OR QJS_ENABLE_UBSAN
   OR QJS_INTERP_FRAME_DIAGNOSTICS
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_DEBUG
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION_MINSIZEREL
   OR NOT QJS_BACKPORT_CONTEXT_OOM)
    message(
        FATAL_ERROR
            "LINUX_AARCH64 currently requires static qjs, source overlays, no LTO/sanitizers or old VM diagnostics"
    )
endif()
if("${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_DEBUG} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO} ${CMAKE_C_FLAGS_MINSIZEREL}"
   MATCHES
   "-mabi=|-fpack-struct|-fshort-enums|-flto|-fsanitize")
    message(FATAL_ERROR "LINUX_AARCH64 does not admit ABI-altering, LTO or sanitizer flags")
endif()
if("${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_DEBUG} ${CMAKE_C_FLAGS_RELEASE} ${CMAKE_C_FLAGS_RELWITHDEBINFO} ${CMAKE_C_FLAGS_MINSIZEREL}"
   MATCHES
   "-Ofast|-ffast-math|-ffinite-math-only|-funsafe-math-optimizations|-fno-signed-zeros|-freciprocal-math|-fassociative-math|-fno-trapping-math|-fsingle-precision-constant"
)
    message(
        FATAL_ERROR
            "LINUX_AARCH64 requires IEEE double arithmetic, signed zero and NaN semantics; unsafe floating-point flags are not qualified"
    )
endif()
foreach(required REGISTER_ABI INTERNAL_ENTRY)
    if(DEFINED QJS_INTERP_FRAME_${required} AND NOT QJS_INTERP_FRAME_${required})
        message(
            FATAL_ERROR
                "LINUX_AARCH64 requires register ABI and internal entry; select PORTABLE to disable them"
        )
    endif()
endforeach()
foreach(unsupported TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    if(QJS_INTERP_FRAME_${unsupported})
        message(
            FATAL_ERROR
                "LINUX_AARCH64 has not implemented ${unsupported}; omit this option for the experimental tier"
        )
    endif()
endforeach()
include(CheckCSourceCompiles)
unset(QJS_AARCH64_VM_TARGET CACHE)
check_c_source_compiles(
    "#include <features.h>\n#if !defined(__GLIBC__)\n#error First AArch64 backend requires glibc\n#endif\n#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__\n#error Linux AArch64 LE LP64 required\n#endif\n#if defined(__ARM_FEATURE_BTI_DEFAULT) || defined(__ARM_FEATURE_PAC_DEFAULT)\n#error BTI/PAC not qualified\n#endif\nint main(void){return 0;}"
    QJS_AARCH64_VM_TARGET)
if(NOT QJS_AARCH64_VM_TARGET)
    message(FATAL_ERROR "LINUX_AARCH64 requires an actual AArch64 LE LP64 compiler without BTI/PAC")
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(QJS_ENABLE_INTERP_FRAME ON)
set(QJS_FRAME_BACKEND_EFFECTIVE LINUX_AARCH64)
set(QJS_INTERP_FRAME_REGISTER_ABI ON)
set(QJS_INTERP_FRAME_INTERNAL_ENTRY ON)
foreach(feature TAIL_ENTRY INLINE_WINDOW ITERATOR_LITERAL LEAF_ENTRY)
    set(QJS_INTERP_FRAME_${feature} OFF)
endforeach()
option(QJS_INTERP_FRAME_GLOBAL_BINDING
       "Native global cells,activation hints and resolved Symbol continuations" ON)
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
    STATUS "QuickJS frame backend: LINUX_AARCH64 (source-bound qualification; see release report)")
file(
    WRITE "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
    "{\"schema\":1,\"requested\":\"LINUX_AARCH64\",\"effective\":\"LINUX_AARCH64\",\"qualification\":\"build receipt only; source-bound acceptance in docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt\"}\n"
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
