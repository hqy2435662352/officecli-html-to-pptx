# 03 — Compile one HTML table to a native PowerPoint table

**What to build:** Extend the complete Author HTML compiler path so the 9×5 table on Algeria slide 7 is measured as a table, lowered as one PPT Object IR table, and rendered by OfficeCLI as one native PowerPoint table with editable cells.

**Blocked by:** 01 — Compile one Author HTML slide to native shapes and text.

**Status:** complete

- [x] The slide 7 HTML table produces exactly one native PowerPoint table.
- [x] The native table has 9 rows, 5 columns, and 45 cells.
- [x] The table is not represented by rectangle/textbox pairs for individual cells.
- [x] The table's overall x, y, width, and height are within 1pt of the measured source.
- [x] Individual column widths differ by no more than 0.5pt from the normalized source manifest.
- [x] Individual row heights differ by no more than 0.5pt from the normalized source manifest.
- [x] Cell text matches the Author HTML by Unicode code point.
- [x] Supported cell fill, font family, font size, bold, italic, color, horizontal alignment, vertical alignment, padding, and borders are preserved.
- [x] The table and every cell carry stable source identity in the normalized manifest.
- [x] A non-unit `rowspan` or `colspan` fails as unsupported and never falls back to fake table shapes.
- [x] OfficeCLI table query returns one 9×5 native table.
- [x] OfficeCLI validation passes through the public compiler seam.
