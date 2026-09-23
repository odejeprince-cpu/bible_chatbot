import streamlit as st
from dotenv import load_dotenv

from src import chat_store
from src.pipeline import load_pipeline
from src.ui import inject_custom_css, render_history

load_dotenv()

st.set_page_config(
    page_title="KJV Bible Chatbot",
    page_icon="📖",
    layout="wide",
)

inject_custom_css()

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


render_history(st.session_state.history, verse_store)


question = st.chat_input(
    "Ask about the KJV Bible..."
)


if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching the scriptures..."):
            passages = retriever.retrieve(question)

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