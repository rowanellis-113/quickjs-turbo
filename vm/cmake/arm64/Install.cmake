if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64" AND qjs_arm_arguments_enabled)
    set(qjs_arm_virtual "${qjs_arm_vm_dir}/quickjs-linux-virtual-arguments.c")
    set_source_files_properties(
        "${qjs_arm_virtual}"
        PROPERTIES
            GENERATED TRUE
            COMPILE_DEFINITIONS
            "QJS_INTERP_FRAME_INTERNAL_ENTRY;QJS_INTERP_FRAME_REGISTER_ABI;QJS_INTERP_FRAME_LINUX;QJS_LINUX_REGISTER_FOUNDATION"
    )
    target_sources(qjs PRIVATE "${qjs_arm_virtual}")
    target_include_directories(qjs PRIVATE "${qjs_arm_vm_dir}"
                                           "${CMAKE_CURRENT_BINARY_DIR}/generated/backports")
endif()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_AARCH64" AND QJS_ENABLE_INSTALL)
    install(
        FILES
            "${qjs_arm_vm_dir}/VM.json"
            "${qjs_arm_vm_dir}/LITERALS.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-LITERALS.txt"
            "${qjs_arm_vm_dir}/INDEXED.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-INDEXED.txt"
            "${qjs_arm_vm_dir}/VARARGS.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-VARARGS.txt"
            "${qjs_arm_vm_dir}/ARGUMENTS.json"
            "${qjs_arm_vm_dir}/VIRTUAL-ARGUMENTS.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-ARGUMENTS.txt"
            "${qjs_arm_vm_dir}/FORWARDING.json"
            "${qjs_arm_vm_dir}/NULL-PROTO.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-NULL-PROTO.txt"
            "${qjs_arm_vm_dir}/ARRAY-WORKERS.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-ARRAY-WORKERS.txt"
            "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-REGISTER.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-PUBLICATION.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-C-ENTRY.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-C-RETURN.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-PROPERTIES.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-PROPERTY-PRIMITIVES.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-PROPERTY-HINTS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-PROPERTY-PROTOTYPES.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-REFERENCE-STORES.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-GLOBAL-BINDINGS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-COMPARISONS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-CONSTRUCTORS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-ITERATORS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-NUMERIC-WORKERS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-STRINGS.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-STACK-INSERT.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-ARRAY-OWN.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-FORWARDING.txt"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-MECHANISMS.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${qjs_arm_vm_dir}/CHECK.json"
        OPTIONAL
        DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt"
                  "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/build/product-linux-aarch64.sh"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(FILES "${qjs_arm_vm_dir}/SCALAR-OPS.json"
                  "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-SCALAR-OPS.txt"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${qjs_arm_vm_dir}/CALL-LEAVES.json"
              "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-CALL-LEAVES.txt"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(FILES "${qjs_arm_vm_dir}/STACK-INSERT.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/stack-insert.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-STACK-INSERT.json")
    install(FILES "${qjs_arm_vm_dir}/STRING-WORKERS.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/strings.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-STRINGS.json")
    install(FILES "${qjs_arm_vm_dir}/NUMERIC-WORKERS.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(FILES "${qjs_arm_vm_dir}/NUMBER-DATAFLOW.json"
                  "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/arm64/LINUX-AARCH64-VALUE-FLOW.txt"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/number-dataflow.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-NUMBER-DATAFLOW.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/linear-return.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-LINEAR-RETURN.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/numeric-workers.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-NUMERIC-WORKERS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/numeric.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-NUMERIC.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/window.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-WINDOW.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/captures.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-CAPTURES.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/literals.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-LITERALS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/indexed.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-INDEXED.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/varargs.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-VARARGS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/arguments.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ARGUMENTS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/null-proto.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-NULL-PROTO.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/array-workers.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ARRAY-WORKERS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/forwarding.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-FORWARDING.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/shared.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-SHARED.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/prepared-callbacks.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PREPARED-CALLBACKS.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/async-generator.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ASYNC-GENERATOR.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/json.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-JSON.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/regexp.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-REGEXP.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/admission.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ADMISSION.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/publication.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PUBLICATION.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/c-entry.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-C-ENTRY.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/c-return.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-C-RETURN.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/properties.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PROPERTIES.json")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-primitives.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PROPERTY-PRIMITIVES.json")
    install(FILES "${qjs_arm_vm_dir}/PROPERTY-PRIMITIVES.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-hints.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PROPERTY-HINTS.json")
    install(FILES "${qjs_arm_vm_dir}/PROPERTY-HINTS.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/property-prototypes.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-PROPERTY-PROTOTYPES.json")
    install(FILES "${qjs_arm_vm_dir}/PROPERTY-PROTOTYPES.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/reference-stores.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-REFERENCE-STORES.json")
    install(FILES "${qjs_arm_vm_dir}/REFERENCE-STORES.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/global-bindings.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-GLOBAL-BINDINGS.json")
    install(FILES "${qjs_arm_vm_dir}/GLOBAL-BINDINGS.json"
                  "${qjs_arm_vm_dir}/GLOBAL-ORIGINAL-ALGORITHMS.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/constructors.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-CONSTRUCTORS.json")
    install(FILES "${qjs_arm_vm_dir}/CONSTRUCTORS.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/array-own.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ARRAY-OWN.json")
    install(FILES "${qjs_arm_vm_dir}/ARRAY-OWN.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/iterators.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-ITERATORS.json")
    install(FILES "${qjs_arm_vm_dir}/ITERATORS.json" "${qjs_arm_vm_dir}/EXTENDED-CALLS.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/comparisons.json"
        DESTINATION "${CMAKE_INSTALL_DOCDIR}"
        RENAME "AARCH64-COMPARISONS.json")
    if(QJS_AARCH64_FAST_VM)
        install(
            FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/fast-vm.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}"
            RENAME "AARCH64-FAST-VM.json")
        install(FILES "${qjs_arm_vm_dir}/FAST-VM.json" DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    endif()
    install(FILES "${qjs_arm_vm_dir}/COMPARISONS.json"
                  "${qjs_arm_vm_dir}/COMPARISONS-ORIGINAL-ALGORITHMS.json"
            DESTINATION "${CMAKE_INSTALL_DOCDIR}")
endif()
