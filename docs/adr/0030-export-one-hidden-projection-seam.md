---
status: accepted
---

# Export one hidden projection seam for the V0.4.1 probe

The V0.4.1 probe needs a caller to go from an existing PPTX to Canonical Author
HTML without inspecting source, but that path must not become a product
capability: no public command, no package-version change, no new `capabilities`
entry. So exactly one function is exported —
`project_pptx_to_author_html(source_pptx, source_slide_numbers, output_html, proxy_dir=...)`
— and it stays out of `PUBLIC_COMMANDS` and out of the capability manifest.
Reachable by the agent running the probe and by tests; invisible to the supported
command surface.

Because that is the only entry point, the reader stays private: the OfficeCLI
command shapes, the object-capture DTOs, the classification rules and the
emitter are all implementation a caller never names, so they can be reworked
without a compatibility promise. And an OfficeHTML export cannot become a hidden
prerequisite, because there is no parameter through which one could be passed and
no profile in which one could be read.

What counts as a locked visual proxy belongs to this decision too, because it is
the part a reviewer is most likely to misread. A proxy is a render of **one
object alone**: a fresh deck holding only a reconstruction of that object,
cropped to its rectangle. Two cheaper implementations are rejected. Cropping the
composited slide captures any sibling painted inside the rectangle. Culling the
slide's siblings from a copy is subtler and still wrong: the copy renders the
slide's layout and master, so a layout graphic inside the rectangle is baked in
just the same. A representation carrying another object's paint is not
object-local whatever its rectangle is, and when isolation is impossible the
object is classified `unsupported` with a reason rather than represented by a
crop.
