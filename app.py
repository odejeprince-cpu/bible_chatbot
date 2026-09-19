"""
Streamlit chat UI for the KJV Bible RAG chatbot, with a sidebar for
browsing and reopening past conversations (similar to Claude/ChatGPT).

Run with:
    streamlit run app.py
"""
import streamlit as st
from dotenv import load_dotenv

from src import chat_store
from src.config import EMBEDDING_MODEL_NAME, GEMINI_MODEL, INDEX_PATH, METADATA_PATH, TOP_K
from src.embeddings import EmbeddingModel
from src.rag_chain import RAGChain
from src.retriever import HybridRetriever
from src.vector_store import VectorStore

load_dotenv()

st.set_page_config(page_title="KJV Bible Chatbot", page_icon="📖", layout="wide")

# --- Custom styling --------------------------------------------------------
# Streamlit's default look is plain by design; this injects our own CSS to
# hide Streamlit's built-in menu/footer and restyle the sidebar and messages.
st.markdown("""
<style>
    #MainMenu, footer, header {visibility: hidden;}

    section[data-testid="stSidebar"] {
        background-color: #171717;
    }
    section[data-testid="stSidebar"] * {
        color: #e5e5e5 !important;
    }
    section[data-testid="stSidebar"] button {
        background-color: transparent;
        border: 1px solid #3a3a3a;
        text-align: left;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #2a2a2a;
        border-color: #4a4a4a;
    }

    .stChatMessage {
        border-radius: 1rem;
        padding: 0.5rem 0.25rem;
    }
</style>
""", unsafe_allow_html=True)


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
    st.error("Index not found. Run `python download_bible.py` then `python build_index.py` first.")
    st.stop()
except ValueError as e:
    st.error(str(e))
    st.stop()

# --- Session state: which conversation is currently open -------------------
if "chat_id" not in st.session_state:
    st.session_state.chat_id = chat_store.new_chat_id()
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"role", "content", "sources"?}

# --- Sidebar: new chat button + list of saved conversations ----------------
with st.sidebar:
    st.markdown("### 📖 KJV Bible Chatbot")

    if st.button("+ New chat", use_container_width=True):
        st.session_state.chat_id = chat_store.new_chat_id()
        st.session_state.history = []
        st.rerun()

    st.markdown("---")
    st.markdown("**Recent chats**")

    for chat in chat_store.list_chats():
        is_current = chat["id"] == st.session_state.chat_id
        label = ("• " if is_current else "") + chat["title"]
        if st.button(label, key=f"chat_{chat['id']}", use_container_width=True):
            st.session_state.chat_id = chat["id"]
            st.session_state.history = chat_store.load_chat(chat["id"])
            st.rerun()

# --- Main chat area ----------------------------------------------------
st.title("KJV Bible Chatbot")
st.caption(
    "Ask a question or look up a verse (e.g. \"John 3:16\" or \"What does the "
    "Bible say about forgiveness?\"). Answers come only from the KJV text you indexed."
)

for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        sources = message.get("sources")
        if sources:
            with st.expander(f"Sources ({sources[0]['match_type'].replace('_', ' ')})"):
                for p in sources:
                    st.markdown(f"**{p['reference']}** \u2014 {p['text']}")

question = st.chat_input("Ask about the KJV Bible...")
if question:
    st.session_state.history.append({"role": "user", "content": question})
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

    st.session_state.history.append({
        "role": "assistant",
        "content": answer,
        "sources": passages,
    })

    chat_store.save_chat(st.session_state.chat_id, st.session_state.history)