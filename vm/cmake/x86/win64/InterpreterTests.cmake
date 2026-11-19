# Windows x86-64 native interpreter verification.
if(QJS_ENABLE_INTERP_FRAME
   AND MINGW
   AND QJS_INTERP_FRAME_REGISTER_ABI
   AND QJS_INTERP_FRAME_INTERNAL_ENTRY
   AND NOT QJS_INTERP_FRAME_DIAGNOSTICS)
    add_executable(interpreter-test-apply_forward tests/common/native_apply_forward.c)
    target_compile_features(interpreter-test-apply_forward PRIVATE c_std_11)
    target_link_libraries(interpreter-test-apply_forward PRIVATE qjs)
    foreach(apply_mode default off off-zero)
        add_test(NAME interpreter-apply-forward-host-${apply_mode}
                 COMMAND interpreter-test-apply_forward)
        set_tests_properties(interpreter-apply-forward-host-${apply_mode}
                             PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_APPLY_DIRECT=1")
    endforeach()
    set_tests_properties(
        interpreter-apply-forward-host-off
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_APPLY_DIRECT=1;QJS_DISABLE_FRAME_APPLY_DIRECT=1")
    set_tests_properties(
        interpreter-apply-forward-host-off-zero
        PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_APPLY_DIRECT=1;QJS_DISABLE_FRAME_APPLY_DIRECT=0")
endif()

if(QJS_ENABLE_INTERP_FRAME
   AND MINGW
   AND QJS_INTERP_FRAME_REGISTER_ABI
   AND QJS_INTERP_FRAME_INTERNAL_ENTRY
   AND NOT QJS_INTERP_FRAME_DIAGNOSTICS)
    add_executable(interpreter-test-argument_constructor tests/common/native_argument_constructor.c)
    target_compile_features(interpreter-test-argument_constructor PRIVATE c_std_11)
    target_link_libraries(interpreter-test-argument_constructor PRIVATE qjs)
    foreach(argument_ctor_mode default off off-zero)
        add_test(NAME interpreter-argument-constructor-host-${argument_ctor_mode}
                 COMMAND interpreter-test-argument_constructor)
        set_tests_properties(interpreter-argument-constructor-host-${argument_ctor_mode}
                             PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_ARGUMENTS=1")
    endforeach()
    set_tests_properties(
        interpreter-argument-constructor-host-off
        PROPERTIES ENVIRONMENT
                   "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=1")
    set_tests_properties(
        interpreter-argument-constructor-host-off-zero
        PROPERTIES ENVIRONMENT
                   "QJS_OBSERVE_FRAME_ARGUMENTS=1;QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
endif()

if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR
   AND MINGW
   AND QJS_INTERP_FRAME_REGISTER_ABI
   AND QJS_INTERP_FRAME_INTERNAL_ENTRY
   AND NOT QJS_INTERP_FRAME_DIAGNOSTICS)
    foreach(native_rope_mode disabled zero)
        add_test(NAME interpreter-string-concat-native-append-${native_rope_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
    endforeach()
    set_tests_properties(interpreter-string-concat-native-append-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_NATIVE_ROPE_APPEND=1")
    set_tests_properties(interpreter-string-concat-native-append-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_NATIVE_ROPE_APPEND=0")
    set(frame_native_rope_objdump "${QJS_FRAME_OBJDUMP}")
    if(NOT frame_native_rope_objdump)
        set(frame_native_rope_objdump "${CMAKE_OBJDUMP}")
    endif()
    add_test(
        NAME interpreter-native-rope-unwind
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_native_rope_unwind.py" --image
            "$<TARGET_FILE:qjs_exe>" --objdump "${frame_native_rope_objdump}" --report
            "${CMAKE_CURRENT_BINARY_DIR}/tests/native-rope-unwind.json")
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    foreach(indexed_mode native c disabled)
        add_test(NAME interpreter-indexed-own-${indexed_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_indexed_own.js")
    endforeach()
    set_tests_properties(
        interpreter-indexed-own-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-indexed-own-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_OWN=1")
    if(NOT BUILD_SHARED_LIBS)
        add_executable(interpreter-test-indexed_own tests/common/native_indexed_own.c)
        target_link_libraries(interpreter-test-indexed_own PRIVATE qjs)
        foreach(indexed_mode native c disabled)
            add_test(NAME interpreter-indexed-own-host-${indexed_mode}
                     COMMAND interpreter-test-indexed_own)
        endforeach()
        set_tests_properties(
            interpreter-indexed-own-host-c
            PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
        set_tests_properties(interpreter-indexed-own-host-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INDEXED_OWN=1")
    endif()
    foreach(regexp_mode native c disabled closure-disabled)
        add_test(NAME interpreter-regexp-start-${regexp_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_start.js")
    endforeach()
    set_tests_properties(
        interpreter-regexp-start-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-regexp-start-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_START_FILTER=1")
    set_tests_properties(interpreter-regexp-start-closure-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_CASE_CLOSURE=1")
    add_test(NAME interpreter-regexp-differential
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_differential.js")
    set_tests_properties(interpreter-regexp-differential
                         PROPERTIES PASS_REGULAR_EXPRESSION "REGEXP_DIFFERENTIAL 251621 9b20c58d")
    if(NOT BUILD_SHARED_LIBS AND QJS_UPSTREAM_REVISION STREQUAL
                                 "bf8988fc401e737f9946cd10a3463b48aab0fd7e")
        add_executable(interpreter-test-regexp_casefold tests/common/native_regexp_casefold.c)
        target_link_libraries(interpreter-test-regexp_casefold PRIVATE qjs)
        add_test(NAME interpreter-regexp-casefold-domain COMMAND interpreter-test-regexp_casefold)
    endif()
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    add_test(NAME interpreter-native-abi-contracts
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/common/test_vm_abi.py")
    add_test(NAME interpreter-native-private-contracts
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_private.py")
    add_test(NAME interpreter-native-core-route-contracts
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_core_routes.py")
    set(frame_native_tests
        api
        register_abi
        internal_api
        call_env
        call_link_lifecycle
        call_link_vm
        null_allocation
        wire
        regexp_flags
        strict_identity
        array_own
        this_field_leaf
        array_copy
        default_string_sort)
    if(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        list(APPEND frame_native_tests instanceof)
    endif()
    if(MINGW
       AND QJS_INTERP_FRAME_REGISTER_ABI
       AND QJS_INTERP_FRAME_INTERNAL_ENTRY)
        add_test(
            NAME interpreter-standard-unwind-directory
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_standard_directory.py" --build
                "${CMAKE_CURRENT_BINARY_DIR}" --image "$<TARGET_FILE:qjs_exe>" --archive
                "$<TARGET_FILE:qjs>")
    endif()
    if(MSVC)
        add_test(
            NAME interpreter-unwind-capacity-isolation
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_unwind_capacity.py"
                --core-object "${QJS_FRAME_GENERATED_DIR}/quickjs-core-original.obj")
    endif()
    if(QJS_INTERP_FRAME_TAIL_ENTRY)
        list(APPEND frame_native_tests entry_abi)
        # Link the real public-entry object against checked stub executors.
        # This catches stale private offsets without depending on heap layout.
        add_executable(
            interpreter-test-entry_dispatch
            tests/common/native_entry_dispatch.c "${frame_entry_object}"
            "${QJS_FRAME_GENERATED_DIR}/interpreter-private-abi-values.h")
        target_include_directories(
            interpreter-test-entry_dispatch
            PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}"
                    "${QJS_FRAME_GENERATED_DIR}")
        add_test(NAME interpreter-native-entry_dispatch COMMAND interpreter-test-entry_dispatch)
    endif()
    if(QJS_INTERP_FRAME_INTERNAL_ENTRY AND QJS_INTERP_FRAME_REGISTER_ABI)
        add_executable(interpreter-test-env-runtime tests/common/native_env_runtime.c)
        target_include_directories(
            interpreter-test-env-runtime PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                 "${QJS_FRAME_GENERATED_DIR}")
        target_link_libraries(interpreter-test-env-runtime PRIVATE qjs)
        foreach(
            env_mode
            -1
            0
            1
            2
            3
            4
            5)
            add_test(NAME interpreter-env-runtime-${env_mode} COMMAND interpreter-test-env-runtime
                                                                      "${env_mode}")
        endforeach()
    endif()
    foreach(frame_test IN LISTS frame_native_tests)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/native_${frame_test}.c")
            set(frame_native_src
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/native_${frame_test}.c")
        else()
            set(frame_native_src "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/native_${frame_test}.c")
        endif()
        add_executable(interpreter-test-${frame_test} "${frame_native_src}")
        target_include_directories(
            interpreter-test-${frame_test} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                   "${QJS_FRAME_GENERATED_DIR}")
        target_link_libraries(interpreter-test-${frame_test} PRIVATE qjs)
        if(QJS_INTERP_FRAME_DIAGNOSTICS)
            target_compile_definitions(interpreter-test-${frame_test}
                                       PRIVATE QJS_INTERP_FRAME_DIAGNOSTICS)
        endif()
        add_test(NAME interpreter-native-${frame_test} COMMAND interpreter-test-${frame_test})
    endforeach()
    if(MINGW AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        # Match the generated Context layout in the independent polling oracle.
        get_target_property(instanceof_definitions qjs COMPILE_DEFINITIONS)
        target_compile_definitions(interpreter-test-instanceof PRIVATE ${instanceof_definitions})
        target_compile_features(interpreter-test-instanceof PRIVATE c_std_11)
        foreach(leaf_mode off off-zero)
            add_test(NAME interpreter-native-instanceof-leaf-${leaf_mode}
                     COMMAND interpreter-test-instanceof)
            set_tests_properties(
                interpreter-native-instanceof-leaf-${leaf_mode}
                PROPERTIES PASS_REGULAR_EXPRESSION "LEAF-OWNERSHIP-POLL-ORACLE 8 enabled=0")
        endforeach()
        set_tests_properties(interpreter-native-instanceof-leaf-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=1")
        set_tests_properties(interpreter-native-instanceof-leaf-off-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=0")
        add_test(NAME interpreter-native-instanceof-coverage
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_instanceof.js")
        set_tests_properties(
            interpreter-native-instanceof-coverage
            PROPERTIES ENVIRONMENT "QJS_OBSERVE_FRAME_INSTANCEOF=1" PASS_REGULAR_EXPRESSION
                       "INSTANCEOF .*hits\":[1-9][0-9][0-9][0-9]")
    endif()
    foreach(copy_mode c disabled)
        add_test(NAME interpreter-array-copy-host-${copy_mode} COMMAND interpreter-test-array_copy)
    endforeach()
    set_tests_properties(
        interpreter-array-copy-host-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-array-copy-host-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=0")
    add_executable(interpreter-test-array_copy_gc tests/common/native_array_copy.c)
    target_include_directories(interpreter-test-array_copy_gc PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                                      "${QJS_FRAME_GENERATED_DIR}")
    target_compile_definitions(interpreter-test-array_copy_gc PRIVATE FRAME_ARRAY_COPY_GC_ONLY)
    target_link_libraries(interpreter-test-array_copy_gc PRIVATE qjs)
    foreach(copy_mode native c disabled)
        add_test(NAME interpreter-array-copy-gc-${copy_mode} COMMAND interpreter-test-array_copy_gc)
    endforeach()
    set_tests_properties(
        interpreter-array-copy-gc-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-array-copy-gc-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_ARRAY_COPY_GROW=0")
    add_test(NAME interpreter-native-regexp-flags-disabled COMMAND interpreter-test-regexp_flags)
    set_tests_properties(interpreter-native-regexp-flags-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_FLAGS_LEAF=1")
    add_test(NAME interpreter-native-regexp-flags-batch-disabled
             COMMAND interpreter-test-regexp_flags)
    set_tests_properties(interpreter-native-regexp-flags-batch-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_FLAGS_BATCH=1")
    set_tests_properties(interpreter-native-null_allocation PROPERTIES SKIP_RETURN_CODE 77)
    target_compile_definitions(interpreter-test-call_link_vm PRIVATE FRAME_TEST_CALL_METADATA)
    if(MINGW
       AND QJS_INTERP_FRAME_INTERNAL_ENTRY
       AND NOT QJS_INTERP_FRAME_DIAGNOSTICS)
        target_compile_definitions(interpreter-test-register_abi
                                   PRIVATE FRAME_TEST_GNU_STACK_INSERT FRAME_TEST_GNU_NUMBER_TRUTH)
    endif()
    target_include_directories(interpreter-test-call_env PRIVATE "${QJS_FRAME_GENERATED_DIR}")
    target_include_directories(interpreter-test-call_link_lifecycle
                               PRIVATE "${QJS_FRAME_GENERATED_DIR}")
    add_test(NAME interpreter-native-c-entry-disabled COMMAND interpreter-test-internal_api)
    set_tests_properties(interpreter-native-c-entry-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_C_CALL_ENTRY=1")
    # This retained management-API fixture deliberately requires a cold cache
    # for its forced-allocation OOM/reentry assertions. Its original runner also
    # disabled automatic VM fills; keep that precondition explicit in CTest.
    set_tests_properties(interpreter-native-call_link_lifecycle
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_CALL_LINK_VM=1")
    add_test(NAME interpreter-call-link-lifecycle-disabled
             COMMAND interpreter-test-call_link_lifecycle)
    set_tests_properties(
        interpreter-call-link-lifecycle-disabled
        PROPERTIES ENVIRONMENT "QJS_DISABLE_CALL_LINK_VM=1;QJS_DISABLE_CALL_LINK=1")
    add_test(NAME interpreter-call-link-vm-disabled COMMAND interpreter-test-call_link_vm)
    set_tests_properties(interpreter-call-link-vm-disabled PROPERTIES ENVIRONMENT
                                                                      "QJS_DISABLE_CALL_LINK_VM=1")
    add_test(NAME interpreter-call-link-all-disabled COMMAND interpreter-test-call_link_vm)
    set_tests_properties(interpreter-call-link-all-disabled PROPERTIES ENVIRONMENT
                                                                       "QJS_DISABLE_CALL_LINK=1")
    foreach(frame_control QJS_DISABLE_CALL_META_DIRECT QJS_DISABLE_CALL_META_DESTINATION)
        add_test(NAME interpreter-call-link-${frame_control} COMMAND interpreter-test-call_link_vm)
        set_tests_properties(interpreter-call-link-${frame_control} PROPERTIES ENVIRONMENT
                                                                               "${frame_control}=1")
    endforeach()
    # VM CallLink allocation is opt-in on both native Windows compilers.
    # Positive tests still exercise actual hits; disable controls win opt-in.
    if(MINGW OR MSVC)
        foreach(
            frame_case
            interpreter-native-call_link_vm interpreter-call-link-vm-disabled
            interpreter-call-link-all-disabled interpreter-call-link-QJS_DISABLE_CALL_META_DIRECT
            interpreter-call-link-QJS_DISABLE_CALL_META_DESTINATION)
            set_property(
                TEST ${frame_case}
                APPEND
                PROPERTY ENVIRONMENT "QJS_ENABLE_CALL_LINK_VM=1")
        endforeach()
        add_test(NAME interpreter-call-link-opt-in-zero COMMAND interpreter-test-call_link_vm)
        set_tests_properties(interpreter-call-link-opt-in-zero
                             PROPERTIES ENVIRONMENT "QJS_ENABLE_CALL_LINK_VM=0")
        add_test(NAME interpreter-call-link-disable-zero COMMAND interpreter-test-call_link_vm)
        set_tests_properties(
            interpreter-call-link-disable-zero
            PROPERTIES ENVIRONMENT "QJS_ENABLE_CALL_LINK_VM=0;QJS_DISABLE_CALL_LINK_VM=0")
        add_test(
            NAME interpreter-call-link-default-off
            COMMAND
                "${CMAKE_COMMAND}" -E env --unset=QJS_ENABLE_CALL_LINK_VM
                FRAME_TEST_CALL_LINK_DEFAULT_OFF=1 "$<TARGET_FILE:interpreter-test-call_link_vm>")
    endif()
    foreach(frame_control QJS_DISABLE_CALL_LINK QJS_DISABLE_CALL_LINK_VM
                          QJS_DISABLE_CALL_META_DIRECT QJS_DISABLE_CALL_META_DESTINATION)
        add_test(NAME interpreter-call-control-${frame_control}
                 COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_semantics.js")
        set_tests_properties(interpreter-call-control-${frame_control}
                             PROPERTIES ENVIRONMENT "${frame_control}=1")
    endforeach()
    add_test(NAME interpreter-call-env-build-contracts
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_call_env.py")
    foreach(
        frame_test
        bigint
        c_invoke
        dense_pop
        function_creation
        internal
        lazy_scope
        leaf_entries
        native_hot
        object_proto
        object_proto_hint
        register
        selected_regexp
        regexp_flags
        string_proto
        wide_arity
        retained)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_${frame_test}.js")
            set(frame_js_src "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_${frame_test}.js")
        else()
            set(frame_js_src "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_${frame_test}.js")
        endif()
        add_test(NAME interpreter-${frame_test} COMMAND qjs_exe -m "${frame_js_src}")
    endforeach()
    add_test(NAME interpreter-regexp-flags-disabled
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_flags.js")
    set_tests_properties(interpreter-regexp-flags-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_FLAGS_LEAF=1")
    add_test(NAME interpreter-regexp-flags-batch-disabled
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_flags.js")
    set_tests_properties(interpreter-regexp-flags-batch-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_FLAGS_BATCH=1")
    # An actual disabled-path run of the same source/image, not an inferred fallback.
    add_test(NAME interpreter-disabled-semantics
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_semantics.js")
    set_tests_properties(
        interpreter-disabled-semantics
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    add_test(
        NAME interpreter-standard-exception-directory
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/coff/validate-native-image.py"
            "$<TARGET_FILE:qjs_exe>" "$<TARGET_FILE:interpreter-test-register_abi>")
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    add_test(
        NAME interpreter-default-sort-capability
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_default_sort_capability.py"
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(sort_mode off-zero ic-off c)
        add_test(NAME interpreter-native-default-string-sort-${sort_mode}
                 COMMAND interpreter-test-default_string_sort)
    endforeach()
    set_tests_properties(interpreter-native-default-string-sort-off-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=0")
    set_tests_properties(interpreter-native-default-string-sort-ic-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
    set_tests_properties(
        interpreter-native-default-string-sort-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    add_test(
        NAME interpreter-async-capability-contract
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_async_capability_contract.py"
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}")
endif()

if(QJS_BACKPORT_CONTEXT_OOM AND QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "WIN64")
    add_test(
        NAME interpreter-compiler-plan-isolation
        COMMAND
            "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/win64/test_vm_compiler_plan_isolation.py"
            --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}")
    set_tests_properties(interpreter-compiler-plan-isolation
                         PROPERTIES PASS_REGULAR_EXPRESSION "COMPILER_PLAN_ISOLATION_OK")
endif()
