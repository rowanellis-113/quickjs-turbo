/* The exported native target publishes ordinary .pdata before archiving.
    Those consumers need no second PE exception-directory reservation. Keep
    the historical capacity only for explicit legacy links without the marker;
    native record carriers and their UNWIND_INFO remain intact in both modes. */
__qjs_keep_legacy_unwind = DEFINED(__qjs_native_standard_unwind) ?
    !__qjs_native_standard_unwind : 1;

/* New executable islands follow existing standard PE sections. The existing
    default MinGW script still defines every core section and its contents. */
SECTIONS
{
    .qjsvm BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsvm$*)) }
    .qjsprop BLOCK(__section_alignment__) : { *(.qjsprop) }
    .qjscold BLOCK(__section_alignment__) : { *(.qjscold) }
    .qjsro BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsro$*)) }
    /* Explicitly retain all existing source/ASM contributions first.
        Explicit member selectors preserve CX register/null/owned extraction order.
        EXTERNAL_OBJECT archive order cannot insert the new allocator ahead of
        the existing owned-frame entry points. */
    .qjsleaf BLOCK(__section_alignment__) : { *quickjs-interpreter-register.obj(.qjsleaf) *quickjs-interpreter-null-proto.obj(.qjsleaf) *quickjs-interpreter-owned-win64.S.obj(.qjsleaf) *(.qjsleaf) *(.qjsleaf$zznullfast) *(.qjsleaf$zzzatod) *(.qjsleaf$zzzzlocal) *(.qjsleaf$zzzzlocalguard) }
}
INSERT AFTER .reloc;

/* Keep live semantic islands after live core sections, before DWARF.
    Debug level/path growth must not move live extension RVAs.
    This is semantic ordering, without fixed bases, selected RVAs or padding. */
SECTIONS
{
    .qjscall BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjscall$*)) }
}
INSERT AFTER .qjsleaf;

/* Bounded writable hints follow all old code/data. */
SECTIONS { .qjspmet BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjspmet$*)) } }
INSERT AFTER .qjscall;

/* Root-entry code/data follow CG hints; preserve every inherited RIP target. */
SECTIONS { .qjsroot BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsroot$*)) } }
INSERT AFTER .qjspmet;
SECTIONS { .qjsrmet BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsrmet$*)) } }
INSERT AFTER .qjsroot;

/* Zero-root leaves follow all CM code and writable controls. */
SECTIONS { .qjszero BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjszero$*)) } }
INSERT AFTER .qjsrmet;
SECTIONS { .qjszmet BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjszmet$*)) } }
INSERT AFTER .qjszero;

/* Equal-arity roots follow all CR code and controls. */
SECTIONS { .qjsargs BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsargs$*)) } }
INSERT AFTER .qjszmet;
SECTIONS { .qjsamet BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjsamet$*)) } }
INSERT AFTER .qjsargs;

/* Public ABI fusion follows every old code/control island. */
SECTIONS { .qjspub BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjspub$*)) } }
INSERT AFTER .qjsamet;
SECTIONS { .qjspumt BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjspumt$*)) } }
INSERT AFTER .qjspub;

/* Frame-publication experiment follows every inherited code/control island. */
SECTIONS { .qjspfrm BLOCK(__section_alignment__) : { *(.qjspfrm) } }
INSERT AFTER .qjspumt;
SECTIONS { .qjspfro BLOCK(__section_alignment__) : { *(.qjspfro) } }
INSERT AFTER .qjspfrm;
SECTIONS { .qjspfwr BLOCK(__section_alignment__) : { *(.qjspfwr) } }
INSERT AFTER .qjspfro;

/* Known-state kernels follow retained DC RX/RO/RW. */
SECTIONS { .qjsknown BLOCK(__section_alignment__) : { *(.qjsknown) } }
INSERT AFTER .qjspfwr;

/* Private VM C invoke follows all inherited code/control islands. */
SECTIONS { .qjsinv BLOCK(__section_alignment__) : { *(.qjsinv) } }
INSERT AFTER .qjsknown;
SECTIONS { .qjsimet BLOCK(__section_alignment__) : { *(.qjsimet) } }
INSERT AFTER .qjsinv;

/* Bounded native argument windows follow the retained positive-argc kernel. */
SECTIONS { .qjsargc BLOCK(__section_alignment__) : { *(.qjsargc) } }
INSERT AFTER .qjsimet;
SECTIONS { .qjsargm BLOCK(__section_alignment__) : { *(.qjsargm) } }
INSERT AFTER .qjsargc;

/* Prepared native-view entries follow every inherited C argument island. */
SECTIONS { .qjsbent BLOCK(__section_alignment__) : { *(.qjsbent) } }
INSERT AFTER .qjsargm;
SECTIONS { .qjsbenm BLOCK(__section_alignment__) : { *(.qjsbenm) } }
INSERT AFTER .qjsbent;

/* Synchronous iteration coverage follows every inherited native island. */
SECTIONS { .qjsiter BLOCK(__section_alignment__) : { *(.qjsiter) } }
INSERT AFTER .qjsbenm;

/* Guarded iterator steps and root-only exception route follow coverage. */
SECTIONS { .qjsitfa BLOCK(__section_alignment__) : { *(.qjsitfa) } }
INSERT AFTER .qjsiter;

/* C slow iterator bridge follows every retained iteration island. */
SECTIONS { .qjsitsl BLOCK(__section_alignment__) : { *(.qjsitsl) } }
INSERT AFTER .qjsitfa;

/* JS next call and done/value checkpoints follow all retained code/data. */
SECTIONS { .qjsitcp BLOCK(__section_alignment__) : {
    *(.qjsitcp)
    . = ALIGN(4);
    __qjsit_checkpoint_unwind_begin = .;
    *(SORT_BY_NAME(.qjsicfn$*))
    __qjsit_checkpoint_unwind_end = .;
} }
INSERT AFTER .qjsitsl;

/* Research literal structures follow the retained checkpoint code/data. */
SECTIONS { .qjslit BLOCK(__section_alignment__) : {
    *(.qjslit)
    . = ALIGN(4);
    __qjsit_literal_unwind_begin = .;
    *(SORT_BY_NAME(.qjslcfn$*))
    __qjsit_literal_unwind_end = .;
} } INSERT AFTER .qjsitcp;
SECTIONS { .qjslmet BLOCK(__section_alignment__) : { *(.qjslmet) } }
INSERT AFTER .qjslit;

/* Global-binding profiles follow all inherited literal code/data. */
SECTIONS { .qjsglob BLOCK(__section_alignment__) : {
    *(.qjsglob)
    . = ALIGN(4);
    __qjsgl_unwind_begin = .;
    *(SORT_BY_NAME(.qjsgcfn$*))
    __qjsgl_unwind_end = .;
    . = ALIGN(4);
    FILL(0)
    __qjsgl_directory_begin = .;
    . += __qjs_keep_legacy_unwind * (DEFINED(JS_FrameGlobalBindingGet) ?
        SIZEOF(.pdata) +
        (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
        (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
        (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
        (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) : 0);
    __qjsgl_directory_end = .;
} } INSERT AFTER .qjslmet;
SECTIONS { .qjsgmet BLOCK(__section_alignment__) : { *(.qjsgmet) } }
INSERT AFTER .qjsglob;

/* Primitive callee entries follow all inherited code/control islands. */
SECTIONS { .qjslcal BLOCK(__section_alignment__) : {
    *(.qjslcal) . = ALIGN(4); __qjsleaf_unwind_begin = .;
    *(SORT_BY_NAME(.qjslefn$*)) __qjsleaf_unwind_end = .;
} } INSERT AFTER .qjsgmet;
SECTIONS { .qjslcm BLOCK(__section_alignment__) : { *(.qjslcm) *(.qjslcm$zzforward) } }
INSERT AFTER .qjslcal;

/* A new builtin and its directory follow all inherited code and metadata. */
SECTIONS { .qjszre BLOCK(__section_alignment__) : {
    *(SORT_BY_NAME(.qjszre$*))
    . = ALIGN(4); __qjsregexp_unwind_begin = .;
    *(SORT_BY_NAME(.qjsrfn$*)) __qjsregexp_unwind_end = .;
    . = ALIGN(4); FILL(0) __qjsregexp_directory_begin = .;
    . += __qjs_keep_legacy_unwind * (DEFINED(JS_RegExpOwnedReplace) ? SIZEOF(.pdata) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin) : 0);
    __qjsregexp_directory_end = .;
} } INSERT AFTER .qjslcm;

/* Independent scalar undefined descriptor follows every inherited island. */
SECTIONS { .qjsundf BLOCK(__section_alignment__) : { *(.qjsundf) *(.qjsundf$zzbypass) } } INSERT AFTER .qjszre;
SECTIONS { .qjsundm BLOCK(__section_alignment__) : { *(.qjsundm) *(.qjsundm$zzbypass) } } INSERT AFTER .qjsundf;


/* Prepared callbacks own final RX/RW islands after every inherited code and
    metadata contribution. No old writable hint is pushed by callback code. */
SECTIONS { .qjscbck BLOCK(__section_alignment__) : {
    *(.qjscbck$A) *(.qjscbck$C)
} } INSERT AFTER .qjsundm;
SECTIONS { .qjscbmt BLOCK(__section_alignment__) : { *(.qjscbmt) *(.qjscbmt$zzjson) } }
INSERT AFTER .qjscbck;

/* Independently compiled JSON parser precedes the writer after every
    retained callback contribution. No padding/address selection is used. */
SECTIONS { .qjsjson BLOCK(__section_alignment__) : { *(.qjsjson$A) *(.qjsjson$B) *(.qjsjson$C) } } INSERT AFTER .qjscbmt;

/* JSON owns its compiler runtime-function records after both code parts.
    Its final directory follows all retained callback/code/control islands.
    Derived capacity is local to this new directory, so adding JSON helpers
    cannot grow the earlier global/regexp directory through SIZEOF(.pdata). */
SECTIONS { .qjsjfn BLOCK(__section_alignment__) : {
    __qjsjson_unwind_begin = .;
    *(.qjsjfn$A) *(.qjsjfn$B) *(.qjsjfn$C)
    __qjsjson_unwind_end = .;
    /* The actual compiler records give the carrier initialized readonly data;
        its derived directory uses that same mapped contribution. */
    . = ALIGN(4);
    __qjsjson_directory_begin = .;
    . += __qjs_keep_legacy_unwind * ((__qjsjson_unwind_end - __qjsjson_unwind_begin) ? SIZEOF(.pdata) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin) : 0);
    __qjsjson_directory_end = .;
} } INSERT AFTER .qjsjson;

/* Writable callbacks are independently emitted after inherited JSON metadata. */
SECTIONS { .qjscbwr BLOCK(__section_alignment__) : { *(.qjscbwr$A) *(.qjscbwr$C) } } INSERT AFTER .qjsjfn;
SECTIONS { .qjscbwm BLOCK(__section_alignment__) : { *(.qjscbwm) } } INSERT AFTER .qjscbwr;
SECTIONS { .qjscwfn BLOCK(__section_alignment__) : {
    *(.qjscwfn$0) __qjscwrite_native_begin = .;
    *(.qjscwfn$A) *(.qjscwfn$C) *(.qjscwfn$D) *(.qjscwfn$E) __qjscwrite_native_end = .;
    *(.qjscwfn$Z)
    LONG(__qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin))); LONG(1);
    . += __qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin));
} } INSERT AFTER .qjscbwm;

/* Writable JSON callbacks follow all inherited code/control/unwind. */
SECTIONS { .qjsjcwr BLOCK(__section_alignment__) : { *(.qjsjcwr$C) } } INSERT AFTER .qjscwfn;

/* Value-only reviver code follows the selected writable JSON island. */
SECTIONS { .qjsjcrv BLOCK(__section_alignment__) : { *(.qjsjcrv$C) } } INSERT AFTER .qjsjcwr;

/* Value reviver startup control follows all code, old control and unwind. */
SECTIONS { .qjsrvmd BLOCK(__section_alignment__) : { *(.qjsrvmd) } } INSERT AFTER .qjsjcrv;

/* Observable source revivers follow every selected value-only contribution. */
/* Native call-link cold growth follows the stable C VM group. */
SECTIONS { .qjssrc BLOCK(__section_alignment__) : { *(.qjssrc$C) *(.qjssrc$Z) } } INSERT AFTER .qjsrvmd;
SECTIONS { .qjssrm BLOCK(__section_alignment__) : { *(.qjssrm) } } INSERT AFTER .qjssrc;
SECTIONS { .qjssrf BLOCK(__section_alignment__) : {
    *(.qjssrf$0) __qjssource_native_begin = .;
    *(.qjssrf$C) __qjssource_native_end = .;
    *(.qjssrf$Z)
    LONG(__qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjssource_native_end - __qjssource_native_begin) +
    (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin))); LONG(1);
    FILL(0)
    . += __qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjssource_native_end - __qjssource_native_begin) +
    (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin));
    /* General native C scope code follows the complete unwind reservation. */
    *(.qjssrf$NCS)
} } INSERT AFTER .qjssrm;


/* Per-callsite metadata follows every inherited code/data/CFI contribution.
    Its native rows do not enter .pdata or resize earlier directory reserves. */
SECTIONS { .qjsmeta BLOCK(__section_alignment__) : {
    *(.qjsmeta$C) *(.qjsmeta$A)
} } INSERT AFTER .qjssrf;
SECTIONS { .qjsmfn BLOCK(__section_alignment__) : {
    LONG(0x43534a51); LONG(0x4e555f57); LONG(0x444e4957); LONG(0x2131765f);
    LONG(0); LONG(1); QUAD(0);
    __qjsmeta_native_begin = .;
    *(.qjsmfn$C) *(.qjsmfn$A)
    __qjsmeta_native_end = .;
    LONG(0x43534a51); LONG(0x4e455f57); LONG(0x31765f44); LONG(0x21212121);
    LONG(__qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjssource_native_end - __qjssource_native_begin) +
    (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin) + (__qjsmeta_native_end - __qjsmeta_native_begin))); LONG(1);
    . += __qjs_keep_legacy_unwind * (SIZEOF(.pdata) + (__qjssource_native_end - __qjssource_native_begin) +
    (__qjscwrite_native_end - __qjscwrite_native_begin) +
    (__qjsjson_unwind_end - __qjsjson_unwind_begin) +
    (__qjsit_checkpoint_unwind_end - __qjsit_checkpoint_unwind_begin) +
    (__qjsit_literal_unwind_end - __qjsit_literal_unwind_begin) +
    (__qjsgl_unwind_end - __qjsgl_unwind_begin) +
    (__qjsleaf_unwind_end - __qjsleaf_unwind_begin) +
    (__qjsregexp_unwind_end - __qjsregexp_unwind_begin) + (__qjsmeta_native_end - __qjsmeta_native_begin));
} } INSERT AFTER .qjsmeta;
SECTIONS { .qjsmmet BLOCK(__section_alignment__) : { *(.qjsmmet) } }
INSERT AFTER .qjsmfn;


/* Varargs semantic code and its readonly native directory follow every old
    output section. Explicit ownership prevents GNU orphan-section placement
    from inserting them ahead of core data. No preferred base/RVA is assigned. */
SECTIONS { .qjzzva BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzva$*)) } }
INSERT AFTER .qjsmmet;
SECTIONS { .qjzzvf BLOCK(__section_alignment__) : { *(.qjzzvf) } }
INSERT AFTER .qjzzva;

/* Diagnostic-only counters; production has no such input contribution. */
SECTIONS {
    .qjvsom BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjvsom$*)) }
    .qjzzlc BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzlc$*)) }
    .qjzzlm BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzlm$*)) }
    .qjzzlf BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzlf$*)) }
} INSERT AFTER .qjzzvf;

/* GNU direct prototype snapshot load, after complete retained length module. */
SECTIONS {
    .qjzzdc BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzdc$*)) }
    .qjzzdm BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzdm$*)) }
    .qjzzdf BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzdf$*)) }
} INSERT AFTER .qjzzlf;

/* Current-own-data integer hints follow the COMPLETE inherited prototype
    RX/RW/readonly directory. No orphan placement, fixed base or selected RVA. */
SECTIONS {
    .qjzzoc BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzoc$*)) }
    .qjzzom BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzom$*)) *(SORT_BY_NAME(.qjsem$*)) }
    .qjzzof BLOCK(__section_alignment__) : { *(SORT_BY_NAME(.qjzzof$*)) *(SORT_BY_NAME(.qjser$*)) }
} INSERT AFTER .qjzzdf;

/* Source-built VM refill helpers follow the retained contributions. Their
    compiler unwind records use ordinary .pdata, with no private directory. */
SECTIONS { .qjzzec BLOCK(__section_alignment__) : { *(.qjzzec) *(SORT_BY_NAME(.qjsex$*)) *(SORT_BY_NAME(.qjscmp$*)) } }
INSERT AFTER .qjzzof;
