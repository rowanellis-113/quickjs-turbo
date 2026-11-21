# Complete null-prototype cohort,public ownership/reentry and allocator faults.
add_executable(linux-null-proto tests/common/linux/native_linux_null_proto.c)
target_compile_features(linux-null-proto PRIVATE c_std_11)
target_compile_options(linux-null-proto PRIVATE -Wall -Wextra -Werror -UNDEBUG)
target_link_libraries(linux-null-proto PRIVATE qjs)
foreach(mode on null-zero null-one publish-off frame-off register-off)
    add_test(NAME linux-native-null-proto-${mode} COMMAND linux-null-proto)
    set_tests_properties(
        linux-native-null-proto-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_NULL_PROTO_PUBLIC_OK" TIMEOUT 180)
endforeach()
set_property(
    TEST linux-native-null-proto-null-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=0")
set_property(
    TEST linux-native-null-proto-null-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_NATIVE_NULL_PROTO=1")
set_property(
    TEST linux-native-null-proto-publish-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-null-proto-frame-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
set_property(
    TEST linux-native-null-proto-register-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
# Core C property consumers share the complete ordinary numeric-array leaf.
add_executable(linux-core-array tests/common/linux/native_linux_core_array.c)
target_compile_features(linux-core-array PRIVATE c_std_11)
target_compile_options(linux-core-array PRIVATE -Wall -Wextra -Werror -UNDEBUG)
target_link_libraries(linux-core-array PRIVATE qjs)
foreach(mode on frame-off property-off publish-off)
    add_test(NAME linux-native-core-array-${mode} COMMAND linux-core-array)
    set_tests_properties(
        linux-native-core-array-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_CORE_ARRAY_PUBLIC_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-core-array-frame-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
set_property(
    TEST linux-native-core-array-property-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=0")
set_property(
    TEST linux-native-core-array-publish-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
# Complete GNU global hints: inherited lifecycle,activation collisions,public
# ownership/realm/GC/interrupt and warmed allocator fault recovery.
add_executable(linux-global-bindings-api tests/common/linux/native_linux_global_bindings.c)
target_compile_features(linux-global-bindings-api PRIVATE c_std_11)
target_compile_options(linux-global-bindings-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-global-bindings-api PRIVATE qjs Threads::Threads)
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
    add_test(NAME linux-native-global-bindings-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_global_bindings.js")
    set_tests_properties(
        linux-native-global-bindings-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_BINDINGS_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(mode on global-zero property-zero publish-zero frame-zero)
    add_test(NAME linux-native-global-bindings-inherited-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_global_binding.js")
    set_tests_properties(
        linux-native-global-bindings-inherited-${mode}
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
    add_test(NAME linux-native-global-bindings-api-${mode} COMMAND linux-global-bindings-api)
    set_tests_properties(
        linux-native-global-bindings-api-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_GLOBAL_BINDINGS_PUBLIC_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(mode on global publish frame)
    add_test(NAME linux-native-global-bindings-oom-${mode} COMMAND linux-global-bindings-api oom)
    set_tests_properties(
        linux-native-global-bindings-oom-${mode}
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
            set(test_name linux-native-global-bindings-${kind}${name}-${value})
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
    if(TEST linux-native-global-bindings-oom-${name})
        set_property(
            TEST linux-native-global-bindings-oom-${name}
            APPEND
            PROPERTY ENVIRONMENT "${control}=0")
    endif()
endforeach()

# Complete GNU numeric/local ownership and actual SysV leaf/converter entries.
foreach(kind api direct)
    add_executable(linux-numeric-${kind} tests/common/linux/native_linux_numeric.c)
    target_compile_features(linux-numeric-${kind} PRIVATE c_std_11)
    target_compile_options(linux-numeric-${kind} PRIVATE -UNDEBUG -Wall -Wextra -Werror)
    target_link_libraries(linux-numeric-${kind} PRIVATE qjs)
    if(kind STREQUAL "direct")
        target_compile_definitions(linux-numeric-${kind} PRIVATE QJS_TEST_NUMERIC_DIRECT)
        target_compile_options(linux-numeric-${kind} PRIVATE -frounding-math)
    endif()
endforeach()
foreach(
    mode
    on
    local-zero
    local-one
    release-zero
    release-one
    publish-zero
    frame-zero
    register-zero
    internal-zero)
    add_test(NAME linux-native-numeric-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_numeric.js")
    add_test(NAME linux-native-numeric-api-${mode} COMMAND linux-numeric-api)
    set_tests_properties(linux-native-numeric-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                 "LINUX_NUMERIC_FAMILY_OK")
    set_tests_properties(linux-native-numeric-api-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                     "LINUX_NUMERIC_PUBLIC_OK")
    set_tests_properties(linux-native-numeric-${mode} linux-native-numeric-api-${mode}
                         PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 120)
endforeach()
foreach(pair "local;QJS_DISABLE_NATIVE_ADD_LOCAL" "release;QJS_DISABLE_BIGINT_RELEASE")
    list(GET pair 0 name)
    list(GET pair 1 control)
    foreach(value zero one)
        if(value STREQUAL "zero")
            set(number 0)
        else()
            set(number 1)
        endif()
        set_property(
            TEST linux-native-numeric-${name}-${value} linux-native-numeric-api-${name}-${value}
            APPEND
            PROPERTY ENVIRONMENT "${control}=${number}")
    endforeach()
endforeach()
foreach(pair "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH" "frame;QJS_DISABLE_INTERP_FRAME"
             "register;QJS_DISABLE_REGISTER_INTERP" "internal;QJS_DISABLE_INTERNAL_INTERP")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST linux-native-numeric-${name}-zero linux-native-numeric-api-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
endforeach()
foreach(mode on local release publish frame)
    add_test(NAME linux-native-numeric-oom-${mode} COMMAND linux-numeric-api oom)
    set_tests_properties(
        linux-native-numeric-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_NUMERIC_OOM_OK" TIMEOUT 180)
endforeach()
foreach(pair "local;QJS_DISABLE_NATIVE_ADD_LOCAL" "release;QJS_DISABLE_BIGINT_RELEASE"
             "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH" "frame;QJS_DISABLE_INTERP_FRAME")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST linux-native-numeric-oom-${name}
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
endforeach()
foreach(mode on zero one)
    add_test(NAME linux-native-numeric-direct-${mode} COMMAND linux-numeric-direct)
    set_tests_properties(
        linux-native-numeric-direct-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_NUMERIC_DIRECT_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-numeric-direct-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_BIGINT_RELEASE=0")
set_property(
    TEST linux-native-numeric-direct-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_BIGINT_RELEASE=1")
# Complete native comparison tiers,public API and direct actual SysV entry.
foreach(kind api direct)
    add_executable(linux-comparison-${kind} tests/common/linux/native_linux_comparisons.c)
    target_compile_options(linux-comparison-${kind} PRIVATE -UNDEBUG -Wall -Wextra -Werror)
    target_link_libraries(linux-comparison-${kind} PRIVATE qjs)
    if(kind STREQUAL "direct")
        target_compile_definitions(linux-comparison-${kind} PRIVATE QJS_TEST_DIRECT_COMPARISON)
    endif()
endforeach()
foreach(
    mode
    on
    module-zero
    module-one
    strict-zero
    strict-one
    loose-zero
    loose-one
    c-zero
    c-one
    reference-zero
    reference-one
    strings-zero
    null-zero
    object-null-zero
    publish-zero
    frame-zero
    register-zero)
    add_test(NAME linux-native-comparisons-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_comparisons.js")
    set_tests_properties(
        linux-native-comparisons-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_COMPARISON_FAMILY_OK" TIMEOUT 120)
endforeach()
foreach(
    pair
    "module;QJS_DISABLE_LINUX_COMPARISONS" "strict;QJS_DISABLE_LINUX_STRICT_COMPARE"
    "loose;QJS_DISABLE_LINUX_LOOSE_COMPARE" "c;QJS_DISABLE_LINUX_C_IDENTITY"
    "reference;QJS_DISABLE_FRAME_REFERENCE_EQUALITY")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST linux-native-comparisons-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
    set_property(
        TEST linux-native-comparisons-${name}-one
        APPEND
        PROPERTY ENVIRONMENT "${control}=1")
endforeach()
foreach(
    pair
    "strings;QJS_DISABLE_FRAME_LOOSE_EQ_STRINGS"
    "null;QJS_DISABLE_FRAME_LOOSE_EQ_NULL"
    "object-null;QJS_DISABLE_FRAME_LOOSE_EQ_OBJECT_NULL"
    "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH"
    "frame;QJS_DISABLE_INTERP_FRAME"
    "register;QJS_DISABLE_REGISTER_INTERP")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST linux-native-comparisons-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
endforeach()
foreach(
    mode
    on
    module-zero
    strict-zero
    loose-zero
    c-zero
    reference-zero
    publish-zero
    frame-zero
    register-zero)
    get_property(
        comparison_environment
        TEST linux-native-comparisons-${mode}
        PROPERTY ENVIRONMENT)
    foreach(kind api direct)
        add_test(NAME linux-native-comparisons-${kind}-${mode} COMMAND linux-comparison-${kind})
        set_tests_properties(
            linux-native-comparisons-${kind}-${mode}
            PROPERTIES ENVIRONMENT "${comparison_environment}" PASS_REGULAR_EXPRESSION
                       "LINUX_COMPARISON_API_OK" TIMEOUT 120)
    endforeach()
endforeach()
foreach(mode on module-zero c-zero reference-zero publish-zero frame-zero)
    get_property(
        comparison_environment
        TEST linux-native-comparisons-${mode}
        PROPERTY ENVIRONMENT)
    add_test(NAME linux-native-comparisons-oom-${mode} COMMAND linux-comparison-api oom)
    set_tests_properties(
        linux-native-comparisons-oom-${mode}
        PROPERTIES ENVIRONMENT "${comparison_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_COMPARISON_OOM_OK" TIMEOUT 120)
endforeach()

# Complete RegExp builtin routes use actual core types and public SysV calls.
add_executable(linux-regexp-api tests/common/linux/native_linux_regexp.c)
target_compile_options(linux-regexp-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-regexp-api PRIVATE qjs)
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
    add_test(NAME linux-native-regexp-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_regexp.js")
    set_tests_properties(
        linux-native-regexp-${mode}
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
        TEST linux-native-regexp-${name}-zero
        APPEND
        PROPERTY ENVIRONMENT "${control}=0")
    set_property(
        TEST linux-native-regexp-${name}-one
        APPEND
        PROPERTY ENVIRONMENT "${control}=1")
endforeach()
foreach(pair "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH" "frame;QJS_DISABLE_INTERP_FRAME"
             "register;QJS_DISABLE_REGISTER_INTERP")
    list(GET pair 0 name)
    list(GET pair 1 control)
    set_property(
        TEST linux-native-regexp-${name}-zero
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
    add_test(NAME linux-native-regexp-api-${mode} COMMAND linux-regexp-api)
    set_tests_properties(
        linux-native-regexp-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_REGEXP_API_OK" TIMEOUT 120)
    if(NOT mode STREQUAL "on")
        get_property(
            regexp_environment
            TEST linux-native-regexp-${mode}
            PROPERTY ENVIRONMENT)
        set_property(TEST linux-native-regexp-api-${mode} PROPERTY ENVIRONMENT
                                                                   "${regexp_environment}")
    endif()
endforeach()
foreach(mode on module-zero argv-zero frame-zero publish-zero)
    add_test(NAME linux-native-regexp-oom-${mode} COMMAND linux-regexp-api oom)
    set_tests_properties(
        linux-native-regexp-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_REGEXP_OWNED_OOM_OK" TIMEOUT 120)
    if(NOT mode STREQUAL "on")
        get_property(
            regexp_environment
            TEST linux-native-regexp-${mode}
            PROPERTY ENVIRONMENT)
        set_property(TEST linux-native-regexp-oom-${mode} PROPERTY ENVIRONMENT
                                                                   "${regexp_environment}")
    endif()
endforeach()

# Public API and private observation tests for the actual Linux archive.
if(QJS_PROPERTY_IC)
    add_executable(linux-property-api tests/common/linux/native_linux_properties.c)
    target_compile_options(linux-property-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
    target_link_libraries(linux-property-api PRIVATE qjs)
    foreach(
        mode
        on
        own-zero
        own-one
        proto-zero
        proto-one
        persist-zero
        persist-one
        direct-zero
        direct-one
        length-zero
        length-one
        local-zero
        symbol-zero
        publish-zero
        frame-zero
        register-zero)
        add_test(NAME linux-native-properties-${mode}
                 COMMAND qjs_exe --std -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_properties.js")
        set_tests_properties(
            linux-native-properties-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_PROPERTY_FAMILY_OK" TIMEOUT 120)
    endforeach()
    foreach(kind own proto persist direct length)
        if(kind STREQUAL "own")
            set(property_control QJS_DISABLE_NATIVE_OWN_BYTECODE)
        elseif(kind STREQUAL "proto")
            set(property_control QJS_DISABLE_PROTO_LOAD_CACHE)
        elseif(kind STREQUAL "persist")
            set(property_control QJS_DISABLE_PROTO_LOAD_PERSIST)
        elseif(kind STREQUAL "direct")
            set(property_control QJS_DISABLE_PROTO_DIRECT)
        else()
            set(property_control QJS_DISABLE_NATIVE_LENGTH)
        endif()
        set_property(
            TEST linux-native-properties-${kind}-zero
            APPEND
            PROPERTY ENVIRONMENT "${property_control}=0")
        set_property(
            TEST linux-native-properties-${kind}-one
            APPEND
            PROPERTY ENVIRONMENT "${property_control}=1")
    endforeach()
    foreach(
        pair
        "local;QJS_DISABLE_FRAME_LOCAL_FIELD" "symbol;QJS_DISABLE_SYMBOL_CASE"
        "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH" "frame;QJS_DISABLE_INTERP_FRAME"
        "register;QJS_DISABLE_REGISTER_INTERP")
        list(GET pair 0 name)
        list(GET pair 1 control)
        set_property(
            TEST linux-native-properties-${name}-zero
            APPEND
            PROPERTY ENVIRONMENT "${control}=0")
    endforeach()
    foreach(
        mode
        on
        own-zero
        proto-zero
        persist-zero
        direct-zero
        publish-zero
        frame-zero)
        add_test(NAME linux-native-properties-api-${mode} COMMAND linux-property-api)
        set_tests_properties(
            linux-native-properties-api-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_PROPERTY_API_OK" TIMEOUT 120)
        if(NOT mode STREQUAL "on")
            get_property(
                property_environment
                TEST linux-native-properties-${mode}
                PROPERTY ENVIRONMENT)
            set_property(TEST linux-native-properties-api-${mode}
                         PROPERTY ENVIRONMENT "${property_environment}")
        endif()
    endforeach()
    foreach(
        mode
        on
        own-zero
        proto-zero
        persist-zero
        direct-zero
        local-zero
        symbol-zero
        publish-zero
        frame-zero)
        add_test(
            NAME linux-native-property-routes-${mode}
            COMMAND qjs_exe --std
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_property_routes.js")
        set_tests_properties(
            linux-native-property-routes-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_PROPERTY_ROUTES_OK" TIMEOUT 120)
        if(NOT mode STREQUAL "on")
            get_property(
                property_environment
                TEST linux-native-properties-${mode}
                PROPERTY ENVIRONMENT)
            set_property(TEST linux-native-property-routes-${mode}
                         PROPERTY ENVIRONMENT "${property_environment}")
        endif()
    endforeach()
    foreach(mode on own-zero frame-zero)
        add_test(NAME linux-native-properties-reader-oom-${mode} COMMAND linux-property-api
                                                                         reader-oom)
        set_tests_properties(
            linux-native-properties-reader-oom-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_PROPERTY_READER_OOM_OK" TIMEOUT 120)
        if(NOT mode STREQUAL "on")
            get_property(
                property_environment
                TEST linux-native-properties-${mode}
                PROPERTY ENVIRONMENT)
            set_property(TEST linux-native-properties-reader-oom-${mode}
                         PROPERTY ENVIRONMENT "${property_environment}")
        endif()
    endforeach()
endif()
add_executable(linux-frame-quota tests/common/linux/native_linux_frame_quota.c)
target_link_libraries(linux-frame-quota PRIVATE qjs)
add_test(NAME linux-native-frame-quota COMMAND linux-frame-quota)
set_tests_properties(linux-native-frame-quota PROPERTIES PASS_REGULAR_EXPRESSION
                                                         "LINUX_FRAME_QUOTA_REENTRY_INTERRUPT_OK")
add_executable(linux-shared-tls tests/common/linux/native_linux_shared_tls.c)
target_link_libraries(linux-shared-tls PRIVATE qjs Threads::Threads)
foreach(mode on off-zero off-one retained-scoped)
    add_test(NAME linux-native-shared-${mode} COMMAND linux-shared-tls)
    set_tests_properties(linux-native-shared-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                "LINUX_SHARED_TLS_OK")
endforeach()
set_tests_properties(linux-native-shared-off-zero PROPERTIES ENVIRONMENT
                                                             "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(linux-native-shared-off-one PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_SHARED_ENTRY=1")
set_tests_properties(linux-native-shared-retained-scoped PROPERTIES ENVIRONMENT
                                                                    "QJS_RETAIN_SCOPED_HOST=0")
add_test(NAME linux-native-stack
         COMMAND qjs_exe "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_vm_stack.js")
set_tests_properties(linux-native-stack PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_VM_STACK_OK")
add_test(NAME linux-native-entry
         COMMAND qjs_exe
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_internal_entry.js")
foreach(mode on zero one frame-off)
    add_test(NAME linux-native-publication-${mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_publication.js")
    set_tests_properties(
        linux-native-publication-${mode} PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256"
                                                    PASS_REGULAR_EXPRESSION "LINUX_PUBLICATION_OK")
endforeach()
set_property(
    TEST linux-native-publication-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-publication-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
set_property(
    TEST linux-native-publication-frame-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_MIN_CALL_FRAME=1")

add_executable(linux-publication-api tests/common/linux/native_linux_publication.c)
target_compile_options(linux-publication-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-publication-api PRIVATE qjs)
foreach(
    mode
    on
    zero
    one
    shared-off
    register-off
    frame-off
    owned-off)
    add_test(NAME linux-native-publication-api-${mode} COMMAND linux-publication-api)
    set_tests_properties(
        linux-native-publication-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_PUBLICATION_API_OK" TIMEOUT 120)
endforeach()
foreach(mode on zero one frame-off owned-off)
    add_test(NAME linux-native-publication-oom-${mode} COMMAND linux-publication-api oom)
    set_tests_properties(
        linux-native-publication-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_PUBLICATION_OOM_OK" TIMEOUT 120)
endforeach()
foreach(kind api oom)
    set_property(
        TEST linux-native-publication-${kind}-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_property(
        TEST linux-native-publication-${kind}-one
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
    set_property(
        TEST linux-native-publication-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    set_property(
        TEST linux-native-publication-${kind}-owned-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_JS_OWNED_MISSING=0")
endforeach()
set_property(
    TEST linux-native-publication-api-shared-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
set_property(
    TEST linux-native-publication-api-register-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")

foreach(kind continuation boundary)
    if(kind STREQUAL "continuation")
        set(construct_marker CONSTRUCT_CONTINUATION_OK)
    else()
        set(construct_marker CONSTRUCT_BOUNDARY_ERRORS_OK)
    endif()
    foreach(mode on construct-0 construct-1 iterator-0 iterator-1 frame-off)
        add_test(NAME linux-native-construct-${kind}-${mode}
                 COMMAND qjs_exe --std -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_construct_${kind}.js")
        set_tests_properties(
            linux-native-construct-${kind}-${mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "${construct_marker}" ENVIRONMENT
                       "QJS_EXPERIMENT_ALLOCATOR=256")
    endforeach()
    foreach(value 0 1)
        set_property(
            TEST linux-native-construct-${kind}-construct-${value}
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=${value}")
        set_property(
            TEST linux-native-construct-${kind}-iterator-${value}
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=${value}")
    endforeach()
    set_property(
        TEST linux-native-construct-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_MIN_CALL_FRAME=1")
endforeach()

foreach(kind primitive compound character paths)
    if(kind STREQUAL "primitive")
        set(leaf_fixture common/test_vm_leaf_entries.js)
        set(leaf_success "checksum")
    elseif(kind STREQUAL "compound")
        set(leaf_fixture common/test_vm_compound_leaf.js)
        set(leaf_success "FRAME_COMPOUND_LEAF_OK")
    elseif(kind STREQUAL "paths")
        set(leaf_fixture common/linux/test_linux_vm_leaves.js)
        set(leaf_success "LINUX_VM_LEAVES_PATHS_OK")
    else()
        set(leaf_fixture common/test_vm_character_set_leaf.js)
        set(leaf_success "FRAME_CHARACTER_SET_LEAF_OK")
    endif()
    add_test(NAME linux-native-vm-leaf-${kind}-on
             COMMAND qjs_exe --std -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/${leaf_fixture}")
    set_tests_properties(
        linux-native-vm-leaf-${kind}-on PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256"
                                                   PASS_REGULAR_EXPRESSION "${leaf_success}")
    foreach(
        pair IN
        ITEMS "leaf=QJS_DISABLE_FRAME_LEAF_ENTRY" "compound=QJS_DISABLE_FRAME_COMPOUND_LEAF"
              "character=QJS_DISABLE_FRAME_CHARACTER_SET_LEAF"
              "latin=QJS_DISABLE_LOCALE_COMPARE_LATIN1")
        string(REPLACE "=" ";" fields "${pair}")
        list(GET fields 0 label)
        list(GET fields 1 control)
        foreach(value 0 1)
            add_test(NAME linux-native-vm-leaf-${kind}-${label}-${value}
                     COMMAND qjs_exe --std -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/${leaf_fixture}")
            set_tests_properties(
                linux-native-vm-leaf-${kind}-${label}-${value}
                PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${control}=${value}"
                           PASS_REGULAR_EXPRESSION "${leaf_success}")
        endforeach()
    endforeach()
    add_test(NAME linux-native-vm-leaf-${kind}-frame-off
             COMMAND qjs_exe --std -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/${leaf_fixture}")
    set_tests_properties(
        linux-native-vm-leaf-${kind}-frame-off
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;QJS_DISABLE_MIN_CALL_FRAME=1"
                   PASS_REGULAR_EXPRESSION "${leaf_success}")
endforeach()

add_executable(linux-vm-leaves-api tests/common/linux/native_linux_vm_leaves.c)
target_compile_options(linux-vm-leaves-api PRIVATE -UNDEBUG)
target_link_libraries(linux-vm-leaves-api PRIVATE qjs)
foreach(
    mode
    on
    leaf-0
    leaf-1
    compound-0
    compound-1
    character-0
    character-1
    latin-0
    latin-1
    frame-off)
    add_test(NAME linux-native-vm-leaf-api-${mode} COMMAND linux-vm-leaves-api)
    get_test_property(linux-native-vm-leaf-paths-${mode} ENVIRONMENT leaf_environment)
    set_tests_properties(
        linux-native-vm-leaf-api-${mode}
        PROPERTIES ENVIRONMENT "${leaf_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_VM_LEAVES_API_OK")
endforeach()
foreach(mode on leaf-1 compound-1 character-1 latin-1 frame-off)
    add_test(NAME linux-native-vm-leaf-oom-${mode} COMMAND linux-vm-leaves-api oom)
    get_test_property(linux-native-vm-leaf-paths-${mode} ENVIRONMENT leaf_environment)
    set_tests_properties(
        linux-native-vm-leaf-oom-${mode}
        PROPERTIES ENVIRONMENT "${leaf_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_VM_LEAVES_OOM_OK")
endforeach()

add_executable(linux-construct-api tests/common/linux/native_linux_construct.c)
target_compile_options(linux-construct-api PRIVATE -UNDEBUG)
target_link_libraries(linux-construct-api PRIVATE qjs)
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
                NAME linux-native-construct-${kind}-${mode}
                COMMAND qjs_exe --std -m
                        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_construct.js")
            set(construct_success LINUX_CONSTRUCT_PATHS_OK)
        else()
            add_test(NAME linux-native-construct-${kind}-${mode} COMMAND linux-construct-api)
            set(construct_success LINUX_CONSTRUCT_API_OK)
        endif()
        set_tests_properties(
            linux-native-construct-${kind}-${mode}
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
                TEST linux-native-construct-${kind}-${label}-${value}
                APPEND
                PROPERTY ENVIRONMENT "${control}=${value}")
        endforeach()
    endforeach()
    set_property(
        TEST linux-native-construct-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_MIN_CALL_FRAME=1")
endforeach()
foreach(mode on construct-1 iterator-1 slow-1 shared-1 frame-off)
    add_test(NAME linux-native-construct-oom-${mode} COMMAND linux-construct-api oom)
    get_test_property(linux-native-construct-api-${mode} ENVIRONMENT construct_environment)
    set_tests_properties(
        linux-native-construct-oom-${mode}
        PROPERTIES ENVIRONMENT "${construct_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_CONSTRUCT_OOM_OK")
endforeach()
foreach(mode on construct-1)
    add_test(NAME linux-native-construct-grown-oom-${mode} COMMAND linux-construct-api oom-grown)
    get_test_property(linux-native-construct-api-${mode} ENVIRONMENT construct_environment)
    set_tests_properties(
        linux-native-construct-grown-oom-${mode}
        PROPERTIES ENVIRONMENT "${construct_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_CONSTRUCT_OOM_OK")
endforeach()

set_tests_properties(linux-native-entry PROPERTIES PASS_REGULAR_EXPRESSION
                                                   "LINUX_INTERNAL_ENTRY_OK")
add_executable(linux-slow-host tests/common/linux/native_linux_slow_host.c)
target_link_libraries(linux-slow-host PRIVATE qjs Threads::Threads)
foreach(mode on off-zero off-one shared-off)
    add_test(NAME linux-native-slow-host-${mode} COMMAND linux-slow-host)
    set_tests_properties(linux-native-slow-host-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                   "LINUX_SLOW_HOST_OK")
endforeach()
set_tests_properties(linux-native-slow-host-off-zero PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_SLOW_HOST_SHARE=0")
set_tests_properties(linux-native-slow-host-off-one PROPERTIES ENVIRONMENT
                                                               "QJS_DISABLE_SLOW_HOST_SHARE=1")
set_tests_properties(linux-native-slow-host-shared-off PROPERTIES ENVIRONMENT
                                                                  "QJS_DISABLE_SHARED_ENTRY=0")
add_executable(linux-c-invoke tests/common/linux/native_linux_c_invoke.c)
target_link_libraries(linux-c-invoke PRIVATE qjs)
foreach(mode on off-zero off-one shared-off direct-off)
    add_test(NAME linux-native-c-invoke-${mode} COMMAND linux-c-invoke)
    set_tests_properties(linux-native-c-invoke-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                  "LINUX_C_INVOKE_ABI_OK")
endforeach()
set_tests_properties(linux-native-c-invoke-off-zero PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=0")
set_tests_properties(linux-native-c-invoke-off-one PROPERTIES ENVIRONMENT "QJS_DISABLE_C_INVOKE=1")
set_tests_properties(linux-native-c-invoke-shared-off PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(linux-native-c-invoke-direct-off PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_DIRECT_HOST_CALL=0")
foreach(
    mode
    on
    off-zero
    off-one
    large-off-zero
    large-off-one
    regexp-off-zero
    regexp-off-one
    register-off)
    add_test(NAME linux-native-admission-${mode}
             COMMAND qjs_exe
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_admission.js")
    set_tests_properties(linux-native-admission-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                   "LINUX_ADMISSION_OK")
endforeach()
set_tests_properties(linux-native-admission-off-zero PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_LINUX_ADMISSION=0")
set_tests_properties(linux-native-admission-off-one PROPERTIES ENVIRONMENT
                                                               "QJS_DISABLE_LINUX_ADMISSION=1")
set_tests_properties(linux-native-admission-large-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=0")
set_tests_properties(linux-native-admission-large-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=1")
set_tests_properties(linux-native-admission-regexp-off-zero PROPERTIES ENVIRONMENT
                                                                       "QJS_DISABLE_FRAME_REGEXP=0")
set_tests_properties(linux-native-admission-regexp-off-one PROPERTIES ENVIRONMENT
                                                                      "QJS_DISABLE_FRAME_REGEXP=1")
set_tests_properties(linux-native-admission-register-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_REGISTER_INTERP=0")
add_executable(linux-literal-oom tests/common/linux/native_linux_literal_oom.c)
target_compile_options(linux-literal-oom PRIVATE -UNDEBUG)
target_link_libraries(linux-literal-oom PRIVATE qjs)
foreach(mode on off-zero off-one)
    add_test(NAME linux-native-literal-oom-${mode} COMMAND linux-literal-oom)
    set_tests_properties(linux-native-literal-oom-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                     "LINUX_LITERAL_OOM_OK")
endforeach()
set_tests_properties(linux-native-literal-oom-off-zero PROPERTIES ENVIRONMENT
                                                                  "QJS_DISABLE_LINUX_ADMISSION=0")
set_tests_properties(linux-native-literal-oom-off-one PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_LINUX_ADMISSION=1")
add_executable(linux-literal-reserve tests/common/native_literal_reserve.c)
target_compile_options(linux-literal-reserve PRIVATE -UNDEBUG)
target_link_libraries(linux-literal-reserve PRIVATE qjs)
add_test(NAME linux-native-literal-reserve-on COMMAND linux-literal-reserve)
add_test(NAME linux-native-literal-reserve-spare-off COMMAND linux-literal-reserve off)
add_test(NAME linux-native-literal-reserve-transition-off COMMAND linux-literal-reserve off)
add_test(NAME linux-native-literal-reserve-ordinary-off COMMAND linux-literal-reserve off)
set_tests_properties(
    linux-native-literal-reserve-on linux-native-literal-reserve-spare-off
    linux-native-literal-reserve-transition-off linux-native-literal-reserve-ordinary-off
    PROPERTIES PASS_REGULAR_EXPRESSION "LITERAL_RESERVE_OK" TIMEOUT 120)
set_tests_properties(linux-native-literal-reserve-spare-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_SPARE=0")
set_tests_properties(linux-native-literal-reserve-transition-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION=0")
set_tests_properties(linux-native-literal-reserve-ordinary-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL=0")
foreach(mode on off-zero off-one)
    add_test(NAME linux-native-global-cells-${mode}
             COMMAND qjs_exe
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_global_cells.js")
    set_tests_properties(linux-native-global-cells-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                      "LINUX_GLOBAL_CELLS_OK")
endforeach()
set_tests_properties(linux-native-global-cells-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_BINDING_CELL=0")
set_tests_properties(linux-native-global-cells-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_BINDING_CELL=1")
add_executable(linux-prepared-callback tests/common/linux/native_linux_prepared_callback.c)
target_compile_options(linux-prepared-callback PRIVATE -UNDEBUG)
target_link_libraries(linux-prepared-callback PRIVATE qjs)
foreach(
    mode
    on
    off-zero
    off-one
    write-off
    arity-off
    bypass-off
    shared-off
    register-off
    c-invoke-off
    frame-off)
    add_test(NAME linux-native-prepared-${mode} COMMAND linux-prepared-callback)
    set_tests_properties(linux-native-prepared-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                  "LINUX_PREPARED_SEMANTICS_OK")
endforeach()
set_tests_properties(linux-native-prepared-off-zero PROPERTIES ENVIRONMENT
                                                               "QJS_DISABLE_PREPARED_CALLBACK=0")
set_tests_properties(linux-native-prepared-off-one PROPERTIES ENVIRONMENT
                                                              "QJS_DISABLE_PREPARED_CALLBACK=1")
set_tests_properties(linux-native-prepared-write-off PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_CALLBACK_WRITE=0")
set_tests_properties(linux-native-prepared-arity-off PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_CALLBACK_ARITY=0")
set_tests_properties(linux-native-prepared-bypass-off PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_SHARED_CALL_BYPASS=0")
set_tests_properties(linux-native-prepared-shared-off PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_SHARED_ENTRY=0")
set_tests_properties(linux-native-prepared-register-off PROPERTIES ENVIRONMENT
                                                                   "QJS_DISABLE_REGISTER_INTERP=0")
set_tests_properties(linux-native-prepared-c-invoke-off PROPERTIES ENVIRONMENT
                                                                   "QJS_DISABLE_C_INVOKE=0")
set_tests_properties(linux-native-prepared-frame-off PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_INTERP_FRAME=0")
foreach(mode on off-zero write-off)
    add_test(NAME linux-native-prepared-oom-${mode} COMMAND linux-prepared-callback sweep)
    set_tests_properties(linux-native-prepared-oom-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                      "LINUX_PREPARED_OOM_OK")
endforeach()
set_tests_properties(linux-native-prepared-oom-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=0")
set_tests_properties(linux-native-prepared-oom-write-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_CALLBACK_WRITE=0")
add_executable(linux-json-family tests/common/linux/native_linux_json_family.c)
target_compile_options(linux-json-family PRIVATE -UNDEBUG)
target_link_libraries(linux-json-family PRIVATE qjs)
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
        NAME linux-native-json-${mode}
        COMMAND
            linux-json-family
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_json_family.js"
            "${json_expect}")
    set_tests_properties(linux-native-json-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                              "LINUX_JSON_SEMANTICS_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-json-mode127 PROPERTIES ENVIRONMENT "QJS_JSON_MODE=127")
set_tests_properties(linux-native-json-value-off PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_JSON_REVIVER_VALUE=0")
set_tests_properties(linux-native-json-source-off PROPERTIES ENVIRONMENT
                                                             "QJS_DISABLE_JSON_REVIVER_SOURCE=0")
set_tests_properties(linux-native-json-codeunits-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_SOURCE_CODEUNITS=0")
set_tests_properties(linux-native-json-write-off PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_JSON_CALLBACK_WRITE=0")
set_tests_properties(linux-native-json-quote-off PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_JSON_DIRECT_QUOTE=0")
set_tests_properties(linux-native-json-slot-off PROPERTIES ENVIRONMENT
                                                           "QJS_DISABLE_JSON_TOJSON_SLOT=0")
set_tests_properties(linux-native-json-prepared-off PROPERTIES ENVIRONMENT
                                                               "QJS_DISABLE_PREPARED_CALLBACK=0")
set_tests_properties(linux-native-json-arity-off PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_CALLBACK_ARITY=0")
set_tests_properties(linux-native-json-source-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_SOURCE_PREPARED=0")
set_tests_properties(linux-native-json-value-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_JSON_VALUE_PREPARED=0")
set_tests_properties(linux-native-json-no-simd PROPERTIES ENVIRONMENT "QJS_JSON_MODE=32")
set_tests_properties(linux-native-json-no-cache PROPERTIES ENVIRONMENT "QJS_JSON_MODE=4")
set_tests_properties(linux-native-json-register-off PROPERTIES ENVIRONMENT
                                                               "QJS_DISABLE_REGISTER_INTERP=0")
foreach(mode on prepared-off)
    add_test(NAME linux-native-json-oom-${mode} COMMAND linux-json-family sweep)
    set_tests_properties(linux-native-json-oom-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                  "LINUX_JSON_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-json-oom-prepared-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PREPARED_CALLBACK=0")
foreach(component ADD_BOUNDARY ADD_LOCAL LOCAL_ROPE_APPEND FRAME_NATIVE_ROPE_APPEND)
    foreach(value 0 1)
        string(TOLOWER "${component}" label)
        add_test(NAME linux-native-string-${label}-off-${value}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
        if(component STREQUAL "ADD_BOUNDARY" OR component STREQUAL "ADD_LOCAL")
            set(control "QJS_DISABLE_NATIVE_${component}")
        else()
            set(control "QJS_DISABLE_${component}")
        endif()
        set_tests_properties(
            linux-native-string-${label}-off-${value}
            PROPERTIES ENVIRONMENT "${control}=${value};QJS_EXPERIMENT_ALLOCATOR=256"
                       PASS_REGULAR_EXPRESSION "CONCAT_ROPE_SMOKE_PASSED")
    endforeach()
endforeach()
foreach(component CONCAT_ROPE LOCAL_ROPE_SPARE)
    string(TOLOWER "${component}" label)
    add_test(NAME linux-native-string-${label}-off-zero
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
    set_tests_properties(
        linux-native-string-${label}-off-zero
        PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=0;QJS_EXPERIMENT_ALLOCATOR=256"
                   PASS_REGULAR_EXPRESSION "CONCAT_ROPE_SMOKE_PASSED")
endforeach()
add_test(NAME linux-native-locale-off-zero
         COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_locale_compare.js")
set_tests_properties(
    linux-native-locale-off-zero PROPERTIES ENVIRONMENT "QJS_DISABLE_LOCALE_COMPARE_LATIN1=0"
                                            PASS_REGULAR_EXPRESSION "LOCALE_COMPARE 67789 PASS")
add_executable(linux-string-ownership tests/common/linux/native_linux_strings.c)
target_compile_options(linux-string-ownership PRIVATE -UNDEBUG)
target_link_libraries(linux-string-ownership PRIVATE qjs Threads::Threads)
foreach(mode on off-zero off-one)
    add_test(NAME linux-native-string-ownership-${mode} COMMAND linux-string-ownership)
    set_tests_properties(linux-native-string-ownership-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_STRING_OWNERSHIP_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-string-ownership-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SMALL_CHAR_CACHE=0")
set_tests_properties(linux-native-string-ownership-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_SMALL_CHAR_CACHE=1")
add_executable(linux-default-string-sort tests/common/native_default_string_sort.c)
target_link_libraries(linux-default-string-sort PRIVATE qjs)
foreach(mode on off-zero off-one)
    add_test(NAME linux-native-default-string-sort-${mode} COMMAND linux-default-string-sort)
    set_tests_properties(linux-native-default-string-sort-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "SORT_HOST_PASS" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-default-string-sort-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=0")
set_tests_properties(linux-native-default-string-sort-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=1")
foreach(variant host gc)
    add_executable(linux-array-copy-${variant} tests/common/native_array_copy.c)
    target_compile_definitions(linux-array-copy-${variant} PRIVATE QJS_INTERP_FRAME_LINUX)
    target_include_directories(linux-array-copy-${variant} PRIVATE "${qjs_linux_abi_dir}")
    add_dependencies(linux-array-copy-${variant} qjs-core)
    if(variant STREQUAL "gc")
        target_compile_definitions(linux-array-copy-${variant} PRIVATE FRAME_ARRAY_COPY_GC_ONLY)
    endif()
    target_link_libraries(linux-array-copy-${variant} PRIVATE qjs)
    foreach(mode on off-zero off-one)
        add_test(NAME linux-native-array-copy-${variant}-${mode}
                 COMMAND linux-array-copy-${variant})
        set_tests_properties(linux-native-array-copy-${variant}-${mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "passed" TIMEOUT 120)
    endforeach()
    set_tests_properties(linux-native-array-copy-${variant}-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=0")
    set_tests_properties(linux-native-array-copy-${variant}-off-one
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=1")
endforeach()
add_executable(linux-sort-ownership tests/common/linux/native_linux_sort.c)
target_compile_options(linux-sort-ownership PRIVATE -UNDEBUG)
target_link_libraries(linux-sort-ownership PRIVATE qjs)
add_test(NAME linux-native-sort-ownership-on COMMAND linux-sort-ownership)
set_tests_properties(linux-native-sort-ownership-on
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
        add_test(NAME linux-native-sort-${label}-off-${value} COMMAND linux-sort-ownership)
        set_tests_properties(
            linux-native-sort-${label}-off-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_SORT_SEMANTICS_OK" TIMEOUT 120)
    endforeach()
endforeach()
foreach(mode on off)
    add_test(NAME linux-native-sort-oom-${mode} COMMAND linux-sort-ownership oom)
    set_tests_properties(linux-native-sort-oom-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                  "LINUX_SORT_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-sort-oom-off PROPERTIES ENVIRONMENT
                                                          "QJS_DISABLE_PREPARED_SORT_CALL=0")
foreach(mode on off)
    add_test(NAME linux-native-sort-growth-oom-${mode} COMMAND linux-sort-ownership growth-oom)
    set_tests_properties(linux-native-sort-growth-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_SORT_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-sort-growth-oom-off PROPERTIES ENVIRONMENT
                                                                 "QJS_DISABLE_PREPARED_SORT_CALL=0")
foreach(mode on off-zero off-one frame-off)
    add_test(NAME linux-native-array-append-${mode}
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_array_append.js")
    set_tests_properties(linux-native-array-append-${mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                      "LINUX_ARRAY_APPEND_OK")
endforeach()
set_tests_properties(linux-native-array-append-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_APPEND=0")
set_tests_properties(linux-native-array-append-off-one
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_APPEND=1")
set_tests_properties(linux-native-array-append-frame-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_INTERP_FRAME=0")

add_executable(linux-c-entry tests/common/linux/native_linux_c_entry.c)
target_compile_options(linux-c-entry PRIVATE -UNDEBUG)
target_link_libraries(linux-c-entry PRIVATE qjs)
add_test(NAME linux-native-c-entry-on COMMAND linux-c-entry)
set_tests_properties(linux-native-c-entry-on PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_C_ENTRY_OK"
                                                        TIMEOUT 120)
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
        add_test(NAME linux-native-c-entry-${label}-off-${value} COMMAND linux-c-entry)
        set_tests_properties(
            linux-native-c-entry-${label}-off-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_C_ENTRY_OK" TIMEOUT 120)
    endforeach()
endforeach()
add_test(NAME linux-native-c-entry-numeric-both-off COMMAND linux-c-entry)
set_tests_properties(
    linux-native-c-entry-numeric-both-off
    PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_NUMERIC_INVOKE=0;QJS_DISABLE_NUMERIC_TRAMPOLINE=0"
               PASS_REGULAR_EXPRESSION "LINUX_C_ENTRY_OK" TIMEOUT 120)
foreach(mode on off)
    add_test(NAME linux-native-c-entry-oom-${mode} COMMAND linux-c-entry oom)
    set_tests_properties(linux-native-c-entry-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_C_ENTRY_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-c-entry-oom-off PROPERTIES ENVIRONMENT
                                                             "QJS_DISABLE_NATIVE_SLICE=0")
add_executable(linux-dense-pop-leaf tests/common/native_dense_pop_leaf.c)
target_compile_definitions(linux-dense-pop-leaf PRIVATE LEAF_DIAGNOSTIC=0 LEAF_HAS_ARGC_WINDOW=0)
target_link_libraries(linux-dense-pop-leaf PRIVATE qjs)
foreach(mode on leaf-off pop-off c-invoke-off)
    add_test(NAME linux-native-dense-pop-leaf-${mode} COMMAND linux-dense-pop-leaf)
    set_tests_properties(linux-native-dense-pop-leaf-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "DENSE_POP_LEAF_PASS" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-dense-pop-leaf-leaf-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DENSE_ARRAY_POP_LEAF=0")
set_tests_properties(linux-native-dense-pop-leaf-pop-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_DENSE_ARRAY_POP=0")
set_tests_properties(linux-native-dense-pop-leaf-c-invoke-off PROPERTIES ENVIRONMENT
                                                                         "QJS_DISABLE_C_INVOKE=0")

foreach(mode on geometry stack transient off)
    add_test(
        NAME linux-native-view-argument-alias-${mode}
        COMMAND qjs_exe
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_view_argument_alias.js")
    set_tests_properties(
        linux-native-view-argument-alias-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_VIEW_ARGUMENT_ALIAS_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-view-argument-alias-geometry
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_LIFETIME=0")
set_tests_properties(linux-native-view-argument-alias-stack
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_ARENA=0")
set_tests_properties(linux-native-view-argument-alias-transient
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_NATIVE_FRAME_REUSE=0")
set_tests_properties(linux-native-view-argument-alias-off PROPERTIES ENVIRONMENT
                                                                     "QJS_DISABLE_NATIVE_SLICE=0")

add_executable(linux-js-calls tests/common/linux/native_linux_js_calls.c)
target_compile_options(linux-js-calls PRIVATE -UNDEBUG)
target_link_libraries(linux-js-calls PRIVATE qjs)
add_test(NAME linux-native-js-call-on COMMAND linux-js-calls)
set_tests_properties(linux-native-js-call-on PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_JS_CALL_OK"
                                                        TIMEOUT 120)
foreach(
    component
    FRAME_JS_OWNED_MISSING
    FRAME_JS_CAPTURED
    FRAME_CAPTURED_READONLY
    FRAME_SET_NAME
    C_INVOKE
    SHARED_ENTRY
    REGISTER_INTERP
    INTERP_FRAME)
    foreach(value 0 1)
        string(TOLOWER "${component}" label)
        add_test(NAME linux-native-js-call-${label}-off-${value} COMMAND linux-js-calls)
        set_tests_properties(
            linux-native-js-call-${label}-off-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_JS_CALL_OK" TIMEOUT 120)
    endforeach()
endforeach()
foreach(mode on owned-off captured-off proof-off)
    add_test(NAME linux-native-js-call-oom-${mode} COMMAND linux-js-calls oom)
    set_tests_properties(linux-native-js-call-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_JS_CALL_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-js-call-oom-owned-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_JS_OWNED_MISSING=0")
set_tests_properties(linux-native-js-call-oom-captured-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_JS_CAPTURED=0")
set_tests_properties(linux-native-js-call-oom-proof-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CAPTURED_READONLY=0")

add_executable(linux-call-forward tests/common/linux/native_linux_call_forward.c)
target_compile_options(linux-call-forward PRIVATE -UNDEBUG)
target_link_libraries(linux-call-forward PRIVATE qjs)

# Real public/SysV private entry, frame-free leaves and component fallbacks.
add_executable(linux-native-entry-api tests/common/linux/native_linux_entry.c)
target_compile_options(linux-native-entry-api PRIVATE -UNDEBUG)
target_link_libraries(linux-native-entry-api PRIVATE qjs)
add_test(NAME linux-native-entry-api-on COMMAND linux-native-entry-api)
set_tests_properties(
    linux-native-entry-api-on PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256"
                                         PASS_REGULAR_EXPRESSION "LINUX_NATIVE_ENTRY_OK")
set(linux_entry_all_off "QJS_EXPERIMENT_ALLOCATOR=256")
foreach(
    pair IN
    ITEMS "public=QJS_DISABLE_PUBLIC_ROOT"
          "root=QJS_DISABLE_NATIVE_ROOT_ENTRY"
          "zero=QJS_DISABLE_NATIVE_ROOT_ZERO"
          "args=QJS_DISABLE_NATIVE_ROOT_ARGS"
          "child=QJS_DISABLE_NATIVE_CHILD"
          "leaf=QJS_DISABLE_NATIVE_CHILD_LEAF"
          "getter=QJS_DISABLE_THIS_FIELD_LEAF"
          "shared=QJS_DISABLE_SHARED_ENTRY")
    string(REPLACE "=" ";" fields "${pair}")
    list(GET fields 0 label)
    list(GET fields 1 control)
    list(APPEND linux_entry_all_off "${control}=1")
    foreach(value 0 1)
        add_test(NAME linux-native-entry-api-${label}-${value} COMMAND linux-native-entry-api)
        set_tests_properties(
            linux-native-entry-api-${label}-${value}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;${control}=${value}"
                       PASS_REGULAR_EXPRESSION "LINUX_NATIVE_ENTRY_OK")
    endforeach()
endforeach()
add_test(NAME linux-native-entry-api-frame-off COMMAND linux-native-entry-api)
set_tests_properties(
    linux-native-entry-api-frame-off
    PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;QJS_DISABLE_MIN_CALL_FRAME=1"
               PASS_REGULAR_EXPRESSION "LINUX_NATIVE_ENTRY_OK")
add_test(NAME linux-native-entry-api-all-entry-off COMMAND linux-native-entry-api)
set_tests_properties(
    linux-native-entry-api-all-entry-off PROPERTIES ENVIRONMENT "${linux_entry_all_off}"
                                                    PASS_REGULAR_EXPRESSION "LINUX_NATIVE_ENTRY_OK")
foreach(
    mode
    on
    public-1
    root-1
    zero-1
    args-1
    child-1
    leaf-1
    all-entry-off
    frame-off)
    add_test(NAME linux-native-entry-oom-${mode} COMMAND linux-native-entry-api oom)
    get_test_property(linux-native-entry-api-${mode} ENVIRONMENT entry_environment)
    set_tests_properties(
        linux-native-entry-oom-${mode}
        PROPERTIES ENVIRONMENT "${entry_environment}" PASS_REGULAR_EXPRESSION
                   "LINUX_NATIVE_ENTRY_OOM_OK")
endforeach()
foreach(mode on)
    add_test(NAME linux-native-call-forward-${mode}
             COMMAND qjs_exe
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_call_forward.js")
    set_tests_properties(linux-native-call-forward-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_CALL_FORWARD_OK" TIMEOUT 120)
    add_test(NAME linux-native-call-forward-host-${mode} COMMAND linux-call-forward)
    set_tests_properties(linux-native-call-forward-host-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_FORWARD_HOST_OK" TIMEOUT 120)
endforeach()
foreach(
    component
    FRAME_CALL_FORWARD
    FRAME_CALL_FORWARD_LEAF
    FRAME_CALL_FORWARD_NATIVE
    FRAME_CALL_FORWARD_OWNED
    FRAME_CALL_FORWARD_BORROW
    FRAME_CALL_FORWARD_BORROW_MISSING
    FRAME_CALL_PREPARE
    FRAME_CALL_PREPARE_OWNED
    FRAME_CAPTURED_READONLY
    REGISTER_INTERP
    INTERP_FRAME)
    foreach(value 0 1)
        string(TOLOWER "${component}" label)
        add_test(
            NAME linux-native-call-forward-${label}-off-${value}
            COMMAND qjs_exe
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_call_forward.js")
        set_tests_properties(
            linux-native-call-forward-${label}-off-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_CALL_FORWARD_OK" TIMEOUT 120)
        add_test(NAME linux-native-call-forward-host-${label}-off-${value}
                 COMMAND linux-call-forward)
        set_tests_properties(
            linux-native-call-forward-host-${label}-off-${value}
            PROPERTIES ENVIRONMENT "QJS_DISABLE_${component}=${value}" PASS_REGULAR_EXPRESSION
                       "LINUX_FORWARD_HOST_OK" TIMEOUT 120)
    endforeach()
endforeach()
foreach(
    mode
    on
    forward-off
    native-off
    owned-off
    borrow-off
    prepare-off
    prepared-owned-off)
    add_test(NAME linux-native-call-forward-oom-${mode} COMMAND linux-call-forward oom)
    set_tests_properties(linux-native-call-forward-oom-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_FORWARD_OOM_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-call-forward-oom-forward-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
set_tests_properties(linux-native-call-forward-oom-native-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
set_tests_properties(linux-native-call-forward-oom-owned-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_OWNED=0")
set_tests_properties(linux-native-call-forward-oom-borrow-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_BORROW=0")
set_tests_properties(linux-native-call-forward-oom-prepare-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_PREPARE=0")
set_tests_properties(linux-native-call-forward-oom-prepared-owned-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_PREPARE_OWNED=0")
foreach(mode on forward-off native-off frame-off)
    add_test(NAME linux-native-call-forward-quota-${mode} COMMAND linux-call-forward quota)
    set_tests_properties(linux-native-call-forward-quota-${mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "LINUX_FORWARD_QUOTA_OK" TIMEOUT 120)
endforeach()
set_tests_properties(linux-native-call-forward-quota-forward-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
set_tests_properties(linux-native-call-forward-quota-native-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE=0")
set_tests_properties(linux-native-call-forward-quota-frame-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")

foreach(
    mode
    on
    zero
    one
    native-off
    borrow-off
    access-off
    forward-off
    index-off
    length-off
    constructor-off
    native-length-off
    publish-off
    frame-off
    register-off
    shared-off)
    add_test(NAME linux-native-arguments-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_arguments.js")
    set_tests_properties(
        linux-native-arguments-${mode} PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256"
                                                  PASS_REGULAR_EXPRESSION "LINUX_ARGUMENTS_OK")
endforeach()
set_property(
    TEST linux-native-arguments-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS=0")
set_property(
    TEST linux-native-arguments-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS=1")
set_property(
    TEST linux-native-arguments-native-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_NATIVE=0")
set_property(
    TEST linux-native-arguments-borrow-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_BORROW=0")
set_property(
    TEST linux-native-arguments-access-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_ACCESS=0")
set_property(
    TEST linux-native-arguments-forward-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_FORWARD=0")
set_property(
    TEST linux-native-arguments-index-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_INDEX=0")
set_property(
    TEST linux-native-arguments-length-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_LENGTH=0")
set_property(
    TEST linux-native-arguments-constructor-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
set_property(
    TEST linux-native-arguments-native-length-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_NATIVE_LENGTH=0")
set_property(
    TEST linux-native-arguments-publish-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-arguments-frame-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
set_property(
    TEST linux-native-arguments-register-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_property(
    TEST linux-native-arguments-shared-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")

# Same public protocol owner, with argument-bearing JS frames selected at compile time.
add_executable(linux-arguments-api tests/common/linux/native_linux_publication.c)
target_compile_definitions(linux-arguments-api PRIVATE QJS_TEST_ARGUMENT_PROTOCOL)
target_compile_options(linux-arguments-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-arguments-api PRIVATE qjs)
foreach(mode on zero one borrow-off publish-off frame-off)
    add_test(NAME linux-native-arguments-api-${mode} COMMAND linux-arguments-api)
    set_tests_properties(
        linux-native-arguments-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ARGUMENTS_API_OK" TIMEOUT 120)
endforeach()
foreach(mode on zero borrow-off frame-off)
    add_test(NAME linux-native-arguments-oom-${mode} COMMAND linux-arguments-api oom)
    set_tests_properties(
        linux-native-arguments-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ARGUMENTS_OOM_OK" TIMEOUT 120)
endforeach()
foreach(kind api oom)
    set_property(
        TEST linux-native-arguments-${kind}-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS=0")
    set_property(
        TEST linux-native-arguments-${kind}-borrow-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_BORROW=0")
    set_property(
        TEST linux-native-arguments-${kind}-frame-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endforeach()
set_property(
    TEST linux-native-arguments-api-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS=1")
set_property(
    TEST linux-native-arguments-api-publish-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")

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
    add_test(NAME linux-native-iterators-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_iterators.js")
    set_tests_properties(
        linux-native-iterators-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-iterators-iterator-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=0")
set_property(
    TEST linux-native-iterators-iterator-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=1")
set_property(
    TEST linux-native-iterators-js-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=0")
set_property(
    TEST linux-native-iterators-js-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=1")
set_property(
    TEST linux-native-iterators-array-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=0")
set_property(
    TEST linux-native-iterators-array-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=1")
set_property(
    TEST linux-native-iterators-slow-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR_SLOW=0")
set_property(
    TEST linux-native-iterators-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-iterators-share-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
set_property(
    TEST linux-native-iterators-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
add_executable(linux-argument-constructor tests/common/native_argument_constructor.c)
target_link_libraries(linux-argument-constructor PRIVATE qjs)
foreach(mode on zero one)
    add_test(NAME linux-native-argument-constructor-host-${mode} COMMAND linux-argument-constructor)
    set_tests_properties(
        linux-native-argument-constructor-host-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256;QJS_OBSERVE_FRAME_ARGUMENTS=1"
                   PASS_REGULAR_EXPRESSION "ARGUMENT_CONSTRUCTOR_HOST_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-argument-constructor-host-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
set_property(
    TEST linux-native-argument-constructor-host-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=1")

add_executable(linux-argument-construct-api tests/common/linux/native_linux_construct.c)
target_compile_definitions(linux-argument-construct-api
                           PRIVATE QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL)
target_compile_options(linux-argument-construct-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-argument-construct-api PRIVATE qjs)
foreach(mode on zero one arguments-off frame-off)
    add_test(NAME linux-native-argument-construct-api-${mode} COMMAND linux-argument-construct-api)
    set_tests_properties(
        linux-native-argument-construct-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ARGUMENT_CONSTRUCT_API_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-argument-construct-api-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
set_property(
    TEST linux-native-argument-construct-api-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=1")
set_property(
    TEST linux-native-argument-construct-api-arguments-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS=0")
set_property(
    TEST linux-native-argument-construct-api-frame-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
foreach(kind oom oom-grown)
    foreach(mode on off)
        add_test(NAME linux-native-argument-construct-${kind}-${mode}
                 COMMAND linux-argument-construct-api ${kind})
        set_tests_properties(
            linux-native-argument-construct-${kind}-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_ARGUMENT_CONSTRUCT_OOM_OK" TIMEOUT 120)
    endforeach()
    set_property(
        TEST linux-native-argument-construct-${kind}-off
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
endforeach()

# Public-only owner fixture, exercising actual JS-next/realm/GC continuations.
add_executable(linux-iterators-api tests/common/linux/native_linux_publication.c)
target_compile_definitions(linux-iterators-api PRIVATE QJS_TEST_ITERATOR_PROTOCOL)
target_compile_options(linux-iterators-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-iterators-api PRIVATE qjs)
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
    add_test(NAME linux-native-iterators-api-${mode} COMMAND linux-iterators-api)
    set_tests_properties(
        linux-native-iterators-api-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_API_OK" TIMEOUT 120)
endforeach()
foreach(mode on js-zero iterator-zero frame-zero)
    add_test(NAME linux-native-iterators-oom-${mode} COMMAND linux-iterators-api oom)
    set_tests_properties(
        linux-native-iterators-oom-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_ITERATORS_OOM_OK" TIMEOUT 120)
endforeach()
foreach(kind api oom)
    set_property(
        TEST linux-native-iterators-${kind}-js-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=0")
    set_property(
        TEST linux-native-iterators-${kind}-iterator-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR=0")
    set_property(
        TEST linux-native-iterators-${kind}-frame-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
endforeach()
set_property(
    TEST linux-native-iterators-api-js-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_JS_CALL=1")
set_property(
    TEST linux-native-iterators-api-array-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ARRAY_ITERATOR=0")
set_property(
    TEST linux-native-iterators-api-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-iterators-api-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
set_property(
    TEST linux-native-iterators-api-slow-host-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")

foreach(
    mode
    on
    varargs-zero
    varargs-one
    direct-zero
    direct-one
    fusion-zero
    fusion-one
    apply-zero
    apply-one
    forward-zero
    publish-zero
    shared-zero
    frame-zero)
    add_test(NAME linux-native-varargs-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_varargs.js")
    set_tests_properties(
        linux-native-varargs-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_VARARGS_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-varargs-varargs-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS=0")
set_property(
    TEST linux-native-varargs-varargs-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS=1")
set_property(
    TEST linux-native-varargs-direct-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_DIRECT=0")
set_property(
    TEST linux-native-varargs-direct-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_DIRECT=1")
set_property(
    TEST linux-native-varargs-fusion-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_FUSION=0")
set_property(
    TEST linux-native-varargs-fusion-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_FUSION=1")
set_property(
    TEST linux-native-varargs-apply-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=0")
set_property(
    TEST linux-native-varargs-apply-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=1")
set_property(
    TEST linux-native-varargs-forward-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_CALL_FORWARD=0")
set_property(
    TEST linux-native-varargs-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-varargs-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
set_property(
    TEST linux-native-varargs-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")

foreach(
    mode
    on
    ordinary-zero
    ordinary-one
    transition-zero
    lazy-zero
    repeat-zero
    spare-zero
    vm-hit-zero
    cache-alloc-fail
    lazy-alloc-fail
    typeof-zero
    predicate-zero
    truth-zero
    number-zero
    insert-zero
    iterator-zero
    iterator-transition-zero
    publish-zero
    shared-zero
    frame-zero)
    add_test(NAME linux-native-literals-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_literals.js")
    set_tests_properties(
        linux-native-literals-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_LITERALS_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-literals-ordinary-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL=0")
set_property(
    TEST linux-native-literals-ordinary-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL=1")
set_property(
    TEST linux-native-literals-transition-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION=0")
set_property(
    TEST linux-native-literals-lazy-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_LAZY=0")
set_property(
    TEST linux-native-literals-repeat-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_REPEAT_GUARD=0")
set_property(
    TEST linux-native-literals-spare-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_SPARE=0")
set_property(
    TEST linux-native-literals-vm-hit-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_VM_HIT=0")
set_property(
    TEST linux-native-literals-cache-alloc-fail
    APPEND
    PROPERTY ENVIRONMENT "QJS_ORDINARY_LITERAL_FAIL_CACHE_ALLOC=1")
set_property(
    TEST linux-native-literals-lazy-alloc-fail
    APPEND
    PROPERTY ENVIRONMENT "QJS_LITERAL_LAZY_FAIL_ALLOC=1")
set_property(
    TEST linux-native-literals-typeof-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_TYPEOF=0")
set_property(
    TEST linux-native-literals-predicate-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_PREDICATE=0")
set_property(
    TEST linux-native-literals-truth-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_TRUTHINESS=0")
set_property(
    TEST linux-native-literals-number-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_NUMBER_TRUTH=0")
set_property(
    TEST linux-native-literals-insert-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_STACK_INSERT=0")
set_property(
    TEST linux-native-literals-iterator-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_LITERAL_SHAPES=0")
set_property(
    TEST linux-native-literals-iterator-transition-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ITERATOR_LITERAL_TRANSITION=0")
set_property(
    TEST linux-native-literals-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-literals-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
set_property(
    TEST linux-native-literals-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")

# Reuse the public C owner fixture for dense snapshots and cache-owned native
# prototypes, including missing formals and a grown 97-actual/99-formal frame.
foreach(variant default wide)
    add_executable(linux-varargs-literal-${variant}-api
                   tests/common/linux/native_linux_publication.c)
    target_compile_definitions(linux-varargs-literal-${variant}-api
                               PRIVATE QJS_TEST_VARARGS_LITERAL_PROTOCOL)
    if(variant STREQUAL "wide")
        target_compile_definitions(linux-varargs-literal-${variant}-api
                                   PRIVATE QJS_TEST_VARARGS_WIDE)
    endif()
    target_compile_options(linux-varargs-literal-${variant}-api PRIVATE -UNDEBUG -Wall -Wextra
                                                                        -Werror)
    target_link_libraries(linux-varargs-literal-${variant}-api PRIVATE qjs)
    foreach(
        mode
        on
        varargs-zero
        direct-zero
        fusion-zero
        apply-zero
        ordinary-zero
        transition-zero
        lazy-zero
        cache-fail
        lazy-fail
        publish-zero
        shared-zero
        slow-host-zero
        frame-zero)
        add_test(NAME linux-native-varargs-literal-${variant}-api-${mode}
                 COMMAND linux-varargs-literal-${variant}-api)
        set_tests_properties(
            linux-native-varargs-literal-${variant}-api-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_VARARGS_LITERALS_API_OK" TIMEOUT 120)
    endforeach()
    foreach(mode on varargs-zero apply-zero ordinary-zero cache-fail frame-zero)
        add_test(NAME linux-native-varargs-literal-${variant}-oom-${mode}
                 COMMAND linux-varargs-literal-${variant}-api oom)
        set_tests_properties(
            linux-native-varargs-literal-${variant}-oom-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_VARARGS_LITERALS_OOM_OK" TIMEOUT 120)
    endforeach()
    foreach(kind api oom)
        set_property(
            TEST linux-native-varargs-literal-${variant}-${kind}-varargs-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS=0")
        set_property(
            TEST linux-native-varargs-literal-${variant}-${kind}-apply-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=0")
        set_property(
            TEST linux-native-varargs-literal-${variant}-${kind}-ordinary-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL=0")
        set_property(
            TEST linux-native-varargs-literal-${variant}-${kind}-cache-fail
            APPEND
            PROPERTY ENVIRONMENT "QJS_ORDINARY_LITERAL_FAIL_CACHE_ALLOC=1")
        set_property(
            TEST linux-native-varargs-literal-${variant}-${kind}-frame-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    endforeach()
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-direct-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_DIRECT=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-fusion-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_VARARGS_FUSION=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-transition-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-lazy-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_LITERAL_LAZY=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-lazy-fail
        APPEND
        PROPERTY ENVIRONMENT "QJS_LITERAL_LAZY_FAIL_ALLOC=1")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-publish-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-shared-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
    set_property(
        TEST linux-native-varargs-literal-${variant}-api-slow-host-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
endforeach()

foreach(
    mode
    on
    slow-zero
    slow-one
    indexed-zero
    own-zero
    instance-step-zero
    instance-leaf-zero
    instance-zero
    instance-observe
    publish-zero
    frame-zero
    register-zero
    shared-zero)
    add_test(NAME linux-native-indexed-${mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_indexed.js")
    set_tests_properties(
        linux-native-indexed-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "LINUX_INDEXED_OK" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-indexed-slow-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_SLOW_DIRECT=0")
set_property(
    TEST linux-native-indexed-slow-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_SLOW_DIRECT=1")
set_property(
    TEST linux-native-indexed-indexed-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_STEP=0")
set_property(
    TEST linux-native-indexed-own-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_OWN=0")
set_property(
    TEST linux-native-indexed-instance-step-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_STEP=0")
set_property(
    TEST linux-native-indexed-instance-leaf-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=0")
set_property(
    TEST linux-native-indexed-instance-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF=0")
set_property(
    TEST linux-native-indexed-instance-observe
    APPEND
    PROPERTY ENVIRONMENT "QJS_OBSERVE_FRAME_INSTANCEOF=1")
set_property(
    TEST linux-native-indexed-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-indexed-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
set_property(
    TEST linux-native-indexed-register-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_property(
    TEST linux-native-indexed-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")

foreach(variant direct coercion)
    add_executable(linux-indexed-${variant}-api tests/common/linux/native_linux_publication.c)
    target_compile_definitions(linux-indexed-${variant}-api PRIVATE QJS_TEST_INDEXED_PROTOCOL)
    if(variant STREQUAL "coercion")
        target_compile_definitions(linux-indexed-${variant}-api PRIVATE QJS_TEST_INDEXED_COERCION)
    endif()
    target_compile_options(linux-indexed-${variant}-api PRIVATE -UNDEBUG -Wall -Wextra -Werror)
    target_link_libraries(linux-indexed-${variant}-api PRIVATE qjs)
    foreach(
        mode
        on
        slow-zero
        indexed-zero
        own-zero
        instance-step-zero
        instance-leaf-zero
        publish-zero
        shared-zero
        slow-host-zero
        frame-zero)
        add_test(NAME linux-native-indexed-${variant}-api-${mode}
                 COMMAND linux-indexed-${variant}-api)
        set_tests_properties(
            linux-native-indexed-${variant}-api-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_INDEXED_API_OK" TIMEOUT 120)
    endforeach()
    foreach(mode on slow-zero own-zero instance-leaf-zero frame-zero)
        add_test(NAME linux-native-indexed-${variant}-oom-${mode}
                 COMMAND linux-indexed-${variant}-api oom)
        set_tests_properties(
            linux-native-indexed-${variant}-oom-${mode}
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                       "LINUX_INDEXED_OOM_OK" TIMEOUT 120)
    endforeach()
    foreach(kind api oom)
        set_property(
            TEST linux-native-indexed-${variant}-${kind}-slow-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_SLOW_DIRECT=0")
        set_property(
            TEST linux-native-indexed-${variant}-${kind}-own-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_OWN=0")
        set_property(
            TEST linux-native-indexed-${variant}-${kind}-instance-leaf-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=0")
        set_property(
            TEST linux-native-indexed-${variant}-${kind}-frame-zero
            APPEND
            PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
    endforeach()
    set_property(
        TEST linux-native-indexed-${variant}-api-indexed-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_STEP=0")
    set_property(
        TEST linux-native-indexed-${variant}-api-instance-step-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_STEP=0")
    set_property(
        TEST linux-native-indexed-${variant}-api-publish-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
    set_property(
        TEST linux-native-indexed-${variant}-api-shared-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")
    set_property(
        TEST linux-native-indexed-${variant}-api-slow-host-zero
        APPEND
        PROPERTY ENVIRONMENT "QJS_DISABLE_SLOW_HOST_SHARE=0")
endforeach()

# Scalar leaves retain all observing/failing cases in the original call protocol.
foreach(
    mode
    on
    off-zero
    off-one
    frame-zero
    register-zero
    publish-zero
    shared-zero)
    add_test(
        NAME linux-native-integer-expression-${mode}
        COMMAND qjs_exe --std
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_integer_expression.js")
    set_tests_properties(
        linux-native-integer-expression-${mode}
        PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=256" PASS_REGULAR_EXPRESSION
                   "integer-expression semantics OK 36892" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-integer-expression-off-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF=0")
set_property(
    TEST linux-native-integer-expression-off-one
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF=1")
set_property(
    TEST linux-native-integer-expression-frame-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=0")
set_property(
    TEST linux-native-integer-expression-register-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=0")
set_property(
    TEST linux-native-integer-expression-publish-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=0")
set_property(
    TEST linux-native-integer-expression-shared-zero
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_SHARED_ENTRY=0")

# Exact nonescaping forwarding constructors: public ownership, reentry,
# cross-realm/descriptor fallbacks, callsite identity and allocation faults.
add_executable(linux-virtual-arguments tests/common/linux/native_linux_virtual_arguments.c)
target_compile_features(linux-virtual-arguments PRIVATE c_std_11)
target_compile_options(linux-virtual-arguments PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_link_libraries(linux-virtual-arguments PRIVATE qjs)
foreach(
    mode
    on
    zero
    one
    frame
    register
    arguments
    apply
    forward
    publish
    borrow)
    add_test(
        NAME linux-native-virtual-arguments-${mode}
        COMMAND linux-virtual-arguments
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/linux/test_linux_virtual_arguments.js")
    set_tests_properties(
        linux-native-virtual-arguments-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "VIRTUAL_ARGUMENTS_HOST_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256;QJS_OBSERVE_FRAME_ARGUMENTS=1" TIMEOUT 120)
endforeach()
set_property(
    TEST linux-native-virtual-arguments-on
    APPEND
    PROPERTY ENVIRONMENT "REQUIRE_VIRTUAL_HIT=1")
foreach(
    pair
    "zero;QJS_DISABLE_VIRTUAL_ARGUMENTS"
    "one;QJS_DISABLE_VIRTUAL_ARGUMENTS"
    "frame;QJS_DISABLE_INTERP_FRAME"
    "register;QJS_DISABLE_REGISTER_INTERP"
    "arguments;QJS_DISABLE_FRAME_ARGUMENTS"
    "apply;QJS_DISABLE_FRAME_APPLY_DIRECT"
    "forward;QJS_DISABLE_FRAME_CALL_FORWARD"
    "publish;QJS_DISABLE_DEFERRED_FRAME_PUBLISH"
    "borrow;QJS_DISABLE_FRAME_ARGUMENTS_BORROW")
    list(GET pair 0 mode)
    list(GET pair 1 control)
    if(mode STREQUAL "one")
        set(value 1)
    else()
        set(value 0)
    endif()
    set_property(
        TEST linux-native-virtual-arguments-${mode}
        APPEND
        PROPERTY ENVIRONMENT "${control}=${value}")
    if(mode STREQUAL "publish")
        set_property(
            TEST linux-native-virtual-arguments-${mode}
            APPEND
            PROPERTY ENVIRONMENT "REQUIRE_VIRTUAL_HIT=1")
    else()
        set_property(
            TEST linux-native-virtual-arguments-${mode}
            APPEND
            PROPERTY ENVIRONMENT "REQUIRE_VIRTUAL_FALLBACK=1")
    endif()
endforeach()
foreach(mode on off)
    add_test(NAME linux-native-virtual-arguments-oom-${mode} COMMAND linux-virtual-arguments oom)
    set_tests_properties(
        linux-native-virtual-arguments-oom-${mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "VIRTUAL_ARGUMENTS_OOM_OK" ENVIRONMENT
                   "QJS_EXPERIMENT_ALLOCATOR=256" TIMEOUT 180)
endforeach()
set_property(
    TEST linux-native-virtual-arguments-oom-off
    APPEND
    PROPERTY ENVIRONMENT "QJS_DISABLE_VIRTUAL_ARGUMENTS=0")

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
    add_test(
        NAME linux-x86-elf-tools
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/linux/test_linux_elf_tools.py" --object
            "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/qjs.dir/src/x86/linux/integer-expression.c.o"
            --output "${CMAKE_CURRENT_BINARY_DIR}/generated/linux-abi/elf-tools-test.json")
    add_test(NAME linux-x86-elf-policy
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/linux/test_elf_machine_x86.py")
endif()
