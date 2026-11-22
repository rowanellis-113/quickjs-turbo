set(QJS_FRAME_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${QJS_FRAME_GENERATED_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/InterpreterStage.cmake")
# Native adapter implementation. Included only after backend capability checks.
qjs_frame_stage_command(
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/cvm_segments.py"
    --source-root
    "${CMAKE_CURRENT_SOURCE_DIR}"
    --check
    VERBATIM)
foreach(
    frame_definition
    QJS_ENABLE_INTERP_FRAME
    QJS_INTERP_FRAME_REGISTER_ABI
    QJS_INTERP_FRAME_TAIL_ENTRY
    QJS_INTERP_FRAME_INTERNAL_ENTRY
    QJS_INTERP_FRAME_INLINE_WINDOW
    QJS_INTERP_FRAME_DIAGNOSTICS
    QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
    if(${frame_definition})
        target_compile_definitions(qjs PRIVATE ${frame_definition})
    endif()
endforeach()
qjs_frame_stage_command(
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/retained_modules.py"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --archive
    "$<TARGET_FILE:qjs>"
    --capture
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/standard_unwind.py"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --archive
    "$<TARGET_FILE:qjs>"
    --restore
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/call_env_adapter.py"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --archive
    "$<TARGET_FILE:qjs>"
    --restore
    VERBATIM)
if(QJS_ENABLE_INTERP_FRAME)
    if(NOT WIN32
       OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8
       OR NOT CMAKE_GENERATOR STREQUAL "Ninja"
       OR BUILD_SHARED_LIBS)
        message(
            FATAL_ERROR
                "The experimental frame adapter currently requires Windows x64, Ninja and a static library"
        )
    endif()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    set(QJS_FRAME_DEBUG_SOURCE_ORIGIN
        ""
        CACHE PATH "Logical source path for reproducible frame DWARF")
    set(QJS_FRAME_DEBUG_BUILD_ORIGIN
        ""
        CACHE PATH "Logical build path for reproducible frame DWARF")
    set(frame_asm_debug_flags)
    if(MINGW
       AND QJS_FRAME_DEBUG_SOURCE_ORIGIN
       AND QJS_FRAME_DEBUG_BUILD_ORIGIN)
        set(frame_asm_debug_flags
            "-Wa,--debug-prefix-map,${CMAKE_CURRENT_SOURCE_DIR}=${QJS_FRAME_DEBUG_SOURCE_ORIGIN}"
            "-Wa,--debug-prefix-map,${CMAKE_CURRENT_BINARY_DIR}=${QJS_FRAME_DEBUG_BUILD_ORIGIN}")
    endif()
    # Adapter outputs can mutate one another's COFF inputs. A tool source
    # change must begin a coherent core/extra-object epoch, not replay only
    # a downstream merge against an already adapted input.
    file(
        GLOB_RECURSE
        frame_adapter_source_dependencies
        CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/*.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/*.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/*.json"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.inc"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/*.inc"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/common/*.json"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/*.json"
        "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/*.inc")
    set(frame_private_header "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-private.h")
    set(frame_retained_private_header
        "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-retained-private.h")
    set(frame_wire_private_header "${QJS_FRAME_GENERATED_DIR}/interpreter-wire-private.h")
    set(frame_core_object "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs-core.dir/quickjs.c.obj")
    if(MINGW
       AND QJS_INTERP_FRAME_REGISTER_ABI
       AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
        # Allocator routing proves exact creator CALL sites against source
        # lines. Supply the required line tables in ordinary Release builds;
        # this must not depend on a profiling shell's global compiler flags.
        target_compile_options(qjs-core PRIVATE -g1 -gdwarf-4)
    endif()
    set(frame_internal_adapter)
    if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
        list(APPEND frame_internal_adapter --internal-entry)
        if(MINGW)
            list(APPEND frame_internal_adapter --objdump "${CMAKE_OBJDUMP}")
        endif()
    endif()
    set(frame_atod_route_commands)
    if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
        list(
            APPEND
            frame_atod_route_commands
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/atod-route.py"
            --object
            "${frame_core_object}")
    endif()
    set(frame_native_slice_adapter_commands)
    if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND MINGW)
        list(
            APPEND
            frame_native_slice_adapter_commands
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/native-slice.py"
            --adapt
            --source
            "${CMAKE_CURRENT_SOURCE_DIR}"
            --object
            "${frame_core_object}"
            --header
            "${QJS_FRAME_GENERATED_DIR}/quickjs-native-slice-private.h")
    endif()
    if(QJS_INTERP_FRAME_REGISTER_ABI
       AND QJS_INTERP_FRAME_INTERNAL_ENTRY
       AND (MINGW OR (MSVC AND QJS_INTERP_FRAME_LEAF_ENTRY)))
        list(
            APPEND
            frame_native_slice_adapter_commands
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/prepared-callback.py"
            --adapt
            --source
            "${CMAKE_CURRENT_SOURCE_DIR}"
            --object
            "${frame_core_object}"
            --header
            "${QJS_FRAME_GENERATED_DIR}/quickjs-callback-private.h")
    endif()
    if(QJS_INTERP_FRAME_REGISTER_ABI
       AND QJS_INTERP_FRAME_INTERNAL_ENTRY
       AND (MINGW OR (MSVC AND QJS_INTERP_FRAME_LEAF_ENTRY)))
        list(
            APPEND
            frame_native_slice_adapter_commands
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/json-serializer.py"
            --adapt
            --source
            "${CMAKE_CURRENT_SOURCE_DIR}"
            --object
            "${frame_core_object}"
            --header
            "${QJS_FRAME_GENERATED_DIR}/quickjs-json-private.h")
    endif()
    if(QJS_INTERP_FRAME_REGISTER_ABI AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
        set_property(
            SOURCE src/x86/win64/common/quickjs-interpreter.c
            APPEND
            PROPERTY OBJECT_DEPENDS
                     "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/adapter-restart.py")
        qjs_frame_stage_command(
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/native-c-scope.py"
            --restore-vm
            --source
            "${CMAKE_CURRENT_SOURCE_DIR}"
            --build
            "${CMAKE_CURRENT_BINARY_DIR}"
            VERBATIM)
        qjs_frame_stage_command(
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/adapter-restart.py"
            --object
            "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
            --build
            "${CMAKE_CURRENT_BINARY_DIR}"
            VERBATIM)
    endif()
    if(QJS_INTERP_FRAME_REGISTER_ABI AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
        qjs_frame_stage_command(
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/call-link.py"
            --restore-vm
            --source
            "${CMAKE_CURRENT_SOURCE_DIR}"
            --build
            "${CMAKE_CURRENT_BINARY_DIR}"
            VERBATIM)
    endif()
    qjs_frame_stage_command(
        COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py"
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        --compiled-times
        capture
        VERBATIM)
    # This intrinsic is qualified for GNU. Other compilers keep the exact
    # original dependency graph, C hook and archive members, not an OFF guard.
    set(frame_instanceof_adapter)
    if(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        set(frame_instanceof_adapter --native-instanceof)
    endif()
    add_custom_command(
        OUTPUT "${frame_private_header}" "${frame_retained_private_header}"
               "${frame_wire_private_header}"
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/adapter-restart.py" --core --object
            "${frame_core_object}" --build "${CMAKE_CURRENT_BINARY_DIR}"
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py" --source
            "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --compiled-times
            core
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/generate-bigint.py" --source
            "${CMAKE_CURRENT_SOURCE_DIR}" --output
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-bigint.inc" --check
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/generate_shared_host.py" --source
            "${CMAKE_CURRENT_SOURCE_DIR}" --output
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-shared-host.inc"
            --check
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/backports/generate-wire.py" --source
            "${CMAKE_CURRENT_SOURCE_DIR}" --output
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/wire/wire.c" --check
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/object-adapter.py" --source
            "${QJS_UPSTREAM_DIR}/quickjs.c" --object "${frame_core_object}" --header
            "${frame_private_header}" --retained-header "${frame_retained_private_header}"
            --wire-header "${frame_wire_private_header}" ${frame_internal_adapter}
            ${frame_instanceof_adapter} ${frame_atod_route_commands}
            ${frame_native_slice_adapter_commands}
        DEPENDS qjs-core
                "${frame_core_object}"
                tools/x86/win64/coff/object-adapter.py
                tools/x86/win64/codegen/atod-route.py
                tools/x86/win64/codegen/adapter-restart.py
                ${frame_adapter_source_dependencies}
                src/x86/win64/common/quickjs-interpreter.c
                src/common/call/quickjs-interpreter-loop.inc
                src/common/call/quickjs-interpreter-ops.inc
                src/common/call/quickjs-interpreter-bigint.inc
                tools/common/backports/generate-bigint.py
                src/common/value/instanceof.c
                src/common/call/quickjs-interpreter-shared-host.inc
                tools/common/c_extract/generate_shared_host.py
                tools/x86/win64/codegen/native-slice.py
                src/x86/win64/common/quickjs-interpreter-slice-native.inc
                src/x86/win64/common/quickjs-interpreter-cached-sort.inc
                src/common/call/quickjs-interpreter-prepared-entry.inc
                tools/x86/common/codegen/regexp.py
                src/x86/win64/common/quickjs-regexp-replace.inc
                src/x86/win64/common/quickjs-regexp-flags.inc
                src/common/string/locale-compare.inc
                tools/common/backports/regexp_test.py
                src/common/regexp/test.inc
                src/common/regexp/exec.inc
                src/common/regexp/flag-atoms.inc
                tools/x86/common/codegen/prepared-callback.py
                src/x86/win64/common/quickjs-interpreter-prepared-callback.inc
                tools/x86/win64/codegen/json-serializer.py
                src/x86/win64/common/quickjs-interpreter-json.inc
                tools/x86/common/codegen/json-callback.py
                src/x86/win64/common/quickjs-interpreter-json-callback.inc
                tools/x86/win64/codegen/call-link.py
                tools/x86/win64/codegen/numeric-invoke.py
                tools/x86/win64/codegen/native-c-scope.py
                tools/x86/win64/codegen/call-metadata.py
                tools/x86/common/codegen/varargs.py
                src/x86/win64/common/quickjs-interpreter-call-link.inc
        BYPRODUCTS "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-private.json"
                   "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi.h"
                   "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-values.h"
                   "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-gas.inc"
                   "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-masm.inc"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-core-original.obj"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-json-private.h"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-json-writer-private.h"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-json-parser-backend.h"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-json-writer-backend.h"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-json-split.json"
        VERBATIM)
    target_sources(qjs PRIVATE src/x86/win64/common/quickjs-interpreter.c "${frame_private_header}")
    if(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        target_sources(qjs PRIVATE src/common/value/instanceof.c)
        set_source_files_properties(src/common/value/instanceof.c
                                    PROPERTIES OBJECT_DEPENDS "${frame_private_header}")
        set_property(
            SOURCE src/x86/win64/common/quickjs-interpreter.c
            APPEND
            PROPERTY COMPILE_DEFINITIONS JS_IsInstanceOf=JS_FrameInstanceOf)
    endif()
    set_source_files_properties(src/x86/win64/common/quickjs-interpreter.c
                                PROPERTIES OBJECT_DEPENDS "${frame_private_header}")
    target_include_directories(qjs PRIVATE "${QJS_FRAME_GENERATED_DIR}"
                                           "${CMAKE_CURRENT_BINARY_DIR}")
    if(QJS_PROPERTY_IC)
        # Move only cold IC invalidation/cache releases out of the large core.
        # Ordinary RC and native transition hits retain their existing bodies.
        target_compile_definitions(qjs-core PRIVATE QJS_PROPERTY_IC_LIFETIME_MODULE)
        target_compile_definitions(qjs PRIVATE QJS_PROPERTY_IC_LIFETIME_MODULE)
        set(property_lifetime_header
            "${QJS_FRAME_GENERATED_DIR}/quickjs-property-ic-lifetime-private.h")
        add_custom_command(
            OUTPUT "${property_lifetime_header}"
            COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/property_ic_lifetime.py"
                --source "${CMAKE_CURRENT_SOURCE_DIR}" --core
                "${QJS_FRAME_GENERATED_DIR}/quickjs-core-original.obj" --output
                "${property_lifetime_header}"
            DEPENDS "${frame_private_header}" tools/x86/win64/codegen/property_ic_lifetime.py
                    src/common/property/property-ic-lifetime.c
                    src/common/property/property-ic-lifetime.inc src/common/property/property-ic.h
            BYPRODUCTS "${QJS_FRAME_GENERATED_DIR}/quickjs-property-ic-lifetime-private.json"
            VERBATIM)
        target_sources(qjs PRIVATE src/common/property/property-ic-lifetime.c
                                   "${property_lifetime_header}")
        set_source_files_properties(src/common/property/property-ic-lifetime.c
                                    PROPERTIES OBJECT_DEPENDS "${property_lifetime_header}")
    endif()

    if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
        target_compile_definitions(qjs PRIVATE QJS_INTERP_FRAME_INTERNAL_ENTRY)
        set(frame_internal_masm "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-internal-win64.asm")
        set(frame_internal_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-internal-win64.S")
        set(frame_internal_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-internal.obj")
        add_custom_command(
            OUTPUT "${frame_internal_masm}" "${frame_internal_gas}"
            COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/generate-internal.py" --source
                "${CMAKE_CURRENT_SOURCE_DIR}" --out "${QJS_FRAME_GENERATED_DIR}"
            DEPENDS tools/x86/win64/codegen/generate-internal.py
            VERBATIM)
        if(MSVC)
            find_program(frame_internal_assembler NAMES ml64 REQUIRED)
            add_custom_command(
                OUTPUT "${frame_internal_object}"
                COMMAND "${frame_internal_assembler}" /nologo /c /Zi "/Fo${frame_internal_object}"
                        "${frame_internal_masm}"
                DEPENDS "${frame_internal_masm}"
                VERBATIM)
        elseif(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
            add_custom_command(
                OUTPUT "${frame_internal_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g ${frame_asm_debug_flags} -x assembler-with-cpp
                        "${frame_internal_gas}" -o "${frame_internal_object}"
                DEPENDS "${frame_internal_gas}"
                VERBATIM)
        else()
            message(FATAL_ERROR "The internal entry supports MSVC or MinGW GCC on Win64")
        endif()
        set_source_files_properties("${frame_internal_object}" PROPERTIES GENERATED TRUE
                                                                          EXTERNAL_OBJECT TRUE)
        target_sources(qjs PRIVATE "${frame_internal_object}")
    endif()
    if(QJS_INTERP_FRAME_INLINE_WINDOW)
        target_compile_definitions(qjs PRIVATE QJS_INTERP_FRAME_INLINE_WINDOW)
    endif()
    if(QJS_INTERP_FRAME_REGISTER_ABI)
        set(frame_slow_header "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-slow.h")
        add_custom_command(
            OUTPUT "${frame_slow_header}"
            COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/generate-slow.py" --source
                "${CMAKE_CURRENT_SOURCE_DIR}" --output "${frame_slow_header}"
            DEPENDS tools/x86/win64/codegen/generate-slow.py
                    src/common/call/quickjs-interpreter-loop.inc
            VERBATIM)
        target_sources(qjs PRIVATE "${frame_slow_header}")
        set_property(
            SOURCE src/x86/win64/common/quickjs-interpreter.c
            APPEND
            PROPERTY OBJECT_DEPENDS "${frame_slow_header}")
        set(frame_register_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-register.obj")
        set(frame_register_masm "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-register-win64.asm")
        set(frame_register_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-register-win64.S")
        set(frame_register_diagnostics)
        if(QJS_FRAME_EXPERIMENTAL_COMPARE)
            list(APPEND frame_register_diagnostics --numeric-compare)
        endif()
        set(frame_global_binding_commands)
        set(frame_global_binding_arguments)
        if(QJS_INTERP_FRAME_GLOBAL_BINDING)
            set(frame_global_binding_gas
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-global-binding-win64.S")
            if(QJS_INTERP_FRAME_LEAF_ENTRY)
                list(APPEND frame_global_binding_arguments --leaf-entry)
            endif()
            if(QJS_INTERP_FRAME_DIAGNOSTICS)
                list(APPEND frame_global_binding_arguments --diagnostics)
            endif()
            list(
                APPEND
                frame_global_binding_commands
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/global-binding.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --build
                "${CMAKE_CURRENT_BINARY_DIR}"
                ${frame_global_binding_arguments})
        endif()
        if(MSVC AND QJS_INTERP_FRAME_LEAF_ENTRY)
            list(APPEND frame_register_diagnostics --leaf-entry-masm)
        endif()
        if(QJS_INTERP_FRAME_DIAGNOSTICS)
            list(APPEND frame_register_diagnostics --diagnostics)
        endif()
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            list(APPEND frame_register_diagnostics --internal-entry)
        endif()

        set(frame_owned_masm "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-owned-win64.asm")
        set(frame_owned_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-owned-win64.S")
        set(frame_local_masm
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string-win64.asm")
        set(frame_local_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string-win64.S")
        set(frame_native_slice_gas
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-slice-win64.S")
        set(frame_native_slice_masm
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-slice-win64.asm")
        set(frame_native_root_select_gas
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-select-win64.S")
        set(frame_native_root_select_object
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-select.obj")
        set(frame_native_root_args_gas
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-args-win64.S")
        set(frame_native_root_args_object
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-args.obj")
        set(frame_public_root_gas
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-public-root-win64.S")
        set(frame_public_root_object
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-public-root.obj")
        set(frame_publish_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-publish-win64.S")
        set(frame_publish_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-publish.obj")
        set(frame_c_invoke_gas "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-c-invoke-win64.S")
        set(frame_c_invoke_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-c-invoke.obj")
        set(frame_native_root_zero_gas
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-zero-win64.S")
        set(frame_native_root_zero_object
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root-zero.obj")
        set(frame_owned_outputs)
        if(qjs_frame_leaf_masm_default AND QJS_INTERP_FRAME_LEAF_ENTRY)
            list(APPEND frame_register_diagnostics --c-invoke-masm)
        endif()
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND MINGW)
            list(APPEND frame_register_diagnostics --native-slice)
            if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
                list(APPEND frame_register_diagnostics --pool-allocator)
            endif()
            list(
                APPEND
                frame_owned_outputs
                "${frame_native_slice_gas}"
                "${frame_native_slice_masm}"
                "${frame_native_root_zero_gas}"
                "${frame_native_root_select_gas}"
                "${frame_native_root_args_gas}"
                "${frame_public_root_gas}"
                "${frame_publish_gas}"
                "${frame_c_invoke_gas}"
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-win64.S")
        endif()
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            list(APPEND frame_owned_outputs "${frame_owned_masm}" "${frame_owned_gas}"
                 "${frame_local_masm}" "${frame_local_gas}")
        endif()
        if(QJS_INTERP_FRAME_GLOBAL_BINDING)
            list(APPEND frame_owned_outputs "${frame_global_binding_gas}"
                 "${CMAKE_CURRENT_BINARY_DIR}/global-binding-generation.json")
        endif()
        add_custom_command(
            OUTPUT "${frame_register_masm}" "${frame_register_gas}" ${frame_owned_outputs}
            COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/generate-register.py" --source
                "${CMAKE_CURRENT_SOURCE_DIR}" --out "${QJS_FRAME_GENERATED_DIR}"
                ${frame_register_diagnostics} ${frame_global_binding_commands}
            DEPENDS tools/x86/common/codegen/generate-register.py
                    tools/x86/common/codegen/array-append.py
                    tools/x86/common/codegen/publish-boundary.py
                    tools/x86/win64/codegen/c-invoke.py
                    tools/x86/win64/codegen/numeric-invoke.py
                    tools/x86/win64/codegen/native-c-scope.py
                    tools/x86/win64/codegen/call-metadata.py
                    tools/x86/common/codegen/varargs.py
                    tools/x86/common/codegen/iterator.py
                    tools/x86/common/codegen/iterator-fast.py
                    tools/x86/win64/codegen/public-root.py
                    tools/x86/win64/codegen/native-root.py
                    tools/x86/win64/codegen/native-root-zero.py
                    tools/x86/win64/codegen/native-root-args.py
                    tools/x86/win64/codegen/native-slice.py
                    tools/x86/common/codegen/number-property.py
                    tools/x86/common/codegen/proto-load.py
                    tools/x86/common/codegen/local-string.py
                    tools/x86/win64/codegen/numeric-trampoline.py
                    tools/x86/common/codegen/global-binding.py
                    tools/x86/common/codegen/leaf-entry.py
                    tools/x86/win64/codegen/generic-trampoline.py
                    tools/x86/win64/codegen/generic-window.py
                    tools/x86/win64/codegen/child-entry.py
                    tools/x86/win64/codegen/generate-internal.py
                    tools/x86/common/codegen/slot-store.py
                    tools/x86/win64/codegen/add-boundary.py
                    tools/x86/common/codegen/zero-host.py
                    tools/x86/common/codegen/child-leaf.py
                    tools/x86/common/codegen/root-leaf.py
                    tools/x86/common/codegen/null-proto.py
                    tools/x86/common/codegen/add-local.py
                    tools/x86/common/codegen/free-boundary.py
                    tools/x86/common/codegen/js-owned-missing.py
                    "${QJS_UPSTREAM_DIR}/quickjs-opcode.h"
                    "${QJS_UPSTREAM_DIR}/quickjs.c"
                    src/common/call/quickjs-interpreter-register.h
            VERBATIM)
        if(MSVC)
            find_program(frame_register_assembler NAMES ml64 REQUIRED)
            add_custom_command(
                OUTPUT "${frame_register_object}"
                COMMAND "${frame_register_assembler}" /nologo /c /Zi "/Fo${frame_register_object}"
                        "${frame_register_masm}"
                DEPENDS "${frame_register_masm}"
                VERBATIM)
        elseif(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
            add_custom_command(
                OUTPUT "${frame_register_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g ${frame_asm_debug_flags} -x assembler-with-cpp
                        "${frame_register_gas}" -o "${frame_register_object}"
                DEPENDS "${frame_register_gas}"
                VERBATIM)
        else()
            message(FATAL_ERROR "The register ABI currently supports MSVC or MinGW GCC on Win64")
        endif()
        set_source_files_properties("${frame_register_object}" PROPERTIES GENERATED TRUE
                                                                          EXTERNAL_OBJECT TRUE)
        target_sources(
            qjs
            PRIVATE "${frame_register_object}"
                    src/common/call/quickjs-interpreter-register.h
                    src/common/call/quickjs-interpreter-shared.inc
                    src/common/call/quickjs-interpreter-shared-host.inc
                    src/x86/win64/common/quickjs-interpreter-numeric-host.inc
                    src/x86/win64/common/quickjs-interpreter-generic-host.inc)
        set_property(
            SOURCE src/x86/win64/common/quickjs-interpreter.c
            APPEND
            PROPERTY
                OBJECT_DEPENDS
                "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-shared.inc"
                "${CMAKE_CURRENT_SOURCE_DIR}/src/common/call/quickjs-interpreter-shared-host.inc"
                "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/common/quickjs-interpreter-numeric-host.inc"
                "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/common/quickjs-interpreter-generic-host.inc"
        )
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            set_property(
                SOURCE src/x86/win64/common/quickjs-interpreter.c
                APPEND
                PROPERTY OBJECT_DEPENDS
                         "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/shared-alias.py"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/null-proto.py")
            qjs_frame_stage_command(
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/shared-alias.py"
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                VERBATIM)
            # Append the new C contribution after existing register islands.
            # The old validator remains compiled with its original call graph.
            set(frame_null_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-null-proto.obj")
            set(frame_null_arena_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-null-arena.obj")
            set(frame_atod_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-atod.obj")
            set(frame_local_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string.obj")
            set(frame_null_arena_asan OFF)
            if(QJS_ENABLE_ASAN OR "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_RELEASE}" MATCHES
                                  "[-/]fsanitize=address")
                set(frame_null_arena_asan ON)
            endif()
            set(frame_owned_merge_commands)
            set(frame_owned_merge_depends)
            set(frame_owned_merge_byproducts)
            if(MSVC)
                set(frame_owned_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-owned.obj")
                list(
                    APPEND
                    frame_owned_merge_commands
                    COMMAND
                    "${frame_register_assembler}"
                    /nologo
                    /c
                    /Zi
                    "/Fo${frame_owned_object}"
                    "${frame_owned_masm}"
                    COMMAND
                    "${frame_register_assembler}"
                    /nologo
                    /c
                    /Zi
                    "/Fo${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string-guard.obj"
                    "${frame_local_masm}"
                    COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/owned-merge.py"
                    --destination
                    "${frame_null_object}"
                    --source
                    "${frame_owned_object}")
                # ASan registration metadata must remain in its ordinary object.
                # Release/diagnostic builds keep f94f's existing member layout.
                if(NOT frame_null_arena_asan)
                    list(
                        APPEND
                        frame_owned_merge_commands
                        COMMAND
                        "${Python3_EXECUTABLE}"
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/null-merge.py"
                        --destination
                        "${frame_null_object}"
                        --source
                        "${frame_null_arena_object}")
                    list(
                        APPEND
                        frame_owned_merge_commands
                        COMMAND
                        "${Python3_EXECUTABLE}"
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/atod-merge.py"
                        --destination
                        "${frame_null_object}"
                        --source
                        "${frame_atod_object}")
                    list(
                        APPEND
                        frame_owned_merge_commands
                        COMMAND
                        "${Python3_EXECUTABLE}"
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/extension-merge.py"
                        --destination
                        "${frame_null_object}"
                        --source
                        "${frame_local_object}"
                        --entry
                        JS_FrameAddLocalString
                        --tag
                        local-string
                        --keep-all)
                endif()
                list(
                    APPEND
                    frame_owned_merge_commands
                    COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/extension-merge.py"
                    --destination
                    "${frame_null_object}"
                    --source
                    "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string-guard.obj"
                    --entry
                    JS_FrameAddLocalStringCold
                    --tag
                    local-string-guard)
                list(APPEND frame_owned_merge_depends "${frame_local_masm}" "${frame_local_object}"
                     tools/x86/win64/codegen/extension-merge.py)
                list(
                    APPEND
                    frame_owned_merge_depends
                    "${frame_owned_masm}"
                    tools/x86/win64/codegen/owned-merge.py
                    "${frame_null_arena_object}"
                    tools/x86/win64/codegen/null-merge.py
                    "${frame_atod_object}"
                    tools/x86/win64/codegen/atod-merge.py)
                list(APPEND frame_owned_merge_byproducts "${frame_owned_object}"
                     "${frame_null_object}.before-owned" "${frame_null_object}.owned-merge.json")
            endif()
            add_custom_command(
                OUTPUT "${frame_null_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/null-proto.py" --compile
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --out "${frame_null_object}" ${frame_owned_merge_commands}
                BYPRODUCTS ${frame_owned_merge_byproducts}
                DEPENDS "${frame_private_header}"
                        ${frame_owned_merge_depends}
                        tools/x86/common/codegen/null-proto.py
                        tools/x86/common/codegen/add-local.py
                        src/common/call/quickjs-interpreter-bigint.inc
                        src/common/call/quickjs-interpreter-loop.inc
                VERBATIM)
            set_source_files_properties("${frame_null_object}" PROPERTIES GENERATED TRUE
                                                                          EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_null_object}")
            qjs_frame_stage_command(
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/null-proto.py"
                --route
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                --objdump
                "${frame_null_objdump}"
                VERBATIM)
        endif()

        # MinGW preserves old prefixes with an ordinary last source. MSVC
        # appends to the existing null-proto member in its compile command.
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND MINGW)
            enable_language(ASM)
            set(frame_owned_source "${frame_owned_gas}")
            set(frame_owned_object
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/generated/quickjs-interpreter-owned-win64.S.obj"
            )
            set_source_files_properties("${frame_owned_source}" PROPERTIES GENERATED TRUE)
            target_sources(qjs PRIVATE "${frame_owned_source}")
        endif()
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            set(frame_null_arena_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-null-arena.obj")
            add_custom_command(
                OUTPUT "${frame_null_arena_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/null-arena.py" --compile
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --out "${frame_null_arena_object}"
                DEPENDS "${frame_private_header}" tools/x86/common/codegen/null-arena.py
                        tools/x86/common/codegen/null-proto.py "${QJS_UPSTREAM_DIR}/quickjs.c"
                VERBATIM)
            set_source_files_properties("${frame_null_arena_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set(frame_null_arena_extension_object)
            if(MINGW OR frame_null_arena_asan)
                target_sources(qjs PRIVATE "${frame_null_arena_object}")
                set(frame_null_arena_extension_object "${frame_null_arena_object}")
            endif()
        endif()
        set(frame_atod_extension_object)
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            set(frame_atod_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-atod.obj")
            add_custom_command(
                OUTPUT "${frame_atod_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/atod.py" --compile --source
                    "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --out
                    "${frame_atod_object}"
                DEPENDS "${frame_private_header}" tools/x86/win64/codegen/atod.py
                        tools/x86/common/codegen/null-proto.py src/x86/common/string-to-number.c
                        "${QJS_UPSTREAM_DIR}/dtoa.h"
                VERBATIM)
            set_source_files_properties("${frame_atod_object}" PROPERTIES GENERATED TRUE
                                                                          EXTERNAL_OBJECT TRUE)
            if(MINGW OR frame_null_arena_asan)
                target_sources(qjs PRIVATE "${frame_atod_object}")
                set(frame_atod_extension_object "${frame_atod_object}")
            endif()
        endif()
        set(frame_local_extension_object)
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY)
            set(frame_local_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-local-string.obj")
            add_custom_command(
                OUTPUT "${frame_local_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/local-string.py" --compile
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --out "${frame_local_object}"
                DEPENDS "${frame_private_header}" tools/x86/common/codegen/local-string.py
                        tools/x86/win64/codegen/atod.py src/common/call/quickjs-interpreter-loop.inc
                        src/common/string/local-rope-append.inc
                VERBATIM)
            set_source_files_properties("${frame_local_object}" PROPERTIES GENERATED TRUE
                                                                           EXTERNAL_OBJECT TRUE)
            if(MINGW OR frame_null_arena_asan)
                target_sources(qjs PRIVATE "${frame_local_object}")
                set(frame_local_extension_object "${frame_local_object}")
            endif()
            if(MINGW)
                set_source_files_properties("${frame_local_gas}" PROPERTIES GENERATED TRUE)
                target_sources(qjs PRIVATE "${frame_local_gas}")
                set(frame_local_guard_object
                    "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/generated/quickjs-interpreter-local-string-win64.S.obj"
                )
            endif()
        endif()
        set(frame_native_slice_object)
        set(frame_native_slice_guard_object)
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND MINGW)
            set(frame_native_slice_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-slice.obj")
            set(frame_cached_sort_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-cached-sort.obj")
            set(frame_prepared_sort_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-prepared-sort.obj")
            set(frame_number_property_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-number-property.obj")
            set(frame_proto_load_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-proto-load.obj")
            set(frame_proto_persistent_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-proto-persistent.obj")
            set(frame_native_root_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-root.obj")
            add_custom_command(
                OUTPUT "${frame_native_slice_object}"
                       "${frame_cached_sort_object}"
                       "${frame_prepared_sort_object}"
                       "${frame_number_property_object}"
                       "${frame_proto_load_object}"
                       "${frame_proto_persistent_object}"
                       "${frame_native_root_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/native-slice.py" --compile
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --out "${frame_native_slice_object}"
                DEPENDS "${frame_private_header}"
                        tools/x86/win64/codegen/native-slice.py
                        tools/x86/win64/codegen/atod.py
                        src/x86/win64/common/quickjs-interpreter-slice-native.inc
                        src/x86/win64/common/quickjs-interpreter-cached-sort.inc
                        src/common/call/quickjs-interpreter-prepared-entry.inc
                        src/x86/win64/common/quickjs-interpreter-number-property.inc
                        src/x86/win64/common/quickjs-interpreter-proto-load.inc
                        src/x86/win64/common/quickjs-interpreter-proto-persistent.inc
                        src/x86/win64/common/quickjs-interpreter-native-root.inc
                VERBATIM)
            set_source_files_properties("${frame_native_slice_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set_source_files_properties("${frame_native_slice_gas}"
                                        PROPERTIES GENERATED TRUE COMPILE_OPTIONS "-g0")
            set_source_files_properties("${frame_cached_sort_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set_source_files_properties("${frame_prepared_sort_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set_source_files_properties("${frame_number_property_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set_source_files_properties(
                "${frame_proto_load_object}" "${frame_proto_persistent_object}"
                PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            set_source_files_properties("${frame_native_root_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            add_custom_command(
                OUTPUT "${frame_native_root_zero_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${frame_native_root_zero_gas}" -o "${frame_native_root_zero_object}"
                DEPENDS "${frame_native_root_zero_gas}"
                VERBATIM)
            set_source_files_properties("${frame_native_root_zero_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_native_root_zero_object}")
            add_custom_command(
                OUTPUT "${frame_native_root_select_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${frame_native_root_select_gas}" -o "${frame_native_root_select_object}"
                DEPENDS "${frame_native_root_select_gas}"
                VERBATIM)
            set_source_files_properties("${frame_native_root_select_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_native_root_select_object}")
            add_custom_command(
                OUTPUT "${frame_native_root_args_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${frame_native_root_args_gas}" -o "${frame_native_root_args_object}"
                DEPENDS "${frame_native_root_args_gas}"
                VERBATIM)
            set_source_files_properties("${frame_native_root_args_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_native_root_args_object}")
            add_custom_command(
                OUTPUT "${frame_public_root_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${frame_public_root_gas}" -o "${frame_public_root_object}"
                DEPENDS "${frame_public_root_gas}"
                VERBATIM)
            set_source_files_properties("${frame_public_root_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_public_root_object}")
            add_custom_command(
                OUTPUT "${frame_publish_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp "${frame_publish_gas}" -o
                        "${frame_publish_object}"
                DEPENDS "${frame_publish_gas}"
                VERBATIM)
            set_source_files_properties("${frame_publish_object}" PROPERTIES GENERATED TRUE
                                                                             EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_publish_object}")
            target_sources(
                qjs
                PRIVATE "${frame_native_slice_object}"
                        "${frame_native_slice_gas}"
                        "${frame_cached_sort_object}"
                        "${frame_prepared_sort_object}"
                        "${frame_number_property_object}"
                        "${frame_proto_load_object}"
                        "${frame_proto_persistent_object}"
                        "${frame_native_root_object}")
            set(frame_native_slice_guard_object
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/generated/quickjs-interpreter-native-slice-win64.S.obj"
            )
            add_custom_command(
                OUTPUT "${frame_c_invoke_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp "${frame_c_invoke_gas}"
                        -o "${frame_c_invoke_object}"
                DEPENDS "${frame_c_invoke_gas}"
                VERBATIM)
            set_source_files_properties("${frame_c_invoke_object}" PROPERTIES GENERATED TRUE
                                                                              EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_c_invoke_object}")
            set(frame_iterator_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator.obj")
            set(frame_iterator_asm_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-asm.obj")
            set(frame_iterator_gas
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-win64.S")
            add_custom_command(
                OUTPUT "${frame_iterator_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator.py" --compile
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --out "${frame_iterator_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py"
                    --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                    --compiled-times iterator
                # Both generators publish aliases in the live core object.
                # Serialize the read/modify/write operations before consumers.
                DEPENDS "${frame_private_header}"
                        "${frame_null_arena_object}"
                        tools/x86/common/codegen/iterator.py
                        tools/x86/win64/codegen/atod.py
                        tools/x86/win64/codegen/generate-slow.py
                        src/common/call/quickjs-interpreter-loop.inc
                        src/common/call/quickjs-interpreter-ops.inc
                        src/common/call/quickjs-interpreter-opcodes.h
                        src/common/call/quickjs-interpreter-dispatch.inc
                        "${QJS_UPSTREAM_DIR}/quickjs.c"
                VERBATIM)
            add_custom_command(
                OUTPUT "${frame_iterator_asm_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp "${frame_iterator_gas}"
                        -o "${frame_iterator_asm_object}"
                DEPENDS "${frame_iterator_gas}"
                VERBATIM)
            set_source_files_properties("${frame_iterator_object}" "${frame_iterator_asm_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_iterator_object}" "${frame_iterator_asm_object}")
            set(frame_iterator_fast_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-fast.obj")
            add_custom_command(
                OUTPUT "${frame_iterator_fast_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-fast.py"
                    --compile --source "${CMAKE_CURRENT_SOURCE_DIR}" --build
                    "${CMAKE_CURRENT_BINARY_DIR}" --out "${frame_iterator_fast_object}"
                DEPENDS "${frame_iterator_object}"
                        tools/x86/common/codegen/iterator-fast.py
                        tools/x86/win64/codegen/atod.py
                        src/common/call/quickjs-interpreter-register.h
                        src/common/call/quickjs-interpreter-loop.inc
                        "${QJS_UPSTREAM_DIR}/quickjs.c"
                VERBATIM)
            set_source_files_properties("${frame_iterator_fast_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_iterator_fast_object}")
            set(frame_iterator_slow_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-slow.obj")
            add_custom_command(
                OUTPUT "${frame_iterator_slow_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-slow.py"
                    --compile --source "${CMAKE_CURRENT_SOURCE_DIR}" --build
                    "${CMAKE_CURRENT_BINARY_DIR}" --out "${frame_iterator_slow_object}"
                DEPENDS "${frame_iterator_fast_object}" tools/x86/common/codegen/iterator-slow.py
                        tools/x86/common/codegen/iterator.py tools/x86/win64/codegen/atod.py
                        "${QJS_UPSTREAM_DIR}/quickjs.c"
                VERBATIM)
            set_source_files_properties("${frame_iterator_slow_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_iterator_slow_object}")
            set(frame_iterator_checkpoint_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-checkpoint.obj")
            add_custom_command(
                OUTPUT "${frame_iterator_checkpoint_object}"
                BYPRODUCTS
                    "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-checkpoint-win64.S"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-checkpoint.py"
                    --compile --source "${CMAKE_CURRENT_SOURCE_DIR}" --build
                    "${CMAKE_CURRENT_BINARY_DIR}" --out "${frame_iterator_checkpoint_object}"
                DEPENDS "${frame_iterator_slow_object}"
                        tools/x86/common/codegen/iterator-checkpoint.py
                        tools/x86/common/codegen/iterator.py
                        tools/x86/win64/codegen/atod.py
                        "${QJS_UPSTREAM_DIR}/quickjs.c"
                VERBATIM)
            set_source_files_properties("${frame_iterator_checkpoint_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_iterator_checkpoint_object}")
            set(frame_iterator_checkpoint_asm_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-checkpoint-asm.obj")
            add_custom_command(
                OUTPUT "${frame_iterator_checkpoint_asm_object}"
                COMMAND
                    "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                    "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-checkpoint-win64.S" -o
                    "${frame_iterator_checkpoint_asm_object}"
                DEPENDS "${frame_iterator_checkpoint_object}"
                VERBATIM)
            set_source_files_properties("${frame_iterator_checkpoint_asm_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_iterator_checkpoint_asm_object}")
            if(QJS_INTERP_FRAME_ITERATOR_LITERAL)
                set(frame_iterator_literal_object
                    "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-literal.obj")
                add_custom_command(
                    OUTPUT "${frame_iterator_literal_object}"
                    COMMAND
                        "${Python3_EXECUTABLE}"
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py"
                        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
                        --out "${frame_iterator_literal_object}"
                    DEPENDS "${frame_iterator_checkpoint_object}"
                            tools/x86/common/codegen/iterator-literal.py
                            tools/x86/win64/codegen/atod.py
                            tools/x86/win64/coff/object-adapter.py
                            tools/x86/common/codegen/iterator-checkpoint.py
                            src/common/call/quickjs-interpreter-register.h
                            "${QJS_UPSTREAM_DIR}/quickjs.c"
                    VERBATIM)
                set_source_files_properties("${frame_iterator_literal_object}"
                                            PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
                target_sources(qjs PRIVATE "${frame_iterator_literal_object}")
                set(frame_iterator_literal_asm_object
                    "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-literal-asm.obj")
                add_custom_command(
                    OUTPUT "${frame_iterator_literal_asm_object}"
                    COMMAND
                        "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-iterator-literal-win64.S" -o
                        "${frame_iterator_literal_asm_object}"
                    DEPENDS "${frame_iterator_literal_object}"
                    VERBATIM)
                set_source_files_properties("${frame_iterator_literal_asm_object}"
                                            PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
                target_sources(qjs PRIVATE "${frame_iterator_literal_asm_object}")
                set_property(
                    SOURCE src/x86/win64/common/quickjs-interpreter.c
                    APPEND
                    PROPERTY
                        OBJECT_DEPENDS
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py")
            endif()
            qjs_frame_stage_command(
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --objdump
                "${CMAKE_OBJDUMP}"
                --route
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                "${frame_register_object}"
                "${frame_publish_object}"
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-fast.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --objdump
                "${CMAKE_OBJDUMP}"
                --route
                "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                "${frame_register_object}"
                "${frame_publish_object}"
                "${frame_iterator_object}"
                "${frame_iterator_asm_object}"
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-slow.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --objdump
                "${CMAKE_OBJDUMP}"
                --route
                "${frame_iterator_object}"
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-checkpoint.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --objdump
                "${CMAKE_OBJDUMP}"
                --route
                "${frame_iterator_object}"
                "${frame_iterator_asm_object}"
                "${frame_iterator_fast_object}"
                VERBATIM)
            if(QJS_INTERP_FRAME_ITERATOR_LITERAL)
                qjs_frame_stage_command(
                    COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py"
                    --source
                    "${CMAKE_CURRENT_SOURCE_DIR}"
                    --alias-core
                    "${frame_core_object}"
                    --build
                    "${CMAKE_CURRENT_BINARY_DIR}"
                    --objdump
                    "${CMAKE_OBJDUMP}"
                    --route-build
                    VERBATIM)
            endif()
        endif()
        if(QJS_INTERP_FRAME_GLOBAL_BINDING)
            set(frame_global_binding_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-global-binding.obj")
            add_custom_command(
                OUTPUT "${frame_global_binding_object}"
                COMMAND "${CMAKE_C_COMPILER}" -c -g0 -x assembler-with-cpp
                        "${frame_global_binding_gas}" -o "${frame_global_binding_object}"
                DEPENDS "${frame_global_binding_gas}"
                VERBATIM)
            set_source_files_properties("${frame_global_binding_object}"
                                        PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            target_sources(qjs PRIVATE "${frame_global_binding_object}")
            qjs_frame_stage_command(
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/global-binding.py"
                --source
                "${CMAKE_CURRENT_SOURCE_DIR}"
                --build
                "${CMAKE_CURRENT_BINARY_DIR}"
                --adapt-build
                --objdump
                "${CMAKE_OBJDUMP}"
                ${frame_global_binding_arguments}
                VERBATIM)
        endif()
        if(MSVC AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
            qjs_frame_stage_command(
                COMMAND
                "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/cold-order.py"
                --register
                "${frame_register_object}"
                --last
                "${frame_null_object}"
                VERBATIM)
        endif()
        # Executable extension storage has its own late PE island. Changing
        # only its COFF classification leaves core code/data and unwind intact.
        set_property(
            SOURCE src/x86/win64/common/quickjs-interpreter.c
            APPEND
            PROPERTY OBJECT_DEPENDS
                     "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/extension-section.py"
                     "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/cold-order.py")
        qjs_frame_stage_command(
            COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/extension-section.py"
            "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
            "${frame_register_object}"
            ${frame_null_object}
            ${frame_owned_object}
            ${frame_null_arena_extension_object}
            ${frame_atod_extension_object}
            ${frame_local_extension_object}
            ${frame_local_guard_object}
            ${frame_native_slice_object}
            ${frame_native_slice_guard_object}
            VERBATIM)
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND (MINGW OR (MSVC AND QJS_INTERP_FRAME_LEAF_ENTRY)))
            set(frame_callback_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-prepared-callback.obj")
            add_custom_command(
                OUTPUT "${frame_callback_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/prepared-callback.py"
                    --compile --source "${CMAKE_CURRENT_SOURCE_DIR}" --build
                    "${CMAKE_CURRENT_BINARY_DIR}" --out "${frame_callback_object}"
                DEPENDS "${frame_private_header}"
                        "${frame_register_object}"
                        "${QJS_FRAME_GENERATED_DIR}/quickjs-regexp-replace.obj"
                        tools/x86/common/codegen/prepared-callback.py
                        tools/x86/win64/codegen/extension-merge.py
                        tools/x86/win64/codegen/atod.py
                        src/x86/win64/common/quickjs-interpreter-prepared-callback.inc
                VERBATIM)
            set_source_files_properties("${frame_callback_object}" PROPERTIES GENERATED TRUE
                                                                              EXTERNAL_OBJECT TRUE)
            if(MSVC)
                add_custom_target(qjs-callback-island DEPENDS "${frame_callback_object}")
                add_dependencies(qjs qjs-callback-island)
            else()
                target_sources(qjs PRIVATE "${frame_callback_object}")
            endif()
        endif()
        if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND (MINGW OR (MSVC AND QJS_INTERP_FRAME_LEAF_ENTRY)))
            set(frame_call_link_publish_dependency)
            if(MINGW)
                list(APPEND frame_call_link_publish_dependency "${frame_publish_object}")
            endif()
            set(frame_json_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-json.obj")
            set(frame_json_writer_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-json-writer.obj")
            set(frame_json_callback_object
                "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-json-callback.obj")
            add_custom_command(
                OUTPUT "${frame_json_object}" "${frame_json_writer_object}"
                       "${frame_json_callback_object}"
                COMMAND
                    "${Python3_EXECUTABLE}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/json-serializer.py"
                    --compile --source "${CMAKE_CURRENT_SOURCE_DIR}" --build
                    "${CMAKE_CURRENT_BINARY_DIR}" --out "${frame_json_object}"
                DEPENDS "${frame_private_header}"
                        "${frame_callback_object}"
                        ${frame_call_link_publish_dependency}
                        tools/x86/win64/codegen/json-serializer.py
                        tools/x86/win64/codegen/extension-merge.py
                        tools/x86/win64/codegen/atod.py
                        src/x86/win64/common/quickjs-interpreter-json.inc
                        src/x86/win64/common/quickjs-interpreter-json-callback.inc
                        tools/x86/common/codegen/json-callback.py
                VERBATIM)
            set_source_files_properties(
                "${frame_json_object}" "${frame_json_writer_object}" "${frame_json_callback_object}"
                PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
            if(MSVC)
                add_custom_target(
                    qjs-json-island DEPENDS "${frame_json_object}" "${frame_json_writer_object}"
                                            "${frame_json_callback_object}")
                add_dependencies(qjs qjs-json-island)
            else()
                target_sources(qjs PRIVATE "${frame_json_object}" "${frame_json_writer_object}"
                                           "${frame_json_callback_object}")
            endif()
        endif()
        if(MINGW)
            if(IS_ABSOLUTE "${CMAKE_INSTALL_DATADIR}")
                set(frame_install_layout "${CMAKE_INSTALL_DATADIR}/quickjs/extension-layout.ld")
            else()
                set(frame_install_layout
                    "$<INSTALL_PREFIX>/${CMAKE_INSTALL_DATADIR}/quickjs/extension-layout.ld")
            endif()
            # The archive stage above publishes every native record into
            # standard .pdata. Bind its public linker recipe to that contract,
            # so adding ordinary C functions cannot grow legacy directories.
            target_link_options(
                qjs
                INTERFACE
                "-Wl,--defsym,__qjs_native_standard_unwind=1"
                "$<BUILD_INTERFACE:-Wl,-T,${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/extension-layout.ld>"
                "$<INSTALL_INTERFACE:-Wl,-T,${frame_install_layout}>")
            if(QJS_ENABLE_INSTALL)
                install(FILES tools/x86/win64/coff/extension-layout.ld
                        DESTINATION "${CMAKE_INSTALL_DATADIR}/quickjs")
            endif()
        endif()
    endif()
    if(QJS_INTERP_FRAME_TAIL_ENTRY)
        # Assemble separately so the project's C warning/sanitizer flags are
        # never passed to MASM. No C source or core object is changed here.
        set(frame_entry_object "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-entry.obj")
        if(MSVC)
            find_program(frame_masm NAMES ml64)
            if(NOT frame_masm)
                message(FATAL_ERROR "The Win64 tail entry requires ml64 in the MSVC environment")
            endif()
            set(frame_entry_source
                "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/msvc/quickjs-interpreter-entry-win64.asm"
            )
            add_custom_command(
                OUTPUT "${frame_entry_object}"
                COMMAND "${frame_masm}" /nologo /c /Zi "/I${QJS_FRAME_GENERATED_DIR}"
                        "/Fo${frame_entry_object}" "${frame_entry_source}"
                DEPENDS "${frame_entry_source}"
                        "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-masm.inc"
                VERBATIM)
        elseif(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
            set(frame_entry_source
                "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/mingw64/quickjs-interpreter-entry-win64.S"
            )
            set(frame_entry_public_define)
            if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND NOT QJS_INTERP_FRAME_DIAGNOSTICS)
                # Same source/debug line geometry; only one existing RO pointer relocation.
                set(frame_entry_public_define "-DJS_FrameRunCall=JS_FramePublicRootSelect")
            endif()
            add_custom_command(
                OUTPUT "${frame_entry_object}"
                COMMAND
                    "${CMAKE_C_COMPILER}" ${frame_entry_public_define} -c -g
                    ${frame_asm_debug_flags} "-I${QJS_FRAME_GENERATED_DIR}" -x assembler-with-cpp
                    "${frame_entry_source}" -o "${frame_entry_object}"
                DEPENDS "${frame_entry_source}"
                        "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-gas.inc"
                VERBATIM)
        else()
            message(FATAL_ERROR "The Win64 tail entry currently supports MSVC or MinGW GCC")
        endif()
        set_source_files_properties("${frame_entry_object}" PROPERTIES GENERATED TRUE
                                                                       EXTERNAL_OBJECT TRUE)
        target_sources(qjs PRIVATE "${frame_entry_object}")
    endif()
endif()

# Compile new builtins outside the core and frame interpreter call graphs.
if(QJS_ENABLE_INTERP_FRAME)
    set(regexp_object "${QJS_FRAME_GENERATED_DIR}/quickjs-regexp-replace.obj")
    set(array_copy_object "${QJS_FRAME_GENERATED_DIR}/quickjs-array-copy.obj")
    set(default_sort_object "${QJS_FRAME_GENERATED_DIR}/quickjs-default-sort.obj")
    set(generator_capability_object "${QJS_FRAME_GENERATED_DIR}/quickjs-generator-capability.obj")
    set(string_object "${QJS_FRAME_GENERATED_DIR}/quickjs-string.obj")
    set(regexp_split_object "${QJS_FRAME_GENERATED_DIR}/quickjs-regexp-split.obj")
    set(regexp_core_alias_dependencies)
    if(MINGW)
        list(APPEND regexp_core_alias_dependencies "${frame_iterator_fast_object}"
             "${frame_native_slice_object}")
    else()
        list(APPEND regexp_core_alias_dependencies "${frame_null_object}")
    endif()
    add_custom_command(
        OUTPUT "${regexp_object}" "${array_copy_object}" "${string_object}" "${regexp_split_object}"
               "${default_sort_object}" "${generator_capability_object}"
        COMMAND
            "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/regexp.py"
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --out
            "${regexp_object}"
        DEPENDS "${frame_private_header}"
                ${regexp_core_alias_dependencies}
                tools/x86/common/codegen/regexp.py
                tools/x86/common/codegen/regexp_split.py
                src/common/regexp/split.inc
                src/common/regexp/replace-empty.inc
                tools/common/backports/regexp_test.py
                src/common/regexp/test.inc
                src/common/regexp/exec.inc
                src/common/regexp/flag-atoms.inc
                tools/x86/win64/codegen/array-copy.py
                tools/x86/win64/codegen/default-sort.py
                src/common/array/default-string-sort.inc
                tools/x86/common/codegen/generator-capability.py
                src/common/promise/generator-capability.inc
                src/x86/win64/abi/generator-capability.json
                tools/x86/win64/codegen/string-workers.py
                tools/common/backports/string_rope.py
                src/common/array/copy-grow.inc
                src/common/array/length.inc
                src/x86/win64/common/quickjs-regexp-replace.inc
                src/x86/win64/common/quickjs-regexp-flags.inc
                src/common/string/locale-compare.inc
                src/common/string/concat-rope.inc
                src/x86/win64/common/quickjs-string-control.inc
        VERBATIM)
    set_source_files_properties(
        "${regexp_object}" "${array_copy_object}" "${string_object}" "${regexp_split_object}"
        "${default_sort_object}" "${generator_capability_object}" PROPERTIES GENERATED TRUE
                                                                             EXTERNAL_OBJECT TRUE)
    target_sources(qjs PRIVATE "${array_copy_object}" "${default_sort_object}"
                               "${generator_capability_object}")
    if(MSVC)
        # The builtin is appended to an already retained archive member.
        add_custom_target(qjs-regexp-island DEPENDS "${regexp_object}")
        add_dependencies(qjs qjs-regexp-island)
    else()
        target_sources(qjs PRIVATE "${regexp_object}" "${string_object}")
    endif()
endif()
if(QJS_INTERP_FRAME_DIAGNOSTICS)
    target_compile_definitions(qjs PRIVATE QJS_INTERP_FRAME_DIAGNOSTICS)
endif()

if(QJS_ENABLE_INTERP_FRAME
   AND QJS_INTERP_FRAME_REGISTER_ABI
   AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
    if(MSVC)
        set(frame_native_c_scope_object
            "${QJS_FRAME_GENERATED_DIR}/native-c-scope/implementation.obj")
        set(frame_native_c_scope_outputs "${frame_native_c_scope_object}")
    else()
        set(frame_native_c_scope_object
            "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-native-c-scope.obj")
        set(frame_native_c_scope_outputs "${frame_native_c_scope_object}"
                                         "${QJS_FRAME_GENERATED_DIR}/native-scope-entry/entry.obj")
    endif()
    add_custom_command(
        OUTPUT ${frame_native_c_scope_outputs}
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/native-c-scope.py" --compile-module
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
        DEPENDS "${frame_json_callback_object}" tools/x86/win64/codegen/native-c-scope.py
                tools/x86/win64/codegen/call-metadata.py tools/x86/common/codegen/varargs.py
                tools/x86/win64/codegen/c-invoke.py tools/x86/win64/codegen/numeric-invoke.py
        VERBATIM)
    if(MSVC)
        add_custom_target(qjs-native-c-scope DEPENDS ${frame_native_c_scope_outputs})
        add_dependencies(qjs qjs-native-c-scope)
    else()
        set_source_files_properties("${frame_native_c_scope_object}"
                                    PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
        target_sources(qjs PRIVATE "${frame_native_c_scope_object}")
    endif()
    # Compile the accepted VM refill clone as an ordinary archive member. Its
    # private types come from this build's generated header, never an old .obj.
    set(frame_call_env_source "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-call-env.c")
    add_custom_command(
        OUTPUT "${frame_call_env_source}"
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/call_env_adapter.py" --source
            "${CMAKE_CURRENT_SOURCE_DIR}" --output "${frame_call_env_source}"
        DEPENDS tools/x86/win64/coff/call_env_adapter.py
                tools/x86/win64/codegen/call-metadata.py
                tools/x86/win64/codegen/call-link.py
                src/x86/win64/common/quickjs-interpreter-call-link.inc
                src/common/call/quickjs-interpreter-loop.inc
        BYPRODUCTS "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-call-env-parent.c"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-call-env-parent.contract.json"
                   "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-call-env.contract.json"
        VERBATIM)
    set_source_files_properties("${frame_call_env_source}" PROPERTIES OBJECT_DEPENDS
                                                                      "${frame_null_object}")
    target_sources(qjs PRIVATE "${frame_call_env_source}")
    qjs_frame_stage_command(
        COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/call-link.py"
        --route-vm
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        VERBATIM)
    qjs_frame_stage_command(
        COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/varargs.py"
        --compile
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/native-c-scope.py"
        --route-vm
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        COMMAND
        "${Python3_EXECUTABLE}"
        -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/call_env_adapter.py"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        --archive
        "$<TARGET_FILE:qjs>"
        VERBATIM)
endif()

include("${CMAKE_CURRENT_LIST_DIR}/InterpreterRetained.cmake")

# Last adapter, after all native contributions have been composed. The archive
# now carries ordinary .pdata, so external consumers need no PE patching step.
qjs_frame_stage_command(
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/standard_unwind.py"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --archive
    "$<TARGET_FILE:qjs>"
    VERBATIM)

# Ninja binds dependency records to the compiler output mtime. Unwind
# publication also edits COFF objects, so restore the captured compiler times
# only after the final object mutation. The source epoch and archive hashes
# still govern invalidation and reject unrecognized adapted inputs.
if(QJS_ENABLE_INTERP_FRAME)
    qjs_frame_stage_command(
        COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/common/codegen/iterator-literal.py"
        --source
        "${CMAKE_CURRENT_SOURCE_DIR}"
        --build
        "${CMAKE_CURRENT_BINARY_DIR}"
        --compiled-times
        restore
        VERBATIM)
endif()

qjs_frame_stage_attach()

# New split code has its own compiler context and ordinary unwind records.
if(QJS_ENABLE_INTERP_FRAME)
    target_sources(qjs PRIVATE "${regexp_split_object}")
endif()
