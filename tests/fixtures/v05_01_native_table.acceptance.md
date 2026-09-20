# V0.5.1 ticket #24 acceptance fixture

This one-slide Author fixture is deliberately limited to the merged-table
vertical slice. It contains:

- one combined `rowspan="2" colspan="2"` anchor;
- one ordinary cell beneath the vertical merge;
- one horizontal `colspan="2"` region;
- one ordinary row that fixes the three logical column widths;
- anchor-owned rich text, solid fills, alignment, padding, and four borders.

The expected normalized regions are expressed in one-based logical coordinates:

```text
(1, 1, 2, 2)  combined anchor
(1, 3, 1, 1)  header
(2, 3, 1, 1)  vertical follower
(3, 1, 1, 2)  horizontal region
(3, 3, 1, 1)  ordinary cell
(4, 1, 1, 1)  ordinary cell
(4, 2, 1, 1)  ordinary cell
(4, 3, 1, 1)  ordinary cell
```

Acceptance compares this normalized topology and the logical row/column
dimensions. It does not inspect OfficeCLI/OOXML continuation-cell `hMerge` or
`vMerge` serialization.
