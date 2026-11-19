# Explicit order is part of the retained backend's layout contract. This file
# does not discover source files by compiler-prefixed glob or object basename.
if(MSVC)
    set(frame_retained_toolchain msvc)
else()
    set(frame_retained_toolchain mingw)
endif()
set(frame_backend_file "${CMAKE_CURRENT_SOURCE_DIR}/src/x86/win64/backend.json")
file(READ "${frame_backend_file}" frame_backend_json)
string(JSON frame_module_count LENGTH "${frame_backend_json}" toolchains
                                      "${frame_retained_toolchain}" modules)
math(EXPR frame_module_last "${frame_module_count}-1")
foreach(frame_index RANGE 0 ${frame_module_last})
    string(
        JSON
        frame_module
        GET
        "${frame_backend_json}"
        toolchains
        "${frame_retained_toolchain}"
        modules
        ${frame_index})
    string(JSON frame_id GET "${frame_module}" id)
    set(frame_module_${frame_id} "${frame_module}")
endforeach()

set(frame_retained_c)
set(frame_retained_asm)
foreach(frame_kind c gas masm)
    string(JSON frame_order_count LENGTH "${frame_backend_json}" toolchains
                                         "${frame_retained_toolchain}" build_order "${frame_kind}")
    if(frame_order_count EQUAL 0)
        continue()
    endif()
    math(EXPR frame_order_last "${frame_order_count}-1")
    foreach(frame_index RANGE 0 ${frame_order_last})
        string(
            JSON
            frame_id
            GET
            "${frame_backend_json}"
            toolchains
            "${frame_retained_toolchain}"
            build_order
            "${frame_kind}"
            ${frame_index})
        string(JSON frame_relative GET "${frame_module_${frame_id}}" source)
        set(frame_source "${CMAKE_CURRENT_SOURCE_DIR}/${frame_relative}")
        if(NOT EXISTS "${frame_source}")
            message(FATAL_ERROR "Missing frame module ${frame_id}: ${frame_relative}")
        endif()
        if(frame_kind STREQUAL "c")
            list(APPEND frame_retained_c "${frame_relative}")
        else()
            list(APPEND frame_retained_asm "${frame_id}")
        endif()
    endforeach()
endforeach()
string(JSON frame_wire_header GET "${frame_module_wire}" generated_private_header)
if(NOT frame_wire_header STREQUAL "interpreter-wire-private.h")
    message(FATAL_ERROR "Unknown generated wire private ABI header: ${frame_wire_header}")
endif()
