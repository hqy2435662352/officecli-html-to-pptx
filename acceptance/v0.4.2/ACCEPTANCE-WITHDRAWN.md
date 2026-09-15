# V0.4.2 acceptance — WITHDRAWN

**This bundle's `PASS_WITH_FINDINGS` verdict is withdrawn. Do not treat it as
acceptance evidence.**

## Why

An independent spec-and-standards review rejected the claim on matters of
substance, not on the implementation failing to run. The review found, and the
primary agent independently confirmed on the code:

**Spec axis**

1. **The three-deck corpus was never run.** #18 requires "eight real selected
   pages from three source decks". The run projects eight pages of *one* deck.
   The multi-deck selected-page seam is therefore not integration-verified on
   real decks at all.
2. **Private material is in the public repository and PR history.** The private
   source deck's full SHA-256 appears in this report and in `corpus-manifest.json`
   (ten occurrences), and this report contains a machine-specific absolute path.
   The original spec says private filenames, paths, hashes, page content and
   screenshots do not enter the public repository or tracker. A later deletion
   commit cannot remove them from the branch's history.
3. **"Supported style declarations read back independently" is not implemented.**
   `source_delta_gate.py` builds `TextReadback.style_declarations` from the
   *generated HTML* (`_style_declarations(html_text, item.html_id)`), not from
   the rebuilt PPTX, and `TextReadback.matched` compares text only. Changing a
   rebuilt object's font, colour, weight or paragraph spacing while leaving its
   characters intact would still pass.
4. **Text comparison strips every whitespace character** (`compact_text`), so
   `A B` equals `AB` and `line one\nline two` equals `line oneline two`. The
   hard break and list marker defects were repaired at the emitter; this gate
   cannot prove they will not regress, and it did not catch them.
5. **Native table expectations come from the projection's own HTML.** The
   "independent" table check compares the emitted HTML table against the deck
   rebuilt from that same HTML, so a dropped row or cell in the projection is
   faithfully reproduced by the compiler and reported as a pass.
6. **Proxy proof reporting contradicts itself.** This report's summary says
   `proxy isolation proofs passed | 0` where 41 proofs exist and 41 are recorded
   as passed. The generator reads a top-level array the gate does not emit.
7. **Synthetic probe B does not meet its own declared surface.** Nested list items
   keep their indent but not their native `lvl`; the theme-resolved body renders
   in a different colour and is classified `canonical-editable` rather than
   `base-only-semantic`.

**Standards axis**

8. **The hidden seam became a second public API.** ADR 0030 exports exactly one
   function and keeps reader DTOs and classification rules private. The package
   root now exports a second function plus a family of DTOs, exceptions,
   disposition constants and comparison rules.
9. **The Author Contract changed while still claiming to be unchanged.**
   `CONTRACT_VERSION` remains `"1.0"` but `list-style-type` was added to the
   accepted declaration set.
10. **Non-overwriting publication has a TOCTOU race.** A pre-flight `exists()`
    is followed later by `Path.replace()`, so two concurrent runs can both pass
    the check and the later one overwrites the earlier; the failure path then
    unlinks destinations it cannot prove it created.
11. **The tracked artifact manifest breaks a clean checkout.** It lists 130
    artifacts of which 128 are gitignored; the test fails on any machine that has
    OfficeCLI and a clean checkout. CI is green only because the module is
    skipped where OfficeCLI is absent.
12. **The gate uses a non-retrying OfficeCLI helper** while the seam retries, so
    the gate can fail non-deterministically under load.
13. **Two published reports disagree.** This bundle's acceptance report still
    states that a hard break is not rebuilt as a break and that a source list
    marker is not reconstructed, while `GATE3-REVIEW.md` records both as fixed.
    Only the review was updated after the repair, so the authoritative report was
    never regenerated.

## Current disposition

- **Verdict: rejected.** PR #19 stays open and unmerged; #15, #17 and #18 stay
  open; #16's implementation direction is accepted subject to integration
  acceptance.
- The implementation itself is not rejected: selected-page projection, the
  object disposition ledger, native `ellipse` / `rightArrow`, list markers, hard
  breaks, native table structure readback and source immutability all have real
  substance behind them.

## What the acceptance claim needs before it can be restated

1. Sanitise the public branch of private hashes, absolute paths and business
   page content, including branch history.
2. Run the frozen corpus as three real source decks through the same
   multi-deck selected-page seam.
3. Make the #17 evidence genuinely independent: styles read back from the
   rebuilt PPTX, native table expectations read from the source PPTX, and text
   compared with meaningful whitespace and paragraph structure preserved.
4. Add gate negative tests for font, colour, weight, paragraph spacing, space,
   hard break, a dropped source table cell, and a blank proxy target.
5. Fix the remaining page defects: page 1's source text effect that paints
   invisibly, page 6's paragraph spacing and painted layout, page 10's native
   nesting level and theme-token colour.
6. Fix the publication race and the missing retry.
7. Regenerate one authoritative report and one review bundle, bound to the final
   commit and manifest, with after-render hashes that match the bundle they
   describe.
8. Re-run the manifest test and the three-deck acceptance on a clean checkout
   with OfficeCLI, then repeat the independent Gate 3.

## Note on the Gate 3 review in this directory

`GATE3-REVIEW.md` remains accurate about the seven defects it found and their
repair — that work stands. It is not, however, evidence of acceptance: it
reviewed a corpus that does not satisfy #18's corpus criterion, and its
"all text restored" and "faithful within 1.5pt" findings on pages 1 and 6 are
overtaken by defects 3, 4 and 5 above, which the review did not examine.
