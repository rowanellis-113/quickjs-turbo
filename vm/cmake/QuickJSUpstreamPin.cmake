# Exact QuickJS-NG base selected from Capsid; no Capsid patches are imported.
# Source: https://github.com/ErosZy/capsid/blob/4ed21e6623814f485fd7cca7a223ad66c0be1dcf/docs/txiki-upgrade-baseline.json
set(QJS_UPSTREAM_REVISION "bf8988fc401e737f9946cd10a3463b48aab0fd7e")
set(QJS_UPSTREAM_VERSION "0.15.1")
set(qjs_upstream_source_pin
    "quickjs.c:ddab054455e43cfafbe5c0671fa38acd9f3a1eac4ce2a49a97dfec6437701ebe"
    "quickjs.h:8011dd97fbeb1cc551020f90dde4b4f21f83a6145b6254b5e815f6d885ed3874"
    "quickjs-opcode.h:0054b0c45fd091afa308c3fb93b5862e0b071235918d3d73e413d23fce388bbc"
    "quickjs-atom.h:66654ae6533d15073ea527979c453709d7ed83162142c656095a10dcef737a60"
    "quickjs-c-atomics.h:29883c742a5c512278fce54d19b1b9af949006e1d7dfc9ffa2e0946b184d8c5c"
    "cutils.h:b93331edd1bf86e1c0b516657d0b16b95bba5f24d799d9824df16f903173b5c2"
    "list.h:cb6e24e8ee54bccdd66234fe54cd702d1160b9841db2b9b9adeb5003afe301d5"
    "dtoa.c:a8d2cf2d04db406e0c16acdd95ab0e709d309902865722f41dac07a1ba5676af"
    "dtoa.h:1c4a4540c0038632c8a4c225472fbc21bd476fb35c4da4a857a11965b58231b9"
    "libregexp.c:d1e7c4280e1948a25310aaa80aedc273b6fe12322964965f9025ba1800f2c14d"
    "libregexp.h:991adcaedb0e0ab653811f7f6e1244a23a7454dff6ce647b518df9a22201c122"
    "libregexp-opcode.h:c5ee518885eb6e720537b6df5565ddc2bcaadbda512f3fc072adc96fb24a7648"
    "libunicode.c:62bfe07a00c297d62cf89d2a147f1d0cd0e90ae7c8058e0fabb66e896950a702"
    "libunicode.h:70f9f38b1cd10186d22e30d5f604465f4747662701f3310e089e5749060f4d4f"
    "libunicode-table.h:391d664bacefef239c4349d338c59bf6aa70128f23b105bb5c052db48a14c439"
    "quickjs-libc.c:827118a0ad4272559e03cd2d6b84fe810bf8c522dd55ceef8120add6f5abaa70"
    "quickjs-libc.h:55c6b4504124941903fc09c35aecedddb88fa45c27d5e62c65962bb670ae17d1"
    "qjs.c:86e68b2868bedbca894155b2ca8ac27359e4f545f14c6bed3d0f2cb7908f93df"
    "qjsc.c:0d8ce14fce606a87bbdf9521badd2147c12a1ad5961510fec9e69a3292e59a47")

# Normalize checkout line endings; preserve the upstream source bytes otherwise.
if(NOT DEFINED QJS_UPSTREAM_DIR)
    get_filename_component(QJS_UPSTREAM_DIR "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
endif()
foreach(qjs_pin IN LISTS qjs_upstream_source_pin)
    string(REPLACE ":" ";" qjs_pin_parts "${qjs_pin}")
    list(GET qjs_pin_parts 0 qjs_pin_name)
    list(GET qjs_pin_parts 1 qjs_pin_expected)
    file(READ "${QJS_UPSTREAM_DIR}/${qjs_pin_name}" qjs_pin_text)
    string(REPLACE "\r\n" "\n" qjs_pin_text "${qjs_pin_text}")
    string(SHA256 qjs_pin_actual "${qjs_pin_text}")
    if(NOT qjs_pin_actual STREQUAL qjs_pin_expected)
        message(
            FATAL_ERROR
                "QuickJS upstream pin ${QJS_UPSTREAM_REVISION}: ${qjs_pin_name} differs. Review and update the pin explicitly."
        )
    endif()
endforeach()
unset(qjs_pin_text)
message(STATUS "QuickJS-NG ${QJS_UPSTREAM_VERSION}, pinned upstream ${QJS_UPSTREAM_REVISION}")
