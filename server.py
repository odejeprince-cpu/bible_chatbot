"""
KJV Bible Chatbot - web server (FastAPI). Replaces the Streamlit app.

Run locally:   uvicorn server:app --reload --port 8000
Run on a host: uvicorn server:app --host 0.0.0.0 --port $PORT
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import traceback
import urllib.parse
from contextlib import asynccontextmanager, closing
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()  # must run before any src imports

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------- config
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "app_data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

SESSION_COOKIE = "bible_session"
STATE_COOKIE = "g_state"
SESSION_DAYS = 30

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
).strip()
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Secure cookies only work over https; derive from the redirect URI unless overridden.
COOKIE_SECURE = os.getenv(
    "COOKIE_SECURE", "1" if GOOGLE_REDIRECT_URI.startswith("https://") else "0"
).lower() in ("1", "true", "yes")


# ---------------------------------------------------------------- database
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                phone TEXT UNIQUE,
                email TEXT,
                google_id TEXT UNIQUE,
                password_hash TEXT,
                disclaimer_dismissed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New chat',
                messages TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chats_user
                ON chats(user_id, updated_at DESC);
            """
        )


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored) -> bool:
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def normalize_phone(raw: str) -> str:
    raw = (raw or "").strip()
    digits = "".join(c for c in raw if c.isdigit())
    return ("+" if raw.startswith("+") else "") + digits


# ---------------------------------------------------------------- sessions
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, time.time() + SESSION_DAYS * 86400),
        )
    return token


def delete_session(token: str) -> None:
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def user_for_token(token):
    if not token:
        return None
    with closing(db()) as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (_token_hash(token), time.time()),
        ).fetchone()
    return dict(row) if row else None


def attach_session(response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session(user_id),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def current_user(request: Request) -> dict:
    user = user_for_token(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"] or user["phone"] or user["email"] or "friend",
        "disclaimer_dismissed": bool(user["disclaimer_dismissed"]),
    }


# ---------------------------------------------------------------- chats
def new_chat_id() -> str:
    return secrets.token_hex(8)


def load_chat(user_id: int, chat_id: str):
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT id, title, messages FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
    if not row:
        return None
    return {"id": row["id"], "title": row["title"], "messages": json.loads(row["messages"])}


def save_chat(user_id: int, chat_id: str, title: str, messages: list) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            """INSERT INTO chats (id, user_id, title, messages, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   messages = excluded.messages,
                   updated_at = excluded.updated_at
               WHERE chats.user_id = excluded.user_id""",
            (chat_id, user_id, title, json.dumps(messages), time.time()),
        )


# ---------------------------------------------------------------- pipeline
_pipeline = None
_pipeline_lock = threading.Lock()


def get_pipeline():
    """Load the retriever + Gemini chain once, on first use."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from src.pipeline import load_pipeline

                _pipeline = load_pipeline()
    return _pipeline


def _warm_up() -> None:
    try:
        get_pipeline()
        print("Pipeline ready.", flush=True)
    except Exception:
        traceback.print_exc()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------------------------------------------------------- phone auth
class SignupBody(BaseModel):
    name: str = ""
    phone: str
    password: str


class LoginBody(BaseModel):
    phone: str
    password: str


class ChatBody(BaseModel):
    question: str
    chat_id: str | None = None


@app.post("/api/signup")
def signup(body: SignupBody):
    phone = normalize_phone(body.phone)
    if len(phone) < 7:
        raise HTTPException(400, "Please enter a valid phone number.")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    try:
        with closing(db()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO users (name, phone, password_hash) VALUES (?, ?, ?)",
                (body.name.strip(), phone, hash_password(body.password)),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That phone number already has an account.")
    resp = JSONResponse({"ok": True})
    attach_session(resp, user_id)
    return resp


@app.post("/api/login")
def login(body: LoginBody):
    phone = normalize_phone(body.phone)
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Incorrect phone number or password.")
    resp = JSONResponse({"ok": True})
    attach_session(resp, row["id"])
    return resp


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return public_user(user)


@app.post("/api/disclaimer/dismiss")
def dismiss_disclaimer(user: dict = Depends(current_user)):
    with closing(db()) as conn, conn:
        conn.execute(
            "UPDATE users SET disclaimer_dismissed = 1 WHERE id = ?", (user["id"],)
        )
    return {"ok": True}


# ---------------------------------------------------------------- google auth
def _redirect_with_error(message: str) -> RedirectResponse:
    resp = RedirectResponse(
        "/?auth_error=" + urllib.parse.quote(message), status_code=302
    )
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@app.get("/auth/google/login")
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return _redirect_with_error("Google sign-in is not set up on this server.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    resp = RedirectResponse(
        f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", status_code=302
    )
    resp.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True,
        samesite="lax", secure=COOKIE_SECURE, path="/",
    )
    return resp


@app.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return _redirect_with_error(f"Google sign-in was cancelled ({error}).")

    expected = request.cookies.get(STATE_COOKIE)
    if not code or not state or not expected or not hmac.compare_digest(state, expected):
        return _redirect_with_error("Sign-in expired. Please try again.")

    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if not token_resp.ok:
            print("Google token error", token_resp.status_code, token_resp.text, flush=True)
            try:
                body = token_resp.json()
                detail = body.get("error_description") or body.get("error") or "unknown error"
            except Exception:
                detail = token_resp.text[:200]
            return _redirect_with_error(f"Google rejected the sign-in: {detail}")

        access_token = token_resp.json()["access_token"]
        info = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        info.raise_for_status()
        profile = info.json()
        google_id = profile["sub"]
    except Exception:
        traceback.print_exc()
        return _redirect_with_error("Could not complete sign-in with Google. Please try again.")

    email = profile.get("email", "")
    name = profile.get("name", "")
    with closing(db()) as conn, conn:
        row = conn.execute("SELECT id FROM users WHERE google_id = ?", (google_id,)).fetchone()
        if row:
            user_id = row["id"]
            conn.execute(
                "UPDATE users SET email = ?, name = CASE WHEN name = '' THEN ? ELSE name END WHERE id = ?",
                (email, name, user_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO users (name, email, google_id) VALUES (?, ?, ?)",
                (name, email, google_id),
            )
            user_id = cur.lastrowid

    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    attach_session(resp, user_id)
    return resp


# ---------------------------------------------------------------- chat api
@app.get("/api/chats")
def list_chats(user: dict = Depends(current_user)):
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, title FROM chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT 100",
            (user["id"],),
        ).fetchall()
    return [{"id": r["id"], "title": r["title"]} for r in rows]


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, user: dict = Depends(current_user)):
    chat = load_chat(user["id"], chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found.")
    return chat


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, user: dict = Depends(current_user)):
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, user["id"]))
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatBody, user: dict = Depends(current_user)):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Please type a question.")
    if len(question) > 1000:
        raise HTTPException(400, "That question is too long (max 1000 characters).")

    try:
        retriever, chain, _verse_store = get_pipeline()
    except FileNotFoundError:
        raise HTTPException(
            503, "The Bible search index was not found on the server. Run build_index.py."
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(503, f"The chatbot could not start: {e}")

    existing = load_chat(user["id"], body.chat_id) if body.chat_id else None
    chat_id = existing["id"] if existing else new_chat_id()
    messages = existing["messages"] if existing else []
    title = existing["title"] if existing else (question[:40] + ("…" if len(question) > 40 else ""))

    def stream():
        parts = []
        try:
            passages = retriever.retrieve(question)
            for chunk in chain.answer_stream(question, passages):
                text = str(chunk)
                parts.append(text)
                yield text
        except Exception:
            traceback.print_exc()
            err = "Sorry, something went wrong while asking the model. Please try again."
            if parts:
                err = "\n\n" + err
            parts.append(err)
            yield err
        finally:
            answer = "".join(parts)
            if answer:
                try:
                    save_chat(
                        user["id"],
                        chat_id,
                        title,
                        messages
                        + [
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": answer},
                        ],
                    )
                except Exception:
                    traceback.print_exc()

    return StreamingResponse(
        stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Chat-Id": chat_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )