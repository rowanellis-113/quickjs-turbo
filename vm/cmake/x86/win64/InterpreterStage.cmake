# Collect native mutations as one source-epoch stage. An archive-only rebuild
# reuses verified final objects instead of replaying non-idempotent generators.
set_property(GLOBAL PROPERTY QJS_FRAME_STAGE_SCRIPT "")
set_property(GLOBAL PROPERTY QJS_FRAME_STAGE_COUNT 0)

function(qjs_frame_stage_command)
    set(frame_command)
    foreach(frame_argument IN LISTS ARGN)
        if(frame_argument STREQUAL "COMMAND" OR frame_argument STREQUAL "VERBATIM")
            if(frame_command)
                get_property(frame_count GLOBAL PROPERTY QJS_FRAME_STAGE_COUNT)
                math(EXPR frame_count "${frame_count}+1")
                set(frame_text "execute_process(COMMAND")
                foreach(frame_value IN LISTS frame_command)
                    if(frame_value MATCHES "\\]===\\]")
                        message(FATAL_ERROR "Unsupported native command bracket delimiter")
                    endif()
                    string(APPEND frame_text " [===[${frame_value}]===]")
                endforeach()
                string(APPEND frame_text " RESULT_VARIABLE frame_stage_result)\n")
                string(
                    APPEND
                    frame_text
                    "if(NOT \"\${frame_stage_result}\" STREQUAL \"0\")\n  message(FATAL_ERROR \"Native stage command ${frame_count} failed: \${frame_stage_result}\")\nendif()\n"
                )
                set_property(GLOBAL APPEND_STRING PROPERTY QJS_FRAME_STAGE_SCRIPT "${frame_text}")
                set_property(GLOBAL PROPERTY QJS_FRAME_STAGE_COUNT "${frame_count}")
                set(frame_command)
            endif()
        else()
            list(APPEND frame_command "${frame_argument}")
        endif()
    endforeach()
    if(frame_command)
        message(FATAL_ERROR "Native stage command must end with VERBATIM")
    endif()
endfunction()

function(qjs_frame_stage_attach)
    get_property(frame_script GLOBAL PROPERTY QJS_FRAME_STAGE_SCRIPT)
    set(frame_pipeline "${QJS_FRAME_GENERATED_DIR}/quickjs-interpreter-stage.cmake")
    file(
        GENERATE
        OUTPUT "${frame_pipeline}"
        CONTENT "${frame_script}")
    add_custom_command(
        TARGET qjs
        PRE_LINK
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/build/archive_stage.py" --build
            "${CMAKE_CURRENT_BINARY_DIR}" --archive "$<TARGET_FILE:qjs>" --cmake "${CMAKE_COMMAND}"
            --pipeline "${frame_pipeline}"
        VERBATIM)
endfunction()
