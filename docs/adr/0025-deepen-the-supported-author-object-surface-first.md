---
status: accepted
---

# Deepen the supported Author object surface first

V0.2 capability development will first improve the fidelity and practical
coverage of the existing textbox, shape, picture, table, and slide surface.
Priorities include richer native text and paragraph formatting, common shape
geometry and styling, reliable picture and SVG handling, native table merges
and formatting, and slide backgrounds. Unsupported visible content will keep
failing explicitly rather than disappearing or flattening silently.

V0.2 will defer broad new PowerPoint object families such as masters and
layouts, groups, bound connectors, native charts, SmartArt, animations, audio,
and video. This keeps development centered on making the supported Author HTML
path useful and faithful before expanding the PPT Object IR into structurally
different domains.
