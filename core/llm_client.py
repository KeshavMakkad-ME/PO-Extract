import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_openai_client() -> OpenAI:
    return OpenAI()  # reads OPENAI_API_KEY from environment


def call_llm_json(prompt: str, client: OpenAI, model: str) -> dict:
    """
    Single place where all LLM JSON calls are made.
    Raises on any error — callers decide how to handle failures.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    return json.loads(raw)
