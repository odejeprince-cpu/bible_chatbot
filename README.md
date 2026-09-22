# KJV Bible Chatbot (RAG)

A Python chatbot that answers questions using **only** the King James
Version Bible as its knowledge source. It combines exact verse lookup
("John 3:16") with semantic search (conceptual questions like "what does
the Bible say about forgiveness?"), and is instructed to say so plainly
whenever the retrieved passages don't contain the answer, rather than
guessing.

## How it works

1. **`download_bible.py`** fetches a complete, public-domain KJV PDF.
2. **`build_index.py`** parses the PDF into individual verses (via
   `src/pdf_parser.py`), groups them into small overlapping chunks that
   each keep an exact `Book Chapter:Verse` reference (`src/chunker.py`),
   embeds them locally with `sentence-transformers`
   (`src/embeddings.py`), and stores them in a FAISS index
   (`src/vector_store.py`). It also saves the individual local KJV verses
   used for exact lookup.
3. **`app.py`** is a Streamlit chat UI. Each question goes through
   `src/retriever.py`, which:
   - checks whether the question names an exact reference
     (`src/reference_parser.py`) and looks it up directly if so;
   - otherwise falls back to semantic search over the FAISS index.
   The retrieved passages are then passed to `src/rag_chain.py`, which
   prompts Google Gemini with a strict system instruction: answer only
   from the given passages, always cite `Book Chapter:Verse`, and say
   "I don't have enough information..." when the passages don't cover
   the question.

## Project structure

```
kjv-bible-chatbot/
├── data/
│   └── kjv_bible.pdf          # created by download_bible.py
├── index/
│   ├── kjv.faiss               # created by build_index.py
│   ├── kjv_metadata.json       # created by build_index.py
│   └── kjv_verses.json         # created by build_index.py; exact local lookup
├── src/
│   ├── __init__.py
│   ├── config.py                # paths, model names, chunk/retrieval settings
│   ├── pdf_parser.py            # PDF -> list of {book, chapter, verse, text}
│   ├── chunker.py                # verses -> overlapping referenced chunks
│   ├── embeddings.py             # sentence-transformers wrapper
│   ├── vector_store.py           # FAISS index wrapper (save/load/search)
│   ├── reference_parser.py       # detects "John 3:16" style references
│   ├── verse_store.py             # exact local KJV verse lookup
│   ├── retriever.py               # hybrid exact + semantic retrieval
│   └── rag_chain.py               # strict-grounding prompt + Gemini call
├── download_bible.py             # fetches the public-domain KJV PDF
├── build_index.py                 # one-time: PDF -> FAISS index
├── app.py                          # Streamlit chat interface
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Setup

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Gemini API key
cp .env.example .env
# then edit .env and paste your key from https://aistudio.google.com/apikey

# 4. Download the Bible PDF (public domain KJV, 1769 standardized text)
python download_bible.py

# 5. Build the search index (parses the PDF, embeds every verse chunk)
python build_index.py

# 6. Launch the chatbot
streamlit run app.py
```

## About the included Bible PDF

`download_bible.py` fetches **`KJVtext.pdf`** from the Internet Archive
item [kjvtextbible](https://archive.org/details/kjvtextbible) - the
complete King James (Authorized) Version, standardized 1769 text,
courtesy of the Crosswire Bible Society and eBible.org. It is public
domain worldwide except that UK printing/importing is still covered by
the Crown's letters patent (irrelevant to using the text digitally
outside the UK). All 66 books, every chapter and verse, are included.

If you'd rather supply your own KJV PDF, just place any complete KJV
PDF at `data/kjv_bible.pdf` and run `build_index.py` directly - skip
`download_bible.py`.

## Notes on accuracy and grounding

- The chatbot is instructed to answer **only** from retrieved KJV
  passages, to always cite `Book Chapter:Verse`, to quote verses
  verbatim (not paraphrase them into other wording), and to say it
  doesn't have enough information rather than guessing.
- If your PDF's text layer is laid out differently than expected (e.g.
  two columns, heavy per-word Strong's-number tagging), `build_index.py`
  will warn you if the parsed verse count looks too low (a complete
  Bible has 31,102 verses). In that case, adjust the heading/verse
  regular expressions in `src/pdf_parser.py` to match your PDF's layout.
- Chunk size (`VERSES_PER_CHUNK`) and overlap (`CHUNK_OVERLAP`) are set
  in `src/config.py` if you want coarser or finer-grained retrieval.
