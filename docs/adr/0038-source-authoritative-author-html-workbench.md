---
status: accepted
---

# Integrate a source-authoritative Author HTML Workbench in Product 0.6.1

Product 0.6.1 adds the public `workbench` command as an authoring entry point
for one real Candidate or Author HTML file. It is an editor for source HTML,
not an existing-PPTX editor and not a second compiler model.

## Decision

- The resolved UTF-8 Author HTML file is the only compiler source of truth.
  Draft text, Preview DOM, thumbnails, source maps, diagnostics, recovery data,
  and editor state are derived products.
- The Workbench server binds to loopback only and owns one source path, one
  authorized local asset root, one session token, one output root, and one
  lifecycle. Mutations require both the unguessable token and the current
  same-session identifier.
- Save is an internal whole-document Source Patch guarded by the session's
  expected source SHA-256. It uses a same-directory temporary UTF-8 write and
  atomic replacement. A disk hash mismatch returns `CONFLICT`, leaves external
  bytes unchanged, and preserves the draft. A saved Candidate may still be
  Contract-invalid.
- Draft Check reuses the existing text-based Contract checker. Its result is
  bound to the exact draft SHA and cannot authorize a different saved revision.
- Build Revision is enabled only when the draft SHA equals the disk SHA, no
  external conflict exists, and Contract PASS is recorded for that exact saved
  SHA. It calls the existing `build_author_html` operation and preserves the
  normal non-overwriting Artifact Pair, independent readback, validation/issues,
  Evidence, Gate 3, and finalize semantics.
- Preview is isolated, 16:9, and non-authoritative. Workbench-only markers and
  scripts are injected in memory and never enter Save text, Contract input,
  Build input, hashes, or Evidence. Remote resources, traversal, executable
  local resources, and top-window navigation are blocked.
- The installed wheel embeds the complete editor assets. The UI has no CDN,
  runtime npm installation, remote font, or public network dependency. The
  public Python API remains the compiler API; `workbench` is the supported
  interactive Product Command and its session module stays an implementation
  boundary.

## Acceptance boundary

Ticket #44 tracks a focused multi-slide corpus covering CJK text, inline CSS,
deterministic images, native text/table/shape/chart objects, and localized
fallback. Conflict/recovery and security scenarios are tracked separately.
The installed Windows path must show startup, edit, Preview/navigation/source
selection, draft Check, conflict-safe Save, exact-hash Check, Build Revision,
independent readback, validation/issues, slide-by-slide Gate 3, and finalize.

This decision does not add property forms, canvas drag/drop editing, public
Source Patch JSON, remote/LAN collaboration, existing-PPTX editing, or an
editor-specific exporter. Missing owner behavior returns to #41 (session/Save),
#43 (Preview/source navigation), or #42 (Contract/Build) instead of being
implemented by the release integration ticket.
