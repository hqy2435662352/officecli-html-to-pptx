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
    #diagnostics { margin-top: 16px; }
    .diagnostic { border-top: 1px solid #d5dce2; padding: 8px 0; }
    .diagnostic code { font-weight: 600; }
    .muted { color: #5d6d7e; }
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
    <button id="check" type="button">Check</button>
    <button id="build" class="primary" type="button" disabled>Build Revision</button>
    <button id="save" class="primary" type="button">Save</button>
    <button id="recover" type="button" hidden>Recover draft</button>
  </header>
  <main>
    <section class="panel"><textarea id="editor" spellcheck="false" aria-label="Author HTML source"></textarea></section>
    <aside class="panel">
      <p>Edit the real UTF-8 Author HTML source. Preview is non-authoritative; Check and Build use the saved source/hash gates.</p>
      <dl>
        <dt>Source</dt><dd id="source"></dd>
        <dt>Saved SHA-256</dt><dd id="source-sha"></dd>
        <dt>Draft SHA-256</dt><dd id="draft-sha"></dd>
        <dt>Candidate / Author</dt><dd id="author-status"></dd>
        <dt>Contract</dt><dd id="contract-status"></dd>
        <dt>Build Revision</dt><dd id="build-status"></dd>
        <dt>Output root</dt><dd id="output-root"></dd>
        <dt>Recovery</dt><dd id="recovery"></dd>
      </dl>
      <section id="diagnostics" aria-live="polite"></section>
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
      const check = document.getElementById("check");
      const build = document.getElementById("build");
      const recover = document.getElementById("recover");
      const diagnostics = document.getElementById("diagnostics");
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
        document.getElementById("author-status").textContent = snapshot.author_status || "CANDIDATE";
        document.getElementById("contract-status").textContent = snapshot.contract_status || "UNKNOWN";
        document.getElementById("build-status").textContent = (snapshot.build && snapshot.build.status) || "IDLE";
        document.getElementById("output-root").textContent = body.output_root || snapshot.output_root || "";
        const available = Boolean(body.recovery && body.recovery.available);
        document.getElementById("recovery").textContent = available ? "Available (not applied)" : "None";
        recover.hidden = !available;
        const checkRecord = body.check || snapshot.contract_check || {};
        const buildItems = body.build && body.build.diagnostics;
        const items = (buildItems && buildItems.length) ? buildItems : (checkRecord.diagnostics || []);
        diagnostics.textContent = "";
        if (!items.length) {
          const empty = document.createElement("p");
          empty.className = "muted";
          empty.textContent = "No Contract diagnostics.";
          diagnostics.appendChild(empty);
        } else {
          items.forEach((item) => {
            const row = document.createElement("div");
            row.className = "diagnostic";
            const title = document.createElement("code");
            title.textContent = `[${item.code}] ${item.severity} · ${item.blocking ? "BLOCK" : "advisory"}`;
            row.appendChild(title);
            const text = document.createElement("div");
            text.textContent = item.message || "";
            row.appendChild(text);
            if (item.source_object) {
              const source = document.createElement("div");
              source.className = "muted";
              source.textContent = `source: ${item.source_object} · navigation: unmapped`;
              row.appendChild(source);
            }
            diagnostics.appendChild(row);
          });
        }
        build.disabled = !(
          snapshot.author_status === "AUTHOR" &&
          snapshot.contract_status === "PASS" &&
          snapshot.state !== "DIRTY" &&
          snapshot.state !== "CONFLICT" &&
          snapshot.build && snapshot.build.status !== "BUILDING"
        );
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
        build.disabled = true;
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(async () => {
          try { paint(await api("/api/draft", {method: "POST", body: JSON.stringify({text: editor.value})})); }
          catch (error) { showError(error); }
        }, 180);
      });

      check.addEventListener("click", async () => {
        check.disabled = true;
        try { paint(await api("/api/check", {method: "POST", body: JSON.stringify({text: editor.value})})); }
        catch (error) { showError(error); }
        finally { check.disabled = false; }
      });

      build.addEventListener("click", async () => {
        build.disabled = true;
        try { paint(await api("/api/build", {method: "POST", body: JSON.stringify({})})); }
        catch (error) { showError(error); }
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
