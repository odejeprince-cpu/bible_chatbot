"""
Streamlit UI helpers for the KJV Bible chatbot: styling and chat history rendering.
"""
import streamlit as st

from src.reference_parser import find_references
from src.verse_store import format_reference


CUSTOM_CSS = """
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
"""


def inject_custom_css() -> None:
    """Apply the chatbot's custom styling (hides Streamlit chrome, styles bubbles)."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_scripture_references(answer_text: str, message_id: str, verse_store) -> None:
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


def render_history(history: list, verse_store) -> None:
    """Redraw the full question/answer chat bubbles for the current session."""
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

            render_scripture_references(answer_text, f"history_{i}", verse_store)

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