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
    #inspector { border-top: 1px solid #d5dce2; margin-top: 14px; padding-top: 8px; }
    #inspector h2 { font-size: 14px; margin: 4px 0 8px; }
    #inspector textarea, #inspector input { display: block; width: 100%; box-sizing: border-box; margin: 4px 0 6px;
      padding: 6px; border: 1px solid #93a4b3; border-radius: 4px; background: transparent; color: inherit; }
    #inspector textarea { min-height: 58px; resize: vertical; }
    .inspector-field { border-top: 1px solid #e3e8ed; padding: 6px 0; }
    .inspector-field label { font-weight: 600; }
    .inspector-field .muted { font-size: 11px; }
    #source-diff { white-space: pre-wrap; overflow-wrap: anywhere; background: #f4f6f8; padding: 8px; }
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
      <section id="inspector" aria-label="Selected object Inspector">
        <h2>Inspector</h2>
        <p id="inspector-selection" class="muted">Select a mapped text leaf or run in Preview.</p>
        <label for="inspector-text">Text</label>
        <textarea id="inspector-text" disabled></textarea>
        <div id="inspector-text-origin" class="muted"></div>
        <button id="apply-text" type="button" disabled>Apply text</button>
        <div id="inspector-fields"></div>
        <details>
          <summary>Focused source diff</summary>
          <pre id="source-diff" class="muted">No Inspector patch applied.</pre>
        </details>
      </section>
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
      const inspectorSelection = document.getElementById("inspector-selection");
      const inspectorText = document.getElementById("inspector-text");
      const inspectorTextOrigin = document.getElementById("inspector-text-origin");
      const applyTextButton = document.getElementById("apply-text");
      const inspectorFields = document.getElementById("inspector-fields");
      const sourceDiff = document.getElementById("source-diff");
      let snapshot = null;
      let sessionId = "";
      let previewTimer = null;
      let preview = null;
      let previewRequest = 0;
      let selectionRequest = 0;
      let selected = null;
      let editVersion = 0;
      let lastServerText = null;
      let mutationQueue = Promise.resolve();
      let requestedSlide = 1;

      function normalizedText(value) { return String(value).replace(/\r\n?/g, "\n"); }
      function editorMatchesText(value, text) { return normalizedText(value) === normalizedText(text); }
      function editorDraftText() {
        return snapshot && editorMatchesText(editor.value, snapshot.text) ? snapshot.text : editor.value;
      }

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

      function enqueueMutation(action) {
        const result = mutationQueue.then(action);
        mutationQueue = result.catch(() => {});
        return result;
      }

      function draftPreconditions() {
        return {
          expected_draft_revision: snapshot.draft_revision,
          expected_draft_sha256: snapshot.draft_sha256,
        };
      }

      function updatePreview(body) {
        if (!body.preview) return;
        preview = body.preview;
        if (body.preview.status === "CURRENT" && body.preview.html) {
          previewFrame.srcdoc = body.preview.html;
          renderRail();
        }
        paintPreviewState(body.preview);
      }

      function clearInspector(messageText = "Select a mapped text leaf or run in Preview.") {
        selected = null;
        selectionRequest += 1;
        inspectorSelection.textContent = messageText;
        inspectorText.value = "";
        inspectorText.disabled = true;
        inspectorTextOrigin.textContent = "";
        applyTextButton.disabled = true;
        inspectorFields.replaceChildren();
      }

      function renderInspector(selection, identity) {
        const inspector = selection.inspector || {};
        selected = Object.assign({marker: selection.marker}, identity);
        const label = `${selection.kind || "object"}${selection.tag ? ` · <${selection.tag}>` : ""}`;
        inspectorSelection.textContent = `Slide ${selection.slide || "?"} · ${label}`;
        const text = inspector.text || {};
        inspectorText.value = text.source || "";
        inspectorText.disabled = !text.editable;
        inspectorTextOrigin.textContent = [
          text.computed != null ? `Computed: ${text.computed}` : "Computed: unavailable",
          text.origin ? `Source/origin: ${text.origin}` : "",
          text.reason || "",
        ].filter(Boolean).join(" · ");
        applyTextButton.disabled = !text.editable;
        inspectorFields.replaceChildren();
        Object.entries(inspector.fields || {}).forEach(([name, field]) => {
          const row = document.createElement("div");
          row.className = "inspector-field";
          const labelNode = document.createElement("label");
          labelNode.textContent = name;
          const computedNode = document.createElement("div");
          computedNode.className = "muted";
          computedNode.textContent = `Computed: ${field.computed == null ? "unavailable" : field.computed}`;
          const sourceNode = document.createElement("div");
          sourceNode.className = "muted";
          sourceNode.textContent = `Source/origin: ${field.source || field.origin || "none"}`;
          row.append(labelNode, computedNode, sourceNode);
          if (field.local_override && field.editable) {
            const override = document.createElement("div");
            override.className = "muted";
            override.textContent = "Local override: this edits only the selected object; the shared class rule stays unchanged.";
            row.appendChild(override);
          }
          const input = document.createElement("input");
          input.type = "text";
          input.value = field.computed == null ? "" : String(field.computed);
          input.disabled = !field.editable;
          input.setAttribute("aria-label", `${name} value`);
          const apply = document.createElement("button");
          apply.type = "button";
          apply.textContent = `Apply ${name}`;
          apply.disabled = !field.editable;
          apply.addEventListener("click", () => applyInspector({kind: "property", name, value: input.value}));
          row.append(input, apply);
          if (field.reason) {
            const reason = document.createElement("div");
            reason.className = "muted";
            reason.textContent = `Read-only: ${field.reason}`;
            row.appendChild(reason);
          }
          inspectorFields.appendChild(row);
        });
        selectionStatus.dataset.mapping = selection.status || "mapped";
        selectionStatus.textContent = `Selected ${label} at line ${selection.line}, column ${selection.column}.`;
      }

      function paintPreviewState(value) {
        const status = value.status || "IDLE";
        previewStatus.dataset.status = status;
        previewStatus.textContent = `Preview ${status}`;
        if (status === "ERROR") previewError.textContent = (value.error && value.error.message) || "Preview failed";
        else previewError.textContent = "";
      }

      function paint(body, editorVersion = null) {
        if (body.session_id) sessionId = body.session_id;
        snapshot = body.document;
        const editorWasInSync = lastServerText === null || editorMatchesText(editor.value, lastServerText);
        if ((editorVersion === null && editorWasInSync) || editorVersion === editVersion) {
          editor.value = snapshot.text;
        }
        lastServerText = snapshot.text;
        const editorMatchesDraft = editorMatchesText(editor.value, snapshot.text);
        state.textContent = editorMatchesDraft ? snapshot.state : "DIRTY";
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
          editorMatchesDraft &&
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
          const result = await enqueueMutation(async () => {
            const version = editVersion;
            const body = await api("/api/preview", {
              method: "POST",
              body: JSON.stringify(Object.assign({text: editorDraftText()}, draftPreconditions())),
            });
            paint(body, version);
            if (requestId !== previewRequest) paintPreviewState({status: "STALE"});
            return {body, version};
          });
          if (requestId !== previewRequest) return;
          const body = result.body;
          updatePreview(body);
          clearInspector();
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

      async function applyInspector(intent) {
        if (!selected || !snapshot) return;
        if (!editorMatchesText(editor.value, snapshot.text)) {
          showError(new Error("Source editor has an unsent change; wait for Preview to refresh, then select the object again."));
          return;
        }
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        const chosen = Object.assign({}, selected);
        const version = editVersion;
        try {
          const body = await enqueueMutation(async () => {
            if (
              editVersion !== version || !editorMatchesText(editor.value, snapshot.text) ||
              snapshot.draft_revision !== chosen.draft_revision ||
              snapshot.draft_sha256 !== chosen.draft_sha256 ||
              !preview || preview.revision !== chosen.preview_revision || preview.status !== "CURRENT"
            ) throw new Error("Preview selection is stale; refresh Preview and select the object again.");
            const response = await api("/api/inspector/apply", {
              method: "POST",
              body: JSON.stringify({
                marker: chosen.marker,
                preview_revision: chosen.preview_revision,
                draft_revision: chosen.draft_revision,
                draft_sha256: chosen.draft_sha256,
                intent,
              }),
            });
            paint(response, version);
            return response;
          });
          if (version !== editVersion) {
            paintPreviewState({status: "STALE"});
            return;
          }
          if (body.source_patch) sourceDiff.textContent = body.source_patch.diff;
          updatePreview(body);
          clearInspector("Patch applied to the Draft. Select the refreshed Preview object to continue.");
          message.textContent = body.source_patch && body.source_patch.local_override
            ? "Applied as a local override; the shared class rule remains unchanged."
            : "Inspector patch applied to the Draft. Save and Check remain explicit.";
        } catch (error) { showError(error); }
      }

      window.addEventListener("message", async (event) => {
        if (!event.data || event.source !== previewFrame.contentWindow || event.data.channel !== "officecli-workbench-preview") return;
        if (event.data.type === "slide") {
          const reported = Number(event.data.index) || 1;
          if (reported === requestedSlide) selectSlide(reported, false);
          return;
        }
        if (event.data.type !== "selection" || !event.data.marker || !preview) return;
        const requestId = ++selectionRequest;
        const selectedPreview = preview;
        const identity = {
          preview_revision: selectedPreview.revision,
          draft_revision: selectedPreview.draft_revision,
          draft_sha256: selectedPreview.draft_sha256,
        };
        try {
          const body = await api("/api/preview/select", {
            method: "POST",
            body: JSON.stringify(Object.assign({
              marker: event.data.marker,
              computed: {text: event.data.text, styles: event.data.styles},
              matched_styles: event.data.matched_styles,
            }, identity)),
          });
          if (requestId !== selectionRequest || preview !== selectedPreview) return;
          const selected = body.selection || {};
          selectionStatus.dataset.mapping = selected.status || "unmapped";
          if (selected.status === "mapped") {
            if (selected.editor_start != null && selected.editor_end != null) {
              editor.focus();
              editor.setSelectionRange(selected.editor_start, selected.editor_end);
            }
            renderInspector(selected, Object.assign({marker: event.data.marker}, identity));
          } else {
            selectionStatus.textContent = `Source selection ${selected.status || "unmapped"}: ${selected.reason || "No verified source range."}`;
            clearInspector(selectionStatus.textContent);
          }
        } catch (error) {
          if (requestId !== selectionRequest) return;
          selectionStatus.dataset.mapping = "unmapped";
          selectionStatus.textContent = error.message;
          clearInspector(error.message);
        }
      });

      async function load() {
        try {
          paint(await api("/api/session"));
          await refreshPreview();
        } catch (error) { showError(error); state.textContent = "ERROR"; }
      }

      editor.addEventListener("input", () => {
        editVersion += 1;
        state.textContent = "DIRTY";
        build.disabled = true;
        paintPreviewState({status: "STALE"});
        clearInspector("Source changed. Wait for Preview to refresh, then select the object again.");
        schedulePreview();
      });

      applyTextButton.addEventListener("click", () => applyInspector({kind: "text", value: inspectorText.value}));

      check.addEventListener("click", async () => {
        check.disabled = true;
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        try {
          await enqueueMutation(async () => {
            const version = editVersion;
            const body = await api("/api/check", {
              method: "POST",
              body: JSON.stringify(Object.assign({text: editorDraftText()}, draftPreconditions())),
            });
            paint(body, version);
            if (version !== editVersion) paintPreviewState({status: "STALE"});
            if (body.preview && body.preview.status === "STALE") schedulePreview();
          });
        }
        catch (error) { showError(error); }
        finally { check.disabled = false; }
      });

      build.addEventListener("click", async () => {
        build.disabled = true;
        try { await enqueueMutation(async () => paint(await api("/api/build", {method: "POST", body: JSON.stringify({})}))); }
        catch (error) { showError(error); }
      });
      refreshPreviewButton.addEventListener("click", refreshPreview);

      save.addEventListener("click", async () => {
        if (!snapshot) return;
        state.textContent = "SAVING";
        save.disabled = true;
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        try {
          await enqueueMutation(async () => {
            const version = editVersion;
            const body = await api("/api/save", {
              method: "POST",
              body: JSON.stringify(Object.assign({expected_sha256: snapshot.source_sha256, text: editorDraftText()}, draftPreconditions())),
            });
            paint(body, version);
            if (version !== editVersion) paintPreviewState({status: "STALE"});
            if (body.preview && body.preview.status === "STALE") schedulePreview();
          });
        }
        catch (error) { showError(error); }
        finally { save.disabled = false; }
      });

      recover.addEventListener("click", async () => {
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        try {
          await enqueueMutation(async () => {
            const body = await api("/api/recovery/restore", {
              method: "POST",
              body: JSON.stringify(draftPreconditions()),
            });
            paint(body);
            schedulePreview();
          });
        }
        catch (error) { showError(error); }
      });

      load();
    })();
  </script>
</body>
</html>
"""


__all__ = ["INDEX_HTML"]
