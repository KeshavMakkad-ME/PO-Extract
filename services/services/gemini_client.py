import logging
import os

import pandas as pd
from openai import OpenAI

from config.services.field_map import LINE_ITEM_FIELDS
from core.llm_client import call_llm_json

logger = logging.getLogger(__name__)


def build_extraction_prompt(config_df: pd.DataFrame, invoice_text: str) -> str:
    extracted = config_df[config_df["source"] == "extracted"]
    invoice_level = extracted[~extracted["field_name"].isin(LINE_ITEM_FIELDS)]
    item_level = extracted[extracted["field_name"].isin(LINE_ITEM_FIELDS)]

    invoice_fields_block = ""
    for _, row in invoice_level.iterrows():
        invoice_fields_block += f'  "{row["field_name"]}": "",  // {row["description"]}\n'

    item_fields_block = ""
    for _, row in item_level.iterrows():
        item_fields_block += f'    "{row["field_name"]}": "",  // {row["description"]}\n'

    return f"""
You are a data extraction assistant for an Indian accounting system (Tally).

Extract fields from the service invoice text below and return ONLY a valid JSON object.
No explanation. No markdown. No code fences. Just raw JSON.

GENERAL RULES:
- If a field is not found, return empty string "" — never null
- Do not invent or guess values — only extract what is explicitly present
- Dates must be formatted as DD/MM/YYYY
- party_name is the vendor/supplier name as printed on the invoice header

TAX RULES:
- These are service invoices — GST is typically IGST (inter-state).
- igst_amount is the IGST tax amount for each line item.
- If the invoice shows only a total IGST and has multiple line items, compute per-line
  igst_amount proportionally: igst_amount = round(purchase_amount / total_taxable * total_igst, 2)

LINE-ITEM RULES:
- Each distinct service charge, product, or billing line on the invoice is ONE line_item.
- purchase_amount is the taxable (pre-GST) amount for that specific charge.
- igst_amount is the IGST amount for that specific charge.
- If the invoice has only one total charge with no breakdown, produce a single line_item.

EXAMPLE — invoice with two service lines:
  Meta Ads - HR Campaign:  taxable 1000, IGST 180
  Meta Ads - Brand Campaign: taxable 500, IGST 90

  Correct output:
  {{
    "supplier_invoice_number": "ADS607-105342671",
    "supplier_invoice_date": "20/01/2026",
    "party_name": "Meta Platforms Inc.",
    "voucher_type": "",
    "purchase_ledger": "",
    "line_items": [
      {{"purchase_amount": 1000, "igst_amount": 180}},
      {{"purchase_amount": 500,  "igst_amount": 90}}
    ]
  }}

Return this exact JSON structure:

{{
{invoice_fields_block}  "line_items": [
    {{
{item_fields_block}    }}
  ]
}}

INVOICE TEXT:
{invoice_text}
"""


def extract_services_fields(invoice_text: str, config_df: pd.DataFrame, client: OpenAI) -> dict:
    prompt = build_extraction_prompt(config_df, invoice_text)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    try:
        data = call_llm_json(prompt, client, model)
        logger.info(f"Services extraction successful — {len(data.get('line_items', []))} line item(s)")
        return data
    except Exception as e:
        logger.error(f"Services extraction failed: {e}")
        raise
