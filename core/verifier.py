import logging
import os

from openai import OpenAI

from core.llm_client import call_llm_json

logger = logging.getLogger(__name__)


def verify_extraction(prompt: str, client: OpenAI) -> dict:
    """
    Runs the verification prompt through the LLM and returns the result.
    The prompt is built by the caller (domain-specific prompt builders in services/).
    Returns a dict with keys: passed (bool|None), flags (list), summary (str).
    Never raises — returns a safe fallback on any failure so the main flow continues.
    """
    model = os.environ.get("VERIFIER_MODEL", "gpt-4.1")
    try:
        result = call_llm_json(prompt, client, model)
        flag_count = len(result.get("flags", []))
        status = "PASSED" if result.get("passed") else f"FAILED ({flag_count} flag(s))"
        logger.info(f"Verification {status} — {result.get('summary', '')}")
        return result
    except Exception as e:
        logger.error(f"Verifier failed: {e}")
        return {"passed": None, "flags": [], "summary": f"Verifier error: {e}"}
