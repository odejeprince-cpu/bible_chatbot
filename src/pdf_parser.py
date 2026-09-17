"""
Parses this KJV PDF's actual layout, which we discovered by inspecting
the extracted text directly:

  - Every page starts with a running header like:
        "Genesis 1:1 1 Genesis 1:30"
    meaning: <book> <start_chapter>:<start_verse> <page_number>
             <book> <end_chapter>:<end_verse>
    We use this header - not the ornate historical book titles like
    "The First Book of Moses, called Genesis" - as the reliable source
    for which book and chapter a page belongs to.

  - Inside the body text, each verse is marked by a bare number
    followed by the verse text, e.g.:
        "6 ¶ And God said, Let there be a firmament..."
    KJV prose always spells numbers as words ("forty days", never
    "40 days"), so a bare digit followed by a capital letter, quote
    mark, or paragraph mark (¶) reliably means "a new verse starts
    here" - it's never part of the verse's own wording.

  - Chapter numbers are only ever printed once, in the header, so we
    track the current chapter ourselves: whenever a verse number is
    lower than the previous one (e.g. we were at verse 25 and the next
    marker is "1"), a new chapter has begun.
"""
import re
from typing import Dict, List

import pypdf

BOOK_NAMES = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
]

_book_variants = sorted(BOOK_NAMES, key=len, reverse=True)
_book_pattern = '|'.join(re.escape(b).replace(r'\ ', r'\s+') for b in _book_variants)

# The running header at the very top of a page's extracted text, e.g.
# "Genesis 1:1 1 Genesis 1:30" or "1 Corinthians 13:1 812 1 Corinthians 13:13".
HEADER_RE = re.compile(
    r'^\s*(' + _book_pattern + r')\s+(\d{1,3}):(\d{1,3})\s+\d+\s+'
    r'(' + _book_pattern + r')\s+(\d{1,3}):(\d{1,3})',
    re.IGNORECASE,
)

# A bare verse-number marker: digits not preceded by another digit,
# followed by whitespace then a capital letter, quote mark, or pilcrow.
VERSE_NUM_RE = re.compile(r'(?<!\d)(\d{1,3})\s+(?=[A-Z"\u2018\u2019\u00b6])')

# Strip inline Strong's-number annotations, in case a future PDF has them.
STRONGS_STRIP_RE = re.compile(r'[<\[]\s*[HG]\d+\s*[>\]]')


def _canonicalize_book_name(raw: str) -> str:
    norm = re.sub(r'\s+', ' ', raw).strip()
    for book in BOOK_NAMES:
        if book.lower() == norm.lower():
            return book
    return norm


def extract_pdf_text(pdf_path: str) -> str:
    """Utility for debugging: all pages' text, concatenated in order."""
    reader = pypdf.PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_bible(pdf_path: str) -> List[Dict]:
    """
    Returns a flat list of verse records:
        {"book": str, "chapter": int, "verse": int, "text": str}
    """
    reader = pypdf.PdfReader(pdf_path)

    verses: List[Dict] = []
    current_book = None
    current_chapter = None
    previous_verse = None

    for page in reader.pages:
        page_text = page.extract_text() or ""
        header_match = HEADER_RE.match(page_text.strip())
        if not header_match:
            # Table of contents, title page, blank page, etc. - skip it.
            continue

        book_name = _canonicalize_book_name(header_match.group(1))
        start_chapter = int(header_match.group(2))

        if book_name != current_book:
            current_book = book_name
            current_chapter = start_chapter
            previous_verse = None

        body = STRONGS_STRIP_RE.sub("", page_text[header_match.end():])
        matches = list(VERSE_NUM_RE.finditer(body))

        for i, m in enumerate(matches):
            verse_num = int(m.group(1))
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            text = body[start:end].strip().lstrip("¶").strip()
            if not text:
                continue

            if previous_verse is not None and verse_num < previous_verse:
                current_chapter += 1

            verses.append({
                "book": current_book,
                "chapter": current_chapter,
                "verse": verse_num,
                "text": text,
            })
            previous_verse = verse_num

    return verses