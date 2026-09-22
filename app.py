import streamlit as st
from dotenv import load_dotenv

from src import chat_store
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
from src.reference_parser import find_references
from src.retriever import HybridRetriever
from src.vector_store import VectorStore
from src.verse_store import VerseStore, format_reference

load_dotenv()

st.set_page_config(
    page_title="KJV Bible Chatbot",
    page_icon="📖",
    layout="wide",
)

st.markdown(
    """
    <style>
    #MainMenu, footer, header {
        visibility: hidden;
    }

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

    .question-container {
        display: flex;
        justify-content: flex-end;
        margin-top: 24px;
        margin-bottom: 12px;
    }

    .question-box {
        background-color: #eeeeee;
        border-radius: 16px;
        padding: 12px 18px;
        max-width: 70%;
        color: #111111;
    }

    .question-label {
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 5px;
        color: #555555;
    }

    .answer-container {
        display: flex;
        justify-content: flex-start;
        margin-bottom: 12px;
    }

    .answer-box {
        background-color: #f7f7f7;
        border: 1px solid #e1e1e1;
        border-radius: 16px;
        padding: 18px;
        max-width: 85%;
        color: #111111;
    }

    .answer-label {
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 8px;
        color: #555555;
    }

    @media (max-width: 768px) {
        .question-box {
            max-width: 90%;
        }

        .answer-box {
            max-width: 95%;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_pipeline():
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


try:
    retriever, chain, verse_store = load_pipeline()

except FileNotFoundError:
    st.error(
        "Bible index data not found. Run `python build_index.py` to "
        "create the local search index and exact verse data."
    )
    st.stop()

except ValueError as e:
    st.error(str(e))
    st.stop()


if "chat_id" not in st.session_state:
    st.session_state.chat_id = chat_store.new_chat_id()

if "history" not in st.session_state:
    st.session_state.history = []


with st.sidebar:
    st.markdown("### 📖 KJV Bible Chatbot")

    if st.button("+ New chat", use_container_width=True):
        st.session_state.chat_id = chat_store.new_chat_id()
        st.session_state.history = []
        st.rerun()

    if st.session_state.history:
        if st.button(
            "🗑️ Clear current chat",
            use_container_width=True,
        ):
            st.session_state.history = []

            chat_store.save_chat(
                st.session_state.chat_id,
                st.session_state.history,
            )

            st.rerun()

    st.markdown("---")
    st.markdown("**Recent chats**")

    for chat in chat_store.list_chats():
        is_current = chat["id"] == st.session_state.chat_id

        label = (
            ("• " if is_current else "")
            + chat["title"]
        )

        if st.button(
            label,
            key=f"chat_{chat['id']}",
            use_container_width=True,
        ):
            st.session_state.chat_id = chat["id"]
            st.session_state.history = chat_store.load_chat(
                chat["id"]
            )
            st.rerun()


st.title("📖 KJV Bible Chatbot")

st.caption(
    "Ask a question or look up a verse. "
    "Answers come from the KJV Bible text you indexed."
)


history = st.session_state.history


def render_scripture_references(answer_text: str, message_id: str) -> None:
    """Render local KJV lookups for citations Gemini included in an answer."""
    references = find_references(answer_text)
    if not references:
        return

    st.caption("Scripture references")
    for number, reference in enumerate(references):
        label = format_reference(reference)
        selection_key = f"selected_scripture_{message_id}"
        if st.button(f"📖 {label}", key=f"scripture_{message_id}_{number}"):
            st.session_state[selection_key] = reference

    selected = st.session_state.get(f"selected_scripture_{message_id}")
    if selected:
        verses = verse_store.lookup(selected)
        label = format_reference(selected)
        with st.expander(f"KJV — {label}", expanded=True):
            if verses:
                for verse in verses:
                    st.markdown(f"**{verse['reference']}** — {verse['text']}")
            else:
                st.warning("This reference was not found in the local KJV data.")


i = 0

while i < len(history):
    message = history[i]

    if (
        message["role"] == "user"
        and i + 1 < len(history)
        and history[i + 1]["role"] == "assistant"
    ):
        question_text = message["content"]
        answer_message = history[i + 1]

        answer_text = answer_message["content"]
        sources = answer_message.get("sources")

        st.markdown(
            f"""
            <div class="question-container">
                <div class="question-box">
                    <div class="question-label">
                        ❓ QUESTION
                    </div>
                    {question_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="answer-container">
                <div class="answer-box">
                    <div class="answer-label">
                        📖 ANSWER
                    </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(answer_text)

        st.markdown(
            """
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_scripture_references(answer_text, f"history_{i}")

        if sources:
            with st.expander(
                "📜 Sources "
                f"({sources[0]['match_type'].replace('_', ' ')})"
            ):
                for passage in sources:
                    st.markdown(
                        f"**{passage['reference']}** — "
                        f"{passage['text']}"
                    )

        i += 2

    else:
        i += 1


question = st.chat_input(
    "Ask about the KJV Bible..."
)


if question:
    st.write("**Step 1: Searching the Bible...**")

    passages = retriever.retrieve(question)

    st.write(
        "**Step 2: Bible search finished. "
        f"Found {len(passages)} passages.**"
    )

    st.write("**Step 3: Asking Gemini...**")

    answer_placeholder = st.empty()
    answer_parts = []

    try:
        for chunk in chain.answer_stream(
            question,
            passages,
        ):
            answer_parts.append(chunk)

            answer_placeholder.markdown(
                "".join(answer_parts)
            )

    except Exception:
        answer = (
            "An unexpected error occurred while asking Gemini. "
            "Please try again."
        )
        answer_parts = [answer]
        answer_placeholder.markdown(answer)

    answer = "".join(answer_parts)

    st.write("**Step 4: Gemini finished.**")

    st.session_state.history.append(
        {
            "role": "user",
            "content": question,
        }
    )

    st.session_state.history.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": passages,
        }
    )

    chat_store.save_chat(
        st.session_state.chat_id,
        st.session_state.history,
    )

    st.rerun()
