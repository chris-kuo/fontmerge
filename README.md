# fontmerge

[![CI](https://github.com/chris-kuo/fontmerge/actions/workflows/ci.yml/badge.svg)](https://github.com/chris-kuo/fontmerge/actions/workflows/ci.yml)

**Use it in your browser: <https://chris-kuo.github.io/fontmerge/>** (English and 繁體中文).
Fonts are merged on your own device and never uploaded.

Merge two fonts into one: Latin and other Western scripts from a **Western font**,
Chinese/Japanese scripts from a **CJK font**.

Design notes: [docs/design.md](docs/design.md) (architecture, module interfaces) and
[docs/font-selection.md](docs/font-selection.md) (why Literata Light + Iansui, and the settings used).
Web app: [docs/webapp-plan.md](docs/webapp-plan.md) (how it runs in the browser, deployment).

## Install

```bash
pip install -e .                    # core: fontTools + pydantic
pip install -e ".[woff2,preview,ots]"   # optional: WOFF2 output, PNG previews, OTS check
```

## Usage

```bash
fontmerge --western Literata-Light.ttf --cjk Iansui-Regular.ttf \
          -o IansuiLiterata-Light.ttf --family "Iansui Literata" --style Light \
          --scale 0.96 --preview html
```

Or put the settings in a TOML file (paths are relative to the file) and run:

```bash
fontmerge -c examples/iansui-literata.toml
```

Command-line options override the file. `python -m fontmerge` works too.

Each run writes the font, a `.report.json` with the validation results, and
optionally a preview (`.preview.html` or `.preview.png`). A font with validation
errors is not written; `--strict` also refuses warnings.

To see what fontmerge makes of a font, or to list the faces in a `.ttc`:

```bash
fontmerge inspect Iansui-Regular.ttf
fontmerge inspect NotoSansCJK.ttc --face "Noto Sans CJK JP"
```

### Main options

| Option | Config key | Default | What it does |
| --- | --- | --- | --- |
| `--western-face`, `--cjk-face` | `[western] face` | | Face index or name in a `.ttc` |
| `--format ttf/otf/woff2` | `[output] formats` | from `-o` suffix | Also write these formats |
| `--scale 0.96` | `[normalize] western_scale` | automatic | Size of Western glyphs next to CJK |
| `--baseline-shift N` | `[normalize] western_baseline_shift` | 0 | Move Western glyphs up/down |
| `--outline` | `[normalize] target_outline` | the CJK font's | `glyf` (TrueType) or `CFF` |
| `--line-height` | `[metrics] line_height` | `cjk` | `cjk`, `western`, `average` or `max` |
| `--punctuation` | `[routing] punctuation` | `split` | Who supplies quotes, dashes, middle dot |
| `--symbols` | `[routing] symbols` | `cjk` | Who supplies arrows, boxes, shapes |
| `--include-hangul` | `[routing] include_hangul` | off | Keep Korean from the CJK font |
| `--no-fallback` | `[routing] fallback` | on | Leave out characters the preferred font lacks |
| `--override U+2018-U+201D=cjk` | `[[routing.overrides]]` | | Force a range to one font |

Run `fontmerge merge --help` for the full list.

## How it works

Each stage is one module, passing typed objects (see `models.py`) to the next:

| Stage | Module | Does |
| --- | --- | --- |
| Load | `loader.py` | Open TTF/OTF/WOFF/TTC, pick a collection face, reject variable fonts |
| Inspect | `inspector.py` | Read UPM, coverage, metrics, em box, licence; flag unsuitable fonts |
| Route | `router.py`, `unicode_ranges.py` | Decide which font supplies each character |
| Subset | `subset.py` | Cut each font to its characters, keeping feature-reachable glyphs |
| Normalize | `normalize.py` | Match UPM and outlines, scale/shift Western glyphs, add vertical metrics |
| Merge | `merge.py` | Combine the fonts (CJK as base), rename clashing glyphs |
| Metadata | `metadata.py` | Names, line metrics, style bits, embedding, licence |
| Validate | `validate.py` | Coverage, source of every character, metrics, names, OTS |
| Write | `writer.py`, `preview.py` | Font files, JSON report, preview |
| Run | `pipeline.py`, `config.py`, `cli.py` | Config loading, orchestration, command line |

## Example merge: Iansui Literata Light

| Role | Font | Notes |
| --- | --- | --- |
| Western | Literata Light | Stem weight matches Iansui; covers pinyin, Greek, Cyrillic |
| CJK | Iansui Regular | Traditional Chinese, with kana and Bopomofo |
| Output | Iansui Literata Light | Line height from Iansui (940 / -180 / 0 = 1.12 em) |

Literata's glyphs are scaled to 96% so its x-height (0.505 em) sits closer to
Iansui's (0.468 em) while capitals stay close (0.673 vs 0.695 em); the automatic
scale arrives at the same value. Settings: `examples/iansui-literata.toml`.

## Development

```bash
pip install -e ".[dev,woff2,preview,ots]"
pytest
ruff check . && ruff format --check .
mypy            # if mypy runs in its own env: mypy --python-executable "$(which python)"
```

Unit tests use tiny fonts generated in code (`tests/fontfactory.py`). Tests marked
`realfont` also run on two real OFL fonts in `tests/realfonts/` (Literata Light,
Iansui), including a full command-line merge.

## Licence

The fontmerge code and documentation are under the [MIT License](LICENSE).

The test fonts in `tests/realfonts/` (Literata Light, Iansui) are under the
[SIL Open Font License 1.1](tests/realfonts/OFL.txt), not MIT.

Fonts you make with the tool are governed by the licences of the fonts you merge, not
by this repository's licence. For OFL fonts this means the merged font is also OFL and
must not use either source's Reserved Font Names; fontmerge writes both licence notices
into the merged font and refuses reserved names.
