# Pure-CMake pre-generated assembly bundle loader (zero Python dependency).
# Verifies upstream pin and per-file SHA256 hashes from PREGEN-MANIFEST.json.
function(qjs_load_pregen_bundle bundle_slug)
    set(bundle_dir "${QJS_PREGEN_DIR}/${bundle_slug}")
    set(manifest_path "${bundle_dir}/PREGEN-MANIFEST.json")
    if(NOT EXISTS "${manifest_path}")
        message(FATAL_ERROR "Pre-generated bundle manifest not found: ${manifest_path}")
    endif()
    file(READ "${manifest_path}" manifest_json)
    string(JSON manifest_schema GET "${manifest_json}" schema)
    if(NOT manifest_schema STREQUAL "1")
        message(
            FATAL_ERROR
                "Unsupported pregen manifest schema '${manifest_schema}' in ${manifest_path}")
    endif()
    string(JSON manifest_upstream GET "${manifest_json}" upstream_revision)
    if(NOT manifest_upstream STREQUAL "${QJS_UPSTREAM_REVISION}")
        message(
            FATAL_ERROR
                "Pregen bundle upstream mismatch: bundle=${manifest_upstream}, expected=${QJS_UPSTREAM_REVISION}"
        )
    endif()
    string(JSON manifest_property_ic GET "${manifest_json}" property_ic)
    if(QJS_PROPERTY_IC AND NOT manifest_property_ic STREQUAL "ON")
        message(
            FATAL_ERROR
                "QJS_PROPERTY_IC=ON does not match pregen bundle (${manifest_path} has property_ic=${manifest_property_ic})"
        )
    elseif(NOT QJS_PROPERTY_IC AND manifest_property_ic STREQUAL "ON")
        message(
            FATAL_ERROR
                "QJS_PROPERTY_IC=OFF does not match pregen bundle (${manifest_path} has property_ic=ON)"
        )
    endif()
    string(JSON file_count LENGTH "${manifest_json}" files)
    if(file_count EQUAL 0)
        message(FATAL_ERROR "Pregen manifest contains no files: ${manifest_path}")
    endif()
    math(EXPR last_idx "${file_count} - 1")
    foreach(idx RANGE 0 ${last_idx})
        string(JSON rel_path MEMBER "${manifest_json}" files ${idx})
        string(JSON expected_sha GET "${manifest_json}" files "${rel_path}")
        set(src_file "${bundle_dir}/${rel_path}")
        if(NOT EXISTS "${src_file}")
            message(FATAL_ERROR "Missing pregen file: ${src_file}")
        endif()
        file(SHA256 "${src_file}" actual_sha)
        if(NOT actual_sha STREQUAL "${expected_sha}")
            message(
                FATAL_ERROR
                    "SHA256 mismatch for pregen file ${rel_path}: expected ${expected_sha}, got ${actual_sha}"
            )
        endif()
        set(dst_file "${CMAKE_CURRENT_BINARY_DIR}/${rel_path}")
        get_filename_component(dst_parent "${dst_file}" DIRECTORY)
        file(MAKE_DIRECTORY "${dst_parent}")
        configure_file("${src_file}" "${dst_file}" COPYONLY)
    endforeach()
    set_property(
        DIRECTORY
        APPEND
        PROPERTY CMAKE_CONFIGURE_DEPENDS "${manifest_path}")
    if(EXISTS "${CMAKE_CURRENT_BINARY_DIR}/generated/backports/BACKPORTS.json")
        set(QJS_PREGEN_BACKPORTS_READY
            TRUE
            PARENT_SCOPE)
    endif()
    message(STATUS "QuickJS pre-generated bundle verified: ${bundle_dir} (${file_count} files)")
endfunction()
