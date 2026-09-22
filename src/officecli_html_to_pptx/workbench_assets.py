"""Embedded, dependency-free assets for the source-authoritative Workbench."""

from __future__ import annotations


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OfficeCLI Author HTML Workbench</title>
  <style>
    :root { color-scheme: light dark; font: 14px/1.45 system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; background: #f4f6f8; color: #17202a; }
    header { display: flex; align-items: center; gap: 16px; padding: 12px 18px;
      background: #17202a; color: #fff; }
    header h1 { font-size: 16px; margin: 0; flex: 1; }
    #state { border-radius: 999px; padding: 3px 10px; background: #496273; font-size: 12px; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 14px;
      padding: 14px; height: calc(100vh - 67px); box-sizing: border-box; }
    .panel { min-height: 0; background: #fff; border: 1px solid #d5dce2; border-radius: 8px;
      box-shadow: 0 2px 10px #17202a12; }
    #editor { width: 100%; height: 100%; resize: none; box-sizing: border-box; border: 0;
      border-radius: 8px; padding: 16px; font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
      color: inherit; background: transparent; }
    aside { padding: 14px; overflow: auto; }
    button { border: 1px solid #93a4b3; border-radius: 5px; padding: 7px 10px; margin: 0 5px 8px 0;
      background: #fff; color: inherit; cursor: pointer; }
    button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
    button:disabled { opacity: .5; cursor: wait; }
    dl { margin: 12px 0; }
    dt { color: #5d6d7e; font-size: 11px; text-transform: uppercase; margin-top: 10px; }
    dd { margin: 2px 0; word-break: break-word; }
    #message { white-space: pre-wrap; color: #9b1c1c; }
    @media (prefers-color-scheme: dark) {
      body { background: #101418; color: #e6edf3; }
      .panel, button { background: #182027; border-color: #3a4b58; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Author HTML Workbench</h1>
    <span id="state">Loading</span>
    <button id="save" class="primary" type="button">Save</button>
    <button id="recover" type="button" hidden>Recover draft</button>
  </header>
  <main>
    <section class="panel"><textarea id="editor" spellcheck="false" aria-label="Author HTML source"></textarea></section>
    <aside class="panel">
      <p>Edit the real UTF-8 Author HTML source. Preview, Contract Check, and Build belong to later Workbench slices.</p>
      <dl>
        <dt>Source</dt><dd id="source"></dd>
        <dt>Saved SHA-256</dt><dd id="source-sha"></dd>
        <dt>Draft SHA-256</dt><dd id="draft-sha"></dd>
        <dt>Recovery</dt><dd id="recovery"></dd>
      </dl>
      <p id="message" role="status"></p>
    </aside>
  </main>
  <script>
    (() => {
      const token = new URL(window.location.href).searchParams.get("token") || "";
      const editor = document.getElementById("editor");
      const state = document.getElementById("state");
      const message = document.getElementById("message");
      const save = document.getElementById("save");
      const recover = document.getElementById("recover");
      let snapshot = null;
      let sessionId = "";
      let draftTimer = null;

      async function api(path, options = {}) {
        const headers = Object.assign({"Accept": "application/json", "X-Workbench-Token": token}, options.headers || {});
        if (sessionId) headers["X-Workbench-Session"] = sessionId;
        if (options.body !== undefined) headers["Content-Type"] = "application/json; charset=utf-8";
        const response = await fetch(path, Object.assign({}, options, {headers}));
        const body = await response.json();
        if (!response.ok) {
          const error = new Error((body.error && body.error.message) || "Workbench request failed");
          error.body = body;
          throw error;
        }
        return body;
      }

      function paint(body) {
        if (body.session_id) sessionId = body.session_id;
        snapshot = body.document;
        if (document.activeElement !== editor || editor.value === "") editor.value = snapshot.text;
        state.textContent = snapshot.state;
        document.getElementById("source").textContent = snapshot.source_path;
        document.getElementById("source-sha").textContent = snapshot.source_sha256;
        document.getElementById("draft-sha").textContent = snapshot.draft_sha256;
        const available = Boolean(body.recovery && body.recovery.available);
        document.getElementById("recovery").textContent = available ? "Available (not applied)" : "None";
        recover.hidden = !available;
        if (snapshot.state !== "ERROR") message.textContent = "";
      }

      function showError(error) {
        const body = error.body;
        if (body && body.document) paint(body);
        message.textContent = error.message;
      }

      async function load() {
        try { paint(await api("/api/session")); }
        catch (error) { showError(error); state.textContent = "ERROR"; }
      }

      editor.addEventListener("input", () => {
        state.textContent = "DIRTY";
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(async () => {
          try { paint(await api("/api/draft", {method: "POST", body: JSON.stringify({text: editor.value})})); }
          catch (error) { showError(error); }
        }, 180);
      });

      save.addEventListener("click", async () => {
        if (!snapshot) return;
        state.textContent = "SAVING";
        save.disabled = true;
        try {
          paint(await api("/api/save", {method: "POST", body: JSON.stringify({expected_sha256: snapshot.source_sha256, text: editor.value})}));
        } catch (error) { showError(error); }
        finally { save.disabled = false; }
      });

      recover.addEventListener("click", async () => {
        try { paint(await api("/api/recovery/restore", {method: "POST"})); }
        catch (error) { showError(error); }
      });

      load();
    })();
  </script>
</body>
</html>
"""


__all__ = ["INDEX_HTML"]
