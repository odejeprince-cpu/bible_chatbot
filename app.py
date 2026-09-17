"""
Streamlit chat UI for the KJV Bible RAG chatbot.

Run with:
    streamlit run app.py
"""
import streamlit as st
from dotenv import load_dotenv

from src.config import EMBEDDING_MODEL_NAME, GEMINI_MODEL, INDEX_PATH, METADATA_PATH, TOP_K
from src.embeddings import EmbeddingModel
from src.rag_chain import RAGChain
from src.retriever import HybridRetriever
from src.vector_store import VectorStore

load_dotenv()

st.set_page_config(page_title="KJV Bible Chatbot", page_icon="book")
st.title("KJV Bible Chatbot")
st.caption(
    "Ask a question or look up a verse (e.g. \"John 3:16\" or \"What does the "
    "Bible say about forgiveness?\"). Answers come only from the KJV text you indexed."
)


@st.cache_resource
def load_pipeline():
    embedder = EmbeddingModel(EMBEDDING_MODEL_NAME)
    store = VectorStore.load(INDEX_PATH, METADATA_PATH)
    retriever = HybridRetriever(store, embedder, top_k=TOP_K)
    chain = RAGChain(model=GEMINI_MODEL)
    return retriever, chain


try:
    retriever, chain = load_pipeline()
except FileNotFoundError:
    st.error(
        "Index not found. Run `python download_bible.py` then "
        "`python build_index.py` first."
    )
    st.stop()
except ValueError as e:
    st.error(str(e))
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

question = st.chat_input("Ask about the KJV Bible...")
if question:
    st.session_state.history.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching the scriptures..."):
            passages = retriever.retrieve(question)
            answer = chain.answer(question, passages)
        st.markdown(answer)
        if passages:
            with st.expander(f"Sources ({passages[0]['match_type'].replace('_', ' ')})"):
                for p in passages:
                    st.markdown(f"**{p['reference']}** \u2014 {p['text']}")
    st.session_state.history.append(("assistant", answer))