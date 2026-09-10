# Author HTML

Read this reference only while creating, reconstructing, or materially
repairing the Candidate HTML. It is practical authoring guidance; the
installed Author Contract and generated capability data remain authoritative
for exact supported properties, object kinds, and versions.

## Workbench target

Create a browsable slide workbench with one clear slide boundary per intended
slide. Keep visible content as independent authored DOM objects so the Core
Product can lower it to editable text, shapes, pictures, and tables. Keep
source and reconstructed work in a new `.author.html` file; the user's
original HTML and reference files remain unchanged.

Treat the supplied content brief as content and composition context, not as a
compiler input. Treat each supplied reference image as appearance context. If
references are supplied, inspect every image before authoring and preserve the
meaningful visible details that the brief or reference establishes.

## Contract-first authoring

1. Start from the installed Contract and `check --json`. Read
   `capabilities --json` when a choice depends on whether a CSS property,
   object kind, or resource form is supported. Do not copy a capability matrix
   into this reference; those commands are the source of truth.
2. Author with native text, shapes, pictures, and tables inside that reported
   surface. Keep measurement-only or preview-only concerns separate from
   authored content so they cannot silently become visible output.
3. Keep every intended visible item represented. At an unsupported boundary,
   preserve the source context and emit an explicit diagnostic or route the
   item to an authorized product-development decision. A missing object is not
   a successful approximation.
4. Use deterministic, locally available inputs supported by the Contract. Keep
   visible external resources out of the normal workbench unless the Contract
   explicitly accepts that form.

After authoring, inspect the workbench at enough scale to catch missing slides,
obvious overflow, unreadable text, missing images, unintended overlap, and
Contract-visible unsupported content. Then run `check --json`; fix the exact
diagnostics and check again. Use the first successful Build's Comparison
Images for Build-Driven Visual Discovery instead of delaying the first build
for speculative polish.

**Authoring completion criterion:** the separate `.author.html` is browsable,
contains all intended slides and visible objects, and the exact file passes the
installed Author Contract with no unresolved blocking diagnostics.
