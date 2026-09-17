"""
Wraps the Google Gemini API (via the current google-genai SDK) with a
strict, grounding-only system prompt so the model never answers from
outside knowledge or invents verses.
"""
import os
from typing import Dict, List

from google import genai

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


class RAGChain:
    def __init__(self, api_key: str = None, model: str = "gemini-2.0-flash"):
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

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text