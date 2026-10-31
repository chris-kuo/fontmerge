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
    family: "Family name",
    style: "Style",
    scale: "Western scale",
    scaleHelp: "Leave blank for automatic",
    lineHeight: "Line height",
    lineCjk: "CJK font's",
    lineWestern: "Western font's",
    lineMax: "Larger of both",
    format: "Format",
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
    dropHere: "Drop a font here, or click to choose (.ttf, .otf, .ttc)",
    face: "Face",
    reading: "Reading font…",
    glyphsN: "{n} glyphs",
    charactersN: "{n} characters",
    upmN: "{n} units/em",
    covLatin: "Latin",
    covGreek: "Greek",
    covCyrillic: "Cyrillic",
    covHan: "Han",
    covKana: "Kana",
    covHangul: "Hangul",
    embedding: "Embedding",
    reservedNames: "Reserved names",
    none: "none",
    swap: "Swap the two fonts",
    suggested: "Name, style and scale were suggested from the fonts; edit them freely.",
    rfnWarning: "“{names}” is a Reserved Font Name of a source font. The OFL does not allow it in the name of a merged font.",
    more: "More settings",
    punctuation: "Shared punctuation",
    punctSplit: "Split: ASCII Western, full-width CJK",
    punctWestern: "Western font",
    punctCjk: "CJK font",
    symbols: "Arrows, boxes, shapes",
    fromCjkFont: "CJK font",
    fromWesternFont: "Western font",
    outline: "Outline format",
    outlineAuto: "Same as the CJK font",
    baselineShift: "Western baseline shift",
    fontVersion: "Version",
    vendor: "Vendor ID",
    includeHangul: "Include Korean (Hangul)",
    fallback: "Fill gaps from the other font",
    strict: "Treat warnings as errors",
    overrides: "Force ranges to a font (one per line)",
    overridesHelp: "U+2018-U+201D=cjk",
    cancel: "Cancel",
    statusCancelled: "Cancelled. Reloading the runtime…",
    elapsed: "{s} s",
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
    family: "字族名稱",
    style: "樣式",
    scale: "西文縮放比例",
    scaleHelp: "留空則自動計算",
    lineHeight: "行高",
    lineCjk: "使用中日文字型",
    lineWestern: "使用西文字型",
    lineMax: "取兩者較大值",
    format: "格式",
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
    dropHere: "將字型拖放到這裡，或點按選擇（.ttf、.otf、.ttc）",
    face: "字型",
    reading: "正在讀取字型…",
    glyphsN: "{n} 個字符",
    charactersN: "{n} 個字元",
    upmN: "每 em {n} 單位",
    covLatin: "拉丁",
    covGreek: "希臘",
    covCyrillic: "西里爾",
    covHan: "漢字",
    covKana: "假名",
    covHangul: "韓文",
    embedding: "嵌入權限",
    reservedNames: "保留名稱",
    none: "無",
    swap: "交換兩個字型",
    suggested: "字族名稱、樣式與縮放比例是依字型自動建議的，可自由修改。",
    rfnWarning: "「{names}」是來源字型的保留字型名稱（Reserved Font Name），OFL 授權不允許合併後的字型使用。",
    more: "更多設定",
    punctuation: "共用標點",
    punctSplit: "分開：半形西文、全形中日",
    punctWestern: "西文字型",
    punctCjk: "中日文字型",
    symbols: "箭頭、框線、圖形",
    fromCjkFont: "中日文字型",
    fromWesternFont: "西文字型",
    outline: "外框格式",
    outlineAuto: "與中日文字型相同",
    baselineShift: "西文基線位移",
    fontVersion: "版本",
    vendor: "廠商代碼",
    includeHangul: "包含韓文（諺文）",
    fallback: "缺字時由另一個字型補上",
    strict: "將警告視為錯誤",
    overrides: "強制指定範圍使用的字型（每行一項）",
    overridesHelp: "U+2018-U+201D=cjk",
    cancel: "取消",
    statusCancelled: "已取消，正在重新載入執行環境…",
    elapsed: "{s} 秒",
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
  for (const el of root.querySelectorAll("[data-i18n-title]")) {
    el.title = t(lang, el.dataset.i18nTitle);
    el.setAttribute("aria-label", el.title);
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

// Chinese text for the Inspector's font checks; English uses the message from Python.
const ISSUES_ZH = {
  "role-coverage:western": "這個字型缺少大部分基本拉丁字母，不適合當西文字型。",
  "role-coverage:cjk": "這個字型的漢字與假名很少，不太像中日文字型。",
  "license-reserved-names": "授權保留了字型名稱 {names}，合併後的字型不能使用這些名稱。",
  "license-unknown": "沒有授權資訊，請確認你有權修改這個字型。",
  "license-restricted": "嵌入權限受限；散布合併後的字型前，請確認授權允許修改。",
  "license-no-subsetting": "嵌入權限禁止擷取子集，因此無法合併。",
  "license-bitmap-only": "嵌入權限只允許點陣嵌入。",
};

export function issueText(lang, issue, role, profile) {
  if (lang !== "zh-Hant") return issue.message;
  const template = ISSUES_ZH[`${issue.code}:${role}`] ?? ISSUES_ZH[issue.code];
  if (!template) return issue.message;
  const names = (profile.reserved_font_names || []).map((n) => `「${n}」`).join("、");
  return template.replace("{names}", names);
}
