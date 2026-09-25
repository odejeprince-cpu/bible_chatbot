"""
Local user accounts (SQLite) - supports Google sign-in and manual
phone number + password accounts. Apple Sign-In isn't wired up yet;
it needs a paid Apple Developer account, ping me when you're ready.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from typing import Optional, Dict

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.db"
)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            phone TEXT UNIQUE,
            password_hash TEXT,
            password_salt TEXT,
            google_id TEXT UNIQUE,
            name TEXT,
            email TEXT,
            created_at REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT,
            created_at REAL,
            expires_at REAL
        )
        """
    )
    conn.commit()
    conn.close()


def _hash_password(password: str, salt: Optional[str] = None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    )
    return digest.hex(), salt


def _new_user_id() -> str:
    return secrets.token_hex(12)


def create_user_with_phone(phone: str, password: str, name: str = "") -> Dict:
    """Creates a manual account. Raises ValueError if the phone is taken."""
    init_db()
    conn = _connect()
    existing = conn.execute(
        "SELECT id FROM users WHERE phone = ?", (phone,)
    ).fetchone()
    if existing:
        conn.close()
        raise ValueError("An account with that phone number already exists.")

    password_hash, salt = _hash_password(password)
    user_id = _new_user_id()
    conn.execute(
        """
        INSERT INTO users (id, phone, password_hash, password_salt, name, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, phone, password_hash, salt, name, time.time()),
    )
    conn.commit()
    conn.close()
    return {"id": user_id, "phone": phone, "name": name}


def verify_phone_login(phone: str, password: str) -> Optional[Dict]:
    init_db()
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    if row is None:
        return None
    check_hash, _ = _hash_password(password, row["password_salt"])
    if not hmac.compare_digest(check_hash, row["password_hash"]):
        return None
    return {"id": row["id"], "phone": row["phone"], "name": row["name"]}


def get_or_create_google_user(google_id: str, email: str, name: str) -> Dict:
    """Looks up a user by google_id, creating one on first sign-in."""
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()
    if row:
        conn.close()
        return {"id": row["id"], "email": row["email"], "name": row["name"]}

    user_id = _new_user_id()
    conn.execute(
        """
        INSERT INTO users (id, google_id, email, name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, google_id, email, name, time.time()),
    )
    conn.commit()
    conn.close()
    return {"id": user_id, "email": email, "name": name}


def get_user_by_id(user_id: str) -> Optional[Dict]:
    init_db()
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "phone": row["phone"],
        "email": row["email"],
        "name": row["name"],
    }


def create_session(user_id: str, days_valid: int = 30) -> str:
    """Creates a long-lived session token for 'remember me' via cookie."""
    init_db()
    conn = _connect()
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, now + days_valid * 86400),
    )
    conn.commit()
    conn.close()
    return token


def get_user_id_for_session(token: str) -> Optional[str]:
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if row["expires_at"] < time.time():
        delete_session(token)
        return None
    return row["user_id"]


def delete_session(token: str) -> None:
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def _ensure_disclaimer_column() -> None:
    """One-time migration for databases created before this column existed."""
    conn = _connect()
    try:
        conn.execute(
            "ALTER TABLE users ADD COLUMN disclaimer_dismissed INTEGER DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.close()


def get_disclaimer_dismissed(user_id: str) -> bool:
    init_db()
    _ensure_disclaimer_column()
    conn = _connect()
    row = conn.execute(
        "SELECT disclaimer_dismissed FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row and row["disclaimer_dismissed"])


def set_disclaimer_dismissed(user_id: str) -> None:
    init_db()
    _ensure_disclaimer_column()
    conn = _connect()
    conn.execute(
        "UPDATE users SET disclaimer_dismissed = 1 WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()