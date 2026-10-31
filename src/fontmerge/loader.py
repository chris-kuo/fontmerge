"""Font Loader: open a font file and select the face to work on.

Handles single-face files (TTF, OTF, WOFF, WOFF2) and collections (TTC, OTC). A face in a
collection is picked by index or by name; a collection with several faces and no face
given is an error that lists the faces, so the user can choose.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont, TTLibError

from fontmerge.errors import ConfigError, FontLoadError, UnsupportedFontError
from fontmerge.models import FaceInfo, FontSource, OutlineFormat

_COLLECTION_TAG = b"ttcf"


def is_collection(path: Path) -> bool:
    """True when the file starts with the TTC/OTC header tag."""
    with path.open("rb") as f:
        return f.read(4) == _COLLECTION_TAG


def face_info(font: TTFont, index: int = 0) -> FaceInfo:
    name = font.get("name")

    def get(name_id: int) -> str:
        if name is None:
            return ""
        value = name.getDebugName(name_id)
        return value.strip() if value else ""

    return FaceInfo(
        index=index,
        family=get(1),
        subfamily=get(2),
        full_name=get(4),
        postscript_name=get(6),
        typographic_family=get(16) or None,
    )


def list_faces(path: Path) -> list[FaceInfo]:
    """Names of every face in a font file (one entry for a single-face file)."""
    path = _check_path(path)
    try:
        if is_collection(path):
            coll = TTCollection(str(path), lazy=True)
            return [face_info(f, i) for i, f in enumerate(coll.fonts)]
        return [face_info(TTFont(str(path), lazy=True))]
    except (TTLibError, OSError, ValueError, AssertionError) as e:
        raise FontLoadError(f"could not read {path.name}: {e}") from e


def load_font(
    path: Path,
    face: int | str | None = None,
    *,
    allow_variable: bool = False,
    option_name: str = "face",
) -> FontSource:
    """Open ``path`` and return the selected face as a ``FontSource``.

    ``face`` is a 0-based index or a face name (family, full, PostScript or typographic
    family name; case-insensitive). ``option_name`` is the CLI option the user sets
    (e.g. ``--cjk-face``) and is used only in error hints.
    """
    path = _check_path(path)
    collection = is_collection(path)
    faces = list_faces(path)
    index = _select_face(path, faces, face, option_name)

    try:
        font = TTFont(str(path), fontNumber=index if collection else -1)
    except (TTLibError, OSError, ValueError, AssertionError) as e:
        raise FontLoadError(f"could not read {path.name}: {e}") from e

    outline = _outline_format(font, path)
    variable = "fvar" in font
    if variable and not allow_variable:
        raise UnsupportedFontError(
            f"{path.name} is a variable font, which fontmerge does not support yet",
            hint="export a static instance first, e.g. with `fonttools varLib.instancer`",
        )

    return FontSource(
        path=path,
        face_index=index,
        ttfont=font,
        outline=outline,
        is_variable=variable,
        is_collection=collection,
        face=faces[index],
    )


# --------------------------------------------------------------------------------------


def _check_path(path: Path) -> Path:
    path = Path(path).expanduser()
    if not path.exists():
        raise FontLoadError(f"font file not found: {path}")
    if not path.is_file():
        raise FontLoadError(f"not a file: {path}")
    return path


def _describe_faces(faces: list[FaceInfo]) -> str:
    return "; ".join(f"{f.index}: {f.full_name or f.family}" for f in faces)


def _select_face(
    path: Path, faces: list[FaceInfo], face: int | str | None, option_name: str
) -> int:
    if face is None:
        if len(faces) > 1:
            raise ConfigError(
                f"{path.name} contains {len(faces)} faces; choose one",
                hint=f"set {option_name} to an index or name ({_describe_faces(faces)})",
            )
        return 0

    if isinstance(face, int):
        if not 0 <= face < len(faces):
            raise ConfigError(
                f"{path.name} has no face {face} (it has {len(faces)})",
                hint=f"valid faces: {_describe_faces(faces)}",
            )
        return face

    matches = [f.index for f in faces if f.matches(face)]
    if not matches:
        raise ConfigError(
            f"no face named {face!r} in {path.name}",
            hint=f"valid faces: {_describe_faces(faces)}",
        )
    return matches[0]


def _outline_format(font: TTFont, path: Path) -> OutlineFormat:
    if "glyf" in font:
        return "glyf"
    if "CFF " in font:
        return "CFF"
    if "CFF2" in font:
        return "CFF2"
    raise UnsupportedFontError(
        f"{path.name} has no outline glyphs (no glyf, CFF or CFF2 table)",
        hint="bitmap-only and SVG-only fonts are not supported",
    )
