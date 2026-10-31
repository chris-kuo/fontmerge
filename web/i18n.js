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
    technicalDetails: "Technical details",
    retry: "Try again",
    reportBug: "Report a problem",
    downloadReport: "Report (JSON)",
    preview: "Preview",
    previewSize: "Size",
    previewReset: "Reset text",
    previewText: "Sample text (edit freely)",
    horizontal: "Horizontal",
    vertical: "Vertical",
    previewSample: "The quick brown fox jumps over the lazy dog. 0123456789\n我們在 Taipei 吃了 3 碗 Beef Noodles。\n東京で Typography を学ぶ「こんにちは」\n你好 nǐ hǎo，媽 mā 麻 má 馬 mǎ 罵 mà！",
    previewMissing: "{count} characters in the sample are not in the merged font. They are underlined in red and drawn in a fallback font: {chars}",
    errorsN: "Errors ({n})",
    warningsN: "Warnings ({n})",
    notesN: "Notes ({n})",
    errConfigError: "There is a problem with the settings",
    errFontLoadError: "A font could not be read",
    errUnsupportedFontError: "This font is not supported",
    errRoutingError: "Characters could not be assigned",
    errGlyphLimitError: "Too many glyphs for one font",
    errMergeFailedError: "The fonts could not be merged",
    errValidationFailedError: "The merged font did not pass validation, so it was not saved",
    errRuntimeLoadError: "The Python runtime could not be loaded",
    errRuntimeHint: "The page downloads Pyodide from cdn.jsdelivr.net. Check your connection; some networks, firewalls or content blockers block it.",
    errInternal: "Something unexpected went wrong",
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
    technicalDetails: "技術細節",
    retry: "重試",
    reportBug: "回報問題",
    downloadReport: "報告（JSON）",
    preview: "預覽",
    previewSize: "大小",
    previewReset: "重設文字",
    previewText: "範例文字（可自由修改）",
    horizontal: "橫排",
    vertical: "直排",
    previewSample: "我們在 Taipei 吃了 3 碗 Beef Noodles。\n東京で Typography を学ぶ「こんにちは」\n你好 nǐ hǎo，媽 mā 麻 má 馬 mǎ 罵 mà！\nThe quick brown fox jumps over the lazy dog. 0123456789",
    previewMissing: "範例中有 {count} 個字元不在合併後的字型裡，以紅色底線標示並用備用字型顯示：{chars}",
    errorsN: "錯誤（{n}）",
    warningsN: "警告（{n}）",
    notesN: "備註（{n}）",
    errConfigError: "設定有問題",
    errFontLoadError: "無法讀取字型",
    errUnsupportedFontError: "不支援這個字型",
    errRoutingError: "無法分配字元",
    errGlyphLimitError: "字符數超過單一字型的上限",
    errMergeFailedError: "無法合併字型",
    errValidationFailedError: "合併後的字型未通過驗證，因此沒有輸出",
    errRuntimeLoadError: "無法載入 Python 執行環境",
    errRuntimeHint: "本頁會從 cdn.jsdelivr.net 下載 Pyodide。請檢查網路連線；有些網路、防火牆或內容封鎖工具會擋住它。",
    errInternal: "發生了預期外的錯誤",
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

// Report and font-check wording. English uses Python's message unless EN overrides it;
// Chinese fills each template from the issue's params.
const EN = {
  "ots-skipped": "The browser version skips the OTS browser-compatibility check; the command-line tool runs it.",
};

const ZH = {
  "role-coverage:western": "西文字型「{font}」缺少 {missing} 個基本拉丁字母，不適合當西文字型。",
  "role-coverage:cjk": "中日文字型「{font}」只有 {han} 個漢字和 {kana} 個假名，不太像中日文字型。",
  "license-reserved-names": "「{font}」的授權保留了字型名稱 {names}，合併後的字型不能使用這些名稱。",
  "license-unknown": "「{font}」沒有授權資訊，請確認你有權修改這個字型。",
  "license-restricted": "嵌入權限受限；散布合併後的字型前，請確認授權允許修改。",
  "license-no-subsetting": "嵌入權限禁止擷取子集，因此無法合併。",
  "license-bitmap-only": "嵌入權限只允許點陣嵌入。",
  "glyph-limit": "字符數 {count} 超過 OpenType 的上限 {limit}。",
  notdef: "第一個字符必須是 .notdef。",
  upm: "每 em 單位數 {upm} 超出允許範圍。",
  unmapped: "{count} 個預定來自{source}的字元遺失了：{examples}{more}",
  unplanned: "{count} 個字元不在分配計畫中：{examples}{more}",
  "wrong-source": "{count} 個字元與{source}裡的字符不一致：{examples}{more}",
  "empty-glyph": "{count} 個可見字元的字符是空白的：{examples}{more}",
  "line-metrics": "行距度量看起來有誤（上緣 {ascender}、下緣 {descender}）。",
  "line-metrics-differ": "hhea 與 OS/2 的行距度量不同，不同程式顯示的行距可能不一致。",
  clipping: "有字符最高到 {high}、最低到 {low}，超出 Windows 的裁切範圍（{win_ascent}／−{win_descent}），在 Windows 上會被截掉。",
  "tall-glyphs": "{count} 個西文字元高於上緣（{ascender}），可能碰到上一行：{examples}{more}",
  vertical: "部分字符缺少直排度量。",
  names: "字型名稱資料不完整或不符合規定。",
  ots: "OTS 檢查未通過，瀏覽器可能拒絕使用這個字型。",
  "ots-skipped": "瀏覽器版不執行 OTS 瀏覽器相容性檢查；命令列工具會執行。",
  "not-routed": "因為關閉了缺字補字，有 {count} 個字元被略過。",
};

function fill(template, params, lang) {
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    const value = params[key];
    if (key === "more") return value ? (lang === "zh-Hant" ? ` 等，另有 ${value} 個` : ` and ${value} more`) : "";
    if (key === "source") return value === "western" ? "西文字型" : "中日文字型";
    if (key === "names") return (value || []).map((n) => `「${n}」`).join("、");
    return value === undefined || value === null ? "" : String(value);
  });
}

// role: "western" | "cjk" for font checks shown under a font; report issues carry it in params.
export function issueText(lang, issue, role) {
  const params = issue.params || {};
  const r = role || params.role;
  if (lang !== "zh-Hant") return EN[issue.code] || issue.message;
  const template = ZH[`${issue.code}:${r}`] ?? ZH[issue.code];
  return template ? fill(template, params, lang) : issue.message;
}

export function errorTitle(lang, kind) {
  const key = `err${kind}`;
  const known = STRINGS.en[key] !== undefined;
  return t(lang, known ? key : "errInternal");
}
