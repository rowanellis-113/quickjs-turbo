cmake_minimum_required(VERSION 3.20)
project(ReferenceSlotPublicHost C)
find_package(qjs CONFIG REQUIRED)
add_executable(reference-slot-host main.c)
target_compile_features(reference-slot-host PRIVATE c_std_11)
target_link_libraries(reference-slot-host PRIVATE qjs)
enable_testing()
foreach(mode native off-zero off-one register-c c)
    set(extra "")
    if(mode STREQUAL "off-zero")
        set(extra "QJS_DISABLE_NATIVE_SLOT_STORE=0")
    elseif(mode STREQUAL "off-one")
        set(extra "QJS_DISABLE_NATIVE_SLOT_STORE=1")
    elseif(mode STREQUAL "register-c")
        set(extra "QJS_DISABLE_REGISTER_INTERP=1")
    elseif(mode STREQUAL "c")
        set(extra
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    endif()
    add_test(NAME reference-slot-${mode} COMMAND reference-slot-host)
    set_tests_properties(
        reference-slot-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${extra}" PASS_REGULAR_EXPRESSION
                   "REFERENCE_SLOT_HOST_OK born=256 finalized=256 reentries=128")
endforeach()
