// Page logic: pick and inspect fonts, suggest settings, run the merge in the worker.
import {
  applyLanguage,
  detectLanguage,
  errorTitle,
  issueText,
  saveLanguage,
  t,
  translateProgress,
} from "./i18n.js";

const $ = (id) => document.getElementById(id);
const ROLES = ["western", "cjk"];
const TOTAL_STEPS = 11; // progress messages printed by pipeline.run

const state = {
  lang: detectLanguage(),
  ready: false,
  build: { version: "?", commit: "dev" },
  files: { western: null, cjk: null },
  info: { western: null, cjk: null }, // inspect result: {faces, profile, selected_face}
  inspectError: { western: null, cjk: null },
  face: { western: null, cjk: null },
  edited: { family: false, style: false, scale: false },
  seq: 0, // id of the latest request, per kind
  inspectId: { western: 0, cjk: 0 },
  suggestId: 0,
  mergeId: 0,
  merging: false,
  timer: null,
  downloadUrl: null,
  reportUrl: null,
  report: null, // last validation report, re-rendered on language change
  coverage: null, // Set of codepoints in the merged font
  previewFace: null,
  previewEdited: false,
};

// Test hook: the browser tests read state from here. simulate() feeds a worker message to
// the page, so layout can be checked without the Python runtime.
window.__fontmerge = {
  ready: false,
  lastResult: null,
  lastError: null,
  suggestion: null,
  info: state.info,
  simulate: (msg) => handle(msg),
};

let worker = createWorker();

function createWorker() {
  const w = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  w.onmessage = (event) => handle(event.data);
  w.onerror = (event) => {
    setStatus("error", "statusRuntimeFailed");
    showError({ kind: "WorkerError", message: event.message || "worker failed", hint: null });
  };
  return w;
}

function nextId() {
  state.seq += 1;
  return state.seq;
}

function handle(msg) {
  switch (msg.type) {
    case "status":
      if (!state.merging) setStatus("loading", msg.key);
      break;
    case "ready":
      state.ready = true;
      window.__fontmerge.ready = true;
      setStatus("ready", "statusReady");
      // Inspect anything picked while the runtime was loading (or after a cancel).
      for (const role of ROLES) if (state.files[role] && !state.info[role]) inspect(role);
      updateButtons();
      break;
    case "inspected":
      if (msg.id === state.inspectId[msg.role]) onInspected(msg.role, msg.info);
      break;
    case "suggested":
      if (msg.id === state.suggestId) onSuggested(msg.suggestion);
      break;
    case "progress":
      if (msg.id === state.mergeId) addProgress(msg.message);
      break;
    case "result":
      if (msg.id === state.mergeId) showResult(msg);
      break;
    case "error":
      if (msg.fatal) {
        setStatus("error", "statusRuntimeFailed");
        showError(msg.error);
      } else if (msg.role === "western" || msg.role === "cjk") {
        if (msg.id === state.inspectId[msg.role]) {
          state.inspectError[msg.role] = msg.error;
          renderSummary(msg.role);
          updateButtons();
        }
      } else if (msg.id === state.mergeId) {
        endMerge();
        setStatus("error", "statusError");
        showError(msg.error);
        window.__fontmerge.lastError = msg.error;
      }
      break;
  }
}

// --- picking and inspecting fonts ---------------------------------------------------

for (const role of ROLES) {
  $(role).addEventListener("change", () => {
    if ($(role).files[0]) setFile(role, $(role).files[0]);
  });
  const drop = $(`${role}-drop`);
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    const file = e.dataTransfer && e.dataTransfer.files[0];
    if (file) setFile(role, file);
  });
  $(`${role}-face`).addEventListener("change", () => {
    state.face[role] = Number($(`${role}-face`).value);
    state.info[role] = { ...state.info[role], profile: null };
    inspect(role);
  });
}

function setFile(role, file) {
  state.files[role] = file;
  state.info[role] = null;
  state.inspectError[role] = null;
  state.face[role] = null;
  renderFileName(role);
  renderSummary(role);
  inspect(role);
  updateButtons();
}

async function inspect(role) {
  const file = state.files[role];
  if (!file) return;
  const id = nextId();
  state.inspectId[role] = id;
  renderSummary(role);
  const bytes = new Uint8Array(await file.arrayBuffer());
  worker.postMessage(
    { type: "inspect", id, role, name: file.name, bytes, face: state.face[role] },
    [bytes.buffer],
  );
}

function onInspected(role, info) {
  const previous = state.info[role];
  state.info[role] = info;
  window.__fontmerge.info = state.info;
  const faces = info.faces || [];
  const row = $(`${role}-face-row`);
  row.hidden = faces.length < 2;
  if (faces.length > 1) {
    const select = $(`${role}-face`);
    if (!previous || select.options.length !== faces.length) {
      select.replaceChildren(
        ...faces.map((f) => new Option(`${f.index}: ${f.name}`, String(f.index))),
      );
    }
    if (!info.profile) {
      // A collection: start with the first face; the user can pick another.
      state.face[role] = 0;
      select.value = "0";
      inspect(role);
      return;
    }
    select.value = String(info.selected_face ?? 0);
  }
  renderSummary(role);
  requestSuggestion();
  updateButtons();
}

function requestSuggestion() {
  const w = state.info.western && state.info.western.profile;
  const c = state.info.cjk && state.info.cjk.profile;
  if (!w || !c) return;
  const id = nextId();
  state.suggestId = id;
  worker.postMessage({ type: "suggest", id, western: w, cjk: c });
}

function onSuggested(s) {
  window.__fontmerge.suggestion = s;
  let changed = false;
  if (!state.edited.family) {
    $("family").value = s.family;
    changed = true;
  }
  if (!state.edited.style) {
    $("style").value = s.style;
    changed = true;
  }
  if (!state.edited.scale) {
    $("scale").value = s.scale.toFixed(2);
    changed = true;
  }
  $("suggested").hidden = !changed;
  checkReservedNames();
}

$("swap").addEventListener("click", () => {
  for (const key of ["files", "info", "inspectError", "face"]) {
    [state[key].western, state[key].cjk] = [state[key].cjk, state[key].western];
  }
  for (const role of ROLES) {
    renderFileName(role);
    const faces = (state.info[role] && state.info[role].faces) || [];
    $(`${role}-face-row`).hidden = faces.length < 2;
    $(`${role}-face`).replaceChildren(
      ...faces.map((f) => new Option(`${f.index}: ${f.name}`, String(f.index))),
    );
    if (state.face[role] !== null) $(`${role}-face`).value = String(state.face[role]);
    renderSummary(role);
  }
  state.edited.scale = false; // the scale depends on which font is which
  requestSuggestion();
  updateButtons();
});

// --- settings ------------------------------------------------------------------------

for (const field of ["family", "style", "scale"]) {
  $(field).addEventListener("input", () => {
    state.edited[field] = true;
    if (field === "family") checkReservedNames();
  });
}

function reservedNames() {
  const names = [];
  for (const role of ROLES) {
    const p = state.info[role] && state.info[role].profile;
    if (p) names.push(...(p.reserved_font_names || []));
  }
  return names;
}

// Same rule as fontmerge.metadata (case-insensitive, spaces ignored); Python enforces it too.
function checkReservedNames() {
  const family = $("family").value.toLowerCase();
  const squashed = family.replace(/ /g, "");
  const hits = reservedNames().filter((r) => {
    const low = r.toLowerCase();
    return family.includes(low) || squashed.includes(low.replace(/ /g, ""));
  });
  const warning = $("rfn-warning");
  warning.hidden = hits.length === 0;
  warning.dataset.names = hits.join(", ");
  warning.textContent = hits.length ? t(state.lang, "rfnWarning", { names: hits.join("”, “") }) : "";
  return hits;
}

function settingsFromForm() {
  const value = (id) => $(id).value.trim();
  const settings = {
    naming: {
      family: value("family"),
      style: value("style") || "Regular",
      version: value("font-version") || "1.000",
      vendor_id: value("vendor") || "NONE",
    },
    metrics: { line_height: $("line-height").value },
    routing: {
      punctuation: $("punctuation").value,
      symbols: $("symbols").value,
      include_hangul: $("include-hangul").checked,
      fallback: $("fallback").checked,
      overrides: $("overrides")
        .value.split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    },
    normalize: { target_outline: $("outline").value },
    format: $("format").value,
    strict: $("strict").checked,
  };
  const scale = parseFloat($("scale").value);
  if (Number.isFinite(scale)) settings.normalize.western_scale = scale;
  const shift = parseInt($("baseline-shift").value, 10);
  if (Number.isFinite(shift)) settings.normalize.western_baseline_shift = shift;
  if (state.face.western !== null) settings.western_face = state.face.western;
  if (state.face.cjk !== null) settings.cjk_face = state.face.cjk;
  return settings;
}

// --- merging -------------------------------------------------------------------------

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.files.western || !state.files.cjk) {
    setStatus("error", "statusNeedFiles");
    return;
  }
  state.mergeId = nextId();
  resetPanels();
  startMerge();
  const [wBytes, cBytes] = await Promise.all([
    state.files.western.arrayBuffer().then((b) => new Uint8Array(b)),
    state.files.cjk.arrayBuffer().then((b) => new Uint8Array(b)),
  ]);
  worker.postMessage(
    {
      type: "merge",
      id: state.mergeId,
      western: { name: state.files.western.name, bytes: wBytes },
      cjk: { name: state.files.cjk.name, bytes: cBytes },
      settings: settingsFromForm(),
    },
    [wBytes.buffer, cBytes.buffer],
  );
});

$("cancel").addEventListener("click", () => {
  if (!state.merging) return;
  worker.terminate();
  state.ready = false;
  window.__fontmerge.ready = false;
  state.mergeId = nextId(); // ignore anything still in flight
  endMerge();
  setStatus("loading", "statusCancelled");
  window.__fontmerge.cancelled = true;
  worker = createWorker();
  updateButtons();
});

function startMerge() {
  state.merging = true;
  $("progress-panel").hidden = false;
  $("bar").hidden = false;
  $("bar").value = 0;
  const started = performance.now();
  const tick = () => {
    $("elapsed").textContent = t(state.lang, "elapsed", { s: Math.round((performance.now() - started) / 1000) });
  };
  tick();
  state.timer = setInterval(tick, 1000);
  setStatus("merging", "merging");
  updateButtons();
}

function endMerge() {
  state.merging = false;
  clearInterval(state.timer);
  $("bar").hidden = true;
  updateButtons();
}

// --- display -------------------------------------------------------------------------

function setStatus(stateName, key, vars) {
  const el = $("status");
  el.dataset.state = stateName;
  el.dataset.key = key;
  el.dataset.vars = JSON.stringify(vars || {});
  el.textContent = t(state.lang, key, vars);
}

function updateButtons() {
  const merge = $("merge");
  merge.disabled = state.merging || !state.ready;
  merge.dataset.i18n = state.merging ? "merging" : "merge";
  merge.textContent = t(state.lang, merge.dataset.i18n);
  $("cancel").hidden = !state.merging;
  $("swap").disabled = state.merging || !(state.files.western || state.files.cjk);
}

function renderFileName(role) {
  const label = $(`${role}-name`);
  const file = state.files[role];
  if (file) {
    label.textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`;
    label.removeAttribute("data-i18n");
    $(`${role}-drop`).classList.add("has-file");
  } else {
    label.dataset.i18n = "dropHere";
    label.textContent = t(state.lang, "dropHere");
    $(`${role}-drop`).classList.remove("has-file");
  }
}

function renderSummary(role) {
  const box = $(`${role}-summary`);
  box.replaceChildren();
  if (!state.files[role]) return;
  const error = state.inspectError[role];
  if (error) {
    box.append(el("p", "summary-error", error.message));
    return;
  }
  const info = state.info[role];
  if (!info || !info.profile) {
    box.append(el("p", "muted", t(state.lang, "reading")));
    return;
  }
  const p = info.profile;
  const nf = new Intl.NumberFormat(state.lang === "zh-Hant" ? "zh-TW" : "en");
  box.append(el("p", "summary-name", `${p.family} ${p.style}`.trim()));
  box.append(
    el(
      "p",
      "muted",
      [
        t(state.lang, "glyphsN", { n: nf.format(p.glyphs) }),
        t(state.lang, "charactersN", { n: nf.format(p.characters) }),
        t(state.lang, "upmN", { n: p.upm }),
        p.outline === "glyf" ? "TrueType" : p.outline,
      ].join(" · "),
    ),
  );
  const chips = el("p", "chips");
  const labels = { latin: "covLatin", greek: "covGreek", cyrillic: "covCyrillic", han: "covHan", kana: "covKana", hangul: "covHangul" };
  for (const [key, label] of Object.entries(labels)) {
    const n = p.coverage[key];
    if (n) chips.append(el("span", "chip", `${t(state.lang, label)} ${nf.format(n)}`));
  }
  box.append(chips);
  const reserved = p.reserved_font_names.length ? p.reserved_font_names.join(", ") : t(state.lang, "none");
  box.append(
    el("p", "muted", `${t(state.lang, "embedding")}: ${p.embedding} · ${t(state.lang, "reservedNames")}: ${reserved}`),
  );
  const issues = role === "western" ? p.as_western : p.as_cjk;
  const shown = issues.filter((i) => i.code !== "license-reserved-names");
  if (shown.length) {
    const list = el("ul", "summary-issues");
    for (const issue of shown) list.append(el("li", issue.severity, issueText(state.lang, issue, role)));
    box.append(list);
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function addProgress(message) {
  const li = document.createElement("li");
  li.dataset.raw = message;
  li.textContent = translateProgress(state.lang, message);
  $("progress").append(li);
  $("bar").value = Math.min($("progress").children.length, TOTAL_STEPS);
}

function resetPanels() {
  $("progress").replaceChildren();
  $("error-panel").hidden = true;
  $("result-panel").hidden = true;
  window.__fontmerge.lastResult = null;
  window.__fontmerge.lastError = null;
  window.__fontmerge.cancelled = false;
}

function showError(error) {
  $("error-panel").hidden = false;
  $("error-panel").dataset.kind = error.kind;
  $("error-title").textContent = errorTitle(state.lang, error.kind);
  $("error-title").dataset.kind = error.kind;
  $("error-message").textContent = error.message;
  const runtime = error.kind === "RuntimeLoadError" || error.kind === "WorkerError";
  const hintText = error.hint || (runtime ? t(state.lang, "errRuntimeHint") : "");
  const hint = $("error-hint");
  hint.hidden = !hintText;
  hint.querySelector("span").textContent = hintText;
  $("error-detail-box").hidden = !error.detail;
  $("error-detail").textContent = error.detail || "";
  $("retry").hidden = !runtime;
  const known = errorTitle("en", error.kind) !== errorTitle("en", "Internal");
  $("report-bug").hidden = known && !error.detail;
  updateButtons();
}

$("retry").addEventListener("click", () => {
  worker.terminate();
  state.ready = false;
  window.__fontmerge.ready = false;
  $("error-panel").hidden = true;
  setStatus("loading", "statusLoadingRuntime");
  worker = createWorker();
  updateButtons();
});

function showResult(msg) {
  const { meta, font } = msg;
  const report = meta.report;
  endMerge();
  if (state.downloadUrl) URL.revokeObjectURL(state.downloadUrl);
  const type = meta.format === "otf" ? "font/otf" : meta.format === "woff2" ? "font/woff2" : "font/ttf";
  state.downloadUrl = URL.createObjectURL(new Blob([font], { type }));
  const link = $("download");
  link.href = state.downloadUrl;
  link.download = meta.filename;
  $("r-file").textContent = `${meta.filename} · ${(font.byteLength / 1048576).toFixed(1)} MB`;

  const nf = new Intl.NumberFormat(state.lang === "zh-Hant" ? "zh-TW" : "en");
  const chars = (report.coverage.western || 0) + (report.coverage.cjk || 0);
  $("r-glyphs").textContent = nf.format(report.glyph_count);
  $("r-chars").textContent = nf.format(chars);
  $("r-chars").title = `${nf.format(report.coverage.western)} ${t(state.lang, "fromWestern")}, ${nf.format(report.coverage.cjk)} ${t(state.lang, "fromCjk")}`;
  $("r-time").textContent = `${meta.seconds} s`;
  $("r-memory").textContent = msg.wasmHeapBytes ? `${Math.round(msg.wasmHeapBytes / 1048576)} MB` : "–";

  $("download-format").textContent = meta.format.toUpperCase();
  if (state.reportUrl) URL.revokeObjectURL(state.reportUrl);
  const reportJson = JSON.stringify({ ...report, font: meta.filename, fontmerge: meta.version }, null, 2);
  state.reportUrl = URL.createObjectURL(new Blob([reportJson], { type: "application/json" }));
  $("download-report").href = state.reportUrl;
  $("download-report").download = meta.filename.replace(/\.[^.]+$/, "") + ".report.json";

  state.report = report;
  renderReport();
  state.coverage = expandRanges(meta.codepoints || []);
  loadPreviewFont(font, meta.filename);

  $("result-panel").hidden = false;
  setStatus("done", "statusDone", { seconds: meta.seconds });
  window.__fontmerge.lastResult = {
    filename: meta.filename,
    seconds: meta.seconds,
    wasmHeapBytes: msg.wasmHeapBytes,
    glyphs: report.glyph_count,
    coverage: report.coverage,
    issues: report.issues,
    bytes: font.byteLength,
  };
}

// --- report ------------------------------------------------------------------------

function renderReport() {
  const box = $("report");
  box.replaceChildren();
  const report = state.report;
  if (!report) return;
  if (!report.issues.length) {
    box.append(el("p", "muted", t(state.lang, "noIssues")));
    return;
  }
  const groups = [
    ["error", "errorsN"],
    ["warning", "warningsN"],
    ["info", "notesN"],
  ];
  for (const [severity, key] of groups) {
    const issues = report.issues.filter((i) => i.severity === severity);
    if (!issues.length) continue;
    const section = el("section", `report-group ${severity}`);
    section.dataset.severity = severity;
    section.append(el("h4", "", t(state.lang, key, { n: issues.length })));
    const list = el("ul", "");
    for (const issue of issues) {
      const li = el("li", severity, issueText(state.lang, issue));
      li.dataset.code = issue.code;
      list.append(li);
    }
    section.append(list);
    box.append(section);
  }
}

// --- preview -------------------------------------------------------------------------

function expandRanges(ranges) {
  const set = new Set();
  for (const [start, end] of ranges) for (let cp = start; cp <= end; cp++) set.add(cp);
  return set;
}

async function loadPreviewFont(bytes, filename) {
  const family = `fontmerge-preview-${state.mergeId}`;
  const face = new FontFace(family, bytes);
  try {
    await face.load();
  } catch (e) {
    console.warn("preview font failed to load", e);
    return;
  }
  if (state.previewFace) document.fonts.delete(state.previewFace);
  document.fonts.add(face);
  state.previewFace = face;
  for (const id of ["preview-h", "preview-v"]) {
    $(id).style.fontFamily = `"${family}", system-ui, sans-serif`;
  }
  window.__fontmerge.preview = { family, filename };
  if (!state.previewEdited) $("preview-text").value = t(state.lang, "previewSample");
  renderPreview();
}

const NO_GLYPH_NEEDED = /[\s\u200b-\u200f\ufe00-\ufe0f]/;

function renderPreview() {
  const text = $("preview-text").value;
  const missing = new Set();
  for (const id of ["preview-h", "preview-v"]) {
    const box = $(id);
    box.replaceChildren();
    for (const ch of text) {
      const cp = ch.codePointAt(0);
      if (ch === "\n") {
        box.append(document.createElement("br"));
      } else if (state.coverage && !state.coverage.has(cp) && !NO_GLYPH_NEEDED.test(ch)) {
        missing.add(ch);
        const span = el("span", "missing", ch);
        span.title = `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`;
        box.append(span);
      } else {
        box.append(document.createTextNode(ch));
      }
    }
  }
  const note = $("preview-missing");
  note.hidden = missing.size === 0;
  note.textContent = missing.size
    ? t(state.lang, "previewMissing", { count: missing.size, chars: [...missing].join(" ") })
    : "";
  window.__fontmerge.previewMissing = [...missing];
}

function setPreviewSize() {
  const size = Number($("preview-size").value);
  for (const id of ["preview-h", "preview-v"]) $(id).style.fontSize = `${size}px`;
  $("preview-size-value").textContent = `${size} px`;
}

$("preview-text").addEventListener("input", () => {
  state.previewEdited = true;
  renderPreview();
});
$("preview-size").addEventListener("input", setPreviewSize);
$("preview-reset").addEventListener("click", () => {
  state.previewEdited = false;
  $("preview-text").value = t(state.lang, "previewSample");
  renderPreview();
});
setPreviewSize();

// --- language and footer -----------------------------------------------------------

function renderLanguage() {
  applyLanguage(state.lang);
  const status = $("status");
  if (status.dataset.key) status.textContent = t(state.lang, status.dataset.key, JSON.parse(status.dataset.vars || "{}"));
  for (const li of $("progress").children) li.textContent = translateProgress(state.lang, li.dataset.raw);
  for (const role of ROLES) {
    renderFileName(role);
    renderSummary(role);
  }
  checkReservedNames();
  renderReport();
  if (state.previewFace) {
    if (!state.previewEdited) $("preview-text").value = t(state.lang, "previewSample");
    renderPreview();
  }
  const errorTitleEl = $("error-title");
  if (errorTitleEl.dataset.kind) errorTitleEl.textContent = errorTitle(state.lang, errorTitleEl.dataset.kind);
  updateButtons();
  $("footer").textContent = t(state.lang, "footer", { version: state.build.version, commit: state.build.commit });
}

$("lang").addEventListener("click", () => {
  state.lang = state.lang === "zh-Hant" ? "en" : "zh-Hant";
  saveLanguage(state.lang);
  renderLanguage();
});

fetch("build.json", { cache: "no-cache" })
  .then((r) => (r.ok ? r.json() : null))
  .then((data) => {
    if (data) state.build = { version: data.version, commit: String(data.commit).slice(0, 7) };
    renderLanguage();
  })
  .catch(() => renderLanguage());

renderLanguage();
setStatus("loading", "statusLoadingRuntime");
