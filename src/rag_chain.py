"""
Wraps the Google Gemini API (via the current google-genai SDK) with a
strict, grounding-only system prompt so the model never answers from
outside knowledge or invents verses.

Also retries automatically on temporary server-side errors (like a
503 "high demand" response) with a short, increasing delay between
attempts - most of these clear up within a second or two, so a plain
retry often means the person never even notices the hiccup happened.
"""
import os
import time
from typing import Dict, List

from google import genai
from google.genai import errors as genai_errors

SYSTEM_INSTRUCTIONS = """You are a Bible study assistant that answers questions using ONLY the \
King James Version (KJV) Bible passages provided as context below.

Rules you MUST follow:
1. Only use information found in the provided passages. Never use outside \
knowledge, other Bible translations, or invented content.
2. Always cite the exact Bible reference (Book Chapter:Verse) for every \
claim, based only on the passages given.
3. If the provided passages do not contain enough information to answer \
the question, say clearly: "I don't have enough information in the KJV \
text I was given to answer that." Do not guess or fill gaps.
4. When quoting Scripture, use the exact KJV wording from the context - \
do not paraphrase it into modern English or another translation's wording.
5. Keep a respectful, neutral tone. Don't add theological interpretation \
beyond what the text itself says, unless the question explicitly asks you \
to explain a passage's plain meaning."""

# How many times to retry a request that fails with a temporary server
# error, and how long to wait before the first retry (doubling each time -
# e.g. 2s, then 4s - which is the standard "exponential backoff" pattern).
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2


class RAGChain:
    def __init__(self, api_key: str = None, model: str = "gemini-3.6-flash"):
        api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )
        self.client = genai.Client(api_key=api_key)
        self.model = model

    @staticmethod
    def _build_context(passages: List[Dict]) -> str:
        return "\n\n".join(f"[{p['reference']}] {p['text']}" for p in passages)

    def answer(self, question: str, passages: List[Dict]) -> str:
        if not passages:
            return "I don't have enough information in the KJV text I was given to answer that."

        context = self._build_context(passages)
        prompt = (
            f"{SYSTEM_INSTRUCTIONS}\n\n"
            f"KJV Bible passages:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer (cite references in the form Book Chapter:Verse):"
        )

        backoff = INITIAL_BACKOFF_SECONDS
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                )
                return response.text
            except genai_errors.ServerError:
                # A 5xx error (e.g. 503 "high demand") is temporary and
                # worth retrying. A 4xx error (bad key, bad request) would
                # raise ClientError instead - retrying that would just
                # fail the same way every time, so we deliberately don't
                # catch it here and let it surface immediately.
                if attempt == MAX_RETRIES:
                    return (
                        "Gemini is temporarily unavailable right now (the "
                        "servers are reporting high demand). Please try "
                        "asking again in a moment."
                    )
                time.sleep(backoff)
                backoff *= 2