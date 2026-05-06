import json
import logging
import os

import pandas as pd
from openai import OpenAI

logger = logging.getLogger(__name__)

_LINE_ITEM_FIELDS = {
    "product_description", "hsn_code", "quantity", "unit_price",
    "eway_doc_no", "eway_date", "vehicle_number",
}


def get_openai_client() -> OpenAI:
    return OpenAI()  # reads OPENAI_API_KEY from environment automatically


def build_extraction_prompt(config_df: pd.DataFrame, po_text: str) -> str:
    extracted = config_df[config_df["source"] == "extracted"]
    po_level = extracted[~extracted["field_name"].isin(_LINE_ITEM_FIELDS)]
    item_level = extracted[extracted["field_name"].isin(_LINE_ITEM_FIELDS)]

    po_fields_block = ""
    for _, row in po_level.iterrows():
        po_fields_block += f'  "{row["field_name"]}": "",  // {row["description"]}\n'

    item_fields_block = ""
    for _, row in item_level.iterrows():
        item_fields_block += f'    "{row["field_name"]}": "",  // {row["description"]}\n'

    return f"""
You are a data extraction assistant for an Indian GST e-invoice system.

Extract fields from the Purchase Order text below and return ONLY a valid JSON object.
No explanation. No markdown. No code fences. Just raw JSON.

Rules:
- If a field is not found in the document, return empty string "" not null
- Do not invent or guess values — only extract what is explicitly present
- A PO can have multiple products — return one object per product in line_items array
- Dates must be formatted as DD/MM/YYYY
- Pincodes must be 6 digit numbers
- unit_price is Basic Cost Price — NOT landing rate, NOT MRP
- For fields that say "copy the exact same value as X" — copy that field value exactly

Return this exact JSON structure:

{{
{po_fields_block}
  "line_items": [
    {{
{item_fields_block}
    }}
  ]
}}

PURCHASE ORDER TEXT:
{po_text}
"""


def extract_po_fields(po_text: str, config_df: pd.DataFrame, client: OpenAI) -> dict:
    prompt = build_extraction_prompt(config_df, po_text)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        logger.info(f"Extraction successful — {len(data.get('line_items', []))} line item(s) found")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"OpenAI returned invalid JSON: {e}")
        raise

    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise
