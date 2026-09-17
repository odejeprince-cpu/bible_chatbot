"""
Minimal FAISS wrapper: holds normalized embeddings (inner product =
cosine similarity) plus a parallel Python list of metadata dicts, and
knows how to save/load both to disk.
"""
import json
from typing import Dict, List

import faiss
import numpy as np


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.metadata: List[Dict] = []

    def add(self, embeddings: np.ndarray, metadata: List[Dict]) -> None:
        self.index.add(embeddings)
        self.metadata.extend(metadata)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Dict]:
        scores, indices = self.index.search(query_embedding, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            item = dict(self.metadata[idx])
            item["score"] = float(score)
            results.append(item)
        return results

    def save(self, index_path: str, metadata_path: str) -> None:
        faiss.write_index(self.index, index_path)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f)

    @classmethod
    def load(cls, index_path: str, metadata_path: str) -> "VectorStore":
        index = faiss.read_index(index_path)
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        store = cls(dim=index.d)
        store.index = index
        store.metadata = metadata
        return store