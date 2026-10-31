// Page logic: read the two fonts, send them to the worker, show progress and the result.
import { applyLanguage, detectLanguage, saveLanguage, t, translateProgress } from "./i18n.js";

const $ = (id) => document.getElementById(id);
let lang = detectLanguage();
let runtimeReady = false;
let mergeId = 0;
let downloadUrl = null;
let build = { version: "?", commit: "dev" };

// Test hook: the browser tests read results from here.
window.__fontmerge = { ready: false, lastResult: null, lastError: null };

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
worker.onmessage = (event) => handle(event.data);
worker.onerror = (event) => {
  setStatus("error", "statusRuntimeFailed");
  showError({ kind: "WorkerError", message: event.message || "worker failed", hint: null });
};

function handle(msg) {
  switch (msg.type) {
    case "status":
      setStatus("loading", msg.key);
      break;
    case "ready":
      runtimeReady = true;
      window.__fontmerge.ready = true;
      setStatus("ready", "statusReady");
      updateButton();
      break;
    case "progress":
      if (msg.id === mergeId) addProgress(msg.message);
      break;
    case "result":
      if (msg.id === mergeId) showResult(msg);
      break;
    case "error":
      if (msg.fatal) {
        setStatus("error", "statusRuntimeFailed");
        showError(msg.error);
      } else if (msg.id === mergeId) {
        setStatus("error", "statusError");
        showError(msg.error);
        window.__fontmerge.lastError = msg.error;
        updateButton();
      }
      break;
  }
}

// --- form ---------------------------------------------------------------------------

for (const id of ["western", "cjk"]) {
  $(id).addEventListener("change", () => {
    const file = $(id).files[0];
    const label = $(`${id}-name`);
    if (file) {
      label.textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`;
      label.removeAttribute("data-i18n");
    }
    updateButton();
  });
}

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const western = $("western").files[0];
  const cjk = $("cjk").files[0];
  if (!western || !cjk) {
    setStatus("error", "statusNeedFiles");
    return;
  }
  mergeId += 1;
  resetPanels();
  $("progress-panel").hidden = false;
  setBusy(true);
  const [wBytes, cBytes] = await Promise.all([readBytes(western), readBytes(cjk)]);
  worker.postMessage(
    {
      type: "merge",
      id: mergeId,
      western: { name: western.name, bytes: wBytes },
      cjk: { name: cjk.name, bytes: cBytes },
      settings: settingsFromForm(),
    },
    [wBytes.buffer, cBytes.buffer],
  );
});

function settingsFromForm() {
  const settings = {
    naming: { family: $("family").value.trim(), style: $("style").value.trim() || "Regular" },
    metrics: { line_height: $("line-height").value },
    format: $("format").value,
  };
  const scale = parseFloat($("scale").value);
  if (Number.isFinite(scale)) settings.normalize = { western_scale: scale };
  const face = $("cjk-face").value.trim();
  if (face) settings.cjk_face = /^\d+$/.test(face) ? Number(face) : face;
  return settings;
}

async function readBytes(file) {
  return new Uint8Array(await file.arrayBuffer());
}

// --- display ------------------------------------------------------------------------

function setStatus(state, key, vars) {
  const el = $("status");
  el.dataset.state = state;
  el.dataset.key = key;
  el.dataset.vars = JSON.stringify(vars || {});
  el.textContent = t(lang, key, vars);
}

function setBusy(busy) {
  const button = $("merge");
  button.disabled = busy;
  button.textContent = t(lang, busy ? "merging" : "merge");
  button.dataset.i18n = busy ? "merging" : "merge";
  if (busy) setStatus("merging", "merging");
}

function updateButton() {
  const busy = $("status").dataset.state === "merging";
  $("merge").disabled = busy || !runtimeReady;
}

function addProgress(message) {
  const li = document.createElement("li");
  li.dataset.raw = message;
  li.textContent = translateProgress(lang, message);
  $("progress").append(li);
}

function resetPanels() {
  $("progress").replaceChildren();
  $("error-panel").hidden = true;
  $("result-panel").hidden = true;
  window.__fontmerge.lastResult = null;
  window.__fontmerge.lastError = null;
}

function showError(error) {
  $("error-panel").hidden = false;
  $("error-message").textContent = error.message;
  const hint = $("error-hint");
  hint.hidden = !error.hint;
  hint.querySelector("span").textContent = error.hint || "";
  const detail = $("error-detail");
  detail.hidden = !error.detail;
  detail.textContent = error.detail || "";
  setBusy(false);
  updateButton();
}

function showResult(msg) {
  const { meta, font } = msg;
  const report = meta.report;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  const type = meta.format === "otf" ? "font/otf" : meta.format === "woff2" ? "font/woff2" : "font/ttf";
  downloadUrl = URL.createObjectURL(new Blob([font], { type }));
  const link = $("download");
  link.href = downloadUrl;
  link.download = meta.filename;
  $("r-file").textContent = `${meta.filename} · ${(font.byteLength / 1048576).toFixed(1)} MB`;

  const nf = new Intl.NumberFormat(lang === "zh-Hant" ? "zh-TW" : "en");
  const chars = (report.coverage.western || 0) + (report.coverage.cjk || 0);
  $("r-glyphs").textContent = nf.format(report.glyph_count);
  $("r-chars").textContent = nf.format(chars);
  $("r-time").textContent = `${meta.seconds} s`;
  $("r-memory").textContent = msg.wasmHeapBytes ? `${Math.round(msg.wasmHeapBytes / 1048576)} MB` : "–";
  $("r-chars").title = `${nf.format(report.coverage.western)} ${t(lang, "fromWestern")}, ${nf.format(report.coverage.cjk)} ${t(lang, "fromCjk")}`;

  const list = $("issues");
  list.replaceChildren();
  if (!report.issues.length) {
    const li = document.createElement("li");
    li.textContent = t(lang, "noIssues");
    list.append(li);
  }
  for (const issue of report.issues) {
    const li = document.createElement("li");
    li.className = issue.severity;
    li.textContent = `[${issue.severity}] ${issue.message}`;
    list.append(li);
  }

  $("result-panel").hidden = false;
  setBusy(false);
  setStatus("done", "statusDone", { seconds: meta.seconds });
  updateButton();
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

// --- language and footer -----------------------------------------------------------

function renderLanguage() {
  applyLanguage(lang);
  const status = $("status");
  if (status.dataset.key) status.textContent = t(lang, status.dataset.key, JSON.parse(status.dataset.vars || "{}"));
  for (const li of $("progress").children) li.textContent = translateProgress(lang, li.dataset.raw);
  for (const id of ["western", "cjk"]) {
    const file = $(id).files[0];
    if (file) $(`${id}-name`).textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`;
  }
  $("footer").textContent = t(lang, "footer", { version: build.version, commit: build.commit });
}

$("lang").addEventListener("click", () => {
  lang = lang === "zh-Hant" ? "en" : "zh-Hant";
  saveLanguage(lang);
  renderLanguage();
});

fetch("build.json", { cache: "no-cache" })
  .then((r) => (r.ok ? r.json() : null))
  .then((data) => {
    if (data) build = { version: data.version, commit: String(data.commit).slice(0, 7) };
    renderLanguage();
  })
  .catch(() => renderLanguage());

renderLanguage();
setStatus("loading", "statusLoadingRuntime");
updateButton();
