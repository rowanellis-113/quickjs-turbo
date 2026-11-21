# Accept previous cache option spellings while exposing the current names.
# The old backend acronym is assembled from separate parts so compatibility
# does not impose the retired terminology on the current source interface.
string(CONCAT qjs_previous_backend "L" "LINT")
foreach(
    qjs_current_option
    QJS_ENABLE_INTERP_FRAME
    QJS_INTERP_FRAME_DIAGNOSTICS
    QJS_INTERP_FRAME_REGISTER_ABI
    QJS_INTERP_FRAME_INTERNAL_ENTRY
    QJS_INTERP_FRAME_TAIL_ENTRY
    QJS_INTERP_FRAME_INLINE_WINDOW
    QJS_INTERP_FRAME_ITERATOR_LITERAL
    QJS_INTERP_FRAME_GLOBAL_BINDING
    QJS_INTERP_FRAME_LEAF_ENTRY)
    string(REPLACE "INTERP" "${qjs_previous_backend}" qjs_previous_option "${qjs_current_option}")
    if(DEFINED ${qjs_previous_option})
        if(DEFINED ${qjs_current_option})
            if(${qjs_previous_option})
                set(qjs_previous_value TRUE)
            else()
                set(qjs_previous_value FALSE)
            endif()
            if(${qjs_current_option})
                set(qjs_current_value TRUE)
            else()
                set(qjs_current_value FALSE)
            endif()
            if(NOT qjs_previous_value STREQUAL qjs_current_value)
                message(
                    FATAL_ERROR "Conflicting current and previous values for ${qjs_current_option}")
            endif()
        else()
            set(${qjs_current_option}
                "${${qjs_previous_option}}"
                CACHE BOOL "Interpreter configuration compatibility")
        endif()
    endif()
endforeach()

# Frame support is optional. A normal upstream build requires no Python, MASM
# or binutils. AUTO falls back before adding objects, flags or custom commands;
# WIN64 is strict, so an explicitly requested backend cannot silently disappear.
if(NOT DEFINED QJS_FRAME_BACKEND)
    if(QJS_ENABLE_INTERP_FRAME)
        set(QJS_FRAME_BACKEND
            WIN64
            CACHE STRING "Frame backend: PORTABLE, AUTO, WIN64 or LINUX_X86_64")
    else()
        set(QJS_FRAME_BACKEND
            PORTABLE
            CACHE STRING "Frame backend: PORTABLE, AUTO, WIN64 or LINUX_X86_64")
    endif()
endif()
set_property(
    CACHE QJS_FRAME_BACKEND
    PROPERTY STRINGS
             PORTABLE
             AUTO
             WIN64
             LINUX_X86_64
             LINUX_AARCH64
             MACOS_X86_64)
string(TOUPPER "${QJS_FRAME_BACKEND}" frame_requested)
if(NOT frame_requested MATCHES "^(PORTABLE|AUTO|WIN64|LINUX_X86_64|LINUX_AARCH64|MACOS_X86_64)$")
    message(
        FATAL_ERROR
            "QJS_FRAME_BACKEND must be PORTABLE, AUTO, WIN64, LINUX_X86_64, LINUX_AARCH64 or MACOS_X86_64"
    )
endif()

if(frame_requested STREQUAL "LINUX_AARCH64")
    include("${CMAKE_CURRENT_LIST_DIR}/../arm64/InterpreterOptions.cmake")
    return()
endif()

if(frame_requested STREQUAL "MACOS_X86_64"
   OR (frame_requested STREQUAL "AUTO"
       AND CMAKE_SYSTEM_NAME STREQUAL "Darwin"
       AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64)$"))
    include("${CMAKE_CURRENT_LIST_DIR}/../x86/macos/InterpreterOptions.cmake")
    return()
endif()

if(frame_requested STREQUAL "LINUX_X86_64"
   OR (frame_requested STREQUAL "AUTO" AND CMAKE_SYSTEM_NAME STREQUAL "Linux"))
    include("${CMAKE_CURRENT_LIST_DIR}/../x86/linux/InterpreterOptions.cmake")
    return()
endif()

include("${CMAKE_CURRENT_LIST_DIR}/../x86/win64/InterpreterOptions.cmake")
if(NOT QJS_ENABLE_INTERP_FRAME)
    # Normal variables shadow cached feature preferences for a coherent fallback.
    foreach(
        frame_option
        DIAGNOSTICS
        REGISTER_ABI
        INTERNAL_ENTRY
        TAIL_ENTRY
        INLINE_WINDOW
        ITERATOR_LITERAL
        GLOBAL_BINDING
        LEAF_ENTRY)
        set(QJS_INTERP_FRAME_${frame_option} OFF)
    endforeach()
endif()
message(
    STATUS "QuickJS frame backend: ${QJS_FRAME_BACKEND_EFFECTIVE} (requested ${frame_requested})")
set(frame_fallback_reason "")
if(frame_requested STREQUAL "AUTO" AND NOT QJS_ENABLE_INTERP_FRAME)
    set(frame_fallback_reason "${frame_unavailable}")
endif()
file(
    WRITE "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
    "{\"schema\":1,\"requested\":\"${frame_requested}\",\"effective\":\"${QJS_FRAME_BACKEND_EFFECTIVE}\",\"fallback_reason\":\"${frame_fallback_reason}\"}\n"
)
