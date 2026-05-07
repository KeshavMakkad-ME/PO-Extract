import json

import pandas as pd


def build_verification_prompt(invoice_text: str, extracted_data: dict, config_df: pd.DataFrame) -> str:
    verifiable = config_df[config_df["source"] == "extracted"]
    verifiable_names = set(verifiable["field_name"].tolist())

    field_ctx = "\n".join(
        f'  - {row["field_name"]}: {row["description"]}'
        for _, row in verifiable.iterrows()
    )

    inv_vals = {
        k: v for k, v in extracted_data.items()
        if k not in ("line_items",) and k in verifiable_names
    }

    items_parts = []
    for i, item in enumerate(extracted_data.get("line_items", []), 1):
        item_vals = {k: v for k, v in item.items() if k in verifiable_names}
        if item_vals:
            items_parts.append(f"Line Item {i}: {json.dumps(item_vals, ensure_ascii=False)}")

    extracted_block = json.dumps(inv_vals, ensure_ascii=False, indent=2)
    if items_parts:
        extracted_block += "\n\n" + "\n".join(items_parts)

    return f"""You are a strict financial data auditor verifying AI-extracted vendor invoice data.
This data will be recorded in Tally for GST accounting — accuracy directly affects stock,
tax credits, and financial reporting.

You are specifically auditing a vendor/supplier invoice. Pay close attention to:
- supplier_invoice_number: must match the invoice number exactly as printed by the vendor
- supplier_invoice_date: must match the date printed on the vendor's invoice
- party_name: must match the supplier/vendor name as printed on the invoice
- item_name: must match the product description as printed
- billed_quantity and item_rate: must match exactly — these affect stock valuation
- taxable_amount: pre-tax line item value — verify it matches what is printed
- cgst_amount / sgst_amount / igst_amount: must match the tax amounts on the invoice
- batch_number: must match the batch/lot number exactly — critical for traceability
- manuf_date and expire_date: must match manufacturing and expiry dates printed on invoice

FIELD REFERENCE (what each field is supposed to contain):
{field_ctx}

EXTRACTED DATA:
{extracted_block}

ORIGINAL VENDOR INVOICE TEXT:
{invoice_text}

VERIFICATION RULES:
1. ACCEPTABLE format differences — do NOT flag:
   - Dates reformatted to DD/MM/YYYY from any source format (including timestamps, written months)
   - Capitalisation, punctuation, extra whitespace
   - Common abbreviations for units (e.g. "Nos" vs "Numbers", "Kgs" vs "Kilograms")
   - Tax name formatting variations (e.g. "IGST @ 18%" vs "Input IGST 18%" — both refer to the same tax)
2. MUST flag — critical differences:
   - Wrong supplier invoice number (digit or character mismatch)
   - Quantity or rate that clearly differs from what is printed on the invoice
   - Batch number mismatch — even a single character difference
   - A tax amount that differs from what is printed on the invoice
3. Do NOT flag empty string values ("") — they legitimately mean the field was absent on the invoice
4. ANTI-HALLUCINATION — most important rule: before flagging any field, you MUST quote the exact
   verbatim text from the invoice that contradicts the extracted value.
   Include it as: 'Source text: "..."'. If you cannot find and quote conflicting source text,
   do NOT flag under any circumstances.
5. Only flag what the invoice actually says — never infer or assume what it "should" say.
6. Do NOT reason about plausibility of dates, batch numbers, or amounts. Your only job is text comparison.
7. FLAGS ARRAY = PROBLEMS ONLY. It is NOT a verification log.
   Before writing your response, scan every entry you planned to put in flags.
   DELETE any entry whose issue text contains "matches", "no issue", "consistent",
   "correct", "appears under", "matching", or any synonym meaning "this is fine".
   If that removes all entries, output "flags": [].
   A flags entry that says anything other than a genuine problem MUST be removed.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "passed": true,
  "flags": [],
  "summary": "All invoice fields verified against source document"
}}

If issues are found:
{{
  "passed": false,
  "flags": [
    {{
      "field": "batch_number",
      "extracted_value": "GC26/DI/JNR/124",
      "issue": "Source text: \\"Batch No: GC26/DI/JNR/125\\" — last digit differs",
      "severity": "critical"
    }}
  ],
  "summary": "1 critical issue found"
}}
"""
