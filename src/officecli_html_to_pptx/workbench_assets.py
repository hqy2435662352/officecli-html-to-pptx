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
    header { display: flex; align-items: center; gap: 12px; padding: 12px 18px;
      background: #17202a; color: #fff; }
    header h1 { font-size: 16px; margin: 0; flex: 1; }
    #state { border-radius: 999px; padding: 3px 10px; background: #496273; font-size: 12px; }
    main { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(360px, 1.5fr) 220px; gap: 14px;
      padding: 14px; height: calc(100vh - 67px); box-sizing: border-box; }
    .panel { min-height: 0; background: #fff; border: 1px solid #d5dce2; border-radius: 8px;
      box-shadow: 0 2px 10px #17202a12; }
    #editor { width: 100%; height: 100%; resize: none; box-sizing: border-box; border: 0;
      border-radius: 8px; padding: 16px; font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
      color: inherit; background: transparent; }
    aside { padding: 14px; overflow: auto; }
    #preview-panel { display: flex; flex-direction: column; padding: 12px; min-width: 0; }
    #preview-status { align-self: flex-start; border-radius: 999px; padding: 3px 10px;
      background: #496273; color: #fff; font-size: 12px; margin-bottom: 10px; }
    #preview-shell { width: 100%; aspect-ratio: 16 / 9; background: #111820; border-radius: 6px;
      overflow: hidden; position: relative; }
    #preview-frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
    #slide-rail { display: flex; gap: 8px; overflow-x: auto; padding: 10px 0 2px; min-height: 78px; }
    .slide-thumbnail { display: flex; flex-direction: column; flex: 0 0 112px; gap: 3px; }
    .slide-thumbnail button { margin: 0; padding: 3px; width: 112px; height: 70px; overflow: hidden; }
    .slide-thumbnail button.current { outline: 2px solid #2563eb; }
    .slide-thumbnail iframe { display: block; width: 100%; height: 100%; border: 0; pointer-events: none;
      transform-origin: top left; }
    .slide-thumbnail .slide-label { font-size: 11px; text-align: center; }
    #selection-status { white-space: pre-wrap; color: #155e75; min-height: 2em; }
    #preview-error { white-space: pre-wrap; color: #9b1c1c; }
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
    @media (max-width: 1100px) {
      main { grid-template-columns: minmax(240px, 1fr) minmax(300px, 1.2fr); }
      aside { grid-column: 1 / -1; max-height: 170px; }
    }
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
    <span id="preview-status" data-status="IDLE">Preview IDLE</span>
    <button id="refresh-preview" type="button">Refresh Preview</button>
    <button id="save" class="primary" type="button">Save</button>
    <button id="recover" type="button" hidden>Recover draft</button>
  </header>
  <main>
    <section class="panel"><textarea id="editor" spellcheck="false" aria-label="Author HTML source"></textarea></section>
    <section id="preview-panel" class="panel" aria-label="Live 16:9 slide Preview">
      <div id="preview-shell"><iframe id="preview-frame" title="Live slide Preview" sandbox="allow-scripts"
        referrerpolicy="no-referrer"></iframe></div>
      <nav id="slide-rail" aria-label="Slides"></nav>
      <p id="preview-error" role="status"></p>
      <p id="selection-status" data-mapping="">Click a supported Preview object to select its source.</p>
    </section>
    <aside class="panel">
      <p>Edit the real UTF-8 Author HTML source. Preview is isolated and non-authoritative; Check and Build use the saved source/hash gates.</p>
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
      const refreshPreviewButton = document.getElementById("refresh-preview");
      const previewStatus = document.getElementById("preview-status");
      const previewFrame = document.getElementById("preview-frame");
      const slideRail = document.getElementById("slide-rail");
      const previewError = document.getElementById("preview-error");
      const selectionStatus = document.getElementById("selection-status");
      let snapshot = null;
      let sessionId = "";
      let draftTimer = null;
      let previewTimer = null;
      let preview = null;
      let previewRequest = 0;
      let requestedSlide = 1;

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

      function paintPreviewState(value) {
        const status = value.status || "IDLE";
        previewStatus.dataset.status = status;
        previewStatus.textContent = `Preview ${status}`;
        if (status === "ERROR") previewError.textContent = (value.error && value.error.message) || "Preview failed";
        else previewError.textContent = "";
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
        if (body.preview) paintPreviewState(body.preview);
      }

      function showError(error) {
        const body = error.body;
        if (body && body.document) paint(body);
        message.textContent = error.message;
      }

      function selectSlide(index, notifyFrame = true) {
        if (!preview || !preview.slide_count) return;
        const selected = Math.max(1, Math.min(Number(index) || 1, preview.slide_count || 1));
        requestedSlide = selected;
        const payload = {channel: "officecli-workbench-preview", type: "show-slide", index: selected - 1};
        if (notifyFrame && previewFrame.contentWindow) previewFrame.contentWindow.postMessage(payload, "*");
        slideRail.querySelectorAll("[data-slide-index]").forEach((button) => {
          button.classList.toggle("current", Number(button.dataset.slideIndex) === selected);
        });
      }

      function renderRail() {
        slideRail.replaceChildren();
        if (!preview) return;
        preview.slides.forEach((slide) => {
          const wrapper = document.createElement("div");
          wrapper.className = "slide-thumbnail";
          const button = document.createElement("button");
          button.type = "button";
          button.dataset.slideIndex = String(slide.index);
          button.setAttribute("aria-label", `Go to ${slide.label}`);
          const thumbnail = document.createElement("iframe");
          thumbnail.title = `${slide.label} thumbnail`;
          thumbnail.setAttribute("sandbox", "allow-scripts");
          thumbnail.setAttribute("referrerpolicy", "no-referrer");
          thumbnail.srcdoc = preview.html;
          thumbnail.addEventListener("load", () => {
            thumbnail.contentWindow.postMessage(
              {channel: "officecli-workbench-preview", type: "show-slide", index: slide.index - 1},
              "*",
            );
          });
          button.appendChild(thumbnail);
          button.addEventListener("click", () => selectSlide(slide.index));
          const label = document.createElement("span");
          label.className = "slide-label";
          label.textContent = slide.label;
          wrapper.append(button, label);
          slideRail.appendChild(wrapper);
        });
        selectSlide(1);
      }

      async function refreshPreview() {
        const requestId = ++previewRequest;
        paintPreviewState({status: "STALE"});
        try {
          const body = await api("/api/preview", {
            method: "POST",
            body: JSON.stringify({text: editor.value}),
          });
          if (requestId !== previewRequest) return;
          paint(body);
          preview = body.preview;
          if (body.preview.status === "CURRENT" && body.preview.html) {
            previewFrame.srcdoc = body.preview.html;
            renderRail();
          }
          if (!body.ok) previewError.textContent = (body.preview.error && body.preview.error.message) || "Preview failed";
        } catch (error) {
          if (requestId !== previewRequest) return;
          showError(error);
          paintPreviewState({status: "ERROR", error: {message: error.message}});
        }
      }

      function schedulePreview() {
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = setTimeout(refreshPreview, 300);
      }

      window.addEventListener("message", async (event) => {
        if (!event.data || event.source !== previewFrame.contentWindow || event.data.channel !== "officecli-workbench-preview") return;
        if (event.data.type === "slide") {
          const reported = Number(event.data.index) || 1;
          if (reported === requestedSlide) selectSlide(reported, false);
          return;
        }
        if (event.data.type !== "selection" || !event.data.marker || !preview) return;
        try {
          const body = await api("/api/preview/select", {
            method: "POST",
            body: JSON.stringify({marker: event.data.marker, revision: preview.revision}),
          });
          const selected = body.selection || {};
          selectionStatus.dataset.mapping = selected.status || "unmapped";
          if (selected.status === "mapped") {
            editor.focus();
            editor.setSelectionRange(selected.editor_start ?? selected.source_start, selected.editor_end ?? selected.source_end);
            selectionStatus.textContent = `Selected ${selected.kind} at line ${selected.line}, column ${selected.column}.`;
          } else {
            selectionStatus.textContent = `Source selection ${selected.status || "unmapped"}: ${selected.reason || "No verified source range."}`;
          }
        } catch (error) {
          selectionStatus.dataset.mapping = "unmapped";
          selectionStatus.textContent = error.message;
        }
      });

      async function load() {
        try {
          paint(await api("/api/session"));
          await refreshPreview();
        } catch (error) { showError(error); state.textContent = "ERROR"; }
      }

      editor.addEventListener("input", () => {
        state.textContent = "DIRTY";
        build.disabled = true;
        paintPreviewState({status: "STALE"});
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(async () => {
          try { paint(await api("/api/draft", {method: "POST", body: JSON.stringify({text: editor.value})})); }
          catch (error) { showError(error); }
        }, 180);
        schedulePreview();
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
      refreshPreviewButton.addEventListener("click", refreshPreview);

      save.addEventListener("click", async () => {
        if (!snapshot) return;
        state.textContent = "SAVING";
        save.disabled = true;
        try { paint(await api("/api/save", {method: "POST", body: JSON.stringify({expected_sha256: snapshot.source_sha256, text: editor.value})})); }
        catch (error) { showError(error); }
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
