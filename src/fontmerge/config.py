"""Config: build a validated ``MergeConfig`` from a TOML file and command-line values.

Command-line values override the file. Relative paths in the file are resolved from
the file's own folder, so a config can sit next to its fonts. Validation problems
become one ``ConfigError`` that names each bad setting.

Example file::

    [western]
    path = "Literata-Light.ttf"

    [cjk]
    path = "Iansui-Regular.ttf"

    [output]
    path = "out/IansuiLiterata-Light.ttf"
    preview = "html"

    [naming]
    family = "Iansui Literata"
    style = "Light"

    [normalize]
    western_scale = 0.96

    [[routing.overrides]]
    start = "U+2018"
    end = "U+201D"
    source = "cjk"
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fontmerge.errors import ConfigError
from fontmerge.models import MergeConfig

# (section, key) pairs whose values are paths, resolved relative to the config file.
_PATH_KEYS = (("western", "path"), ("cjk", "path"), ("output", "path"))

_HINTS = {
    "western": "set --western or [western] path",
    "cjk": "set --cjk or [cjk] path",
    "output": "set -o/--output or [output] path",
    "naming": "set --family or [naming] family",
}


def load_config(cli_values: Mapping[str, Any], config_path: Path | None = None) -> MergeConfig:
    """``cli_values`` is nested like the file, e.g. ``{"naming": {"family": "X"}}``.

    Keys whose value is ``None`` are ignored, so unset command-line options never
    override the file.
    """
    data: dict[str, Any] = {}
    if config_path is not None:
        data = read_toml(config_path)
        _resolve_paths(data, config_path.parent)
    merged = _deep_merge(data, _drop_none(cli_values))

    missing = [key for key in ("western", "cjk", "output", "naming") if key not in merged]
    if missing:
        raise ConfigError(
            "missing required settings: " + ", ".join(missing),
            hint="; ".join(_HINTS[k] for k in missing),
        )
    try:
        return MergeConfig.model_validate(merged)
    except ValidationError as e:
        raise ConfigError("invalid settings: " + _describe(e)) from e


def read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name} is not valid TOML: {e}") from e


def parse_face(value: str | None) -> int | str | None:
    """A face given on the command line: digits are an index, anything else a name."""
    if value is None:
        return None
    return int(value) if value.strip().isdigit() else value


def parse_override(text: str) -> dict[str, str]:
    """``"U+2018-U+201D=cjk"`` or ``"U+00B7=western"`` -> override dict."""
    try:
        span, source = text.rsplit("=", 1)
    except ValueError:
        raise ConfigError(
            f"bad override {text!r}", hint='use START-END=SOURCE, e.g. "U+2018-U+201D=cjk"'
        ) from None
    start, _, end = span.partition("-")
    return {"start": start.strip(), "end": (end or start).strip(), "source": source.strip()}


# --------------------------------------------------------------------------------------


def _resolve_paths(data: dict[str, Any], base: Path) -> None:
    for section, key in _PATH_KEYS:
        value = data.get(section, {}).get(key)
        if isinstance(value, str):
            p = Path(value).expanduser()
            data[section][key] = os.path.normpath(p if p.is_absolute() else (base / p))


def _drop_none(values: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in values.items():
        if isinstance(v, Mapping):
            nested = _drop_none(v)
            if nested:
                out[k] = nested
        elif v is not None:
            out[k] = v
    return out


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _describe(error: ValidationError) -> str:
    parts = []
    for err in error.errors():
        where = ".".join(str(p) for p in err["loc"]) or "config"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)
