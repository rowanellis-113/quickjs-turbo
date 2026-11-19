if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "LINUX_X86_64")
    if(TARGET qjs_exe)
        add_custom_command(
            TARGET qjs_exe
            POST_BUILD
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/linux/record-native.py" --source
                "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --binary
                "$<TARGET_FILE:qjs_exe>" --archive "$<TARGET_FILE:qjs>"
            VERBATIM)
    endif()
    if(QJS_ENABLE_INSTALL)
        file(GLOB qjs_linux_install_docs CONFIGURE_DEPENDS
             "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/x86/linux/LINUX-*.txt"
             "${CMAKE_CURRENT_SOURCE_DIR}/docs/architecture/x86/linux/LINUX-*.json")
        set(qjs_linux_install_files "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json"
                                    ${qjs_linux_install_docs})
        if(TARGET qjs_exe)
            list(APPEND qjs_linux_install_files "${CMAKE_CURRENT_BINARY_DIR}/BUILD.json"
                 "${CMAKE_CURRENT_BINARY_DIR}/native-elf.txt")
        endif()
        install(FILES ${qjs_linux_install_files} DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    endif()
endif()
