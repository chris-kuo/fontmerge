"""Previewer: show the merged font on mixed sample text.

* ``.html``: a page that loads the font with ``@font-face``, so a browser shapes the
  text for real (ligatures, kerning, vertical forms). Needs no extra packages.
* ``.png``: a picture rendered with Pillow (``pip install pillow``). Vertical text is
  included when Pillow has libraqm.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

from fontTools.ttLib import TTFont

from fontmerge.errors import ConfigError

DEFAULT_SAMPLES: tuple[str, ...] = (
    "我們在 Taipei 吃了 3 碗 Beef Noodles。",
    "東京で Typography を学ぶ「こんにちは」2026年",
    "你好 nǐ hǎo，媽 mā 麻 má 馬 mǎ 罵 mà！",
    "Café · Straße · Αθήνα · Москва · “quotes” — 1½",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789",
    "永和九年，歲在癸丑，暮春之初，會于會稽山陰之蘭亭。",
)
DEFAULT_VERTICAL: tuple[str, ...] = ("縱排測試：「你好」。", "東京で Typography を学ぶ")


def render_preview(
    font_path: Path,
    out: Path,
    samples: tuple[str, ...] = DEFAULT_SAMPLES,
    vertical: tuple[str, ...] = DEFAULT_VERTICAL,
) -> Path:
    suffix = out.suffix.lower()
    if suffix == ".html":
        return _render_html(font_path, out, samples, vertical)
    if suffix == ".png":
        return _render_png(font_path, out, samples, vertical)
    raise ConfigError(f"preview must be .html or .png, not {out.suffix!r}")


def _family(font_path: Path) -> str:
    name = TTFont(str(font_path), lazy=True)["name"]
    return name.getDebugName(4) or font_path.stem


def _render_html(
    font_path: Path, out: Path, samples: tuple[str, ...], vertical: tuple[str, ...]
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    src = Path(os.path.relpath(font_path.resolve(), out.parent.resolve())).as_posix()
    title = html.escape(_family(font_path))
    lines = "\n".join(f"    <p>{html.escape(s)}</p>" for s in samples)
    cols = "\n".join(f"    <p>{html.escape(s)}</p>" for s in vertical)
    page = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{title} preview</title>
<style>
  @font-face {{ font-family: "Merged Preview"; src: url("{html.escape(src)}"); }}
  body {{ margin: 32px; background: #fff; color: #111; font-family: system-ui, sans-serif; }}
  h1 {{ font-size: 15px; font-weight: 600; color: #555; }}
  .sample {{ font-family: "Merged Preview"; font-size: 40px; }}
  .sample p {{ margin: 0; }}
  .vertical {{ writing-mode: vertical-rl; height: 520px; margin-top: 32px; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #111; color: #eee; }} }}
</style>
</head>
<body>
  <h1>{title}: horizontal text at the font's own line height</h1>
  <div class="sample">
{lines}
  </div>
  <h1>Vertical text</h1>
  <div class="sample vertical">
{cols}
  </div>
</body>
</html>
"""
    out.write_text(page, encoding="utf-8")
    return out


def _render_png(
    font_path: Path, out: Path, samples: tuple[str, ...], vertical: tuple[str, ...]
) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont, features
    except ImportError as e:
        raise ConfigError("PNG previews need Pillow", hint="pip install pillow") from e

    size, margin = 44, 32
    raqm = bool(features.check("raqm"))
    layout = ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC
    font = ImageFont.truetype(str(font_path), size, layout_engine=layout)
    label = ImageFont.truetype(str(font_path), 20)
    ascent, descent = font.getmetrics()
    line = ascent + descent

    # Size the canvas from the measured text, so nothing is cut off.
    widest = max((font.getlength(s) for s in samples), default=0)
    width = max(1500, int(widest) + 2 * margin)
    columns = vertical if raqm else ()
    tallest = max((font.getlength(c, direction="ttb") for c in columns), default=0)
    vertical_h = int(tallest) + 40 + margin if columns else 0
    height = margin * 2 + 40 + line * len(samples) + (30 + vertical_h if vertical_h else 0)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.text((margin, margin), f"{_family(font_path)} preview", font=label, fill=(90, 90, 90))
    y = margin + 40
    for s in samples:
        draw.text((margin, y), s, font=font, fill="black")
        y += line
    if columns:
        y += 30
        draw.text((margin, y), "Vertical text", font=label, fill=(90, 90, 90))
        x = width - margin - size
        for col in columns:
            draw.text((x, y + 40), col, font=font, fill="black", direction="ttb", features=["vert"])
            x -= int(size * 1.3)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
