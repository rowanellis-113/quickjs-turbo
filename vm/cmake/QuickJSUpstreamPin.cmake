# Pinned upstream QuickJS-NG base matching txiki.js v26.11.0 deps/quickjs.
set(QJS_UPSTREAM_REVISION "7b5f588e0f9b643e2996f291bfc861abeaceddc2")
set(QJS_UPSTREAM_VERSION "0.17.0")
set(qjs_upstream_source_pin
    "quickjs.c:51b1d3919ffe812d0e01793f85d347bcea48c924c11262c5c5f00df1e4759d74"
    "quickjs.h:50689b8d0ef5eedcbb8513a45d1a5fd56c81c124148b79af991abf394df3024a"
    "quickjs-opcode.h:0054b0c45fd091afa308c3fb93b5862e0b071235918d3d73e413d23fce388bbc"
    "quickjs-atom.h:8045b870825a43ecdb50692aac7ad21b43139b288df466ca5f7b780bde4ac13f"
    "quickjs-c-atomics.h:29883c742a5c512278fce54d19b1b9af949006e1d7dfc9ffa2e0946b184d8c5c"
    "cutils.h:dffec8bea17f08108da5a91c1178804754698bbbb6202dc100268e78e8c5b770"
    "list.h:cb6e24e8ee54bccdd66234fe54cd702d1160b9841db2b9b9adeb5003afe301d5"
    "dtoa.c:a8d2cf2d04db406e0c16acdd95ab0e709d309902865722f41dac07a1ba5676af"
    "dtoa.h:1c4a4540c0038632c8a4c225472fbc21bd476fb35c4da4a857a11965b58231b9"
    "libregexp.c:af13e996abb1767fe0cdfda123c45b811d53688d403a2ac47142e97bf79f1fae"
    "libregexp.h:53ff95a038f7001b752c455d195d998e2955f0ae4ed62a002c13eca798db3ceb"
    "libregexp-opcode.h:2a98d646089f3a72f25480116297c5fdb5b28fd9f815447273951f4ade4a115e"
    "libunicode.c:c4724e77ec5f122373d2635b6d481cfb5d96024a38453a54a0830007c4b5f3c9"
    "libunicode.h:ad13f66aaea3fab1616e84b9c048f2a315e1bdbab628b966617a7a3e55bcba2b"
    "libunicode-table.h:5840a921ac11664b505ee37b1219f518fff2a04972fe848b4bdf1e85c5a0bd83"
    "quickjs-libc.c:60b8af33a1404a842f00de2ccf70d97ebc9a789bdcbe075a6c01b4df47c081a6"
    "quickjs-libc.h:55c6b4504124941903fc09c35aecedddb88fa45c27d5e62c65962bb670ae17d1"
    "qjs.c:ed4ad1b1cff7411f73c98855bddf383bf040bcf79dc950b32b17c1a8edda3a7c"
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
