---
status: accepted
---

# Use normalized topology and canonical borders for merged native tables

Contract 1.1 supports legal rectangular, non-overlapping Author `rowspan` and
`colspan` regions as native PowerPoint table merges. Acceptance compares each
region as `(anchorRow, anchorColumn, rowSpan, columnSpan)`, logical row heights
and column widths, and four visible outer borders; it does not bind the Contract
to OfficeCLI or OOXML hMerge/vMerge continuation serialization. The anchor owns
the region's content, formatting, and normalized final top/right/bottom/left
borders, while internal merged borders are absent. This is the public canonical
border model, not an attempt to reproduce the full browser collapsed-border
conflict algorithm.
