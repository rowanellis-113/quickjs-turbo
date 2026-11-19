cmake_minimum_required(VERSION 3.20)
project(ClosureTemplatePublicSafety C)
find_package(qjs CONFIG REQUIRED)
add_executable(closure-owner main.c)
add_executable(closure-fault fault.c)
add_executable(closure-fault-wide fault.c)
add_executable(internal-function-owner internal.c)
target_compile_definitions(closure-fault-wide PRIVATE QJS_TEST_WIDE_CAPTURE=1)
set(closure_targets closure-owner closure-fault closure-fault-wide internal-function-owner)
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    add_executable(closure-adjacent adjacent.c)
    list(APPEND closure_targets closure-adjacent)
endif()
foreach(target ${closure_targets})
    target_compile_features(${target} PRIVATE c_std_11)
    target_link_libraries(${target} PRIVATE qjs)
    if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
        target_compile_options(${target} PRIVATE -g -gdwarf-4)
    endif()
endforeach()

enable_testing()
foreach(disabled 0 1)
    add_test(NAME internal-function-disabled-${disabled} COMMAND internal-function-owner)
    set_tests_properties(
        internal-function-disabled-${disabled}
        PROPERTIES ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256;QJS_DISABLE_INTERNAL_FUNCTION_TEMPLATE=${disabled}"
                   TIMEOUT 60)
endforeach()

foreach(mode default disabled inline-disabled noic register-c c)
    set(extra "")
    if(mode STREQUAL "disabled")
        set(extra "QJS_DISABLE_CLOSURE_SHAPE_TEMPLATE=0")
    elseif(mode STREQUAL "inline-disabled")
        set(extra "QJS_DISABLE_CLOSURE_INLINE_REFS=1")
    elseif(mode STREQUAL "noic")
        set(extra "QJS_DISABLE_PROPERTY_IC=1")
    elseif(mode STREQUAL "register-c")
        set(extra "QJS_DISABLE_REGISTER_INTERP=1")
    elseif(mode STREQUAL "c")
        set(extra
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    endif()
    foreach(target ${closure_targets})
        add_test(NAME ${target}-${mode} COMMAND ${target})
        set_tests_properties(
            ${target}-${mode} PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${extra}"
                                         TIMEOUT 60)
    endforeach()
endforeach()
