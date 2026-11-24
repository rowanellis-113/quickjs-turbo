# Public API owner/quota/reentry checks have no architecture-specific gates.
find_package(Threads REQUIRED)
add_executable(aarch64-c-invoke tests/common/linux/native_linux_c_invoke.c)
target_link_libraries(aarch64-c-invoke PRIVATE qjs)
foreach(
    mode
    native
    zero
    one
    shared-off
    direct-off
    retained
    register-off
    legacy)
    add_test(NAME interpreter-aarch64-c-invoke-${mode} COMMAND aarch64-c-invoke)
    set_tests_properties(interpreter-aarch64-c-invoke-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                         "LINUX_C_INVOKE_ABI_OK")
endforeach()
set_tests_properties(interpreter-aarch64-c-invoke-zero PROPERTIES ENVIRONMENT
                                                                  "QJS_DISABLE_C_INVOKE=0")
set_tests_properties(interpreter-aarch64-c-invoke-one PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_C_INVOKE=1")
set_tests_properties(interpreter-aarch64-c-invoke-shared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(interpreter-aarch64-c-invoke-direct-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=0")
set_tests_properties(interpreter-aarch64-c-invoke-retained PROPERTIES ENVIRONMENT
                                                                      "QJS_RETAIN_SCOPED_HOST=0")
set_tests_properties(interpreter-aarch64-c-invoke-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_tests_properties(
    interpreter-aarch64-c-invoke-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
add_executable(aarch64-c-entry tests/common/linux/native_linux_c_entry.c)
target_compile_options(aarch64-c-entry PRIVATE -UNDEBUG)
target_link_libraries(aarch64-c-entry PRIVATE qjs)
add_test(NAME interpreter-aarch64-c-entry-native COMMAND aarch64-c-entry)
set_tests_properties(interpreter-aarch64-c-entry-native PROPERTIES PASS_REGULAR_EXPRESSION
                                                                   "LINUX_C_ENTRY_OK")
foreach(
    component
    NATIVE_NUMERIC_INVOKE
    NUMERIC_TRAMPOLINE
    NATIVE_SLICE
    NATIVE_FRAME_ARENA
    NATIVE_FRAME_REUSE
    NATIVE_FRAME_LIFETIME
    NATIVE_CALL_LINK
    NATIVE_VM_BRIDGE
    NATIVE_NUMBER_FRAME
    C_INVOKE
    SHARED_ENTRY
    REGISTER_INTERP
    INTERP_FRAME
    DIRECT_HOST_CALL)
    foreach(value 0 1)
        string(TOLOWER "${component}" label)
        add_test(NAME interpreter-aarch64-c-entry-${label}-${value} COMMAND aarch64-c-entry)
        set_tests_properties(
            interpreter-aarch64-c-entry-${label}-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_C_ENTRY_OK" TIMEOUT 300)
    endforeach()
endforeach()
add_test(NAME interpreter-aarch64-c-entry-numeric-both-off COMMAND aarch64-c-entry)
set_tests_properties(
    interpreter-aarch64-c-entry-numeric-both-off
    PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NUMERIC_INVOKE=0;QJS_DISABLE_NUMERIC_TRAMPOLINE=0"
               PASS_REGULAR_EXPRESSION "LINUX_C_ENTRY_OK")
foreach(mode native off)
    add_test(NAME interpreter-aarch64-c-entry-oom-${mode} COMMAND aarch64-c-entry oom)
    set_tests_properties(interpreter-aarch64-c-entry-oom-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                            "LINUX_C_ENTRY_OOM_OK")
endforeach()
set_tests_properties(interpreter-aarch64-c-entry-oom-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_NATIVE_SLICE=0")
add_executable(aarch64-dense-pop-leaf tests/common/native_dense_pop_leaf.c)
target_compile_definitions(aarch64-dense-pop-leaf PRIVATE LEAF_DIAGNOSTIC=0 LEAF_HAS_ARGC_WINDOW=0)
target_link_libraries(aarch64-dense-pop-leaf PRIVATE qjs)
foreach(mode native leaf-zero leaf-one pop-zero pop-one c-invoke-off)
    add_test(NAME interpreter-aarch64-dense-pop-leaf-${mode} COMMAND aarch64-dense-pop-leaf)
    set_tests_properties(interpreter-aarch64-dense-pop-leaf-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "DENSE_POP_LEAF_PASS" TIMEOUT 300)
endforeach()
set_tests_properties(interpreter-aarch64-dense-pop-leaf-leaf-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DENSE_ARRAY_POP_LEAF=0")
set_tests_properties(interpreter-aarch64-dense-pop-leaf-leaf-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DENSE_ARRAY_POP_LEAF=1")
set_tests_properties(interpreter-aarch64-dense-pop-leaf-pop-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DENSE_ARRAY_POP=0")
set_tests_properties(interpreter-aarch64-dense-pop-leaf-pop-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DENSE_ARRAY_POP=1")
set_tests_properties(interpreter-aarch64-dense-pop-leaf-c-invoke-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
# Complete GNU global hints: inherited lifecycle,activation collisions,public
# ownership/realm/GC/interrupt and warmed allocator fault recovery.
add_executable(aarch64-global-api tests/common/linux/native_linux_global_bindings.c)
target_compile_features(aarch64-global-api PRIVATE c_std_11)
target_compile_options(aarch64-global-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(aarch64-global-api PRIVATE qjs Threads::Threads)
foreach(
    mode
    on
    global-zero
    global-one
    undefined-zero
    undefined-one
    large-zero
    large-one
    publish-zero
    property-zero
    frame-zero
    register-zero)
    add_test(NAME interpreter-aarch64-global-family-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_global_bindings.js")
    set_tests_properties(
        interpreter-aarch64-global-family-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_BINDINGS_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(mode on global-zero property-zero publish-zero frame-zero)
    add_test(NAME interpreter-aarch64-global-family-inherited-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_global_binding.js")
    set_tests_properties(
        interpreter-aarch64-global-family-inherited-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "BINDING_RELINK_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(
    mode
    on
    global-zero
    undefined-zero
    large-zero
    publish-zero
    property-zero
    frame-zero)
    add_test(NAME interpreter-aarch64-global-family-api-${mode} COMMAND aarch64-global-api)
    set_tests_properties(
        interpreter-aarch64-global-family-api-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_BINDINGS_PUBLIC_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(mode on global publish frame)
    add_test(NAME interpreter-aarch64-global-family-oom-${mode} COMMAND aarch64-global-api oom)
    set_tests_properties(
        interpreter-aarch64-global-family-oom-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_BINDINGS_OOM_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 180)
endforeach()
foreach(
    pair
    "global;QJS_DISABLE_FRAME_GLOBAL_BINDING"
    "undefined;QJS_DISABLE_FRAME_GLOBAL_UNDEFINED"
    "large;QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS"
    "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH"
    "property;QJS_DISABLE_PROPERTY_IC"
    "frame;QJS_DISABLE_INTERP_FRAME"
    "register;QJS_DISABLE_REGISTER_INTERP")
    list(GET pair 0 name)
    list(GET pair 1 control)
    foreach(kind "" inherited- api-)
        foreach(value zero one)
            set(test_name interpreter-aarch64-global-family-${kind}${name}-${value})
            if(TEST ${test_name})
                if(value STREQUAL "zero")
                    set(number 0)
                else()
                    set(number 1)
                endif()
                set_property(
                    TEST ${test_name}
                    APPEND
                    PROPERTY ENVIRONMENT "${control}=${number}")
            endif()
        endforeach()
    endforeach()
    if(TEST interpreter-aarch64-global-family-oom-${name})
        set_property(
            TEST interpreter-aarch64-global-family-oom-${name}
            APPEND
            PROPERTY ENVIRONMENT "${control}=0")
    endif()
endforeach()

foreach(mode on off-zero off-one)
    add_test(NAME interpreter-aarch64-global-cells-${mode}
             COMMAND qjs_exe
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_global_cells.js")
    set_tests_properties(interpreter-aarch64-global-cells-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_CELLS_OK")
endforeach()
set_tests_properties(interpreter-aarch64-global-cells-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_BINDING_CELL=0")
set_tests_properties(interpreter-aarch64-global-cells-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_BINDING_CELL=1")

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-global-bindings tests/arm64/global-bindings.c)
    target_include_directories(aarch64-global-bindings PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-global-bindings PRIVATE qjs)
    foreach(
        mode
        native
        global-zero
        global-one
        cell-zero
        cell-one
        symbol-zero
        symbol-one
        reference-zero
        reference-one
        undefined-zero
        undefined-one
        large-zero
        large-one
        property-zero
        property-one
        publish-zero
        hints-off
        own-off
        register-off
        legacy)
        add_test(NAME interpreter-aarch64-global-paths-${mode} COMMAND aarch64-global-bindings)
        set_tests_properties(
            interpreter-aarch64-global-paths-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_GLOBAL_BINDINGS_OK" TIMEOUT 300)
    endforeach()
    foreach(
        pair
        "global;QJS_DISABLE_FRAME_GLOBAL_BINDING"
        "cell;QJS_DISABLE_FRAME_BINDING_CELL"
        "symbol;QJS_DISABLE_SYMBOL_CASE"
        "reference;QJS_DISABLE_FRAME_REFERENCE_EQUALITY"
        "undefined;QJS_DISABLE_FRAME_GLOBAL_UNDEFINED"
        "large;QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS"
        "property;QJS_DISABLE_PROPERTY_IC")
        list(GET pair 0 label)
        list(GET pair 1 control)
        set_tests_properties(interpreter-aarch64-global-paths-${label}-zero
                             PROPERTIES ENVIRONMENT "${control}=0")
        set_tests_properties(interpreter-aarch64-global-paths-${label}-one
                             PROPERTIES ENVIRONMENT "${control}=1")
    endforeach()
    set_tests_properties(interpreter-aarch64-global-paths-publish-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-global-paths-hints-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=0")
    set_tests_properties(interpreter-aarch64-global-paths-own-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_OWN_BYTECODE=0")
    set_tests_properties(interpreter-aarch64-global-paths-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-global-paths-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    add_executable(aarch64-reference-stores tests/arm64/reference-stores.c)
    target_include_directories(aarch64-reference-stores PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-reference-stores PRIVATE qjs)
    foreach(
        mode
        native
        slot-zero
        slot-one
        store-zero
        store-one
        core-zero
        core-one
        base-off
        deferred-off
        hints-off
        primitives-off
        prototypes-off
        register-off
        legacy)
        add_test(NAME interpreter-aarch64-reference-stores-${mode} COMMAND aarch64-reference-stores)
        set_tests_properties(
            interpreter-aarch64-reference-stores-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_REFERENCE_STORES_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-reference-stores-slot-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=0")
    set_tests_properties(interpreter-aarch64-reference-stores-slot-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=1")
    set_tests_properties(interpreter-aarch64-reference-stores-store-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_STORES=0")
    set_tests_properties(interpreter-aarch64-reference-stores-store-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_STORES=1")
    set_tests_properties(interpreter-aarch64-reference-stores-core-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-reference-stores-core-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
    set_tests_properties(interpreter-aarch64-reference-stores-base-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-reference-stores-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-reference-stores-hints-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=0")
    set_tests_properties(interpreter-aarch64-reference-stores-primitives-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=0")
    set_tests_properties(interpreter-aarch64-reference-stores-prototypes-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES=0")
    set_tests_properties(interpreter-aarch64-reference-stores-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-reference-stores-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    foreach(mode native slot-off store-off deferred-off register-off legacy)
        add_test(NAME interpreter-aarch64-reference-stores-oom-${mode}
                 COMMAND aarch64-reference-stores oom)
        set_tests_properties(
            interpreter-aarch64-reference-stores-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_REFERENCE_STORES_OOM_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-reference-stores-oom-slot-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=0")
    set_tests_properties(interpreter-aarch64-reference-stores-oom-store-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_STORES=0")
    set_tests_properties(interpreter-aarch64-reference-stores-oom-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-reference-stores-oom-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-reference-stores-oom-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    add_executable(aarch64-property-prototypes tests/arm64/property-prototypes.c)
    target_include_directories(aarch64-property-prototypes PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-property-prototypes PRIVATE qjs Threads::Threads)
    foreach(
        mode
        native
        off-zero
        off-one
        cache-zero
        cache-one
        persist-zero
        persist-one
        direct-zero
        direct-one
        core-zero
        core-one
        base-off
        deferred-off
        primitives-off
        hints-off
        own-off
        register-off
        legacy)
        add_test(NAME interpreter-aarch64-property-prototypes-${mode}
                 COMMAND aarch64-property-prototypes)
        set_tests_properties(
            interpreter-aarch64-property-prototypes-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_PROTOTYPES_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-property-prototypes-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-off-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES=1")
    set_tests_properties(interpreter-aarch64-property-prototypes-cache-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_CACHE=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-cache-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_CACHE=1")
    set_tests_properties(interpreter-aarch64-property-prototypes-persist-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_PERSIST=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-persist-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_PERSIST=1")
    set_tests_properties(interpreter-aarch64-property-prototypes-direct-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_DIRECT=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-direct-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_DIRECT=1")
    set_tests_properties(interpreter-aarch64-property-prototypes-core-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-core-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
    set_tests_properties(interpreter-aarch64-property-prototypes-base-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-primitives-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-hints-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-own-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_OWN_BYTECODE=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-property-prototypes-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    foreach(mode native cache-off persist-off direct-off off legacy)
        add_test(NAME interpreter-aarch64-property-prototypes-threads-${mode}
                 COMMAND aarch64-property-prototypes threads)
        set_tests_properties(
            interpreter-aarch64-property-prototypes-threads-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_PROTOTYPES_THREADS_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-property-prototypes-threads-cache-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_CACHE=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-threads-persist-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_PERSIST=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-threads-direct-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_DIRECT=0")
    set_tests_properties(interpreter-aarch64-property-prototypes-threads-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES=0")
    set_tests_properties(
        interpreter-aarch64-property-prototypes-threads-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    add_executable(aarch64-property-hints tests/arm64/property-hints.c)
    target_include_directories(aarch64-property-hints PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-property-hints PRIVATE qjs)
    foreach(
        mode
        native
        own-zero
        own-one
        target-zero
        target-one
        local-zero
        local-one
        core-zero
        core-one
        base-off
        deferred-off
        register-off
        legacy)
        add_test(NAME interpreter-aarch64-property-hints-${mode} COMMAND aarch64-property-hints)
        set_tests_properties(
            interpreter-aarch64-property-hints-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_HINTS_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-property-hints-own-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_OWN_BYTECODE=0")
    set_tests_properties(interpreter-aarch64-property-hints-own-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_OWN_BYTECODE=1")
    set_tests_properties(interpreter-aarch64-property-hints-target-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=0")
    set_tests_properties(interpreter-aarch64-property-hints-target-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=1")
    set_tests_properties(interpreter-aarch64-property-hints-local-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LOCAL_FIELD=0")
    set_tests_properties(interpreter-aarch64-property-hints-local-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LOCAL_FIELD=1")
    set_tests_properties(interpreter-aarch64-property-hints-core-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-property-hints-core-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
    set_tests_properties(interpreter-aarch64-property-hints-base-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-property-hints-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-property-hints-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-property-hints-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    foreach(mode own-off-core-off target-off-core-off)
        add_test(NAME interpreter-aarch64-property-hints-${mode} COMMAND aarch64-property-hints)
        set_tests_properties(
            interpreter-aarch64-property-hints-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_HINTS_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(
        interpreter-aarch64-property-hints-own-off-core-off
        PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_OWN_BYTECODE=0;QJS_DISABLE_PROPERTY_IC=0")
    set_tests_properties(
        interpreter-aarch64-property-hints-target-off-core-off
        PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_HINTS=0;QJS_DISABLE_PROPERTY_IC=0")
    foreach(mode reserve original)
        add_test(NAME interpreter-aarch64-property-hints-oom-${mode} COMMAND aarch64-property-hints
                                                                             oom-${mode})
        set_tests_properties(
            interpreter-aarch64-property-hints-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_HINTS_OOM_OK" TIMEOUT 300)
    endforeach()
    add_executable(aarch64-property-hints-precrt tests/arm64/property-hints.c)
    target_compile_definitions(aarch64-property-hints-precrt PRIVATE ARM_OWN_EARLY_PRODUCER=1)
    target_include_directories(aarch64-property-hints-precrt PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-property-hints-precrt PRIVATE qjs)
    add_test(NAME interpreter-aarch64-property-hints-precrt COMMAND aarch64-property-hints-precrt)
    set_tests_properties(
        interpreter-aarch64-property-hints-precrt
        PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_HINTS_PRECRT_OK" TIMEOUT 300)
    add_executable(aarch64-property-primitives tests/arm64/property-primitives.c)
    target_include_directories(aarch64-property-primitives PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-property-primitives PRIVATE qjs)
    foreach(
        mode
        native
        off-zero
        off-one
        proto-zero
        proto-one
        number-zero
        number-one
        length-zero
        length-one
        stack
        transient
        geometry
        view-off
        invoke-off
        deferred-off
        return-off
        direct-off
        shared-off
        retained
        register-off
        legacy
        base-off
        core-off)
        add_test(
            NAME interpreter-aarch64-property-primitives-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_property_primitives.py" --exe
                "$<TARGET_FILE:aarch64-property-primitives>" --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-aarch64-property-primitives-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_PRIMITIVES_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-property-primitives-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=0")
    set_tests_properties(interpreter-aarch64-property-primitives-off-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=1")
    set_tests_properties(interpreter-aarch64-property-primitives-proto-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_CACHE=0")
    set_tests_properties(interpreter-aarch64-property-primitives-proto-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROTO_LOAD_CACHE=1")
    set_tests_properties(interpreter-aarch64-property-primitives-number-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NUMBER_PROPERTY_FAST=0")
    set_tests_properties(interpreter-aarch64-property-primitives-number-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NUMBER_PROPERTY_FAST=1")
    set_tests_properties(interpreter-aarch64-property-primitives-length-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_LENGTH=0")
    set_tests_properties(interpreter-aarch64-property-primitives-length-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_LENGTH=1")
    set_tests_properties(interpreter-aarch64-property-primitives-stack
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_ARENA=0")
    set_tests_properties(interpreter-aarch64-property-primitives-transient
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_REUSE=0")
    set_tests_properties(interpreter-aarch64-property-primitives-geometry
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_LIFETIME=0")
    set_tests_properties(interpreter-aarch64-property-primitives-view-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLICE=0")
    set_tests_properties(interpreter-aarch64-property-primitives-invoke-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(interpreter-aarch64-property-primitives-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-property-primitives-return-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
    set_tests_properties(interpreter-aarch64-property-primitives-direct-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=0")
    set_tests_properties(interpreter-aarch64-property-primitives-shared-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
    set_tests_properties(interpreter-aarch64-property-primitives-retained
                         PROPERTIES ENVIRONMENT "QJS_RETAIN_SCOPED_HOST=0")
    set_tests_properties(interpreter-aarch64-property-primitives-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-property-primitives-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    set_tests_properties(interpreter-aarch64-property-primitives-base-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
    set_tests_properties(interpreter-aarch64-property-primitives-core-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
    foreach(mode native primitives-off invoke-off legacy)
        add_test(
            NAME interpreter-aarch64-property-primitives-oom-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_property_primitives.py" --exe
                "$<TARGET_FILE:aarch64-property-primitives>" --mode oom --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-aarch64-property-primitives-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_PRIMITIVES_OOM_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-property-primitives-oom-primitives-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=0")
    set_tests_properties(interpreter-aarch64-property-primitives-oom-invoke-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(
        interpreter-aarch64-property-primitives-oom-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    if(QJS_PROPERTY_IC)
        add_executable(aarch64-property-ic tests/arm64/property-ic.c)
        target_include_directories(aarch64-property-ic PRIVATE "${qjs_arm_vm_dir}")
        target_link_libraries(aarch64-property-ic PRIVATE qjs)
        foreach(
            mode
            native
            off-zero
            off-one
            core-zero
            core-one
            adaptive-off
            weak-off
            deferred-off
            return-off
            invoke-off
            register-off
            legacy)
            add_test(NAME interpreter-aarch64-property-ic-${mode} COMMAND aarch64-property-ic)
            set_tests_properties(
                interpreter-aarch64-property-ic-${mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PROPERTY_IC_OK" TIMEOUT 300)
        endforeach()
        set_tests_properties(interpreter-aarch64-property-ic-off-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
        set_tests_properties(interpreter-aarch64-property-ic-off-one
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=1")
        set_tests_properties(interpreter-aarch64-property-ic-core-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
        set_tests_properties(interpreter-aarch64-property-ic-core-one
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
        set_tests_properties(interpreter-aarch64-property-ic-adaptive-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_IC_ADAPTIVE_WAYS=0")
        set_tests_properties(interpreter-aarch64-property-ic-weak-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC_WEAK_PROTO=0")
        set_tests_properties(interpreter-aarch64-property-ic-deferred-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
        set_tests_properties(interpreter-aarch64-property-ic-return-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
        set_tests_properties(interpreter-aarch64-property-ic-invoke-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
        set_tests_properties(interpreter-aarch64-property-ic-register-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
        set_tests_properties(
            interpreter-aarch64-property-ic-legacy
            PROPERTIES
                ENVIRONMENT
                "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
        )
    endif()
    add_executable(aarch64-c-return tests/arm64/c-return.c)
    target_link_libraries(aarch64-c-return PRIVATE qjs)
    foreach(
        mode
        native
        return-zero
        return-one
        invoke-zero
        invoke-one
        shared-off
        retained
        deferred-off
        direct-off
        register-off
        legacy)
        add_test(
            NAME interpreter-aarch64-c-return-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_c_return.py" --exe
                "$<TARGET_FILE:aarch64-c-return>" --runner ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(interpreter-aarch64-c-return-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_C_RETURN_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-c-return-return-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
    set_tests_properties(interpreter-aarch64-c-return-return-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=1")
    set_tests_properties(interpreter-aarch64-c-return-invoke-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(interpreter-aarch64-c-return-invoke-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=1")
    set_tests_properties(interpreter-aarch64-c-return-shared-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
    set_tests_properties(interpreter-aarch64-c-return-retained
                         PROPERTIES ENVIRONMENT "QJS_RETAIN_SCOPED_HOST=0")
    set_tests_properties(interpreter-aarch64-c-return-deferred-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-c-return-direct-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=0")
    set_tests_properties(interpreter-aarch64-c-return-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-c-return-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    foreach(mode native return-off invoke-off legacy)
        add_test(
            NAME interpreter-aarch64-c-return-oom-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_c_return.py" --exe
                "$<TARGET_FILE:aarch64-c-return>" --mode oom --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-aarch64-c-return-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_C_RETURN_OOM_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-c-return-oom-return-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
    set_tests_properties(interpreter-aarch64-c-return-oom-invoke-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(
        interpreter-aarch64-c-return-oom-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    add_executable(aarch64-c-entry-window tests/arm64/c-entry-window.c)
    target_link_libraries(aarch64-c-entry-window PRIVATE qjs)
    foreach(
        mode
        native
        geometry
        transient
        stack
        c-off
        slice-off
        register-off
        legacy)
        add_test(NAME interpreter-aarch64-c-entry-window-${mode} COMMAND aarch64-c-entry-window)
        set_tests_properties(interpreter-aarch64-c-entry-window-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_C_WINDOW_OK")
    endforeach()
    set_tests_properties(interpreter-aarch64-c-entry-window-geometry
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_LIFETIME=0")
    set_tests_properties(interpreter-aarch64-c-entry-window-transient
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_REUSE=0")
    set_tests_properties(interpreter-aarch64-c-entry-window-stack
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_ARENA=0")
    set_tests_properties(interpreter-aarch64-c-entry-window-c-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(interpreter-aarch64-c-entry-window-slice-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLICE=0")
    set_tests_properties(interpreter-aarch64-c-entry-window-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-c-entry-window-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    add_executable(aarch64-dense-pop-observer tests/arm64/dense-pop-observer.c)
    target_compile_options(aarch64-dense-pop-observer PRIVATE -UNDEBUG)
    target_compile_definitions(aarch64-dense-pop-observer PRIVATE LEAF_DIAGNOSTIC=0
                                                                  LEAF_HAS_ARGC_WINDOW=0)
    target_link_libraries(aarch64-dense-pop-observer PRIVATE qjs)
    foreach(mode native leaf-zero leaf-one pop-zero pop-one c-invoke-off)
        add_test(NAME interpreter-aarch64-dense-pop-observer-${mode}
                 COMMAND aarch64-dense-pop-observer)
        get_test_property(interpreter-aarch64-dense-pop-leaf-${mode} ENVIRONMENT mode_env)
        if(mode_env)
            set_tests_properties(interpreter-aarch64-dense-pop-observer-${mode}
                                 PROPERTIES ENVIRONMENT "${mode_env}")
        endif()
        set_tests_properties(interpreter-aarch64-dense-pop-observer-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_DENSE_POP_PATH_OK")
    endforeach()
    add_executable(aarch64-c-invoke-observer tests/arm64/c-invoke-observer.c)
    target_compile_options(aarch64-c-invoke-observer PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-c-invoke-observer PRIVATE qjs)
    foreach(
        mode
        native
        zero
        one
        shared-off
        direct-off
        retained
        register-off
        legacy)
        add_test(
            NAME interpreter-aarch64-c-invoke-observer-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_c_invoke.py" --exe
                "$<TARGET_FILE:aarch64-c-invoke-observer>" --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        get_test_property(interpreter-aarch64-c-invoke-${mode} ENVIRONMENT mode_env)
        if(mode_env)
            set_tests_properties(interpreter-aarch64-c-invoke-observer-${mode}
                                 PROPERTIES ENVIRONMENT "${mode_env}")
        endif()
        set_tests_properties(interpreter-aarch64-c-invoke-observer-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_C_INVOKE_UNWIND_OK")
    endforeach()
    add_executable(aarch64-c-entry-observer tests/arm64/c-entry-observer.c)
    target_compile_options(aarch64-c-entry-observer PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-c-entry-observer PRIVATE qjs)
    foreach(
        mode
        native
        numeric-off
        trampoline-off
        both-off
        arena-off
        reuse-off
        geometry-off
        slice-off
        number-off
        c-off
        shared-off
        retained
        register-off)
        add_test(NAME interpreter-aarch64-c-entry-observer-${mode} COMMAND aarch64-c-entry-observer)
        set_tests_properties(
            interpreter-aarch64-c-entry-observer-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_C_ENTRY_COUNTS_OK" TIMEOUT 300)
    endforeach()
    set_tests_properties(interpreter-aarch64-c-entry-observer-numeric-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NUMERIC_INVOKE=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-trampoline-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NUMERIC_TRAMPOLINE=0")
    set_tests_properties(
        interpreter-aarch64-c-entry-observer-both-off
        PROPERTIES ENVIRONMENT
                   "QJS_DISABLE_NATIVE_NUMERIC_INVOKE=0;QJS_DISABLE_NUMERIC_TRAMPOLINE=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-arena-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_ARENA=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-reuse-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_REUSE=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-geometry-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_LIFETIME=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-slice-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLICE=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-number-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NUMBER_FRAME=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-c-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-shared-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-retained
                         PROPERTIES ENVIRONMENT "QJS_RETAIN_SCOPED_HOST=0")
    set_tests_properties(interpreter-aarch64-c-entry-observer-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
endif()
add_test(
    NAME interpreter-aarch64-publication-macros
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_publication.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}")
set_tests_properties(interpreter-aarch64-publication-macros
                     PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PUBLICATION_MACROS_OK")
add_executable(aarch64-publication-api tests/common/linux/native_linux_publication.c)
target_compile_options(aarch64-publication-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(aarch64-publication-api PRIVATE qjs)
foreach(
    mode
    native
    zero
    one
    register-off
    legacy
    owned-off
    shared-off)
    add_test(NAME interpreter-aarch64-publication-js-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_publication.js")
    add_test(NAME interpreter-aarch64-publication-api-${mode} COMMAND aarch64-publication-api)
    add_test(NAME interpreter-aarch64-publication-oom-${mode} COMMAND aarch64-publication-api oom)
    foreach(kind js api oom)
        set_tests_properties(interpreter-aarch64-publication-${kind}-${mode}
                             PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 300)
        if(mode STREQUAL "zero" OR mode STREQUAL "one")
            if(mode STREQUAL "zero")
                set(value 0)
            else()
                set(value 1)
            endif()
            set_property(
                TEST interpreter-aarch64-publication-${kind}-${mode}
                APPEND
                PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=${value}")
        elseif(mode STREQUAL "register-off")
            set_property(
                TEST interpreter-aarch64-publication-${kind}-${mode}
                APPEND
                PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
        elseif(mode STREQUAL "legacy")
            set_property(
                TEST interpreter-aarch64-publication-${kind}-${mode}
                APPEND
                PROPERTY
                    ENVIRONMENT
                    "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
            )
        elseif(mode STREQUAL "owned-off")
            set_property(
                TEST interpreter-aarch64-publication-${kind}-${mode}
                APPEND
                PROPERTY ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=0")
        elseif(mode STREQUAL "shared-off")
            set_property(
                TEST interpreter-aarch64-publication-${kind}-${mode}
                APPEND
                PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
        endif()
    endforeach()
    set_tests_properties(interpreter-aarch64-publication-js-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_PUBLICATION_OK")
    set_tests_properties(interpreter-aarch64-publication-api-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_PUBLICATION_API_OK")
    set_tests_properties(interpreter-aarch64-publication-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_PUBLICATION_OOM_OK")
endforeach()
if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-publication tests/arm64/publication.c)
    target_link_libraries(aarch64-publication PRIVATE qjs)
    foreach(mode native zero one register-off legacy)
        add_test(NAME interpreter-aarch64-publication-path-${mode} COMMAND aarch64-publication
                                                                           ${mode})
        set_tests_properties(
            interpreter-aarch64-publication-path-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "AARCH64_PUBLICATION_OK")
    endforeach()
    set_property(
        TEST interpreter-aarch64-publication-path-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_property(
        TEST interpreter-aarch64-publication-path-one
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
    set_property(
        TEST interpreter-aarch64-publication-path-register-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_property(
        TEST interpreter-aarch64-publication-path-legacy
        APPEND
        PROPERTY
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
endif()
foreach(
    large_mode
    native
    enabled
    enabled-zero
    enable-disable
    disabled
    zero
    long-off
    c
    bypass-off
    bypass-zero
    regexp-off
    regexp-zero)
    add_test(NAME interpreter-aarch64-large-code-${large_mode}
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_large_code.js")
endforeach()
set_tests_properties(interpreter-aarch64-large-code-enabled
                     PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=1")
set_tests_properties(interpreter-aarch64-large-code-enabled-zero
                     PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=0")
set_tests_properties(
    interpreter-aarch64-large-code-enable-disable
    PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=1;QJS_DISABLE_FRAME_LARGE_CODE=0")
set_tests_properties(interpreter-aarch64-large-code-disabled
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=1")
set_tests_properties(interpreter-aarch64-large-code-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=0")
set_tests_properties(interpreter-aarch64-large-code-long-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_CODE=1")
set_tests_properties(
    interpreter-aarch64-large-code-c
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(interpreter-aarch64-large-code-bypass-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS=1")
set_tests_properties(interpreter-aarch64-large-code-bypass-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS=0")
set_tests_properties(interpreter-aarch64-large-code-regexp-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=1")
set_tests_properties(interpreter-aarch64-large-code-regexp-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=0")
if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-regexp-opcode tests/arm64/regexp-opcode.c)
    target_include_directories(aarch64-regexp-opcode PRIVATE "${qjs_arm_vm_dir}")
    target_compile_definitions(aarch64-regexp-opcode PRIVATE QJS_AARCH64_VM_INSTRUMENT)
    target_link_libraries(aarch64-regexp-opcode PRIVATE qjs)
    foreach(
        mode
        native
        regexp-off
        regexp-zero
        large-off
        large-zero
        long-off
        longregexp-off
        longregexp-zero
        admission-off
        register-off
        legacy
        enabled-zero)
        add_test(
            NAME interpreter-aarch64-regexp-opcode-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_regexp_opcode.py" --exe
                "$<TARGET_FILE:aarch64-regexp-opcode>" --mode semantics --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-aarch64-regexp-opcode-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_REGEXP_OPCODE_OK" TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-regexp-opcode-regexp-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REGEXP=1")
    set_tests_properties(interpreter-aarch64-regexp-opcode-regexp-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REGEXP=0")
    set_tests_properties(interpreter-aarch64-regexp-opcode-large-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=1")
    set_tests_properties(interpreter-aarch64-regexp-opcode-large-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=0")
    set_tests_properties(interpreter-aarch64-regexp-opcode-long-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_CODE=1")
    set_tests_properties(interpreter-aarch64-regexp-opcode-longregexp-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=1")
    set_tests_properties(interpreter-aarch64-regexp-opcode-longregexp-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=0")
    set_tests_properties(interpreter-aarch64-regexp-opcode-admission-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_ADMISSION=0")
    set_tests_properties(interpreter-aarch64-regexp-opcode-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-regexp-opcode-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    set_tests_properties(interpreter-aarch64-regexp-opcode-enabled-zero
                         PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=0")
    foreach(mode native regexp-off register-off legacy)
        add_test(
            NAME interpreter-aarch64-regexp-opcode-oom-${mode}
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_regexp_opcode.py" --exe
                "$<TARGET_FILE:aarch64-regexp-opcode>" --mode oom --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-aarch64-regexp-opcode-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_REGEXP_OPCODE_OOM_OK" TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-regexp-opcode-oom-regexp-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REGEXP=0")
    set_tests_properties(interpreter-aarch64-regexp-opcode-oom-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-regexp-opcode-oom-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
endif()
if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-regexp-routing tests/arm64/regexp-routing.c)
    target_link_libraries(aarch64-regexp-routing PRIVATE qjs)
    foreach(mode native module-zero module-one argv-zero argv-one)
        add_test(NAME interpreter-aarch64-regexp-routing-${mode} COMMAND aarch64-regexp-routing)
        set_tests_properties(
            interpreter-aarch64-regexp-routing-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_REGEXP_ROUTING_OK" TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-regexp-routing-module-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_REGEXP_WORKERS=0")
    set_tests_properties(interpreter-aarch64-regexp-routing-module-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_REGEXP_WORKERS=1")
    set_tests_properties(interpreter-aarch64-regexp-routing-argv-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV=0")
    set_tests_properties(interpreter-aarch64-regexp-routing-argv-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV=1")
endif()
add_executable(aarch64-regexp-api tests/common/linux/native_linux_regexp.c)
target_compile_options(aarch64-regexp-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(aarch64-regexp-api PRIVATE qjs)
foreach(
    mode
    on
    module-zero
    module-one
    argv-zero
    argv-one
    leaf-zero
    leaf-one
    batch-zero
    batch-one
    split-zero
    split-one
    empty-zero
    empty-one
    publish-zero
    frame-zero
    register-zero)
    add_test(NAME interpreter-aarch64-regexp-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_regexp.js")
    set_tests_properties(
        interpreter-aarch64-regexp-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_REGEXP_FAMILY_OK" TIMEOUT 120)
endforeach()
foreach(
    pair
    "module;QJS_DISABLE_LINUX_REGEXP_WORKERS" "argv;QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV"
    "leaf;QJS_DISABLE_REGEXP_FLAGS_LEAF" "batch;QJS_DISABLE_REGEXP_FLAGS_BATCH"
    "split;QJS_DISABLE_REGEXP_SPLIT" "empty;QJS_DISABLE_REGEXP_REPLACE_EMPTY")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST interpreter-aarch64-regexp-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
    set_property(
        TEST interpreter-aarch64-regexp-${name}-one
        APPEND
        PROPERTY ENVIRONMENT "${control}=1")
endforeach()
foreach(pair "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH" "frame;QJS_DISABLE_INTERP_FRAME"
             "register;QJS_DISABLE_REGISTER_INTERP")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST interpreter-aarch64-regexp-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
endforeach()
foreach(
    mode
    on
    module-zero
    module-one
    argv-zero
    leaf-zero
    batch-zero
    publish-zero
    frame-zero
    register-zero)
    add_test(NAME interpreter-aarch64-regexp-api-${mode} COMMAND aarch64-regexp-api)
    set_tests_properties(
        interpreter-aarch64-regexp-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_REGEXP_API_OK" TIMEOUT 120)
    if(NOT mode STREQUAL "on")
        get_property(
            regexp_environment
            TEST interpreter-aarch64-regexp-${mode}
            PROPERTY ENVIRONMENT)
        set_property(TEST interpreter-aarch64-regexp-api-${mode} PROPERTY ENVIRONMENT
                                                                          "${regexp_environment}")
    endif()
endforeach()
foreach(mode on module-zero argv-zero frame-zero publish-zero)
    add_test(NAME interpreter-aarch64-regexp-oom-${mode} COMMAND aarch64-regexp-api oom)
    set_tests_properties(
        interpreter-aarch64-regexp-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_REGEXP_OWNED_OOM_OK" TIMEOUT 120)
    if(NOT mode STREQUAL "on")
        get_property(
            regexp_environment
            TEST interpreter-aarch64-regexp-${mode}
            PROPERTY ENVIRONMENT)
        set_property(TEST interpreter-aarch64-regexp-oom-${mode} PROPERTY ENVIRONMENT
                                                                          "${regexp_environment}")
    endif()
endforeach()

add_executable(aarch64-json-paths tests/arm64/json-paths.c)
target_link_libraries(aarch64-json-paths PRIVATE qjs)
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-json-paths PRIVATE QJS_AARCH64_VM_INSTRUMENT)
endif()
foreach(mode native no-simd disabled)
    if(mode STREQUAL "native")
        set(json_vectors active)
    else()
        set(json_vectors idle)
    endif()
    add_test(NAME interpreter-aarch64-json-paths-${mode} COMMAND aarch64-json-paths ${json_vectors})
    set_tests_properties(interpreter-aarch64-json-paths-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_JSON_PATHS_OK" TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-json-paths-no-simd PROPERTIES ENVIRONMENT
                                                                       "QJS_JSON_MODE=32")
set_tests_properties(interpreter-aarch64-json-paths-disabled PROPERTIES ENVIRONMENT
                                                                        "QJS_JSON_MODE=127")
add_executable(aarch64-json-vector tests/arm64/json-vector.c)
add_dependencies(aarch64-json-vector qjs-aarch64-vm-inputs)
target_include_directories(aarch64-json-vector PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                       "${qjs_arm_vm_dir}")
add_test(NAME interpreter-aarch64-json-vector COMMAND aarch64-json-vector)
set_tests_properties(interpreter-aarch64-json-vector
                     PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_JSON_VECTOR_OK" TIMEOUT 180)
add_executable(aarch64-json-family tests/common/linux/native_linux_json_family.c)
target_compile_options(aarch64-json-family PRIVATE -UNDEBUG)
target_link_libraries(aarch64-json-family PRIVATE qjs)
foreach(
    mode
    on
    mode127
    value-off
    source-off
    codeunits-off
    write-off
    quote-off
    slot-off
    prepared-off
    arity-off
    source-prepared-off
    value-prepared-off
    no-simd
    no-cache
    register-off)
    set(json_expect active)
    if(mode MATCHES "^(mode127|prepared-off|register-off)$")
        set(json_expect idle)
    endif()
    add_test(
        NAME interpreter-aarch64-json-${mode}
        COMMAND
            aarch64-json-family
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_json_family.js"
            "${json_expect}")
    set_tests_properties(interpreter-aarch64-json-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_JSON_SEMANTICS_OK" TIMEOUT 120)
endforeach()
set_tests_properties(interpreter-aarch64-json-mode127 PROPERTIES ENVIRONMENT "QJS_JSON_MODE=127")
set_tests_properties(interpreter-aarch64-json-value-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_REVIVER_VALUE=0")
set_tests_properties(interpreter-aarch64-json-source-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_REVIVER_SOURCE=0")
set_tests_properties(interpreter-aarch64-json-codeunits-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_SOURCE_CODEUNITS=0")
set_tests_properties(interpreter-aarch64-json-write-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_CALLBACK_WRITE=0")
set_tests_properties(interpreter-aarch64-json-quote-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_DIRECT_QUOTE=0")
set_tests_properties(interpreter-aarch64-json-slot-off PROPERTIES ENVIRONMENT
                                                                  "QJS_DISABLE_JSON_TOJSON_SLOT=0")
set_tests_properties(interpreter-aarch64-json-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=0")
set_tests_properties(interpreter-aarch64-json-arity-off PROPERTIES ENVIRONMENT
                                                                   "QJS_DISABLE_CALLBACK_ARITY=0")
set_tests_properties(interpreter-aarch64-json-source-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_SOURCE_PREPARED=0")
set_tests_properties(interpreter-aarch64-json-value-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_VALUE_PREPARED=0")
set_tests_properties(interpreter-aarch64-json-no-simd PROPERTIES ENVIRONMENT "QJS_JSON_MODE=32")
set_tests_properties(interpreter-aarch64-json-no-cache PROPERTIES ENVIRONMENT "QJS_JSON_MODE=4")
set_tests_properties(interpreter-aarch64-json-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
foreach(
    mode
    value-off
    source-off
    codeunits-off
    write-off
    quote-off
    slot-off
    prepared-off
    arity-off
    source-prepared-off
    value-prepared-off
    register-off)
    set(json_expect active)
    if(mode MATCHES "^(prepared-off|register-off)$")
        set(json_expect idle)
    endif()
    get_test_property(interpreter-aarch64-json-${mode} ENVIRONMENT json_control_zero)
    string(REGEX REPLACE "=0$" "=1" json_control_one "${json_control_zero}")
    if(json_control_zero STREQUAL json_control_one)
        message(FATAL_ERROR "JSON presence control is not the original explicit-zero case")
    endif()
    add_test(
        NAME interpreter-aarch64-json-${mode}-one
        COMMAND
            aarch64-json-family
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_json_family.js"
            "${json_expect}")
    set_tests_properties(
        interpreter-aarch64-json-${mode}-one
        PROPERTIES ENVIRONMENT "${json_control_one}" PASS_REGULAR_EXPRESSION
                   "LINUX_JSON_SEMANTICS_OK" TIMEOUT 180)
endforeach()
foreach(mode on prepared-off)
    add_test(NAME interpreter-aarch64-json-oom-${mode} COMMAND aarch64-json-family sweep)
    set_tests_properties(interpreter-aarch64-json-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_JSON_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(interpreter-aarch64-json-oom-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=0")
foreach(mode direct-off direct-zero settled-off settled-zero output-off output-zero)
    if(mode MATCHES "^direct")
        set(async_control QJS_DISABLE_DIRECT_AWAIT)
    elseif(mode MATCHES "^settled")
        set(async_control QJS_DISABLE_SETTLED_AWAIT)
    else()
        set(async_control QJS_DISABLE_GENERATOR_CAPABILITY_OUTPUT)
    endif()
    if(mode MATCHES "zero$")
        set(async_control_value 0)
    else()
        set(async_control_value 1)
    endif()
    add_test(
        NAME interpreter-aarch64-async-generator-${mode}
        COMMAND qjs_exe --std
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_async_generator_capability.js")
    set_tests_properties(
        interpreter-aarch64-async-generator-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION
                   "\"passed\":true"
                   FAIL_REGULAR_EXPRESSION
                   "FAIL"
                   ENVIRONMENT
                   "${async_control}=${async_control_value}"
                   TIMEOUT
                   180)
    add_test(NAME interpreter-aarch64-async-ownership-${mode}
             COMMAND interpreter-test-async_capability generator)
    add_test(NAME interpreter-aarch64-async-oom-${mode} COMMAND interpreter-test-async_capability
                                                                generator sweep)
    set_tests_properties(
        interpreter-aarch64-async-ownership-${mode} interpreter-aarch64-async-oom-${mode}
        PROPERTIES ENVIRONMENT "${async_control}=${async_control_value}" TIMEOUT 180)
endforeach()
foreach(mode off clone)
    add_test(NAME interpreter-aarch64-async-oom-${mode} COMMAND interpreter-test-async_capability
                                                                generator sweep)
    set_tests_properties(interpreter-aarch64-async-oom-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-async-oom-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_GENERATOR_CAPABILITY=0")
set_tests_properties(interpreter-aarch64-async-oom-clone
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_GENERATOR_CAPABILITY_FAST=0")
foreach(mode register-off legacy)
    add_test(
        NAME interpreter-aarch64-async-generator-${mode}
        COMMAND qjs_exe --std
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_async_generator_capability.js")
    add_test(NAME interpreter-aarch64-async-ownership-${mode}
             COMMAND interpreter-test-async_capability generator)
    set_tests_properties(
        interpreter-aarch64-async-generator-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "\"passed\":true" FAIL_REGULAR_EXPRESSION "FAIL" TIMEOUT
                   180)
    set_tests_properties(interpreter-aarch64-async-ownership-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(
    interpreter-aarch64-async-generator-register-off
    interpreter-aarch64-async-ownership-register-off PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-async-generator-legacy interpreter-aarch64-async-ownership-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
add_executable(aarch64-prepared-callback tests/common/linux/native_linux_prepared_callback.c)
target_compile_options(aarch64-prepared-callback PRIVATE -UNDEBUG)
target_compile_definitions(aarch64-prepared-callback PRIVATE QJS_NATIVE_CALLBACK_UNWIND_TEST
                                                             "qjs_native_vm_end=qjs_aarch64_vm_end")
target_link_libraries(aarch64-prepared-callback PRIVATE qjs)
foreach(
    mode
    native
    off
    zero
    write-off
    write-zero
    arity-off
    arity-zero
    bypass-off
    bypass-zero
    shared-off
    shared-zero
    scoped
    host-off
    register-off
    legacy)
    add_test(NAME interpreter-aarch64-prepared-callback-${mode} COMMAND aarch64-prepared-callback)
    set_tests_properties(interpreter-aarch64-prepared-callback-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-prepared-callback-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=1")
set_tests_properties(interpreter-aarch64-prepared-callback-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=0")
set_tests_properties(interpreter-aarch64-prepared-callback-write-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_WRITE=1")
set_tests_properties(interpreter-aarch64-prepared-callback-write-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_WRITE=0")
set_tests_properties(interpreter-aarch64-prepared-callback-arity-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_ARITY=1")
set_tests_properties(interpreter-aarch64-prepared-callback-arity-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_ARITY=0")
set_tests_properties(interpreter-aarch64-prepared-callback-bypass-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_CALL_BYPASS=1")
set_tests_properties(interpreter-aarch64-prepared-callback-bypass-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_CALL_BYPASS=0")
set_tests_properties(interpreter-aarch64-prepared-callback-shared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(interpreter-aarch64-prepared-callback-shared-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(interpreter-aarch64-prepared-callback-scoped
                     PROPERTIES ENVIRONMENT "QJS_RETAIN_SCOPED_HOST=1")
set_tests_properties(interpreter-aarch64-prepared-callback-host-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=1")
set_tests_properties(interpreter-aarch64-prepared-callback-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-prepared-callback-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
foreach(mode native off write-off arity-off shared-off register-off)
    add_test(NAME interpreter-aarch64-prepared-oom-${mode} COMMAND aarch64-prepared-callback oom)
    set_tests_properties(interpreter-aarch64-prepared-oom-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-prepared-oom-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=1")
set_tests_properties(interpreter-aarch64-prepared-oom-write-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_WRITE=1")
set_tests_properties(interpreter-aarch64-prepared-oom-arity-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_ARITY=1")
set_tests_properties(interpreter-aarch64-prepared-oom-shared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(interpreter-aarch64-prepared-oom-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
add_test(NAME interpreter-aarch64-prepared-legacy-noarena COMMAND aarch64-prepared-callback
                                                                  legacy-noarena)
set_tests_properties(
    interpreter-aarch64-prepared-legacy-noarena
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
foreach(mode native off write-off arity-off shared-off register-off)
    add_test(NAME interpreter-aarch64-prepared-write-oom-${mode} COMMAND aarch64-prepared-callback
                                                                         write-oom)
    set_tests_properties(interpreter-aarch64-prepared-write-oom-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-prepared-write-oom-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=1")
set_tests_properties(interpreter-aarch64-prepared-write-oom-write-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_WRITE=1")
set_tests_properties(interpreter-aarch64-prepared-write-oom-arity-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CALLBACK_ARITY=1")
set_tests_properties(interpreter-aarch64-prepared-write-oom-shared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(interpreter-aarch64-prepared-write-oom-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
add_executable(aarch64-shared-tls tests/common/linux/native_linux_shared_tls.c)
target_link_libraries(aarch64-shared-tls PRIVATE qjs Threads::Threads)
foreach(mode native off zero scoped)
    add_test(NAME interpreter-aarch64-shared-tls-${mode} COMMAND aarch64-shared-tls)
    set_tests_properties(interpreter-aarch64-shared-tls-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-shared-tls-off PROPERTIES ENVIRONMENT
                                                                   "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(interpreter-aarch64-shared-tls-zero PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(interpreter-aarch64-shared-tls-scoped PROPERTIES ENVIRONMENT
                                                                      "QJS_RETAIN_SCOPED_HOST=1")
add_executable(aarch64-shared-scope tests/arm64/shared-scope.c)
target_include_directories(aarch64-shared-scope PRIVATE "${qjs_arm_vm_dir}")
target_link_libraries(aarch64-shared-scope PRIVATE qjs)
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-shared-scope PRIVATE QJS_AARCH64_VM_INSTRUMENT)
endif()
foreach(
    mode
    native
    off
    zero
    scoped
    host-off
    slow-off
    register-off
    legacy)
    add_test(NAME interpreter-aarch64-shared-scope-${mode} COMMAND aarch64-shared-scope ${mode})
    set_tests_properties(interpreter-aarch64-shared-scope-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-shared-scope-off PROPERTIES ENVIRONMENT
                                                                     "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(interpreter-aarch64-shared-scope-zero PROPERTIES ENVIRONMENT
                                                                      "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(interpreter-aarch64-shared-scope-scoped PROPERTIES ENVIRONMENT
                                                                        "QJS_RETAIN_SCOPED_HOST=1")
set_tests_properties(interpreter-aarch64-shared-scope-host-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=1")
set_tests_properties(
    interpreter-aarch64-shared-scope-slow-off
    PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=1;QJS_DISABLE_SLOW_HOST_SHARE=1")
set_tests_properties(interpreter-aarch64-shared-scope-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-shared-scope-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
add_executable(aarch64-captured-entry tests/arm64/captured-entry.c)
target_include_directories(aarch64-captured-entry PRIVATE "${qjs_arm_vm_dir}")
target_link_libraries(aarch64-captured-entry PRIVATE qjs)
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-captured-entry PRIVATE QJS_AARCH64_VM_INSTRUMENT)
endif()
foreach(
    mode
    native
    capture-off
    capture-zero
    missing-off
    missing-zero
    owned-off
    window-off
    name-off
    name-zero
    register-off
    legacy)
    add_test(NAME interpreter-aarch64-captured-entry-${mode} COMMAND aarch64-captured-entry ${mode})
    set_tests_properties(interpreter-aarch64-captured-entry-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-captured-entry-capture-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_ENTRY=1")
set_tests_properties(interpreter-aarch64-captured-entry-capture-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_ENTRY=0")
set_tests_properties(interpreter-aarch64-captured-entry-missing-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_MISSING=1")
set_tests_properties(interpreter-aarch64-captured-entry-missing-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_MISSING=0")
set_tests_properties(interpreter-aarch64-captured-entry-owned-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=1")
set_tests_properties(interpreter-aarch64-captured-entry-window-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_MISSING_WINDOW=1")
set_tests_properties(interpreter-aarch64-captured-entry-name-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_SET_NAME=1")
set_tests_properties(interpreter-aarch64-captured-entry-name-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_SET_NAME=0")
set_tests_properties(interpreter-aarch64-captured-entry-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-captured-entry-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
add_executable(aarch64-captured-oom tests/arm64/captured-oom.c)
target_include_directories(aarch64-captured-oom PRIVATE "${qjs_arm_vm_dir}")
target_link_libraries(aarch64-captured-oom PRIVATE qjs)
foreach(mode native capture-off missing-off owned-off register-off legacy)
    add_test(NAME interpreter-aarch64-captured-oom-${mode} COMMAND aarch64-captured-oom ${mode})
    set_tests_properties(interpreter-aarch64-captured-oom-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-captured-oom-capture-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_ENTRY=1")
set_tests_properties(interpreter-aarch64-captured-oom-missing-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_MISSING=1")
set_tests_properties(interpreter-aarch64-captured-oom-owned-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=1")
set_tests_properties(interpreter-aarch64-captured-oom-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-captured-oom-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
add_executable(aarch64-this-value tests/arm64/this-value.c)
target_link_libraries(aarch64-this-value PRIVATE qjs)
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-this-value PRIVATE QJS_AARCH64_VM_INSTRUMENT)
endif()
foreach(mode native register-off legacy)
    add_test(NAME interpreter-aarch64-this-value-${mode} COMMAND aarch64-this-value ${mode})
    set_tests_properties(interpreter-aarch64-this-value-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-this-value-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-this-value-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
add_executable(aarch64-public-api tests/common/native_api.c)
target_compile_features(aarch64-public-api PRIVATE c_std_11)
target_compile_options(aarch64-public-api PRIVATE -UNDEBUG)
target_link_libraries(aarch64-public-api PRIVATE qjs)
foreach(mode on register-off legacy)
    add_test(NAME interpreter-aarch64-public-api-${mode} COMMAND aarch64-public-api)
    set_tests_properties(interpreter-aarch64-public-api-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-public-api-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-public-api-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
add_executable(aarch64-numeric-ops tests/arm64/numeric-ops.c)
target_link_libraries(aarch64-numeric-ops PRIVATE qjs)
add_test(
    NAME interpreter-aarch64-numeric-differential
    COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_numeric.py"
            --exe "$<TARGET_FILE:aarch64-numeric-ops>" --runner ${CMAKE_CROSSCOMPILING_EMULATOR})
set_tests_properties(interpreter-aarch64-numeric-differential PROPERTIES TIMEOUT 180)
add_executable(aarch64-class-host tests/arm64/class-host.c)
target_include_directories(aarch64-class-host PRIVATE "${qjs_arm_vm_dir}")
target_link_libraries(aarch64-class-host PRIVATE qjs)
target_link_options(aarch64-class-host PRIVATE -rdynamic)
foreach(mode native class-off class-zero host-off register-off legacy)
    add_test(NAME interpreter-aarch64-class-host-${mode} COMMAND aarch64-class-host ${mode})
    set_tests_properties(interpreter-aarch64-class-host-${mode} PROPERTIES TIMEOUT 180)
endforeach()
foreach(component base-method core-method retained-method)
    add_test(NAME interpreter-aarch64-class-host-${component} COMMAND aarch64-class-host native)
    set_tests_properties(interpreter-aarch64-class-host-${component} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-class-host-base-method
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_IC=0")
set_tests_properties(interpreter-aarch64-class-host-core-method
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
set_tests_properties(interpreter-aarch64-class-host-retained-method
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES=0")
set_tests_properties(interpreter-aarch64-class-host-class-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CLASS_HOST=1")
set_tests_properties(interpreter-aarch64-class-host-class-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CLASS_HOST=0")
set_tests_properties(interpreter-aarch64-class-host-host-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=1")
set_tests_properties(interpreter-aarch64-class-host-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-class-host-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-numeric-ops PRIVATE QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-class-host PRIVATE QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-missing-window tests/arm64/missing-window.c)
    target_link_libraries(aarch64-missing-window PRIVATE qjs)
    foreach(mode native window-off window-zero register-off legacy)
        add_test(NAME interpreter-aarch64-missing-window-${mode} COMMAND aarch64-missing-window
                                                                         ${mode})
        set_tests_properties(interpreter-aarch64-missing-window-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-missing-window-window-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_MISSING_WINDOW=1")
    set_tests_properties(interpreter-aarch64-missing-window-window-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_MISSING_WINDOW=0")
    set_tests_properties(interpreter-aarch64-missing-window-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-missing-window-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-owned-args tests/arm64/owned-args.c)
    target_link_libraries(aarch64-owned-args PRIVATE qjs)
    foreach(mode native owned-off owned-zero register-off legacy)
        add_test(NAME interpreter-aarch64-owned-args-${mode} COMMAND aarch64-owned-args ${mode})
        set_tests_properties(interpreter-aarch64-owned-args-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-owned-args-owned-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=1")
    set_tests_properties(interpreter-aarch64-owned-args-owned-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=0")
    set_tests_properties(interpreter-aarch64-owned-args-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-owned-args-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-reference-ops tests/arm64/reference-ops.c)
    target_link_libraries(aarch64-reference-ops PRIVATE qjs)
    foreach(mode native ref-off ref-zero register-off legacy)
        add_test(NAME interpreter-aarch64-reference-ops-${mode} COMMAND aarch64-reference-ops
                                                                        ${mode})
        set_tests_properties(interpreter-aarch64-reference-ops-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-reference-ops-ref-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_REFS=1")
    set_tests_properties(interpreter-aarch64-reference-ops-ref-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_REFS=0")
    set_tests_properties(interpreter-aarch64-reference-ops-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-reference-ops-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-value-ops tests/arm64/value-ops.c)
    target_link_libraries(aarch64-value-ops PRIVATE qjs)
    foreach(mode native slot-off slot-zero register-off legacy)
        add_test(NAME interpreter-aarch64-value-ops-${mode} COMMAND aarch64-value-ops ${mode})
    endforeach()
    set_tests_properties(interpreter-aarch64-value-ops-slot-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=1")
    set_tests_properties(interpreter-aarch64-value-ops-slot-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=0")
    set_tests_properties(interpreter-aarch64-value-ops-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-value-ops-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-slot-owners tests/arm64/slot-owners.c)
    target_link_libraries(aarch64-slot-owners PRIVATE qjs)
    foreach(mode native slot-off slot-zero register-off legacy)
        add_test(NAME interpreter-aarch64-slot-owners-${mode} COMMAND aarch64-slot-owners ${mode})
        set_tests_properties(interpreter-aarch64-slot-owners-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-slot-owners-slot-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=1")
    set_tests_properties(interpreter-aarch64-slot-owners-slot-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_SLOT_STORE=0")
    set_tests_properties(interpreter-aarch64-slot-owners-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-slot-owners-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-host-call tests/arm64/host-call.c)
    target_link_libraries(aarch64-host-call PRIVATE qjs)
    foreach(mode native host-off register-off legacy)
        add_test(NAME interpreter-aarch64-host-call-${mode} COMMAND aarch64-host-call ${mode})
        set_tests_properties(interpreter-aarch64-host-call-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-host-call-host-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DIRECT_HOST_CALL=1")
    set_tests_properties(interpreter-aarch64-host-call-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-host-call-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    add_executable(aarch64-call-owners tests/arm64/call-owners.c)
    target_link_libraries(aarch64-call-owners PRIVATE qjs)
    foreach(mode native register-off legacy)
        add_test(NAME interpreter-aarch64-call-owners-${mode} COMMAND aarch64-call-owners ${mode})
        set_tests_properties(interpreter-aarch64-call-owners-${mode} PROPERTIES TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-call-owners-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-call-owners-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endif()
add_executable(aarch64-call-oom tests/arm64/call-oom.c)
target_include_directories(aarch64-call-oom PRIVATE "${qjs_arm_vm_dir}")
target_link_libraries(aarch64-call-oom PRIVATE qjs)
if(QJS_AARCH64_VM_INSTRUMENT)
    target_compile_definitions(aarch64-call-oom PRIVATE QJS_AARCH64_VM_INSTRUMENT)
endif()
foreach(mode native register-off legacy)
    add_test(NAME interpreter-aarch64-call-oom-${mode} COMMAND aarch64-call-oom ${mode})
    set_tests_properties(interpreter-aarch64-call-oom-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-call-oom-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-call-oom-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")

# Reuse the complete original semantic/allocator/finalizer comparison fixtures.
add_executable(aarch64-comparison-api tests/common/linux/native_linux_comparisons.c)
target_link_libraries(aarch64-comparison-api PRIVATE qjs)
foreach(
    mode
    native
    group-zero
    group-one
    strict-zero
    loose-zero
    identity-zero
    reference-zero
    strings-zero
    null-zero
    object-null-zero
    publish-zero
    register-off
    legacy)
    add_test(NAME interpreter-aarch64-comparison-family-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_comparisons.js")
    set_tests_properties(
        interpreter-aarch64-comparison-family-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_COMPARISON_FAMILY_OK" TIMEOUT 180)
    add_test(NAME interpreter-aarch64-comparison-api-${mode} COMMAND aarch64-comparison-api)
    set_tests_properties(interpreter-aarch64-comparison-api-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_COMPARISON_API_OK" TIMEOUT 180)
endforeach()
foreach(
    pair
    "group;QJS_DISABLE_LINUX_COMPARISONS"
    "strict;QJS_DISABLE_LINUX_STRICT_COMPARE"
    "loose;QJS_DISABLE_LINUX_LOOSE_COMPARE"
    "identity;QJS_DISABLE_LINUX_C_IDENTITY"
    "reference;QJS_DISABLE_FRAME_REFERENCE_EQUALITY"
    "strings;QJS_DISABLE_FRAME_LOOSE_EQ_STRINGS"
    "null;QJS_DISABLE_FRAME_LOOSE_EQ_NULL"
    "object-null;QJS_DISABLE_FRAME_LOOSE_EQ_OBJECT_NULL"
    "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH")
    list(GET pair 0 label)
    list(GET pair 1 control)
    foreach(kind family api)
        foreach(number zero one)
            if(TEST interpreter-aarch64-comparison-${kind}-${label}-${number})
                if(number STREQUAL "zero")
                    set(value 0)
                else()
                    set(value 1)
                endif()
                set_tests_properties(interpreter-aarch64-comparison-${kind}-${label}-${number}
                                     PROPERTIES ENVIRONMENT "${control}=${value}")
            endif()
        endforeach()
    endforeach()
endforeach()
foreach(kind family api)
    set_tests_properties(interpreter-aarch64-comparison-${kind}-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-comparison-${kind}-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
endforeach()
foreach(mode native group-zero identity-zero)
    add_test(NAME interpreter-aarch64-comparison-oom-${mode} COMMAND aarch64-comparison-api oom)
    set_tests_properties(interpreter-aarch64-comparison-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_COMPARISON_OOM_OK" TIMEOUT 300)
endforeach()
set_tests_properties(interpreter-aarch64-comparison-oom-group-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_COMPARISONS=0")
set_tests_properties(interpreter-aarch64-comparison-oom-identity-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_C_IDENTITY=0")
if(QJS_INTERP_FRAME_COMPARISONS)
    add_executable(aarch64-comparison-direct tests/common/linux/native_linux_comparisons.c)
    target_compile_definitions(aarch64-comparison-direct PRIVATE QJS_TEST_DIRECT_COMPARISON)
    target_link_libraries(aarch64-comparison-direct PRIVATE qjs)
    foreach(mode native group-zero identity-zero reference-zero)
        add_test(NAME interpreter-aarch64-comparison-direct-${mode}
                 COMMAND aarch64-comparison-direct)
        set_tests_properties(
            interpreter-aarch64-comparison-direct-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_COMPARISON_API_OK" TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-comparison-direct-group-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_COMPARISONS=0")
    set_tests_properties(interpreter-aarch64-comparison-direct-identity-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_C_IDENTITY=0")
    set_tests_properties(interpreter-aarch64-comparison-direct-reference-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REFERENCE_EQUALITY=0")
endif()

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-comparison-paths tests/arm64/comparisons.c)
    target_include_directories(aarch64-comparison-paths PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-comparison-paths PRIVATE qjs)
    foreach(
        mode
        native
        group-zero
        group-one
        strict-zero
        loose-zero
        reference-zero
        strings-zero
        null-zero
        object-null-zero
        loose-all-zero
        identity-zero
        publish-zero
        register-off
        legacy
        observe)
        add_test(NAME interpreter-aarch64-comparison-paths-${mode} COMMAND aarch64-comparison-paths)
        set_tests_properties(
            interpreter-aarch64-comparison-paths-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_COMPARISON_PATHS_OK" TIMEOUT 180)
    endforeach()
    foreach(
        pair
        "group;QJS_DISABLE_LINUX_COMPARISONS"
        "strict;QJS_DISABLE_LINUX_STRICT_COMPARE"
        "loose;QJS_DISABLE_LINUX_LOOSE_COMPARE"
        "reference;QJS_DISABLE_FRAME_REFERENCE_EQUALITY"
        "strings;QJS_DISABLE_FRAME_LOOSE_EQ_STRINGS"
        "null;QJS_DISABLE_FRAME_LOOSE_EQ_NULL"
        "object-null;QJS_DISABLE_FRAME_LOOSE_EQ_OBJECT_NULL"
        "loose-all;QJS_DISABLE_FRAME_LOOSE_EQ"
        "identity;QJS_DISABLE_LINUX_C_IDENTITY"
        "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH")
        list(GET pair 0 label)
        list(GET pair 1 control)
        set_tests_properties(interpreter-aarch64-comparison-paths-${label}-zero
                             PROPERTIES ENVIRONMENT "${control}=0")
    endforeach()
    set_tests_properties(interpreter-aarch64-comparison-paths-group-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_COMPARISONS=1")
    set_tests_properties(interpreter-aarch64-comparison-paths-observe
                         PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_LOOSE_EQ=1")
    set_tests_properties(interpreter-aarch64-comparison-paths-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(
        interpreter-aarch64-comparison-paths-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
endif()

# Original ordinary constructor and complete cleanup qualification.
foreach(kind continuation boundary)
    if(kind STREQUAL "continuation")
        set(construct_marker CONSTRUCT_CONTINUATION_OK)
    else()
        set(construct_marker CONSTRUCT_BOUNDARY_ERRORS_OK)
    endif()
    foreach(mode on construct-0 construct-1 iterator-0 iterator-1 frame-off)
        add_test(NAME interpreter-aarch64-construct-${kind}-${mode}
                 COMMAND qjs_exe --std -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_construct_${kind}.js")
        set_tests_properties(
            interpreter-aarch64-construct-${kind}-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "${construct_marker}" ENVIRONMENT
                       "QJS_EXPERIMENT_ALLOCATOR=256")
    endforeach()
    foreach(value 0 1)
        set_property(
            TEST interpreter-aarch64-construct-${kind}-construct-${value}
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=${value}")
        set_property(
            TEST interpreter-aarch64-construct-${kind}-iterator-${value}
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=${value}")
    endforeach()
    set_property(
        TEST interpreter-aarch64-construct-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_MIN_CALL_FRAME=1")
endforeach()

add_executable(aarch64-construct-api tests/common/linux/native_linux_construct.c)
target_compile_options(aarch64-construct-api PRIVATE -UNDEBUG)
target_link_libraries(aarch64-construct-api PRIVATE qjs)
foreach(kind paths api)
    foreach(
        mode
        on
        construct-0
        construct-1
        iterator-0
        iterator-1
        slow-0
        slow-1
        shared-0
        shared-1
        frame-off)
        if(kind STREQUAL "paths")
            add_test(
                NAME interpreter-aarch64-construct-${kind}-${mode}
                COMMAND qjs_exe --std -m
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_construct.js")
            set(construct_success LINUX_CONSTRUCT_PATHS_OK)
        else()
            add_test(NAME interpreter-aarch64-construct-${kind}-${mode}
                     COMMAND aarch64-construct-api)
            set(construct_success LINUX_CONSTRUCT_API_OK)
        endif()
        set_tests_properties(
            interpreter-aarch64-construct-${kind}-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "${construct_success}")
    endforeach()
    foreach(
        pair IN
        ITEMS "construct=QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION"
              "iterator=QJS_DISABLE_FRAME_ITERATOR" "slow=QJS_DISABLE_SLOW_HOST_SHARE"
              "shared=QJS_DISABLE_SHARED_ENTRY")
        string(REPLACE "=" ";" fields "${pair}")
        list(GET fields 0 label)
        list(GET fields 1 control)
        foreach(value 0 1)
            set_property(
                TEST interpreter-aarch64-construct-${kind}-${label}-${value}
                APPEND
                PROPERTY ENVIRONMENT "${control}=${value}")
        endforeach()
    endforeach()
    set_property(
        TEST interpreter-aarch64-construct-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_MIN_CALL_FRAME=1")
endforeach()
foreach(mode on construct-1 iterator-1 slow-1 shared-1 frame-off)
    add_test(NAME interpreter-aarch64-construct-oom-${mode} COMMAND aarch64-construct-api oom)
    get_test_property(interpreter-aarch64-construct-api-${mode} ENVIRONMENT construct_environment)
    set_tests_properties(
        interpreter-aarch64-construct-oom-${mode}
        PROPERTIES ENVIRONMENT "${construct_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_CONSTRUCT_OOM_OK")
endforeach()
foreach(mode on construct-1)
    add_test(NAME interpreter-aarch64-construct-grown-oom-${mode} COMMAND aarch64-construct-api
                                                                          oom-grown)
    get_test_property(interpreter-aarch64-construct-api-${mode} ENVIRONMENT construct_environment)
    set_tests_properties(
        interpreter-aarch64-construct-grown-oom-${mode}
        PROPERTIES ENVIRONMENT "${construct_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_CONSTRUCT_OOM_OK")
endforeach()

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-constructor-paths tests/arm64/constructors.c)
    target_include_directories(aarch64-constructor-paths PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-constructor-paths PRIVATE qjs)
    foreach(
        mode
        native
        zero
        one
        iterator-zero
        varargs-zero
        slow-zero
        shared-zero
        host-return-zero
        publish-zero
        register-off
        frame-off
        legacy)
        add_test(NAME interpreter-aarch64-constructor-paths-${mode}
                 COMMAND aarch64-constructor-paths)
        set_tests_properties(
            interpreter-aarch64-constructor-paths-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_CONSTRUCTOR_PATHS_OK" TIMEOUT 180)
    endforeach()
    set_tests_properties(interpreter-aarch64-constructor-paths-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=0")
    set_tests_properties(interpreter-aarch64-constructor-paths-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=1")
    foreach(
        pair
        "iterator;QJS_DISABLE_FRAME_ITERATOR" "varargs;QJS_DISABLE_FRAME_VARARGS"
        "slow;QJS_DISABLE_SLOW_HOST_SHARE" "shared;QJS_DISABLE_SHARED_ENTRY"
        "host-return;QJS_DISABLE_AARCH64_HOST_RETURN" "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH")
        list(GET pair 0 label)
        list(GET pair 1 control)
        set_tests_properties(interpreter-aarch64-constructor-paths-${label}-zero
                             PROPERTIES ENVIRONMENT "${control}=0")
    endforeach()
    set_tests_properties(interpreter-aarch64-constructor-paths-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-constructor-paths-frame-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    set_tests_properties(
        interpreter-aarch64-constructor-paths-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endif()

# Whole iterator protocol, with independent native/checkpoint/array controls.
foreach(
    mode
    on
    iterator-zero
    iterator-one
    js-zero
    js-one
    array-zero
    array-one
    slow-zero
    publish-zero
    share-zero
    frame-zero)
    add_test(NAME interpreter-aarch64-iterators-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_iterators.js")
    set_tests_properties(
        interpreter-aarch64-iterators-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST interpreter-aarch64-iterators-iterator-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=0")
set_property(
    TEST interpreter-aarch64-iterators-iterator-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=1")
set_property(
    TEST interpreter-aarch64-iterators-js-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=0")
set_property(
    TEST interpreter-aarch64-iterators-js-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=1")
set_property(
    TEST interpreter-aarch64-iterators-array-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=0")
set_property(
    TEST interpreter-aarch64-iterators-array-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=1")
set_property(
    TEST interpreter-aarch64-iterators-slow-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR_SLOW=0")
set_property(
    TEST interpreter-aarch64-iterators-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST interpreter-aarch64-iterators-share-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
set_property(
    TEST interpreter-aarch64-iterators-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
# Public-only owner fixture, exercising actual JS-next/realm/GC continuations.
add_executable(aarch64-iterators-api tests/common/linux/native_linux_publication.c)
target_compile_definitions(aarch64-iterators-api PRIVATE QJS_TEST_ITERATOR_PROTOCOL)
target_compile_options(aarch64-iterators-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(aarch64-iterators-api PRIVATE qjs)
foreach(
    mode
    on
    js-zero
    js-one
    array-zero
    iterator-zero
    publish-zero
    shared-zero
    slow-host-zero
    frame-zero)
    add_test(NAME interpreter-aarch64-iterators-api-${mode} COMMAND aarch64-iterators-api)
    set_tests_properties(
        interpreter-aarch64-iterators-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_API_OK" TIMEOUT 120)
endforeach()
foreach(mode on js-zero iterator-zero frame-zero)
    add_test(NAME interpreter-aarch64-iterators-oom-${mode} COMMAND aarch64-iterators-api oom)
    set_tests_properties(
        interpreter-aarch64-iterators-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_OOM_OK" TIMEOUT 120)
endforeach()
foreach(kind api oom)
    set_property(
        TEST interpreter-aarch64-iterators-${kind}-js-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=0")
    set_property(
        TEST interpreter-aarch64-iterators-${kind}-iterator-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=0")
    set_property(
        TEST interpreter-aarch64-iterators-${kind}-frame-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endforeach()
set_property(
    TEST interpreter-aarch64-iterators-api-js-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=1")
set_property(
    TEST interpreter-aarch64-iterators-api-array-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=0")
set_property(
    TEST interpreter-aarch64-iterators-api-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST interpreter-aarch64-iterators-api-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
set_property(
    TEST interpreter-aarch64-iterators-api-slow-host-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")

foreach(
    mode
    on
    constructor-zero
    refs-zero
    host-return-zero
    publish-zero
    register-zero
    frame-zero)
    add_test(NAME interpreter-aarch64-complete-dispatch-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_aarch64_complete_dispatch.js")
    set_tests_properties(
        interpreter-aarch64-complete-dispatch-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_COMPLETE_DISPATCH_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST interpreter-aarch64-complete-dispatch-constructor-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=0")
set_property(
    TEST interpreter-aarch64-complete-dispatch-refs-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_REFS=0")
set_property(
    TEST interpreter-aarch64-complete-dispatch-host-return-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
set_property(
    TEST interpreter-aarch64-complete-dispatch-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST interpreter-aarch64-complete-dispatch-register-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_property(
    TEST interpreter-aarch64-complete-dispatch-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-iterator-paths tests/arm64/iterators.c)
    target_link_libraries(aarch64-iterator-paths PRIVATE qjs)
    target_include_directories(aarch64-iterator-paths PRIVATE "${qjs_arm_vm_dir}")
    foreach(
        mode
        on
        constructor-zero
        iterator-zero
        js-zero
        array-zero
        slow-array-zero
        publish-zero
        host-return-zero
        register-zero
        frame-zero)
        add_test(NAME interpreter-aarch64-iterator-paths-${mode} COMMAND aarch64-iterator-paths)
        set_tests_properties(
            interpreter-aarch64-iterator-paths-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_ITERATOR_PATHS_OK" TIMEOUT 120)
    endforeach()
    set_property(
        TEST interpreter-aarch64-iterator-paths-constructor-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-iterator-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-js-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-array-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-slow-array-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR_SLOW=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-publish-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-host-return-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-register-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_property(
        TEST interpreter-aarch64-iterator-paths-frame-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endif()

# Complete public array-own semantics; the direct leaf exists only when ON.
if(QJS_INTERP_FRAME_ARRAY_OWN)
    add_executable(aarch64-array-own tests/arm64/array-own.c)
    target_link_libraries(aarch64-array-own PRIVATE qjs)
    target_compile_options(aarch64-array-own PRIVATE -UNDEBUG)
    if(QJS_AARCH64_VM_INSTRUMENT)
        target_compile_definitions(aarch64-array-own PRIVATE QJS_AARCH64_VM_INSTRUMENT)
        if(qjs_arm_indexed_enabled)
            target_compile_definitions(aarch64-array-own PRIVATE QJS_TEST_AARCH64_INDEXED)
        endif()
    endif()
    foreach(mode native register-off frame-off)
        add_test(NAME interpreter-aarch64-array-own-${mode} COMMAND aarch64-array-own)
        set_tests_properties(
            interpreter-aarch64-array-own-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "ARRAY OWN PASS" FAIL_REGULAR_EXPRESSION
                       "Assertion|Segmentation")
    endforeach()
    set_tests_properties(interpreter-aarch64-array-own-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-array-own-frame-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    if(qjs_arm_indexed_enabled)
        foreach(value 0 1)
            add_test(NAME interpreter-aarch64-array-own-indexed-own-${value}
                     COMMAND aarch64-array-own)
            set_tests_properties(
                interpreter-aarch64-array-own-indexed-own-${value}
                PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_OWN=${value}"
                           PASS_REGULAR_EXPRESSION "ARRAY OWN PASS" FAIL_REGULAR_EXPRESSION
                           "Assertion|Segmentation")
        endforeach()
    endif()
endif()
foreach(mode native register-off frame-off)
    add_test(NAME interpreter-aarch64-array-own-indexed-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_indexed.js")
    set_tests_properties(interpreter-aarch64-array-own-indexed-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_INDEXED_OK")
endforeach()
set_tests_properties(interpreter-aarch64-array-own-indexed-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_tests_properties(interpreter-aarch64-array-own-indexed-frame-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")

# Shared .call semantics remain separate from the not-yet-complete native set.
if(QJS_INTERP_FRAME_CALL_FORWARD)
    add_executable(aarch64-forward-api tests/common/linux/native_linux_call_forward.c)
    target_compile_options(aarch64-forward-api PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-forward-api PRIVATE qjs)
    foreach(
        mode
        on
        forward-zero
        leaf-zero
        native-zero
        native-one
        publication-zero
        register-zero
        frame-zero)
        add_test(
            NAME interpreter-aarch64-forward-language-${mode}
            COMMAND qjs_exe
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_call_forward.js")
        set_tests_properties(interpreter-aarch64-forward-language-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_CALL_FORWARD_OK" TIMEOUT 120)
    endforeach()
    foreach(mode on forward-zero publication-zero frame-zero)
        foreach(case api oom quota)
            if(case STREQUAL "api")
                add_test(NAME interpreter-aarch64-forward-${case}-${mode}
                         COMMAND aarch64-forward-api)
                set(marker "LINUX_FORWARD_HOST_OK")
            else()
                add_test(NAME interpreter-aarch64-forward-${case}-${mode}
                         COMMAND aarch64-forward-api ${case})
                string(TOUPPER "${case}" suffix)
                set(marker "LINUX_FORWARD_${suffix}_OK")
            endif()
            set_tests_properties(interpreter-aarch64-forward-${case}-${mode}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "${marker}" TIMEOUT 120)
        endforeach()
    endforeach()
    foreach(group language api oom quota)
        set_tests_properties(interpreter-aarch64-forward-${group}-forward-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-publication-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-frame-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    endforeach()
    set_tests_properties(interpreter-aarch64-forward-language-leaf-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF=0")
    set_tests_properties(interpreter-aarch64-forward-language-native-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
    set_tests_properties(interpreter-aarch64-forward-language-native-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=1")
    set_tests_properties(interpreter-aarch64-forward-language-register-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    if(QJS_AARCH64_VM_INSTRUMENT)
        foreach(kind logical leaf)
            add_executable(aarch64-forward-${kind} tests/arm64/forward-${kind}.c)
            target_compile_options(aarch64-forward-${kind} PRIVATE -UNDEBUG)
            target_include_directories(aarch64-forward-${kind}
                                       PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
            target_link_libraries(aarch64-forward-${kind} PRIVATE qjs)
        endforeach()
        foreach(mode c-leaf c-child-native-pop c-child-publication-off master-off)
            add_test(NAME interpreter-aarch64-forward-logical-${mode}
                     COMMAND aarch64-forward-logical)
            set_tests_properties(
                interpreter-aarch64-forward-logical-${mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "FORWARD_STAGE1_PATHS_OK" ENVIRONMENT
                           "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
        endforeach()
        set_property(
            TEST interpreter-aarch64-forward-logical-c-child-native-pop
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF=0")
        set_property(
            TEST interpreter-aarch64-forward-logical-c-child-publication-off
            APPEND
            PROPERTY ENVIRONMENT
                     "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF=0;QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
        set_property(
            TEST interpreter-aarch64-forward-logical-master-off
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
        foreach(mode on native-zero native-one forward-zero publication-zero)
            add_test(NAME interpreter-aarch64-forward-native-leaf-${mode}
                     COMMAND aarch64-forward-leaf)
            set_tests_properties(
                interpreter-aarch64-forward-native-leaf-${mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "FORWARD_NATIVE_INTEGER_PATH_OK")
        endforeach()
        set_tests_properties(interpreter-aarch64-forward-native-leaf-native-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
        set_tests_properties(interpreter-aarch64-forward-native-leaf-native-one
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=1")
        set_tests_properties(interpreter-aarch64-forward-native-leaf-forward-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
        set_tests_properties(interpreter-aarch64-forward-native-leaf-publication-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
        add_executable(aarch64-forward-c-owner tests/common/linux/native_linux_call_forward.c
                                               tests/arm64/forward-probe.c)
        target_compile_options(aarch64-forward-c-owner PRIVATE -UNDEBUG)
        target_include_directories(aarch64-forward-c-owner PRIVATE "${qjs_arm_vm_dir}")
        target_link_libraries(aarch64-forward-c-owner PRIVATE qjs)
        foreach(mode on publication-zero)
            add_test(NAME interpreter-aarch64-forward-C-normalizer-${mode}
                     COMMAND aarch64-forward-c-owner)
            set_tests_properties(
                interpreter-aarch64-forward-C-normalizer-${mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_FORWARD_HOST_OK" ENVIRONMENT
                           "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
        endforeach()
        set_property(
            TEST interpreter-aarch64-forward-C-normalizer-publication-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    endif()
endif()

# Public calls must distinguish native ownership routes from C normalization.
if(QJS_INTERP_FRAME_CALL_FORWARD AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-forward-owned tests/arm64/forward-owned.c)
    target_compile_options(aarch64-forward-owned PRIVATE -UNDEBUG)
    target_include_directories(aarch64-forward-owned PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(aarch64-forward-owned PRIVATE qjs)
    foreach(
        mode
        on
        native-zero
        native-one
        owned-zero
        owned-one
        borrow-zero
        borrow-one
        missing-zero
        missing-one
        publication-zero
        forward-zero
        register-zero
        frame-zero
        leaf-zero)
        add_test(NAME interpreter-aarch64-forward-owned-${mode} COMMAND aarch64-forward-owned)
        set_tests_properties(
            interpreter-aarch64-forward-owned-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "FORWARD_OWNED_PATHS_OK" TIMEOUT 120)
        add_test(NAME interpreter-aarch64-forward-native-public-${mode}
                 COMMAND aarch64-forward-c-owner)
        set_tests_properties(interpreter-aarch64-forward-native-public-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_FORWARD_HOST_OK" TIMEOUT 120)
    endforeach()
    foreach(group owned native-public)
        foreach(value zero one)
            if(value STREQUAL "zero")
                set(control_value 0)
            else()
                set(control_value 1)
            endif()
            foreach(component native owned borrow missing)
                if(component STREQUAL "missing")
                    set(suffix FRAME_CALL_FORWARD_BORROW_MISSING)
                else()
                    string(TOUPPER "${component}" upper)
                    set(suffix FRAME_CALL_FORWARD_${upper})
                endif()
                set_tests_properties(
                    interpreter-aarch64-forward-${group}-${component}-${value}
                    PROPERTIES ENVIRONMENT "QJS_DISABLE_${suffix}=${control_value}")
            endforeach()
        endforeach()
        set_tests_properties(interpreter-aarch64-forward-${group}-publication-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-forward-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-register-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-frame-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
        set_tests_properties(interpreter-aarch64-forward-${group}-leaf-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF=0")
    endforeach()
endif()

# The test uses the same DATA_TYPE source literal as the actual C owner.
if(QJS_INTERP_FRAME_CALL_FORWARD AND QJS_AARCH64_VM_INSTRUMENT)
    set(qjs_arm_prepare_test_types
        "${CMAKE_CURRENT_BINARY_DIR}/tests/arm64/aarch64-prepared-data.h")
    add_custom_command(
        OUTPUT "${qjs_arm_prepare_test_types}"
        COMMAND
            "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_prepare_types.py"
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --output "${qjs_arm_prepare_test_types}"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_prepare_types.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/c_extract/call_prepare_c.py"
        VERBATIM)
    add_executable(aarch64-prepared-forward tests/arm64/prepared-forward.c
                                            "${qjs_arm_prepare_test_types}")
    target_include_directories(
        aarch64-prepared-forward PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                         "${CMAKE_CURRENT_BINARY_DIR}/tests/arm64")
    target_compile_options(aarch64-prepared-forward PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-prepared-forward PRIVATE qjs)
    foreach(
        mode
        on
        prepare-zero
        prepare-one
        owned-zero
        owned-one
        native-zero
        native-one
        leaf-zero
        leaf-one
        observe-zero
        observe-one
        publication-zero
        forward-zero
        register-zero
        frame-zero)
        add_test(NAME interpreter-aarch64-prepared-forward-${mode} COMMAND aarch64-prepared-forward)
        set_tests_properties(
            interpreter-aarch64-prepared-forward-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_PREPARED_PATHS_OK" TIMEOUT 120)
    endforeach()
    foreach(value zero one)
        if(value STREQUAL "zero")
            set(control_value 0)
        else()
            set(control_value 1)
        endif()
        set_tests_properties(
            interpreter-aarch64-prepared-forward-prepare-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_PREPARE=${control_value}")
        set_tests_properties(
            interpreter-aarch64-prepared-forward-owned-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_PREPARE_OWNED=${control_value}")
        set_tests_properties(
            interpreter-aarch64-prepared-forward-native-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=${control_value}")
        set_tests_properties(
            interpreter-aarch64-prepared-forward-leaf-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF=${control_value}")
        set_tests_properties(
            interpreter-aarch64-prepared-forward-observe-${value}
            PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_CALL_PREPARE=${control_value}")
    endforeach()
    set_tests_properties(interpreter-aarch64-prepared-forward-publication-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-prepared-forward-forward-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
    set_tests_properties(interpreter-aarch64-prepared-forward-register-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-prepared-forward-frame-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endif()

# Exact source proof,real graph boundary and borrowed captured-argument views.
if(QJS_INTERP_FRAME_CALL_FORWARD AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-captured-readonly tests/arm64/captured-readonly.c
                                             tests/arm64/forward-probe.c)
    target_compile_options(aarch64-captured-readonly PRIVATE -UNDEBUG)
    target_include_directories(aarch64-captured-readonly PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                                 "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-captured-readonly PRIVATE qjs)
    if(QJS_AARCH64_FAST_VM)
        target_compile_definitions(aarch64-captured-readonly PRIVATE QJS_AARCH64_FAST_VM)
    endif()
    foreach(
        mode
        on
        proof-zero
        proof-one
        entry-zero
        entry-one
        owned-zero
        owned-one
        missing-zero
        missing-one
        window-zero
        window-one
        forward-zero
        forward-one
        borrow-zero
        borrow-one
        pad-zero
        pad-one
        publication-zero
        register-zero
        frame-zero)
        add_test(NAME interpreter-aarch64-captured-readonly-${mode}
                 COMMAND aarch64-captured-readonly)
        set_tests_properties(
            interpreter-aarch64-captured-readonly-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_CAPTURED_READONLY_OK" TIMEOUT 120)
    endforeach()
    foreach(value zero one)
        if(value STREQUAL "zero")
            set(control_value 0)
        else()
            set(control_value 1)
        endif()
        set_tests_properties(
            interpreter-aarch64-captured-readonly-proof-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CAPTURED_READONLY=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-entry-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_CAPTURED_ENTRY=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-owned-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_ARGS=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-missing-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_OWNED_MISSING=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-window-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_MISSING_WINDOW=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-forward-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-borrow-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_BORROW=${control_value}")
        set_tests_properties(
            interpreter-aarch64-captured-readonly-pad-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING=${control_value}")
    endforeach()
    set_tests_properties(interpreter-aarch64-captured-readonly-publication-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-captured-readonly-register-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-captured-readonly-frame-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endif()
# Preserve the original owned-entry assertions under both proof disable values.
if(QJS_INTERP_FRAME_CALL_FORWARD)
    foreach(
        mode
        native
        capture-off
        capture-zero
        missing-off
        missing-zero
        owned-off
        window-off
        name-off
        name-zero
        register-off
        legacy)
        get_property(
            original_captured_environment
            TEST interpreter-aarch64-captured-entry-${mode}
            PROPERTY ENVIRONMENT)
        foreach(value 0 1)
            add_test(NAME interpreter-aarch64-captured-entry-proof${value}-${mode}
                     COMMAND aarch64-captured-entry ${mode})
            set_tests_properties(
                interpreter-aarch64-captured-entry-proof${value}-${mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_CAPTURED_ENTRY_OK" TIMEOUT 180)
            if(original_captured_environment)
                set_tests_properties(interpreter-aarch64-captured-entry-proof${value}-${mode}
                                     PROPERTIES ENVIRONMENT "${original_captured_environment}")
            endif()
            set_property(
                TEST interpreter-aarch64-captured-entry-proof${value}-${mode}
                APPEND
                PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CAPTURED_READONLY=${value}")
        endforeach()
    endforeach()
endif()

# Complete original array/sort fixtures;actual private constants are readonly.
if(QJS_INTERP_FRAME_ARRAY_SORT)
    set(qjs_arm_array_test_header
        "${CMAKE_CURRENT_BINARY_DIR}/tests/arm64/interpreter-private-abi-values.h")
    add_custom_command(
        OUTPUT "${qjs_arm_array_test_header}"
        COMMAND
            "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_array_values.py"
            --header "${qjs_arm_vm_dir}/interpreter-private-abi.h" --output
            "${qjs_arm_array_test_header}"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_array_values.py"
                "${qjs_arm_vm_dir}/interpreter-private-abi.h"
        VERBATIM)
    add_executable(aarch64-default-string-sort tests/common/native_default_string_sort.c)
    target_link_libraries(aarch64-default-string-sort PRIVATE qjs)
    foreach(mode on off-zero off-one)
        add_test(NAME interpreter-aarch64-default-string-sort-${mode}
                 COMMAND aarch64-default-string-sort)
        set_tests_properties(interpreter-aarch64-default-string-sort-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "SORT_HOST_PASS" TIMEOUT 120)
    endforeach()
    set_tests_properties(interpreter-aarch64-default-string-sort-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=0")
    set_tests_properties(interpreter-aarch64-default-string-sort-off-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=1")
    foreach(variant host gc)
        add_executable(aarch64-array-copy-${variant} tests/common/native_array_copy.c
                                                     "${qjs_arm_array_test_header}")
        target_compile_options(aarch64-array-copy-${variant} PRIVATE -UNDEBUG)
        target_include_directories(aarch64-array-copy-${variant}
                                   PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/tests/arm64")
        target_link_libraries(aarch64-array-copy-${variant} PRIVATE qjs)
        if(variant STREQUAL "gc")
            target_compile_definitions(aarch64-array-copy-${variant}
                                       PRIVATE FRAME_ARRAY_COPY_GC_ONLY)
        endif()
        foreach(mode on off-zero off-one)
            add_test(NAME interpreter-aarch64-array-copy-${variant}-${mode}
                     COMMAND aarch64-array-copy-${variant})
            set_tests_properties(interpreter-aarch64-array-copy-${variant}-${mode}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "passed" TIMEOUT 120)
        endforeach()
        set_tests_properties(interpreter-aarch64-array-copy-${variant}-off-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=0")
        set_tests_properties(interpreter-aarch64-array-copy-${variant}-off-one
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=1")
    endforeach()
    add_executable(aarch64-sort-ownership tests/common/linux/native_linux_sort.c)
    target_compile_options(aarch64-sort-ownership PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-sort-ownership PRIVATE qjs)
    add_test(NAME interpreter-aarch64-sort-ownership-on COMMAND aarch64-sort-ownership)
    set_tests_properties(interpreter-aarch64-sort-ownership-on
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_SORT_SEMANTICS_OK" TIMEOUT 120)
    foreach(
        component
        CACHED_SORT_CALL
        PREPARED_SORT_CALL
        PREPARED_SORT_ENTRY
        REGISTER_INTERP
        SHARED_ENTRY
        INTERNAL_INTERP
        INTERP_FRAME
        SHARED_CALL_BYPASS
        C_INVOKE)
        foreach(value 0 1)
            string(TOLOWER "${component}" label)
            add_test(NAME interpreter-aarch64-sort-${label}-off-${value}
                     COMMAND aarch64-sort-ownership)
            set_tests_properties(
                interpreter-aarch64-sort-${label}-off-${value}
                PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                           "LINUX_SORT_SEMANTICS_OK" TIMEOUT 120)
        endforeach()
    endforeach()
    foreach(mode on off)
        foreach(kind oom growth-oom)
            add_test(NAME interpreter-aarch64-sort-${kind}-${mode} COMMAND aarch64-sort-ownership
                                                                           ${kind})
            set_tests_properties(interpreter-aarch64-sort-${kind}-${mode}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_SORT_OOM_OK" TIMEOUT 120)
        endforeach()
    endforeach()
    set_tests_properties(interpreter-aarch64-sort-oom-off interpreter-aarch64-sort-growth-oom-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_SORT_CALL=0")
endif()

if(QJS_INTERP_FRAME_NATIVE_NULL_PROTO)
    add_executable(aarch64-null-proto-public tests/common/linux/native_linux_null_proto.c)
    target_compile_options(aarch64-null-proto-public PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-null-proto-public PRIVATE qjs)
    foreach(mode on off-zero off-one register-off)
        add_test(NAME interpreter-aarch64-null-proto-public-${mode}
                 COMMAND aarch64-null-proto-public)
        set_tests_properties(
            interpreter-aarch64-null-proto-public-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_NULL_PROTO_PUBLIC_OK" TIMEOUT 120)
    endforeach()
    set_tests_properties(interpreter-aarch64-null-proto-public-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=0")
    set_tests_properties(interpreter-aarch64-null-proto-public-off-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=1")
    set_tests_properties(interpreter-aarch64-null-proto-public-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
endif()

if(QJS_INTERP_FRAME_NATIVE_NULL_PROTO AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-null-proto-paths tests/arm64/null-proto.c)
    target_compile_options(aarch64-null-proto-paths PRIVATE -UNDEBUG)
    target_compile_definitions(aarch64-null-proto-paths PRIVATE QJS_AARCH64_VM_INSTRUMENT)
    target_include_directories(aarch64-null-proto-paths PRIVATE "${qjs_arm_vm_dir}")
    target_link_libraries(aarch64-null-proto-paths PRIVATE qjs)
    foreach(
        mode
        on
        null-zero
        null-one
        admission-zero
        admission-one
        register-zero
        register-one
        frame-zero
        frame-one
        publication-zero
        publication-one)
        add_test(NAME interpreter-aarch64-null-proto-paths-${mode} COMMAND aarch64-null-proto-paths)
        set_tests_properties(interpreter-aarch64-null-proto-paths-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "ARM64_NULL_PATHS_OK" TIMEOUT 120)
    endforeach()
    set_tests_properties(interpreter-aarch64-null-proto-paths-null-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=0")
    set_tests_properties(interpreter-aarch64-null-proto-paths-null-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=1")
    set_tests_properties(interpreter-aarch64-null-proto-paths-admission-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_ADMISSION=0")
    set_tests_properties(interpreter-aarch64-null-proto-paths-admission-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LINUX_ADMISSION=1")
    set_tests_properties(interpreter-aarch64-null-proto-paths-register-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-null-proto-paths-register-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(interpreter-aarch64-null-proto-paths-frame-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    set_tests_properties(interpreter-aarch64-null-proto-paths-frame-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1")
    set_tests_properties(interpreter-aarch64-null-proto-paths-publication-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-null-proto-paths-publication-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
endif()

if(qjs_arm_arguments_enabled)
    add_executable(aarch64-arguments-constructor tests/common/native_argument_constructor.c)
    add_executable(aarch64-arguments-virtual tests/common/linux/native_linux_virtual_arguments.c)
    foreach(target aarch64-arguments-constructor aarch64-arguments-virtual)
        target_compile_options(${target} PRIVATE -UNDEBUG)
        target_link_libraries(${target} PRIVATE qjs)
    endforeach()
    add_test(NAME interpreter-aarch64-arguments-language
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_arguments.js")
    set_tests_properties(interpreter-aarch64-arguments-language
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_ARGUMENTS_OK" TIMEOUT 120)
    foreach(
        component
        FRAME_ARGUMENTS
        FRAME_ARGUMENTS_BORROW
        FRAME_ARGUMENTS_NATIVE
        FRAME_ARGUMENTS_ACCESS
        FRAME_ARGUMENTS_INDEX
        FRAME_ARGUMENTS_LENGTH
        FRAME_ARGUMENTS_FORWARD
        REGISTER_INTERP
        DEFERRED_FRAME_PUBLISH)
        string(TOLOWER "${component}" label)
        foreach(value 0 1)
            add_test(
                NAME interpreter-aarch64-arguments-${label}-${value}
                COMMAND qjs_exe -m
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_arguments.js")
            set_tests_properties(
                interpreter-aarch64-arguments-${label}-${value}
                PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                           "LINUX_ARGUMENTS_OK" TIMEOUT 120)
        endforeach()
    endforeach()
    foreach(mode on zero one)
        add_test(NAME interpreter-aarch64-arguments-constructor-${mode}
                 COMMAND aarch64-arguments-constructor)
        set_tests_properties(
            interpreter-aarch64-arguments-constructor-${mode}
            PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1" PASS_REGULAR_EXPRESSION
                       "ARGUMENT_CONSTRUCTOR_HOST_OK" TIMEOUT 120)
    endforeach()
    set_tests_properties(
        interpreter-aarch64-arguments-constructor-zero
        PROPERTIES ENVIRONMENT
                   "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
    set_tests_properties(
        interpreter-aarch64-arguments-constructor-one
        PROPERTIES ENVIRONMENT
                   "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=1")
    add_test(
        NAME interpreter-aarch64-arguments-virtual
        COMMAND aarch64-arguments-virtual
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_virtual_arguments.js")
    set_tests_properties(
        interpreter-aarch64-arguments-virtual
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1;REQUIRE_VIRTUAL_HIT=1"
                   PASS_REGULAR_EXPRESSION "VIRTUAL_ARGUMENTS_HOST_OK" TIMEOUT 120)
    add_test(NAME interpreter-aarch64-arguments-virtual-oom COMMAND aarch64-arguments-virtual oom)
    set_tests_properties(
        interpreter-aarch64-arguments-virtual-oom
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1" PASS_REGULAR_EXPRESSION
                   "VIRTUAL_ARGUMENTS_OOM_OK" TIMEOUT 120)
endif()
if(qjs_arm_arguments_enabled AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-arguments-ready tests/arm64/arguments-ready.c)
    target_compile_options(aarch64-arguments-ready PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-arguments-ready PRIVATE qjs)
    add_test(NAME interpreter-aarch64-arguments-ready COMMAND aarch64-arguments-ready)
    set_tests_properties(
        interpreter-aarch64-arguments-ready
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1" PASS_REGULAR_EXPRESSION
                   "AARCH64_ARGUMENTS_READY_OK" TIMEOUT 120)
    foreach(component FRAME_ARGUMENTS_NATIVE FRAME_ARGUMENTS_BORROW FRAME_ARGUMENTS REGISTER_INTERP
                      DEFERRED_FRAME_PUBLISH)
        string(TOLOWER "${component}" label)
        foreach(value 0 1)
            add_test(NAME interpreter-aarch64-arguments-ready-${label}-${value}
                     COMMAND aarch64-arguments-ready)
            set_tests_properties(
                interpreter-aarch64-arguments-ready-${label}-${value}
                PROPERTIES ENVIRONMENT
                           "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_${component}=${value}"
                           PASS_REGULAR_EXPRESSION "AARCH64_ARGUMENTS_READY_OK" TIMEOUT 120)
        endforeach()
    endforeach()
endif()

if(qjs_arm_arguments_enabled)
    add_executable(aarch64-arguments-access tests/arm64/arguments-access.c)
    target_compile_options(aarch64-arguments-access PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-arguments-access PRIVATE qjs)
    add_test(NAME interpreter-aarch64-arguments-access COMMAND aarch64-arguments-access)
    set_tests_properties(
        interpreter-aarch64-arguments-access
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1" PASS_REGULAR_EXPRESSION
                   "AARCH64_ARGUMENTS_ACCESS_OK" TIMEOUT 120)
    foreach(
        component
        FRAME_ARGUMENTS_ACCESS
        FRAME_ARGUMENTS_INDEX
        FRAME_ARGUMENTS_LENGTH
        NATIVE_LENGTH
        FRAME_ARGUMENTS
        REGISTER_INTERP
        DEFERRED_FRAME_PUBLISH)
        string(TOLOWER "${component}" label)
        foreach(value 0 1)
            add_test(NAME interpreter-aarch64-arguments-access-${label}-${value}
                     COMMAND aarch64-arguments-access)
            set_tests_properties(
                interpreter-aarch64-arguments-access-${label}-${value}
                PROPERTIES ENVIRONMENT
                           "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_${component}=${value}"
                           PASS_REGULAR_EXPRESSION "AARCH64_ARGUMENTS_ACCESS_OK" TIMEOUT 120)
        endforeach()
    endforeach()
endif()

if(qjs_arm_arguments_enabled AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-arguments-forward tests/arm64/arguments-forward.c)
    target_compile_options(aarch64-arguments-forward PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-arguments-forward PRIVATE qjs)
    add_test(NAME interpreter-aarch64-arguments-forward COMMAND aarch64-arguments-forward)
    set_tests_properties(
        interpreter-aarch64-arguments-forward
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1" PASS_REGULAR_EXPRESSION
                   "AARCH64_ARGUMENTS_FORWARD_OK" TIMEOUT 120)
    foreach(
        component
        FRAME_ARGUMENTS_FORWARD
        FRAME_ARGUMENTS
        FRAME_CALL_FORWARD
        FRAME_CALL_FORWARD_LEAF
        FRAME_ARGUMENTS_BORROW
        REGISTER_INTERP
        DEFERRED_FRAME_PUBLISH)
        string(TOLOWER "${component}" label)
        foreach(value 0 1)
            add_test(NAME interpreter-aarch64-arguments-forward-${label}-${value}
                     COMMAND aarch64-arguments-forward)
            set_tests_properties(
                interpreter-aarch64-arguments-forward-${label}-${value}
                PROPERTIES ENVIRONMENT
                           "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_${component}=${value}"
                           PASS_REGULAR_EXPRESSION "AARCH64_ARGUMENTS_FORWARD_OK" TIMEOUT 120)
        endforeach()
    endforeach()
endif()

if(qjs_arm_varargs_enabled)
    add_executable(aarch64-varargs-apply-public tests/common/native_apply_forward.c)
    target_compile_options(aarch64-varargs-apply-public PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-varargs-apply-public PRIVATE qjs)
    foreach(mode on zero one)
        add_test(NAME interpreter-aarch64-varargs-apply-public-${mode}
                 COMMAND aarch64-varargs-apply-public)
        set_tests_properties(
            interpreter-aarch64-varargs-apply-public-${mode}
            PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_APPLY_DIRECT=1" PASS_REGULAR_EXPRESSION
                       "APPLY_PUBLIC_HOST_OK" TIMEOUT 180)
    endforeach()
    set_property(
        TEST interpreter-aarch64-varargs-apply-public-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=0")
    set_property(
        TEST interpreter-aarch64-varargs-apply-public-one
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=1")
    foreach(fixture oom reentry)
        add_executable(aarch64-varargs-${fixture} tests/arm64/varargs-${fixture}.c)
        target_include_directories(aarch64-varargs-${fixture} PRIVATE "${qjs_arm_vm_dir}")
        target_compile_options(aarch64-varargs-${fixture} PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-varargs-${fixture} PRIVATE qjs)
    endforeach()
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-varargs-paths tests/arm64/varargs-paths.c)
        target_compile_options(aarch64-varargs-paths PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-varargs-paths PRIVATE qjs)
    endif()
    foreach(
        component
        ON
        FRAME_VARARGS
        FRAME_VARARGS_DIRECT
        FRAME_VARARGS_FUSION
        FRAME_APPLY_DIRECT
        FRAME_CALL_FORWARD
        REGISTER_INTERP
        DEFERRED_FRAME_PUBLISH)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_OBSERVE_FRAME_APPLY_DIRECT=1")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            foreach(fixture linux_varargs vm_core_spread_call vm_apply_forward)
                if(fixture STREQUAL "linux_varargs")
                    set(varargs_js_rel "tests/common/linux/test_${fixture}.js")
                else()
                    set(varargs_js_rel "tests/common/test_${fixture}.js")
                endif()
                add_test(NAME interpreter-aarch64-varargs-${fixture}-${label}
                         COMMAND qjs_exe --std -m "${CMAKE_CURRENT_SOURCE_DIR}/${varargs_js_rel}")
                set_tests_properties(interpreter-aarch64-varargs-${fixture}-${label}
                                     PROPERTIES ENVIRONMENT "${environment}" TIMEOUT 180)
            endforeach()
            set_tests_properties(interpreter-aarch64-varargs-linux_varargs-${label}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_VARARGS_OK")
            set_tests_properties(interpreter-aarch64-varargs-vm_core_spread_call-${label}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "FRAME_CORE_SPREAD_OK")
            set_tests_properties(interpreter-aarch64-varargs-vm_apply_forward-${label}
                                 PROPERTIES PASS_REGULAR_EXPRESSION "APPLY_EXTRA_SEMANTICS_OK")
            if(QJS_AARCH64_VM_INSTRUMENT)
                add_test(NAME interpreter-aarch64-varargs-paths-${label}
                         COMMAND aarch64-varargs-paths)
                set_tests_properties(
                    interpreter-aarch64-varargs-paths-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "AARCH64_VARARGS_PATHS_OK" TIMEOUT 180)
            endif()
        endforeach()
    endforeach()
    foreach(
        component
        ON
        FRAME_VARARGS_DIRECT
        FRAME_VARARGS_FUSION
        FRAME_APPLY_DIRECT
        REGISTER_INTERP
        DEFERRED_FRAME_PUBLISH
        SLOW_HOST_SHARE)
        string(TOLOWER "${component}" label)
        set(environment "")
        if(NOT component STREQUAL "ON")
            set(environment "QJS_DISABLE_${component}=0")
        endif()
        add_test(NAME interpreter-aarch64-varargs-reentry-${label} COMMAND aarch64-varargs-reentry)
        set_tests_properties(
            interpreter-aarch64-varargs-reentry-${label}
            PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                       "AARCH64_VARARGS_REENTRY_OK" TIMEOUT 180)
        if(NOT component STREQUAL "SLOW_HOST_SHARE")
            add_test(NAME interpreter-aarch64-varargs-oom-${label} COMMAND aarch64-varargs-oom)
            set_tests_properties(
                interpreter-aarch64-varargs-oom-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                           "AARCH64_VARARGS_OOM_OK" TIMEOUT 180)
        endif()
    endforeach()
endif()

# Complete source-owned indexed semantics and native execution controls.
if(qjs_arm_indexed_enabled)
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-indexed-paths tests/arm64/indexed-paths.c)
        target_compile_options(aarch64-indexed-paths PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-indexed-paths PRIVATE qjs)
    endif()
    foreach(variant ordinary coercion)
        add_executable(aarch64-indexed-${variant}-api tests/common/linux/native_linux_publication.c)
        target_compile_definitions(aarch64-indexed-${variant}-api PRIVATE QJS_TEST_INDEXED_PROTOCOL)
        if(variant STREQUAL "coercion")
            target_compile_definitions(aarch64-indexed-${variant}-api
                                       PRIVATE QJS_TEST_INDEXED_COERCION)
        endif()
        target_compile_options(aarch64-indexed-${variant}-api PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-indexed-${variant}-api PRIVATE qjs)
    endforeach()
    foreach(
        component
        ON
        FRAME_SLOW_DIRECT
        FRAME_INDEXED_STEP
        FRAME_INDEXED_OWN
        FRAME_ARRAY_APPEND
        FRAME_INSTANCEOF_STEP
        FRAME_INSTANCEOF_LEAF
        FRAME_INSTANCEOF
        DEFERRED_FRAME_PUBLISH
        REGISTER_INTERP
        INTERP_FRAME
        SLOW_HOST_SHARE
        SHARED_ENTRY)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_EXPERIMENT_ALLOCATOR=256")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            foreach(fixture indexed array_append)
                add_test(
                    NAME interpreter-aarch64-indexed-${fixture}-${label}
                    COMMAND
                        qjs_exe --std -m
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_${fixture}.js")
                string(TOUPPER "${fixture}" marker)
                set_tests_properties(
                    interpreter-aarch64-indexed-${fixture}-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "LINUX_${marker}_OK" TIMEOUT 180)
            endforeach()
            if(QJS_AARCH64_VM_INSTRUMENT)
                add_test(NAME interpreter-aarch64-indexed-paths-${label}
                         COMMAND aarch64-indexed-paths)
                set_tests_properties(
                    interpreter-aarch64-indexed-paths-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "AARCH64_INDEXED_PATHS_OK" TIMEOUT 180)
            endif()
            foreach(variant ordinary coercion)
                foreach(kind api oom)
                    if(kind STREQUAL "oom")
                        set(arguments oom)
                        set(marker LINUX_INDEXED_OOM_OK)
                    else()
                        set(arguments "")
                        set(marker LINUX_INDEXED_API_OK)
                    endif()
                    add_test(NAME interpreter-aarch64-indexed-${variant}-${kind}-${label}
                             COMMAND aarch64-indexed-${variant}-api ${arguments})
                    set_tests_properties(
                        interpreter-aarch64-indexed-${variant}-${kind}-${label}
                        PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION "${marker}"
                                   TIMEOUT 180)
                endforeach()
            endforeach()
        endforeach()
    endforeach()
endif()

# Original activation-owned literal lifetime and its scalar opcode controls.
if(qjs_arm_literals_enabled)
    foreach(variant default wide)
        add_executable(aarch64-literal-${variant}-api tests/common/linux/native_linux_publication.c)
        target_compile_definitions(aarch64-literal-${variant}-api
                                   PRIVATE QJS_TEST_VARARGS_LITERAL_PROTOCOL)
        if(variant STREQUAL "wide")
            target_compile_definitions(aarch64-literal-${variant}-api PRIVATE QJS_TEST_VARARGS_WIDE)
        endif()
        target_compile_options(aarch64-literal-${variant}-api PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-literal-${variant}-api PRIVATE qjs)
    endforeach()
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-literal-paths tests/arm64/literal-paths.c)
        target_compile_options(aarch64-literal-paths PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-literal-paths PRIVATE qjs)
    endif()
    foreach(
        component
        ON
        FRAME_ORDINARY_LITERAL
        FRAME_ORDINARY_LITERAL_TRANSITION
        FRAME_LITERAL_LAZY
        FRAME_LITERAL_REPEAT_GUARD
        FRAME_LITERAL_SPARE
        FRAME_LITERAL_VM_HIT
        FRAME_TYPEOF
        FRAME_PREDICATE
        FRAME_TRUTHINESS
        FRAME_NUMBER_TRUTH
        FRAME_STACK_INSERT
        FRAME_ITERATOR_LITERAL_SHAPES
        FRAME_ITERATOR_LITERAL_TRANSITION
        DEFERRED_FRAME_PUBLISH
        SLOW_HOST_SHARE
        REGISTER_INTERP
        INTERP_FRAME)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_EXPERIMENT_ALLOCATOR=256;QJS_OBSERVE_FRAME_ORDINARY_LITERAL=1")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            add_test(
                NAME interpreter-aarch64-literal-language-${label}
                COMMAND qjs_exe --std
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_literals.js")
            set_tests_properties(
                interpreter-aarch64-literal-language-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION "LINUX_LITERALS_OK"
                           TIMEOUT 180)
            foreach(variant default wide)
                foreach(kind api oom)
                    if(kind STREQUAL "oom")
                        set(arguments oom)
                        set(marker LINUX_VARARGS_LITERALS_OOM_OK)
                    else()
                        set(arguments "")
                        set(marker LINUX_VARARGS_LITERALS_API_OK)
                    endif()
                    add_test(NAME interpreter-aarch64-literal-${variant}-${kind}-${label}
                             COMMAND aarch64-literal-${variant}-api ${arguments})
                    set_tests_properties(
                        interpreter-aarch64-literal-${variant}-${kind}-${label}
                        PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION "${marker}"
                                   TIMEOUT 180)
                endforeach()
            endforeach()
            if(QJS_AARCH64_VM_INSTRUMENT)
                add_test(NAME interpreter-aarch64-literal-paths-${label}
                         COMMAND aarch64-literal-paths)
                set_tests_properties(
                    interpreter-aarch64-literal-paths-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "AARCH64_LITERAL_PATHS_OK" TIMEOUT 180)
            endif()
        endforeach()
    endforeach()
    foreach(component QJS_ORDINARY_LITERAL_FAIL_CACHE_ALLOC QJS_LITERAL_LAZY_FAIL_ALLOC)
        foreach(value 0 1)
            string(TOLOWER "${component}-${value}" label)
            set(environment
                "QJS_EXPERIMENT_ALLOCATOR=256;QJS_OBSERVE_FRAME_ORDINARY_LITERAL=1;${component}=${value}"
            )
            add_test(
                NAME interpreter-aarch64-literal-cache-language-${label}
                COMMAND qjs_exe --std
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_literals.js")
            set_tests_properties(
                interpreter-aarch64-literal-cache-language-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION "LINUX_LITERALS_OK"
                           TIMEOUT 180)
            foreach(variant default wide)
                add_test(NAME interpreter-aarch64-literal-cache-api-${variant}-${label}
                         COMMAND aarch64-literal-${variant}-api)
                set_tests_properties(
                    interpreter-aarch64-literal-cache-api-${variant}-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "LINUX_VARARGS_LITERALS_API_OK" TIMEOUT 180)
            endforeach()
        endforeach()
    endforeach()
    add_executable(aarch64-literal-reserve tests/common/native_literal_reserve.c)
    target_compile_options(aarch64-literal-reserve PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-literal-reserve PRIVATE qjs)
    add_test(NAME interpreter-aarch64-literal-reserve-on COMMAND aarch64-literal-reserve)
    add_test(NAME interpreter-aarch64-literal-reserve-spare-off COMMAND aarch64-literal-reserve off)
    add_test(NAME interpreter-aarch64-literal-reserve-transition-off COMMAND aarch64-literal-reserve
                                                                             off)
    add_test(NAME interpreter-aarch64-literal-reserve-ordinary-off COMMAND aarch64-literal-reserve
                                                                           off)
    set_tests_properties(
        interpreter-aarch64-literal-reserve-on interpreter-aarch64-literal-reserve-spare-off
        interpreter-aarch64-literal-reserve-transition-off
        interpreter-aarch64-literal-reserve-ordinary-off
        PROPERTIES PASS_REGULAR_EXPRESSION "LITERAL_RESERVE_OK" TIMEOUT 180)
    set_tests_properties(interpreter-aarch64-literal-reserve-spare-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_SPARE=0")
    set_tests_properties(interpreter-aarch64-literal-reserve-transition-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION=0")
    set_tests_properties(interpreter-aarch64-literal-reserve-ordinary-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL=0")
endif()

# Original GNU numeric owners, with actual AAPCS64 release and FPCR controls.
if(QJS_INTERP_FRAME_NATIVE_NUMERIC)
    add_executable(aarch64-numeric-reentry tests/arm64/numeric-reentry.c
                                           tests/arm64/numeric-saved.S)
    target_compile_options(aarch64-numeric-reentry PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-numeric-reentry PRIVATE qjs)
    foreach(component ON NATIVE_ADD_LOCAL BIGINT_RELEASE DEFERRED_FRAME_PUBLISH REGISTER_INTERP
                      INTERP_FRAME)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            add_test(NAME interpreter-aarch64-native-numeric-reentry-${label}
                     COMMAND aarch64-numeric-reentry)
            set_tests_properties(
                interpreter-aarch64-native-numeric-reentry-${label}
                PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_NUMERIC_REENTRY_OK" TIMEOUT 180)
            if(NOT component STREQUAL "ON")
                set_tests_properties(interpreter-aarch64-native-numeric-reentry-${label}
                                     PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}")
            endif()
        endforeach()
    endforeach()
endif()

if(QJS_INTERP_FRAME_NATIVE_NUMERIC)
    foreach(kind api direct)
        add_executable(aarch64-numeric-${kind} tests/common/linux/native_linux_numeric.c)
        target_compile_features(aarch64-numeric-${kind} PRIVATE c_std_11)
        target_compile_options(aarch64-numeric-${kind} PRIVATE -UNDEBUG -Wall -Wextra -Werror)
        target_link_libraries(aarch64-numeric-${kind} PRIVATE qjs)
        if(kind STREQUAL "direct")
            target_compile_definitions(aarch64-numeric-${kind} PRIVATE QJS_TEST_NUMERIC_DIRECT)
            target_compile_options(aarch64-numeric-${kind} PRIVATE -frounding-math)
        endif()
    endforeach()
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-numeric-paths tests/arm64/numeric-paths.c)
        target_compile_options(aarch64-numeric-paths PRIVATE -UNDEBUG -frounding-math)
        if(QJS_INTERP_FRAME_COMPILER_PROJECTION AND QJS_BACKPORT_CONTEXT_OOM)
            target_compile_definitions(aarch64-numeric-paths PRIVATE QJS_TEST_COMPILER_PROJECTION)
        endif()
        target_link_libraries(aarch64-numeric-paths PRIVATE qjs)
    endif()
    foreach(
        component
        ON
        NATIVE_ADD_LOCAL
        BIGINT_RELEASE
        DEFERRED_FRAME_PUBLISH
        REGISTER_INTERP
        INTERP_FRAME
        INTERNAL_INTERP)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_EXPERIMENT_ALLOCATOR=256")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            add_test(NAME interpreter-aarch64-native-numeric-language-${label}
                     COMMAND qjs_exe --std -m
                             "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_numeric.js")
            set_tests_properties(
                interpreter-aarch64-native-numeric-language-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                           "LINUX_NUMERIC_FAMILY_OK" TIMEOUT 180)
            foreach(kind api direct oom)
                if(kind STREQUAL "oom")
                    set(target aarch64-numeric-api)
                    set(arguments oom)
                    set(marker LINUX_NUMERIC_OOM_OK)
                else()
                    set(target aarch64-numeric-${kind})
                    set(arguments "")
                    if(kind STREQUAL "direct")
                        set(marker LINUX_NUMERIC_DIRECT_OK)
                    else()
                        set(marker LINUX_NUMERIC_PUBLIC_OK)
                    endif()
                endif()
                add_test(NAME interpreter-aarch64-native-numeric-${kind}-${label}
                         COMMAND ${target} ${arguments})
                set_tests_properties(
                    interpreter-aarch64-native-numeric-${kind}-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION "${marker}"
                               TIMEOUT 180)
            endforeach()
            # INTERNAL_INTERP disables the full C frame owner; its language,
            # API/OOM and converter cases above retain the original fallback.
            if(QJS_AARCH64_VM_INSTRUMENT AND NOT component STREQUAL "INTERNAL_INTERP")
                add_test(NAME interpreter-aarch64-native-numeric-paths-${label}
                         COMMAND aarch64-numeric-paths)
                set_tests_properties(
                    interpreter-aarch64-native-numeric-paths-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "AARCH64_NUMERIC_PATHS_OK" TIMEOUT 180)
            endif()
        endforeach()
    endforeach()
endif()

# Complete accepted GNU string owners and actual AAPCS64 entry/path controls.
if(QJS_INTERP_FRAME_STRING_WORKERS
   AND QJS_FRAME_EXPERIMENTAL_ALLOCATOR
   AND TARGET interpreter-test-string_concat)
    # Retain the original strict positive/negative allocation bounds. ARM now
    # carries this capability; a missing capability define inverted the test.
    target_compile_definitions(interpreter-test-string_concat PRIVATE FRAME_TEST_STRING_POOL_NATIVE)
endif()

if(QJS_INTERP_FRAME_STRING_WORKERS)
    add_executable(aarch64-string-ownership tests/common/linux/native_linux_strings.c)
    target_compile_options(aarch64-string-ownership PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-string-ownership PRIVATE qjs Threads::Threads)
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-string-paths tests/arm64/string-paths.c)
        if(qjs_arm_indexed_enabled)
            target_compile_definitions(aarch64-string-paths PRIVATE QJS_TEST_NATIVE_STRING_INDEX)
        endif()
        target_compile_options(aarch64-string-paths PRIVATE -UNDEBUG)
        target_link_libraries(aarch64-string-paths PRIVATE qjs)
    endif()
    foreach(
        component
        ON
        NATIVE_ADD_BOUNDARY
        NATIVE_ADD_LOCAL
        LOCAL_ROPE_APPEND
        LOCAL_ROPE_SPARE
        FRAME_NATIVE_ROPE_APPEND
        CONCAT_ROPE
        SMALL_CHAR_CACHE
        FRAME_STRING_INDEX
        REGISTER_INTERP
        INTERP_FRAME
        DEFERRED_FRAME_PUBLISH)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_EXPERIMENT_ALLOCATOR=256")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            add_test(NAME interpreter-aarch64-native-string-concat-${label}
                     COMMAND qjs_exe --std -m
                             "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
            set_tests_properties(
                interpreter-aarch64-native-string-concat-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                           "CONCAT_ROPE_SMOKE_PASSED" TIMEOUT 180)
            add_test(NAME interpreter-aarch64-native-string-locale-${label}
                     COMMAND qjs_exe --std -m
                             "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_locale_compare.js")
            set_tests_properties(
                interpreter-aarch64-native-string-locale-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                           "LOCALE_COMPARE 67789 PASS" TIMEOUT 180)
            if(TARGET aarch64-string-paths)
                add_test(NAME interpreter-aarch64-native-string-paths-${label}
                         COMMAND aarch64-string-paths)
                set_tests_properties(
                    interpreter-aarch64-native-string-paths-${label}
                    PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                               "AARCH64_STRING_PATHS_OK" TIMEOUT 180)
            endif()
            if(component STREQUAL "ON"
               OR component STREQUAL "SMALL_CHAR_CACHE"
               OR component STREQUAL "REGISTER_INTERP"
               OR component STREQUAL "INTERP_FRAME")
                set(owner_environment "")
                if(NOT component STREQUAL "ON")
                    set(owner_environment "QJS_DISABLE_${component}=${value}")
                endif()
                add_test(NAME interpreter-aarch64-native-string-ownership-${label}
                         COMMAND aarch64-string-ownership)
                set_tests_properties(
                    interpreter-aarch64-native-string-ownership-${label}
                    PROPERTIES ENVIRONMENT "${owner_environment}" PASS_REGULAR_EXPRESSION
                               "LINUX_STRING_OWNERSHIP_OK" TIMEOUT 180)
            endif()
        endforeach()
    endforeach()
endif()

if(QJS_INTERP_FRAME_STACK_INSERT
   AND qjs_arm_indexed_enabled
   AND QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-stack-insert-paths tests/arm64/stack-insert.c)
    target_compile_options(aarch64-stack-insert-paths PRIVATE -UNDEBUG)
    target_link_libraries(aarch64-stack-insert-paths PRIVATE qjs)
    foreach(component ON FRAME_STACK_INSERT DEFERRED_FRAME_PUBLISH REGISTER_INTERP INTERP_FRAME)
        if(component STREQUAL "ON")
            set(values on)
        else()
            set(values 0 1)
        endif()
        foreach(value ${values})
            string(TOLOWER "${component}-${value}" label)
            set(environment "QJS_EXPERIMENT_ALLOCATOR=256")
            if(NOT component STREQUAL "ON")
                list(APPEND environment "QJS_DISABLE_${component}=${value}")
            endif()
            add_test(NAME interpreter-aarch64-stack-insert-paths-${label}
                     COMMAND aarch64-stack-insert-paths)
            set_tests_properties(
                interpreter-aarch64-stack-insert-paths-${label}
                PROPERTIES ENVIRONMENT "${environment}" PASS_REGULAR_EXPRESSION
                           "AARCH64_STACK_INSERT_PATHS_OK" TIMEOUT 120)
        endforeach()
    endforeach()
endif()

# Source-owned frame-free call family;all controls run in fresh processes.
if(QJS_INTERP_FRAME_CALL_LEAVES)
    foreach(body leaf_entries character_set_leaf compound_leaf)
        add_test(NAME interpreter-aarch64-call-leaves-${body}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_${body}.js")
    endforeach()
    add_test(
        NAME interpreter-aarch64-call-leaves-integer-expression
        COMMAND qjs_exe --std
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_integer_expression.js")
    foreach(body character compound)
        add_executable(aarch64-${body}-leaf-host "tests/common/embedding/${body}-leaf/main.c")
        target_link_libraries(aarch64-${body}-leaf-host PRIVATE qjs)
        foreach(mode ON 0 1)
            add_test(NAME interpreter-aarch64-call-leaves-${body}-host-${mode}
                     COMMAND aarch64-${body}-leaf-host)
            if(NOT mode STREQUAL "ON")
                if(body STREQUAL "character")
                    set_tests_properties(
                        interpreter-aarch64-call-leaves-${body}-host-${mode}
                        PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CHARACTER_SET_LEAF=${mode}")
                else()
                    set_tests_properties(
                        interpreter-aarch64-call-leaves-${body}-host-${mode}
                        PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_COMPOUND_LEAF=${mode}")
                endif()
            endif()
        endforeach()
    endforeach()
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-call-leaf-owners tests/arm64/call-leaf-owners.c)
        target_link_libraries(aarch64-call-leaf-owners PRIVATE qjs)
        foreach(component ON AARCH64_HOST_RETURN DEFERRED_FRAME_PUBLISH FRAME_LEAF_ENTRY
                          REGISTER_INTERP INTERP_FRAME)
            foreach(value 0 1)
                if(component STREQUAL "ON" AND value STREQUAL "1")
                    continue()
                endif()
                add_test(NAME interpreter-aarch64-call-leaves-owners-${component}-${value}
                         COMMAND aarch64-call-leaf-owners)
                set_tests_properties(
                    interpreter-aarch64-call-leaves-owners-${component}-${value}
                    PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_CALL_LEAF_OWNERS_OK")
                if(NOT component STREQUAL "ON")
                    set_tests_properties(
                        interpreter-aarch64-call-leaves-owners-${component}-${value}
                        PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}")
                endif()
            endforeach()
        endforeach()
        add_executable(aarch64-call-leaves tests/arm64/call-leaves.c)
        target_link_libraries(aarch64-call-leaves PRIVATE qjs)
        add_test(NAME interpreter-aarch64-call-leaves-paths COMMAND aarch64-call-leaves)
        set_tests_properties(interpreter-aarch64-call-leaves-paths
                             PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_CALL_LEAVES_OK")
        foreach(
            component
            NATIVE_CHILD_LEAF
            THIS_FIELD_LEAF
            NATIVE_INT_EXPRESSION_LEAF
            FRAME_LEAF_ENTRY
            FRAME_CHARACTER_SET_LEAF
            FRAME_COMPOUND_LEAF
            AARCH64_HOST_RETURN
            DEFERRED_FRAME_PUBLISH
            REGISTER_INTERP
            INTERP_FRAME)
            foreach(value 0 1)
                add_test(NAME interpreter-aarch64-call-leaves-paths-${component}-${value}
                         COMMAND aarch64-call-leaves)
                set_tests_properties(
                    interpreter-aarch64-call-leaves-paths-${component}-${value}
                    PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}"
                               PASS_REGULAR_EXPRESSION "AARCH64_CALL_LEAVES_OK")
            endforeach()
        endforeach()

    endif()
endif()

# Entire source-owned base scalar family,including observed last-owner fallback.
if(QJS_INTERP_FRAME_SCALAR_OPS)
    set(qjs_scalar_base_env
        "QJS_DISABLE_FRAME_LEAF_ENTRY=1;QJS_DISABLE_NATIVE_CHILD_LEAF=1;QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF=1"
    )
    if(QJS_AARCH64_VM_INSTRUMENT)
        add_executable(aarch64-scalar-ops tests/arm64/scalar-ops.c)
        target_link_libraries(aarch64-scalar-ops PRIVATE qjs)
        add_executable(aarch64-scalar-owners tests/arm64/scalar-owners.c)
        target_link_libraries(aarch64-scalar-owners PRIVATE qjs)
        target_include_directories(aarch64-scalar-owners PRIVATE "${qjs_arm_vm_dir}")
    endif()
    foreach(component ON SCALAR PUBLISH REGISTER FRAME)
        foreach(value 0 1)
            if(component STREQUAL "ON" AND value STREQUAL "1")
                continue()
            endif()
            set(scalar_env "${qjs_scalar_base_env}")
            if(component STREQUAL "SCALAR")
                list(APPEND scalar_env "QJS_DISABLE_AARCH64_SCALAR_OPS=${value}")
            elseif(component STREQUAL "PUBLISH")
                list(APPEND scalar_env "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=${value}")
            elseif(component STREQUAL "REGISTER")
                list(APPEND scalar_env "QJS_DISABLE_REGISTER_INTERP=${value}")
            elseif(component STREQUAL "FRAME")
                list(APPEND scalar_env "QJS_DISABLE_INTERP_FRAME=${value}")
            endif()
            add_test(NAME interpreter-aarch64-scalar-semantics-${component}-${value}
                     COMMAND qjs_exe --std
                             "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_aarch64_scalar_ops.js")
            set_tests_properties(
                interpreter-aarch64-scalar-semantics-${component}-${value}
                PROPERTIES ENVIRONMENT "${scalar_env}" PASS_REGULAR_EXPRESSION
                           "AARCH64_SCALAR_SEMANTICS_OK")
            if(QJS_AARCH64_VM_INSTRUMENT)
                add_test(NAME interpreter-aarch64-scalar-paths-${component}-${value}
                         COMMAND aarch64-scalar-ops)
                add_test(NAME interpreter-aarch64-scalar-owners-${component}-${value}
                         COMMAND aarch64-scalar-owners)
                set_tests_properties(
                    interpreter-aarch64-scalar-paths-${component}-${value}
                    PROPERTIES ENVIRONMENT "${scalar_env}" PASS_REGULAR_EXPRESSION
                               "AARCH64_SCALAR_PATHS_OK")
                set_tests_properties(
                    interpreter-aarch64-scalar-owners-${component}-${value}
                    PROPERTIES ENVIRONMENT "${scalar_env}" PASS_REGULAR_EXPRESSION
                               "AARCH64_SCALAR_OWNERS_OK")
            endif()
        endforeach()
    endforeach()
endif()

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(aarch64-return-alias tests/arm64/return-alias.c)
    if(QJS_AARCH64_LINEAR_RETURN)
        target_compile_definitions(aarch64-return-alias PRIVATE QJS_TEST_LINEAR_RETURN)
    endif()
    target_link_libraries(aarch64-return-alias PRIVATE qjs)
    target_include_directories(aarch64-return-alias PRIVATE "${qjs_arm_vm_dir}")
    target_compile_options(aarch64-return-alias PRIVATE -UNDEBUG)
    target_link_options(aarch64-return-alias PRIVATE -rdynamic)
    foreach(
        mode
        native
        publication-zero
        publication-one
        register-zero
        register-one
        frame-zero
        frame-one
        legacy
        host-return-off)
        add_test(NAME interpreter-aarch64-return-alias-${mode} COMMAND aarch64-return-alias
                                                                       candidate)
        set_tests_properties(
            interpreter-aarch64-return-alias-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_RETURN_ALIAS_OK" FAIL_REGULAR_EXPRESSION
                       "RETURN_ALIAS_EXCEPTION" TIMEOUT 120)
    endforeach()
    set_tests_properties(interpreter-aarch64-return-alias-publication-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_tests_properties(interpreter-aarch64-return-alias-publication-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
    set_tests_properties(interpreter-aarch64-return-alias-register-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
    set_tests_properties(interpreter-aarch64-return-alias-register-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(interpreter-aarch64-return-alias-frame-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    set_tests_properties(interpreter-aarch64-return-alias-frame-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1")
    set_tests_properties(
        interpreter-aarch64-return-alias-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
    set_tests_properties(interpreter-aarch64-return-alias-host-return-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_AARCH64_HOST_RETURN=1")
    foreach(mode native legacy)
        add_test(NAME interpreter-aarch64-return-alias-oom-${mode} COMMAND aarch64-return-alias oom)
        set_tests_properties(
            interpreter-aarch64-return-alias-oom-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "AARCH64_RETURN_ALIAS_OOM_OK"
                       FAIL_REGULAR_EXPRESSION "RETURN_ALIAS_EXCEPTION" TIMEOUT 120)
    endforeach()
    set_tests_properties(
        interpreter-aarch64-return-alias-oom-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_REGISTER_INTERP=1;QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1"
    )
endif()

foreach(mode native register-off)
    add_test(NAME interpreter-aarch64-number-local-${mode}
             COMMAND qjs_exe --std ${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/number-local.js)
    set_tests_properties(interpreter-aarch64-number-local-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                             "NUMBER_LOCAL_OK")
endforeach()
set_tests_properties(interpreter-aarch64-number-local-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")

foreach(mode native register-off legacy)
    add_test(NAME interpreter-aarch64-fast-vm-${mode}
             COMMAND qjs_exe --std ${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/fast-vm.js)
    set_tests_properties(interpreter-aarch64-fast-vm-${mode} PROPERTIES TIMEOUT 180)
endforeach()
set_tests_properties(interpreter-aarch64-fast-vm-register-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-aarch64-fast-vm-legacy
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")

add_test(
    NAME interpreter-aarch64-register-image
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/verify/check_vm.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --image
        "$<TARGET_FILE:qjs_exe>" --archive "$<TARGET_FILE:qjs>" --ar "${CMAKE_AR}" --readelf
        "${CMAKE_READELF}")

if(QJS_AARCH64_VM_INSTRUMENT)
    add_executable(interpreter-aarch64-register-vm tests/arm64/register-vm.c)
    target_link_libraries(interpreter-aarch64-register-vm PRIVATE qjs)
    target_include_directories(interpreter-aarch64-register-vm PRIVATE "${qjs_arm_vm_dir}")
    target_link_options(interpreter-aarch64-register-vm PRIVATE -rdynamic)
    foreach(mode native register-off legacy)
        add_test(NAME interpreter-aarch64-register-vm-${mode}
                 COMMAND interpreter-aarch64-register-vm ${mode})
    endforeach()
    set_tests_properties(interpreter-aarch64-register-vm-register-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-aarch64-register-vm-legacy
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endif()
