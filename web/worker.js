// Web Worker: runs Pyodide and the fontmerge package, so the page stays responsive.
//
// Messages in:  {type: "merge", id, western: {name, bytes}, cjk: {name, bytes}, settings}
// Messages out: {type: "status", key}            loading steps (i18n keys)
//               {type: "ready", version}
//               {type: "progress", id, message}  pipeline steps
//               {type: "result", id, meta, font, wasmHeapBytes}
//               {type: "error", id, error: {kind, message, hint}}

// One place to change the Pyodide version. Upgrades are tested in CI.
export const PYODIDE_VERSION = "314.0.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const PY_HELPERS = `
import json, traceback
from fontmerge import web

def fm_merge(western, cjk, settings_json, progress, western_name, cjk_name):
    try:
        result = web.merge_bytes(
            western.to_bytes() if hasattr(western, "to_bytes") else bytes(western),
            cjk.to_bytes() if hasattr(cjk, "to_bytes") else bytes(cjk),
            json.loads(settings_json),
            progress,
            western_name=western_name,
            cjk_name=cjk_name,
        )
    except Exception as e:  # report every failure to the page
        err = web.error_to_dict(e)
        if err["kind"] not in ("ConfigError", "FontLoadError", "UnsupportedFontError",
                               "RoutingError", "GlyphLimitError", "MergeFailedError",
                               "ValidationFailedError"):
            err["detail"] = traceback.format_exc()
        return json.dumps({"error": err}), None
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
  } catch (e) {
    post({
      type: "error",
      id: null,
      fatal: true,
      error: { kind: "RuntimeLoadError", message: String(e && e.message ? e.message : e), hint: null },
    });
    throw e;
  }
}

self.onmessage = async (event) => {
  const msg = event.data;
  if (msg.type !== "merge") return;
  try {
    await ready;
  } catch {
    return; // the load error has already been posted
  }
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
  } catch (e) {
    post({
      type: "error",
      id: msg.id,
      error: { kind: "InternalError", message: String(e && e.message ? e.message : e), hint: null },
    });
  } finally {
    if (out) out.destroy();
    fmMerge.destroy();
  }
};

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
