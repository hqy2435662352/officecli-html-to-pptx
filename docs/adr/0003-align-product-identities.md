---
status: accepted
---

# Align the repository, distribution, namespace, and command

V0.2 will use `officecli-html-to-pptx` for the repository, Python distribution,
and primary command, and `officecli_html_to_pptx` for the Python import
namespace. It will not retain `html-to-pptx` or `html_to_pptx` compatibility
entry points. Making the breaking identity change before the independent
product acquires external compatibility obligations avoids carrying two names
through documentation, diagnostics, Skills, Plugins, and future releases.
