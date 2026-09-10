---
status: accepted
---

# Use two visual finding levels and three outcomes

V0.2 Visual Review will classify findings only as `major` or `minor` and will
produce only `PASS`, `PASS_WITH_FINDINGS`, or `REVISION_REQUIRED`. Any major
finding triggers a Revision Loop; minor findings are reported but finish the
workflow successfully. The product will not introduce numeric similarity
scores, confidence values, pixel thresholds, or additional severity levels,
because delivery impact rather than rendering noise is the decision boundary.
