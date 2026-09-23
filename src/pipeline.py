"""
Pipeline setup for the KJV Bible chatbot.

Handles building (and caching) the retrieval + generation pipeline so
app.py can stay focused on the Streamlit UI loop.
"""
import streamlit as st

from src.config import (
    EMBEDDING_MODEL_NAME,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_MS,
    INDEX_PATH,
    METADATA_PATH,
    TOP_K,
    VERSE_DATA_PATH,
)
from src.embeddings import EmbeddingModel
from src.rag_chain import RAGChain
from src.retriever import HybridRetriever
from src.vector_store import VectorStore
from src.verse_store import VerseStore


@st.cache_resource
def load_pipeline():
    """Build the embedder, vector store, verse store, retriever, and RAG chain.

    Cached so this only runs once per Streamlit session, not on every rerun.
    """
    embedder = EmbeddingModel(EMBEDDING_MODEL_NAME)
    store = VectorStore.load(INDEX_PATH, METADATA_PATH)

    try:
        verse_store = VerseStore.load(VERSE_DATA_PATH)
    except FileNotFoundError:
        # Older indexes predate verse-level data. Derive it from their local
        # KJV chunks so this feature works immediately, then use the dedicated
        # data automatically after the next normal index rebuild.
        verse_store = VerseStore.from_chunk_metadata(store.metadata)

    retriever = HybridRetriever(
        store,
        embedder,
        verse_store=verse_store,
        top_k=TOP_K,
    )
    chain = RAGChain(
        model=GEMINI_MODEL,
        timeout_ms=GEMINI_TIMEOUT_MS,
    )

    return retriever, chain, verse_store