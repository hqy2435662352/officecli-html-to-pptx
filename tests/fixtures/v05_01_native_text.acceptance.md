# V05-01-01 native text structure acceptance checklist

This fixture is the focused Contract 1.1 text slice for ticket #23. It is
intentionally independent of the merged-table and native-shape tickets.

- `p` boundaries remain native paragraphs in authored order.
- `<br>` remains an intra-paragraph native hard break (`a:br`) and does not
  increase the native paragraph count.
- The leading, intervening, consecutive, and trailing empty paragraphs remain
  present with their exact cardinality.
- `visualLines` is retained only as measurement/evidence; changing the measured
  width cannot change the paragraph or hard-break structure.
- The public run matrix is limited to font family, size, weight, style, solid
  color, and single/none underline.
- The public paragraph matrix is limited to authored boundaries, hard breaks,
  empty paragraphs, alignment, direction, line-height, and supported margins;
  standalone block margins stay in the measured bounds, while table-cell
  paragraph margins are the native `spaceBefore`/`spaceAfter` projection.
- Microsoft YaHei is authored through the single public `font-family` property
  and is checked in OfficeCLI readback plus the Gate 3 visual comparison.
