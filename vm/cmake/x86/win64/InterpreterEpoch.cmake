# All source changes reconfigure before Ninja decides which objects are fresh.
# The adapters currently require a coherent rebuild rather than partial replay
# of a previous in-place adaptation. This is a build cost, not a runtime knob.
file(
    GLOB
    frame_epoch_inputs
    CONFIGURE_DEPENDS
    "${QJS_UPSTREAM_DIR}/*.c"
    "${QJS_UPSTREAM_DIR}/*.h"
    "${QJS_UPSTREAM_DIR}/*.S"
    "${QJS_UPSTREAM_DIR}/*.asm"
    "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt"
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/QuickJSUpstreamPin.cmake"
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/common/*.cmake"
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/x86/win64/*.cmake")
set_property(
    DIRECTORY
    APPEND
    PROPERTY CMAKE_CONFIGURE_DEPENDS ${frame_epoch_inputs})
# The same inventory drives the Python epoch digest and CMake dependency DAG.
# Keep benchmark tools/corpora and unrelated upstream test subtrees outside it.
set(frame_input_inventory "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/build/native-inputs.json")
file(READ "${frame_input_inventory}" frame_input_json)
set(frame_retained_epoch_inputs "${frame_input_inventory}")
foreach(frame_input_kind directories files)
    string(JSON frame_input_count LENGTH "${frame_input_json}" "${frame_input_kind}")
    math(EXPR frame_input_last "${frame_input_count}-1")
    foreach(frame_input_index RANGE 0 ${frame_input_last})
        string(JSON frame_input GET "${frame_input_json}" "${frame_input_kind}"
               ${frame_input_index})
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${frame_input}")
            set(frame_input_base "${CMAKE_CURRENT_SOURCE_DIR}/${frame_input}")
        else()
            set(frame_input_base "${QJS_UPSTREAM_DIR}/${frame_input}")
        endif()
        if(frame_input_kind STREQUAL "directories")
            file(
                GLOB_RECURSE
                frame_input_paths
                CONFIGURE_DEPENDS
                "${frame_input_base}/*.py"
                "${frame_input_base}/*.ps1"
                "${frame_input_base}/*.cmake"
                "${frame_input_base}/*.ld"
                "${frame_input_base}/*.c"
                "${frame_input_base}/*.h"
                "${frame_input_base}/*.inc"
                "${frame_input_base}/*.js"
                "${frame_input_base}/*.S"
                "${frame_input_base}/*.asm"
                "${frame_input_base}/*.json")
            list(APPEND frame_retained_epoch_inputs ${frame_input_paths})
        else()
            list(APPEND frame_retained_epoch_inputs "${frame_input_base}")
        endif()
    endforeach()
endforeach()
set_property(
    DIRECTORY
    APPEND
    PROPERTY CMAKE_CONFIGURE_DEPENDS ${frame_retained_epoch_inputs})
set_property(
    DIRECTORY
    APPEND
    PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/interpreter-native-epoch.json")
set_property(
    DIRECTORY
    APPEND
    PROPERTY ADDITIONAL_CLEAN_FILES "${CMAKE_CURRENT_BINARY_DIR}/interpreter-native-epoch.json")
get_directory_property(frame_epoch_definitions COMPILE_DEFINITIONS)
get_directory_property(frame_epoch_compile_options COMPILE_OPTIONS)
get_directory_property(frame_epoch_link_options LINK_OPTIONS)
set(frame_epoch_tools)
foreach(
    frame_epoch_tool
    "${CMAKE_C_COMPILER}"
    "${QJS_FRAME_MASM}"
    "${QJS_FRAME_OBJDUMP}"
    "${QJS_FRAME_AS}"
    "${Python3_EXECUTABLE}"
    "${CMAKE_AR}"
    "${CMAKE_LINKER}")
    if(EXISTS "${frame_epoch_tool}")
        file(SHA256 "${frame_epoch_tool}" frame_epoch_tool_hash)
        string(APPEND frame_epoch_tools "|${frame_epoch_tool}:${frame_epoch_tool_hash}")
        set_property(
            DIRECTORY
            APPEND
            PROPERTY CMAKE_CONFIGURE_DEPENDS "${frame_epoch_tool}")
    endif()
endforeach()
string(
    CONCAT
        frame_epoch_configuration
        "backport-context-oom=${QJS_BACKPORT_CONTEXT_OOM}|allocator=${QJS_FRAME_EXPERIMENTAL_ALLOCATOR}|"
        "default-allocator=${QJS_DEFAULT_EXPERIMENT_ALLOCATOR}|"
        "numeric-compare=${QJS_FRAME_EXPERIMENTAL_COMPARE}|computed-assign=${QJS_BACKPORT_COMPUTED_ASSIGN}|"
        "value64=${QJS_BACKPORT_VALUE64_INIT}|mixed-numbers=${QJS_BACKPORT_MIXED_NUMBERS}|"
        "map-pointer-hash=${QJS_BACKPORT_MAP_POINTER_HASH}|property-ic=${QJS_PROPERTY_IC}|"
        "${CMAKE_C_COMPILER}|${CMAKE_C_COMPILER_ID}|${CMAKE_C_COMPILER_VERSION}|${CMAKE_BUILD_TYPE}|${CMAKE_C_FLAGS}|${CMAKE_C_FLAGS_RELEASE}|${CMAKE_C_FLAGS_RELWITHDEBINFO}|${QJS_FRAME_MASM}|${QJS_FRAME_OBJDUMP}|${QJS_INTERP_FRAME_DIAGNOSTICS}|${QJS_INTERP_FRAME_TAIL_ENTRY}|${QJS_INTERP_FRAME_INLINE_WINDOW}|${QJS_INTERP_FRAME_ITERATOR_LITERAL}|${QJS_INTERP_FRAME_GLOBAL_BINDING}|${QJS_INTERP_FRAME_LEAF_ENTRY}|${frame_epoch_definitions}|${frame_epoch_compile_options}|${frame_epoch_link_options}|${qjs_defines}|${QJS_BUILD_LIBC}|${frame_epoch_tools}|${CMAKE_C_COMPILER_ARG1}|${CMAKE_MSVC_RUNTIME_LIBRARY}|${CMAKE_POSITION_INDEPENDENT_CODE}|${QJS_FRAME_DEBUG_SOURCE_ORIGIN}|${QJS_FRAME_DEBUG_BUILD_ORIGIN}"
)
execute_process(
    COMMAND
        "${Python3_EXECUTABLE}" -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/build/native_epoch.py" --source
        "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --configuration
        "${frame_epoch_configuration}"
    RESULT_VARIABLE frame_epoch_result
    OUTPUT_VARIABLE frame_epoch_output
    ERROR_VARIABLE frame_epoch_error)
if(NOT frame_epoch_result EQUAL 0)
    message(
        FATAL_ERROR
            "Cannot prepare a coherent native build epoch:\n${frame_epoch_output}\n${frame_epoch_error}"
    )
endif()
string(STRIP "${frame_epoch_output}" frame_epoch_output)
message(STATUS "${frame_epoch_output}")
# Recreate the build-local tool binding after invalidating an old native epoch.
file(TO_CMAKE_PATH "${QJS_FRAME_OBJDUMP}" frame_objdump_json)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/quickjs-interpreter-tools.json"
     "{\"objdump\":\"${frame_objdump_json}\"}\n")
