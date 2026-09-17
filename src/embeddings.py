"""
Thin wrapper around sentence-transformers so the rest of the codebase
doesn't need to know which embedding model or library is in use.
"""
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: List[str], batch_size: int = 64, show_progress_bar: bool = True) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
            convert_to_numpy=True,
            normalize_embeddings=True,  # so inner product == cosine similarity
        )
        return embeddings.astype(np.float32)