# fontmerge

Merge two fonts into one: Latin and other Western scripts from a **Western font**,
Chinese/Japanese scripts from a **CJK font**.

> Work in progress. Built in stages; see the status table below.

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
tests/
  fontfactory.py   builds test fonts (Latin TTF, CJK OTF, TTC, variable)
  conftest.py      pytest fixtures for those fonts
  realfonts/       real fonts for tests marked `realfont` (Averia Serif Libre, Iansui)
```

## Stages

| Stage | Modules | Status |
| --- | --- | --- |
| 0 | Scaffold, models, errors, test fonts | Done |
| 1 | Loader, Inspector | Done |
| 2 | Script Router | Done |
| 3 | Subsetter | |
| 4 | Normalizer | |
| 5 | Merger, Metadata | |
| 6 | Validator, Writer, Preview | |
| 7 | Orchestrator, CLI | |
