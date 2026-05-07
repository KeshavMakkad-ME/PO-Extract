import logging
import os

import pandas as pd
from openai import OpenAI

from config.rm_pm.field_map import LINE_ITEM_FIELDS
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

Extract fields from the vendor invoice text below and return ONLY a valid JSON object.
No explanation. No markdown. No code fences. Just raw JSON.

GENERAL RULES:
- If a field is not found, return empty string "" — never null
- Do not invent or guess values — only extract what is explicitly present
- Dates must be formatted as DD/MM/YYYY
- godown is the ship-to receiver / consignee company name (e.g. "AM Enterprises")
- freight_charges: if the invoice has a "Transportation Charges" line, extract that amount.
  It is an invoice-level field — do NOT create a line_item for transportation charges.

TAX RULES:
- Identify the tax type from the invoice tax summary (IGST only = inter-state; CGST+SGST = intra-state).
- For inter-state invoices: populate igst_name (e.g. "Input IGST 18%"), leave cgst_name and sgst_name as "".
- For intra-state invoices: populate cgst_name and sgst_name, leave igst_name as "".
- Tax name format: "Input <TAX TYPE> <RATE>%" — e.g. "Input IGST 18%", "Input CGST 9%".
- Per-batch tax amounts must be COMPUTED (the invoice only shows totals):
    igst_amount  = round(taxable_amount × igst_rate  / 100, 2)   [0 if not applicable]
    cgst_amount  = round(taxable_amount × cgst_rate  / 100, 2)   [0 if not applicable]
    sgst_amount  = round(taxable_amount × sgst_rate  / 100, 2)   [0 if not applicable]
- Repeat the same tax name(s) on every batch row for the same product.

BATCH / LINE-ITEM RULES — READ CAREFULLY:
- A product that appears with multiple batch numbers must produce ONE line_item object PER BATCH.
  Do this even if the product name and rate are identical across batches.
- billed_quantity is the weight/quantity for THAT specific batch — NOT the product total.
- taxable_amount = billed_quantity × item_rate  (compute it — do not copy from any invoice total).
- A product that has NO batch breakdown → one line_item for the full quantity with batch_number = "".
- item_rate is the base rate EXCLUDING tax (use the "Rate per KGS/Unit" column, not "Rate Incl. of Tax").

EXAMPLE — how to handle an invoice with two products, one having two batches:
  Product 1: Sunova JNR, HSN 33049990, Rate 4100/KGS, IGST 18%
    Batch GC26/DI/JNR/111  195 KGS
    Batch GC26/DI/JNR/112  255 KGS
  Product 2: Gurattivo BRN, HSN 29072990, 50 KGS, Rate 17000/KGS, IGST 18%  (no batches)
  Transportation Charges 3500

  Correct line_items output (3 rows):
  [
    {{ "item_name": "Sunova JNR", "batch_number": "GC26/DI/JNR/111", "billed_quantity": 195,
       "item_rate": 4100, "taxable_amount": 799500, "igst_name": "Input IGST 18%",
       "igst_amount": 143910, "cgst_name": "", "cgst_amount": 0, "sgst_name": "", "sgst_amount": 0,
       "manuf_date": "", "expire_date": "" }},
    {{ "item_name": "Sunova JNR", "batch_number": "GC26/DI/JNR/112", "billed_quantity": 255,
       "item_rate": 4100, "taxable_amount": 1045500, "igst_name": "Input IGST 18%",
       "igst_amount": 188190, "cgst_name": "", "cgst_amount": 0, "sgst_name": "", "sgst_amount": 0,
       "manuf_date": "", "expire_date": "" }},
    {{ "item_name": "Gurattivo BRN", "batch_number": "", "billed_quantity": 50,
       "item_rate": 17000, "taxable_amount": 850000, "igst_name": "Input IGST 18%",
       "igst_amount": 153000, "cgst_name": "", "cgst_amount": 0, "sgst_name": "", "sgst_amount": 0,
       "manuf_date": "", "expire_date": "" }}
  ]
  freight_charges = 3500  (at invoice level, NOT a line_item)

Return this exact JSON structure:

{{
{invoice_fields_block}
  "line_items": [
    {{
{item_fields_block}
    }}
  ]
}}

INVOICE TEXT:
{invoice_text}
"""


def extract_rm_pm_fields(invoice_text: str, config_df: pd.DataFrame, client: OpenAI) -> dict:
    prompt = build_extraction_prompt(config_df, invoice_text)
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    try:
        data = call_llm_json(prompt, client, model)
        logger.info(f"RM/PM extraction successful — {len(data.get('line_items', []))} line item(s)")
        return data
    except Exception as e:
        logger.error(f"RM/PM extraction failed: {e}")
        raise
