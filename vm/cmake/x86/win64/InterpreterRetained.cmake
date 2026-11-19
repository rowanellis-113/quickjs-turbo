include("${CMAKE_CURRENT_LIST_DIR}/InterpreterSources.cmake")
target_sources(qjs PRIVATE ${frame_retained_c})
set_property(
    SOURCE ${frame_retained_c}
    APPEND
    PROPERTY OBJECT_DEPENDS "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-retained-private.h")
if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    set_source_files_properties(${frame_retained_c} PROPERTIES COMPILE_OPTIONS
                                                               "-Wno-unused-function")
endif()
set(frame_shared_asm "${CMAKE_CURRENT_SOURCE_DIR}/asm/x86/win64/common")
file(GLOB frame_shared_asm_dependencies CONFIGURE_DEPENDS "${frame_shared_asm}/*.inc")
foreach(frame_id IN LISTS frame_retained_asm)
    string(JSON frame_relative GET "${frame_module_${frame_id}}" source)
    string(JSON frame_object_relative GET "${frame_module_${frame_id}}" object)
    set(frame_source "${CMAKE_CURRENT_SOURCE_DIR}/${frame_relative}")
    set(frame_object "${CMAKE_CURRENT_BINARY_DIR}/${frame_object_relative}")
    if(frame_relative MATCHES "\\.asm$")
        add_custom_command(
            OUTPUT "${frame_object}"
            COMMAND "${QJS_FRAME_MASM}" /nologo /c "/I${QJS_FRAME_GENERATED_DIR}"
                    "/Fo${frame_object}" "${frame_source}"
            DEPENDS "${frame_source}" "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-private.h"
                    ${frame_shared_asm_dependencies}
            VERBATIM)
    else()
        add_custom_command(
            OUTPUT "${frame_object}"
            COMMAND
                "${QJS_FRAME_AS}" --64 --defsym
                "QJS_FRAME_DIAGNOSTICS=$<IF:$<BOOL:${QJS_INTERP_FRAME_DIAGNOSTICS}>,1,0>" -I
                "${frame_shared_asm}" -I "${QJS_FRAME_GENERATED_DIR}" "${frame_source}" -o
                "${frame_object}"
            DEPENDS "${frame_source}" "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-private.h"
                    ${frame_shared_asm_dependencies}
            VERBATIM)
    endif()
    set_source_files_properties("${frame_object}" PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
    target_sources(qjs PRIVATE "${frame_object}")
endforeach()
get_target_property(frame_retained_sources qjs SOURCES)
list(REMOVE_ITEM frame_retained_sources "${QJS_UPSTREAM_DIR}/libregexp.c" libregexp.c)
set_property(TARGET qjs PROPERTY SOURCES "${frame_retained_sources}")
target_sources(qjs PRIVATE src/common/regexp/libregexp.c)
if(QJS_UPSTREAM_REVISION STREQUAL "bf8988fc401e737f9946cd10a3463b48aab0fd7e")
    # Retained regexp bytecode/case-folding needs the newer Unicode helpers.
    # Isolate them from the pinned core's original Unicode symbols and data.
    set_property(
        SOURCE src/common/regexp/libregexp.c
        APPEND
        PROPERTY COMPILE_DEFINITIONS QJS_FRAME_REGEXP_PRIVATE_UNICODE=1)
    target_sources(qjs PRIVATE src/common/regexp/unicode/regexp-unicode.c
                               src/common/regexp/legacy-0151.c)
endif()
qjs_frame_stage_command(
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/retained_modules.py"
    --source
    "${CMAKE_CURRENT_SOURCE_DIR}"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --archive
    "$<TARGET_FILE:qjs>"
    --toolchain
    "${frame_retained_toolchain}"
    VERBATIM)
# The retained core stage reconstructs its historical helper aliases. Publish
# the independently compiled string owners only after that reconstruction,
# before the enclosing archive stage seals all objects and native unwind.
qjs_frame_stage_command(
    COMMAND
    "${Python3_EXECUTABLE}"
    -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/string-workers.py"
    --source
    "${CMAKE_CURRENT_SOURCE_DIR}"
    --build
    "${CMAKE_CURRENT_BINARY_DIR}"
    --route
    VERBATIM)
