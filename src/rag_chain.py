import os
import time
from typing import Dict, List, Generator

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

SYSTEM_INSTRUCTIONS = """You are a Bible study assistant that answers questions using ONLY the King James Version (KJV) Bible passages provided as context below.

Rules you MUST follow:
1. Only use information found in the provided passages. Never use outside knowledge, other Bible translations, or invented content.
2. Always cite the exact Bible reference (Book Chapter:Verse) for every claim, based only on the passages given.
3. If the provided passages do not contain enough information to answer the question, say clearly: "I don't have enough information in the KJV text I was given to answer that." Do not guess or fill gaps.
4. When quoting Scripture, use the exact KJV wording from the context - do not paraphrase it into modern English or another translation's wording.
5. Keep a respectful, neutral tone. Don't add theological interpretation beyond what the text itself says, unless the question explicitly asks you to explain a passage's plain meaning.
"""

MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1


class RAGChain:
    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-3.6-flash",
        timeout_ms: int = 30_000,
    ):
        api_key = api_key or os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Add it to your .env file."
            )

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self.model = model

    @staticmethod
    def _build_context(passages: List[Dict]) -> str:
        return "\n\n".join(
            f"[{p['reference']}] {p['text']}"
            for p in passages
        )

    @staticmethod
    def _client_error_message(error: genai_errors.ClientError) -> str:
        """Return safe, actionable guidance without exposing API details."""
        if error.code in (401, 403):
            return (
                "Gemini denied access. Check that GOOGLE_API_KEY is a valid "
                "Google AI Studio key with Gemini API access."
            )
        if error.code == 404:
            return (
                "The configured Gemini model is not available to this API "
                "key. Check the model name and the key's Gemini access."
            )
        if error.code == 429:
            return (
                "Gemini's request limit or quota has been reached. Wait a "
                "moment, or review your Gemini API quota and billing."
            )
        if error.code == 400:
            return (
                "Gemini rejected the request format. Check the model "
                "configuration and try again."
            )
        return f"Gemini rejected this request (HTTP {error.code}). Please try again."

    def answer_stream(
        self,
        question: str,
        passages: List[Dict]
    ) -> Generator[str, None, None]:

        if not passages:
            yield (
                "I don't have enough information in the KJV text "
                "I was given to answer that."
            )
            return

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
                response = self.client.models.generate_content_stream(
                    model=self.model,
                    contents=prompt,
                )

                for chunk in response:
                    if chunk.text:
                        yield chunk.text

                return

            except (genai_errors.ServerError, httpx.TimeoutException):

                if attempt == MAX_RETRIES:
                    yield (
                        "Gemini did not respond in time. Please try again "
                        "in a moment."
                    )
                    return

                time.sleep(backoff)
                backoff *= 2

            except httpx.NetworkError:
                yield (
                    "I could not connect to Gemini. Check that this computer "
                    "has internet access and that its DNS, firewall, proxy, "
                    "or VPN allows access to Google's Gemini API."
                )
                return

            except genai_errors.ClientError as error:
                yield self._client_error_message(error)
                return
