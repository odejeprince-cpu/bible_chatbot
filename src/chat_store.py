"""
Simple file-based chat history storage - one JSON file per conversation,
saved under a top-level chats/ folder. No database needed for a
single-user local app; this is the "backend" piece that app.py (the
frontend) calls into.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List

CHATS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chats"
)


def _ensure_dir() -> None:
    Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)


def _path(chat_id: str) -> str:
    return os.path.join(CHATS_DIR, f"{chat_id}.json")


def new_chat_id() -> str:
    """A unique ID based on the current time, e.g. '1758100800123'."""
    return str(int(time.time() * 1000))


def _default_title(messages: List[Dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            text = m["content"].strip()
            return text[:40] + ("..." if len(text) > 40 else "")
    return "New chat"


def save_chat(chat_id: str, messages: List[Dict]) -> None:
    """Writes (or overwrites) one conversation's full message list to disk."""
    _ensure_dir()
    data = {
        "id": chat_id,
        "title": _default_title(messages),
        "updated_at": time.time(),
        "messages": messages,
    }
    with open(_path(chat_id), "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_chat(chat_id: str) -> List[Dict]:
    """Returns the message list for one saved conversation."""
    with open(_path(chat_id), "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("messages", [])


def list_chats() -> List[Dict]:
    """Returns [{'id', 'title', 'updated_at'}, ...], most recent first."""
    _ensure_dir()
    chats = []
    for fname in os.listdir(CHATS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHATS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            chats.append({
                "id": data["id"],
                "title": data.get("title") or "New chat",
                "updated_at": data.get("updated_at", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue  # skip any corrupted file rather than crashing the app
    chats.sort(key=lambda c: c["updated_at"], reverse=True)
    return chats