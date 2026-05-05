import json
import logging
import os

import pandas as pd
from openai import OpenAI

logger = logging.getLogger(__name__)


def _build_verification_prompt(po_text: str, extracted_data: dict, config_df: pd.DataFrame) -> str:
    # Only verify extracted fields — derived fields are computed deterministically by code
    # and cannot be meaningfully checked against source text by an AI
    verifiable = config_df[config_df["source"] == "extracted"]
    verifiable_names = set(verifiable["field_name"].tolist())

    field_ctx = "\n".join(
        f'  - {row["field_name"]}: {row["description"]}'
        for _, row in verifiable.iterrows()
    )

    po_vals = {
        k: v for k, v in extracted_data.items()
        if k not in ("line_items",) and k in verifiable_names
    }

    items_parts = []
    for i, item in enumerate(extracted_data.get("line_items", []), 1):
        item_vals = {k: v for k, v in item.items() if k in verifiable_names}
        if item_vals:
            items_parts.append(f"Line Item {i}: {json.dumps(item_vals, ensure_ascii=False)}")

    extracted_block = json.dumps(po_vals, ensure_ascii=False, indent=2)
    if items_parts:
        extracted_block += "\n\n" + "\n".join(items_parts)

    return f"""You are a strict financial data auditor verifying AI-extracted Purchase Order data.
This data will be used for Indian GST e-invoicing — accuracy is critical.

FIELD REFERENCE (what each field is supposed to contain):
{field_ctx}

EXTRACTED DATA:
{extracted_block}

ORIGINAL SOURCE DOCUMENT:
{po_text}

VERIFICATION RULES:
1. The following are all ACCEPTABLE format differences — do NOT flag them:
   - Dates: any date extracted as DD/MM/YYYY is acceptable regardless of how the source formats it, including with time components, written months, etc.
   - Capitalisation, punctuation, extra whitespace
   - Address/location abbreviations or common city-level variants (e.g. "Bengaluru" for "Bengaluru Urban", "Pune" for a suburb/locality within Pune district)
   - Partial addresses that capture the essential identifying information
2. Critical differences that MUST be flagged: a completely different number (e.g. wrong invoice number digits), a completely different name, a wrong GSTIN where individual characters differ from what is printed in the document
3. Do NOT flag empty string values ("") — they legitimately indicate the field was not found
4. ANTI-HALLUCINATION — most important rule: before flagging any field, you MUST quote the exact verbatim text from the source document that directly contradicts the extracted value. Include that quote in the issue field as: 'Source text: "..."'. If you cannot find and quote conflicting source text, do NOT flag it under any circumstances.
5. Never infer what the source "should" say — only flag what it actually does say, and only when it clearly contradicts the extracted value
6. Do NOT reason about whether dates, years, or values are plausible, real, or in the future. Your only job is text comparison. If the source says 2026 and the extraction says 2026, they match — full stop.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "passed": true,
  "flags": [],
  "summary": "All extracted values verified against source document"
}}

If issues are found:
{{
  "passed": false,
  "flags": [
    {{
      "field": "invoice_number",
      "extracted_value": "PO-12345",
      "issue": "Source text: \\"P.O. Number : INV-12345\\" — different prefix, not a format difference",
      "severity": "critical"
    }}
  ],
  "summary": "1 critical issue found"
}}
"""


def verify_extraction(
    po_text: str,
    extracted_data: dict,
    config_df: pd.DataFrame,
    client: OpenAI,
) -> dict:
    """
    Calls a separate AI pass to verify extracted values against the original PO text.
    Only checks 'extracted' source fields — derived fields are computed deterministically
    by code and cannot be meaningfully verified by AI against source text.
    Returns a dict with keys: passed (bool|None), flags (list), summary (str).
    """
    prompt = _build_verification_prompt(po_text, extracted_data, config_df)
    model = os.environ.get("VERIFIER_MODEL", "gpt-4.1")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        flag_count = len(result.get("flags", []))
        status = "PASSED" if result.get("passed") else f"FAILED ({flag_count} flag(s))"
        logger.info(f"Verification {status} — {result.get('summary', '')}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Verifier returned invalid JSON: {e}")
        return {"passed": None, "flags": [], "summary": f"Verifier parse error: {e}"}

    except Exception as e:
        logger.error(f"Verifier API call failed: {e}")
        return {"passed": None, "flags": [], "summary": f"Verifier error: {e}"}
