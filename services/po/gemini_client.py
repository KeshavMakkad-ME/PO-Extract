import logging
import os

import pandas as pd
from openai import OpenAI

from core.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_LINE_ITEM_FIELDS = {
    "product_description", "hsn_code", "quantity", "unit_price",
    "eway_doc_no", "eway_date", "vehicle_number",
}


_BLINKIT_ADDRESS_GUIDANCE = """
ADDRESS RULES (Blinkit PO format):
- The document has a "Vendor" section (top-left) — that is BTM Ventures (us, the seller). Do NOT extract party fields from there.
- The "Delivered To" section is Blink Commerce (the buyer/party).
- party_gstin, party_trade_name, party_legal_name, party_address1, party_location, party_pincode
  → ALL come from the "Delivered To" section.
- ship_to_trade_name, ship_to_address1, ship_to_location, ship_to_pincode
  → also come from the "Delivered To" section (same location as party).
"""

_FLIPKART_ADDRESS_GUIDANCE = """
ADDRESS RULES (Flipkart Stock Transfer Invoice format):
The document has four labelled blocks: "Ship To", "Shipped From", "Bill To", "Bill From".
- party_gstin, party_trade_name, party_legal_name, party_address1, party_location, party_pincode
  → ALL come from the "Bill To" section ONLY.
- ship_to_gstin, ship_to_trade_name, ship_to_name, ship_to_address1, ship_to_location, ship_to_pincode
  → ALL come from the "Ship To" section ONLY.
- "Bill From" and "Shipped From" are OUR address (the seller) — NEVER use these for party_* or ship_to_* fields.
"""


def build_extraction_prompt(config_df: pd.DataFrame, po_text: str, company: str = "blinkit") -> str:
    extracted = config_df[config_df["source"] == "extracted"]
    po_level = extracted[~extracted["field_name"].isin(_LINE_ITEM_FIELDS)]
    item_level = extracted[extracted["field_name"].isin(_LINE_ITEM_FIELDS)]

    po_fields_block = ""
    for _, row in po_level.iterrows():
        po_fields_block += f'  "{row["field_name"]}": "",  // {row["description"]}\n'

    item_fields_block = ""
    for _, row in item_level.iterrows():
        item_fields_block += f'    "{row["field_name"]}": "",  // {row["description"]}\n'

    address_guidance = _FLIPKART_ADDRESS_GUIDANCE if company == "flipkart" else _BLINKIT_ADDRESS_GUIDANCE

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
{address_guidance}

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


def extract_po_fields(po_text: str, config_df: pd.DataFrame, client: OpenAI, company: str = "blinkit") -> dict:
    prompt = build_extraction_prompt(config_df, po_text, company)
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    try:
        data = call_llm_json(prompt, client, model)
        logger.info(f"PO extraction successful — {len(data.get('line_items', []))} line item(s)")
        return data
    except Exception as e:
        logger.error(f"PO extraction failed: {e}")
        raise
