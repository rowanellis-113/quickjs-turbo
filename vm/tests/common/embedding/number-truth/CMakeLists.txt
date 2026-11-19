cmake_minimum_required(VERSION 3.20)
project(QuickJSNumberTruthPublicConsumer C)
find_package(qjs CONFIG REQUIRED)
if(NOT EXISTS "${FRAME_SOURCE_ROOT}/tests/common/native_number_truth.c")
    message(FATAL_ERROR "FRAME_SOURCE_ROOT must name the reviewed source checkout")
endif()
add_executable(interpreter-number-truth-host
               "${FRAME_SOURCE_ROOT}/tests/common/native_number_truth.c")
target_compile_features(interpreter-number-truth-host PRIVATE c_std_11)
target_link_libraries(interpreter-number-truth-host PRIVATE qjs)
enable_testing()
foreach(mode default off off-zero c clean broad-off)
    set(extra "")
    if(mode STREQUAL "off")
        set(extra "QJS_DISABLE_FRAME_NUMBER_TRUTH=1")
    elseif(mode STREQUAL "off-zero")
        set(extra "QJS_DISABLE_FRAME_NUMBER_TRUTH=0")
    elseif(mode STREQUAL "c")
        set(extra
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    elseif(mode STREQUAL "clean")
        set(extra "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
    elseif(mode STREQUAL "broad-off")
        set(extra "QJS_DISABLE_FRAME_TRUTHINESS=1")
    endif()
    add_test(NAME number-truth-${mode} COMMAND interpreter-number-truth-host)
    set_tests_properties(
        number-truth-${mode}
        PROPERTIES
            ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${extra}" PASS_REGULAR_EXPRESSION
            "NUMBER_TRUTH_HOST_OK born=240 finalized=240 collections=240 reentries=240 interrupts=3"
    )
endforeach()
