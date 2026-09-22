"""Local, exact KJV verse lookup backed by build_index.py output."""
import json
import re
from typing import Dict, List


def format_reference(ref: Dict) -> str:
    """Format a parsed reference using the project's canonical book names."""
    label = f"{ref['book']} {ref['chapter']}"
    if "verse_start" not in ref:
        return label
    label += f":{ref['verse_start']}"
    if ref["verse_end"] != ref["verse_start"]:
        label += f"-{ref['verse_end']}"
    return label


class VerseStore:
    """In-memory index of individual KJV verses; no network access is used."""

    def __init__(self, verses: List[Dict]):
        self._verses = {}
        for verse in verses:
            key = (verse["book"], verse["chapter"], verse["verse"])
            self._verses[key] = dict(verse)

    @classmethod
    def load(cls, path: str) -> "VerseStore":
        with open(path, "r", encoding="utf-8") as file:
            return cls(json.load(file))

    @classmethod
    def from_chunk_metadata(cls, chunks: List[Dict]) -> "VerseStore":
        """Build exact records from the already-local indexed KJV chunks.

        This keeps existing installations working until their next index
        rebuild creates ``kjv_verses.json``. Chunk text is assembled from
        numbered verse text, so its number markers safely delimit the verses.
        """
        verses = []
        marker = re.compile(r"(?<!\d)(\d{1,3})\.\s+")
        seen = set()
        for chunk in chunks:
            matches = list(marker.finditer(chunk["text"]))
            for index, match in enumerate(matches):
                verse_number = int(match.group(1))
                if not chunk["verse_start"] <= verse_number <= chunk["verse_end"]:
                    continue
                key = (chunk["book"], chunk["chapter"], verse_number)
                if key in seen:
                    continue
                end = matches[index + 1].start() if index + 1 < len(matches) else len(chunk["text"])
                text = chunk["text"][match.end():end].strip()
                if text:
                    verses.append({
                        "book": chunk["book"],
                        "chapter": chunk["chapter"],
                        "verse": verse_number,
                        "text": text,
                    })
                    seen.add(key)
        return cls(verses)

    def lookup(self, ref: Dict) -> List[Dict]:
        """Return one local KJV record per requested verse, in canonical order."""
        start = ref.get("verse_start")
        end = ref.get("verse_end")
        if start is None:
            matches = [
                verse for (book, chapter, _), verse in self._verses.items()
                if book == ref["book"] and chapter == ref["chapter"]
            ]
        else:
            matches = [
                self._verses[key]
                for key in (
                    (ref["book"], ref["chapter"], verse)
                    for verse in range(start, end + 1)
                )
                if key in self._verses
            ]

        return [
            {
                **verse,
                "reference": f"{verse['book']} {verse['chapter']}:{verse['verse']}",
            }
            for verse in sorted(matches, key=lambda verse: verse["verse"])
        ]
