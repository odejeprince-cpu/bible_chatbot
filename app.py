import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src import auth, chat_store, google_auth
from src.pipeline import load_pipeline
from src.ui import inject_custom_css, render_history

st.set_page_config(
    page_title="KJV Bible Chatbot",
    page_icon="📖",
    layout="wide",
)

inject_custom_css()

# ---------- Auth gate ----------
if "user" not in st.session_state:
    st.session_state.user = None

query_params = st.query_params
if st.session_state.user is None and "code" in query_params:
    try:
        profile = google_auth.exchange_code_for_user(query_params["code"])
        user = auth.get_or_create_google_user(
            google_id=profile["sub"],
            email=profile.get("email", ""),
            name=profile.get("name", ""),
        )
        st.session_state.user = user
        st.query_params.clear()
        st.rerun()
    except Exception:
        st.error("Google sign-in failed. Please try again.")
        st.query_params.clear()

if st.session_state.user is None:
    st.title("📖 KJV Bible Chatbot")
    st.caption("Sign in to save and revisit your chat history.")

    st.link_button(
        "Continue with Google",
        google_auth.google_login_url(),
        use_container_width=True,
    )

    st.markdown("---")

    tab_signin, tab_signup = st.tabs(["Sign in", "Create account"])

    with tab_signin:
        with st.form("signin_form"):
            phone = st.text_input("Phone number")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in"):
                user = auth.verify_phone_login(phone, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Incorrect phone number or password.")

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("Name")
            phone = st.text_input("Phone number", key="signup_phone")
            password = st.text_input(
                "Password", type="password", key="signup_password"
            )
            confirm = st.text_input(
                "Confirm password", type="password", key="signup_confirm"
            )
            if st.form_submit_button("Create account"):
                if not phone or not password:
                    st.error("Phone number and password are required.")
                elif password != confirm:
                    st.error("Passwords don't match.")
                else:
                    try:
                        user = auth.create_user_with_phone(phone, password, name)
                        st.session_state.user = user
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    st.stop()

user = st.session_state.user


@st.dialog("A Note Before You Continue")
def show_disclaimer_dialog():
    st.markdown("**MOMENT OF REFLECTION**")
    st.markdown(
        "_He that getteth wisdom loveth his own soul: "
        "he that keepeth understanding shall find good._"
    )
    st.markdown("---")
    st.write(
        "This chatbot is not a substitute for professional counseling, "
        "medical advice, or pastoral care. If you are facing emotional, "
        "mental, or spiritual challenges, please reach out to a licensed "
        "counselor or therapist, a medical professional, or a trusted pastor."
    )
    dont_show_again = st.checkbox("Don't show again")
    if st.button("Ok, I understand", use_container_width=True):
        st.session_state.disclaimer_seen = True
        if dont_show_again:
            auth.set_disclaimer_dismissed(user["id"])
        st.rerun()


if "disclaimer_seen" not in st.session_state:
    st.session_state.disclaimer_seen = auth.get_disclaimer_dismissed(user["id"])

if not st.session_state.disclaimer_seen:
    show_disclaimer_dialog()
    st.stop()

# ---------- Pipeline ----------
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
    st.caption(
        f"Signed in as {user.get('name') or user.get('phone') or user.get('email')}"
    )

    if st.button("Sign out", use_container_width=True):
        st.session_state.user = None
        st.session_state.pop("chat_id", None)
        st.session_state.pop("history", None)
        st.rerun()

    if st.button("+ New chat", use_container_width=True):
        st.session_state.chat_id = chat_store.new_chat_id()
        st.session_state.history = []
        st.rerun()

    if st.session_state.history:
        if st.button("🗑️ Clear current chat", use_container_width=True):
            st.session_state.history = []
            chat_store.save_chat(
                user["id"], st.session_state.chat_id, st.session_state.history
            )
            st.rerun()

    st.markdown("---")
    st.markdown("**Recent chats**")

    for chat in chat_store.list_chats(user["id"]):
        is_current = chat["id"] == st.session_state.chat_id
        label = ("• " if is_current else "") + chat["title"]
        if st.button(label, key=f"chat_{chat['id']}", use_container_width=True):
            st.session_state.chat_id = chat["id"]
            st.session_state.history = chat_store.load_chat(user["id"], chat["id"])
            st.rerun()


st.title("📖 KJV Bible Chatbot")
st.caption(
    "Ask a question or look up a verse. "
    "Answers come from the KJV Bible text you indexed."
)

render_history(st.session_state.history, verse_store)

question = st.chat_input("Ask about the KJV Bible...")

if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching the scriptures..."):
            passages = retriever.retrieve(question)

            answer_placeholder = st.empty()
            answer_parts = []

            try:
                for chunk in chain.answer_stream(question, passages):
                    answer_parts.append(chunk)
                    answer_placeholder.markdown("".join(answer_parts))
            except Exception:
                answer = (
                    "An unexpected error occurred while asking Gemini. "
                    "Please try again."
                )
                answer_parts = [answer]
                answer_placeholder.markdown(answer)

            answer = "".join(answer_parts)

    st.session_state.history.append({"role": "user", "content": question})
    st.session_state.history.append(
        {"role": "assistant", "content": answer, "sources": passages}
    )

    chat_store.save_chat(user["id"], st.session_state.chat_id, st.session_state.history)
    st.rerun()