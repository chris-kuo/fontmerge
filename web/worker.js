// Web Worker: runs Pyodide and the fontmerge package, so the page stays responsive.
//
// Messages in:
//   {type: "inspect", id, role, name, bytes, face}
//   {type: "suggest", id, western, cjk}              (profile dicts from inspect)
//   {type: "merge", id, western: {name, bytes}, cjk: {name, bytes}, settings}
// Messages out:
//   {type: "status", key}                            loading steps (i18n keys)
//   {type: "ready", version, pyodide}
//   {type: "inspected", id, role, info}
//   {type: "suggested", id, suggestion}
//   {type: "progress", id, message}                  pipeline steps
//   {type: "result", id, meta, font, wasmHeapBytes}
//   {type: "error", id, role?, fatal?, error: {kind, message, hint, detail?}}

// One place to change the Pyodide version. Upgrades are tested in CI.
export const PYODIDE_VERSION = "314.0.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const PY_HELPERS = `
import json, traceback
from fontmerge import web

_EXPECTED = ("ConfigError", "FontLoadError", "UnsupportedFontError", "RoutingError",
             "GlyphLimitError", "MergeFailedError", "ValidationFailedError")

def _bytes(data):
    return data.to_bytes() if hasattr(data, "to_bytes") else bytes(data)

def _error(e):
    err = web.error_to_dict(e)
    if err["kind"] not in _EXPECTED:
        err["detail"] = traceback.format_exc()
    return json.dumps({"error": err})

def fm_inspect(data, face_json, name):
    try:
        return json.dumps({"info": web.inspect_bytes(_bytes(data), json.loads(face_json), name)})
    except Exception as e:
        return _error(e)

def fm_suggest(western_json, cjk_json):
    try:
        return json.dumps({"suggestion": web.suggest(json.loads(western_json), json.loads(cjk_json))})
    except Exception as e:
        return _error(e)

def fm_merge(western, cjk, settings_json, progress, western_name, cjk_name):
    try:
        result = web.merge_bytes(_bytes(western), _bytes(cjk), json.loads(settings_json),
                                 progress, western_name=western_name, cjk_name=cjk_name)
    except Exception as e:
        return _error(e), None
    font = result.pop("font")
    return json.dumps(result), font
`;

let pyodide = null;
const ready = init();

async function init() {
  try {
    post({ type: "status", key: "statusLoadingRuntime" });
    const { loadPyodide } = await import(PYODIDE_URL + "pyodide.mjs");
    pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

    post({ type: "status", key: "statusLoadingPackages" });
    await pyodide.loadPackage(["fonttools", "pydantic"]);

    post({ type: "status", key: "statusLoadingTool" });
    const build = await (await fetch("build.json", { cache: "no-cache" })).json();
    const wheel = await (await fetch(build.wheel)).arrayBuffer();
    pyodide.unpackArchive(wheel, "wheel");
    pyodide.runPython(PY_HELPERS);

    post({ type: "ready", version: pyodide.runPython("web.version()"), pyodide: PYODIDE_VERSION });
    return true;
  } catch (e) {
    // Report once and resolve to false: a rejected promise nobody awaits would surface
    // as an uncaught error in the page.
    post({ type: "error", id: null, fatal: true, error: internal(e, "RuntimeLoadError") });
    return false;
  }
}

self.onmessage = async (event) => {
  const msg = event.data;
  if (!(await ready)) return; // the load error has already been posted
  try {
    if (msg.type === "inspect") inspect(msg);
    else if (msg.type === "suggest") suggest(msg);
    else if (msg.type === "merge") {
      // WOFF2 needs brotli; load it only when asked for, so TTF users skip the download.
      if (msg.settings && msg.settings.format === "woff2") await pyodide.loadPackage(["brotli"]);
      merge(msg);
    }
  } catch (e) {
    post({ type: "error", id: msg.id, role: msg.role, error: internal(e, "InternalError") });
  }
};

function callJson(name, ...args) {
  const fn = pyodide.globals.get(name);
  try {
    return JSON.parse(fn(...args));
  } finally {
    fn.destroy();
  }
}

function inspect(msg) {
  const out = callJson("fm_inspect", msg.bytes, JSON.stringify(msg.face ?? null), msg.name);
  if (out.error) post({ type: "error", id: msg.id, role: msg.role, error: out.error });
  else post({ type: "inspected", id: msg.id, role: msg.role, info: out.info });
}

function suggest(msg) {
  const out = callJson("fm_suggest", JSON.stringify(msg.western), JSON.stringify(msg.cjk));
  if (out.error) post({ type: "error", id: msg.id, role: "suggest", error: out.error });
  else post({ type: "suggested", id: msg.id, suggestion: out.suggestion });
}

function merge(msg) {
  const progress = (text) => post({ type: "progress", id: msg.id, message: String(text) });
  const fmMerge = pyodide.globals.get("fm_merge");
  let out = null;
  try {
    out = fmMerge(
      msg.western.bytes,
      msg.cjk.bytes,
      JSON.stringify(msg.settings || {}),
      progress,
      msg.western.name,
      msg.cjk.name,
    );
    const meta = JSON.parse(out.get(0));
    if (meta.error) {
      post({ type: "error", id: msg.id, error: meta.error });
      return;
    }
    const fontProxy = out.get(1);
    const buffer = fontProxy.getBuffer("u8");
    const font = buffer.data.slice(); // copy out of WebAssembly memory
    buffer.release();
    fontProxy.destroy();
    post({ type: "result", id: msg.id, meta, font, wasmHeapBytes: wasmHeapBytes() }, [font.buffer]);
  } finally {
    if (out) out.destroy();
    fmMerge.destroy();
  }
}

function internal(e, kind) {
  return { kind, message: String(e && e.message ? e.message : e), hint: null };
}

function wasmHeapBytes() {
  try {
    const mod = pyodide._module;
    return mod && mod.HEAPU8 ? mod.HEAPU8.buffer.byteLength : null;
  } catch {
    return null;
  }
}

function post(message, transfer) {
  self.postMessage(message, transfer || []);
}
