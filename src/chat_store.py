"""
Simple file-based chat history storage - one JSON file per conversation,
saved under chats/<user_id>/. Each signed-in user gets their own folder.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List

CHATS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chats"
)


def _user_dir(user_id: str) -> str:
    return os.path.join(CHATS_DIR, user_id)


def _ensure_dir(user_id: str) -> None:
    Path(_user_dir(user_id)).mkdir(parents=True, exist_ok=True)


def _path(user_id: str, chat_id: str) -> str:
    return os.path.join(_user_dir(user_id), f"{chat_id}.json")


def new_chat_id() -> str:
    """A unique ID based on the current time, e.g. '1758100800123'."""
    return str(int(time.time() * 1000))


def _default_title(messages: List[Dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            text = m["content"].strip()
            return text[:40] + ("..." if len(text) > 40 else "")
    return "New chat"


def save_chat(user_id: str, chat_id: str, messages: List[Dict]) -> None:
    """Writes (or overwrites) one conversation's full message list to disk."""
    _ensure_dir(user_id)
    data = {
        "id": chat_id,
        "title": _default_title(messages),
        "updated_at": time.time(),
        "messages": messages,
    }
    with open(_path(user_id, chat_id), "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_chat(user_id: str, chat_id: str) -> List[Dict]:
    """Returns the message list for one saved conversation."""
    with open(_path(user_id, chat_id), "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("messages", [])


def list_chats(user_id: str) -> List[Dict]:
    """Returns [{'id', 'title', 'updated_at'}, ...], most recent first."""
    _ensure_dir(user_id)
    chats = []
    for fname in os.listdir(_user_dir(user_id)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(
                os.path.join(_user_dir(user_id), fname), "r", encoding="utf-8"
            ) as f:
                data = json.load(f)
            chats.append(
                {
                    "id": data["id"],
                    "title": data.get("title") or "New chat",
                    "updated_at": data.get("updated_at", 0),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue  # skip any corrupted file rather than crashing the app
    chats.sort(key=lambda c: c["updated_at"], reverse=True)
    return chats