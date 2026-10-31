# fontmerge

Merge two fonts into one: Latin and other Western scripts from a **Western font**,
Chinese/Japanese scripts from a **CJK font**.

> Work in progress. Built in stages; see the status table below.

## Target merge

The first real merge this tool is being built for:

| Role | Font | Notes |
| --- | --- | --- |
| Western | Literata Light | Stem weight matches Iansui; covers pinyin, Greek, Cyrillic |
| CJK | Iansui Regular | Traditional Chinese, with kana and Bopomofo |

Adjustment: Literata's glyphs are scaled to 96% (`western_scale = 0.96`) so its
x-height (0.505 em) sits closer to Iansui's (0.468 em) while capitals stay close
(0.673 vs 0.695 em). The automatic scale (`auto_western_scale`) arrives at the same value.

## Development

```bash
pip install -e ".[dev,woff2]"
pytest
ruff check . && ruff format --check .
mypy            # if mypy runs in its own env: mypy --python-executable "$(which python)"
```

Unit tests use tiny fonts generated in code (`tests/fontfactory.py`). Tests marked
`realfont` also run on two real OFL fonts in `tests/realfonts/`.

## Layout

```
src/fontmerge/
  models.py     shared data models (config + runtime contracts between modules)
  errors.py     error types, each with a user-facing hint
  loader.py     open TTF/OTF/WOFF/TTC, pick a collection face, reject variable fonts
  inspector.py  read a FontProfile (UPM, coverage, metrics, em box, licence) + role checks
  unicode_ranges.py  Unicode blocks -> routing categories
  router.py     decide which font supplies each codepoint (AssignmentPlan)
  subset.py     cut each font to its assigned codepoints, keeping feature-reachable glyphs
  normalize.py  match UPM and outline format, scale/shift Western glyphs, add vertical metrics
tests/
  fontfactory.py   builds test fonts (Latin TTF, CJK OTF, TTC, variable)
  conftest.py      pytest fixtures for those fonts
  realfonts/       real fonts for tests marked `realfont` (Literata Light, Iansui)
```

## Stages

| Stage | Modules | Status |
| --- | --- | --- |
| 0 | Scaffold, models, errors, test fonts | Done |
| 1 | Loader, Inspector | Done |
| 2 | Script Router | Done |
| 3 | Subsetter | Done |
| 4 | Normalizer | Done |
| 5 | Merger, Metadata | |
| 6 | Validator, Writer, Preview | |
| 7 | Orchestrator, CLI | |
