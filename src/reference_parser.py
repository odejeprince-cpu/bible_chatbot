"""
Detects an exact Bible reference (e.g. "John 3:16", "1 Cor 13:4-7",
"Genesis 1") inside a free-text question, so it can be looked up
directly instead of relying on semantic search alone.
"""
import re
from typing import Dict, Optional

# common name -> canonical book name (add more abbreviations as needed)
BOOK_ALIASES: Dict[str, str] = {
    "gen": "Genesis", "genesis": "Genesis",
    "exo": "Exodus", "exod": "Exodus", "exodus": "Exodus",
    "lev": "Leviticus", "leviticus": "Leviticus",
    "num": "Numbers", "numbers": "Numbers",
    "deut": "Deuteronomy", "deuteronomy": "Deuteronomy",
    "josh": "Joshua", "joshua": "Joshua",
    "judg": "Judges", "judges": "Judges",
    "ruth": "Ruth",
    "1 sam": "1 Samuel", "1sam": "1 Samuel", "1 samuel": "1 Samuel",
    "2 sam": "2 Samuel", "2sam": "2 Samuel", "2 samuel": "2 Samuel",
    "1 kgs": "1 Kings", "1kgs": "1 Kings", "1 kings": "1 Kings",
    "2 kgs": "2 Kings", "2kgs": "2 Kings", "2 kings": "2 Kings",
    "1 chr": "1 Chronicles", "1chr": "1 Chronicles", "1 chronicles": "1 Chronicles",
    "2 chr": "2 Chronicles", "2chr": "2 Chronicles", "2 chronicles": "2 Chronicles",
    "ezra": "Ezra",
    "neh": "Nehemiah", "nehemiah": "Nehemiah",
    "esth": "Esther", "esther": "Esther",
    "job": "Job",
    "ps": "Psalms", "psa": "Psalms", "psalm": "Psalms", "psalms": "Psalms",
    "prov": "Proverbs", "proverbs": "Proverbs",
    "eccl": "Ecclesiastes", "ecclesiastes": "Ecclesiastes",
    "song": "Song of Solomon", "song of solomon": "Song of Solomon", "sos": "Song of Solomon",
    "isa": "Isaiah", "isaiah": "Isaiah",
    "jer": "Jeremiah", "jeremiah": "Jeremiah",
    "lam": "Lamentations", "lamentations": "Lamentations",
    "ezek": "Ezekiel", "ezekiel": "Ezekiel",
    "dan": "Daniel", "daniel": "Daniel",
    "hos": "Hosea", "hosea": "Hosea",
    "joel": "Joel",
    "amos": "Amos",
    "obad": "Obadiah", "obadiah": "Obadiah",
    "jonah": "Jonah",
    "mic": "Micah", "micah": "Micah",
    "nah": "Nahum", "nahum": "Nahum",
    "hab": "Habakkuk", "habakkuk": "Habakkuk",
    "zeph": "Zephaniah", "zephaniah": "Zephaniah",
    "hag": "Haggai", "haggai": "Haggai",
    "zech": "Zechariah", "zechariah": "Zechariah",
    "mal": "Malachi", "malachi": "Malachi",
    "matt": "Matthew", "mt": "Matthew", "matthew": "Matthew",
    "mark": "Mark", "mk": "Mark",
    "luke": "Luke", "lk": "Luke",
    "john": "John", "jn": "John",
    "acts": "Acts",
    "rom": "Romans", "romans": "Romans",
    "1 cor": "1 Corinthians", "1cor": "1 Corinthians", "1 corinthians": "1 Corinthians",
    "2 cor": "2 Corinthians", "2cor": "2 Corinthians", "2 corinthians": "2 Corinthians",
    "gal": "Galatians", "galatians": "Galatians",
    "eph": "Ephesians", "ephesians": "Ephesians",
    "phil": "Philippians", "philippians": "Philippians",
    "col": "Colossians", "colossians": "Colossians",
    "1 thess": "1 Thessalonians", "1thess": "1 Thessalonians", "1 thessalonians": "1 Thessalonians",
    "2 thess": "2 Thessalonians", "2thess": "2 Thessalonians", "2 thessalonians": "2 Thessalonians",
    "1 tim": "1 Timothy", "1tim": "1 Timothy", "1 timothy": "1 Timothy",
    "2 tim": "2 Timothy", "2tim": "2 Timothy", "2 timothy": "2 Timothy",
    "titus": "Titus",
    "philem": "Philemon", "philemon": "Philemon",
    "heb": "Hebrews", "hebrews": "Hebrews",
    "james": "James", "jas": "James",
    "1 pet": "1 Peter", "1pet": "1 Peter", "1 peter": "1 Peter",
    "2 pet": "2 Peter", "2pet": "2 Peter", "2 peter": "2 Peter",
    "1 john": "1 John", "1john": "1 John",
    "2 john": "2 John", "2john": "2 John",
    "3 john": "3 John", "3john": "3 John",
    "jude": "Jude",
    "rev": "Revelation", "revelation": "Revelation", "revelations": "Revelation",
}

# Build the book-name alternation from the alias table itself (longest
# first, so "1 Corinthians" is tried before "1 Cor" is tried before "Cor")
# rather than a generic "any word" pattern - this avoids false positives
# like matching "about" in "tell me about 1 Cor 13:4-7" as a book name.
_alias_keys = sorted(BOOK_ALIASES.keys(), key=len, reverse=True)
_book_alternation = "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in _alias_keys)

REFERENCE_RE = re.compile(
    r'\b(' + _book_alternation + r')\.?\s+'
    r'(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?\b',
    re.IGNORECASE,
)


def parse_reference(query: str) -> Optional[Dict]:
    """
    Returns {"book", "chapter", "verse_start"?, "verse_end"?} for the
    first recognizable Bible reference found in the query, or None.
    """
    match = REFERENCE_RE.search(query)
    if not match:
        return None
    raw_book, chapter, verse_start, verse_end = match.groups()
    key = re.sub(r'\s+', ' ', raw_book.strip().lower())
    book = BOOK_ALIASES.get(key)
    if not book:
        return None
    result: Dict = {"book": book, "chapter": int(chapter)}
    if verse_start:
        result["verse_start"] = int(verse_start)
        result["verse_end"] = int(verse_end) if verse_end else int(verse_start)
    return result