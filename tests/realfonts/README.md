# Real fonts for tests

Tests marked `realfont` run against real fonts placed in this folder. They are skipped
when a font is missing. Both fonts are under the SIL Open Font License, which allows
redistribution.

| File | Role | Source | Licence |
| --- | --- | --- | --- |
| `Literata-Light.ttf` | Western | The Literata Project Authors | SIL OFL 1.1 |
| `Iansui-Regular.ttf` | CJK (Traditional Chinese) | Iansui project | SIL OFL 1.1 |

To use a different folder, set `FONTMERGE_REAL_FONTS=/path/to/fonts`.
