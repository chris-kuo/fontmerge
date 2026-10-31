// UI text in English and Traditional Chinese (Taiwan usage).
// Elements carry data-i18n="key" (text) or data-i18n-placeholder="key".

export const STRINGS = {
  en: {
    title: "fontmerge",
    tagline: "Merge a Western font and a Chinese/Japanese font into one font file.",
    privacy: "Fonts are processed on your device. They are never uploaded.",
    language: "中文",
    westernFont: "Western font",
    westernHelp: "Latin, Greek, Cyrillic",
    cjkFont: "CJK font",
    cjkHelp: "Chinese and Japanese",
    chooseFile: "Choose a .ttf, .otf or .ttc file",
    family: "Family name",
    style: "Style",
    scale: "Western scale",
    scaleHelp: "Leave blank for automatic",
    lineHeight: "Line height",
    lineCjk: "CJK font's",
    lineWestern: "Western font's",
    lineMax: "Larger of both",
    format: "Format",
    cjkFace: "Face in collection",
    cjkFaceHelp: "Index or name, for a .ttc file",
    merge: "Merge fonts",
    merging: "Merging…",
    download: "Download",
    statusLoadingRuntime: "Loading the Python runtime (about 20 MB the first time, then cached)…",
    statusLoadingPackages: "Loading fontTools and Pydantic…",
    statusLoadingTool: "Loading fontmerge…",
    statusReady: "Ready.",
    statusRuntimeFailed: "Could not load the Python runtime.",
    statusNeedFiles: "Choose both fonts first.",
    statusDone: "Done in {seconds} s.",
    statusError: "The merge failed.",
    progress: "Progress",
    result: "Result",
    glyphs: "Glyphs",
    characters: "Characters",
    fromWestern: "from the Western font",
    fromCjk: "from the CJK font",
    time: "Merge time",
    memory: "Memory used",
    issues: "Validation",
    noIssues: "No issues.",
    hint: "Hint",
    footer: "fontmerge {version} · built from {commit} · MIT licence · fonts keep their own licences",
    licenceNote: "You are responsible for having the right to modify the fonts you merge.",
  },
  "zh-Hant": {
    title: "fontmerge",
    tagline: "將西文字型與中日文字型合併成一個字型檔。",
    privacy: "字型只在你的裝置上處理，不會上傳。",
    language: "English",
    westernFont: "西文字型",
    westernHelp: "拉丁、希臘、西里爾字母",
    cjkFont: "中日文字型",
    cjkHelp: "中文與日文",
    chooseFile: "選擇 .ttf、.otf 或 .ttc 檔案",
    family: "字族名稱",
    style: "樣式",
    scale: "西文縮放比例",
    scaleHelp: "留空則自動計算",
    lineHeight: "行高",
    lineCjk: "使用中日文字型",
    lineWestern: "使用西文字型",
    lineMax: "取兩者較大值",
    format: "格式",
    cjkFace: "字型集合中的字型",
    cjkFaceHelp: ".ttc 檔適用：輸入編號或名稱",
    merge: "合併字型",
    merging: "合併中…",
    download: "下載",
    statusLoadingRuntime: "正在載入 Python 執行環境（首次約 20 MB，之後會快取）…",
    statusLoadingPackages: "正在載入 fontTools 與 Pydantic…",
    statusLoadingTool: "正在載入 fontmerge…",
    statusReady: "準備就緒。",
    statusRuntimeFailed: "無法載入 Python 執行環境。",
    statusNeedFiles: "請先選擇兩個字型。",
    statusDone: "完成，耗時 {seconds} 秒。",
    statusError: "合併失敗。",
    progress: "進度",
    result: "結果",
    glyphs: "字符數",
    characters: "字元數",
    fromWestern: "來自西文字型",
    fromCjk: "來自中日文字型",
    time: "合併耗時",
    memory: "記憶體用量",
    issues: "驗證結果",
    noIssues: "沒有問題。",
    hint: "提示",
    footer: "fontmerge {version} · 版本 {commit} · MIT 授權 · 字型沿用其原有授權",
    licenceNote: "請確認你有權修改所合併的字型。",
  },
};

// Progress steps printed by pipeline.run, in order of appearance.
const STEPS_ZH = [
  ["Loading fonts", "載入字型"],
  ["Inspecting fonts", "檢查字型"],
  ["Routing characters", "分配字元"],
  ["Subsetting", "擷取子集"],
  ["Normalizing", "調整尺寸與格式"],
  ["Merging", "合併"],
  ["Writing names and metrics", "寫入名稱與度量"],
  ["Validating", "驗證"],
  ["Writing files", "寫出檔案"],
  ["Rendering preview", "產生預覽"],
  ["Done", "完成"],
];

export function detectLanguage() {
  try {
    const saved = localStorage.getItem("fontmerge.lang");
    if (saved && saved in STRINGS) return saved;
  } catch {
    // storage unavailable: fall through to the browser language
  }
  const langs = navigator.languages || [navigator.language || "en"];
  return langs.some((l) => l.toLowerCase().startsWith("zh")) ? "zh-Hant" : "en";
}

export function saveLanguage(lang) {
  try {
    localStorage.setItem("fontmerge.lang", lang);
  } catch {
    // not fatal
  }
}

export function t(lang, key, vars = {}) {
  const text = (STRINGS[lang] && STRINGS[lang][key]) ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ""));
}

export function applyLanguage(lang, root = document) {
  document.documentElement.lang = lang === "zh-Hant" ? "zh-Hant" : "en";
  for (const el of root.querySelectorAll("[data-i18n]")) {
    el.textContent = t(lang, el.dataset.i18n);
  }
  for (const el of root.querySelectorAll("[data-i18n-placeholder]")) {
    el.placeholder = t(lang, el.dataset.i18nPlaceholder);
  }
}

// "[  1.2s] Subsetting (1,147 Western + ...)" -> localized step name, details kept.
export function translateProgress(lang, message) {
  if (lang !== "zh-Hant") return message;
  const m = message.match(/^(\[[^\]]*\]\s*)(.*)$/);
  const prefix = m ? m[1] : "";
  const body = m ? m[2] : message;
  for (const [en, zh] of STEPS_ZH) {
    if (body.startsWith(en)) return prefix + zh + body.slice(en.length);
  }
  return message;
}
