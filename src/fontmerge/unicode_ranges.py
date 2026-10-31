"""Unicode blocks grouped into the categories the Script Router routes by.

Each block maps to a ``Category``. The Router turns a category into a preferred source
font, using the routing config for the categories that are configurable
(punctuation, symbols, Hangul).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    WESTERN = "western"
    """Latin, Greek, Cyrillic and their marks and symbols: always the Western font."""
    CJK = "cjk"
    """Han, kana, Bopomofo, CJK punctuation, full-width forms: always the CJK font."""
    HANGUL = "hangul"
    """Korean: the CJK font when ``include_hangul`` is on, otherwise left out."""
    PUNCTUATION = "punctuation"
    """Characters both scripts use with different shapes: follows the punctuation policy."""
    SYMBOL = "symbol"
    """Box drawing, arrows, shapes, dingbats: follows the ``symbols`` setting."""
    OTHER = "other"
    """Any other script: the Western font if it has it, else the CJK font."""


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    name: str
    category: Category


_C = Category

# Sorted by start; non-overlapping. Unlisted codepoints are Category.OTHER.
BLOCKS: tuple[Block, ...] = (
    Block(0x0000, 0x007F, "Basic Latin", _C.WESTERN),
    Block(0x0080, 0x00FF, "Latin-1 Supplement", _C.WESTERN),
    Block(0x0100, 0x017F, "Latin Extended-A", _C.WESTERN),
    Block(0x0180, 0x024F, "Latin Extended-B", _C.WESTERN),
    Block(0x0250, 0x02AF, "IPA Extensions", _C.WESTERN),
    Block(0x02B0, 0x02FF, "Spacing Modifier Letters", _C.WESTERN),
    Block(0x0300, 0x036F, "Combining Diacritical Marks", _C.WESTERN),
    Block(0x0370, 0x03FF, "Greek and Coptic", _C.WESTERN),
    Block(0x0400, 0x04FF, "Cyrillic", _C.WESTERN),
    Block(0x0500, 0x052F, "Cyrillic Supplement", _C.WESTERN),
    Block(0x1100, 0x11FF, "Hangul Jamo", _C.HANGUL),
    Block(0x1AB0, 0x1AFF, "Combining Diacritical Marks Extended", _C.WESTERN),
    Block(0x1C80, 0x1C8F, "Cyrillic Extended-C", _C.WESTERN),
    Block(0x1D00, 0x1D7F, "Phonetic Extensions", _C.WESTERN),
    Block(0x1D80, 0x1DBF, "Phonetic Extensions Supplement", _C.WESTERN),
    Block(0x1DC0, 0x1DFF, "Combining Diacritical Marks Supplement", _C.WESTERN),
    Block(0x1E00, 0x1EFF, "Latin Extended Additional", _C.WESTERN),
    Block(0x1F00, 0x1FFF, "Greek Extended", _C.WESTERN),
    Block(0x2000, 0x206F, "General Punctuation", _C.PUNCTUATION),
    Block(0x2070, 0x209F, "Superscripts and Subscripts", _C.WESTERN),
    Block(0x20A0, 0x20CF, "Currency Symbols", _C.WESTERN),
    Block(0x20D0, 0x20FF, "Combining Diacritical Marks for Symbols", _C.WESTERN),
    Block(0x2100, 0x214F, "Letterlike Symbols", _C.WESTERN),
    Block(0x2150, 0x218F, "Number Forms", _C.WESTERN),
    Block(0x2190, 0x21FF, "Arrows", _C.SYMBOL),
    Block(0x2200, 0x22FF, "Mathematical Operators", _C.WESTERN),
    Block(0x2300, 0x23FF, "Miscellaneous Technical", _C.SYMBOL),
    Block(0x2460, 0x24FF, "Enclosed Alphanumerics", _C.SYMBOL),
    Block(0x2500, 0x257F, "Box Drawing", _C.SYMBOL),
    Block(0x2580, 0x259F, "Block Elements", _C.SYMBOL),
    Block(0x25A0, 0x25FF, "Geometric Shapes", _C.SYMBOL),
    Block(0x2600, 0x26FF, "Miscellaneous Symbols", _C.SYMBOL),
    Block(0x2700, 0x27BF, "Dingbats", _C.SYMBOL),
    Block(0x27F0, 0x27FF, "Supplemental Arrows-A", _C.SYMBOL),
    Block(0x2900, 0x297F, "Supplemental Arrows-B", _C.SYMBOL),
    Block(0x2980, 0x29FF, "Miscellaneous Mathematical Symbols-B", _C.WESTERN),
    Block(0x2B00, 0x2BFF, "Miscellaneous Symbols and Arrows", _C.SYMBOL),
    Block(0x2C60, 0x2C7F, "Latin Extended-C", _C.WESTERN),
    Block(0x2DE0, 0x2DFF, "Cyrillic Extended-A", _C.WESTERN),
    Block(0x2E00, 0x2E7F, "Supplemental Punctuation", _C.PUNCTUATION),
    Block(0x2E80, 0x2EFF, "CJK Radicals Supplement", _C.CJK),
    Block(0x2F00, 0x2FDF, "Kangxi Radicals", _C.CJK),
    Block(0x2FF0, 0x2FFF, "Ideographic Description Characters", _C.CJK),
    Block(0x3000, 0x303F, "CJK Symbols and Punctuation", _C.CJK),
    Block(0x3040, 0x309F, "Hiragana", _C.CJK),
    Block(0x30A0, 0x30FF, "Katakana", _C.CJK),
    Block(0x3100, 0x312F, "Bopomofo", _C.CJK),
    Block(0x3130, 0x318F, "Hangul Compatibility Jamo", _C.HANGUL),
    Block(0x3190, 0x319F, "Kanbun", _C.CJK),
    Block(0x31A0, 0x31BF, "Bopomofo Extended", _C.CJK),
    Block(0x31C0, 0x31EF, "CJK Strokes", _C.CJK),
    Block(0x31F0, 0x31FF, "Katakana Phonetic Extensions", _C.CJK),
    Block(0x3200, 0x32FF, "Enclosed CJK Letters and Months", _C.CJK),
    Block(0x3300, 0x33FF, "CJK Compatibility", _C.CJK),
    Block(0x3400, 0x4DBF, "CJK Unified Ideographs Extension A", _C.CJK),
    Block(0x4DC0, 0x4DFF, "Yijing Hexagram Symbols", _C.CJK),
    Block(0x4E00, 0x9FFF, "CJK Unified Ideographs", _C.CJK),
    Block(0xA640, 0xA69F, "Cyrillic Extended-B", _C.WESTERN),
    Block(0xA700, 0xA71F, "Modifier Tone Letters", _C.WESTERN),
    Block(0xA720, 0xA7FF, "Latin Extended-D", _C.WESTERN),
    Block(0xA960, 0xA97F, "Hangul Jamo Extended-A", _C.HANGUL),
    Block(0xAB30, 0xAB6F, "Latin Extended-E", _C.WESTERN),
    Block(0xAC00, 0xD7AF, "Hangul Syllables", _C.HANGUL),
    Block(0xD7B0, 0xD7FF, "Hangul Jamo Extended-B", _C.HANGUL),
    Block(0xF900, 0xFAFF, "CJK Compatibility Ideographs", _C.CJK),
    Block(0xFB00, 0xFB06, "Alphabetic Presentation Forms (Latin ligatures)", _C.WESTERN),
    Block(0xFE10, 0xFE1F, "Vertical Forms", _C.CJK),
    Block(0xFE20, 0xFE2F, "Combining Half Marks", _C.WESTERN),
    Block(0xFE30, 0xFE4F, "CJK Compatibility Forms", _C.CJK),
    Block(0xFE50, 0xFE6F, "Small Form Variants", _C.CJK),
    Block(0xFF00, 0xFFEF, "Halfwidth and Fullwidth Forms", _C.CJK),
    Block(0x1B000, 0x1B0FF, "Kana Supplement", _C.CJK),
    Block(0x1B100, 0x1B12F, "Kana Extended-A", _C.CJK),
    Block(0x1B130, 0x1B16F, "Small Kana Extension", _C.CJK),
    Block(0x1F100, 0x1F1FF, "Enclosed Alphanumeric Supplement", _C.SYMBOL),
    Block(0x1F200, 0x1F2FF, "Enclosed Ideographic Supplement", _C.CJK),
    Block(0x1F780, 0x1F7FF, "Geometric Shapes Extended", _C.SYMBOL),
    Block(0x20000, 0x2A6DF, "CJK Unified Ideographs Extension B", _C.CJK),
    Block(0x2A700, 0x2EBEF, "CJK Unified Ideographs Extensions C-F", _C.CJK),
    Block(0x2EBF0, 0x2EE5F, "CJK Unified Ideographs Extension I", _C.CJK),
    Block(0x2F800, 0x2FA1F, "CJK Compatibility Ideographs Supplement", _C.CJK),
    Block(0x30000, 0x323AF, "CJK Unified Ideographs Extensions G-H", _C.CJK),
)

# Punctuation that is specific to CJK typography even though it sits in a general block.
# Under the SPLIT policy these still come from the CJK font.
CJK_PREFERRED_PUNCTUATION: frozenset[int] = frozenset(
    {
        0x2025,  # ‥ two dot leader
        0x203B,  # ※ reference mark
        0x2E3A,  # ⸺ two-em dash
        0x2E3B,  # ⸻ three-em dash
    }
)

# Characters outside the punctuation blocks that behave like shared punctuation.
EXTRA_PUNCTUATION: frozenset[int] = frozenset(
    {
        0x00B7,  # · middle dot: Western shape is small; CJK shape is centred and wide
    }
)

_STARTS = [b.start for b in BLOCKS]


def block_of(codepoint: int) -> Block | None:
    """The block containing ``codepoint``, or ``None`` if it is not in the table."""
    i = bisect_right(_STARTS, codepoint) - 1
    if i >= 0 and BLOCKS[i].start <= codepoint <= BLOCKS[i].end:
        return BLOCKS[i]
    return None


def category_of(codepoint: int) -> Category:
    if codepoint in EXTRA_PUNCTUATION:
        return Category.PUNCTUATION
    block = block_of(codepoint)
    return block.category if block else Category.OTHER
