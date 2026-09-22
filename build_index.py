"""
One-time (re)build of the FAISS index from data/kjv_bible.pdf.

Usage:
    python download_bible.py   # first, to fetch the PDF
    python build_index.py      # then, to build the searchable index
"""
import json
from pathlib import Path

from src.chunker import chunk_verses
from src.config import (
    CHUNK_OVERLAP,
    EMBEDDING_MODEL_NAME,
    INDEX_PATH,
    METADATA_PATH,
    PDF_PATH,
    VERSE_DATA_PATH,
    VERSES_PER_CHUNK,
)
from src.embeddings import EmbeddingModel
from src.pdf_parser import parse_bible
from src.vector_store import VectorStore


def main():
    if not Path(PDF_PATH).exists():
        raise FileNotFoundError(
            f"Bible PDF not found at {PDF_PATH}.\n"
            f"Run `python download_bible.py` first, or place a KJV PDF there manually."
        )

    print("Parsing PDF into verses...")
    verses = parse_bible(PDF_PATH)
    print(f"Parsed {len(verses)} verses.")
    if len(verses) < 20000:
        print(
            "WARNING: verse count looks low for a complete Bible (~31,102 verses). "
            "Check the PDF's text layer and the heading/verse regex in src/pdf_parser.py."
        )

    Path(VERSE_DATA_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(VERSE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(verses, f)
    print(f"Saved exact verse data to {VERSE_DATA_PATH}")

    print("Chunking verses...")
    chunks = chunk_verses(verses, verses_per_chunk=VERSES_PER_CHUNK, overlap=CHUNK_OVERLAP)
    print(f"Created {len(chunks)} chunks.")

    print("Loading embedding model (first run downloads it, ~90 MB)...")
    embedder = EmbeddingModel(EMBEDDING_MODEL_NAME)

    print("Encoding chunks...")
    texts = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts)

    print("Building FAISS index...")
    store = VectorStore(dim=embeddings.shape[1])
    store.add(embeddings, chunks)

    Path(INDEX_PATH).parent.mkdir(parents=True, exist_ok=True)
    store.save(INDEX_PATH, METADATA_PATH)
    print(f"Saved index to {INDEX_PATH}")
    print(f"Saved metadata to {METADATA_PATH}")
    print("Done. Run `streamlit run app.py` to chat with it.")


if __name__ == "__main__":
    main()
