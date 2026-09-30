# Known issues

Small defects with a known shape, each fixed on its own. A section says what goes wrong, why when it
is known, and the fix. A fixed issue is deleted from here; a design change it needed goes into the
feature's document.

## §2 · LexiBeat's default seed does not survive JSON

Given no seed, the generator uses `secrets.randbits(64)`, which cannot round-trip through JSON into a
browser. 2^53 does everything 2^64 does, the seed being a replay token rather than a key. Acervo is
unaffected, since it mints the seed itself. **Fixed in the LexiBeat repository**, at its next release,
and re-pinned here.
