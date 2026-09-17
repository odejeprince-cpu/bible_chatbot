"""
Groups verse records into small overlapping chunks, never crossing a
chapter boundary, so every chunk can carry an exact Bible reference.
"""
from typing import Dict, List


def chunk_verses(verses: List[Dict], verses_per_chunk: int = 5, overlap: int = 1) -> List[Dict]:
    """
    Returns a list of chunk records:
        {"book", "chapter", "verse_start", "verse_end", "reference", "text"}
    """
    grouped: Dict[tuple, List[Dict]] = {}
    for v in verses:
        key = (v["book"], v["chapter"])
        grouped.setdefault(key, []).append(v)

    chunks: List[Dict] = []
    step = max(1, verses_per_chunk - overlap)

    for (book, chapter), vlist in grouped.items():
        vlist = sorted(vlist, key=lambda x: x["verse"])
        i = 0
        while i < len(vlist):
            group = vlist[i:i + verses_per_chunk]
            if not group:
                break
            verse_start = group[0]["verse"]
            verse_end = group[-1]["verse"]
            text = " ".join(f"{g['verse']}. {g['text']}" for g in group)
            reference = (
                f"{book} {chapter}:{verse_start}"
                if verse_start == verse_end
                else f"{book} {chapter}:{verse_start}-{verse_end}"
            )
            chunks.append({
                "book": book,
                "chapter": chapter,
                "verse_start": verse_start,
                "verse_end": verse_end,
                "reference": reference,
                "text": text,
            })
            if i + verses_per_chunk >= len(vlist):
                break
            i += step

    return chunks