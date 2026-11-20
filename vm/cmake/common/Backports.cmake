# Explicit source overlays for the pinned upstream. Never edit checked-in core
# inputs or weaken their hash checks. Receipts accompany the compiler input.
option(QJS_BACKPORT_CONTEXT_OOM "Apply declared upstream context-construction OOM cleanup fix" ON)
option(QJS_FRAME_EXPERIMENTAL_ALLOCATOR "Build same-image allocator ablations (runtime opt-in)" OFF)
set(QJS_DEFAULT_EXPERIMENT_ALLOCATOR
    ""
    CACHE
        STRING
        "Compile-time fallback for QJS_EXPERIMENT_ALLOCATOR when unset in environment (empty, off, 0, header, 128, 256, 512)"
)
option(QJS_FRAME_EXPERIMENTAL_COMPARE
       "Build mixed integer/double comparison ablation in native handlers" OFF)
option(QJS_BACKPORT_COMPUTED_ASSIGN
       "Apply declared upstream computed-assignment compiler correction" OFF)
option(QJS_BACKPORT_VALUE64_INIT
       "Backport Bellard's complete integer payload initialization in the private core" OFF)
option(QJS_BACKPORT_MIXED_NUMBERS "Backport Bellard's mixed int/double C interpreter fast paths"
       OFF)
option(QJS_BACKPORT_MAP_POINTER_HASH
       "Mix Map/Set object and symbol pointer hashes before narrowing" OFF)
option(QJS_BACKPORT_PORTABLE_REGEXP
       "Use accepted common RegExp and wire semantics in the C backend" OFF)
option(QJS_PROPERTY_IC "Build bytecode-owned property get/set inline caches" OFF)
option(QJS_HYBRID_GC "Build hybrid reference counting with generational partial cycle collection"
       ON)
if(QJS_PROPERTY_IC AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "Property IC requires the declared core overlay")
endif()
if(QJS_HYBRID_GC AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "Hybrid GC requires the declared core source overlay")
endif()
if(QJS_BACKPORT_PORTABLE_REGEXP AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "Portable RegExp compatibility requires the declared core source overlay")
endif()
if(QJS_PROPERTY_IC)
    add_compile_definitions(QJS_PROPERTY_IC)
endif()
if((QJS_BACKPORT_VALUE64_INIT
    OR QJS_BACKPORT_MIXED_NUMBERS
    OR QJS_BACKPORT_MAP_POINTER_HASH)
   AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "Bellard backports require the declared core source overlay")
endif()
if(QJS_BACKPORT_COMPUTED_ASSIGN AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "The compiler ablation currently requires the declared context-OOM overlay")
endif()
if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR AND NOT QJS_BACKPORT_CONTEXT_OOM)
    message(FATAL_ERROR "The allocator experiment requires the declared context-OOM correction")
endif()
if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR AND NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "The current allocator experiment requires a 64-bit target")
endif()
if(NOT QJS_DEFAULT_EXPERIMENT_ALLOCATOR STREQUAL "")
    if(NOT QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        message(
            FATAL_ERROR
                "QJS_DEFAULT_EXPERIMENT_ALLOCATOR requires QJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON")
    endif()
    if(NOT QJS_DEFAULT_EXPERIMENT_ALLOCATOR MATCHES "^(off|0|header|128|256|512)$")
        message(
            FATAL_ERROR
                "QJS_DEFAULT_EXPERIMENT_ALLOCATOR must be empty, off, 0, header, 128, 256 or 512")
    endif()
endif()
function(qjs_apply_declared_backports target)
    if(NOT QJS_BACKPORT_CONTEXT_OOM)
        return()
    endif()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    set(backport_launcher
        "${Python3_EXECUTABLE}"
        -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/backport-core.py"
        --source-root
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build-root
        "${CMAKE_CURRENT_BINARY_DIR}")
    if(QJS_BACKPORT_NATIVE_MODULES)
        list(APPEND backport_launcher --external-compiler-plan)
        list(APPEND backport_launcher --native-string-module)
        # The common length worker is routed in the native core adapter.
        list(APPEND backport_launcher --native-array-length-module)
        list(APPEND backport_launcher --native-regexp-test-module)
    elseif(QJS_BACKPORT_PORTABLE_REGEXP OR QJS_BACKPORT_PORTABLE_REGEXP_REQUIRED)
        # Native ELF workers share these exec/test semantic owners and verify
        # their generated bodies before emitting the real builtin routes.
        # They are required backend inputs even without the portable preset.
        list(APPEND backport_launcher --portable-regexp)
        # A missing prototype can change a bool return into an int call ABI.
        # Reject that integration error before linking a seemingly valid VM.
        if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
            target_compile_options(${target} PRIVATE -Werror=implicit-function-declaration)
        elseif(WIN32)
            target_compile_options(${target} PRIVATE /we4013)
        endif()
    endif()
    if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        list(APPEND backport_launcher --allocator)
    endif()
    if(QJS_BACKPORT_COMPUTED_ASSIGN)
        list(APPEND backport_launcher --computed-assign)
    endif()
    if(QJS_BACKPORT_VALUE64_INIT)
        list(APPEND backport_launcher --value64-init)
        # Narrow readers may be requested by toolchain policy while retaining complete-width stores.
        if(QJS_BACKPORT_NARROW_VALUE_READERS)
            list(APPEND backport_launcher --narrow-value-readers)
        endif()
    endif()
    if(QJS_BACKPORT_MIXED_NUMBERS)
        list(APPEND backport_launcher --mixed-numbers)
    endif()
    if(QJS_BACKPORT_MAP_POINTER_HASH)
        list(APPEND backport_launcher --map-pointer-hash)
    endif()
    if(QJS_PROPERTY_IC)
        list(APPEND backport_launcher --property-ic)
    endif()
    # Native object-module binary adapters pin original core function bytes.
    if(QJS_HYBRID_GC AND NOT QJS_BACKPORT_NATIVE_MODULES)
        list(APPEND backport_launcher --hybrid-gc)
    endif()
    set(backport_generation ${backport_launcher})
    list(APPEND backport_launcher --)
    get_target_property(existing_launcher ${target} C_COMPILER_LAUNCHER)
    if(existing_launcher)
        list(APPEND backport_launcher ${existing_launcher})
    endif()
    set_property(TARGET ${target} PROPERTY C_COMPILER_LAUNCHER "${backport_launcher}")
    set(backport_core_sources "${QJS_UPSTREAM_DIR}/quickjs.c")
    if(EXISTS "${CMAKE_CURRENT_BINARY_DIR}/quickjs.c")
        list(APPEND backport_core_sources "${CMAKE_CURRENT_BINARY_DIR}/quickjs.c")
    endif()
    set_property(
        SOURCE ${backport_core_sources}
        APPEND
        PROPERTY OBJECT_DEPENDS
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/bytecode/compiler-plan-view.h"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/bytecode/compiler-plan-shim.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/backport-core.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/string_rope.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/array_length.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/array/length.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/regexp_test.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/portable_regexp.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/regexp_c.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/generate-wire.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/wire/wire.c"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/wire/regexp_wire.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/test.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/exec.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/regexp/flag-atoms.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/bellard_backports.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/property_ic.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/closure_templates.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/function/closure-template.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/function/closure-template-lifetime.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/function/internal-function-template.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/property-ic.h"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/property-ic.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/property/property-ic-lifetime.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/cvm_segments_c.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/cvm-native-segments.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/cvm-native-segment-opcodes.inc"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/hybrid_gc.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory/hybrid-gc.h"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory/hybrid-gc.inc")
    set_property(
        SOURCE "${QJS_UPSTREAM_DIR}/quickjs-libc.c"
        APPEND
        PROPERTY OBJECT_DEPENDS
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/backport-core.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/file_loader.py"
                 "${CMAKE_CURRENT_SOURCE_DIR}/src/common/io/file-load.inc")
    # Prepare private compiler inputs before Ninja starts compiling. Creating
    # them in the launcher makes their mtimes newer than Ninja's command-start
    # record and forces an otherwise unchanged first incremental build.
    # Track the real source/transformer inputs for native and portable builds;
    # the launcher keeps its hash checks and never changes equal C/header bytes.
    get_source_file_property(backport_core_dependencies "${QJS_UPSTREAM_DIR}/quickjs.c"
                             OBJECT_DEPENDS)
    get_source_file_property(backport_libc_dependencies "${QJS_UPSTREAM_DIR}/quickjs-libc.c"
                             OBJECT_DEPENDS)
    set_property(
        DIRECTORY
        APPEND
        PROPERTY CMAKE_CONFIGURE_DEPENDS "${QJS_UPSTREAM_DIR}/quickjs.c"
                 "${QJS_UPSTREAM_DIR}/quickjs.h" "${QJS_UPSTREAM_DIR}/quickjs-libc.c"
                 ${backport_core_dependencies} ${backport_libc_dependencies})
    get_property(backport_generated GLOBAL PROPERTY QJS_DECLARED_BACKPORTS_READY)
    if(NOT backport_generated)
        execute_process(
            COMMAND ${backport_generation} --generate-only
            RESULT_VARIABLE backport_result
            OUTPUT_VARIABLE backport_output
            ERROR_VARIABLE backport_error)
        if(NOT backport_result EQUAL 0)
            message(
                FATAL_ERROR
                    "Cannot prepare pinned compiler inputs:\n${backport_output}\n${backport_error}")
        endif()
        set_property(GLOBAL PROPERTY QJS_DECLARED_BACKPORTS_READY TRUE)
    endif()
endfunction()
