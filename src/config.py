"""
Central configuration for the KJV Bible RAG chatbot.
Change values here instead of hunting through the other modules.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Paths ------------------------------------------------------------
PDF_PATH = os.path.join(BASE_DIR, "data", "kjv_bible.pdf")
INDEX_DIR = os.path.join(BASE_DIR, "index")
INDEX_PATH = os.path.join(INDEX_DIR, "kjv.faiss")
METADATA_PATH = os.path.join(INDEX_DIR, "kjv_metadata.json")
VERSE_DATA_PATH = os.path.join(INDEX_DIR, "kjv_verses.json")

# --- Embedding model ----------------------------------------------------
# Local, free, CPU-friendly. 384-dim, good enough for verse-level RAG.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# --- Generation model (Google Gemini) ------------------------------------
GEMINI_MODEL = "gemini-3.6-flash"
# The SDK takes this value in milliseconds.  A finite timeout keeps a DNS,
# firewall, or stalled network connection from leaving the Streamlit page
# waiting indefinitely.
GEMINI_TIMEOUT_MS = 30_000

# --- Chunking -------------------------------------------------------------
# Verses are grouped, per chapter, into small overlapping windows so every
# chunk keeps an exact "Book Chapter:Verse-Verse" reference.
VERSES_PER_CHUNK = 5
CHUNK_OVERLAP = 1

# --- Retrieval --------------------------------------------------------
TOP_K = 3
