# 0001: Sidecar-first lyrics, never embedded tags

Status: accepted

## Context
Players read `.lrc` files next to tracks, and rewriting tags risks corrupting libraries and fighting other tag editors.

## Decision
Lyrics are written only to same-directory `.lrc` sidecars, atomically (temp file, fsync, replace, verify). Embedded lyrics are detected and respected but never written or modified. Sidecar text is stored without altering characters (no Unicode compatibility folding); a separate comparison form is used only for hashing.

## Consequences
Users can edit or delete sidecars freely; Versarr records provenance so it can preserve manual edits and deletions. Embedded-only lyrics are left alone.
