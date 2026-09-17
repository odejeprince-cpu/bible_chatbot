"""
Hybrid retrieval: if the question contains an exact Bible reference
("John 3:16"), fetch that passage directly from the metadata. Otherwise
(or if the exact match is empty), fall back to semantic search over the
FAISS index for conceptual questions.
"""
from typing import Dict, List

from .embeddings import EmbeddingModel
from .reference_parser import parse_reference
from .vector_store import VectorStore


class HybridRetriever:
    def __init__(self, vector_store: VectorStore, embedder: EmbeddingModel, top_k: int = 5):
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k

    def _exact_lookup(self, ref: Dict) -> List[Dict]:
        book, chapter = ref["book"], ref["chapter"]
        verse_start = ref.get("verse_start")
        verse_end = ref.get("verse_end")
        matches = []
        for item in self.vector_store.metadata:
            if item["book"] != book or item["chapter"] != chapter:
                continue
            if verse_start is not None:
                if item["verse_end"] < verse_start or item["verse_start"] > verse_end:
                    continue
            matches.append(dict(item))
        matches.sort(key=lambda m: m["verse_start"])
        return matches

    def retrieve(self, query: str) -> List[Dict]:
        ref = parse_reference(query)
        if ref:
            exact = self._exact_lookup(ref)
            if exact:
                for r in exact:
                    r["match_type"] = "exact_reference"
                return exact

        query_embedding = self.embedder.encode([query], show_progress_bar=False)
        results = self.vector_store.search(query_embedding, top_k=self.top_k)
        for r in results:
            r["match_type"] = "semantic"
        return results