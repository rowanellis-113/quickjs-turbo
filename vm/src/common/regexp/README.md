# Regular expression implementation

The public sources remain pinned to QuickJS-NG 0.17.0. The owned native worker
and portable source overlay use `exec.inc`; the generator checks the pinned
entry body before substitution. Native builtin identity checks recognize that
worker, while the C overlay retains the original static function identity.

`exec.inc` preserves receiver and string conversion, lastIndex, named groups,
indices, properties and exception cleanup. Up to 16 capture entries, including
the full match, use a 32-pointer automatic buffer; larger matches use the
existing allocator. Result storage is reserved once and filled directly. The
array's initialized count advances after each owned value, before the next
allocating operation, so GC and partial-failure cleanup see an exact prefix.
No GC deferral, object reuse or new runtime layout is required.

`flag-atoms.inc` borrows existing atoms only during callback-free live
descriptor checks. It creates and retains nothing and caches no runtime atom
IDs. The eight hashes are the pinned hash_string8 results. Generator hash
checks and C assertions fail closed when that algorithm, type or mask changes.
Observable getters, overrides, realm checks and reentry still use the original
fallback. The ownership regression compares atom counts after context disposal
using the public API, alongside exec fault injection, GC and interrupt reentry.

The shared VM uses computed labels on qualified native GNU builds. Other compilers, other
platforms, diagnostic switch builds and dump builds use the same switch body.
Character width, decoding, captures, backtracking, polling and errors remain
shared. No assembly or public ABI changes are involved.

The changes follow LLInt's pre-sized result/direct initialization pattern,
adapted to QuickJS ownership rather than copying its GC representation.
Performance and full compatibility evidence belongs in the external product
baseline archive; experimental variants and benchmark output stay outside this
source tree.
