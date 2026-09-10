---
status: accepted
---

# Keep product development behind explicit user authorization

`build-a-pptx-with-html` will contain a normally hidden Development Path that
may modify the Author Contract or product source only after explicit user
authorization. It will not be a public CLI command or a second Skill, and a
failed Contract check will never activate it automatically. Changes must model
a general capability, add public-seam regression coverage, and produce an
Experimental Build identified by source revision and dirty state; successful
experimental evidence does not become a formal product-support claim until a
later reviewed release.
