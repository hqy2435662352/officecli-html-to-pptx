# officecli-html-to-pptx 0.6.1

Product 0.6.1 adds the source-authoritative Author HTML Workbench while
retaining Author Contract 1.3, the OfficeCLI `>=1.0.151` floor, native object
semantics, explicit localized fallback, and the existing Evidence/Gate 3
delivery path.

## Public authority

- Product version: `0.6.1`.
- Author Contract: `1.3`.
- Minimum OfficeCLI: `1.0.151` (`>=1.0.151`).
- Public commands: `capabilities`, `doctor`, `check`, `build`, `finalize`, and
  `workbench`.
- The Capability Manifest publishes the Workbench source-authority rule,
  exact-hash build prerequisites, loopback binding, token policy, and the fact
  that Preview is non-authoritative.

The Python public API remains the compiler API. `workbench` is the supported
interactive command; the session/document module is an internal seam so the
product does not create a second Python-level workflow contract.

## Workbench lifecycle

`officecli-html-to-pptx workbench <input.html>` resolves one real UTF-8 source,
starts a loopback-only server, emits a startup envelope or concise URL, and
serves a fully embedded editor and isolated 16:9 Preview. The wheel has no CDN,
runtime npm installation, remote font, or public-network requirement for
editing.

The editor operates on an in-memory draft. Preview, thumbnails, source maps,
diagnostics, and recovery records are derived and non-authoritative. Save is an
atomic whole-document replacement guarded by the loaded source SHA-256. A disk
hash mismatch returns `CONFLICT` and preserves the draft; Save may persist a
Contract-invalid Candidate. Build Revision never implicitly saves and is
allowed only when:

1. the draft SHA equals the current disk SHA;
2. no external modification conflict exists; and
3. Contract Check returned `PASS` for that exact saved SHA.

Build Revision allocates a fresh session-owned target and calls the ordinary
`build_author_html` path. It therefore produces the normal PPTX/Evidence Pair,
independent readback, validate/issues evidence, Comparison Images, Gate 3
review, and finalize outcome. Edits made while a build runs do not rebind the
initiating artifact; the Workbench marks that result stale.

## Tracked acceptance

`tests/fixtures/v06_01_workbench_corpus.html` is a four-slide corpus covering
CJK text, inline CSS, deterministic data images, native text/table/shape/chart
objects, and one explicit localized fallback. Its chart Preview is drawn by an
inline authoring projector that reads the same inert JSON spec used by the
native chart compiler; no second chart data model is introduced. The associated
acceptance notes and separately tracked conflict/recovery/security scenarios are
part of the release integration surface. Product 0.5.3's four-slide localized corpus,
Product 0.5.2's chart corpus, Product 0.5.1's native corpus, and the V0.4
projection corpus remain regression assets; they do not become new 0.6.1
capability claims.

The installed Windows acceptance sequence is:

```text
workbench startup -> edit -> Preview/navigation/source selection -> draft Check
-> conflict-safe Save -> exact-hash Check -> Build Revision -> independent
readback -> validate/issues -> slide-by-slide Gate 3 -> finalize
```

The release does not add property panels, direct canvas editing, a public patch
schema, remote collaboration, existing-PPTX editing, or editor-specific PPTX
export.
