cmake_minimum_required(VERSION 3.20)
project(QuickJSArgumentConstructOwnership C)
find_package(qjs CONFIG REQUIRED)
add_executable(interpreter-construct-host main.c)
target_compile_features(interpreter-construct-host PRIVATE c_std_11)
target_link_libraries(interpreter-construct-host PRIVATE qjs)
enable_testing()
foreach(mode native disabled noic register-c c)
    set(extra "")
    if(mode STREQUAL "disabled")
        set(extra "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=0")
    elseif(mode STREQUAL "noic")
        set(extra "QJS_DISABLE_PROPERTY_IC=1")
    elseif(mode STREQUAL "register-c")
        set(extra "QJS_DISABLE_REGISTER_INTERP=1")
    elseif(mode STREQUAL "c")
        set(extra
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    endif()
    add_test(NAME construct-ownership-${mode} COMMAND interpreter-construct-host)
    set_tests_properties(construct-ownership-${mode}
                         PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${extra}")
endforeach()

foreach(mode arguments-off arguments-copy)
    add_test(NAME construct-ownership-${mode} COMMAND interpreter-construct-host)
endforeach()
set_tests_properties(
    construct-ownership-arguments-off
    PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
set_tests_properties(
    construct-ownership-arguments-copy
    PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;QJS_DISABLE_FRAME_ARGUMENTS_BORROW=0")

add_executable(interpreter-argument-crossrealm crossrealm.c)
target_compile_features(interpreter-argument-crossrealm PRIVATE c_std_11)
target_link_libraries(interpreter-argument-crossrealm PRIVATE qjs)
foreach(
    mode
    native
    disabled
    noic
    register-c
    c
    arguments-off
    arguments-copy)
    add_test(NAME argument-crossrealm-${mode} COMMAND interpreter-argument-crossrealm)
    get_test_property(construct-ownership-${mode} ENVIRONMENT argument_mode_environment)
    set_tests_properties(argument-crossrealm-${mode} PROPERTIES ENVIRONMENT
                                                                "${argument_mode_environment}")
endforeach()
